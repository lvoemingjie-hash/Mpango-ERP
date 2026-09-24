"""C3 migration matrix / C5 deployment order — real alembic 039 on a real
PG16 cluster, disposable per-test databases (async_test_utils), migration
module executed through alembic's Operations context (the dc11t4h pattern).

Covers the CTO C3 state matrix (credit/non-credit, paid/fulfilled/returned,
soft-deleted payments, unexplainable history), P14 exposure-only cache
proof, zero-partial-write on late-tenant failure, pre-existing table
refusal, forward-only downgrade, bootstrap-first rejection, and the
catalog-parity proof between the migration path and the bootstrap path.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from tests.async_test_utils import temporary_database_url

BACKEND = Path(__file__).resolve().parents[2]
MIGRATION_039 = BACKEND / "alembic" / "versions" / "039_order_credit_holds.py"
BOOTSTRAP_SCRIPT = BACKEND / "scripts" / "bootstrap_tenant_schema.py"

pytestmark = pytest.mark.skipif(
    os.environ.get("MPANGO_ALLOW_TEMP_DB_CREATE") != "1",
    reason="set MPANGO_ALLOW_TEMP_DB_CREATE=1 for migration database tests",
)


def _engine(database_url: str):
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return create_engine(sync_url, future=True)


def _load_migration(module_name: str = "r2_migration_039"):
    if not MIGRATION_039.exists():
        pytest.fail(
            "C3-GAP: alembic/versions/039_order_credit_holds.py does not "
            "exist in the parent commit — the product cannot synthesize "
            "per-order credit-hold lifecycles")
    spec = importlib.util.spec_from_file_location(module_name, MIGRATION_039)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration_039(connection) -> None:
    module = _load_migration()
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    context = MigrationContext.configure(connection)
    operations = Operations(context)
    original_op = module.op
    module.op = operations
    try:
        module.upgrade()
    finally:
        module.op = original_op


def _upgrade_to_head(db_url: str) -> None:
    """Real `alembic upgrade head` against a disposable database (env.py
    redirects at $DATABASE_URL; isolated thread keeps the session loop)."""
    from unittest import mock

    def job():
        from alembic import command
        from alembic.config import Config

        with mock.patch.dict(os.environ, {"DATABASE_URL": db_url}):
            cfg = Config(str(BACKEND / "alembic.ini"))
            cfg.set_main_option("script_location", str(BACKEND / "alembic"))
            command.upgrade(cfg, "head")

    _run_in_fresh_loop(job)


def _run_in_fresh_loop(fn, *args):
    """Run a callable that owns its own event loop (alembic env.py uses
    asyncio.run) in an isolated thread so the pytest-asyncio session loop is
    never touched."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(fn, *args).result()


def _upgrade_to_038(db_url: str) -> None:
    """Bring a disposable database to the frozen baseline (public schema).

    alembic/env.py overrides sqlalchemy.url from $DATABASE_URL, so the env
    var is redirected at the disposable database for the upgrade, and the
    whole upgrade runs in an isolated thread/loop."""
    from unittest import mock

    def job():
        from alembic import command
        from alembic.config import Config

        with mock.patch.dict(os.environ, {"DATABASE_URL": db_url}):
            cfg = Config(str(BACKEND / "alembic.ini"))
            cfg.set_main_option("script_location", str(BACKEND / "alembic"))
            command.upgrade(cfg, "038_catalog_identity_vertical_slice")

    _run_in_fresh_loop(job)


