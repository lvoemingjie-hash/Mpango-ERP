"""G1-R2E-P1 tenant-DDL authority contract (new file, existing tests untouched).

Authorization: CTO-AUTH-MPANGO-PROMOTION-G1-R2E-P1-AUTHORITY-20260926.

Contract under test (037/038 + provisioner one-way capability):
  1. existence probes read pg_catalog, so genuinely-missing tenant tables are
     rejected BY NAME and never confused with privilege-filtered blindness;
  2. the migration authority reaches app-owned tenant objects ONLY through
     the admin-provisioned one-way membership (GRANT mpango_app TO
     mpango_migrate WITH INHERIT FALSE, SET TRUE) exercised inside the
     narrowest SET ROLE windows, which restore the migration identity after
     every window end AND after exception rollback (SET ROLE survives
     ROLLBACK — proven directly on a live connection);
  3. the capability must NOT confer anything by default: privilege-filtered
     views stay blind and tenant reads stay 42501 for the bare migration
     identity; the runtime role gains nothing (no SET ROLE escalation to the
     authority, no public CREATE, no reverse membership).

Every scenario runs in its own disposable migration-owned database via the
sanctioned three-identity temporary-database harness; cluster-global
mutations (capability revocation, reverse membership) are always restored
through the PRODUCT provisioner path in ``finally`` blocks.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from sqlalchemy import create_engine, text

from tests.async_test_utils import temporary_database_url

BACKEND = Path(__file__).resolve().parents[1]
PROVISIONER = BACKEND / "scripts" / "provision_runtime_db_roles.py"
MIGRATION_038 = BACKEND / "alembic" / "versions" / "038_catalog_identity_vertical_slice.py"
REV_036 = "036_retailer_mvp_identity"
REV_038 = "038_catalog_identity_vertical_slice"
MIGRATE_ROLE = "mpango_migrate"
APP_ROLE = "mpango_app"

pytestmark = pytest.mark.skipif(
    os.environ.get("MPANGO_ALLOW_TEMP_DB_CREATE") != "1",
    reason="set MPANGO_ALLOW_TEMP_DB_CREATE=1 for migration database tests",
)


def _admin_url() -> str:
    url = os.environ.get("TEST_ADMIN_DATABASE_URL")
    if not url:
        pytest.fail(
            "this contract requires TEST_ADMIN_DATABASE_URL (cluster admin on "
            "the maintenance database) for the product provisioner phases")
    return url


def _retarget(url: str, database: str) -> str:
    parsed = urlsplit(url.replace("postgresql+asyncpg://", "postgresql://", 1))
    return urlunsplit(parsed._replace(path=f"/{database}"))


def _db_name(db_url) -> str:
    return urlsplit(str(db_url).replace(
        "postgresql+asyncpg://", "postgresql://", 1)).path.lstrip("/")


def _run(argv: list[str], env_extra: dict[str, str], cwd: str | None = None) -> dict:
    env = dict(os.environ)
    env.update(env_extra)
    proc = subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
    return {"rc": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr}


def _provisioner_env_for_name(database: str) -> dict[str, str]:
    """Provisioner URLs targeting a NAMED database (bootstrap/restore runs)."""
    return {
        "MPANGO_DB_ADMIN_URL": _admin_url(),
        "MPANGO_DB_MIGRATE_URL": _retarget(
            os.environ["TEST_MIGRATION_DATABASE_URL"], database),
        "MPANGO_DB_APP_URL": _retarget(
            os.environ["TEST_DATABASE_URL"], database),
    }


def _provisioner_env(db_url) -> dict[str, str]:
    """Provisioner URLs for an existing disposable database (the harness
    yields the migration-identity URL; .app_url carries the runtime)."""
    return {
        "MPANGO_DB_ADMIN_URL": _admin_url(),
        "MPANGO_DB_MIGRATE_URL": str(db_url).replace(
            "postgresql+asyncpg://", "postgresql://", 1),
        "MPANGO_DB_APP_URL": str(db_url.app_url).replace(
            "postgresql+asyncpg://", "postgresql://", 1),
    }


def _alembic_env(db_url) -> dict[str, str]:
    return {"DATABASE_URL": str(db_url).replace(
        "postgresql://", "postgresql+asyncpg://", 1)}


def _alembic(db_url, revision: str) -> dict:
    return _run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        _alembic_env(db_url), cwd=str(BACKEND))


def _engine(url: str):
    return create_engine(
        str(url).replace("postgresql+asyncpg://", "postgresql://", 1),
        future=True)


def _admin_engine(db_url):
    return create_engine(
        _retarget(_admin_url(), _db_name(db_url)), future=True)


def _build_036_tenant(admin_conn, schema: str, wholesaler: uuid.UUID, *,
                      sentinel: bool) -> None:
    """Register a wholesaler/tenant and create the 036-era tenant shape AS
    the runtime role (admin SET ROLE), so every tenant object is genuinely
    app-owned — the product ownership topology under test.  ``schema`` must
    be ``t_<wholesaler.hex>`` (the registry-derived identity 037/038
    validate)."""
    admin_conn.execute(text(
        "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
        "VALUES (:id, :code, :name, 'active', false)"),
        {"id": wholesaler,
         "code": f"G1R2E{wholesaler.hex[:8].upper()}",
         "name": f"G1R2E {schema[:12]}"})
    admin_conn.execute(text(
        "INSERT INTO public.tenant_registrations ("
        "id, company_name, country, owner_email, status, email_verified_at, "
        "provisioning_started_at, password_hash_cleared_at, wholesaler_id, "
        "tenant_schema, expires_at, is_deleted) VALUES ("
        ":id, :company, 'KE', :email, 'active', now(), now(), now(), "
        ":wholesaler, :schema, now() + interval '1 day', false)"),
        {"id": uuid.uuid4(), "company": f"co {schema[:12]}",
         "email": f"g1r2e_{wholesaler.hex[:6]}@example.com",
         "wholesaler": wholesaler, "schema": schema})
    admin_conn.execute(text(f'SET ROLE "{APP_ROLE}"'))
    try:
        admin_conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        admin_conn.execute(text(f"""
            DO $$ BEGIN
              CREATE TYPE "{schema}".order_status AS ENUM
              ('draft','confirmed','partially_paid','paid','fulfilled',
               'cancelled','voided','returned');
            EXCEPTION WHEN duplicate_object THEN NULL; END $$;
            CREATE TABLE "{schema}".orders (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                wholesaler_id UUID NOT NULL,
                retailer_id UUID NOT NULL,
                status "{schema}".order_status NOT NULL DEFAULT 'draft',
                total_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                is_deleted BOOLEAN DEFAULT FALSE,
                deleted_at TIMESTAMPTZ,
                created_by UUID, updated_by UUID);
            CREATE TABLE "{schema}".payments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL,
                retailer_id UUID NOT NULL,
                transaction_id VARCHAR(64),
                amount NUMERIC(12,2) NOT NULL,
                method VARCHAR(50) NOT NULL DEFAULT 'cash',
                status VARCHAR(50) NOT NULL DEFAULT 'completed',
                idempotency_key VARCHAR(64),
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                is_deleted BOOLEAN DEFAULT FALSE,
                deleted_at TIMESTAMPTZ,
                created_by UUID, updated_by UUID);
            CREATE TABLE "{schema}".permissions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                code VARCHAR(128) NOT NULL UNIQUE,
                description VARCHAR(255));
            CREATE TABLE "{schema}".roles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(64) NOT NULL UNIQUE);
            CREATE TABLE "{schema}".role_permissions (
                role_id UUID NOT NULL REFERENCES "{schema}".roles(id),
                permission_id UUID NOT NULL REFERENCES "{schema}".permissions(id),
                PRIMARY KEY (role_id, permission_id));
            CREATE TABLE "{schema}".skus (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                sku_code VARCHAR(64) NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                category VARCHAR(64),
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false,
                deleted_at TIMESTAMPTZ,
                created_by UUID, updated_by UUID);
            CREATE TABLE "{schema}".order_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL,
                sku_id UUID NOT NULL,
                quantity NUMERIC(12,3) NOT NULL DEFAULT 1,
                unit_price NUMERIC(12,2) NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false);
            CREATE TABLE "{schema}".inventory_stocks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                sku_id UUID NOT NULL,
                quantity NUMERIC(12,3) NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false);
            CREATE TABLE "{schema}".inventory_movements (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                sku_id UUID NOT NULL,
                delta NUMERIC(12,3) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false);
            CREATE TABLE "{schema}".inventory_reservations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_item_id UUID NOT NULL,
                sku_id UUID NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false);
        """))
        admin_conn.execute(text(
            f'INSERT INTO "{schema}".permissions (code, description) VALUES '
            f"('client:payments:create', 'Retailer: create payment')"))
        admin_conn.execute(text(
            f'INSERT INTO "{schema}".roles (name) VALUES '
            f"('admin'), ('retailer_operator')"))
        admin_conn.execute(text(
            f'INSERT INTO "{schema}".role_permissions (role_id, permission_id) '
            f'SELECT r.id, p.id FROM "{schema}".roles r, '
            f'"{schema}".permissions p WHERE r.name = \'retailer_operator\' '
            f"AND p.code = 'client:payments:create'"))
        if sentinel:
            retailer, order, sku, item = (uuid.uuid4() for _ in range(4))
            admin_conn.execute(text(
                f'INSERT INTO "{schema}".orders (id, wholesaler_id, '
                f'retailer_id, status, total_amount, is_deleted) VALUES '
                f"(:id, :w, :r, 'confirmed', 15000.00, false)"),
                {"id": order, "w": wholesaler, "r": retailer})
            admin_conn.execute(text(
                f'INSERT INTO "{schema}".payments (order_id, retailer_id, '
                f'transaction_id, amount, method, status, is_deleted) VALUES '
                f"(:o, :r, 'TX-SENTINEL-0001', 5000.00, 'cash', 'completed', "
                f"false)"),
                {"o": order, "r": retailer})
            admin_conn.execute(text(
                f'INSERT INTO "{schema}".skus (id, sku_code, name, is_active, '
                f'is_deleted) VALUES (:s, :code, :name, true, false)'),
                {"s": sku, "code": f"SKU-{schema[:10]}", "name": "Sentinel SKU"})
            admin_conn.execute(text(
                f'INSERT INTO "{schema}".inventory_stocks (sku_id, quantity, '
                f'is_deleted) VALUES (:s, 100, false)'), {"s": sku})
            admin_conn.execute(text(
                f'INSERT INTO "{schema}".inventory_movements (sku_id, delta, '
                f'is_deleted) VALUES (:s, 100, false)'), {"s": sku})
            admin_conn.execute(text(
                f'INSERT INTO "{schema}".order_items (id, order_id, sku_id, '
                f'quantity, unit_price, is_deleted) VALUES '
                f'(:i, :o, :s, 5, 250.00, false)'),
                {"i": item, "o": order, "s": sku})
            admin_conn.execute(text(
                f'INSERT INTO "{schema}".inventory_reservations '
                f'(order_item_id, sku_id, is_deleted) VALUES '
                f'(:i, :s, false)'), {"i": item, "s": sku})
    finally:
        admin_conn.execute(text("RESET ROLE"))


def _prepare_036_with_tenant(db_url: str, *, sentinel: bool = True) -> str:
    """Bring the disposable database to the 036 pre-state with product
    grants and one app-owned tenant; returns the tenant schema."""
    assert _alembic(db_url, REV_036)["rc"] == 0
    grants = _run(
        [sys.executable, str(PROVISIONER), "--apply-grants"],
        _provisioner_env(db_url))
    assert grants["rc"] == 0, grants["stderr"][-800:]
    wholesaler = uuid.uuid4()
    schema = f"t_{wholesaler.hex}"
    engine = _admin_engine(db_url)
    try:
        with engine.begin() as conn:
            _build_036_tenant(conn, schema, wholesaler, sentinel=sentinel)
    finally:
        engine.dispose()
    return schema


def _fetchone(engine, sql, params=None):
    with engine.connect() as conn:
        return conn.execute(text(sql), params or {}).fetchone()


def _load_038():
    spec = importlib.util.spec_from_file_location(
        "g1r2e_migration_038", MIGRATION_038)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# cluster-global capability fixture (product path; always restored)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def product_capability():
    """Ensure the one-way capability exists cluster-wide via PRODUCT phase 1
    against a disposable bootstrap database, and drop that database."""
    boot = f"test_g1r2e_boot_{uuid.uuid4().hex[:8]}"
    prov = _run(
        [sys.executable, str(PROVISIONER), "--provision"],
        _provisioner_env_for_name(boot))
    assert prov["rc"] == 0, prov["stderr"][-800:]
    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{boot}"')
    finally:
        admin.dispose()
    yield True


# ---------------------------------------------------------------------------
# 1. capability absent -> named refusal, zero residue (negative control)
# ---------------------------------------------------------------------------

def test_capability_absent_named_refusal_and_zero_residue(product_capability):
    admin_maintenance = create_engine(_admin_url())
    try:
        with admin_maintenance.begin() as conn:
            conn.exec_driver_sql(f'REVOKE "{APP_ROLE}" FROM "{MIGRATE_ROLE}"')
    finally:
        admin_maintenance.dispose()
    try:
        source = os.environ["TEST_DATABASE_URL"]
        with temporary_database_url(source, "g1r2eneg") as db_url:
            schema = _prepare_036_with_tenant(db_url, sentinel=True)
            run = _alembic(db_url, REV_038)
            assert run["rc"] != 0
            assert "TenantDDLAuthorityError" in run["stderr"], run["stderr"][-800:]
            assert "capability" in run["stderr"]
            assert "is missing" not in run["stderr"]
            engine = _admin_engine(db_url)
            try:
                assert _fetchone(engine,
                                 "SELECT version_num FROM public.alembic_version"
                                 )[0] == REV_036
                assert _fetchone(engine, (
                    "SELECT format_type(a.atttypid, a.atttypmod) "
                    "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = :s AND c.relname = 'payments' "
                    "AND a.attname = 'transaction_id'"),
                    {"s": schema})[0] == "character varying(64)"
                assert _fetchone(engine, (
                    "SELECT 1 FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid = c.relnamespace WHERE n.nspname = :s "
                    "AND c.relname = 'payment_declarations'"),
                    {"s": schema}) is None
                assert _fetchone(engine, (
                    f'SELECT code FROM "{schema}".permissions LIMIT 1'
                    ))[0] == "client:payments:create"
                assert _fetchone(engine, (
                    f'SELECT amount::text FROM "{schema}".payments LIMIT 1'
                    ))[0] == "5000.00"
            finally:
                engine.dispose()
    finally:
        boot = f"test_g1r2e_res_{uuid.uuid4().hex[:8]}"
        restore = _run(
            [sys.executable, str(PROVISIONER), "--provision"],
            _provisioner_env_for_name(boot))
        assert restore["rc"] == 0, restore["stderr"][-800:]
        admin_maintenance = create_engine(
            _admin_url(), isolation_level="AUTOCOMMIT")
        try:
            with admin_maintenance.connect() as conn:
                conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{boot}"')
        finally:
            admin_maintenance.dispose()


# ---------------------------------------------------------------------------
# 2. capability present -> full 036->038 pass, app-owned, data preserved
# ---------------------------------------------------------------------------

def test_capability_present_full_pass_app_owned(product_capability):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "g1r2epos") as db_url:
        schema = _prepare_036_with_tenant(db_url, sentinel=True)
        # the probe engine is released explicitly: relying on cyclic GC left
        # a pooled admin session attached to the disposable database and the
        # harness teardown (which never terminates other-role sessions) then
        # timed out even though every assertion above had passed
        pre_engine = _admin_engine(db_url)
        try:
            pre_oid = _fetchone(pre_engine, (
                "SELECT c.oid::bigint FROM pg_class c JOIN pg_namespace n "
                "ON n.oid = c.relnamespace WHERE n.nspname = :s "
                "AND c.relname = 'payments'"), {"s": schema})[0]
        finally:
            pre_engine.dispose()
        run = _alembic(db_url, REV_038)
        assert run["rc"] == 0, run["stderr"][-1200:]
        engine = _admin_engine(db_url)
        try:
            assert _fetchone(engine,
                             "SELECT version_num FROM public.alembic_version"
                             )[0] == REV_038
            assert _fetchone(engine, (
                "SELECT format_type(a.atttypid, a.atttypmod) "
                "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :s AND c.relname = 'payments' "
                "AND a.attname = 'transaction_id'"),
                {"s": schema})[0] == "character varying(128)"
            for table in ("payment_declarations", "receipt_sequences",
                          "catalog_products"):
                owner = _fetchone(engine, (
                    "SELECT pg_get_userbyid(c.relowner) FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = :s AND c.relname = :t"),
                    {"s": schema, "t": table})
                assert owner is not None and owner[0] == APP_ROLE, table
            assert _fetchone(engine, (
                "SELECT c.oid::bigint FROM pg_class c JOIN pg_namespace n "
                "ON n.oid = c.relnamespace WHERE n.nspname = :s "
                "AND c.relname = 'payments'"), {"s": schema})[0] == pre_oid
            assert _fetchone(engine, (
                f'SELECT code FROM "{schema}".permissions LIMIT 1'
                ))[0] == "client:payments:declare"
            assert _fetchone(engine, (
                f'SELECT count(*) FROM "{schema}".catalog_products'
                ))[0] == 1
            assert _fetchone(engine, (
                f'SELECT amount::text FROM "{schema}".payments LIMIT 1'
                ))[0] == "5000.00"
            assert _fetchone(engine, (
                f'SELECT identity_status FROM "{schema}".order_items LIMIT 1'
                ))[0] == "linked_legacy"
        finally:
            engine.dispose()
        verify = _run(
            [sys.executable, str(PROVISIONER), "--verify"],
            _provisioner_env(db_url))
        assert verify["rc"] == 0, verify["stdout"][-800:]
        report = json.loads(verify["stdout"][verify["stdout"].index("{"):])
        assert report["ok"] is True
        assert report["checks"]["migration_tenant_authority_capability"]["ok"]
        assert report["checks"][
            "runtime_no_reverse_authority_membership"]["ok"]


# ---------------------------------------------------------------------------
# 3. genuinely missing tenant table -> named rejection, not blindness
# ---------------------------------------------------------------------------

def test_genuinely_missing_table_named_rejection(product_capability):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "g1r2emiss") as db_url:
        schema = _prepare_036_with_tenant(db_url, sentinel=True)
        admin = _admin_engine(db_url)
        try:
            with admin.begin() as conn:
                conn.execute(text(
                    f'DROP TABLE "{schema}".inventory_movements'))
        finally:
            admin.dispose()
        run = _alembic(db_url, REV_038)
        assert run["rc"] != 0
        assert "inventory_movements is missing" in run["stderr"], \
            run["stderr"][-800:]
        assert "TenantDDLAuthorityError" not in run["stderr"]
        engine = _admin_engine(db_url)
        try:
            assert _fetchone(engine,
                             "SELECT version_num FROM public.alembic_version"
                             )[0] == REV_036
        finally:
            engine.dispose()


# ---------------------------------------------------------------------------
# 4. leaked SET ROLE -> the NEXT window refuses by name; and the window
#    restores identity after an in-window exception + transaction rollback
# ---------------------------------------------------------------------------

def test_role_leak_refused_and_exception_restores_identity(product_capability):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "g1r2eleak") as db_url:
        schema = _prepare_036_with_tenant(db_url, sentinel=True)
        module = _load_038()

        engine = _engine(db_url)  # migration identity
        try:
            # (a) leaked SET ROLE: the first window must refuse by name
            with engine.connect() as conn:
                conn.execute(text(f'SET ROLE "{APP_ROLE}"'))
                conn.commit()
                context = MigrationContext.configure(conn)
                operations = Operations(context)
                original_op = module.op
                module.op = operations
                try:
                    with pytest.raises(RuntimeError) as err:
                        module.upgrade()
                    assert err.value.__class__.__name__ == \
                        "TenantDDLAuthorityError"
                    assert "leaked" in str(err.value)
                finally:
                    module.op = original_op
                conn.rollback()
                conn.execute(text("RESET ROLE"))
                conn.commit()

            # (b) in-window failure: identity restored after rollback
            admin = _admin_engine(db_url)
            try:
                with admin.begin() as conn:
                    # poison the tenant so 038's data-quality check fails
                    # INSIDE the preflight window (after SET ROLE app):
                    # an active SKU with a movement but no stock row
                    poison = uuid.uuid4()
                    conn.execute(text(
                        f'INSERT INTO "{schema}".skus (id, sku_code, name, '
                        f'is_active, is_deleted) VALUES ('
                        f":id, 'POISON', 'poison', true, false)"),
                        {"id": poison})
                    conn.execute(text(
                        f'INSERT INTO "{schema}".inventory_movements '
                        f'(sku_id, delta, is_deleted) VALUES '
                        f"(:id, 5, false)"), {"id": poison})
            finally:
                admin.dispose()
            with engine.connect() as conn:
                context = MigrationContext.configure(conn)
                operations = Operations(context)
                original_op = module.op
                module.op = operations
                try:
                    with pytest.raises(RuntimeError) as err:
                        with conn.begin():
                            module.upgrade()
                    assert err.value.__class__.__name__ == "PreflightFailure"
                    assert "inventory evidence but no stock row" in \
                        str(err.value)
                finally:
                    module.op = original_op
                # same connection, after the rolled-back transaction: the
                # window's finally-reset must have restored the identity
                assert conn.execute(text("SELECT current_user")).scalar() \
                    == MIGRATE_ROLE
                assert conn.execute(text("SELECT session_user")).scalar() \
                    == MIGRATE_ROLE
                # zero residue from the failed run
                assert conn.execute(text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid = c.relnamespace WHERE n.nspname = :s "
                    "AND c.relname = 'catalog_products'"),
                    {"s": schema}).scalar() == 0
        finally:
            engine.dispose()


# ---------------------------------------------------------------------------
# 5. default non-inheritance + runtime gains nothing (probe mirror)
# ---------------------------------------------------------------------------

def test_default_non_inheritance_and_runtime_gains_nothing(product_capability):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "g1r2enonin") as db_url:
        schema = _prepare_036_with_tenant(db_url, sentinel=True)

        engine = _engine(db_url)  # migration identity
        try:
            with engine.connect() as conn:
                assert conn.execute(text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = :s"), {"s": schema}).scalar() == 0
                assert conn.execute(text(
                    "SELECT count(*) FROM pg_catalog.pg_class c "
                    "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = :s AND c.relkind IN ('r','p')"),
                    {"s": schema}).scalar() > 0
                assert conn.execute(text(
                    "SELECT pg_has_role(current_user, :r, 'MEMBER')"),
                    {"r": APP_ROLE}).scalar() is True
                assert conn.execute(text(
                    "SELECT pg_has_role(current_user, :r, 'USAGE')"),
                    {"r": APP_ROLE}).scalar() is False
                with pytest.raises(Exception) as err:
                    conn.execute(text(
                        f'SELECT count(*) FROM "{schema}".payments'))
                assert "42501" in str(err.value) or \
                    "permission denied" in str(err.value).lower()
                conn.rollback()
                # explicit window: reads and DDL succeed, then identity back
                conn.execute(text(f'SET ROLE "{APP_ROLE}"'))
                assert conn.execute(text(
                    f'SELECT count(*) FROM "{schema}".payments')).scalar() == 1
                conn.execute(text("RESET ROLE"))
                assert conn.execute(
                    text("SELECT current_user")).scalar() == MIGRATE_ROLE
        finally:
            engine.dispose()

        app_engine = _engine(
            db_url.app_url)
        try:
            with app_engine.connect() as conn:
                assert conn.execute(
                    text("SELECT current_user")).scalar() == APP_ROLE
                with pytest.raises(Exception) as err:
                    conn.execute(text(f'SET ROLE "{MIGRATE_ROLE}"'))
                assert "42501" in str(err.value) or \
                    "permission denied" in str(err.value).lower()
                conn.rollback()
                with pytest.raises(Exception) as err:
                    conn.execute(text(
                        "CREATE TABLE public.should_fail(id int)"))
                assert "42501" in str(err.value) or \
                    "permission denied" in str(err.value).lower()
                conn.rollback()
        finally:
            app_engine.dispose()


# ---------------------------------------------------------------------------
# 6. reverse membership -> product --verify named RED, restore -> GREEN
# ---------------------------------------------------------------------------

def test_reverse_membership_named_red_then_green(product_capability):
    admin_maintenance = create_engine(_admin_url())
    try:
        source = os.environ["TEST_DATABASE_URL"]
        with temporary_database_url(source, "g1r2erev") as db_url:
            assert _alembic(db_url, REV_036)["rc"] == 0
            grants = _run(
                [sys.executable, str(PROVISIONER), "--apply-grants"],
                _provisioner_env(db_url))
            assert grants["rc"] == 0, grants["stderr"][-800:]

            def _verify():
                run = _run(
                    [sys.executable, str(PROVISIONER), "--verify"],
                    _provisioner_env(db_url))
                payload = json.loads(
                    run["stdout"][run["stdout"].index("{"):])
                return run["rc"], payload

            rc, report = _verify()
            assert rc == 0 and report["ok"] is True

            # PostgreSQL refuses circular memberships, so the forward
            # capability is revoked first; the reverse membership is then the
            # ONLY cross-role relationship while the RED proof runs.
            with admin_maintenance.begin() as conn:
                conn.exec_driver_sql(f'REVOKE "{APP_ROLE}" FROM "{MIGRATE_ROLE}"')
                conn.exec_driver_sql(
                    f'GRANT "{MIGRATE_ROLE}" TO "{APP_ROLE}"')
            try:
                rc, report = _verify()
                assert rc == 2 and report["ok"] is False
                reverse_checks = [
                    name for name, check in report["checks"].items()
                    if name in ("runtime_not_member_of_authority",
                                "runtime_no_reverse_authority_membership")
                    and not check["ok"]
                ]
                assert reverse_checks, report["checks"].keys()
            finally:
                with admin_maintenance.begin() as conn:
                    conn.exec_driver_sql(
                        f'REVOKE "{MIGRATE_ROLE}" FROM "{APP_ROLE}"')

            # restore the forward capability through the PRODUCT path
            boot = f"test_g1r2e_rev_{uuid.uuid4().hex[:8]}"
            restore = _run(
                [sys.executable, str(PROVISIONER), "--provision"],
                _provisioner_env_for_name(boot))
            assert restore["rc"] == 0, restore["stderr"][-800:]
            dropper = create_engine(
                _admin_url(), isolation_level="AUTOCOMMIT")
            try:
                with dropper.connect() as conn:
                    conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{boot}"')
            finally:
                dropper.dispose()

            rc, report = _verify()
            assert rc == 0 and report["ok"] is True
    finally:
        admin_maintenance.dispose()


# ---------------------------------------------------------------------------
# 7. provisioner capability idempotency and option normalization
# ---------------------------------------------------------------------------

def test_provisioner_capability_idempotent_and_normalizing(product_capability):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "g1r2eidem") as db_url:
        # --verify reads the migration-owned guard function and the
        # runtime grants, so the disposable database needs the real 036
        # pre-state plus phase-3 grants first.
        assert _alembic(db_url, REV_036)["rc"] == 0
        grants = _run(
            [sys.executable, str(PROVISIONER), "--apply-grants"],
            _provisioner_env(db_url))
        assert grants["rc"] == 0, grants["stderr"][-800:]
        env = _provisioner_env(db_url)
        # The capability already exists cluster-wide (module fixture);
        # provisioning must be idempotent and report it as already present.
        first = _run([sys.executable, str(PROVISIONER), "--provision"], env)
        assert first["rc"] == 0, first["stderr"][-800:]
        assert "already exists (INHERIT FALSE, SET TRUE)" in first["stdout"]

        # Corrupt the options cluster-wide, then let the PRODUCT provisioner
        # normalize them back; --verify must pass again afterwards.
        admin_maintenance = create_engine(_admin_url())
        try:
            with admin_maintenance.begin() as conn:
                conn.exec_driver_sql(
                    f'GRANT "{APP_ROLE}" TO "{MIGRATE_ROLE}" '
                    "WITH INHERIT TRUE, SET FALSE")
        finally:
            admin_maintenance.dispose()
        try:
            verify_bad = _run(
                [sys.executable, str(PROVISIONER), "--verify"],
                _provisioner_env(db_url))
            payload = json.loads(
                verify_bad["stdout"][verify_bad["stdout"].index("{"):])
            assert payload["checks"][
                "migration_tenant_authority_capability"]["ok"] is False

            normalized = _run(
                [sys.executable, str(PROVISIONER), "--provision"], env)
            assert normalized["rc"] == 0, normalized["stderr"][-800:]

            verify_good = _run(
                [sys.executable, str(PROVISIONER), "--verify"],
                _provisioner_env(db_url))
            payload = json.loads(
                verify_good["stdout"][verify_good["stdout"].index("{"):])
            assert payload["ok"] is True
            assert payload["checks"][
                "migration_tenant_authority_capability"]["ok"] is True
        finally:
            # belt and braces: product path re-normalizes if anything failed
            _run([sys.executable, str(PROVISIONER), "--provision"], env)


# ===========================================================================
# G1-R2E-P1R1-039 authority closure (appended 2026-09-28; the seven original
# nodes above are byte-identical). Authorization:
# CTO-AUTH-MPANGO-PROMOTION-G1-R2E-P1R1-039-AUTHORITY-20260928.
#
# New coverage: 039 positive value-chain on two app-owned tenants (036-era
# pre-state, one valid non-empty tenant + one empty), same-connection
# identity restoration across a full in-process 036->039 upgrade, and the
# named fail-closed refusals specific to the 039 phases (capability absence
# from 038, reverse membership, mixed ownership, old confirmed+cash shape,
# missing live binding, stale P14 cache, genuinely-missing orders after
# 038, injected window-body failure, and the SET-success..token-return
# handshake gap).
# ===========================================================================

REV_039 = "039_order_credit_holds"
MIGRATION_039 = BACKEND / "alembic" / "versions" / "039_order_credit_holds.py"


def _load_039():
    spec = importlib.util.spec_from_file_location(
        "g1r2e_p1r1_migration_039", MIGRATION_039)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_036_positive_tenant(admin_conn, schema, wholesaler, *, shape):
    """036-era app-owned tenant with the R2-valid business shapes:
    'positive' (partially_paid 15000 + cash 5000 + live binding at the 038
    exposure-only cache value 0.00 + inventory sentinels), 'positive_nobind'
    (no public binding rows), 'positive_stale_cache' (binding drifted to
    500.00), 'empty' (registry + tables only)."""
    admin_conn.execute(text(
        "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
        "VALUES (:id, :code, :name, 'active', false)"),
        {"id": wholesaler, "code": f"R2E039{wholesaler.hex[:8].upper()}",
         "name": f"R2E039 {schema[:14]}"})
    admin_conn.execute(text(
        "INSERT INTO public.tenant_registrations ("
        "id, company_name, country, owner_email, status, email_verified_at, "
        "provisioning_started_at, password_hash_cleared_at, wholesaler_id, "
        "tenant_schema, expires_at, is_deleted) VALUES ("
        ":id, :company, 'KE', :email, 'active', now(), now(), now(), "
        ":wholesaler, :schema, now() + interval '1 day', false)"),
        {"id": uuid.uuid4(), "company": f"co {schema[:12]}",
         "email": f"r2e039_{wholesaler.hex[:6]}@example.com",
         "wholesaler": wholesaler, "schema": schema})
    admin_conn.execute(text(f'SET ROLE "{APP_ROLE}"'))
    try:
        admin_conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        admin_conn.execute(text(f"""
            DO $$ BEGIN
              CREATE TYPE "{schema}".order_status AS ENUM
              ('draft','confirmed','partially_paid','paid','fulfilled',
               'cancelled','voided','returned');
            EXCEPTION WHEN duplicate_object THEN NULL; END $$;
            CREATE TABLE "{schema}".orders (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                wholesaler_id UUID NOT NULL,
                retailer_id UUID NOT NULL,
                status "{schema}".order_status NOT NULL DEFAULT 'draft',
                total_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                is_deleted BOOLEAN DEFAULT FALSE,
                deleted_at TIMESTAMPTZ,
                created_by UUID, updated_by UUID);
            CREATE TABLE "{schema}".payments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL,
                retailer_id UUID NOT NULL,
                transaction_id VARCHAR(64),
                amount NUMERIC(12,2) NOT NULL,
                method VARCHAR(50) NOT NULL DEFAULT 'cash',
                status VARCHAR(50) NOT NULL DEFAULT 'completed',
                idempotency_key VARCHAR(64),
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                is_deleted BOOLEAN DEFAULT FALSE,
                deleted_at TIMESTAMPTZ,
                created_by UUID, updated_by UUID);
            CREATE TABLE "{schema}".permissions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                code VARCHAR(128) NOT NULL UNIQUE,
                description VARCHAR(255));
            CREATE TABLE "{schema}".roles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(64) NOT NULL UNIQUE);
            CREATE TABLE "{schema}".role_permissions (
                role_id UUID NOT NULL REFERENCES "{schema}".roles(id),
                permission_id UUID NOT NULL REFERENCES "{schema}".permissions(id),
                PRIMARY KEY (role_id, permission_id));
            CREATE TABLE "{schema}".skus (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                sku_code VARCHAR(64) NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                category VARCHAR(64),
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false,
                deleted_at TIMESTAMPTZ,
                created_by UUID, updated_by UUID);
            CREATE TABLE "{schema}".order_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL,
                sku_id UUID NOT NULL,
                quantity NUMERIC(12,3) NOT NULL DEFAULT 1,
                unit_price NUMERIC(12,2) NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false);
            CREATE TABLE "{schema}".inventory_stocks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                sku_id UUID NOT NULL,
                quantity NUMERIC(12,3) NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false);
            CREATE TABLE "{schema}".inventory_movements (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                sku_id UUID NOT NULL,
                delta NUMERIC(12,3) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false);
            CREATE TABLE "{schema}".inventory_reservations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_item_id UUID NOT NULL,
                sku_id UUID NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false);
        """))
        admin_conn.execute(text(
            f'INSERT INTO "{schema}".permissions (code, description) VALUES '
            f"('client:payments:create', 'Retailer: create payment')"))
        admin_conn.execute(text(
            f'INSERT INTO "{schema}".roles (name) VALUES '
            f"('admin'), ('retailer_operator')"))
        admin_conn.execute(text(
            f'INSERT INTO "{schema}".role_permissions (role_id, permission_id) '
            f'SELECT r.id, p.id FROM "{schema}".roles r, '
            f'"{schema}".permissions p WHERE r.name = \'retailer_operator\' '
            f"AND p.code = 'client:payments:create'"))
        if shape != "empty":
            retailer, order, sku, item = (uuid.uuid4() for _ in range(4))
            admin_conn.execute(text(
                f'INSERT INTO "{schema}".orders (id, wholesaler_id, '
                f'retailer_id, status, total_amount, is_deleted) VALUES '
                f"(:id, :w, :r, 'partially_paid', 15000.00, false)"),
                {"id": order, "w": wholesaler, "r": retailer})
            admin_conn.execute(text(
                f'INSERT INTO "{schema}".payments (order_id, retailer_id, '
                f'transaction_id, amount, method, status, is_deleted) '
                f"VALUES (:o, :r, 'TX-039-0001', 5000.00, 'cash', "
                f"'completed', false)"),
                {"o": order, "r": retailer})
            admin_conn.execute(text(
                f'INSERT INTO "{schema}".skus (id, sku_code, name, '
                f'is_active, is_deleted) VALUES (:s, :code, '
                f"'039 Sentinel SKU', true, false)"),
                {"s": sku, "code": f"SKU-039-{schema[:8]}"})
            admin_conn.execute(text(
                f'INSERT INTO "{schema}".inventory_stocks (sku_id, quantity, '
                f'is_deleted) VALUES (:s, 100, false)'), {"s": sku})
            admin_conn.execute(text(
                f'INSERT INTO "{schema}".inventory_movements (sku_id, delta, '
                f'is_deleted) VALUES (:s, 100, false)'), {"s": sku})
            admin_conn.execute(text(
                f'INSERT INTO "{schema}".order_items (id, order_id, sku_id, '
                f'quantity, unit_price, is_deleted) VALUES '
                f"(:i, :o, :s, 5, 250.00, false)"),
                {"i": item, "o": order, "s": sku})
            admin_conn.execute(text(
                f'INSERT INTO "{schema}".inventory_reservations '
                f'(order_item_id, sku_id, is_deleted) VALUES '
                f"(:i, :s, false)"), {"i": item, "s": sku})
            if shape != "positive_nobind":
                cache = "500.00" if shape == "positive_stale_cache" else "0.00"
                admin_conn.execute(text("RESET ROLE"))
                admin_conn.execute(text(
                    "INSERT INTO public.retailers (id, phone, name, "
                    "is_deleted) VALUES (:r, :phone, '039 Retailer', false)"),
                    {"r": retailer, "phone": f"r039-{retailer.hex[:20]}"})
                admin_conn.execute(text(
                    "INSERT INTO public.wholesaler_retailer_bindings "
                    "(wholesaler_id, retailer_id, status, "
                    "outstanding_balance, is_deleted) VALUES "
                    "(:w, :r, 'active', CAST(:cache AS numeric(12,2)), "
                    "false)"),
                    {"w": wholesaler, "r": retailer, "cache": cache})
                admin_conn.execute(text(f'SET ROLE "{APP_ROLE}"'))
    finally:
        try:
            admin_conn.execute(text("RESET ROLE"))
        except Exception:
            # a failed statement aborted the transaction; reset needs a
            # usable transaction first (25P02), the outer context still
            # rolls the partial build back
            admin_conn.rollback()
            admin_conn.execute(text("RESET ROLE"))


def _prepare_036_tenants(db_url, shapes):
    """036 pre-state + product grants + one app-owned tenant per entry
    (key -> shape). Returns key -> schema mapping."""
    assert _alembic(db_url, REV_036)["rc"] == 0
    grants = _run(
        [sys.executable, str(PROVISIONER), "--apply-grants"],
        _provisioner_env(db_url))
    assert grants["rc"] == 0, grants["stderr"][-800:]
    out = {}
    engine = _admin_engine(db_url)
    try:
        with engine.begin() as conn:
            for key, shape in shapes.items():
                wholesaler = uuid.uuid4()
                schema = f"t_{wholesaler.hex}"
                _build_036_positive_tenant(conn, schema, wholesaler,
                                           shape=shape)
                out[key] = schema
    finally:
        engine.dispose()
    return out


# ---------------------------------------------------------------------------
# 8. 039 positive value-chain: two app-owned tenants, single 036->039
# ---------------------------------------------------------------------------

def test_039_full_pass_two_app_owned_tenants_value_chain(product_capability):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "g1r2e039pos") as db_url:
        schemas = _prepare_036_tenants(
            db_url, {"alpha": "positive", "beta": "empty"})
        alpha, beta = schemas["alpha"], schemas["beta"]
        run = _alembic(db_url, "head")
        assert run["rc"] == 0, run["stderr"][-1500:]
        engine = _admin_engine(db_url)
        try:
            assert _fetchone(engine,
                             "SELECT version_num FROM public.alembic_version"
                             )[0] == REV_039
            for s in (alpha, beta):
                owner = _fetchone(engine, (
                    "SELECT pg_get_userbyid(c.relowner) FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname=:s AND c.relname='order_credit_holds'"),
                    {"s": s})
                assert owner and owner[0] == APP_ROLE, s
            hold = _fetchone(engine, (
                f'SELECT h.amount::text, h.remaining_amount::text, h.status, '
                f'h.created_by::text FROM "{alpha}".order_credit_holds h '
                f'JOIN "{alpha}".orders o ON o.id=h.order_id'))
            assert hold == ("15000.00", "10000.00", "active", None), hold
            assert _fetchone(engine, (
                f'SELECT count(*) FROM "{alpha}".order_credit_holds'
                ))[0] == 1  # one lifecycle row per order
            assert _fetchone(engine, (
                f'SELECT count(*) FROM "{beta}".order_credit_holds'))[0] == 0
            # legal cache change: 038 exposure-only 0.00 -> holds + exposure
            assert _fetchone(engine, (
                "SELECT outstanding_balance::text FROM "
                "public.wholesaler_retailer_bindings "
                "WHERE is_deleted IS FALSE"))[0] == "10000.00"
            # conservation of the original business/financial rows
            assert _fetchone(engine, (
                f'SELECT status::text, total_amount::text, is_deleted '
                f'FROM "{alpha}".orders')) ==                 ("partially_paid", "15000.00", False)
            assert _fetchone(engine, (
                f'SELECT amount::text, method, is_deleted FROM '
                f'"{alpha}".payments')) == ("5000.00", "cash", False)
            assert _fetchone(engine, (
                f'SELECT st.quantity::text FROM "{alpha}".inventory_stocks st '
                f'JOIN "{alpha}".skus s ON s.id=st.sku_id'))[0] == "100.000"
            assert _fetchone(engine, (
                f'SELECT count(*) FROM "{alpha}".inventory_reservations '
                f'WHERE is_deleted IS FALSE'))[0] == 1
            assert _fetchone(engine, (
                f'SELECT quantity::text, unit_price::text FROM '
                f'"{alpha}".order_items')) == ("5.000", "250.00")
            # 037 rename happened on the way through (create is gone)
            with engine.connect() as codes_conn:
                codes = {r[0] for r in codes_conn.execute(text(
                    f'SELECT code FROM "{alpha}".permissions'))}
            assert "client:payments:declare" in codes
            assert "client:payments:create" not in codes
        finally:
            engine.dispose()
        verify = _run(
            [sys.executable, str(PROVISIONER), "--verify"],
            _provisioner_env(db_url))
        assert verify["rc"] == 0, verify["stdout"][-800:]


# ---------------------------------------------------------------------------
# 9. full in-process 036->039: identity restored on the SAME connection
# ---------------------------------------------------------------------------

def test_039_upgrade_restores_identity_on_same_connection(product_capability):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "g1r2e039ident") as db_url:
        schemas = _prepare_036_tenants(db_url, {"alpha": "positive"})
        module = _load_039()
        engine = _engine(db_url)  # migration identity
        try:
            with engine.connect() as conn:
                from alembic.migration import MigrationContext
                from alembic.operations import Operations
                original_op = module.op
                module.op = Operations(MigrationContext.configure(conn))
                try:
                    with conn.begin():
                        module.upgrade()
                finally:
                    module.op = original_op
                # same live connection, after the committed upgrade: every
                # window must have RESET ROLEd back to the migration identity
                assert conn.execute(
                    text("SELECT current_user")).scalar() == MIGRATE_ROLE
                assert conn.execute(
                    text("SELECT session_user")).scalar() == MIGRATE_ROLE
                # a direct module.upgrade() does not stamp alembic_version;
                # prove the migration effect via the ADMIN identity — after
                # the reset the migration identity must be 42501-blind to
                # app-owned tenant tables again (by design)
                admin = _admin_engine(db_url)
                try:
                    assert _fetchone(admin, (
                        f'SELECT count(*) FROM "{schemas["alpha"]}".'
                        f'order_credit_holds'))[0] == 1
                    assert _fetchone(admin, (
                        'SELECT outstanding_balance::text FROM '
                        'public.wholesaler_retailer_bindings '
                        'WHERE is_deleted IS FALSE'))[0] == "10000.00"
                finally:
                    admin.dispose()
                with pytest.raises(Exception) as err:
                    conn.execute(text(
                        f'SELECT count(*) FROM "{schemas["alpha"]}".'
                        f'order_credit_holds'))
                assert "42501" in str(err.value) or                     "permission denied" in str(err.value).lower()
                conn.rollback()
        finally:
            engine.dispose()


# ---------------------------------------------------------------------------
# 10. capability absent (from 038) -> 039 named refusal, zero residue
# ---------------------------------------------------------------------------

def test_039_capability_absent_named_refusal_from_038(product_capability):
    admin_maintenance = create_engine(_admin_url())
    try:
        source = os.environ["TEST_DATABASE_URL"]
        with temporary_database_url(source, "g1r2e039cap") as db_url:
            schemas = _prepare_036_tenants(db_url, {"alpha": "positive"})
            up38 = _alembic(db_url, REV_038)
            assert up38["rc"] == 0, up38["stderr"][-800:]
            # revoke ONLY after 038 is reached: the 039 window alone must
            # refuse (037/038 already needed the capability on the way up)
            with admin_maintenance.begin() as conn:
                conn.exec_driver_sql(
                    f'REVOKE "{APP_ROLE}" FROM "{MIGRATE_ROLE}"')
            try:
                run = _alembic(db_url, "head")
                assert run["rc"] != 0
                assert "TenantDDLAuthorityError" in run["stderr"],                     run["stderr"][-800:]
                assert "capability" in run["stderr"]
                assert "is missing" not in run["stderr"]
                engine = _admin_engine(db_url)
                try:
                    assert _fetchone(engine,
                                     "SELECT version_num FROM public.alembic_"
                                     "version")[0] == REV_038
                    assert _fetchone(engine, (
                        "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                        "ON n.oid=c.relnamespace WHERE n.nspname=:s AND "
                        "c.relname='order_credit_holds'"),
                        {"s": schemas["alpha"]})[0] == 0
                    assert _fetchone(engine, (
                        f'SELECT amount::text FROM '
                        f'"{schemas["alpha"]}".payments'))[0] == "5000.00"
                finally:
                    engine.dispose()
            finally:
                # restore the capability through the PRODUCT path even when
                # an assertion fails (cluster-global grant is what matters)
                boot = f"test_g1r2e039_res_{uuid.uuid4().hex[:8]}"
                restore = _run(
                    [sys.executable, str(PROVISIONER), "--provision"],
                    _provisioner_env_for_name(boot))
                assert restore["rc"] == 0, restore["stderr"][-800:]
                dropper = create_engine(
                    _admin_url(), isolation_level="AUTOCOMMIT")
                try:
                    with dropper.connect() as conn:
                        conn.exec_driver_sql(
                            f'DROP DATABASE IF EXISTS "{boot}"')
                finally:
                    dropper.dispose()
    finally:
        admin_maintenance.dispose()


# ---------------------------------------------------------------------------
# 11. reverse membership -> 039 fail-closed and product --verify RED
# ---------------------------------------------------------------------------

def test_039_reverse_membership_fail_closed(product_capability):
    admin_maintenance = create_engine(_admin_url())
    try:
        source = os.environ["TEST_DATABASE_URL"]
        with temporary_database_url(source, "g1r2e039rev") as db_url:
            schemas = _prepare_036_tenants(db_url, {"alpha": "positive"})
            up38 = _alembic(db_url, REV_038)
            assert up38["rc"] == 0, up38["stderr"][-800:]
            # PG refuses circular memberships: forward revoked first, the
            # reverse membership is then the only cross-role relationship.
            with admin_maintenance.begin() as conn:
                conn.exec_driver_sql(
                    f'REVOKE "{APP_ROLE}" FROM "{MIGRATE_ROLE}"')
                conn.exec_driver_sql(
                    f'GRANT "{MIGRATE_ROLE}" TO "{APP_ROLE}"')
            try:
                run = _alembic(db_url, "head")
                assert run["rc"] != 0
                assert "TenantDDLAuthorityError" in run["stderr"], \
                    run["stderr"][-800:]
                engine = _admin_engine(db_url)
                try:
                    assert _fetchone(engine,
                                     "SELECT version_num FROM public.alembic_"
                                     "version")[0] == REV_038
                finally:
                    engine.dispose()
            finally:
                with admin_maintenance.begin() as conn:
                    conn.exec_driver_sql(
                        f'REVOKE "{MIGRATE_ROLE}" FROM "{APP_ROLE}"')
                boot = f"test_g1r2e039_rev_{uuid.uuid4().hex[:8]}"
                restore = _run(
                    [sys.executable, str(PROVISIONER), "--provision"],
                    _provisioner_env_for_name(boot))
                assert restore["rc"] == 0, restore["stderr"][-800:]
                dropper = create_engine(
                    _admin_url(), isolation_level="AUTOCOMMIT")
                try:
                    with dropper.connect() as conn:
                        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{boot}"')
                finally:
                    dropper.dispose()
    finally:
        admin_maintenance.dispose()


# ---------------------------------------------------------------------------
# 12. mixed tenant ownership -> named refusal before any write
# ---------------------------------------------------------------------------

def test_039_mixed_tenant_ownership_refused(product_capability):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "g1r2e039mix") as db_url:
        schemas = _prepare_036_tenants(
            db_url, {"alpha": "positive", "gamma": "positive"})
        up38 = _alembic(db_url, REV_038)
        assert up38["rc"] == 0, up38["stderr"][-800:]
        admin = _admin_engine(db_url)
        try:
            with admin.begin() as conn:
                conn.execute(text(
                    f'ALTER SCHEMA "{schemas["gamma"]}" '
                    f'OWNER TO "{MIGRATE_ROLE}"'))
        finally:
            admin.dispose()
        run = _alembic(db_url, "head")
        assert run["rc"] != 0
        assert "mixed tenant ownership" in run["stderr"], run["stderr"][-800:]
        engine = _admin_engine(db_url)
        try:
            assert _fetchone(engine,
                             "SELECT version_num FROM public.alembic_version"
                             )[0] == REV_038
            for s in schemas.values():
                assert _fetchone(engine, (
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid=c.relnamespace WHERE n.nspname=:s AND "
                    "c.relname='order_credit_holds'"),
                    {"s": s})[0] == 0
        finally:
            engine.dispose()


# ---------------------------------------------------------------------------
# 13. old confirmed+cash sentinel -> named C3 refusal (erratum, permanent)
# ---------------------------------------------------------------------------

def test_039_old_confirmed_cash_shape_named_c3_refusal(product_capability):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "g1r2e039c3old") as db_url:
        schema = _prepare_036_with_tenant(db_url, sentinel=True)
        run = _alembic(db_url, "head")
        assert run["rc"] != 0
        assert "C3" in run["stderr"], run["stderr"][-800:]
        assert "migration state matrix" in run["stderr"]
        assert "is missing" not in run["stderr"]
        engine = _admin_engine(db_url)
        try:
            assert _fetchone(engine,
                             "SELECT version_num FROM public.alembic_version"
                             )[0] == REV_036
            assert _fetchone(engine, (
                f'SELECT status::text, total_amount::text FROM '
                f'"{schema}".orders')) == ("confirmed", "15000.00")
            assert _fetchone(engine, (
                f'SELECT amount::text FROM "{schema}".payments'))[0] == \
                "5000.00"
        finally:
            engine.dispose()


# ---------------------------------------------------------------------------
# 14. missing live binding -> named P12 refusal
# ---------------------------------------------------------------------------

def test_039_missing_live_binding_named_p12_refusal(product_capability):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "g1r2e039p12") as db_url:
        schemas = _prepare_036_tenants(db_url, {"alpha": "positive_nobind"})
        run = _alembic(db_url, "head")
        assert run["rc"] != 0
        assert "lack a live binding" in run["stderr"], run["stderr"][-800:]
        engine = _admin_engine(db_url)
        try:
            assert _fetchone(engine,
                             "SELECT version_num FROM public.alembic_version"
                             )[0] == REV_036
            assert _fetchone(engine, (
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                "ON n.oid=c.relnamespace WHERE n.nspname=:s AND "
                "c.relname='order_credit_holds'"),
                {"s": schemas["alpha"]})[0] == 0
        finally:
            engine.dispose()


# ---------------------------------------------------------------------------
# 15. stale 038 cache -> named P14 refusal (never silently repaired)
# ---------------------------------------------------------------------------

def test_039_stale_binding_cache_named_p14_refusal(product_capability):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "g1r2e039p14") as db_url:
        schemas = _prepare_036_tenants(
            db_url, {"alpha": "positive_stale_cache"})
        run = _alembic(db_url, "head")
        assert run["rc"] != 0
        assert "P14 cache proof failed" in run["stderr"], run["stderr"][-800:]
        engine = _admin_engine(db_url)
        try:
            assert _fetchone(engine,
                             "SELECT version_num FROM public.alembic_version"
                             )[0] == REV_036
            # the drifted cache is NOT repaired by the failed run
            assert _fetchone(engine, (
                "SELECT outstanding_balance::text FROM "
                "public.wholesaler_retailer_bindings "
                "WHERE is_deleted IS FALSE"))[0] == "500.00"
        finally:
            engine.dispose()


# ---------------------------------------------------------------------------
# 16. genuinely missing tenant orders (after 038) -> named refusal
# ---------------------------------------------------------------------------

def test_039_true_missing_orders_after_038_refused(product_capability):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "g1r2e039miss") as db_url:
        schemas = _prepare_036_tenants(db_url, {"alpha": "positive"})
        up38 = _alembic(db_url, REV_038)
        assert up38["rc"] == 0, up38["stderr"][-800:]
        admin = _admin_engine(db_url)
        try:
            with admin.begin() as conn:
                conn.execute(text(
                    f'DROP TABLE "{schemas["alpha"]}".orders CASCADE'))
        finally:
            admin.dispose()
        run = _alembic(db_url, "head")
        assert run["rc"] != 0
        assert "orders is missing" in run["stderr"], run["stderr"][-800:]
        assert "TenantDDLAuthorityError" not in run["stderr"]
        engine = _admin_engine(db_url)
        try:
            assert _fetchone(engine,
                             "SELECT version_num FROM public.alembic_version"
                             )[0] == REV_038
        finally:
            engine.dispose()


# ---------------------------------------------------------------------------
# 17. injected window-body failure -> identity restored, zero residue
# ---------------------------------------------------------------------------

def test_039_window_body_interruption_restores_identity(product_capability):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "g1r2e039body") as db_url:
        schemas = _prepare_036_tenants(db_url, {"alpha": "positive"})
        up38 = _alembic(db_url, REV_038)
        assert up38["rc"] == 0, up38["stderr"][-800:]
        module = _load_039()
        original_backfill = module._backfill_holds

        def exploding_backfill(bind, schema):
            raise RuntimeError("injected body failure inside the B window")

        module._backfill_holds = exploding_backfill
        engine = _engine(db_url)  # migration identity
        try:
            from alembic.migration import MigrationContext
            from alembic.operations import Operations
            with engine.connect() as conn:
                module.op = Operations(MigrationContext.configure(conn))
                try:
                    with pytest.raises(RuntimeError) as err:
                        with conn.begin():
                            module.upgrade()
                    assert "injected body failure" in str(err.value)
                finally:
                    module.op = None
                    module._backfill_holds = original_backfill
                # same connection after the aborted upgrade: identity back
                assert conn.execute(
                    text("SELECT current_user")).scalar() == MIGRATE_ROLE
                assert conn.execute(
                    text("SELECT session_user")).scalar() == MIGRATE_ROLE
                conn.rollback()
                assert conn.execute(text(
                    "SELECT version_num FROM public.alembic_version")
                ).scalar() == REV_038
                assert conn.execute(text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid=c.relnamespace WHERE n.nspname=:s AND "
                    "c.relname='order_credit_holds'"),
                    {"s": schemas["alpha"]}).scalar() == 0
                assert conn.execute(text(
                    "SELECT outstanding_balance::text FROM "
                    "public.wholesaler_retailer_bindings "
                    "WHERE is_deleted IS FALSE")).scalar() == "0.00"
        finally:
            engine.dispose()


# ---------------------------------------------------------------------------
# 18. SET-success .. token-return handshake gap still resets the identity
# ---------------------------------------------------------------------------

class _HandshakeInterruptingBind:
    """Delegates to the real connection but fails the FIRST current_user
    probe after the SET ROLE, simulating a failure between SET ROLE success
    and the window token returning."""

    def __init__(self, conn):
        self._conn = conn
        self._seen_set_role = False
        self._fired = False

    def __getattr__(self, name):
        # faithful delegation (its own docstring promises it): the window now
        # opens a handshake savepoint, exactly as 037/038 already did, so
        # nested-transaction helpers must reach the real connection.  No
        # assertion, selection or skip logic is touched here.
        if name == "_conn":
            raise AttributeError(name)
        return getattr(self._conn, name)

    def execute(self, *a, **kw):
        sql = str(a[0]) if a else ""
        if "SET ROLE" in sql:
            self._seen_set_role = True
        elif (self._seen_set_role and not self._fired
              and "current_user" in sql):
            # ONE-SHOT, exactly as this double's docstring states: the
            # boundary's own identity-verification probe must be allowed
            # through, otherwise the double would exercise a scenario it does
            # not claim (an unverifiable connection) rather than the intended
            # SET-success..token-return failure
            self._fired = True
            raise RuntimeError("injected handshake failure after SET ROLE")
        return self._conn.execute(*a, **kw)


def test_039_set_handshake_failure_still_resets(product_capability):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "g1r2e039hs") as db_url:
        schemas = _prepare_036_tenants(db_url, {"alpha": "positive"})
        module = _load_039()
        engine = _engine(db_url)  # migration identity
        try:
            with engine.connect() as conn:
                wrapper = _HandshakeInterruptingBind(conn)
                with pytest.raises(RuntimeError) as err:
                    module._open_tenant_ddl_authority(
                        wrapper, [schemas["alpha"]], "039 handshake-gap test")
                assert "injected handshake failure" in str(err.value)
                # the except boundary RESET ROLEd through the wrapper
                assert conn.execute(
                    text("SELECT current_user")).scalar() == MIGRATE_ROLE
                assert conn.execute(
                    text("SELECT session_user")).scalar() == MIGRATE_ROLE
        finally:
            engine.dispose()


# ---------------------------------------------------------------------------
# 19. 039 catalog probes are privilege-INDEPENDENT (pg_catalog, not the
#     privilege-filtered information_schema view) — exercised DIRECTLY on a
#     migration-identity connection outside any SET ROLE window
# ---------------------------------------------------------------------------

def test_039_catalog_probe_privilege_independent(product_capability):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "g1r2e039cat") as db_url:
        schemas = _prepare_036_tenants(db_url, {"alpha": "positive"})
        schema = schemas["alpha"]
        module = _load_039()
        engine = _engine(db_url)  # migration identity, NO window
        try:
            with engine.connect() as conn:
                # blindness baseline on the same connection: the
                # privilege-filtered view hides every app-owned tenant table
                assert conn.execute(text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema=:s"), {"s": schema}).scalar() == 0
                # the 039 probe must see the app-owned tenant table anyway
                assert module._table_exists(conn, schema, "orders") is True
                # genuinely absent objects stay absent (no false positives)
                assert module._table_exists(
                    conn, schema, "order_credit_holds") is False
                assert module._table_exists(
                    conn, "t_" + "0" * 32, "orders") is False
        finally:
            engine.dispose()


# ===========================================================================
# G1-R2E-P1R1R1 token-handshake fail-closed closure (appended 2026-09-28; the
# nineteen nodes above are byte-identical).
# Authorization: CTO-DIR-G1-R2E-P1R1R1-SET-ROLE-HANDSHAKE-20260928.
#
# Kilo F-001 (HIGH): 037/038 could leave current_user=mpango_app usable on the
# live migration connection when the token probe failed after a successful SET
# ROLE, because the enclosing window's ``finally`` is unreachable while
# ``_open_tenant_ddl_authority`` raises.  Each node below injects one failure
# class exactly in that gap — a Python exception before the probe reaches
# PostgreSQL, a REAL server-side SQL error (SQLSTATE 22012) that aborts the
# transaction, and a wrong identity returned by the server — and then inspects
# the SAME live connection *before* any outer rollback: the migration identity
# must already be back and the transaction must still be usable.
# ===========================================================================

REV_037 = "037_payment_declarations_schema"
MIGRATION_037 = BACKEND / "alembic" / "versions" / "037_payment_declarations_schema.py"

HANDSHAKE_MODES = ("python_exception", "sql_error", "wrong_identity")
_SQL_ERROR_STATEMENT = "SELECT current_user, 1 / 0"
_WRONG_IDENTITY_STATEMENT = "SELECT 'not_mpango_app'::text"


def _load_037():
    spec = importlib.util.spec_from_file_location(
        "g1r2e_p1r1r1_migration_037", MIGRATION_037)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pgcode(exc):
    return getattr(getattr(exc, "orig", None), "pgcode", None)


class _HandshakeProbeInjector:
    """Proxy over a migration module's ``sa`` helper.

    The first ``SELECT current_user`` clause built AFTER the ``SET ROLE``
    clause is replaced by the configured fault payload, which places every
    injection exactly between SET-ROLE success and the window token being
    returned.  ``saw_reset_role`` records whether the failing path still went
    on to issue an executable reset on that same connection; everything after
    the injection passes through untouched.
    """

    def __init__(self, real_sa, mode):
        assert mode in HANDSHAKE_MODES, mode
        self._sa = real_sa
        self._mode = mode
        self._set_role_seen = False
        self.fired = False
        self.saw_reset_role = False

    def __getattr__(self, name):
        return getattr(self._sa, name)

    def text(self, sql, *args, **kwargs):
        stripped = sql.strip()
        if stripped.startswith("SET ROLE"):
            self._set_role_seen = True
        elif stripped.startswith("RESET ROLE"):
            self.saw_reset_role = True
        elif (self._set_role_seen and not self.fired
              and stripped == "SELECT current_user"):
            self.fired = True
            if self._mode == "python_exception":
                raise RuntimeError(
                    "injected Python failure between SET ROLE success and the "
                    "token probe reaching PostgreSQL")
            if self._mode == "sql_error":
                return self._sa.text(_SQL_ERROR_STATEMENT)
            if self._mode == "wrong_identity":
                return self._sa.text(_WRONG_IDENTITY_STATEMENT)
        return self._sa.text(sql, *args, **kwargs)


def _probe_after_failure(conn):
    """Inspect the SAME live connection right after the injected failure and
    before any outer rollback: identity, transaction usability, SQLSTATE."""
    out = {}
    try:
        row = conn.execute(text("SELECT current_user, session_user")).fetchone()
        out["current_user"], out["session_user"] = row[0], row[1]
        out["identity_already_migration"] = (row[0] == MIGRATE_ROLE
                                            and row[1] == MIGRATE_ROLE)
    except Exception as exc:
        out["identity_already_migration"] = False
        out["identity_probe_pgcode"] = _pgcode(exc)
    try:
        out["tx_still_usable"] = conn.execute(text("SELECT 1")).scalar() == 1
    except Exception as exc:
        out["tx_still_usable"] = False
        out["tx_probe_pgcode"] = _pgcode(exc)
    return out


def _inject_handshake(db_url, which, mode):
    """Drive one migration's ``upgrade()`` with the handshake fault injected
    and collect the fail-closed evidence."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _load_037() if which == "037" else _load_038()
    engine = _engine(db_url)          # migration identity
    record = {"which": which, "mode": mode}
    real_sa = module.sa
    try:
        with engine.connect() as conn:
            injector = _HandshakeProbeInjector(real_sa, mode)
            module.sa = injector
            module.op = Operations(MigrationContext.configure(conn))
            try:
                with pytest.raises(BaseException) as err:
                    with conn.begin():
                        module.upgrade()
                record["raised_type"] = type(err.value).__name__
                record["raised_message"] = str(err.value)[:400]
                record["raised_pgcode"] = _pgcode(err.value)
                record["injection_fired"] = injector.fired
                record["reset_issued"] = injector.saw_reset_role
                # BEFORE any outer rollback: same-connection state
                record.update(_probe_after_failure(conn))
                if mode == "sql_error":
                    naive = {}
                    try:
                        conn.execute(text(f'SET ROLE "{APP_ROLE}"'))
                        try:
                            conn.execute(text("SELECT 1 / 0"))
                        except Exception as exc:
                            naive["error_pgcode"] = _pgcode(exc)
                        try:
                            conn.execute(text("RESET ROLE"))
                            naive["naive_reset_executed"] = True
                        except Exception as exc:
                            naive["naive_reset_executed"] = False
                            naive["naive_reset_pgcode"] = _pgcode(exc)
                        conn.rollback()
                        naive["identity_after_rollback"] = conn.execute(
                            text("SELECT current_user")).scalar()
                    except Exception as exc:
                        # only reachable when the boundary did NOT leave a
                        # usable transaction (the unfixed candidate)
                        naive["demo_unavailable_pgcode"] = _pgcode(exc)
                        conn.rollback()
                    record["naive_reset_counter_demo"] = naive
                conn.rollback()
                record["current_user_after_rollback"] = conn.execute(
                    text("SELECT current_user")).scalar()
                record["version"] = conn.execute(text(
                    "SELECT version_num FROM public.alembic_version")).scalar()
            finally:
                module.sa = real_sa
                module.op = None
    finally:
        engine.dispose()
    return record


