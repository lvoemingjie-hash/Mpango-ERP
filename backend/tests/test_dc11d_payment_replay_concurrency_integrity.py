from __future__ import annotations

import asyncio
import os
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from api.v1.orders import pay_order
from database.session import AsyncSessionLocal
from schemas.order import PayOrderRequest
from tests.async_test_utils import temporary_database_url


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


async def _extension_exists(session, name: str) -> bool:
    return bool((await session.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = :name"),
        {"name": name},
    )).scalar())


async def _table_exists(session, schema: str, table: str) -> bool:
    return bool((await session.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = :table"
        ),
        {"schema": schema, "table": table},
    )).scalar())


async def _column_exists(session, schema: str, table: str, column: str) -> bool:
    return bool((await session.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table "
            "AND column_name = :column"
        ),
        {"schema": schema, "table": table, "column": column},
    )).scalar())


async def _index_exists(session, schema: str, index: str) -> bool:
    return bool((await session.execute(
        text(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = :schema AND indexname = :index"
        ),
        {"schema": schema, "index": index},
    )).scalar())


async def _index_definition(session, schema: str, index: str) -> str | None:
    return (await session.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname = :schema AND indexname = :index"
        ),
        {"schema": schema, "index": index},
    )).scalar_one_or_none()


def _normalize_catalog_sql(sql: str) -> str:
    return " ".join(sql.lower().split())


EXPECTED_BINDING_INDEX_DEF = _normalize_catalog_sql(
    "CREATE UNIQUE INDEX ux_bindings_wholesaler_tenant_user "
    "ON public.wholesaler_retailer_bindings USING btree "
    "(wholesaler_id, tenant_user_id) "
    "WHERE ((tenant_user_id IS NOT NULL) AND (is_deleted IS FALSE))"
)
EXPECTED_BINDING_BALANCE_CHECK = _normalize_catalog_sql(
    "CHECK ((outstanding_balance >= (0)::numeric))"
)
EXPECTED_BINDING_WHOLESALER_RETAILER_UNIQUE = _normalize_catalog_sql(
    "UNIQUE (wholesaler_id, retailer_id)"
)


async def _constraint_definitions(
    session, schema: str, table: str, contype: str
) -> list[str]:
    rows = (await session.execute(
        text(
            "SELECT pg_get_constraintdef(c.oid) "
            "FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "WHERE n.nspname = :schema AND t.relname = :table "
            "AND c.contype = :contype "
            "ORDER BY c.conname"
        ),
        {"schema": schema, "table": table, "contype": contype},
    )).scalars().all()
    return [str(row) for row in rows]


async def _constraint_matches(
    session, schema: str, table: str, contype: str, expected_def: str
) -> bool:
    normalized = _normalize_catalog_sql(expected_def)
    return normalized in {
        _normalize_catalog_sql(definition)
        for definition in await _constraint_definitions(session, schema, table, contype)
    }


async def _public_contract_problems(session) -> list[str]:
    problems: list[str] = []
    if not await _extension_exists(session, "pgcrypto"):
        problems.append("pgcrypto_missing")
    required_columns = {
        "wholesalers": {"status", "is_deleted", "created_at", "updated_at"},
        "retailers": {"email", "email_verified_at", "is_deleted", "created_at", "updated_at"},
        "wholesaler_retailer_bindings": {
            "tenant_user_id",
            "status",
            "outstanding_balance",
            "is_deleted",
            "created_at",
            "updated_at",
        },
    }
    for table, columns in required_columns.items():
        if not await _table_exists(session, "public", table):
            problems.append(f"{table}:missing_table")
            continue
        for column in columns:
            if not await _column_exists(session, "public", table, column):
                problems.append(f"{table}:missing_column:{column}")
    if await _table_exists(session, "public", "wholesaler_retailer_bindings"):
        if not await _constraint_matches(
            session,
            "public",
            "wholesaler_retailer_bindings",
            "c",
            EXPECTED_BINDING_BALANCE_CHECK,
        ):
            problems.append("wholesaler_retailer_bindings:missing_or_incompatible_balance_check")
        if not await _constraint_matches(
            session,
            "public",
            "wholesaler_retailer_bindings",
            "u",
            EXPECTED_BINDING_WHOLESALER_RETAILER_UNIQUE,
        ):
            problems.append("wholesaler_retailer_bindings:missing_or_incompatible_wholesaler_retailer_unique")
        indexdef = await _index_definition(
            session, "public", "ux_bindings_wholesaler_tenant_user"
        )
        if indexdef is None:
            problems.append("wholesaler_retailer_bindings:missing_tenant_user_index")
        elif _normalize_catalog_sql(indexdef) != EXPECTED_BINDING_INDEX_DEF:
            problems.append("wholesaler_retailer_bindings:incompatible_tenant_user_index")
    return problems


