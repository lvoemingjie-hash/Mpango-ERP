from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from api.v1.orders import pay_order
from database.session import AsyncSessionLocal
from schemas.order import PayOrderRequest


class _Token:
    def __init__(self, *, tenant_id: uuid.UUID, tenant_schema: str) -> None:
        self.tenant_id = str(tenant_id)
        self.tenant_schema = tenant_schema
        self.user_id = str(uuid.uuid4())
        self.roles = ["super_admin"]


def _tenant_schema(async_session) -> str:
    return str(async_session.info.get("tenant_schema") or "t_test")


def _tenant_id(async_session) -> uuid.UUID:
    return uuid.UUID(str(async_session.info.get("tenant_id") or "11111111-1111-1111-1111-111111111111"))


async def _set_search_path(session, schema: str) -> None:
    await session.execute(text(f'SET search_path TO "{schema}", public'))


async def _ensure_public_tables(session) -> None:
    await session.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    await session.execute(
        text(
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
        )
    )
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS public.retailers (
                id UUID PRIMARY KEY,
                phone VARCHAR(64) UNIQUE NOT NULL,
                name TEXT NOT NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            )
            """
        )
    )
    await session.execute(
        text(
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
        )
    )


async def _bootstrap_minimal_tenant_schema(session, schema: str) -> None:
    await _ensure_public_tables(session)
    await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    await _set_search_path(session, schema)
    await session.execute(
        text(
            """
            DO $$ BEGIN
                CREATE TYPE order_status AS ENUM (
                    'draft', 'confirmed', 'partially_paid', 'paid',
                    'fulfilled', 'cancelled', 'voided', 'returned'
                );
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
            """
        )
    )
    await session.execute(
        text(
            """
            DO $$ BEGIN
                CREATE TYPE account_type AS ENUM ('receivable', 'revenue', 'cash', 'liability');
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
            """
        )
    )
    await session.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS "{schema}".orders (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                wholesaler_id UUID NOT NULL,
                retailer_id UUID NOT NULL,
                status order_status NOT NULL DEFAULT 'draft',
                total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
                notes TEXT,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                deleted_at TIMESTAMP WITH TIME ZONE,
                created_by UUID,
                updated_by UUID,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            )
            """
        )
    )
    await session.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS "{schema}".order_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL REFERENCES "{schema}".orders(id) ON DELETE CASCADE,
                product_name TEXT NOT NULL,
                sku_code VARCHAR(64) NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price NUMERIC(12, 2) NOT NULL,
                subtotal NUMERIC(12, 2) NOT NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                deleted_at TIMESTAMP WITH TIME ZONE,
                created_by UUID,
                updated_by UUID,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            )
            """
        )
    )
    await session.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS "{schema}".payments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL REFERENCES "{schema}".orders(id) ON DELETE CASCADE,
                retailer_id UUID NOT NULL,
                transaction_id VARCHAR(64),
                amount NUMERIC(12, 2) NOT NULL,
                method VARCHAR(32) NOT NULL,
                status VARCHAR(32) NOT NULL,
                idempotency_key VARCHAR(64) UNIQUE,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                deleted_at TIMESTAMP WITH TIME ZONE,
                created_by UUID,
                updated_by UUID,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            )
            """
        )
    )
    await session.execute(
        text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_transaction_id
            ON "{schema}".payments(transaction_id)
            WHERE transaction_id IS NOT NULL
            """
        )
    )
    await session.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS "{schema}".ledger_entries (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                transaction_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                account_type account_type NOT NULL,
                amount NUMERIC(20, 4) NOT NULL,
                reference_type VARCHAR(50) NOT NULL,
                reference_id UUID NOT NULL,
                description TEXT,
                entry_version INTEGER NOT NULL DEFAULT 1,
                hash VARCHAR(64),
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                deleted_at TIMESTAMP WITH TIME ZONE,
                created_by UUID,
                updated_by UUID,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            )
            """
        )
    )