def _register_tenant(engine, wholesaler_id: uuid.UUID) -> str:
    schema = f"t_{wholesaler_id.hex}"
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
            "VALUES (:id, :code, 'R2C3 Wholesaler', 'active', FALSE)"),
            {"id": wholesaler_id,
             "code": f"R2C3{wholesaler_id.hex[:8].upper()}"})
        conn.execute(text(
            "INSERT INTO public.tenant_registrations ("
            "id, company_name, country, owner_email, status, email_verified_at, "
            "provisioning_started_at, password_hash_cleared_at, wholesaler_id, "
            "tenant_schema, expires_at, is_deleted"
            ") VALUES ("
            ":id, 'R2C3 Company', 'KE', :owner_email, 'active', now(), "
            "now(), now(), :wholesaler_id, :tenant_schema, "
            "now() + interval '1 hour', FALSE)"),
            {"id": uuid.uuid4(),
             "owner_email": f"r2c3_{uuid.uuid4().hex}@example.com",
             "wholesaler_id": wholesaler_id,
             "tenant_schema": schema})
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        conn.execute(text(f"""
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
                created_by UUID, updated_by UUID
            );
            CREATE TABLE "{schema}".payments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL,
                retailer_id UUID NOT NULL,
                transaction_id VARCHAR(128),
                amount NUMERIC(12,2) NOT NULL,
                method VARCHAR(50) NOT NULL DEFAULT 'cash',
                status VARCHAR(50) NOT NULL DEFAULT 'completed',
                idempotency_key VARCHAR(64),
                receipt_number VARCHAR(32),
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                is_deleted BOOLEAN DEFAULT FALSE,
                deleted_at TIMESTAMPTZ,
                created_by UUID, updated_by UUID
            );
        """))
    return schema


def _add_order(engine, schema: str, wholesaler_id: uuid.UUID, retailer_id: uuid.UUID,
               status: str, total: str) -> uuid.UUID:
    oid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text(
            f'INSERT INTO "{schema}".orders (id, wholesaler_id, retailer_id, '
            "status, total_amount, is_deleted) "
            "VALUES (:id, :w, :r, CAST(:st AS \"{}\".order_status), :t, FALSE)".format(schema)),
            {"id": oid, "w": wholesaler_id, "r": retailer_id, "st": status,
             "t": total})
    return oid


def _add_payment(engine, schema: str, order_id: uuid.UUID,
                 retailer_id: uuid.UUID, method: str, amount: str,
                 *, deleted: bool = False) -> uuid.UUID:
    pid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text(
            f'INSERT INTO "{schema}".payments (id, order_id, retailer_id, '
            "amount, method, status, is_deleted) "
            "VALUES (:id, :o, :r, :a, :m, 'completed', :d)"),
            {"id": pid, "o": order_id, "r": retailer_id, "a": amount,
             "m": method, "d": deleted})
    return pid


def _add_binding(engine, wholesaler_id: uuid.UUID, retailer_id: uuid.UUID,
                 balance: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO public.retailers (id, phone, name, is_deleted) "
            "VALUES (:id, :phone, 'R2C3 Retailer', FALSE)"),
            {"id": retailer_id, "phone": f"r2c3-{retailer_id.hex[:20]}"})
        conn.execute(text(
            "INSERT INTO public.wholesaler_retailer_bindings "
            "(wholesaler_id, retailer_id, status, outstanding_balance, is_deleted) "
            "VALUES (:w, :r, 'active', :b, FALSE)"),
            {"w": wholesaler_id, "r": retailer_id, "b": balance})


def _holds(engine, schema: str) -> list[tuple]:
    with engine.connect() as conn:
        rows = conn.execute(text(
            f'SELECT o.status::text, h.amount, h.remaining_amount, h.status '
            f'FROM "{schema}".order_credit_holds h '
            f'JOIN "{schema}".orders o ON o.id = h.order_id '
            "ORDER BY o.created_at, h.order_id")).fetchall()
    return [(r[0], str(r[1]), str(r[2]), r[3]) for r in rows]


def _binding(engine, wholesaler_id: uuid.UUID, retailer_id: uuid.UUID) -> Decimal:
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT outstanding_balance FROM public.wholesaler_retailer_bindings "
            "WHERE wholesaler_id = :w AND retailer_id = :r"),
            {"w": wholesaler_id, "r": retailer_id}).fetchone()
    return Decimal(str(row[0])) if row else Decimal("0")


