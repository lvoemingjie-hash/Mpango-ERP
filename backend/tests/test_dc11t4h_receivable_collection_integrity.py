from __future__ import annotations

import asyncio
import importlib.util
import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from api.v1.finance import get_receivables_summary
from api.v1.orders import pay_order
from core.security import TokenPayload
from database.session import AsyncSessionLocal
from schemas.finance import ReceivablesSummaryResponse
from schemas.order import PayOrderRequest
from tests.test_dc11d_payment_replay_concurrency_integrity import (
    _Token,
    _bootstrap_minimal_tenant_schema,
    _pay_in_new_session,
    _seed_confirmed_order,
    _set_search_path,
    _snapshot,
    _tenant_id,
    _tenant_schema,
)
from tests.async_test_utils import temporary_database_url


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_035 = BACKEND_DIR / "alembic" / "versions" / "035_receivable_collection_integrity.py"
CANONICAL_BINDING_CHECK = (
    "ck_wrb_outstanding_balance_non_negative"
)


@pytest.fixture
def migration_database_url():
    if os.environ.get("MPANGO_ALLOW_TEMP_DB_CREATE") != "1":
        pytest.skip("set MPANGO_ALLOW_TEMP_DB_CREATE=1 for migration database tests")
    source_url = os.environ.get("TEST_DATABASE_URL")
    if not source_url:
        pytest.skip("TEST_DATABASE_URL is required for migration database tests")
    with temporary_database_url(source_url, "dc11t4h") as database_url:
        yield database_url


def _engine(database_url: str):
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return create_engine(sync_url, future=True)


def _load_migration_035():
    spec = importlib.util.spec_from_file_location("dc11t4h_migration_035", MIGRATION_035)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration_035(connection) -> None:
    module = _load_migration_035()
    migration_context = MigrationContext.configure(connection)
    operations = Operations(migration_context)
    original_op = module.op
    module.op = operations
    try:
        module.upgrade()
    finally:
        module.op = original_op


async def _pay(
    session,
    *,
    order_id: uuid.UUID,
    token: _Token,
    amount: Decimal,
    method: str,
    key: str,
    transaction_id: str | None = None,
):
    return await pay_order(
        order_id=str(order_id),
        token=token,
        db=session,
        payment_input=PayOrderRequest(
            amount=amount,
            method=method,
            transaction_id=transaction_id,
        ),
        x_idempotency_key=key,
    )


async def _clear_current_tenant_public_balances(session) -> None:
    await session.execute(
        text(
            "DELETE FROM public.wholesaler_retailer_bindings "
            "WHERE wholesaler_id = :tenant_id"
        ),
        {"tenant_id": _tenant_id(session)},
    )


@pytest.mark.asyncio
async def test_ordinary_cash_and_transfer_from_zero_binding_remain_zero(async_session):
    await _clear_current_tenant_public_balances(async_session)
    tenant_id = _tenant_id(async_session)

    cash_order, cash_retailer, cash_token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    await _pay(
        async_session,
        order_id=cash_order,
        token=cash_token,
        amount=Decimal("100.00"),
        method="cash",
        key="dc11t4h-cash-zero",
    )
    cash_snapshot = await _snapshot(
        async_session,
        order_id=cash_order,
        tenant_id=tenant_id,
        retailer_id=cash_retailer,
    )
    assert cash_snapshot["order_status"] == "paid"
    assert Decimal(str(cash_snapshot["outstanding_balance"])) == Decimal("0.00")

    transfer_order, transfer_retailer, transfer_token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("125.00")
    )
    await _pay(
        async_session,
        order_id=transfer_order,
        token=transfer_token,
        amount=Decimal("125.00"),
        method="transfer",
        key="dc11t4h-transfer-zero",
        transaction_id="DC11T4H-XFER-ZERO",
    )
    transfer_snapshot = await _snapshot(
        async_session,
        order_id=transfer_order,
        tenant_id=tenant_id,
        retailer_id=transfer_retailer,
    )
    assert transfer_snapshot["order_status"] == "paid"
    assert Decimal(str(transfer_snapshot["outstanding_balance"])) == Decimal("0.00")