def _assert_handshake_closure(record, db_url, tenant_schema, artifact):
    """Every §4.2 requirement for one injected handshake failure."""
    assert record["injection_fired"] is True, record
    # the failing path itself must have issued the reset ...
    assert record["reset_issued"] is True, record
    # ... and it must already be effective on the SAME connection, before any
    # outer rollback could mask the leak (this is F-001's discriminator)
    assert record["identity_already_migration"] is True, record
    assert record["tx_still_usable"] is True, record
    assert record["current_user_after_rollback"] == MIGRATE_ROLE, record
    # no head advance, no persistent artifact, no business-row drift
    assert record["version"] == REV_036, record
    engine = _admin_engine(db_url)
    try:
        assert _fetchone(engine, (
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
            "ON n.oid=c.relnamespace WHERE n.nspname=:s AND c.relname=:t"),
            {"s": tenant_schema, "t": artifact})[0] == 0, record
        assert _fetchone(engine, (
            f'SELECT status::text, total_amount::text FROM '
            f'"{tenant_schema}".orders')) == ("confirmed", "15000.00")
        assert _fetchone(engine, (
            f'SELECT amount::text FROM "{tenant_schema}".payments'))[0] == \
            "5000.00"
    finally:
        engine.dispose()
    if record["mode"] == "python_exception":
        assert record["raised_type"] == "RuntimeError", record
        assert "injected Python failure" in record["raised_message"], record
    if record["mode"] == "sql_error":
        assert record["raised_pgcode"] == "22012", record
        naive = record["naive_reset_counter_demo"]
        assert naive.get("error_pgcode") == "22012", naive
        assert naive.get("naive_reset_executed") is False, naive
        assert naive.get("naive_reset_pgcode") == "25P02", naive
        assert naive.get("identity_after_rollback") == MIGRATE_ROLE, naive
    if record["mode"] == "wrong_identity":
        # the named refusal survives the boundary and stays visible
        assert record["raised_type"] == "TenantDDLAuthorityError", record
        assert "expected" in record["raised_message"], record
        assert "not_mpango_app" in record["raised_message"], record