def test_c3_empty_database_upgrade_then_downgrade_refused():
    """Empty registry: a REAL `alembic upgrade head` advances cleanly (no
    tenants); downgrade refuses."""
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "r2c3empty") as db_url:
        engine = _engine(db_url)
        _upgrade_to_038(db_url)
        _upgrade_to_head(db_url)
        version = engine.connect().execute(
            text("SELECT version_num FROM public.alembic_version")).scalar()
        assert version == "039_order_credit_holds"
        module = _load_migration("r2_migration_039_down")
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        with engine.connect() as conn:
            module.op = Operations(MigrationContext.configure(conn))
            try:
                module.downgrade()
            except RuntimeError as exc:
                assert "forward-only" in str(exc), exc
            else:
                raise AssertionError("downgrade must refuse (forward-only)")


def test_c3_full_state_matrix_backfill_exact():
    """C3 matrix: every legal history shape synthesizes the exact lifecycle
    row and the binding cache equals holds + per-order net exposure."""
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "r2c3full") as db_url:
        engine = _engine(db_url)
        _upgrade_to_038(db_url)
        ws = uuid.uuid4()
        retailer = uuid.uuid4()
        schema = _register_tenant(engine, ws)

        o_conf = _add_order(engine, schema, ws, retailer, "confirmed", "50.00")
        o_part = _add_order(engine, schema, ws, retailer, "partially_paid", "100.00")
        _add_payment(engine, schema, o_part, retailer, "cash", "40.00")
        o_crc = _add_order(engine, schema, ws, retailer, "paid", "100.00")
        _add_payment(engine, schema, o_crc, retailer, "credit", "100.00")
        _add_payment(engine, schema, o_crc, retailer, "cash", "25.00")
        o_frc = _add_order(engine, schema, ws, retailer, "fulfilled", "80.00")
        _add_payment(engine, schema, o_frc, retailer, "credit", "80.00")
        o_fnc = _add_order(engine, schema, ws, retailer, "fulfilled", "60.00")
        _add_payment(engine, schema, o_fnc, retailer, "transfer", "60.00")
        o_retc = _add_order(engine, schema, ws, retailer, "returned", "70.00")
        _add_payment(engine, schema, o_retc, retailer, "credit", "70.00")
        o_retn = _add_order(engine, schema, ws, retailer, "returned", "30.00")
        _add_payment(engine, schema, o_retn, retailer, "cash", "30.00")
        o_paid_c = _add_order(engine, schema, ws, retailer, "paid", "90.00")
        _add_payment(engine, schema, o_paid_c, retailer, "cash", "90.00")
        _add_order(engine, schema, ws, retailer, "draft", "10.00")
        _add_order(engine, schema, ws, retailer, "cancelled", "20.00")
        _add_order(engine, schema, ws, retailer, "voided", "5.00")

        # P14: cache must equal the 038 exposure-only formula EXACTLY.
        # exposure = (100-25)+(80)+(70) = 225 for this retailer.
        _add_binding(engine, ws, retailer, "225.00")

        with engine.begin() as conn:
            _run_migration_039(conn)

        holds = _holds(engine, schema)
        by_status = {}
        for (ostatus, amount, remaining, hstatus) in holds:
            by_status.setdefault((ostatus, hstatus), []).append(
                (amount, remaining))
        assert by_status[("confirmed", "active")] == [("50.00", "50.00")]
        assert by_status[("partially_paid", "active")] == [("100.00", "60.00")]
        assert ("paid", "converted") in by_status
        for key in (("paid", "converted"), ("fulfilled", "converted"),
                    ("returned", "converted")):
            for (amount, remaining) in by_status.get(key, []):
                assert remaining == "0.00", (key, amount, remaining)
        for key in (("fulfilled", "settled"), ("returned", "settled"),
                    ("paid", "settled")):
            for (amount, remaining) in by_status.get(key, []):
                assert remaining == "0.00", (key, amount, remaining)
        synthesized_statuses = {hstatus for (_, hstatus) in by_status}
        assert "released" not in synthesized_statuses, (
            "migration must not fabricate historical release events")
        total_rows = sum(len(v) for v in by_status.values())
        assert total_rows == 8, (total_rows, by_status)  # no draft/cancel/void

        expected = Decimal("225.00") + Decimal("50.00") + Decimal("60.00")
        assert _binding(engine, ws, retailer) == expected


