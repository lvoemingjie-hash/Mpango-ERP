"""Focused permanent tests for the combined Order R2 + tenant DB-authority
setup contract (CTO-AUTH-ORDER-R2-DB-AUTHORITY-INTEGRATION-R1-2026-09-19).

Three bounded groups, all exercising PRODUCT entry points only:

  1. the provisioner CLI rejects the invalid ``--provision --apply-grants``
     phase combination BEFORE any connection, role, database or grant write;
  2. the setup preflight rejects single-role configurations, endpoint or
     database mismatches and provisioning-password inconsistencies before any
     side effect, and accepts a conforming three-URL two-role configuration;
  3. (opt-in, disposable database) the full two-role lifecycle using the
     product-supported operator sequence — provision, migrate 001..039 as the
     migration authority, minimum grants, read-only verify, runtime bootstrap,
     tenant lifecycle — plus the read-only public-contract refusal matrix with
     zero-tenant-DDL and ledger-guard invariance proofs.

The historical mutation-runner / source-reader governance artifacts are
deliberately NOT prerequisites: nothing here imports them.
"""
from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
PROVISIONER = BACKEND_DIR / "scripts" / "provision_runtime_db_roles.py"
BOOTSTRAP = BACKEND_DIR / "scripts" / "bootstrap_tenant_schema.py"

PREFLIGHT_PATH = BACKEND_DIR / "scripts" / "setup_preflight.py"
_spec = importlib.util.spec_from_file_location("combined_setup_preflight", PREFLIGHT_PATH)
assert _spec is not None and _spec.loader is not None
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_provisioner(args: list[str], extra_env: dict[str, str]):
    return subprocess.run(
        [sys.executable, str(PROVISIONER), *args],
        env={**os.environ, **extra_env},
        capture_output=True, text=True, timeout=180,
    )


# ---------------------------------------------------------------------------
# 1. provisioner CLI phase contract
# ---------------------------------------------------------------------------
BOGUS_URLS = {
    "MPANGO_DB_ADMIN_URL": "postgresql://postgres:pw@127.0.0.1:1/postgres",
    "MPANGO_DB_MIGRATE_URL": "postgresql://m:pw@127.0.0.1:1/appdb",
    "MPANGO_DB_APP_URL": "postgresql://a:pw@127.0.0.1:1/appdb",
}


def test_provisioner_rejects_combined_phase_before_writes():
    result = _run_provisioner(["--provision", "--apply-grants"], dict(BOGUS_URLS))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "invalid phase combination" in result.stderr
    # Pre-write proof: argparse refused — the port-1 URLs can never connect,
    # so any phase output or connection error would mean the refusal never
    # happened.
    assert "[binding]" not in result.stdout
    assert "[grants]" not in result.stdout
    assert "[roles]" not in result.stdout


def test_provisioner_single_phase_still_reaches_execution():
    """Negative control for the rejection: a single phase is not refused by
    the phase contract (it proceeds far enough to fail on the dead endpoint)."""
    result = _run_provisioner(["--provision"], dict(BOGUS_URLS))
    assert "invalid phase combination" not in result.stderr
    assert result.returncode != 2 or "nothing to do" in result.stderr


def test_provisioner_still_requires_at_least_one_phase():
    result = _run_provisioner([], dict(BOGUS_URLS))
    assert result.returncode == 2
    assert "nothing to do" in result.stderr


# ---------------------------------------------------------------------------
# 2. setup preflight two-role contract
# ---------------------------------------------------------------------------
GOOD_ENV = {
    "DATABASE_URL": "postgresql://mpango_app:app_pw@localhost:5432/mpango_erp",
    "MPANGO_DB_ADMIN_URL": "postgresql://postgres:admin_pw@localhost:5432/mpango_erp",
    "MPANGO_DB_MIGRATE_URL": "postgresql://mpango_migrate:mig_pw@localhost:5432/mpango_erp",
    "MPANGO_DB_APP_PASSWORD": "app_pw",
    "MPANGO_DB_MIGRATE_PASSWORD": "mig_pw",
    "REDIS_URL": "redis://localhost:6379/0",
    "REPORTING_USER_PASSWORD": "rup_pw",
}


