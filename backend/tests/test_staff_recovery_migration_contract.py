"""045 migration controls: true 044 prestate and separately measured 045 poststate."""
import ast
import asyncio
from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from tests.task_owned_pg_resources import _native, task_postgres

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic/versions/045_owner_staff_recovery.py"
PREVIOUS_REVISION = "044_inventory_adjustment_approval"
RECOVERY_REVISION = "045_owner_staff_recovery"


@dataclass
class HistoricalDatabase:
    app_engine: sa.Engine
    migration_url: str
    snapshot: Path
    evidence_root: Path
    migration_env: dict[str, str]


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sync_engine(url):
    return sa.create_engine(url.replace("postgresql+asyncpg://", "postgresql://"), poolclass=NullPool)


def _snapshot(connection, saved):
    result = {"schemas": {}, "bindings": []}
    for schema in _schemas(connection, saved):
        result["schemas"][schema] = {}
        for table in ("users", "roles", "user_roles", "permissions", "role_permissions",
                      "staff_authority", "staff_memberships", "staff_role_templates"):
            rows = connection.execute(sa.text(f'SELECT to_jsonb(x) FROM "{schema}".{table} x')).scalars().all()
            # credential_epoch is the only permitted new user datum.
            for row in rows:
                if table == "users":
                    row.pop("credential_epoch", None)
            result["schemas"][schema][table] = sorted(rows, key=lambda x: json.dumps(x, sort_keys=True))
    ids = [row["id"] for row in json.loads(saved.read_text())["bindings"]] if saved.exists() else None
    rows = connection.execute(sa.text("SELECT to_jsonb(b) FROM public.wholesaler_retailer_bindings b")).scalars().all()
    result["bindings"] = sorted([row for row in rows if ids is None or row["id"] in ids], key=lambda x: x["id"])
    return result


def _schemas(connection, saved):
    if saved.exists():
        return sorted(json.loads(saved.read_text())["schemas"])
    return sorted({"t_dev", "t_test"} | set(connection.execute(sa.text(
        "SELECT tenant_schema FROM public.tenant_registrations WHERE tenant_schema IS NOT NULL AND is_deleted IS FALSE"
    )).scalars()))


def _column_count(connection, saved):
    return connection.scalar(sa.text(
        "SELECT count(*) FROM information_schema.columns WHERE table_schema=ANY(:schemas) "
        "AND table_name='users' AND column_name='credential_epoch'"
    ), {"schemas": _schemas(connection, saved)})


def _predecessor_bootstrap(root):
    """Load the immutable parent of the commit that introduced revision 045."""
    migration_path = MIGRATION.relative_to(ROOT.parent)
    history = subprocess.check_output([
        "git", "log", "--full-history", "--diff-filter=A", "--format=%P", "--", str(migration_path),
    ], cwd=ROOT.parent, timeout=20, text=True).split()
    assert len(history) == 1, "HISTORICAL_044_PREDECESSOR_UNPROVEN"
    parent = history[0]
    old_inputs = subprocess.check_output([
        "git", "ls-tree", "-r", "--name-only", parent, "--", "backend/alembic", "backend/alembic.ini",
    ], cwd=ROOT.parent, timeout=20, text=True).splitlines()
    assert "backend/alembic/versions/044_inventory_adjustment_approval.py" in old_inputs
    subprocess.run(["git", "diff", "--exit-code", parent, "--", *old_inputs],
                   cwd=ROOT.parent, check=True, capture_output=True, timeout=20)
    for name in ("bootstrap_tenant_schema", "provision_runtime_db_roles"):
        contents = subprocess.check_output([
            "git", "show", f"{parent}:backend/scripts/{name}.py",
        ], cwd=ROOT.parent, timeout=20)
        (root / (name + ".py")).write_bytes(contents)
    (root / "044-source.json").write_text(json.dumps({
        "source_commit": parent, "reused_migration_inputs_equal": old_inputs,
        "revision": PREVIOUS_REVISION,
    }, indent=2) + "\n")
    return (
        _load(root / "bootstrap_tenant_schema.py", "foundation_baseline_bootstrap"),
        _load(root / "provision_runtime_db_roles.py", "foundation_baseline_roles"),
    )