def test_c3_unexplainable_history_rejected_zero_partial_write():
    """The LAST tenant carries corrupt history; tenants 1..n-1 must stay at
    the 038 state with zero hold tables and no version advance."""
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "r2c3bad") as db_url:
        engine = _engine(db_url)
        _upgrade_to_038(db_url)
        ws1, ws_bad = uuid.uuid4(), uuid.uuid4()
        s1 = _register_tenant(engine, ws1)
        s2 = _register_tenant(engine, ws_bad)
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        o1 = _add_order(engine, s1, ws1, r1, "confirmed", "50.00")
        _add_binding(engine, ws1, r1, "0.00")
        o2 = _add_order(engine, s2, ws_bad, r2, "paid", "100.00")
        _add_payment(engine, s2, o2, r2, "cash", "120.00")  # overpaid
        _add_binding(engine, ws_bad, r2, "0.00")

        with pytest.raises(Exception, match=r"(?i)preflight|fail"):
            with engine.begin() as conn:
                _run_migration_039(conn)

        version = engine.connect().execute(
            text("SELECT version_num FROM public.alembic_version")).scalar()
        assert version == "038_catalog_identity_vertical_slice", (
            "a failed migration must not advance the version")
        exists = engine.connect().execute(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name = 'order_credit_holds'")).scalar()
        assert int(exists) == 0, "zero partial write violated"


def test_c3_preexisting_hold_table_rejected():
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "r2c3pre") as db_url:
        engine = _engine(db_url)
        _upgrade_to_038(db_url)
        ws = uuid.uuid4()
        schema = _register_tenant(engine, ws)
        with engine.begin() as conn:
            conn.execute(text(
                f'CREATE TABLE "{schema}".order_credit_holds '
                "(id UUID PRIMARY KEY)"))
        with pytest.raises(Exception, match=r"pre-existing R2 schema"):
            with engine.begin() as conn:
                _run_migration_039(conn)


def test_c3_p14_binding_cache_mismatch_rejected():
    """P14: a cache that does not equal the 038 exposure-only formula must
    fail the migration before any write."""
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "r2c3p14") as db_url:
        engine = _engine(db_url)
        _upgrade_to_038(db_url)
        ws = uuid.uuid4()
        schema = _register_tenant(engine, ws)
        retailer = uuid.uuid4()
        o = _add_order(engine, schema, ws, retailer, "paid", "100.00")
        _add_payment(engine, schema, o, retailer, "credit", "100.00")
        # correct exposure-only cache is 100.00; corrupt it to 70.00
        _add_binding(engine, ws, retailer, "70.00")

        with pytest.raises(Exception, match=r"P14 cache proof failed"):
            with engine.begin() as conn:
                _run_migration_039(conn)


def test_c3_soft_deleted_payment_history_boundary():
    """Soft-deleted payments are NOT history: a partially_paid order with
    effective cash 40 + soft-deleted cash 60 migrates with hold remaining
    60 (the deleted row contributes nothing). M3 anchor."""
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "r2c3soft") as db_url:
        engine = _engine(db_url)
        _upgrade_to_038(db_url)
        ws = uuid.uuid4()
        schema = _register_tenant(engine, ws)
        retailer = uuid.uuid4()
        o = _add_order(engine, schema, ws, retailer, "partially_paid", "100.00")
        _add_payment(engine, schema, o, retailer, "cash", "40.00")
        _add_payment(engine, schema, o, retailer, "cash", "60.00",
                     deleted=True)
        _add_binding(engine, ws, retailer, "0.00")
        try:
            with engine.begin() as conn:
                _run_migration_039(conn)
        except Exception as exc:  # noqa: BLE001 — converted to a named RED
            raise AssertionError(
                "M3: the migration refused a history whose ONLY anomaly is a "
                "soft-deleted payment row — effective history must exclude "
                f"is_deleted rows (got {type(exc).__name__}: {exc})") from exc
        rows = _holds(engine, schema)
        assert rows == [("partially_paid", "100.00", "60.00", "active")], (
            f"M3: soft-deleted payment leaked into the backfill (rows={rows}; "
            "effective history must exclude is_deleted rows — expected "
            "remaining 60.00 from cash 40.00 only)")