def _handshake_case(which, mode, prefix):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, prefix) as db_url:
        tenant_schema = _prepare_036_with_tenant(db_url, sentinel=True)
        record = _inject_handshake(db_url, which, mode)
        record["tenant_schema"] = tenant_schema
        artifact = ("payment_declarations" if which == "037"
                    else "catalog_products")
        _assert_handshake_closure(record, db_url, tenant_schema, artifact)


# ---------------------------------------------------------------------------
# 20-22. 037 token-handshake gap: Python exception / real SQL error / wrong
#        identity injected between SET-ROLE success and token return
# ---------------------------------------------------------------------------

def test_037_handshake_python_exception_restores_identity(product_capability):
    _handshake_case("037", "python_exception", "g1r2e037hs_py")


def test_037_handshake_server_sql_error_restores_identity(product_capability):
    _handshake_case("037", "sql_error", "g1r2e037hs_sq")


def test_037_handshake_wrong_identity_named_refusal_restores_identity(
        product_capability):
    _handshake_case("037", "wrong_identity", "g1r2e037hs_id")


# ---------------------------------------------------------------------------
# 23-25. the same three failure classes for 038
# ---------------------------------------------------------------------------

def test_038_handshake_python_exception_restores_identity(product_capability):
    _handshake_case("038", "python_exception", "g1r2e038hs_py")