async def _public_contract_ready(session) -> bool:
    return not await _public_contract_problems(session)


async def _ensure_public_tables(session) -> None:
    if await _public_contract_ready(session):
        return
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
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            )
            """
        )
    )
    await session.execute(
        text(
            """
            ALTER TABLE public.wholesalers
                ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'active',
                ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            """
        )
    )
    problems = await _public_contract_problems(session)
    assert problems == [], (
        "public test contract bootstrap incomplete or incompatible: "
        + ", ".join(problems)
    )
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS public.retailers (
                id UUID PRIMARY KEY,
                phone VARCHAR(64) UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email VARCHAR(255),
                email_verified_at TIMESTAMP WITH TIME ZONE,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            )
            """
        )
    )
    await session.execute(
        text(
            """
            ALTER TABLE public.retailers
                ADD COLUMN IF NOT EXISTS email VARCHAR(255),
                ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP WITH TIME ZONE,
                ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
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
                tenant_user_id UUID,
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                outstanding_balance NUMERIC(12, 2) NOT NULL DEFAULT 0,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                CONSTRAINT ck_wrb_outstanding_balance_non_negative
                    CHECK (outstanding_balance >= 0),
                UNIQUE (wholesaler_id, retailer_id)
            )
            """
        )
    )
    await session.execute(
        text(
            """
            ALTER TABLE public.wholesaler_retailer_bindings
                ADD COLUMN IF NOT EXISTS tenant_user_id UUID,
                ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'active',
                ADD COLUMN IF NOT EXISTS outstanding_balance NUMERIC(12, 2) NOT NULL DEFAULT 0,
                ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_bindings_wholesaler_tenant_user
            ON public.wholesaler_retailer_bindings (wholesaler_id, tenant_user_id)
            WHERE tenant_user_id IS NOT NULL AND is_deleted IS FALSE
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
                sellable_unit_id UUID,
                identity_status VARCHAR(32) NOT NULL DEFAULT 'legacy',
                unit_snapshot VARCHAR(32),
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
            ALTER TABLE "{schema}".order_items
                DROP CONSTRAINT IF EXISTS ck_order_items_identity_shape_minimal
            """
        )
    )
    await session.execute(
        text(
            f"""
            ALTER TABLE "{schema}".order_items
                ADD CONSTRAINT ck_order_items_identity_shape_minimal CHECK (
                    (identity_status = 'legacy' AND sellable_unit_id IS NULL) OR
                    (identity_status = 'linked_legacy' AND sellable_unit_id IS NOT NULL) OR
                    (identity_status = 'stable' AND sellable_unit_id IS NOT NULL AND unit_snapshot IS NOT NULL)
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
    initial_outstanding: Decimal = Decimal("0.00"),
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
            VALUES (:tenant_id, :retailer_id, 'active', :initial_outstanding, FALSE)
            ON CONFLICT (wholesaler_id, retailer_id) DO UPDATE
            SET status = 'active',
                outstanding_balance = :initial_outstanding,
                is_deleted = FALSE,
                updated_at = now()
            """
        ),
        {
            "tenant_id": tenant_id,
            "retailer_id": retailer_id,
            "initial_outstanding": initial_outstanding,
        },
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


# ---------------------------------------------------------------------------
# DC-12R1-MVP-L1-J1-H2-B-R2-R2-R1: cross-module fixture ownership closure.
#
# Suite-order RED baseline (fresh DB): DC11D module -> canonical-payment module
# -> DC3B module leaves TWO scannable wholesalers whose derived schemas fail
# the password-reset user scan (failed-schema aggregate = 2): the fixed
# cross-tenant 22222222-... (schema without a users table) and the shared
# t_test tenant 11111111-... (derived schema never exists), the latter
# committed by five explicitly-committing DC11D nodes and by canonical's
# later committing test.
#
# Ownership rules implemented below (exact identities only — no LIKE, no
# prefixes, no wildcard deletion, no global reset, no soft-delete-only
# cleanup, no DROP DATABASE, no product changes):
# - the fixed cross-tenant UUID/schema (2222...) is task-created: its exact
#   rows and schema are removed and a zero-residue proof must hold;
# - the shared t_test tenant (1111..., resolved at runtime) may PRE-EXIST:
#   its public rows are snapshotted before the test and restored EXACTLY
#   after it — a row is never deleted merely because the test touched it.
#   An independent proof on a fresh connection must show post-state equals
#   pre-test state or the test fails (fail-closed).
# ---------------------------------------------------------------------------

_CROSS_TENANT_SCHEMA = "t_22222222222222222222222222222222"
_CROSS_TENANT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


async def _fetch_rows(session, sql: str, params: dict) -> list[dict]:
    result = await session.execute(text(sql), params)
    return [dict(mapping) for mapping in result.mappings().all()]


async def _snapshot_public_tenant(session, *, wholesaler_id: str) -> dict:
    """Capture the exact public rows owned-by/scope-of one wholesaler UUID."""
    wholesalers = await _fetch_rows(
        session,
        "SELECT * FROM public.wholesalers WHERE id = :w",
        {"w": wholesaler_id},
    )
    bindings = await _fetch_rows(
        session,
        "SELECT * FROM public.wholesaler_retailer_bindings "
        "WHERE wholesaler_id = :w ORDER BY id",
        {"w": wholesaler_id},
    )
    retailers: list[dict] = []
    retailer_ids = sorted({str(binding["retailer_id"]) for binding in bindings})
    if retailer_ids:
        placeholders = ", ".join(f":r{i}" for i in range(len(retailer_ids)))
        params = {f"r{i}": value for i, value in enumerate(retailer_ids)}
        retailers = await _fetch_rows(
            session,
            f"SELECT * FROM public.retailers WHERE id IN ({placeholders}) ORDER BY id",
            params,
        )
    return {
        "wholesaler": wholesalers[0] if wholesalers else None,
        "bindings": bindings,
        "retailers": retailers,
    }


def _insert_sql(table: str, row: dict) -> str:
    columns = ", ".join(row.keys())
    values = ", ".join(f":v_{column}" for column in row)
    return f"INSERT INTO {table} ({columns}) VALUES ({values})"


def _flatten(row: dict) -> dict:
    return {f"v_{column}": value for column, value in row.items()}


async def _restore_public_tenant(session, *, wholesaler_id: str, snap: dict) -> None:
    """Restore the exact pre-test public rows for one wholesaler UUID."""
    current = await _snapshot_public_tenant(session, wholesaler_id=wholesaler_id)
    current_retailer_ids = {str(binding["retailer_id"]) for binding in current["bindings"]}
    snapshot_retailer_ids = {str(row["id"]) for row in snap["retailers"]}
    # Retailers that keep bindings to OTHER wholesalers are not owned by this
    # scope even if this test touched them — they must not be deleted.
    candidate_ids = sorted(current_retailer_ids | snapshot_retailer_ids)
    protected: set[str] = set()
    if candidate_ids:
        placeholders = ", ".join(f":p{i}" for i in range(len(candidate_ids)))
        params = {"w": wholesaler_id}
        params.update({f"p{i}": value for i, value in enumerate(candidate_ids)})
        protected = {
            str(row["retailer_id"])
            for row in await _fetch_rows(
                session,
                "SELECT retailer_id FROM public.wholesaler_retailer_bindings "
                f"WHERE retailer_id IN ({placeholders}) AND wholesaler_id <> :w",
                params,
            )
        }
    await session.execute(
        text("DELETE FROM public.wholesaler_retailer_bindings WHERE wholesaler_id = :w"),
        {"w": wholesaler_id},
    )
    for retailer_id in sorted(current_retailer_ids - snapshot_retailer_ids):
        if retailer_id not in protected:
            await session.execute(
                text("DELETE FROM public.retailers WHERE id = :r"), {"r": retailer_id}
            )
    await session.execute(
        text("DELETE FROM public.wholesalers WHERE id = :w"), {"w": wholesaler_id}
    )
    if snap["wholesaler"] is not None:
        await session.execute(
            text(_insert_sql("public.wholesalers", snap["wholesaler"])),
            _flatten(snap["wholesaler"]),
        )
    for retailer in snap["retailers"]:
        assignments = ", ".join(
            f"{column} = EXCLUDED.{column}" for column in retailer if column != "id"
        )
        await session.execute(
            text(
                f"{_insert_sql('public.retailers', retailer)} "
                f"ON CONFLICT (id) DO UPDATE SET {assignments}"
            ),
            _flatten(retailer),
        )
    for binding in snap["bindings"]:
        await session.execute(
            text(_insert_sql("public.wholesaler_retailer_bindings", binding)),
            _flatten(binding),
        )


@pytest.fixture
async def _shared_tenant_guard(async_session):
    """Snapshot/restore the shared t_test tenant's exact public rows.

    Runs even when the test body fails and cannot mask an original failure
    (the body exception reaches pytest before teardown). The test session is
    rolled back first (idempotent; the async_session fixture repeats it) so
    its locks cannot block cleanup; restore + proof use fresh connections
    outside the test transaction.
    """
    wholesaler_id = str(_tenant_id(async_session))
    async with AsyncSessionLocal() as snapshot_session:
        # Fresh real-db runs may reach this guard before any test has durably
        # created the public ownership tables. Bootstrap them outside the body
        # first so the pre-test snapshot never fails on a missing relation.
        await _ensure_public_tables(snapshot_session)
        await snapshot_session.commit()
        snap = await _snapshot_public_tenant(
            snapshot_session, wholesaler_id=wholesaler_id
        )
    yield
    await async_session.rollback()
    async with AsyncSessionLocal() as cleanup:
        await _restore_public_tenant(cleanup, wholesaler_id=wholesaler_id, snap=snap)
        await cleanup.commit()
    async with AsyncSessionLocal() as proof:
        post = await _snapshot_public_tenant(proof, wholesaler_id=wholesaler_id)
    assert post == snap, (
        "shared-tenant ownership violation: post-test public rows differ from "
        f"pre-test snapshot for wholesaler {wholesaler_id}"
    )


@pytest.fixture
async def _cross_tenant_residue_guard(async_session):
    """Fail-closed teardown for the fixed 2222... cross-tenant residue."""
    # Pre-existing reverse-order hazard (reproduced at base b4c1ec6b): when
    # this node runs FIRST in a fresh process/database, the public helper DDL
    # may still be missing; _ensure_public_tables (via _seed_confirmed_order /
    # _bootstrap_minimal_tenant_schema) would then run INSIDE the still-open
    # test transaction, and the second setup session can block on the same
    # catalog objects until the 10s command timeout. Installing the complete
    # public contract durably BEFORE the body makes all in-test DDL idempotent
    # no-ops. In natural suite order an earlier committing node already does
    # this — only ordering hides the race.
    async with AsyncSessionLocal() as prerequisite_session:
        await _ensure_public_tables(prerequisite_session)
        await prerequisite_session.commit()
    owned = {"second_retailer_id": None}
    yield owned
    await async_session.rollback()
    second_retailer = owned["second_retailer_id"]
    async with AsyncSessionLocal() as cleanup:
        # FK-safe order: binding -> retailer -> wholesaler -> schema.
        if second_retailer is not None:
            await cleanup.execute(
                text(
                    "DELETE FROM public.wholesaler_retailer_bindings "
                    "WHERE wholesaler_id = :wholesaler AND retailer_id = :retailer"
                ),
                {"wholesaler": str(_CROSS_TENANT_ID), "retailer": str(second_retailer)},
            )
            await cleanup.execute(
                text("DELETE FROM public.retailers WHERE id = :retailer"),
                {"retailer": str(second_retailer)},
            )
        await cleanup.execute(
            text("DELETE FROM public.wholesalers WHERE id = :wholesaler"),
            {"wholesaler": str(_CROSS_TENANT_ID)},
        )
        await cleanup.execute(
            text(f'DROP SCHEMA IF EXISTS "{_CROSS_TENANT_SCHEMA}" CASCADE')
        )
        await cleanup.commit()
    async with AsyncSessionLocal() as proof:
        checks = {
            "pg_namespace.schema": (
                "SELECT COUNT(*) FROM pg_namespace WHERE nspname = :schema",
                {"schema": _CROSS_TENANT_SCHEMA},
            ),
            "public.wholesalers": (
                "SELECT COUNT(*) FROM public.wholesalers WHERE id = :wholesaler",
                {"wholesaler": str(_CROSS_TENANT_ID)},
            ),
            "public.wholesaler_retailer_bindings": (
                "SELECT COUNT(*) FROM public.wholesaler_retailer_bindings "
                "WHERE wholesaler_id = :wholesaler",
                {"wholesaler": str(_CROSS_TENANT_ID)},
            ),
        }
        if second_retailer is not None:
            checks["public.retailers"] = (
                "SELECT COUNT(*) FROM public.retailers WHERE id = :retailer",
                {"retailer": str(second_retailer)},
            )
        counts = {}
        for name, (sql, params) in checks.items():
            result = await proof.execute(text(sql), params)
            counts[name] = int(result.scalar_one())
    assert all(count == 0 for count in counts.values()), (
        f"cross-tenant residue teardown left database residue: {counts}"
    )


@pytest.mark.asyncio
async def test_public_bootstrap_rejects_incompatible_existing_binding_index():
    if os.environ.get("MPANGO_ALLOW_TEMP_DB_CREATE") != "1":
        pytest.skip("set MPANGO_ALLOW_TEMP_DB_CREATE=1 for public bootstrap isolation tests")
    source_url = os.environ.get("TEST_DATABASE_URL")
    if not source_url:
        pytest.skip("TEST_DATABASE_URL is required for public bootstrap isolation tests")

    with temporary_database_url(source_url, "dc11dpub") as database_url:
        async_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        engine = create_async_engine(async_url, future=True)
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                await _ensure_public_tables(session)
                await session.commit()
                await session.execute(
                    text("DROP INDEX public.ux_bindings_wholesaler_tenant_user")
                )
                await session.execute(
                    text(
                        """
                        CREATE UNIQUE INDEX ux_bindings_wholesaler_tenant_user
                        ON public.wholesaler_retailer_bindings (tenant_user_id, wholesaler_id)
                        WHERE tenant_user_id IS NOT NULL
                        """
                    )
                )
                await session.commit()

                with pytest.raises(
                    AssertionError,
                    match="incompatible_tenant_user_index",
                ):
                    await _ensure_public_tables(session)

                indexdef = await _index_definition(
                    session, "public", "ux_bindings_wholesaler_tenant_user"
                )
                assert indexdef is not None
                assert _normalize_catalog_sql(indexdef) != EXPECTED_BINDING_INDEX_DEF
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_sequential_same_financial_result_replay_creates_one_financial_result(async_session):
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
    assert replay.data["payment_amount"] == first.data["payment_amount"] == "100.00"
    assert replay.data["payment_method"] == first.data["payment_method"] == "cash"
    assert replay.data["status"] == snapshot["order_status"]
    _assert_single_full_settlement(snapshot)


@pytest.mark.asyncio
async def test_concurrent_same_financial_result_replay_creates_one_financial_result(async_session, _shared_tenant_guard):
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
    assert first.data["payment_amount"] == second.data["payment_amount"] == "100.00"
    assert first.data["payment_method"] == second.data["payment_method"] == "cash"
    await _set_search_path(async_session, schema)
    snapshot = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    assert first.data["status"] == second.data["status"] == snapshot["order_status"]
    _assert_single_full_settlement(snapshot)


@pytest.mark.asyncio
async def test_payment_notes_are_rejected_without_side_effects(async_session):
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    before = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )

    with pytest.raises(HTTPException) as exc_info:
        await pay_order(
            order_id=str(order_id),
            token=token,
            db=async_session,
            payment_input=PayOrderRequest(
                amount=Decimal("100.00"), method="cash", notes="unsupported"
            ),
            x_idempotency_key="dc11d-notes-unsupported",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "PAYMENT_NOTES_UNSUPPORTED"
    after = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    assert after == before


@pytest.mark.asyncio
async def test_concurrent_different_keys_cannot_overpay(async_session, _shared_tenant_guard):
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
    assert failures[0].status_code == 409
    assert failures[0].detail["code"] == "ORDER_ALREADY_PAID"
    await _set_search_path(async_session, schema)
    snapshot = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    _assert_single_full_settlement(snapshot)


@pytest.mark.asyncio
async def test_empty_body_and_empty_object_create_no_side_effects(async_session, _shared_tenant_guard):
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
async def test_unrelated_integrity_error_is_not_idempotency_conflict_and_rolls_back(async_session, _shared_tenant_guard):
    tenant_id = _tenant_id(async_session)
    order_id, retailer_id, token = await _seed_confirmed_order(
        async_session, tenant_id=tenant_id, total=Decimal("100.00")
    )
    await async_session.commit()
    await _set_search_path(async_session, _tenant_schema(async_session))
    before = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )

    async def fail_balance_delta(*_args, **_kwargs):
        raise IntegrityError("dc11d-r1-downstream", {}, RuntimeError("forced integrity failure"))

    from services.payment_service import PaymentService

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            PaymentService,
            "_apply_outstanding_balance_delta",
            fail_balance_delta,
        )
        async with AsyncSessionLocal() as failure_session:
            failure_session.info["tenant_schema"] = _tenant_schema(async_session)
            failure_session.info["tenant_id"] = str(tenant_id)
            await _set_search_path(failure_session, _tenant_schema(async_session))
            with pytest.raises(IntegrityError):
                await pay_order(
                    order_id=str(order_id),
                    token=token,
                    db=failure_session,
                    payment_input=PayOrderRequest(amount=Decimal("100.00"), method="credit"),
                    x_idempotency_key="dc11d-r1-unknown-integrity",
                )

    await _set_search_path(async_session, _tenant_schema(async_session))
    after = await _snapshot(
        async_session, order_id=order_id, tenant_id=tenant_id, retailer_id=retailer_id
    )
    assert after == before


@pytest.mark.asyncio
async def test_rollback_after_state_failure_leaves_tables_unchanged(async_session, _shared_tenant_guard):
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
async def test_cross_tenant_same_idempotency_key_is_isolated(async_session, _cross_tenant_residue_guard):
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
        _cross_tenant_residue_guard["second_retailer_id"] = second_retailer_id
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
