"""
Pytest configuration and fixtures for Mpango ERP backend tests.

S2.5: Uses strong SECRET_KEY for testing to pass security validation.
S5-OPS: Robust async_session fixture for complex transaction tests (S5-A/S5-B).
"""
import os
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import pytest
import pytest_asyncio
from dotenv import dotenv_values

def _load_test_env_defaults() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    project_root = backend_dir.parent
    env_candidates = (
        backend_dir / ".env.test",
        backend_dir / ".env",
        project_root / ".env",
    )
    for env_path in env_candidates:
        if not env_path.is_file():
            continue
        for key, value in dotenv_values(env_path).items():
            if value is not None:
                os.environ.setdefault(key, value)


def _build_database_url_from_postgres_env() -> str:
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "postgres")
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = os.environ.get("POSTGRES_PORT", "5432")
    database = os.environ.get("POSTGRES_DB", "mpango_erp")
    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{database}"
    )


def _resolve_test_database_url() -> str:
    if os.environ.get("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]
    if os.environ.get("POSTGRES_USER") or os.environ.get("POSTGRES_PASSWORD"):
        return _build_database_url_from_postgres_env()
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    return _build_database_url_from_postgres_env()


def _build_test_reporting_database_url(database_url: str) -> str:
    parsed = urlparse(
        database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    )
    host = parsed.hostname or "postgres"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    password = quote_plus(os.environ["REPORTING_USER_PASSWORD"])
    return parsed._replace(
        scheme="postgresql+asyncpg",
        netloc=f"reporting_user:{password}@{host}",
    ).geturl()


# S2.5: Set test environment variables before importing settings.
# S8-SEC: Load local test env defaults, then resolve the final DB URL.
_load_test_env_defaults()
os.environ["DATABASE_URL"] = _resolve_test_database_url()
os.environ.setdefault("REPORTING_USER_PASSWORD", os.environ.get("POSTGRES_PASSWORD", "postgres"))
os.environ["REPORTING_DATABASE_URL"] = os.environ.get(
    "TEST_REPORTING_DATABASE_URL",
    _build_test_reporting_database_url(os.environ["DATABASE_URL"]),
)
# S5/E1: deterministic tenant context used by tenant-guarded order/ledger tests
os.environ.setdefault("TEST_TENANT_SCHEMA", "t_test")
# Generate a deterministic but non-real test SECRET_KEY (passes 32-char + no-weak-substring validation)
import hashlib as _hashlib
_TEST_SECRET = _hashlib.sha256(b"mpango-test-runner-key-not-for-production").hexdigest()
os.environ.setdefault("SECRET_KEY", _TEST_SECRET)
os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("REDIS_URL", f"redis://{os.environ.get('REDIS_HOST', 'redis')}:6379/0")


from typing import AsyncGenerator
from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import AsyncSessionLocal, async_engine


TEST_TENANT_SCHEMA = os.environ.get("TEST_TENANT_SCHEMA", "t_test")
TEST_TENANT_ID = os.environ.get("TEST_TENANT_ID", "11111111-1111-1111-1111-111111111111")
_REPORTING_ROLE_REPAIR_REFUSED = "TEST_REPORTING_ROLE_REPAIR_REFUSED_NON_TEST_DB"
_REPORTING_ROLE_REPAIR_ALLOWED_HOSTS = {
    "127.0.0.1",
    "localhost",
    "postgres",
    "mpango_postgres",  # documented local/CI test Postgres service name
}


def _assert_reporting_role_repair_test_db_guard() -> None:
    if os.environ.get("MPANGO_ENV") != "test":
        raise RuntimeError(_REPORTING_ROLE_REPAIR_REFUSED)

    database_url = os.environ.get("DATABASE_URL", "")
    database_url_host = urlparse(database_url).hostname
    postgres_host = os.environ.get("POSTGRES_HOST")
    hosts = [database_url_host]
    if postgres_host:
        hosts.append(postgres_host)

    if not hosts or any(host not in _REPORTING_ROLE_REPAIR_ALLOWED_HOSTS for host in hosts):
        raise RuntimeError(_REPORTING_ROLE_REPAIR_REFUSED)


@pytest_asyncio.fixture(scope="session")
async def ensure_reporting_user_password() -> None:
    """Align local test reporting_user password with REPORTING_USER_PASSWORD."""
    reporting_password = os.environ.get("REPORTING_USER_PASSWORD")
    if not reporting_password:
        return
    _assert_reporting_role_repair_test_db_guard()

    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                text("SELECT set_config('mpango.reporting_user_password', :password, false)"),
                {"password": reporting_password},
            )
            await session.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'reporting_user') THEN
                            EXECUTE format(
                                'ALTER ROLE reporting_user WITH PASSWORD %L',
                                current_setting('mpango.reporting_user_password')
                            );
                        END IF;
                    END $$;
                    """
                )
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    await async_engine.dispose()
    try:
        from database.reporting_session import reporting_engine

        await reporting_engine.dispose()
    except ImportError:
        pass


async def _bootstrap_tenant_test_schema(session: AsyncSession, tenant_schema: str) -> None:
    """Ensure tenant test schema/tables exist for S5 order+ledger integration tests."""
    await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{tenant_schema}"'))
    await session.execute(text(f'SET search_path TO "{tenant_schema}", public'))

    await session.execute(text("""
        DO $$ BEGIN
            CREATE TYPE order_status AS ENUM (
                'draft',
                'confirmed',
                'partially_paid',
                'paid',
                'fulfilled',
                'cancelled',
                'voided',
                'returned'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """))
    await session.execute(text("ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'returned'"))

    await session.execute(text("""
        DO $$ BEGIN
            CREATE TYPE account_type AS ENUM ('receivable', 'revenue', 'cash', 'liability');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """))

    await session.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{tenant_schema}".catalog_products (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            description TEXT,
            category VARCHAR(64),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TIMESTAMP WITH TIME ZONE,
            created_by UUID,
            updated_by UUID,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))

    await session.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{tenant_schema}".orders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wholesaler_id UUID NOT NULL,
            retailer_id UUID NOT NULL,
            status order_status NOT NULL DEFAULT 'draft',
            total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            notes TEXT,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TIMESTAMP WITH TIME ZONE,
            created_by UUID,
            updated_by UUID,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))

    await session.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{tenant_schema}".order_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id UUID NOT NULL REFERENCES "{tenant_schema}".orders(id) ON DELETE CASCADE,
            product_name TEXT NOT NULL,
            sku_code VARCHAR(64) NOT NULL,
            sellable_unit_id UUID,
            identity_status VARCHAR(32) NOT NULL DEFAULT 'legacy',
            unit_snapshot VARCHAR(32),
            quantity INTEGER NOT NULL,
            unit_price NUMERIC(12, 2) NOT NULL,
            subtotal NUMERIC(12, 2) NOT NULL,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TIMESTAMP WITH TIME ZONE,
            created_by UUID,
            updated_by UUID,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))

    await session.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{tenant_schema}".ledger_entries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            transaction_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))

    await session.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{tenant_schema}".payments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id UUID NOT NULL REFERENCES "{tenant_schema}".orders(id) ON DELETE CASCADE,
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
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))

    await session.execute(text(f"""
        CREATE INDEX IF NOT EXISTS ix_orders_wholesaler_id ON "{tenant_schema}".orders(wholesaler_id)
    """))
    await session.execute(text(f"""
        CREATE INDEX IF NOT EXISTS ix_orders_retailer_id ON "{tenant_schema}".orders(retailer_id)
    """))
    await session.execute(text(f"""
        CREATE INDEX IF NOT EXISTS ix_orders_status ON "{tenant_schema}".orders(status)
    """))
    await session.execute(text(f"""
        CREATE INDEX IF NOT EXISTS ix_orders_created_at ON "{tenant_schema}".orders(created_at)
    """))

    await session.execute(text(f"""
        CREATE INDEX IF NOT EXISTS ix_order_items_order_id ON "{tenant_schema}".order_items(order_id)
    """))
    await session.execute(text(f"""
        CREATE INDEX IF NOT EXISTS ix_order_items_sku_code ON "{tenant_schema}".order_items(sku_code)
    """))

    await session.execute(text(f"""
        CREATE INDEX IF NOT EXISTS ix_ledger_entries_reference
        ON "{tenant_schema}".ledger_entries(reference_type, reference_id)
    """))
    await session.execute(text(f"""
        CREATE INDEX IF NOT EXISTS ix_ledger_entries_account_type
        ON "{tenant_schema}".ledger_entries(account_type)
    """))
    await session.execute(text(f"""
        CREATE INDEX IF NOT EXISTS ix_ledger_entries_transaction_date
        ON "{tenant_schema}".ledger_entries(transaction_date)
    """))

    await session.execute(text(f"""
        CREATE INDEX IF NOT EXISTS ix_payments_order_id
        ON "{tenant_schema}".payments(order_id)
    """))
    await session.execute(text(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_transaction_id
        ON "{tenant_schema}".payments(transaction_id)
        WHERE transaction_id IS NOT NULL
    """))

    # Phase 3: SKUs, inventory, and retailer pricing tables
    await session.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{tenant_schema}".skus (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            catalog_product_id UUID NOT NULL REFERENCES "{tenant_schema}".catalog_products(id) ON DELETE RESTRICT,
            sku_code VARCHAR(64) NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            unit VARCHAR(32) NOT NULL DEFAULT 'piece',
            package_quantity NUMERIC(12, 3) NOT NULL DEFAULT 1.000,
            category VARCHAR(128),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TIMESTAMP WITH TIME ZONE,
            created_by UUID,
            updated_by UUID,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))

    # Upgrade a pre-existing lightweight test schema without guessing SKU identity.
    await session.execute(text(f'''
        ALTER TABLE "{tenant_schema}".skus
            ADD COLUMN IF NOT EXISTS catalog_product_id UUID,
            ADD COLUMN IF NOT EXISTS package_quantity NUMERIC(12, 3) NOT NULL DEFAULT 1.000
    '''))
    await session.execute(text(f'''
        INSERT INTO "{tenant_schema}".catalog_products
            (id, name, description, category, is_active, is_deleted, deleted_at,
             created_by, updated_by, created_at, updated_at)
        SELECT id, name, description, category, is_active, is_deleted, deleted_at,
               created_by, updated_by, created_at, updated_at
          FROM "{tenant_schema}".skus
         WHERE catalog_product_id IS NULL
        ON CONFLICT (id) DO NOTHING
    '''))
    await session.execute(text(f'''
        UPDATE "{tenant_schema}".skus
           SET catalog_product_id = id
         WHERE catalog_product_id IS NULL
    '''))
    await session.execute(text(f'''
        ALTER TABLE "{tenant_schema}".skus
            ALTER COLUMN catalog_product_id SET NOT NULL
    '''))
    await session.execute(text(f'''
        ALTER TABLE "{tenant_schema}".order_items
            ADD COLUMN IF NOT EXISTS sellable_unit_id UUID,
            ADD COLUMN IF NOT EXISTS identity_status VARCHAR(32) NOT NULL DEFAULT 'legacy',
            ADD COLUMN IF NOT EXISTS unit_snapshot VARCHAR(32)
    '''))
    await session.execute(text(f'''
        DO $$ BEGIN
            ALTER TABLE "{tenant_schema}".skus
                ADD CONSTRAINT fk_skus_catalog_product
                FOREIGN KEY (catalog_product_id)
                REFERENCES "{tenant_schema}".catalog_products(id) ON DELETE RESTRICT;
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    '''))
    await session.execute(text(f'''
        DO $$ BEGIN
            ALTER TABLE "{tenant_schema}".skus
                ADD CONSTRAINT ck_skus_package_quantity_positive CHECK (package_quantity > 0);
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    '''))
    await session.execute(text(f'''
        DO $$ BEGIN
            ALTER TABLE "{tenant_schema}".order_items
                ADD CONSTRAINT fk_order_items_sellable_unit
                FOREIGN KEY (sellable_unit_id)
                REFERENCES "{tenant_schema}".skus(id) ON DELETE RESTRICT;
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    '''))
    await session.execute(text(f'''
        DO $$ BEGIN
            ALTER TABLE "{tenant_schema}".order_items
                ADD CONSTRAINT ck_order_items_identity_status
                CHECK (identity_status IN ('legacy', 'linked_legacy', 'stable'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    '''))
    await session.execute(text(f'''
        DO $$ BEGIN
            ALTER TABLE "{tenant_schema}".order_items
                ADD CONSTRAINT ck_order_items_identity_shape CHECK (
                    (identity_status = 'legacy' AND sellable_unit_id IS NULL) OR
                    (identity_status = 'linked_legacy' AND sellable_unit_id IS NOT NULL) OR
                    (identity_status = 'stable' AND sellable_unit_id IS NOT NULL AND unit_snapshot IS NOT NULL)
                );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    '''))
    await session.execute(text(f'''
        CREATE INDEX IF NOT EXISTS ix_skus_catalog_product_id
        ON "{tenant_schema}".skus(catalog_product_id)
    '''))
    await session.execute(text(f'''
        CREATE INDEX IF NOT EXISTS ix_order_items_sellable_unit_id
        ON "{tenant_schema}".order_items(sellable_unit_id)
    '''))

    await session.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{tenant_schema}".inventory_stocks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sku_id UUID NOT NULL,
            quantity_on_hand NUMERIC(12, 2) NOT NULL DEFAULT 0,
            quantity_reserved NUMERIC(12, 2) NOT NULL DEFAULT 0,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TIMESTAMP WITH TIME ZONE,
            created_by UUID,
            updated_by UUID,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))

    await session.execute(text(f"""
        ALTER TABLE "{tenant_schema}".inventory_stocks
        ADD COLUMN IF NOT EXISTS quantity_reserved NUMERIC(12, 2) NOT NULL DEFAULT 0
    """))

    await session.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{tenant_schema}".inventory_movements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sku_id UUID NOT NULL,
            movement_type VARCHAR(32) NOT NULL,
            quantity NUMERIC(12, 2) NOT NULL,
            quantity_before NUMERIC(12, 2) NOT NULL,
            quantity_after NUMERIC(12, 2) NOT NULL,
            reason TEXT,
            reference_type VARCHAR(50),
            reference_id UUID,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TIMESTAMP WITH TIME ZONE,
            created_by UUID,
            updated_by UUID,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))

    await session.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{tenant_schema}".inventory_reservations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id UUID NOT NULL REFERENCES "{tenant_schema}".orders(id) ON DELETE CASCADE,
            order_item_id UUID NOT NULL REFERENCES "{tenant_schema}".order_items(id) ON DELETE CASCADE,
            sku_id UUID NOT NULL REFERENCES "{tenant_schema}".skus(id) ON DELETE CASCADE,
            sku_code VARCHAR(64) NOT NULL,
            quantity NUMERIC(12, 2) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'reserved',
            reserved_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            consumed_at TIMESTAMP WITH TIME ZONE,
            released_at TIMESTAMP WITH TIME ZONE,
            reference_type VARCHAR(50) NOT NULL DEFAULT 'order',
            reference_id UUID NOT NULL,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TIMESTAMP WITH TIME ZONE,
            created_by UUID,
            updated_by UUID,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_inventory_reservations_quantity_positive CHECK (quantity > 0),
            CONSTRAINT ck_inventory_reservations_status
                CHECK (status IN ('reserved', 'consumed', 'released'))
        )
    """))

    await session.execute(text(f"""
        CREATE INDEX IF NOT EXISTS ix_inventory_reservations_order_id
        ON "{tenant_schema}".inventory_reservations(order_id)
    """))
    await session.execute(text(f"""
        CREATE INDEX IF NOT EXISTS ix_inventory_reservations_sku_id
        ON "{tenant_schema}".inventory_reservations(sku_id)
    """))
    await session.execute(text(f"""
        CREATE INDEX IF NOT EXISTS ix_inventory_reservations_status
        ON "{tenant_schema}".inventory_reservations(status)
    """))
    await session.execute(text(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_reservations_active_order_item
        ON "{tenant_schema}".inventory_reservations(order_item_id)
        WHERE status = 'reserved'
    """))

    await session.execute(text(f"""
        CREATE TABLE IF NOT EXISTS "{tenant_schema}".retailer_prices (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            retailer_id UUID NOT NULL,
            sku_id UUID NOT NULL,
            price NUMERIC(12, 2) NOT NULL CHECK (price > 0),
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TIMESTAMP WITH TIME ZONE,
            created_by UUID,
            updated_by UUID,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (retailer_id, sku_id)
        )
    """))

    await session.execute(text("""
        CREATE OR REPLACE FUNCTION public.prevent_ledger_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                RAISE EXCEPTION 'Ledger entries are immutable. UPDATE operations are not allowed.'
                    USING ERRCODE = 'integrity_constraint_violation',
                          HINT = 'Ledger entries cannot be modified after creation. Create a correction entry instead.';
            END IF;

            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Ledger entries are immutable. DELETE operations are not allowed.'
                    USING ERRCODE = 'integrity_constraint_violation',
                          HINT = 'Ledger entries cannot be deleted. Create a reversal entry instead.';
            END IF;

            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
    """))

    await session.execute(text(f"""
        DROP TRIGGER IF EXISTS prevent_ledger_mod
        ON "{tenant_schema}".ledger_entries
    """))
    await session.execute(text(f"""
        DROP TRIGGER IF EXISTS prevent_ledger_modification_trigger
        ON "{tenant_schema}".ledger_entries
    """))
    await session.execute(text(f"""
        CREATE TRIGGER prevent_ledger_modification_trigger
        BEFORE UPDATE OR DELETE ON "{tenant_schema}".ledger_entries
        FOR EACH ROW
        EXECUTE FUNCTION public.prevent_ledger_modification()
    """))