def test_038_handshake_server_sql_error_restores_identity(product_capability):
    _handshake_case("038", "sql_error", "g1r2e038hs_sq")


def test_038_handshake_wrong_identity_named_refusal_restores_identity(
        product_capability):
    _handshake_case("038", "wrong_identity", "g1r2e038hs_id")


# ===========================================================================
# G1-R2E-P1R1R2: 039 handshake parity + cleanup-failure visibility
# (appended 2026-09-28; every node above is byte-identical except the single
#  authorised connection-lifetime fix inside
# test_capability_present_full_pass_app_owned, disclosed in the report).
# Authorization: CTO-DIR-G1-R2E-P1R1R2-039-HANDSHAKE-20260928.
#
# The R1 helpers above are deliberately left untouched (this round may only
# append nodes plus release the leftover engine), so this block carries its own
# driver that also covers 039.
# ===========================================================================

_R2_ARTIFACTS = {"037": "payment_declarations",
                 "038": "catalog_products",
                 "039": "order_credit_holds"}
_R2_MIGRATIONS = {
    "037": BACKEND / "alembic" / "versions" / "037_payment_declarations_schema.py",
    "038": BACKEND / "alembic" / "versions" / "038_catalog_identity_vertical_slice.py",
    "039": BACKEND / "alembic" / "versions" / "039_order_credit_holds.py",
}