def _port_entry(target: int) -> dict:
    return {
        "host_ip": "127.0.0.1", "target": target, "published": target,
        "protocol": "tcp", "mode": "ingress",
    }


def _compose_json() -> dict:
    return {"services": {
        "postgres": {
            "ports": [_port_entry(5432)],
            "environment": {
                "POSTGRES_USER": "postgres",
                "POSTGRES_PASSWORD": "admin_pw",
                "POSTGRES_DB": "mpango_erp",
            },
        },
        "redis": {"ports": [_port_entry(6379)]},
        "backend": {"environment": {"REPORTING_USER_PASSWORD": "rup_pw"}},
    }}


def _run_preflight(monkeypatch, tmp_path, env_overrides: dict[str, str]) -> tuple[int, str]:
    env = dict(GOOD_ENV)
    env.update(env_overrides)
    for key, value in list(env_overrides.items()):
        if value == "":
            env.pop(key, None)
    env_path = tmp_path / "backend.env"
    env_path.write_text("\n".join(f"{k}={v}" for k, v in env.items()) + "\n")
    # process-env conflicts: preflight reads os.environ — keep it consistent
    # with the file for the keys it checks.
    for key in ("DATABASE_URL", "REDIS_URL", "REPORTING_USER_PASSWORD",
                "MPANGO_DB_ADMIN_URL", "MPANGO_DB_MIGRATE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_compose_json())))
    import contextlib
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            pf.run_initial(str(env_path))
    except SystemExit as exc:  # _fail path
        return exc.code or 1, ""
    return 0, stdout.getvalue()


def test_preflight_accepts_conforming_two_role_config(monkeypatch, tmp_path):
    code, out = _run_preflight(monkeypatch, tmp_path, {})
    assert code == 0
    assert out.strip() == "OK"


@pytest.mark.parametrize("field,value,fragment", [
    ("MPANGO_DB_ADMIN_URL", "postgresql://postgres:admin_pw@localhost:5432/other_db",
     "must target one database"),
    ("MPANGO_DB_MIGRATE_URL", "postgresql://mpango_migrate:mig_pw@localhost:5433/mpango_erp",
     "must target one endpoint"),
    ("MPANGO_DB_ADMIN_URL",
     "postgresql://mpango_app:admin_pw@localhost:5432/mpango_erp",
     "three distinct roles"),
    ("MPANGO_DB_MIGRATE_URL",
     "postgresql://postgres:mig_pw@localhost:5432/mpango_erp",
     "three distinct roles"),
])
def test_preflight_rejects_role_and_endpoint_drift(monkeypatch, tmp_path, field, value, fragment):
    code, _ = _run_preflight(monkeypatch, tmp_path, {field: value})
    assert code != 0
    assert fragment in pytest_err(monkeypatch, tmp_path, {field: value})


def pytest_err(monkeypatch, tmp_path, overrides):  # helper capturing stderr
    import contextlib
    env = dict(GOOD_ENV)
    env.update(overrides)
    env_path = tmp_path / "backend.env"
    env_path.write_text("\n".join(f"{k}={v}" for k, v in env.items()) + "\n")
    for key in ("DATABASE_URL", "REDIS_URL", "REPORTING_USER_PASSWORD",
                "MPANGO_DB_ADMIN_URL", "MPANGO_DB_MIGRATE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_compose_json())))
    err = io.StringIO()
    with contextlib.redirect_stderr(err), pytest.raises(SystemExit):
        pf.run_initial(str(env_path))
    return err.getvalue()


def test_preflight_rejects_runtime_naming_compose_admin(monkeypatch, tmp_path):
    err = pytest_err(monkeypatch, tmp_path, {
        "DATABASE_URL": "postgresql://postgres:app_pw@localhost:5432/mpango_erp",
    })
    assert "MPANGO_DB_ADMIN_URL username does not match Compose POSTGRES_USER" in err


def test_preflight_rejects_missing_admin_url(monkeypatch, tmp_path):
    err = pytest_err(monkeypatch, tmp_path, {"MPANGO_DB_ADMIN_URL": ""})
    assert "MPANGO_DB_ADMIN_URL not found in backend/.env" in err


def test_preflight_rejects_app_password_mismatch(monkeypatch, tmp_path):
    err = pytest_err(monkeypatch, tmp_path, {"MPANGO_DB_APP_PASSWORD": "wrong"})
    assert "MPANGO_DB_APP_PASSWORD does not match" in err


def test_preflight_rejects_migrate_password_mismatch(monkeypatch, tmp_path):
    err = pytest_err(monkeypatch, tmp_path, {"MPANGO_DB_MIGRATE_PASSWORD": "wrong"})
    assert "MPANGO_DB_MIGRATE_PASSWORD does not match" in err


# ---------------------------------------------------------------------------
# 3. two-role lifecycle + public-contract refusal matrix (opt-in, real PG16)
# ---------------------------------------------------------------------------
_requires_temp_db = pytest.mark.skipif(
    os.environ.get("MPANGO_ALLOW_TEMP_DB_CREATE") != "1",
    reason="set MPANGO_ALLOW_TEMP_DB_CREATE=1 for migration/lifecycle tests",
)

CANONICAL = "ck_wrb_outstanding_balance_non_negative"
GUARD_SNAPSHOT_SQL = (
    "SELECT oid::text, pg_get_userbyid(proowner), prosrc "
    "FROM pg_proc WHERE oid = 'public.prevent_ledger_modification()'::regprocedure"
)


def _admin_connect(admin_url: str):
    import psycopg2
    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    return conn


def _guard_snapshot(conn):
    with conn.cursor() as cur:
        cur.execute(GUARD_SNAPSHOT_SQL)
        row = cur.fetchone()
    assert row is not None, "ledger guard missing"
    return tuple(row)


def _tenant_schema_count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 't\\_%'")
        return int(cur.fetchone()[0])


def _constraint_names(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "WHERE n.nspname='public' AND t.relname='wholesaler_retailer_bindings' "
            "AND c.contype='c' ORDER BY conname")
        return [r[0] for r in cur.fetchall()]


@_requires_temp_db
def test_two_role_lifecycle_and_public_contract_refusals():
    import psycopg2
    from urllib.parse import urlsplit, urlunparse

    bts = _load_module("combined_contract_bts", BOOTSTRAP)
    source = os.environ["TEST_DATABASE_URL"]
    parsed = urlsplit(source)
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    suffix = uuid.uuid4().hex[:8]
    mig_role = f"mpango_migrate_{suffix}"
    app_role = f"mpango_app_{suffix}"
    mig_pw = f"pw_{suffix}_m"
    app_pw = f"pw_{suffix}_a"
    sandbox_db = f"test_combinedauth_{suffix}"
    tenant = f"t_{uuid.uuid4().hex}"

    def _url(user: str, password: str) -> str:
        return urlunparse(parsed._replace(
            netloc=f"{user}:{password}@{parsed.hostname}:{parsed.port or 5432}",
            path=f"/{sandbox_db}"))

    mig_url = _url(mig_role, mig_pw)
    app_url = _url(app_role, app_pw)
    prov_env = {
        "MPANGO_DB_ADMIN_URL": admin_url,
        "MPANGO_DB_MIGRATE_URL": mig_url,
        "MPANGO_DB_APP_URL": app_url,
        "MPANGO_DB_MIGRATE_ROLE": mig_role,
        "MPANGO_DB_APP_ROLE": app_role,
        "MPANGO_DB_MIGRATE_PASSWORD": mig_pw,
        "MPANGO_DB_APP_PASSWORD": app_pw,
    }
    try:
        # phase 1: provision (admin) — the sandbox database does NOT pre-exist;
        # the product creates it owned by the migration authority.
        result = _run_provisioner(["--provision"], prov_env)
        assert result.returncode == 0, result.stderr
        # phase 2: migrations 001..039 as the migration authority
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR, capture_output=True, text=True, timeout=600,
            env={**os.environ, "DATABASE_URL": mig_url,
                 "REPORTING_USER_PASSWORD": f"rup_{suffix}",
                 "MPANGO_ENV": "test"})
        assert result.returncode == 0, result.stderr[-2000:]
        # phase 3: minimum grants as the migration authority
        result = _run_provisioner(["--apply-grants"], prov_env)
        assert result.returncode == 0, result.stderr
        # phase 4: read-only verification
        result = _run_provisioner(["--verify"], prov_env)
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert '"ok": true' in result.stdout

        admin = _admin_connect(admin_url)
        try:
            with admin.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (sandbox_db,))
                assert cur.fetchone() is not None
                cur.execute("SELECT pg_get_userbyid(datdba) FROM pg_database "
                            "WHERE datname = %s", (sandbox_db,))
                assert cur.fetchone()[0] == mig_role, \
                    "product provision must own the fresh database by the migration authority"
            admin_role = parsed.username or "postgres"

            # --- guard authority negatives on the PRISTINE sandbox (no
            # tenant triggers yet, so the guard can be removed/restored
            # cleanly); every refusal leaves ZERO tenant schemas ------------
            with admin.cursor() as cur:
                cur.execute(
                    "SELECT pg_get_functiondef("
                    "'public.prevent_ledger_modification()'::regprocedure)")
                guard_def = cur.fetchone()[0]

            async def _boot_refuses():
                await bts.bootstrap(f"t_{uuid.uuid4().hex}", app_url)

            with admin.cursor() as cur:
                cur.execute("DROP FUNCTION public.prevent_ledger_modification()")
            with pytest.raises(bts.LedgerGuardAuthorityError):
                asyncio.run(_boot_refuses())
            assert _tenant_schema_count(admin) == 0
            with admin.cursor() as cur:
                cur.execute(guard_def)
            with admin.cursor() as cur:
                cur.execute(f"ALTER FUNCTION public.prevent_ledger_modification() "
                            f"OWNER TO {admin_role}")
            with pytest.raises(bts.LedgerGuardAuthorityError):
                asyncio.run(_boot_refuses())
            assert _tenant_schema_count(admin) == 0
            with admin.cursor() as cur:
                cur.execute(f"ALTER FUNCTION public.prevent_ledger_modification() "
                            f"OWNER TO {mig_role}")

            # --- wrong migration head: simulate drift on alembic_version and
            # require the named refusal --------------------------------------
            with admin.cursor() as cur:
                cur.execute("UPDATE alembic_version SET version_num = "
                            "'038_catalog_identity_vertical_slice'")
            with pytest.raises(RuntimeError) as excinfo:
                asyncio.run(_boot_refuses())
            assert "039_order_credit_holds" in str(excinfo.value)
            assert _tenant_schema_count(admin) == 0
            with admin.cursor() as cur:
                cur.execute("UPDATE alembic_version SET version_num = "
                            "'039_order_credit_holds'")

            guard0 = _guard_snapshot(admin)

            # phase 5: runtime bootstrap (positive path)
            asyncio.run(bts.bootstrap(tenant, app_url))
            assert _tenant_schema_count(admin) == 1

            # guard invariance across further bootstrap attempts
            assert _guard_snapshot(admin) == guard0

            # the runtime role cannot replace the migration-owned guard
            async def _runtime_tries_replacement():
                from sqlalchemy import text
                from sqlalchemy.ext.asyncio import create_async_engine
                engine = create_async_engine(
                    app_url.replace("postgresql://", "postgresql+asyncpg://", 1))
                try:
                    async with engine.begin() as conn:
                        await conn.execute(text(
                            "CREATE OR REPLACE FUNCTION "
                            "public.prevent_ledger_modification() RETURNS trigger "
                            "AS $body$ BEGIN RETURN OLD; END; $body$ LANGUAGE plpgsql"))
                finally:
                    await engine.dispose()
            with pytest.raises(Exception) as excinfo:
                asyncio.run(_runtime_tries_replacement())
            assert "permission" in str(excinfo.value).lower() or "42501" in str(excinfo.value)
            assert _guard_snapshot(admin) == guard0

            # public-contract refusal matrix — every refusal must leave zero
            # additional tenant objects, an unrepaired public state and an
            # unchanged ledger guard (bootstrap performs NO public DDL).
            def _refuse(case: str, fragment: str, corrupt, restore):
                corrupt(admin)
                before = _tenant_schema_count(admin)
                state = _constraint_names(admin)
                with pytest.raises(bts.PublicContractError) as excinfo:
                    asyncio.run(bts.bootstrap(f"t_{uuid.uuid4().hex}", app_url))
                assert fragment in str(excinfo.value), (case, str(excinfo.value))
                assert _tenant_schema_count(admin) == before
                assert _constraint_names(admin) == state
                assert _guard_snapshot(admin) == guard0
                restore(admin)

            def _rename_to_legacy(conn):
                with conn.cursor() as cur:
                    cur.execute(
                        f"ALTER TABLE public.wholesaler_retailer_bindings RENAME "
                        f"CONSTRAINT {CANONICAL} TO ck_wrb_outstanding_balance_legacy")
            def _rename_back(conn):
                with conn.cursor() as cur:
                    cur.execute(
                        "ALTER TABLE public.wholesaler_retailer_bindings RENAME "
                        f"CONSTRAINT ck_wrb_outstanding_balance_legacy TO {CANONICAL}")

            def _drop_canonical(conn):
                with conn.cursor() as cur:
                    cur.execute(
                        f"ALTER TABLE public.wholesaler_retailer_bindings "
                        f"DROP CONSTRAINT {CANONICAL}")
            def _add_canonical(conn):
                with conn.cursor() as cur:
                    cur.execute(
                        f"ALTER TABLE public.wholesaler_retailer_bindings ADD "
                        f"CONSTRAINT {CANONICAL} CHECK (outstanding_balance >= 0)")

            _refuse("legacy", "legacy-named", _rename_to_legacy, _rename_back)
            _refuse("missing", "is missing", _drop_canonical, _add_canonical)

            def _corrupt_incompatible(conn):
                _drop_canonical(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        "ALTER TABLE public.wholesaler_retailer_bindings ADD "
                        "CONSTRAINT ck_wrb_outstanding_balance_upper "
                        "CHECK (outstanding_balance > 0)")
            def _restore_incompatible(conn):
                with conn.cursor() as cur:
                    cur.execute(
                        "ALTER TABLE public.wholesaler_retailer_bindings "
                        "DROP CONSTRAINT ck_wrb_outstanding_balance_upper")
                _add_canonical(conn)
            _refuse("incompatible", "incompatible", _corrupt_incompatible,
                    _restore_incompatible)

            assert _guard_snapshot(admin) == guard0

            # tenant lifecycle: the runtime role owns the tenant schema and can
            # conduct ordinary business there.
            async def _tenant_business():
                from sqlalchemy import text
                from sqlalchemy.ext.asyncio import create_async_engine
                engine = create_async_engine(
                    app_url.replace("postgresql://", "postgresql+asyncpg://", 1))
                try:
                    async with engine.begin() as conn:
                        await conn.execute(text(
                            f'INSERT INTO "{tenant}".catalog_products '
                            "(name, is_active, is_deleted) VALUES ('probe', TRUE, FALSE)"))
                        row = (await conn.execute(text(
                            f'SELECT name FROM "{tenant}".catalog_products '
                            "WHERE name = 'probe'"))).scalar()
                        assert row == "probe"
                finally:
                    await engine.dispose()
            asyncio.run(_tenant_business())
        finally:
            admin.close()
    finally:
        # cleanup: drop the product-created database and roles
        try:
            admin = _admin_connect(admin_url)
            try:
                with admin.cursor() as cur:
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()", (sandbox_db,))
                    cur.execute(f'DROP DATABASE IF EXISTS "{sandbox_db}"')
                    cur.execute(f'DROP ROLE IF EXISTS "{app_role}"')
                    cur.execute(f'DROP ROLE IF EXISTS "{mig_role}"')
            finally:
                admin.close()
        except Exception:
            pass
