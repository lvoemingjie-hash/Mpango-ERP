"""045 migration controls: true 044 prestate and separately measured 045 poststate."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import secrets
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic/versions/045_owner_staff_recovery.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sync_engine(key):
    return sa.create_engine(os.environ[key].replace("postgresql+asyncpg://", "postgresql://"), poolclass=NullPool)


def _snapshot(connection):
    result = {"schemas": {}, "bindings": []}
    for schema in _schemas(connection):
        result["schemas"][schema] = {}
        for table in ("users", "roles", "user_roles", "permissions", "role_permissions",
                      "staff_authority", "staff_memberships", "staff_role_templates"):
            rows = connection.execute(sa.text(f'SELECT to_jsonb(x) FROM "{schema}".{table} x')).scalars().all()
            # credential_epoch is the only permitted new user datum.
            for row in rows:
                if table == "users":
                    row.pop("credential_epoch", None)
            result["schemas"][schema][table] = sorted(rows, key=lambda x: json.dumps(x, sort_keys=True))
    saved = Path(os.environ["FOUNDATION_PRE045_SNAPSHOT"])
    ids = [row["id"] for row in json.loads(saved.read_text())["bindings"]] if saved.exists() else None
    rows = connection.execute(sa.text("SELECT to_jsonb(b) FROM public.wholesaler_retailer_bindings b")).scalars().all()
    result["bindings"] = sorted([row for row in rows if ids is None or row["id"] in ids], key=lambda x: x["id"])
    return result


def _schemas(connection):
    saved = Path(os.environ["FOUNDATION_PRE045_SNAPSHOT"])
    if saved.exists():
        return sorted(json.loads(saved.read_text())["schemas"])
    return sorted({"t_dev", "t_test"} | set(connection.execute(sa.text(
        "SELECT tenant_schema FROM public.tenant_registrations WHERE tenant_schema IS NOT NULL AND is_deleted IS FALSE"
    )).scalars()))


def _column_count(connection):
    return connection.scalar(sa.text(
        "SELECT count(*) FROM information_schema.columns WHERE table_schema=ANY(:schemas) "
        "AND table_name='users' AND column_name='credential_epoch'"
    ), {"schemas": _schemas(connection)})


@pytest_asyncio.fixture
async def pre045():
    """Use the frozen C0 bootstrap, no fabricated Owner/active registration."""
    from core.security import hash_password
    engine = _sync_engine("DATABASE_URL")
    with engine.connect() as c:
        assert c.scalar(sa.text("SELECT version_num FROM public.alembic_version")) == "044_inventory_adjustment_approval"
    baseline = Path(os.environ["FOUNDATION_BASELINE_BOOTSTRAP"])
    assert baseline.is_absolute() and "supply-checkout" in str(baseline)
    await _load(baseline, "foundation_baseline_bootstrap").bootstrap("t_dev", os.environ["DATABASE_URL"])
    snapshot_path = Path(os.environ["FOUNDATION_PRE045_SNAPSHOT"])
    if not snapshot_path.exists():
        # Create the registered historical tenant through the real provisioner
        # and Owner setup; only its bootstrap implementation is the frozen C0.
        from db.tenant_filter import mark_session_as_system
        from services.tenant_provisioning_service import TenantProvisioningService
        from services.owner_credential_service import OwnerCredentialSetupService
        async_engine = create_async_engine(os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://"), poolclass=NullPool)
        factory = async_sessionmaker(async_engine, expire_on_commit=False)
        registration, retailer = uuid4(), uuid4()
        code = "FND" + uuid4().hex[:14].upper()
        try:
            async with factory() as db:
                mark_session_as_system(db, reason="foundation historical migration fixture")
                await db.execute(sa.text("INSERT INTO public.tenant_registrations "
                    "(id,company_name,tenant_code,country,owner_email,status,expires_at,email_verified_at) "
                    "VALUES (:r,'Migration prestate',:c,'KE',:e,'email_verified',now()+interval '1 day',now())"),
                    {"r": registration, "c": code, "e": code.lower() + "@example.com"})
                await db.commit()
                service = TenantProvisioningService(db, bootstrap_func=_load(baseline, "foundation_old_tenant").bootstrap)
                assert (await service.claim_registration_for_provisioning(str(registration))).action == "claimed"
                await db.commit()
                assert (await service.provision_wholesaler_and_schema(str(registration))).action == "provisioned"
                await db.commit()
                owner = OwnerCredentialSetupService(db)
                issued = await owner.issue_setup_token(registration)
                setup = await owner.consume_setup_token(issued.raw_token, secrets.token_urlsafe(32))
                await owner.create_first_admin_rbac(setup)
                wid = await db.scalar(sa.text("SELECT wholesaler_id FROM public.tenant_registrations WHERE id=:r"), {"r": registration})
                await db.execute(sa.text("INSERT INTO public.retailers (id,phone,name) VALUES (:r,:p,'Preserved inactive binding')"),
                                 {"r": retailer, "p": "+254" + str(uuid4().int)[:9]})
                await db.execute(sa.text("INSERT INTO public.wholesaler_retailer_bindings "
                    "(wholesaler_id,retailer_id,status,outstanding_balance) VALUES (:w,:r,'inactive',0)"), {"w": wid, "r": retailer})
                await db.commit()
        finally:
            await async_engine.dispose()
        with engine.begin() as c:
            for schema, active in [("t_dev", False), ("t_test", True)]:
                c.execute(sa.text(f'INSERT INTO "{schema}".users '
                    '(id,email,password_hash,full_name,is_active) VALUES (:u,:e,:p,:n,:a)'),
                    {"u": uuid4(), "e": secrets.token_hex(8) + "@example.com",
                     "p": hash_password(secrets.token_urlsafe(32)), "n": "044 preserved user", "a": active})
        with engine.connect() as c:
            state = _snapshot(c)
        with snapshot_path.open("x") as f:
            os.chmod(snapshot_path, 0o600)
            json.dump(state, f, sort_keys=True)
    with engine.connect() as c:
        assert _snapshot(c) == json.loads(snapshot_path.read_text())
        assert _column_count(c) == 0
    try:
        yield engine
    finally:
        engine.dispose()


class TestMigrationStatic:
    def test_independent_bootstrap_and_migration_ddl_are_equal(self):
        def literal(path, name):
            tree = ast.parse(path.read_text())
            return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                        and any(isinstance(x, ast.Name) and x.id == name for x in n.targets))
        assert literal(MIGRATION, "TENANT_DDL") == literal(ROOT / "scripts/bootstrap_tenant_schema.py", "CREDENTIAL_EPOCH_DDL")
        assert literal(MIGRATION, "down_revision") == "044_inventory_adjustment_approval"
        for n in ast.walk(ast.parse(MIGRATION.read_text())):
            if isinstance(n, ast.ImportFrom):
                assert not (n.module or "").startswith(("models", "services", "scripts"))

    def test_downgrade_cannot_reaccept_old_sessions(self):
        with pytest.raises(RuntimeError, match="forward-only"):
            _load(MIGRATION, "foundation_migration_downgrade").downgrade()


class TestBeforeMigration:
    async def test_actual_asyncpg_upgrade_and_rollback(self, pre045, monkeypatch):
        migration = _load(MIGRATION, "foundation_migration_asyncpg")
        engine = create_async_engine(os.environ["TEST_MIGRATION_DATABASE_URL"].replace(
            "postgresql://", "postgresql+asyncpg://"), poolclass=NullPool)
        with pre045.connect() as app:
            before = _snapshot(app)
        try:
            async with engine.connect() as c:
                tx = await c.begin()
                try:
                    def apply(real_connection):
                        with monkeypatch.context() as patch:
                            patch.setattr(migration.op, "get_bind", lambda: real_connection)
                            migration.upgrade()
                        real_connection.execute(sa.text("SET ROLE mpango_app"))
                        assert _snapshot(real_connection) == before
                        assert _column_count(real_connection) == len(before["schemas"])
                        real_connection.execute(sa.text("RESET ROLE"))
                    await c.run_sync(apply)
                finally:
                    await tx.rollback()
            with pre045.connect() as app:
                assert _snapshot(app) == before and _column_count(app) == 0
        finally:
            await engine.dispose()

    async def test_actual_upgrade_preserves_existing_data_inside_transaction(self, pre045, monkeypatch):
        migration = _load(MIGRATION, "foundation_migration_preserve")
        engine = _sync_engine("TEST_MIGRATION_DATABASE_URL")
        with pre045.connect() as app:
            before = _snapshot(app)
        try:
            with engine.connect() as c:
                tx = c.begin()
                try:
                    with monkeypatch.context() as patch:
                        patch.setattr(migration.op, "get_bind", lambda: c)
                        migration.upgrade()
                    c.execute(sa.text("SET ROLE mpango_app"))
                    assert _snapshot(c) == before
                    assert _column_count(c) == len(before["schemas"])
                    for schema in before["schemas"]:
                        assert set(c.execute(sa.text(f'SELECT credential_epoch FROM "{schema}".users')).scalars()) == {1}
                    c.execute(sa.text("RESET ROLE"))
                finally:
                    tx.rollback()
            with pre045.connect() as app:
                assert _snapshot(app) == before and _column_count(app) == 0
        finally:
            engine.dispose()

    async def test_later_schema_sql_failure_rolls_back_every_schema(self, pre045, monkeypatch):
        migration = _load(MIGRATION, "foundation_migration_rollback")
        engine = _sync_engine("TEST_MIGRATION_DATABASE_URL")
        with pre045.connect() as app:
            before = _snapshot(app)
        reached = []
        try:
            with engine.connect() as c:
                tx = c.begin()
                real_execute = c.execute

                def failing_second_guard(statement, *args, **kwargs):
                    result = real_execute(statement, *args, **kwargs)
                    sql = str(statement)
                    if "CREATE TRIGGER credential_epoch_monotonic" in sql:
                        reached.append(next(s for s in before["schemas"] if '"' + s + '"' in sql))
                        if len(reached) == len(before["schemas"]):
                            real_execute(sa.text("SELECT 1/0"))
                    return result

                try:
                    with monkeypatch.context() as patch:
                        patch.setattr(migration.op, "get_bind", lambda: c)
                        patch.setattr(c, "execute", failing_second_guard)
                        with pytest.raises(sa.exc.DBAPIError):
                            migration.upgrade()
                finally:
                    tx.rollback()
            assert reached == sorted(before["schemas"])
            with pre045.connect() as app:
                assert _column_count(app) == 0 and _snapshot(app) == before
        finally:
            engine.dispose()

    async def test_application_role_cannot_run_migration(self, pre045, monkeypatch):
        migration = _load(MIGRATION, "foundation_migration_app_refused")
        with pre045.begin() as app:
            with monkeypatch.context() as patch:
                patch.setattr(migration.op, "get_bind", lambda: app)
                with pytest.raises(RuntimeError, match="MIGRATION_AUTHORITY_REQUIRED"):
                    migration.upgrade()
            assert _column_count(app) == 0

    async def test_unregistered_schema_is_not_silently_skipped(self, pre045, monkeypatch):
        migration = _load(MIGRATION, "foundation_migration_orphan")
        orphan = "t_" + uuid4().hex
        with pre045.begin() as app:
            app.execute(sa.text(f'CREATE SCHEMA "{orphan}"'))
            app.execute(sa.text(f'CREATE TABLE "{orphan}".users(id uuid PRIMARY KEY)'))
        engine = _sync_engine("TEST_MIGRATION_DATABASE_URL")
        try:
            with engine.begin() as c:
                with monkeypatch.context() as patch:
                    patch.setattr(migration.op, "get_bind", lambda: c)
                    with pytest.raises(RuntimeError, match="TENANT_OBJECT_MISMATCH"):
                        migration.upgrade()
                assert _column_count(c) == 0
        finally:
            with pre045.begin() as app:
                app.execute(sa.text(f'DROP TABLE "{orphan}".users'))
                app.execute(sa.text(f'DROP SCHEMA "{orphan}"'))
            engine.dispose()


class TestAfterMigration:
    def test_native_upgrade_committed_only_new_column_and_guards(self):
        engine = _sync_engine("DATABASE_URL")
        try:
            with engine.connect() as c:
                assert c.scalar(sa.text("SELECT version_num FROM public.alembic_version")) == "045_owner_staff_recovery"
                before = json.loads(Path(os.environ["FOUNDATION_PRE045_SNAPSHOT"]).read_text())
                assert _column_count(c) == len(before["schemas"])
                assert _snapshot(c) == before
                assert before["bindings"] and before["bindings"][0]["status"] == "inactive"
                assert any(s not in {"t_dev", "t_test"} and before["schemas"][s]["user_roles"] for s in before["schemas"])
                for schema in before["schemas"]:
                    assert set(c.execute(sa.text(f'SELECT credential_epoch FROM "{schema}".users')).scalars()) == {1}
        finally:
            engine.dispose()