@pytest.mark.asyncio
async def test_credit_sale_partial_final_collection_and_finance_summary(async_session):
    await _clear_current_tenant_public_balances(async_session)
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )

    credit_response = await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("100.00"),
        method="credit",
        key="dc11t4h-credit-sale",
    )
    credit_snapshot = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    assert credit_response.data["status"] == "paid"
    assert Decimal(str(credit_snapshot["outstanding_balance"])) == Decimal("100.00")

    await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("40.00"),
        method="cash",
        key="dc11t4h-credit-partial-collection",
    )
    partial_snapshot = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    assert partial_snapshot["order_status"] == "paid"
    assert Decimal(str(partial_snapshot["outstanding_balance"])) == Decimal("60.00")
    assert partial_snapshot["completed_count"] == 1
    assert Decimal(str(partial_snapshot["completed_total"])) == Decimal("40.00")
    assert partial_snapshot["ledger_count"] == 2
    assert Decimal(str(partial_snapshot["ledger_sum"])) == Decimal("0.0000")

    finance_response = await get_receivables_summary(
        token=TokenPayload(
            user_id=str(uuid.uuid4()),
            tenant_id=str(tenant_id),
            tenant_schema=str(async_session.info["tenant_schema"]),
        ),
        db=async_session,
    )
    summary = ReceivablesSummaryResponse.model_validate(finance_response.data)
    assert summary.total_outstanding == 60.0
    assert summary.credit_receivables == 60.0
    assert summary.by_retailer[0].outstanding_balance == 60.0
    assert summary.by_retailer[0].credit_receivables == 60.0

    final_response = await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("60.00"),
        method="transfer",
        key="dc11t4h-credit-final-collection",
        transaction_id="DC11T4H-XFER-FINAL",
    )
    final_snapshot = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    assert final_response.data["status"] == "paid"
    assert Decimal(str(final_snapshot["outstanding_balance"])) == Decimal("0.00")
    assert final_snapshot["order_status"] == "paid"
    assert final_snapshot["completed_count"] == 2
    assert Decimal(str(final_snapshot["completed_total"])) == Decimal("100.00")
    assert final_snapshot["ledger_count"] == 4
    assert Decimal(str(final_snapshot["ledger_sum"])) == Decimal("0.0000")


@pytest.mark.asyncio
async def test_over_collection_is_rejected_without_side_effects(async_session):
    await _clear_current_tenant_public_balances(async_session)
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("100.00"),
        method="credit",
        key="dc11t4h-overcollect-credit",
    )
    await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("40.00"),
        method="cash",
        key="dc11t4h-overcollect-partial",
    )
    before = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )

    with pytest.raises(HTTPException) as exc_info:
        await _pay(
            async_session,
            order_id=order_id,
            token=token,
            amount=Decimal("61.00"),
            method="cash",
            key="dc11t4h-overcollect-rejected",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "PAYMENT_EXCEEDS_REMAINING"
    after = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    assert after == before


@pytest.mark.asyncio
async def test_credit_collection_idempotent_replay_has_no_duplicate_ledger(async_session):
    await _clear_current_tenant_public_balances(async_session)
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("100.00"),
        method="credit",
        key="dc11t4h-idempotent-credit",
    )

    first = await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("25.00"),
        method="cash",
        key="dc11t4h-idempotent-collection",
    )
    replay = await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("25.00"),
        method="cash",
        key="dc11t4h-idempotent-collection",
    )
    snapshot = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )

    assert replay.data["payment_id"] == first.data["payment_id"]
    assert snapshot["payment_count"] == 2
    assert snapshot["ledger_count"] == 2
    assert Decimal(str(snapshot["outstanding_balance"])) == Decimal("75.00")