def _r2_load(which):
    spec = importlib.util.spec_from_file_location(
        f"g1r2e_p1r1r2_migration_{which}", _R2_MIGRATIONS[which])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _r2_pgcode(exc):
    return getattr(getattr(exc, "orig", None), "pgcode", None)


def _r2_walk_exception_chain(exc):
    """Every exception visible from ``exc`` through __cause__/__context__."""
    seen, chain, cur = set(), [], exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        chain.append(f"{type(cur).__name__}: {cur}")
        cur = cur.__cause__ if cur.__cause__ is not None else cur.__context__
    return chain


def _r2_probe_after_failure(conn):
    """Same-connection state right after the injected failure, BEFORE any
    outer rollback (the F-001 discriminator)."""
    out = {}
    try:
        row = conn.execute(text("SELECT current_user, session_user")).fetchone()
        out["current_user"], out["session_user"] = row[0], row[1]
        out["identity_already_migration"] = (row[0] == MIGRATE_ROLE
                                             and row[1] == MIGRATE_ROLE)
    except Exception as exc:
        out["identity_already_migration"] = False
        out["identity_probe_pgcode"] = _r2_pgcode(exc)
    try:
        out["tx_still_usable"] = conn.execute(text("SELECT 1")).scalar() == 1
    except Exception as exc:
        out["tx_still_usable"] = False
        out["tx_probe_pgcode"] = _r2_pgcode(exc)
    return out