async def _seed_confirmed_order(
    session,
    *,
    tenant_id: uuid.UUID,
    total: Decimal,
):
    await _ensure_public_tables(session)
    order_id = uuid.uuid4()
    retailer_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO public.wholesalers (id, code, name, status, is_deleted)
            VALUES (:tenant_id, :code, 'DC11D Wholesaler', 'active', FALSE)
            ON CONFLICT (id) DO UPDATE
            SET status = 'active', is_deleted = FALSE, updated_at = now()
            """
        ),
        {"tenant_id": tenant_id, "code": f"DC11D{str(order_id).replace('-', '')[:8]}"},
    )
    await session.execute(
        text(
            """
            INSERT INTO public.retailers (id, phone, name, is_deleted)
            VALUES (:retailer_id, :phone, 'DC11D Retailer', FALSE)
            ON CONFLICT (id) DO UPDATE
            SET is_deleted = FALSE, updated_at = now()
            """
        ),
        {"retailer_id": retailer_id, "phone": f"+1999{str(order_id).replace('-', '')[:10]}"},
    )
    await session.execute(
        text(
            """
            INSERT INTO public.wholesaler_retailer_bindings (
                wholesaler_id, retailer_id, status, outstanding_balance, is_deleted
            )
            VALUES (:tenant_id, :retailer_id, 'active', :total, FALSE)
            ON CONFLICT (wholesaler_id, retailer_id) DO UPDATE
            SET status = 'active',
                outstanding_balance = :total,
                is_deleted = FALSE,
                updated_at = now()
            """
        ),
        {"tenant_id": tenant_id, "retailer_id": retailer_id, "total": total},
    )
    await session.execute(
        text(
            """
            INSERT INTO orders (id, wholesaler_id, retailer_id, status, total_amount)
            VALUES (:order_id, :tenant_id, :retailer_id, 'confirmed', :total)
            """
        ),
        {"order_id": order_id, "tenant_id": tenant_id, "retailer_id": retailer_id, "total": total},
    )
    return order_id, retailer_id, _Token(tenant_id=tenant_id, tenant_schema=str(session.info["tenant_schema"]))


async def _snapshot(session, *, order_id: uuid.UUID, tenant_id: uuid.UUID, retailer_id: uuid.UUID):
    result = await session.execute(
        text(
            """
            SELECT
                (SELECT status::text FROM orders WHERE id = :order_id) AS order_status,
                (SELECT COUNT(*) FROM payments WHERE order_id = :order_id AND is_deleted IS FALSE) AS payment_count,
                (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE order_id = :order_id AND is_deleted IS FALSE) AS payment_total,
                (SELECT COUNT(*) FROM payments WHERE order_id = :order_id AND status = 'completed' AND is_deleted IS FALSE) AS completed_count,
                (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE order_id = :order_id AND status = 'completed' AND is_deleted IS FALSE) AS completed_total,
                (SELECT COUNT(*) FROM ledger_entries WHERE reference_type = 'order' AND reference_id = :order_id) AS ledger_count,
                (SELECT COALESCE(SUM(amount), 0) FROM ledger_entries WHERE reference_type = 'order' AND reference_id = :order_id) AS ledger_sum,
                (SELECT outstanding_balance FROM public.wholesaler_retailer_bindings WHERE wholesaler_id = :tenant_id AND retailer_id = :retailer_id) AS outstanding_balance
            """
        ),
        {"order_id": order_id, "tenant_id": tenant_id, "retailer_id": retailer_id},
    )
    return dict(result.mappings().one())


async def _pay_in_new_session(
    *,
    schema: str,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    amount: Decimal,
    method: str,
    idempotency_key: str,
    transaction_id: str | None = None,
):
    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = schema
        session.info["tenant_id"] = str(tenant_id)
        await _set_search_path(session, schema)
        token = _Token(tenant_id=tenant_id, tenant_schema=schema)
        try:
            response = await pay_order(
                order_id=str(order_id),
                token=token,
                db=session,
                payment_input=PayOrderRequest(
                    amount=amount,
                    method=method,
                    transaction_id=transaction_id,
                ),
                x_idempotency_key=idempotency_key,
            )
            await session.commit()
            return response
        except HTTPException as exc:
            await session.rollback()
            return exc


def _assert_single_full_settlement(snapshot) -> None:
    assert snapshot["order_status"] == "paid"
    assert snapshot["payment_count"] == 1
    assert Decimal(str(snapshot["payment_total"])) == Decimal("100.00")
    assert snapshot["completed_count"] == 1
    assert Decimal(str(snapshot["completed_total"])) == Decimal("100.00")
    assert snapshot["ledger_count"] == 2
    assert Decimal(str(snapshot["ledger_sum"])) == Decimal("0.0000")
    assert Decimal(str(snapshot["outstanding_balance"])) == Decimal("0.00")


@pytest.mark.asyncio
async def test_sequential_exact_replay_creates_one_financial_result(async_session):
    schema = _tenant_schema(async_session)
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )

    first = await pay_order(
        order_id=str(order_id),
        token=token,
        db=async_session,
        payment_input=PayOrderRequest(amount=Decimal("100.00"), method="cash"),
        x_idempotency_key="dc11d-sequential-replay",
    )
    replay = await pay_order(
        order_id=str(order_id),
        token=token,
        db=async_session,
        payment_input=PayOrderRequest(amount=Decimal("100.00"), method="cash"),
        x_idempotency_key="dc11d-sequential-replay",
    )

    snapshot = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    assert replay.data["payment_id"] == first.data["payment_id"]
    _assert_single_full_settlement(snapshot)


@pytest.mark.asyncio
async def test_concurrent_exact_replay_creates_one_financial_result(async_session):
    schema = _tenant_schema(async_session)
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, _token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    await async_session.commit()

    first, second = await asyncio.gather(
        _pay_in_new_session(
            schema=schema,
            tenant_id=tenant_id,
            order_id=order_id,
            amount=Decimal("100.00"),
            method="cash",
            idempotency_key="dc11d-concurrent-replay",
        ),
        _pay_in_new_session(
            schema=schema,
            tenant_id=tenant_id,
            order_id=order_id,
            amount=Decimal("100.00"),
            method="cash",
            idempotency_key="dc11d-concurrent-replay",
        ),
    )

    assert not isinstance(first, HTTPException)
    assert not isinstance(second, HTTPException)
    assert first.data["payment_id"] == second.data["payment_id"]
    await _set_search_path(async_session, schema)
    snapshot = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    _assert_single_full_settlement(snapshot)


@pytest.mark.asyncio
async def test_concurrent_different_keys_cannot_overpay(async_session):
    schema = _tenant_schema(async_session)
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, _token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    await async_session.commit()

    results = await asyncio.gather(
        _pay_in_new_session(
            schema=schema,
            tenant_id=tenant_id,
            order_id=order_id,
            amount=Decimal("100.00"),
            method="cash",
            idempotency_key="dc11d-overpay-key-a",
        ),
        _pay_in_new_session(
            schema=schema,
            tenant_id=tenant_id,
            order_id=order_id,
            amount=Decimal("100.00"),
            method="cash",
            idempotency_key="dc11d-overpay-key-b",
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
    _assert_single_full_settlement(snapshot)


@pytest.mark.asyncio
async def test_empty_body_and_empty_object_create_no_side_effects(async_session):
    schema = _tenant_schema(async_session)
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    await async_session.commit()
    await _set_search_path(async_session, _tenant_schema(async_session))
    before = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )

    for payment_input in (None, PayOrderRequest()):
        with pytest.raises(HTTPException) as exc_info:
            await pay_order(
                order_id=str(order_id),
                token=token,
                db=async_session,
                payment_input=payment_input,
                x_idempotency_key="dc11d-empty-body",
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["code"] == "PAYMENT_BODY_REQUIRED"

    after = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    assert after == before


@pytest.mark.asyncio
async def test_conflicting_idempotency_key_returns_409(async_session):
    tenant_id = _tenant_id(async_session)
    order_id, _retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    await pay_order(
        order_id=str(order_id),
        token=token,
        db=async_session,
        payment_input=PayOrderRequest(amount=Decimal("40.00"), method="cash"),
        x_idempotency_key="dc11d-conflict-key",
    )

    with pytest.raises(HTTPException) as exc_info:
        await pay_order(
            order_id=str(order_id),
            token=token,
            db=async_session,
            payment_input=PayOrderRequest(amount=Decimal("50.00"), method="cash"),
            x_idempotency_key="dc11d-conflict-key",
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "IDEMPOTENCY_KEY_CONFLICT"


@pytest.mark.asyncio
async def test_duplicate_transfer_reference_returns_sanitized_409(async_session):
    tenant_id = _tenant_id(async_session)
    first_order_id, _first_retailer, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    second_order_id, _second_retailer, _token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    await pay_order(
        order_id=str(first_order_id),
        token=token,
        db=async_session,
        payment_input=PayOrderRequest(
            amount=Decimal("100.00"), method="transfer", transaction_id="DC11D-XFER-1"
        ),
        x_idempotency_key="dc11d-xfer-key-a",
    )

    with pytest.raises(HTTPException) as exc_info:
        await pay_order(
            order_id=str(second_order_id),
            token=token,
            db=async_session,
            payment_input=PayOrderRequest(
                amount=Decimal("100.00"), method="transfer", transaction_id="DC11D-XFER-1"
            ),
            x_idempotency_key="dc11d-xfer-key-b",
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "DUPLICATE_TRANSFER_REFERENCE",
        "message": "Transfer transaction_id has already been recorded",
    }


@pytest.mark.asyncio
async def test_rollback_after_state_failure_leaves_tables_unchanged(async_session):
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    await async_session.commit()
    await _set_search_path(async_session, _tenant_schema(async_session))
    before = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )

    async def fail_transition(*_args, **_kwargs):
        raise RuntimeError("state transition failed")

    from services.order_service import OrderService

    with pytest.raises(RuntimeError), pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(OrderService, "transition", fail_transition)
        async with AsyncSessionLocal() as failure_session:
            failure_session.info["tenant_schema"] = _tenant_schema(async_session)
            failure_session.info["tenant_id"] = str(tenant_id)
            await _set_search_path(failure_session, _tenant_schema(async_session))
            await pay_order(
                order_id=str(order_id),
                token=token,
                db=failure_session,
                payment_input=PayOrderRequest(amount=Decimal("100.00"), method="cash"),
                x_idempotency_key="dc11d-rollback-key",
            )

    await _set_search_path(async_session, _tenant_schema(async_session))
    after = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    assert after == before


@pytest.mark.asyncio
async def test_cross_tenant_same_idempotency_key_is_isolated(async_session):
    first_schema = _tenant_schema(async_session)
    first_tenant_id = _tenant_id(async_session)
    second_schema = "t_22222222222222222222222222222222"
    second_tenant_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    shared_key = "dc11d-shared-key"

    first_order_id, first_retailer_id, first_token = await _seed_confirmed_order(
        async_session, tenant_id=first_tenant_id, total=Decimal("100.00")
    )
    async with AsyncSessionLocal() as setup_session:
        setup_session.info["tenant_schema"] = second_schema
        setup_session.info["tenant_id"] = str(second_tenant_id)
        await _bootstrap_minimal_tenant_schema(setup_session, second_schema)
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
        await setup_session.commit()

    await pay_order(
        order_id=str(first_order_id),
        token=first_token,
        db=async_session,
        payment_input=PayOrderRequest(amount=Decimal("100.00"), method="cash"),
        x_idempotency_key=shared_key,
    )
    async with AsyncSessionLocal() as second_session:
        second_session.info["tenant_schema"] = second_schema
        second_session.info["tenant_id"] = str(second_tenant_id)
        await _set_search_path(second_session, second_schema)
        await pay_order(
            order_id=str(second_order_id),
            token=second_token,
            db=second_session,
            payment_input=PayOrderRequest(amount=Decimal("100.00"), method="cash"),
            x_idempotency_key=shared_key,
        )
        await second_session.commit()
        second_snapshot = await _snapshot(
            second_session,
            order_id=second_order_id,
            tenant_id=second_tenant_id,
            retailer_id=second_retailer_id,
        )

    first_snapshot = await _snapshot(
        async_session,
        order_id=first_order_id,
        tenant_id=first_tenant_id,
        retailer_id=first_retailer_id,
    )
    _assert_single_full_settlement(first_snapshot)
    _assert_single_full_settlement(second_snapshot)