@pytest.mark.asyncio
async def test_concurrent_credit_collection_cannot_over_collect(async_session):
    await _clear_current_tenant_public_balances(async_session)
    schema = _tenant_schema(async_session)
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("100.00"),
        method="credit",
        key="dc11t4h-concurrent-credit",
    )
    await async_session.commit()

    results = await asyncio.gather(
        _pay_in_new_session(
            schema=schema,
            tenant_id=tenant_id,
            order_id=order_id,
            amount=Decimal("60.00"),
            method="cash",
            idempotency_key="dc11t4h-concurrent-a",
        ),
        _pay_in_new_session(
            schema=schema,
            tenant_id=tenant_id,
            order_id=order_id,
            amount=Decimal("60.00"),
            method="cash",
            idempotency_key="dc11t4h-concurrent-b",
        ),
    )

    successes = [result for result in results if not isinstance(result, HTTPException)]
    failures = [result for result in results if isinstance(result, HTTPException)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].status_code == 400
    assert failures[0].detail["code"] == "PAYMENT_EXCEEDS_REMAINING"

    await _set_search_path(async_session, schema)
    snapshot = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    assert snapshot["payment_count"] == 2
    assert snapshot["ledger_count"] == 2
    assert Decimal(str(snapshot["outstanding_balance"])) == Decimal("40.00")