def test_c5_bootstrap_before_039_refuses_before_tenant_objects():
    """C5: bootstrap on a pre-039 database must refuse BEFORE creating any
    tenant object (no schema, no wholesalers rows)."""
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "r2c5gate") as db_url:
        engine = _engine(db_url)
        _upgrade_to_038(db_url)

        spec = importlib.util.spec_from_file_location(
            "r2_bootstrap_module", BOOTSTRAP_SCRIPT)
        assert spec and spec.loader
        bootstrap_module = importlib.util.module_from_spec(spec)
        # bootstrap_tenant_schema.py runs module-level env handling only on
        # main; importing it as a module must not execute bootstrap().
        spec.loader.exec_module(bootstrap_module)

        schemas_before = engine.connect().execute(text(
            "SELECT count(*) FROM information_schema.schemata "
            "WHERE schema_name LIKE 't_%'")).scalar()
        ws = uuid.uuid4()
        try:
            _run_in_fresh_loop(asyncio_run, bootstrap_module.bootstrap(
                f"t_{ws.hex}", db_url))
        except Exception as exc:
            assert not str(exc).isspace(), exc
            import re as _re
            assert _re.search(r"(?i)039|alembic|version", str(exc)), (
                f"C5-RED bootstrap-first rejected for the wrong reason: {exc}")
        else:
            pytest.fail(
                "C5-RED: bootstrap-first was NOT rejected on a pre-039 "
                "database (tenant objects were creatable before the 039 "
                "schema contract existed)")

        schemas_after = engine.connect().execute(text(
            "SELECT count(*) FROM information_schema.schemata "
            "WHERE schema_name LIKE 't_%'")).scalar()
        assert int(schemas_after) == int(schemas_before), (
            "bootstrap-first created tenant objects before refusing")


def test_c5_catalog_parity_migration_vs_bootstrap():
    """The 039 DDL and the bootstrap DDL must produce catalog-identical
    order_credit_holds tables (columns/constraints/indexes)."""
    source = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source, "r2c5para") as db_url:
        engine = _engine(db_url)
        _upgrade_to_038(db_url)
        ws_mig = uuid.uuid4()
        schema_mig = _register_tenant(engine, ws_mig)
        _upgrade_to_head(db_url)

        spec = importlib.util.spec_from_file_location(
            "r2_bootstrap_module_parity", BOOTSTRAP_SCRIPT)
        bootstrap_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bootstrap_module)
        ws_boot = uuid.uuid4()
        _run_in_fresh_loop(asyncio_run, bootstrap_module.bootstrap(
            f"t_{ws_boot.hex}", db_url))

        def _catalog(schema: str) -> tuple:
            with engine.connect() as conn:
                cols = conn.execute(text(
                    "SELECT column_name, data_type, is_nullable FROM "
                    "information_schema.columns WHERE table_schema = :s AND "
                    "table_name = 'order_credit_holds' ORDER BY column_name"),
                    {"s": schema}).fetchall()
                cons = conn.execute(text(
                    "SELECT conname, contype, pg_get_constraintdef(c.oid, true) "
                    "FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                    "JOIN pg_namespace n ON n.oid = c.connamespace "
                    "WHERE n.nspname = :s AND t.relname = 'order_credit_holds' "
                    "ORDER BY conname"), {"s": schema}).fetchall()
                idx = conn.execute(text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname = :s AND tablename = 'order_credit_holds' "
                    "ORDER BY indexname"), {"s": schema}).fetchall()
            norm = lambda rows: tuple(
                tuple(str(c).replace(schema, "SCHEMA") for c in row)
                for row in rows)
            return (norm(cols), norm(cons), norm(idx))

        mig_catalog = _catalog(schema_mig)
        boot_catalog = _catalog(f"t_{ws_boot.hex}")
        assert mig_catalog == boot_catalog, (
            f"catalog drift:\nMIGRATION:\n{mig_catalog}\nBOOTSTRAP:\n{boot_catalog}")


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)