def _r2_inject_handshake(db_url, which, mode):
    """Handshake-fault driver for 037/038/039 (R1 driver covers only 037/038)."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _r2_load(which)
    engine = _engine(db_url)
    record = {"which": which, "mode": mode}
    real_sa = module.sa
    try:
        with engine.connect() as conn:
            injector = _HandshakeProbeInjector(real_sa, mode)
            module.sa = injector
            module.op = Operations(MigrationContext.configure(conn))
            try:
                with pytest.raises(BaseException) as err:
                    with conn.begin():
                        module.upgrade()
                record["raised_type"] = type(err.value).__name__
                record["raised_message"] = str(err.value)[:400]
                record["raised_pgcode"] = _r2_pgcode(err.value)
                record["injection_fired"] = injector.fired
                record["reset_issued"] = injector.saw_reset_role
                record.update(_r2_probe_after_failure(conn))
                if mode == "sql_error":
                    naive = {}
                    try:
                        conn.execute(text(f'SET ROLE "{APP_ROLE}"'))
                        try:
                            conn.execute(text("SELECT 1 / 0"))
                        except Exception as exc:
                            naive["error_pgcode"] = _r2_pgcode(exc)
                        try:
                            conn.execute(text("RESET ROLE"))
                            naive["naive_reset_executed"] = True
                        except Exception as exc:
                            naive["naive_reset_executed"] = False
                            naive["naive_reset_pgcode"] = _r2_pgcode(exc)
                        conn.rollback()
                        naive["identity_after_rollback"] = conn.execute(
                            text("SELECT current_user")).scalar()
                    except Exception as exc:
                        naive["demo_unavailable_pgcode"] = _r2_pgcode(exc)
                        conn.rollback()
                    record["naive_reset_counter_demo"] = naive
                conn.rollback()
                record["current_user_after_rollback"] = conn.execute(
                    text("SELECT current_user")).scalar()
                record["version"] = conn.execute(text(
                    "SELECT version_num FROM public.alembic_version")).scalar()
            finally:
                module.sa = real_sa
                module.op = None
    finally:
        engine.dispose()
    return record


def _r2_assert_handshake_closure(record, db_url, tenant_schema, artifact):
    """Same requirements as the R1 nodes, restated for the 039 driver."""
    assert record["injection_fired"] is True, record
    assert record["reset_issued"] is True, record
    assert record["identity_already_migration"] is True, record
    assert record["tx_still_usable"] is True, record
    assert record["current_user_after_rollback"] == MIGRATE_ROLE, record
    assert record["version"] == REV_036, record
    engine = _admin_engine(db_url)
    try:
        assert _fetchone(engine, (
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
            "ON n.oid=c.relnamespace WHERE n.nspname=:s AND c.relname=:t"),
            {"s": tenant_schema, "t": artifact})[0] == 0, record
        assert _fetchone(engine, (
            f'SELECT status::text, total_amount::text FROM '
            f'"{tenant_schema}".orders')) == ("confirmed", "15000.00")
        assert _fetchone(engine, (
            f'SELECT amount::text FROM "{tenant_schema}".payments'))[0] == \
            "5000.00"
    finally:
        engine.dispose()
    if record["mode"] == "python_exception":
        assert record["raised_type"] == "RuntimeError", record
        assert "injected Python failure" in record["raised_message"], record
    if record["mode"] == "sql_error":
        assert record["raised_pgcode"] == "22012", record
        naive = record["naive_reset_counter_demo"]
        assert naive.get("error_pgcode") == "22012", naive
        assert naive.get("naive_reset_executed") is False, naive
        assert naive.get("naive_reset_pgcode") == "25P02", naive
        assert naive.get("identity_after_rollback") == MIGRATE_ROLE, naive
    if record["mode"] == "wrong_identity":
        assert record["raised_type"] == "TenantDDLAuthorityError", record
        assert "expected" in record["raised_message"], record
        assert "not_mpango_app" in record["raised_message"], record


def _r2_handshake_case(which, mode, prefix):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, prefix) as db_url:
        tenant_schema = _prepare_036_with_tenant(db_url, sentinel=True)
        record = _r2_inject_handshake(db_url, which, mode)
        record["tenant_schema"] = tenant_schema
        _r2_assert_handshake_closure(record, db_url, tenant_schema,
                                     _R2_ARTIFACTS[which])


# ---------------------------------------------------------------------------
# 26-28. 039 token-handshake gap: the three failure classes
# ---------------------------------------------------------------------------

def test_039_handshake_python_exception_restores_identity(product_capability):
    _r2_handshake_case("039", "python_exception", "g1r2e039hs2_py")


def test_039_handshake_server_sql_error_restores_identity(product_capability):
    _r2_handshake_case("039", "sql_error", "g1r2e039hs2_sq")


def test_039_handshake_wrong_identity_named_refusal_restores_identity(
        product_capability):
    _r2_handshake_case("039", "wrong_identity", "g1r2e039hs2_id")


# ---------------------------------------------------------------------------
# 29-31. cleanup-failure counterexamples: a failing cleanup step must keep BOTH
#        the cleanup error and the original handshake error visible, and must
#        never report a discard that did not happen.
# ---------------------------------------------------------------------------

class _R2FailingSavepoint:
    """Savepoint whose rollback always fails (injected)."""

    def __init__(self, real):
        self._real = real
        self.rollback_attempts = 0

    def rollback(self):
        self.rollback_attempts += 1
        raise RuntimeError("injected savepoint rollback failure")

    def commit(self):
        return self._real.commit()


class _R2CleanupFaultBind:
    """Delegating bind that injects cleanup-step faults.

    faults is a set drawn from: 'savepoint' (begin_nested() savepoint whose
    rollback raises), 'rollback' (bind.rollback() raises), 'reset' (the RESET
    ROLE statement raises), 'identity' (the identity probe returns a wrong
    identity), 'invalidate' (bind.invalidate() raises).
    """

    def __init__(self, conn, faults):
        self._conn = conn
        self._faults = set(faults)
        self.executed = []
        self.invalidate_attempts = 0
        self.rollback_attempts = 0

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def execute(self, statement, *args, **kwargs):
        sql = " ".join(str(statement).split())
        self.executed.append(sql[:60])
        if "reset" in self._faults and sql.startswith("RESET ROLE"):
            raise RuntimeError("injected RESET ROLE failure")
        if "identity" in self._faults and sql == "SELECT current_user":
            return self._conn.execute(text("SELECT 'not_mpango_app'::text"))
        return self._conn.execute(statement, *args, **kwargs)

    def rollback(self):
        self.rollback_attempts += 1
        if "rollback" in self._faults:
            raise RuntimeError("injected enclosing rollback failure")
        return self._conn.rollback()

    def begin_nested(self):
        real = self._conn.begin_nested()
        if "savepoint" in self._faults:
            return _R2FailingSavepoint(real)
        return real

    def invalidate(self):
        self.invalidate_attempts += 1
        if "invalidate" in self._faults:
            raise RuntimeError("injected invalidate failure")
        return self._conn.invalidate()


def _r2_cleanup_fault_probe(db_url, which, faults):
    """Drive the handshake with a Python-exception injection plus the given
    cleanup faults; return the observable error chain and state."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _r2_load(which)
    engine = _engine(db_url)
    record = {"which": which, "faults": sorted(faults)}
    real_sa = module.sa
    try:
        with engine.connect() as conn:
            injector = _HandshakeProbeInjector(real_sa, "python_exception")
            bind = _R2CleanupFaultBind(conn, faults)
            module.sa = injector
            module.op = Operations(MigrationContext.configure(bind))
            try:
                try:
                    module.upgrade()
                    record["raised"] = None
                except BaseException as exc:  # noqa: BLE001
                    record["raised"] = type(exc).__name__
                    record["raised_message"] = str(exc)[:600]
                    record["chain"] = _r2_walk_exception_chain(exc)
                record["injection_fired"] = injector.fired
                record["invalidate_attempts"] = bind.invalidate_attempts
                record["rollback_attempts"] = bind.rollback_attempts
                try:
                    record["actual_identity"] = conn.execute(
                        text("SELECT current_user")).scalar()
                except Exception as exc:
                    record["actual_identity"] = f"unusable:{_r2_pgcode(exc)}"
                conn.rollback()
                record["version"] = conn.execute(text(
                    "SELECT version_num FROM public.alembic_version")).scalar()
            finally:
                module.sa = real_sa
                module.op = None
    finally:
        engine.dispose()
    return record