# ---------------------------------------------------------------------------
# S5-OPS: Robust async_session with search_path re-set after commit
# ---------------------------------------------------------------------------
# Problem: SET LOCAL search_path only lasts until the current transaction
# ends.  Tests that call session.commit() (e.g. test_invariant_violation_
# confirm_zero_total, test_void_vs_cancel_rules) start a new transaction
# and lose the tenant search_path, causing "relation does not exist" errors.
#
# Fix: Use an "after_begin" event listener that automatically re-sets the
# search_path whenever a new transaction begins on the session.
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="function")
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an async database session for tests.

    Uses the test database configured in DATABASE_URL environment variable.
    Each test gets a fresh session that is rolled back after the test.

    For S5-A/S5-B tests: Uses t_test tenant schema for order and ledger tests.

    Guarantees:
    - search_path is set to t_test on EVERY new transaction (survives commit)
    - Session is always rolled back + closed, even on unhandled exceptions
    - Event loop stays alive across the full test suite (session-scoped loop)
    """
    tenant_schema = TEST_TENANT_SCHEMA
    tenant_id = TEST_TENANT_ID

    async with AsyncSessionLocal() as setup_session:
        setup_session.info["tenant_schema"] = tenant_schema
        setup_session.info["tenant_id"] = tenant_id

        # Ensure schema + S5 tables/types/triggers exist (idempotent)
        await _bootstrap_tenant_test_schema(setup_session, tenant_schema)

        # Hard test isolation: remove S5 state machine / ledger rows per test
        await setup_session.execute(
            text(
                f'TRUNCATE TABLE "{tenant_schema}".order_items, '
                f'"{tenant_schema}".payments, '
                f'"{tenant_schema}".ledger_entries, '
                f'"{tenant_schema}".orders '
                "RESTART IDENTITY CASCADE"
            )
        )
        await setup_session.commit()

    # DDL/truncation can invalidate asyncpg prepared statements. Yield a fresh
    # test session so cached setup plans cannot leak into assertions.
    await async_engine.dispose()

    async with AsyncSessionLocal() as session:
        # Store tenant info on the session for middleware / helpers
        session.info["tenant_schema"] = tenant_schema
        session.info["tenant_id"] = tenant_id

        # --- search_path helper -------------------------------------------
        async def _set_search_path(sess: AsyncSession) -> None:
            """Set search_path for the current transaction."""
            await sess.execute(
                text(f'SET LOCAL search_path TO "{tenant_schema}", public')
            )

        # Set search_path for the initial transaction
        await _set_search_path(session)

        # S5-OPS: Register a listener so search_path is re-applied after
        # every commit (which starts a new implicit transaction).
        sync_session = session.sync_session

        @event.listens_for(sync_session, "after_begin")
        def _after_begin(sess, transaction, connection):
            """Re-set search_path whenever a new transaction begins."""
            # We schedule the SET LOCAL via the connection so it runs inside
            # the new transaction that just started.
            connection.execute(
                text(f'SET LOCAL search_path TO "{tenant_schema}", public')
            )

        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            # Always rollback to ensure test isolation
            await session.rollback()
        finally:
            # Remove the listener to avoid leaking across tests
            event.remove(sync_session, "after_begin", _after_begin)
            await session.close()