@pytest.mark.asyncio
async def test_extra_payment_against_ordinary_paid_order_remains_rejected(async_session):
    await _clear_current_tenant_public_balances(async_session)
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    await _pay(
        async_session,
        order_id=order_id,
        token=token,
        amount=Decimal("100.00"),
        method="cash",
        key="dc11t4h-ordinary-paid",
    )
    before = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )

    with pytest.raises(HTTPException) as exc_info:
        await _pay(
            async_session,
            order_id=order_id,
            token=token,
            amount=Decimal("1.00"),
            method="cash",
            key="dc11t4h-ordinary-extra",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "ORDER_ALREADY_PAID"
    after = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    assert after == before


@pytest.mark.asyncio
async def test_credit_collections_are_isolated_across_tenants(async_session):
    await _clear_current_tenant_public_balances(async_session)
    first_schema = _tenant_schema(async_session)
    first_tenant_id = _tenant_id(async_session)
    second_schema = "t_33333333333333333333333333333333"
    second_tenant_id = uuid.UUID("33333333-3333-3333-3333-333333333333")

    first_order_id, first_retailer_id, first_token = await _seed_confirmed_order(
        async_session, tenant_id=first_tenant_id, total=Decimal("100.00")
    )
    await _pay(
        async_session,
        order_id=first_order_id,
        token=first_token,
        amount=Decimal("100.00"),
        method="credit",
        key="dc11t4h-isolation-credit-a",
    )

    async with AsyncSessionLocal() as setup_session:
        setup_session.info["tenant_schema"] = second_schema
        setup_session.info["tenant_id"] = str(second_tenant_id)
        await _bootstrap_minimal_tenant_schema(setup_session, second_schema)
        await setup_session.execute(
            text(
                "DELETE FROM public.wholesaler_retailer_bindings "
                "WHERE wholesaler_id = :tenant_id"
            ),
            {"tenant_id": second_tenant_id},
        )
        await setup_session.execute(
            text(
                f'TRUNCATE TABLE "{second_schema}".order_items, '
                f'"{second_schema}".payments, '
                f'"{second_schema}".ledger_entries, '
                f'"{second_schema}".orders '
                "RESTART IDENTITY CASCADE"
            )
        )
        await _set_search_path(setup_session, second_schema)
        second_order_id, second_retailer_id, second_token = await _seed_confirmed_order(
            setup_session, tenant_id=second_tenant_id, total=Decimal("100.00")
        )
        await _pay(
            setup_session,
            order_id=second_order_id,
            token=second_token,
            amount=Decimal("100.00"),
            method="credit",
            key="dc11t4h-isolation-credit-b",
        )
        await setup_session.commit()

    await _pay(
        async_session,
        order_id=first_order_id,
        token=first_token,
        amount=Decimal("40.00"),
        method="cash",
        key="dc11t4h-isolation-collect-a",
    )

    first_snapshot = await _snapshot(
        async_session,
        order_id=first_order_id,
        tenant_id=first_tenant_id,
        retailer_id=first_retailer_id,
    )
    async with AsyncSessionLocal() as second_session:
        second_session.info["tenant_schema"] = second_schema
        second_session.info["tenant_id"] = str(second_tenant_id)
        await _set_search_path(second_session, second_schema)
        second_snapshot = await _snapshot(
            second_session,
            order_id=second_order_id,
            tenant_id=second_tenant_id,
            retailer_id=second_retailer_id,
        )

    assert Decimal(str(first_snapshot["outstanding_balance"])) == Decimal("60.00")
    assert Decimal(str(second_snapshot["outstanding_balance"])) == Decimal("100.00")


def _ensure_public_migration_tables(connection) -> None:
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    connection.execute(text(
        """
        CREATE TABLE IF NOT EXISTS public.wholesalers (
            id UUID PRIMARY KEY,
            code VARCHAR(64) UNIQUE NOT NULL,
            name TEXT NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    ))
    connection.execute(text(
        """
        CREATE TABLE IF NOT EXISTS public.retailers (
            id UUID PRIMARY KEY,
            phone VARCHAR(64) UNIQUE NOT NULL,
            name TEXT NOT NULL,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    ))
    connection.execute(text(
        """
        CREATE TABLE IF NOT EXISTS public.tenant_registrations (
            id UUID PRIMARY KEY,
            company_name VARCHAR(255) NOT NULL,
            country VARCHAR(2) NOT NULL,
            owner_email VARCHAR(255) NOT NULL,
            status VARCHAR(40) NOT NULL DEFAULT 'provisioning',
            email_verified_at TIMESTAMP WITH TIME ZONE,
            provisioning_started_at TIMESTAMP WITH TIME ZONE,
            password_hash_cleared_at TIMESTAMP WITH TIME ZONE,
            wholesaler_id UUID,
            tenant_schema VARCHAR(64),
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    ))
    connection.execute(text(
        """
        CREATE TABLE IF NOT EXISTS public.wholesaler_retailer_bindings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wholesaler_id UUID NOT NULL,
            retailer_id UUID NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            outstanding_balance NUMERIC(12, 2) NOT NULL DEFAULT 0,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            UNIQUE (wholesaler_id, retailer_id)
        )
        """
    ))
    connection.execute(text(
        "ALTER TABLE public.wholesaler_retailer_bindings "
        f"DROP CONSTRAINT IF EXISTS {CANONICAL_BINDING_CHECK}"
    ))


def _create_migration_tenant_history(
    connection,
    *,
    schema: str,
    wholesaler_id: uuid.UUID,
    retailer_id: uuid.UUID,
) -> None:
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    connection.execute(text(
        f"""
        CREATE TABLE "{schema}".orders (
            id UUID PRIMARY KEY,
            wholesaler_id UUID NOT NULL,
            retailer_id UUID NOT NULL,
            total_amount NUMERIC(12, 2) NOT NULL,
            status VARCHAR(32) NOT NULL,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    ))
    connection.execute(text(
        f"""
        CREATE TABLE "{schema}".payments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id UUID NOT NULL,
            retailer_id UUID NOT NULL,
            amount NUMERIC(12, 2) NOT NULL,
            method VARCHAR(50) NOT NULL,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    ))
    order_id = uuid.uuid4()
    connection.execute(
        text(
            f'INSERT INTO "{schema}".orders '
            "(id, wholesaler_id, retailer_id, total_amount, status) "
            "VALUES (:order_id, :wholesaler_id, :retailer_id, 2325.00, 'paid')"
        ),
        {
            "order_id": order_id,
            "wholesaler_id": wholesaler_id,
            "retailer_id": retailer_id,
        },
    )
    connection.execute(
        text(
            f'INSERT INTO "{schema}".payments (order_id, retailer_id, amount, method) '
            "VALUES (:order_id, :retailer_id, 2325.00, 'cash')"
        ),
        {"order_id": order_id, "retailer_id": retailer_id},
    )


def _create_migration_credit_collection_history(
    connection,
    *,
    schema: str,
    wholesaler_id: uuid.UUID,
    retailer_id: uuid.UUID,
    credit_amount: Decimal,
    collection_amount: Decimal,
    order_total: Decimal | None = None,
    order_status: str = "paid",
) -> None:
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    connection.execute(text(
        f"""
        CREATE TABLE "{schema}".orders (
            id UUID PRIMARY KEY,
            wholesaler_id UUID NOT NULL,
            retailer_id UUID NOT NULL,
            total_amount NUMERIC(12, 2) NOT NULL,
            status VARCHAR(32) NOT NULL,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    ))
    connection.execute(text(
        f"""
        CREATE TABLE "{schema}".payments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id UUID NOT NULL,
            retailer_id UUID NOT NULL,
            amount NUMERIC(12, 2) NOT NULL,
            method VARCHAR(50) NOT NULL,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    ))
    order_id = uuid.uuid4()
    connection.execute(
        text(
            f'INSERT INTO "{schema}".orders '
            "(id, wholesaler_id, retailer_id, total_amount, status) "
            "VALUES (:order_id, :wholesaler_id, :retailer_id, :total_amount, :status)"
        ),
        {
            "order_id": order_id,
            "wholesaler_id": wholesaler_id,
            "retailer_id": retailer_id,
            "total_amount": order_total if order_total is not None else credit_amount,
            "status": order_status,
        },
    )
    for amount, method in (
        (credit_amount, "credit"),
        (collection_amount, "transfer"),
    ):
        connection.execute(
            text(
                f'INSERT INTO "{schema}".payments (order_id, retailer_id, amount, method) '
                "VALUES (:order_id, :retailer_id, :amount, :method)"
            ),
            {
                "order_id": order_id,
                "retailer_id": retailer_id,
                "amount": amount,
                "method": method,
            },
        )


def _insert_migration_public_contract_rows(
    connection,
    *,
    schema: str,
    wholesaler_id: uuid.UUID,
    retailer_id: uuid.UUID,
    balance: Decimal,
) -> None:
    connection.execute(
        text(
            "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
            "VALUES (:id, :code, 'DC11T4H Wholesaler', 'active', FALSE)"
        ),
        {"id": wholesaler_id, "code": f"DC11T4H{wholesaler_id.hex[:8].upper()}"},
    )
    connection.execute(
        text(
            "INSERT INTO public.retailers (id, phone, name, is_deleted) "
            "VALUES (:id, :phone, 'DC11T4H Retailer', FALSE)"
        ),
        {"id": retailer_id, "phone": f"dc11t4h-{retailer_id.hex[:20]}"},
    )
    connection.execute(
        text(
            "INSERT INTO public.tenant_registrations ("
            "id, company_name, country, owner_email, status, email_verified_at, "
            "provisioning_started_at, password_hash_cleared_at, wholesaler_id, "
            "tenant_schema, expires_at, is_deleted"
            ") VALUES ("
            ":id, 'DC11T4H Company', 'KE', :owner_email, 'active', now(), "
            "now(), now(), :wholesaler_id, :tenant_schema, now() + interval '1 hour', FALSE"
            ")"
        ),
        {
            "id": uuid.uuid4(),
            "owner_email": f"dc11t4h_{uuid.uuid4().hex}@example.com",
            "wholesaler_id": wholesaler_id,
            "tenant_schema": schema,
        },
    )
    connection.execute(
        text(
            "INSERT INTO public.wholesaler_retailer_bindings ("
            "wholesaler_id, retailer_id, status, outstanding_balance, is_deleted"
            ") VALUES (:wholesaler_id, :retailer_id, 'active', :balance, FALSE)"
        ),
        {
            "wholesaler_id": wholesaler_id,
            "retailer_id": retailer_id,
            "balance": balance,
        },
    )


def _migration_binding_balance(
    connection,
    *,
    wholesaler_id: uuid.UUID,
    retailer_id: uuid.UUID,
) -> Decimal:
    balance = connection.execute(
        text(
            "SELECT outstanding_balance "
            "FROM public.wholesaler_retailer_bindings "
            "WHERE wholesaler_id = :wholesaler_id AND retailer_id = :retailer_id"
        ),
        {"wholesaler_id": wholesaler_id, "retailer_id": retailer_id},
    ).scalar_one()
    return Decimal(str(balance))


def _cleanup_migration_rows(connection, *, schema: str, wholesaler_id: uuid.UUID, retailer_id: uuid.UUID) -> None:
    connection.execute(
        text("DELETE FROM public.tenant_registrations WHERE tenant_schema = :schema"),
        {"schema": schema},
    )
    connection.execute(
        text("DELETE FROM public.wholesaler_retailer_bindings WHERE wholesaler_id = :wholesaler_id"),
        {"wholesaler_id": wholesaler_id},
    )
    connection.execute(
        text("DELETE FROM public.retailers WHERE id = :retailer_id"),
        {"retailer_id": retailer_id},
    )
    connection.execute(
        text("DELETE FROM public.wholesalers WHERE id = :wholesaler_id"),
        {"wholesaler_id": wholesaler_id},
    )
    connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


def _assert_migration_history_fails_closed(
    migration_database_url: str,
    *,
    history_setup,
    error_match: str,
) -> None:
    wholesaler_id = uuid.uuid4()
    schema = f"t_{wholesaler_id.hex}"
    retailer_id = uuid.uuid4()
    initial_balance = Decimal("77.00")
    engine = _engine(migration_database_url)

    with engine.connect() as connection:
        try:
            _ensure_public_migration_tables(connection)
            _cleanup_migration_rows(
                connection,
                schema=schema,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
            )
            _insert_migration_public_contract_rows(
                connection,
                schema=schema,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
                balance=initial_balance,
            )
            history_setup(connection, schema, wholesaler_id, retailer_id)
            connection.commit()

            with pytest.raises(RuntimeError, match=error_match):
                _run_migration_035(connection)

            assert _migration_binding_balance(
                connection,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
            ) == initial_balance
        finally:
            connection.rollback()
            _cleanup_migration_rows(
                connection,
                schema=schema,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
            )
            connection.commit()


@pytest.mark.parametrize(
    ("credit_amount", "order_total", "order_status"),
    [
        (Decimal("60.00"), Decimal("100.00"), "paid"),
        (Decimal("100.00"), Decimal("100.00"), "confirmed"),
    ],
)
def test_migration_fails_closed_for_invalid_credit_sale_history(
    migration_database_url,
    credit_amount,
    order_total,
    order_status,
):
    def setup_history(connection, schema, wholesaler_id, retailer_id):
        _create_migration_credit_collection_history(
            connection,
            schema=schema,
            wholesaler_id=wholesaler_id,
            retailer_id=retailer_id,
            credit_amount=credit_amount,
            collection_amount=Decimal("0.00"),
            order_total=order_total,
            order_status=order_status,
        )

    _assert_migration_history_fails_closed(
        migration_database_url,
        history_setup=setup_history,
        error_match="invalid order settlement histories",
    )


def test_migration_fails_closed_for_overpaid_ordinary_order(migration_database_url):
    def setup_history(connection, schema, wholesaler_id, retailer_id):
        _create_migration_tenant_history(
            connection,
            schema=schema,
            wholesaler_id=wholesaler_id,
            retailer_id=retailer_id,
        )
        connection.execute(
            text(f'UPDATE "{schema}".payments SET amount = 3000.00')
        )

    _assert_migration_history_fails_closed(
        migration_database_url,
        history_setup=setup_history,
        error_match="invalid order settlement histories",
    )


def test_migration_fails_closed_for_registry_schema_mismatch(migration_database_url):
    wholesaler_id = uuid.uuid4()
    schema = f"t_{uuid.uuid4().hex}"
    retailer_id = uuid.uuid4()
    initial_balance = Decimal("-19.00")
    engine = _engine(migration_database_url)

    with engine.connect() as connection:
        try:
            _ensure_public_migration_tables(connection)
            _cleanup_migration_rows(
                connection,
                schema=schema,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
            )
            _insert_migration_public_contract_rows(
                connection,
                schema=schema,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
                balance=initial_balance,
            )
            _create_migration_tenant_history(
                connection,
                schema=schema,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
            )
            connection.commit()

            with pytest.raises(RuntimeError, match="tenant_schema does not match"):
                _run_migration_035(connection)

            assert _migration_binding_balance(
                connection,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
            ) == initial_balance
        finally:
            connection.rollback()
            _cleanup_migration_rows(
                connection,
                schema=schema,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
            )
            connection.commit()


def test_migration_fails_closed_for_over_collected_credit_history(migration_database_url):
    wholesaler_id = uuid.uuid4()
    schema = f"t_{wholesaler_id.hex}"
    retailer_id = uuid.uuid4()
    initial_balance = Decimal("-88.00")
    engine = _engine(migration_database_url)

    with engine.connect() as connection:
        try:
            _ensure_public_migration_tables(connection)
            _cleanup_migration_rows(
                connection,
                schema=schema,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
            )
            _insert_migration_public_contract_rows(
                connection,
                schema=schema,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
                balance=initial_balance,
            )
            _create_migration_credit_collection_history(
                connection,
                schema=schema,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
                credit_amount=Decimal("100.00"),
                collection_amount=Decimal("150.00"),
            )
            connection.commit()

            with pytest.raises(RuntimeError, match="over-collected credit orders"):
                _run_migration_035(connection)

            assert _migration_binding_balance(
                connection,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
            ) == initial_balance
        finally:
            connection.rollback()
            _cleanup_migration_rows(
                connection,
                schema=schema,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
            )
            connection.commit()


def test_migration_repairs_legacy_negative_cash_balance_and_adds_check(migration_database_url):
    wholesaler_id = uuid.uuid4()
    schema = f"t_{wholesaler_id.hex}"
    retailer_id = uuid.uuid4()
    engine = _engine(migration_database_url)

    with engine.connect() as connection:
        try:
            _ensure_public_migration_tables(connection)
            _cleanup_migration_rows(
                connection,
                schema=schema,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
            )
            connection.execute(
                text(
                    "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
                    "VALUES (:id, :code, 'DC11T4H Wholesaler', 'active', FALSE)"
                ),
                {"id": wholesaler_id, "code": f"DC11T4H{wholesaler_id.hex[:8].upper()}"},
            )
            connection.execute(
                text(
                    "INSERT INTO public.retailers (id, phone, name, is_deleted) "
                    "VALUES (:id, :phone, 'DC11T4H Retailer', FALSE)"
                ),
                {"id": retailer_id, "phone": f"dc11t4h-{retailer_id.hex[:20]}"},
            )
            connection.execute(
                text(
                    "INSERT INTO public.tenant_registrations ("
                    "id, company_name, country, owner_email, status, email_verified_at, "
                    "provisioning_started_at, password_hash_cleared_at, wholesaler_id, "
                    "tenant_schema, expires_at, is_deleted"
                    ") VALUES ("
                    ":id, 'DC11T4H Company', 'KE', :owner_email, 'active', now(), "
                    "now(), now(), :wholesaler_id, :tenant_schema, now() + interval '1 hour', FALSE"
                    ")"
                ),
                {
                    "id": uuid.uuid4(),
                    "owner_email": f"dc11t4h_{uuid.uuid4().hex}@example.com",
                    "wholesaler_id": wholesaler_id,
                    "tenant_schema": schema,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO public.wholesaler_retailer_bindings ("
                    "wholesaler_id, retailer_id, status, outstanding_balance, is_deleted"
                    ") VALUES (:wholesaler_id, :retailer_id, 'active', -2325.00, FALSE)"
                ),
                {"wholesaler_id": wholesaler_id, "retailer_id": retailer_id},
            )
            _create_migration_tenant_history(
                connection,
                schema=schema,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
            )
            connection.commit()

            _run_migration_035(connection)
            _run_migration_035(connection)
            connection.commit()

            balance = connection.execute(
                text(
                    "SELECT outstanding_balance "
                    "FROM public.wholesaler_retailer_bindings "
                    "WHERE wholesaler_id = :wholesaler_id AND retailer_id = :retailer_id"
                ),
                {"wholesaler_id": wholesaler_id, "retailer_id": retailer_id},
            ).scalar_one()
            assert Decimal(str(balance)) == Decimal("0.00")

            constraint_count = connection.execute(
                text(
                    "SELECT COUNT(*) FROM pg_constraint "
                    "WHERE conname = :constraint_name"
                ),
                {"constraint_name": CANONICAL_BINDING_CHECK},
            ).scalar_one()
            assert constraint_count == 1

            savepoint = connection.begin_nested()
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "UPDATE public.wholesaler_retailer_bindings "
                        "SET outstanding_balance = -0.01 "
                        "WHERE wholesaler_id = :wholesaler_id AND retailer_id = :retailer_id"
                    ),
                    {"wholesaler_id": wholesaler_id, "retailer_id": retailer_id},
                )
            savepoint.rollback()
        finally:
            connection.rollback()
            _cleanup_migration_rows(
                connection,
                schema=schema,
                wholesaler_id=wholesaler_id,
                retailer_id=retailer_id,
            )
            connection.commit()