def _r2_assert_cleanup_visibility(record, expect_reason, expect_discard):
    chain = " | ".join(record.get("chain") or [])
    assert record["raised"] == "TenantDDLAuthorityError", record
    message = record["raised_message"]
    assert "injected Python failure" in chain, record        # original kept
    assert "injected" in message or "injected" in chain, record
    assert expect_reason in message, record
    if expect_discard:
        # a real discard happened -> the message may claim it, but must still
        # name the failure that forced it
        assert "was invalidated and must not be reused" in message, record
    else:
        # invalidate() itself failed -> never claim a successful discard
        assert "invalidation FAILED" in message, record
        assert "was invalidated and must not be reused" not in message, record
    assert record["version"] == REV_036, record


def _r2_cleanup_fault_case(which, prefix):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, prefix) as db_url:
        _prepare_036_with_tenant(db_url, sentinel=True)
        # (1) savepoint rollback AND the enclosing rollback both fail
        rec = _r2_cleanup_fault_probe(db_url, which,
                                      {"savepoint", "rollback"})
        assert "injected savepoint rollback failure" in " | ".join(rec["chain"]), rec
        assert "injected enclosing rollback failure" in " | ".join(rec["chain"]), rec
        _r2_assert_cleanup_visibility(
            rec, "could not be rolled back", expect_discard=True)
        # (2) RESET ROLE fails (primary attempt and the re-verify attempt)
        rec = _r2_cleanup_fault_probe(db_url, which, {"reset"})
        assert "injected RESET ROLE failure" in " | ".join(rec["chain"]), rec
        _r2_assert_cleanup_visibility(
            rec, "could not be verified", expect_discard=True)
        # (3) the identity cannot be restored AND invalidate() fails
        rec = _r2_cleanup_fault_probe(db_url, which,
                                      {"identity", "invalidate"})
        # the cleanup failure must stay visible WITHOUT echoing the
        # underlying exception text: the diagnostic names its safe TYPE
        # identifier instead of the message (G1-R2E-P1R1R3R1)
        assert "invalidation FAILED" in rec["raised_message"], rec
        assert "exception type RuntimeError" in rec["raised_message"], rec
        assert rec["invalidate_attempts"] >= 1, rec
        _r2_assert_cleanup_visibility(
            rec, "failed to restore current_user", expect_discard=False)