async def _seed_historical_state(engine, app_url, bootstrap, snapshot_path):
    """Use the original 044 onboarding and owner setup before snapshotting."""
    from core.security import hash_password
    for schema in ("t_test", "t_dev"):
        await bootstrap(schema, app_url)
    if not snapshot_path.exists():
        # Create the registered historical tenant through the real provisioner
        # and Owner setup; only its bootstrap implementation is the frozen C0.
        from db.tenant_filter import mark_session_as_system
        from services.tenant_provisioning_service import TenantProvisioningService
        from services.owner_credential_service import OwnerCredentialSetupService
        async_engine = create_async_engine(app_url.replace("postgresql://", "postgresql+asyncpg://"), poolclass=NullPool)
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
                service = TenantProvisioningService(
                    db, bootstrap_func=bootstrap, database_url=app_url,
                )
                assert (await service.claim_registration_for_provisioning(str(registration))).action == "claimed"
                await db.commit()
                result = await service.provision_wholesaler_and_schema(str(registration))
                assert result.action == "provisioned", "HISTORICAL_TENANT_BOOTSTRAP_" + str(result.reason)
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
            state = _snapshot(c, snapshot_path)
        with os.fdopen(os.open(snapshot_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
            json.dump(state, f, sort_keys=True)


@pytest_asyncio.fixture(scope="module")
async def historical_database():
    shared = urlsplit(os.environ["DATABASE_URL"])
    with task_postgres("staff_045", cluster_only=True) as cluster:
        root = Path(cluster["private_root"])
        app = urlsplit(cluster["runtime_endpoint"])
        admin = urlsplit(cluster["admin_sync"])
        assert app.hostname == admin.hostname == "127.0.0.1"
        assert app.port == admin.port and app.port != (shared.port or 5432)
        assert admin.username == "postgres" and admin.path == "/postgres"
        assert app.username == "mpango_app" and app.password
        assert cluster["container"] != os.environ.get("CI_PG_CONTAINER_ID")
        database = app.path.removeprefix("/")
        assert database == "test_c91_staff_045"
        migrate_password = secrets.token_urlsafe(32)
        reporting_password = secrets.token_urlsafe(32)
        migrate_url = app._replace(netloc=f"mpango_migrate:{migrate_password}@127.0.0.1:{app.port}").geturl()
        boot, roles = _predecessor_bootstrap(root)
        provisioner = roles.Provisioner(admin.geturl(), migrate_url, app.geturl(),
                                        "mpango_migrate", "mpango_app", database)
        await provisioner.create_roles_and_database(
            app_password=unquote(app.password), migrate_password=migrate_password,
        )
        conn = await asyncpg.connect(admin._replace(path=app.path).geturl())
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        finally:
            await conn.close()
        env = {key: os.environ[key] for key in (
            "HOME", "PATH", "LANG", "VIRTUAL_ENV", "PYTHONNOUSERSITE", "SECRET_KEY",
        ) if key in os.environ}
        env.update(DATABASE_URL=migrate_url, MPANGO_ENV="test", REPORTING_USER_PASSWORD=reporting_password,
                   PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
        await asyncio.to_thread(_native, root, "migrate-044",
                                [sys.executable, "-B", "-m", "alembic", "upgrade", PREVIOUS_REVISION],
                                env=env, timeout=120)
        await provisioner.apply_minimum_grants()
        assert (await provisioner.verify())["ok"] is True
        engine = _sync_engine(app.geturl())
        snapshot = root / "pre045.json"
        try:
            with engine.connect() as c:
                assert c.execute(sa.text("SELECT version_num FROM public.alembic_version")).scalars().all() == [PREVIOUS_REVISION]
            await _seed_historical_state(engine, app.geturl(), boot.bootstrap, snapshot)
            yield HistoricalDatabase(engine, migrate_url, snapshot, root, env)
        finally:
            engine.dispose()


@pytest.fixture
def pre045(historical_database):
    """All pre-controls start at the measured 044 snapshot."""
    fixture = historical_database
    with fixture.app_engine.connect() as c:
        assert c.execute(sa.text("SELECT version_num FROM public.alembic_version")).scalars().all() == [PREVIOUS_REVISION]
        assert _snapshot(c, fixture.snapshot) == json.loads(fixture.snapshot.read_text())
        assert _column_count(c, fixture.snapshot) == 0
    return fixture


@pytest_asyncio.fixture(scope="module")
async def after045(historical_database):
    fixture = historical_database
    with fixture.app_engine.connect() as c:
        assert c.execute(sa.text("SELECT version_num FROM public.alembic_version")).scalars().all() == [PREVIOUS_REVISION]
        assert _snapshot(c, fixture.snapshot) == json.loads(fixture.snapshot.read_text())
        assert _column_count(c, fixture.snapshot) == 0
    await asyncio.to_thread(_native, fixture.evidence_root, "migrate-045",
                            [sys.executable, "-B", "-m", "alembic", "upgrade", RECOVERY_REVISION],
                            env=fixture.migration_env, timeout=120)
    return fixture


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
        engine = create_async_engine(pre045.migration_url.replace(
            "postgresql://", "postgresql+asyncpg://"), poolclass=NullPool)
        with pre045.app_engine.connect() as app:
            before = _snapshot(app, pre045.snapshot)
        try:
            async with engine.connect() as c:
                tx = await c.begin()
                try:
                    def apply(real_connection):
                        with monkeypatch.context() as patch:
                            patch.setattr(migration.op, "get_bind", lambda: real_connection)
                            migration.upgrade()
                        real_connection.execute(sa.text("SET ROLE mpango_app"))
                        assert _snapshot(real_connection, pre045.snapshot) == before
                        assert _column_count(real_connection, pre045.snapshot) == len(before["schemas"])
                        real_connection.execute(sa.text("RESET ROLE"))
                    await c.run_sync(apply)
                finally:
                    await tx.rollback()
            with pre045.app_engine.connect() as app:
                assert _snapshot(app, pre045.snapshot) == before and _column_count(app, pre045.snapshot) == 0
        finally:
            await engine.dispose()

    async def test_actual_upgrade_preserves_existing_data_inside_transaction(self, pre045, monkeypatch):
        migration = _load(MIGRATION, "foundation_migration_preserve")
        engine = _sync_engine(pre045.migration_url)
        with pre045.app_engine.connect() as app:
            before = _snapshot(app, pre045.snapshot)
        try:
            with engine.connect() as c:
                tx = c.begin()
                try:
                    with monkeypatch.context() as patch:
                        patch.setattr(migration.op, "get_bind", lambda: c)
                        migration.upgrade()
                    c.execute(sa.text("SET ROLE mpango_app"))
                    assert _snapshot(c, pre045.snapshot) == before
                    assert _column_count(c, pre045.snapshot) == len(before["schemas"])
                    for schema in before["schemas"]:
                        assert set(c.execute(sa.text(f'SELECT credential_epoch FROM "{schema}".users')).scalars()) == {1}
                    c.execute(sa.text("RESET ROLE"))
                finally:
                    tx.rollback()
            with pre045.app_engine.connect() as app:
                assert _snapshot(app, pre045.snapshot) == before and _column_count(app, pre045.snapshot) == 0
        finally:
            engine.dispose()

    async def test_later_schema_sql_failure_rolls_back_every_schema(self, pre045, monkeypatch):
        migration = _load(MIGRATION, "foundation_migration_rollback")
        engine = _sync_engine(pre045.migration_url)
        with pre045.app_engine.connect() as app:
            before = _snapshot(app, pre045.snapshot)
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
            with pre045.app_engine.connect() as app:
                assert _column_count(app, pre045.snapshot) == 0 and _snapshot(app, pre045.snapshot) == before
        finally:
            engine.dispose()

    async def test_application_role_cannot_run_migration(self, pre045, monkeypatch):
        migration = _load(MIGRATION, "foundation_migration_app_refused")
        with pre045.app_engine.begin() as app:
            with monkeypatch.context() as patch:
                patch.setattr(migration.op, "get_bind", lambda: app)
                with pytest.raises(RuntimeError, match="MIGRATION_AUTHORITY_REQUIRED"):
                    migration.upgrade()
            assert _column_count(app, pre045.snapshot) == 0

    async def test_unregistered_schema_is_not_silently_skipped(self, pre045, monkeypatch):
        migration = _load(MIGRATION, "foundation_migration_orphan")
        orphan = "t_" + uuid4().hex
        with pre045.app_engine.begin() as app:
            app.execute(sa.text(f'CREATE SCHEMA "{orphan}"'))
            app.execute(sa.text(f'CREATE TABLE "{orphan}".users(id uuid PRIMARY KEY)'))
        engine = _sync_engine(pre045.migration_url)
        try:
            with engine.begin() as c:
                with monkeypatch.context() as patch:
                    patch.setattr(migration.op, "get_bind", lambda: c)
                    with pytest.raises(RuntimeError, match="TENANT_OBJECT_MISMATCH"):
                        migration.upgrade()
                assert _column_count(c, pre045.snapshot) == 0
        finally:
            with pre045.app_engine.begin() as app:
                app.execute(sa.text(f'DROP TABLE "{orphan}".users'))
                app.execute(sa.text(f'DROP SCHEMA "{orphan}"'))
            engine.dispose()


class TestAfterMigration:
    def test_native_upgrade_committed_only_new_column_and_guards(self, after045):
        snapshot = after045.snapshot
        with after045.app_engine.connect() as c:
            head = c.execute(sa.text("SELECT version_num FROM public.alembic_version")).scalars().all()
            assert head == [RECOVERY_REVISION]
            before = json.loads(snapshot.read_text())
            assert _column_count(c, snapshot) == len(before["schemas"])
            assert _snapshot(c, snapshot) == before
            assert before["bindings"] and before["bindings"][0]["status"] == "inactive"
            assert any(s not in {"t_dev", "t_test"} and before["schemas"][s]["user_roles"] for s in before["schemas"])
            for schema in before["schemas"]:
                assert set(c.execute(sa.text(f'SELECT credential_epoch FROM "{schema}".users')).scalars()) == {1}
        with (after045.evidence_root / "045-assertions.json").open("x") as record:
            json.dump({"from": PREVIOUS_REVISION, "to": head[0], "data_preserved": True,
                       "tenant_count": len(before["schemas"]),
                       "inactive_binding_preserved": True, "all_initial_epochs": [1]}, record)