def test_037_cleanup_failures_keep_both_errors_visible(product_capability):
    _r2_cleanup_fault_case("037", "g1r2e037cl")


def test_038_cleanup_failures_keep_both_errors_visible(product_capability):
    _r2_cleanup_fault_case("038", "g1r2e038cl")


def test_039_cleanup_failures_keep_both_errors_visible(product_capability):
    _r2_cleanup_fault_case("039", "g1r2e039cl")


# ===========================================================================
# G1-R2E-P1R1R3 diagnostic-leak canaries (appended 2026-09-28; every node above
# is byte-identical).  Authorization:
# CTO-DIR-G1-R2E-P1R1R3-NEUTRAL-DIAGNOSTIC-20260928.
#
# The connection-discard diagnostic used to interpolate the underlying
# exception message, which is outside the boundary's control and could carry a
# credential or DSN fragment into Alembic stderr / JUnit.  Each canary below
# injects an invalidate() failure whose message carries a SYNTHETIC,
# credential-shaped sentinel and requires that the sentinel appears NOWHERE the
# candidate can make public, while the neutral truthful diagnostic and the
# original handshake failure stay visible.
#
# The sentinel is assembled at runtime from separate literals so the committed
# test file contains no credential-shaped value; it only ever surfaces in the
# rejected (private) RED artifact of the unfixed BASE.
# ===========================================================================

_CANARY_TOKEN = "SYNTHETIC" + "-CANARY" + "-NOT-A-REAL-CREDENTIAL"
_CANARY_DSN = "postgresql://canary:" + _CANARY_TOKEN + "@h/c"   # 61 chars < 80


class _R3CanaryInvalidateBind(_R2CleanupFaultBind):
    """R2 fault bind whose invalidate() failure carries the synthetic sentinel
    in its message (it is a stand-in for any driver error text)."""

    def invalidate(self):
        self.invalidate_attempts += 1
        raise RuntimeError(_CANARY_DSN)


def _r3_canary_probe(db_url, which):
    """Handshake with: a Python-exception injection, an identity that cannot be
    restored, and an invalidate() failure carrying the canary."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _r2_load(which)
    engine = _engine(db_url)
    record = {"which": which}
    real_sa = module.sa
    try:
        with engine.connect() as conn:
            injector = _HandshakeProbeInjector(real_sa, "python_exception")
            bind = _R3CanaryInvalidateBind(conn, {"identity"})
            module.sa = injector
            module.op = Operations(MigrationContext.configure(bind))
            try:
                try:
                    module.upgrade()
                    record["raised"] = None
                except BaseException as exc:      # noqa: BLE001
                    record["raised"] = type(exc).__name__
                    record["raised_message"] = str(exc)
                    record["chain"] = _r2_walk_exception_chain(exc)
                record["invalidate_attempts"] = bind.invalidate_attempts
                conn.rollback()
                record["version"] = conn.execute(text(
                    "SELECT version_num FROM public.alembic_version")).scalar()
            finally:
                module.sa = real_sa
                module.op = None
    finally:
        engine.dispose()
    return record


def _r3_assert_no_echo(record, db_url, tenant_schema, artifact):
    assert record["raised"] == "TenantDDLAuthorityError", record
    message = record["raised_message"]
    chain = " | ".join(record.get("chain") or [])
    assert record["invalidate_attempts"] >= 1, record
    # the sentinel must not reach anything the candidate can make public,
    # including anything propagated through the exception chain
    assert _CANARY_TOKEN not in message, record
    assert _CANARY_TOKEN not in chain, record
    # the neutral diagnostic is still named and still truthful
    assert "invalidation FAILED" in message, record
    assert "exception type RuntimeError" in message, record
    assert "was invalidated and must not be reused" not in message, record
    # the ORIGINAL handshake failure stays traceable through the chain
    assert "injected Python failure" in chain, record
    # no head advance and no artifact left behind
    assert record["version"] == REV_036, record
    engine = _admin_engine(db_url)
    try:
        assert _fetchone(engine, (
            "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
            "ON n.oid=c.relnamespace WHERE n.nspname=:s AND c.relname=:t"),
            {"s": tenant_schema, "t": artifact})[0] == 0, record
    finally:
        engine.dispose()


def _r3_canary_case(which, prefix):
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, prefix) as db_url:
        tenant_schema = _prepare_036_with_tenant(db_url, sentinel=True)
        record = _r3_canary_probe(db_url, which)
        record["tenant_schema"] = tenant_schema
        _r3_assert_no_echo(record, db_url, tenant_schema,
                           _R2_ARTIFACTS[which])


# ---------------------------------------------------------------------------
# 32-34. one canary per migration
# ---------------------------------------------------------------------------

def test_037_discard_diagnostic_does_not_echo_underlying_message(
        product_capability):
    _r3_canary_case("037", "g1r2e037leak")


def test_038_discard_diagnostic_does_not_echo_underlying_message(
        product_capability):
    _r3_canary_case("038", "g1r2e038leak")


def test_039_discard_diagnostic_does_not_echo_underlying_message(
        product_capability):
    _r3_canary_case("039", "g1r2e039leak")
