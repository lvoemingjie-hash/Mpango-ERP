"""Focused permanent tests for the combined Order R2 + tenant DB-authority
setup contract (CTO-AUTH-ORDER-R2-DB-AUTHORITY-INTEGRATION-R1-R1-SOURCE-CORRECTION-2026-09-19).

Three bounded groups, all exercising PRODUCT entry points only:

  1. the provisioner CLI rejects the invalid ``--provision --apply-grants``
     phase combination BEFORE any connection, role, database or grant write;
  2. the setup preflight rejects single-role configurations, endpoint
     mismatches, provisioning-password inconsistencies, and any setup-only
     credential inside the rendered backend service environment; the admin
     URL targets the MAINTENANCE database while migration/runtime URLs target
     the application database (the sanctioned maintenance-vs-application
     shape);
  3. (opt-in, disposable databases) the ownership contract: an absent target
     database is created owned by the migration authority; an existing
     correct-owner database is accepted idempotently; any existing
     wrong-owner database - empty, carrying sentinel business data, or with
     fully connectable roles - is refused BEFORE any role/owner/grant write,
     and its contents remain untouched.

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
from urllib.parse import urlsplit

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
    "MPANGO_DB_ADMIN_URL": "postgresql://postgres:pw@127.0.0.1:1/postgres",  # pragma: allowlist secret
    "MPANGO_DB_MIGRATE_URL": "postgresql://m:pw@127.0.0.1:1/appdb",  # pragma: allowlist secret
    "MPANGO_DB_APP_URL": "postgresql://a:pw@127.0.0.1:1/appdb",  # pragma: allowlist secret
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
    "DATABASE_URL": "postgresql://mpango_app:app_pw@localhost:5432/mpango_erp",  # pragma: allowlist secret
    "DATABASE_URL_CONTAINER": "postgresql://mpango_app:app_pw@postgres:5432/mpango_erp",  # pragma: allowlist secret
    "MPANGO_DB_ADMIN_URL": "postgresql://postgres:admin_pw@localhost:5432/postgres",  # pragma: allowlist secret
    "MPANGO_DB_MIGRATE_URL": "postgresql://mpango_migrate:mig_pw@localhost:5432/mpango_erp",  # pragma: allowlist secret
    "MPANGO_DB_APP_PASSWORD": "app_pw",
    "MPANGO_DB_MIGRATE_PASSWORD": "mig_pw",
    "REDIS_URL": "redis://localhost:6379/0",
    "REDIS_URL_CONTAINER": "redis://redis:6379/0",
    "REPORTING_USER_PASSWORD": "rup_pw",
    "PUBLIC_FRONTEND_URL": "https://app.example.com",
    "REPORTING_DATABASE_URL_CONTAINER": "postgresql://reporting_user:rup_pw@postgres:5432/mpango_erp",
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
                "POSTGRES_DB": "postgres",
            },
        },
        "redis": {"ports": [_port_entry(6379)]},
        "backend": {"environment": {
            "DATABASE_URL": GOOD_ENV["DATABASE_URL_CONTAINER"],
            "REDIS_URL": GOOD_ENV["REDIS_URL_CONTAINER"],
            "PUBLIC_FRONTEND_URL": GOOD_ENV["PUBLIC_FRONTEND_URL"],
            "REPORTING_DATABASE_URL": GOOD_ENV["REPORTING_DATABASE_URL_CONTAINER"],
        }},
    }}


def _run_preflight(monkeypatch, tmp_path, env_overrides: dict[str, str],
                   compose_override: dict | None = None):
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
                "MPANGO_DB_ADMIN_URL", "MPANGO_DB_MIGRATE_URL",
                "DATABASE_URL_CONTAINER", "REDIS_URL_CONTAINER"):
        monkeypatch.delenv(key, raising=False)
    compose = compose_override if compose_override is not None else _compose_json()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(compose)))
    import contextlib
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            pf.run_initial(str(env_path))
    except SystemExit as exc:  # _fail path
        return exc.code or 1, ""
    return 0, stdout.getvalue()


def _preflight_err(monkeypatch, tmp_path, overrides: dict[str, str],
                   compose_override: dict | None = None) -> str:
    import contextlib
    env = dict(GOOD_ENV)
    env.update(overrides)
    for key, value in list(overrides.items()):
        if value == "":
            env.pop(key, None)
    env_path = tmp_path / "backend.env"
    env_path.write_text("\n".join(f"{k}={v}" for k, v in env.items()) + "\n")
    for key in ("DATABASE_URL", "REDIS_URL", "REPORTING_USER_PASSWORD",
                "MPANGO_DB_ADMIN_URL", "MPANGO_DB_MIGRATE_URL",
                "DATABASE_URL_CONTAINER", "REDIS_URL_CONTAINER"):
        monkeypatch.delenv(key, raising=False)
    compose = compose_override if compose_override is not None else _compose_json()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(compose)))
    err = io.StringIO()
    with contextlib.redirect_stderr(err), pytest.raises(SystemExit):
        pf.run_initial(str(env_path))
    return err.getvalue()


def test_preflight_accepts_conforming_two_role_config(monkeypatch, tmp_path):
    """The admin URL targets the MAINTENANCE database (postgres) while
    migration/runtime URLs target the application database (mpango_erp) —
    the sanctioned maintenance-vs-application shape."""
    code, out = _run_preflight(monkeypatch, tmp_path, {})
    assert code == 0
    assert out.strip() == "OK"


def test_preflight_rejects_backend_service_with_runtime_url_mismatch(monkeypatch, tmp_path):
    compose = _compose_json()
    compose["services"]["backend"]["environment"]["DATABASE_URL"] = \
        "postgresql://mpango_app:app_pw@postgres:5432/other_db"  # pragma: allowlist secret
    err = _preflight_err(monkeypatch, tmp_path, {}, compose)
    assert ("backend service DATABASE_URL does not match the container "
            "runtime context in backend/.env (DATABASE_URL_CONTAINER)") in err


@pytest.mark.parametrize("setup_key", [
    "MPANGO_DB_ADMIN_URL",
    "MPANGO_DB_MIGRATE_URL",
    "MPANGO_DB_MIGRATE_PASSWORD",
    "MPANGO_DB_APP_PASSWORD",
    "REPORTING_USER_PASSWORD",
])
def test_preflight_rejects_every_setup_only_credential_in_backend_service(
    monkeypatch, tmp_path, setup_key,
):
    compose = _compose_json()
    # a minimal backend env: only the offending key, so the BY-KEY refusal is
    # the first failure (the carry checks would otherwise mask it)
    compose["services"]["backend"]["environment"] = {setup_key: "setup_only_value"}
    err = _preflight_err(monkeypatch, tmp_path, {}, compose)
    assert f"backend service environment must not contain {setup_key}" in err


def test_preflight_rejects_backend_service_without_container_runtime_url(monkeypatch, tmp_path):
    compose = _compose_json()
    compose["services"]["backend"]["environment"] = {"MPANGO_ENV": "production"}
    err = _preflight_err(monkeypatch, tmp_path, {}, compose)
    assert "backend service must carry the runtime DATABASE_URL" in err


@pytest.mark.parametrize("container_field,value,fragment", [
    # host/container URL conflation: the container context must never use a
    # loopback host (the backend container cannot reach the host loopback)
    ("DATABASE_URL_CONTAINER", "postgresql://mpango_app:app_pw@127.0.0.1:5432/mpango_erp",
     "must be the Compose service name"),
    ("DATABASE_URL_CONTAINER", "postgresql://mpango_app:app_pw@localhost:5432/mpango_erp",
     "must be the Compose service name"),
    # wrong service host
    ("DATABASE_URL_CONTAINER", "postgresql://mpango_app:app_pw@dbhost:5432/mpango_erp",
     "must be the Compose postgres"),
    # wrong container target port
    ("DATABASE_URL_CONTAINER", "postgresql://mpango_app:app_pw@postgres:5433/mpango_erp",
     "container target port"),
    # cross-database
    ("DATABASE_URL_CONTAINER", "postgresql://mpango_app:app_pw@postgres:5432/other_db",
     "same role, password"),
    # cross-role
    ("DATABASE_URL_CONTAINER", "postgresql://other_role:app_pw@postgres:5432/mpango_erp",
     "same role, password"),
    # cross-password
    ("DATABASE_URL_CONTAINER", "postgresql://mpango_app:other_pw@postgres:5432/mpango_erp",
     "same role, password"),
])
def test_preflight_rejects_container_context_drift(monkeypatch, tmp_path, container_field, value, fragment):
    err = _preflight_err(monkeypatch, tmp_path, {container_field: value})
    assert fragment in err


def test_preflight_rejects_container_redis_drift(monkeypatch, tmp_path):
    err = _preflight_err(monkeypatch, tmp_path, {"REDIS_URL_CONTAINER": "redis://cache:6379/0"})
    assert "REDIS_URL_CONTAINER host must be the Compose redis service" in err


@pytest.mark.parametrize("redis_container", [
    # cross-index: /15 in the container is not the host context's /0 identity
    "redis://redis:6379/15",
    # index-less URL: the logical database index is part of the identity
    "redis://redis:6379",
    # non-numeric index
    "redis://redis:6379/session",
    # query drift
    "redis://redis:6379/0?ssl_cert_reqs=none",
    # fragment drift
    "redis://redis:6379/0#fragment",
])
def test_preflight_rejects_container_redis_index_and_shape_drift(
    monkeypatch, tmp_path, redis_container,
):
    err = _preflight_err(monkeypatch, tmp_path, {"REDIS_URL_CONTAINER": redis_container})
    assert (
        "same logical database index" in err
        or "must include a numeric logical database index" in err
        or "must not carry a query string" in err
        or "must not carry a fragment" in err
    ), err


def test_preflight_rejects_host_redis_index_mismatch(monkeypatch, tmp_path):
    err = _preflight_err(monkeypatch, tmp_path, {"REDIS_URL": "redis://localhost:6379/15"})
    assert "same logical database index" in err


def test_preflight_rejects_backend_service_with_host_loopback_url(monkeypatch, tmp_path):
    """Conflation rejection: a backend DATABASE_URL carrying the HOST-context
    loopback address differs from the container context and is refused."""
    compose = _compose_json()
    compose["services"]["backend"]["environment"]["DATABASE_URL"] = \
        "postgresql://mpango_app:app_pw@localhost:5432/mpango_erp"  # pragma: allowlist secret
    err = _preflight_err(monkeypatch, tmp_path, {}, compose)
    assert ("backend service DATABASE_URL does not match the container "
            "runtime context in backend/.env (DATABASE_URL_CONTAINER)") in err


def test_preflight_rejects_backend_service_with_host_context_redis(monkeypatch, tmp_path):
    compose = _compose_json()
    compose["services"]["backend"]["environment"]["REDIS_URL"] = "redis://localhost:6379/0"
    err = _preflight_err(monkeypatch, tmp_path, {}, compose)
    assert ("backend service REDIS_URL does not match the container "
            "runtime context in backend/.env (REDIS_URL_CONTAINER)") in err


@pytest.mark.parametrize("field,value,fragment", [
    ("MPANGO_DB_ADMIN_URL", "postgresql://postgres:admin_pw@localhost:5432/other_db",
     "MPANGO_DB_ADMIN_URL database does not match Compose POSTGRES_DB"),
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
    err = _preflight_err(monkeypatch, tmp_path, {field: value})
    assert fragment in err


def test_preflight_rejects_runtime_naming_compose_admin(monkeypatch, tmp_path):
    err = _preflight_err(monkeypatch, tmp_path, {
        "DATABASE_URL": "postgresql://postgres:app_pw@localhost:5432/mpango_erp",
    })
    # the runtime URL naming the admin role is, before anything else, a
    # single-role configuration (runtime must be a distinct third role)
    assert "single-role configuration rejected" in err


def test_preflight_rejects_missing_admin_url(monkeypatch, tmp_path):
    err = _preflight_err(monkeypatch, tmp_path, {"MPANGO_DB_ADMIN_URL": ""})
    assert "MPANGO_DB_ADMIN_URL not found in backend/.env" in err


def test_preflight_rejects_app_password_mismatch(monkeypatch, tmp_path):
    err = _preflight_err(monkeypatch, tmp_path, {"MPANGO_DB_APP_PASSWORD": "wrong"})
    assert "MPANGO_DB_APP_PASSWORD does not match" in err


def test_preflight_rejects_migrate_password_mismatch(monkeypatch, tmp_path):
    err = _preflight_err(monkeypatch, tmp_path, {"MPANGO_DB_MIGRATE_PASSWORD": "wrong"})
    assert "MPANGO_DB_MIGRATE_PASSWORD does not match" in err


# ---------------------------------------------------------------------------
# 3. ownership contract + two-role lifecycle (opt-in, disposable databases)
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


class _SandboxServer:
    """Borrows the test server behind TEST_DATABASE_URL for ownership
    scenarios: unique databases/roles per scenario with guaranteed cleanup."""

    def __init__(self):
        self.source = os.environ["TEST_DATABASE_URL"]
        self.parsed = urlsplit(self.source)
        self.admin_url = self.parsed._replace(path="/postgres").geturl()
        self.admin_role = self.parsed.username or "postgres"
        self._conn = None

    def conn(self):
        if self._conn is None:
            self._conn = _admin_connect(self.admin_url)
        return self._conn

    def url_for(self, db: str, user: str = "", password: str = ""):
        netloc = f"{self.parsed.hostname}:{self.parsed.port or 5432}"
        if user:
            netloc = f"{user}:{password}@{netloc}"
        return self.parsed._replace(netloc=netloc, path=f"/{db}").geturl()

    def admin_db_url(self, db: str):
        """A URL to the given database carrying the test administrator's
        credentials (from TEST_DATABASE_URL)."""
        return self.parsed._replace(path=f"/{db}").geturl()

    def sql(self, statement: str, db: str | None = None):
        conn = self.conn()
        with conn.cursor() as cur:
            cur.execute(statement)

    def db_exists(self, db: str) -> bool:
        with self.conn().cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,))
            return cur.fetchone() is not None

    def db_owner(self, db: str) -> str:
        with self.conn().cursor() as cur:
            cur.execute("SELECT pg_get_userbyid(datdba) FROM pg_database "
                        "WHERE datname = %s", (db,))
            return cur.fetchone()[0]

    def role_exists(self, role: str) -> bool:
        with self.conn().cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
            return cur.fetchone() is not None

    def drop_db(self, db: str):
        c = self.conn()
        with c.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()", (db,))
            cur.execute(f'DROP DATABASE IF EXISTS "{db}"')

    def drop_role(self, role: str):
        with self.conn().cursor() as cur:
            cur.execute(f'DROP ROLE IF EXISTS "{role}"')


def _scenario_env(server: _SandboxServer, db: str, mig_role: str, app_role: str,
                  mig_pw: str, app_pw: str) -> dict:
    return {
        "MPANGO_DB_ADMIN_URL": server.admin_url,
        "MPANGO_DB_MIGRATE_URL": server.url_for(db, mig_role, mig_pw),
        "MPANGO_DB_APP_URL": server.url_for(db, app_role, app_pw),
        "MPANGO_DB_MIGRATE_ROLE": mig_role,
        "MPANGO_DB_APP_ROLE": app_role,
        "MPANGO_DB_MIGRATE_PASSWORD": mig_pw,
        "MPANGO_DB_APP_PASSWORD": app_pw,
    }


@_requires_temp_db
def test_provisioner_creates_absent_database_owned_by_migrate():
    server = _SandboxServer()
    suffix = uuid.uuid4().hex[:8]
    db = f"test_own_absent_{suffix}"
    mig_role, app_role = f"mpango_migrate_{suffix}", f"mpango_app_{suffix}"
    env = _scenario_env(server, db, mig_role, app_role,
                        f"pw_{suffix}_m", f"pw_{suffix}_a")
    try:
        assert not server.db_exists(db)
        result = _run_provisioner(["--provision"], env)
        assert result.returncode == 0, result.stderr
        assert server.db_exists(db)
        assert server.db_owner(db) == mig_role
    finally:
        server.drop_db(db)
        server.drop_role(app_role)
        server.drop_role(mig_role)


@_requires_temp_db
def test_provisioner_accepts_existing_correct_owner_idempotently():
    server = _SandboxServer()
    suffix = uuid.uuid4().hex[:8]
    db = f"test_own_correct_{suffix}"
    mig_role, app_role = f"mpango_migrate_{suffix}", f"mpango_app_{suffix}"
    mig_pw, app_pw = f"pw_{suffix}_m", f"pw_{suffix}_a"
    env = _scenario_env(server, db, mig_role, app_role, mig_pw, app_pw)
    try:
        # pre-create roles and an existing database ALREADY owned by the
        # migration authority (operator-established deployment)
        server.sql(f'CREATE ROLE "{mig_role}" LOGIN PASSWORD \'{mig_pw}\' '
                   "NOSUPERUSER NOCREATEDB CREATEROLE NOINHERIT NOREPLICATION")
        server.sql(f'CREATE ROLE "{app_role}" LOGIN PASSWORD \'{app_pw}\' '
                   "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION")
        server.sql(f'CREATE DATABASE "{db}" OWNER "{mig_role}"')
        result = _run_provisioner(["--provision"], env)
        assert result.returncode == 0, result.stderr
        assert "already exists" in result.stdout
        assert "owned by the migration authority" in result.stdout
        assert server.db_owner(db) == mig_role
    finally:
        server.drop_db(db)
        server.drop_role(app_role)
        server.drop_role(mig_role)


@_requires_temp_db
def test_provisioner_refuses_wrong_owner_empty_database_zero_writes():
    server = _SandboxServer()
    suffix = uuid.uuid4().hex[:8]
    db = f"test_own_wrong_{suffix}"
    mig_role, app_role = f"mpango_migrate_{suffix}", f"mpango_app_{suffix}"
    env = _scenario_env(server, db, mig_role, app_role,
                        f"pw_{suffix}_m", f"pw_{suffix}_a")
    try:
        # compose-style container init: the database exists, owned by the
        # container administrator; the roles do not exist
        server.sql(f'CREATE DATABASE "{db}"')
        owner0 = server.db_owner(db)
        result = _run_provisioner(["--provision"], env)
        assert result.returncode != 0
        assert "zero writes performed" in result.stderr
        # zero writes proven: no roles created, owner untouched
        assert not server.role_exists(mig_role)
        assert not server.role_exists(app_role)
        assert server.db_owner(db) == owner0
    finally:
        server.drop_db(db)


@_requires_temp_db
def test_provisioner_refuses_wrong_owner_database_with_sentinel_data():
    server = _SandboxServer()
    suffix = uuid.uuid4().hex[:8]
    db = f"test_own_sentinel_{suffix}"
    mig_role, app_role = f"mpango_migrate_{suffix}", f"mpango_app_{suffix}"
    env = _scenario_env(server, db, mig_role, app_role,
                        f"pw_{suffix}_m", f"pw_{suffix}_a")
    try:
        server.sql(f'CREATE DATABASE "{db}"')
        sentinel_conn = _admin_connect(server.admin_db_url(db))
        with sentinel_conn.cursor() as cur:
            cur.execute("CREATE SCHEMA business")
            cur.execute("CREATE TABLE business.ledger (id int primary key, "
                        "amount numeric)")
            cur.execute("INSERT INTO business.ledger VALUES (1, 42.00)")
        sentinel_conn.close()
        owner0 = server.db_owner(db)
        result = _run_provisioner(["--provision"], env)
        assert result.returncode != 0
        assert "zero writes performed" in result.stderr
        # the database remains byte/semantically unchanged
        assert server.db_owner(db) == owner0
        assert not server.role_exists(mig_role)
        assert not server.role_exists(app_role)
        probe = _admin_connect(server.admin_db_url(db))
        with probe.cursor() as cur:
            cur.execute("SELECT amount FROM business.ledger WHERE id = 1")
            assert cur.fetchone()[0] == 42.00
        probe.close()
    finally:
        server.drop_db(db)


@_requires_temp_db
def test_provisioner_refuses_connectable_roles_wrong_owner_before_writes():
    """Fully connectable migrate/app roles against an existing wrong-owner
    database: the live binding succeeds, then the ownership gate refuses
    BEFORE any role/owner/grant write."""
    server = _SandboxServer()
    suffix = uuid.uuid4().hex[:8]
    db = f"test_own_live_{suffix}"
    mig_role, app_role = f"mpango_migrate_{suffix}", f"mpango_app_{suffix}"
    mig_pw, app_pw = f"pw_{suffix}_m", f"pw_{suffix}_a"
    env = _scenario_env(server, db, mig_role, app_role, mig_pw, app_pw)
    try:
        server.sql(f'CREATE ROLE "{mig_role}" LOGIN PASSWORD \'{mig_pw}\' '
                   "NOSUPERUSER NOCREATEDB CREATEROLE NOINHERIT NOREPLICATION")
        server.sql(f'CREATE ROLE "{app_role}" LOGIN PASSWORD \'{app_pw}\' '
                   "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION")
        server.sql(f'CREATE DATABASE "{db}"')  # owned by the admin (wrong)
        owner0 = server.db_owner(db)
        result = _run_provisioner(["--provision"], env)
        assert result.returncode != 0
        assert "provisioning refused with zero writes" in result.stderr
        assert "never adopts or re-owns" in result.stderr
        assert server.db_owner(db) == owner0
        # grants were not applied either (phase 3 untouched)
        grants = _run_provisioner(["--apply-grants"], env)
        assert grants.returncode != 0
    finally:
        server.drop_db(db)
        server.drop_role(app_role)
        server.drop_role(mig_role)


@_requires_temp_db
def test_two_role_lifecycle_and_public_contract_refusals():
    import psycopg2

    bts = _load_module("combined_contract_bts", BOOTSTRAP)
    server = _SandboxServer()
    suffix = uuid.uuid4().hex[:8]
    mig_role = f"mpango_migrate_{suffix}"
    app_role = f"mpango_app_{suffix}"
    mig_pw = f"pw_{suffix}_m"
    app_pw = f"pw_{suffix}_a"
    sandbox_db = f"test_combinedauth_{suffix}"
    tenant = f"t_{uuid.uuid4().hex}"

    def _url(user: str, password: str) -> str:
        return server.url_for(db=sandbox_db, user=user, password=password)

    mig_url = _url(mig_role, mig_pw)
    app_url = _url(app_role, app_pw)
    prov_env = {
        "MPANGO_DB_ADMIN_URL": server.admin_url,
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
        # Cluster-global role accommodation (test-env only): reporting_role /
        # reporting_user live cluster-wide.  On a genuinely fresh cluster the
        # sandbox migration authority creates them itself (and holds ADMIN);
        # when another migration authority's run on this cluster created them
        # first, confer ADMIN to the sandbox authority so migration 011 can
        # ALTER/GRANT them.  No product objects are touched.
        admin_conn0 = _admin_connect(server.admin_url)
        try:
            with admin_conn0.cursor() as cur:
                for role in ("reporting_role", "reporting_user"):
                    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
                    if cur.fetchone():
                        cur.execute(f"GRANT {role} TO {mig_role} WITH ADMIN OPTION")
        finally:
            admin_conn0.close()
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

        cluster_admin = _admin_connect(server.admin_url)
        # schema-level objects (guard function, public constraints, tenant
        # schemas, alembic_version) live in the sandbox database — inspect
        # them through a connection TO the sandbox, not the maintenance db
        sandbox_admin_url = server.admin_db_url(sandbox_db)
        admin = _admin_connect(sandbox_admin_url)
        try:
            with cluster_admin.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (sandbox_db,))
                assert cur.fetchone() is not None
                cur.execute("SELECT pg_get_userbyid(datdba) FROM pg_database "
                            "WHERE datname = %s", (sandbox_db,))
                assert cur.fetchone()[0] == mig_role, \
                    "product provision must own the fresh database by the migration authority"
            admin_role = server.admin_role

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
            cluster_admin.close()
    finally:
        # cleanup: drop the product-created database and roles
        try:
            cluster_admin = _admin_connect(server.admin_url)
            try:
                with cluster_admin.cursor() as cur:
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()", (sandbox_db,))
                    cur.execute(f'DROP DATABASE IF EXISTS "{sandbox_db}"')
                    cur.execute(f'DROP ROLE IF EXISTS "{app_role}"')
                    cur.execute(f'DROP ROLE IF EXISTS "{mig_role}"')
            finally:
                cluster_admin.close()
        except Exception:
            pass


def test_preflight_accepts_exact_public_frontend_url_and_still_bans_setup_only(
    monkeypatch, tmp_path,
):
    """R1-R6: the rendered backend environment carries the EXACT authoritative
    PUBLIC_FRONTEND_URL value and the five setup-only credentials remain
    forbidden by key even when the runtime input is otherwise conforming."""
    code, out = _run_preflight(monkeypatch, tmp_path, {})
    assert code == 0
    assert out.strip() == "OK"
    base = _compose_json()
    bad_env = dict(base["services"]["backend"]["environment"])
    bad_env["MPANGO_DB_ADMIN_URL"] = GOOD_ENV["MPANGO_DB_ADMIN_URL"]
    override = {"services": {
        "postgres": base["services"]["postgres"],
        "redis": base["services"]["redis"],
        "backend": {"environment": bad_env},
    }}
    err = _preflight_err(monkeypatch, tmp_path, {}, override)
    assert "backend service environment must not contain MPANGO_DB_ADMIN_URL" in err


# ---------------------------------------------------------------------------
# R1-R7: explicit reporting runtime DSN contract
# ---------------------------------------------------------------------------
def _rsm():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "r1r7_reporting_session",
        BACKEND_DIR / "database" / "reporting_session.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    saved = os.environ.get("REPORTING_DATABASE_URL")
    os.environ["REPORTING_DATABASE_URL"] = (
        "postgresql://" + "reporting_user:" + "rup_pw@postgres:5432/mpango_erp")
    try:
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            os.environ.pop("REPORTING_DATABASE_URL", None)
        else:
            os.environ["REPORTING_DATABASE_URL"] = saved
    return module


def test_reporting_session_requires_explicit_dsn(monkeypatch):
    """R1-R7: the DATABASE_URL + REPORTING_USER_PASSWORD fallback is gone;
    there is no localhost fallback either."""
    monkeypatch.delenv("REPORTING_DATABASE_URL", raising=False)
    rsm = _rsm()
    with pytest.raises(RuntimeError) as exc:
        rsm._build_reporting_url()
    message = str(exc.value)
    assert "REPORTING_DATABASE_URL environment variable must be set" in message
    assert "localhost" not in message


def test_reporting_session_normalizes_driver_exactly_once(monkeypatch):
    url = "postgresql://" + "reporting_user:" + "rup_pw@postgres:5432/mpango_erp"
    monkeypatch.setenv("REPORTING_DATABASE_URL", url)
    rsm = _rsm()
    built = rsm._build_reporting_url()
    assert built == ("postgresql+asyncpg://" + "reporting_user:"
                     + "rup_pw@postgres:5432/mpango_erp")
    assert built.count("asyncpg") == 1


def test_reporting_session_preserves_pre_suffixed_async_url(monkeypatch):
    url = "postgresql+asyncpg://" + "reporting_user:" + "rup_pw@postgres:5432/mpango_erp"
    monkeypatch.setenv("REPORTING_DATABASE_URL", url)
    rsm = _rsm()
    assert rsm._build_reporting_url() == url
    assert url.count("asyncpg") == 1


def test_reporting_session_rejects_wrong_user(monkeypatch):
    monkeypatch.setenv("REPORTING_DATABASE_URL",
                       "postgresql://" + "someone:pw@postgres:5432/mpango_erp")
    rsm = _rsm()
    with pytest.raises(RuntimeError) as exc:
        rsm._build_reporting_url()
    assert "reporting DSN must bind the reporting_user identity" in str(exc.value)


def test_reporting_session_rejects_fragment(monkeypatch):
    monkeypatch.setenv("REPORTING_DATABASE_URL",
                       "postgresql://" + "reporting_user:rup_pw@postgres:5432/mpango_erp#f")
    rsm = _rsm()
    with pytest.raises(RuntimeError) as exc:
        rsm._build_reporting_url()
    assert "reporting DSN must not contain a fragment" in str(exc.value)


def test_reporting_session_rejects_missing_password(monkeypatch):
    monkeypatch.setenv("REPORTING_DATABASE_URL",
                       "postgresql://" + "reporting_user@postgres:5432/mpango_erp")
    rsm = _rsm()
    with pytest.raises(RuntimeError) as exc:
        rsm._build_reporting_url()
    assert "reporting DSN must include a password" in str(exc.value)


def test_reporting_session_diagnostics_never_leak(monkeypatch):
    secret = "sup3r_s3cret_reporting_pw"
    monkeypatch.setenv("REPORTING_DATABASE_URL",
                       "mysql://" + "reporting_user:" + secret + "@postgres:5432/mpango_erp")
    rsm = _rsm()
    with pytest.raises(RuntimeError) as exc:
        rsm._build_reporting_url()
    assert secret not in str(exc.value)


def test_preflight_accepts_conforming_reporting_runtime_url(monkeypatch, tmp_path):
    code, out = _run_preflight(monkeypatch, tmp_path, {})
    assert code == 0
    assert out.strip() == "OK"


def test_preflight_rejects_missing_reporting_container_url(monkeypatch, tmp_path):
    err = _preflight_err(monkeypatch, tmp_path,
                         {"REPORTING_DATABASE_URL_CONTAINER": ""})
    assert err == "REPORTING_DATABASE_URL_CONTAINER not found in backend/.env"


def test_preflight_rejects_wrong_reporting_scheme(monkeypatch, tmp_path):
    err = _preflight_err(monkeypatch, tmp_path,
                         {"REPORTING_DATABASE_URL_CONTAINER":
                          "mysql://" + "reporting_user:rup_pw@postgres:5432/mpango_erp"})
    assert err == "REPORTING_DATABASE_URL_CONTAINER scheme is not postgresql"


def test_preflight_rejects_wrong_reporting_host(monkeypatch, tmp_path):
    err = _preflight_err(monkeypatch, tmp_path,
                         {"REPORTING_DATABASE_URL_CONTAINER":
                          "postgresql://" + "reporting_user:rup_pw@localhost:5432/mpango_erp"})
    assert err == ("REPORTING_DATABASE_URL_CONTAINER host must be the Compose "
                   "postgres service")


def test_preflight_rejects_wrong_reporting_port(monkeypatch, tmp_path):
    err = _preflight_err(monkeypatch, tmp_path,
                         {"REPORTING_DATABASE_URL_CONTAINER":
                          "postgresql://" + "reporting_user:rup_pw@postgres:5433/mpango_erp"})
    assert err == ("REPORTING_DATABASE_URL_CONTAINER port must be the postgres "
                   "container target port")


def test_preflight_rejects_wrong_reporting_user(monkeypatch, tmp_path):
    err = _preflight_err(monkeypatch, tmp_path,
                         {"REPORTING_DATABASE_URL_CONTAINER":
                          "postgresql://" + "someone:rup_pw@postgres:5432/mpango_erp"})
    assert err == ("REPORTING_DATABASE_URL_CONTAINER must bind the "
                   "reporting_user identity")


def test_preflight_rejects_wrong_reporting_database(monkeypatch, tmp_path):
    err = _preflight_err(monkeypatch, tmp_path,
                         {"REPORTING_DATABASE_URL_CONTAINER":
                          "postgresql://" + "reporting_user:rup_pw@postgres:5432/otherdb"})
    assert err == ("REPORTING_DATABASE_URL_CONTAINER must target the "
                   "application database")


def test_preflight_rejects_reporting_fragment(monkeypatch, tmp_path):
    err = _preflight_err(monkeypatch, tmp_path,
                         {"REPORTING_DATABASE_URL_CONTAINER":
                          "postgresql://" + "reporting_user:rup_pw@postgres:5432/mpango_erp#f"})
    assert err == ("REPORTING_DATABASE_URL_CONTAINER must not contain a "
                   "fragment")


def test_preflight_rejects_reporting_query(monkeypatch, tmp_path):
    err = _preflight_err(monkeypatch, tmp_path,
                         {"REPORTING_DATABASE_URL_CONTAINER":
                          "postgresql://" + "reporting_user:rup_pw@postgres:5432/mpango_erp?x=1"})
    assert err == ("REPORTING_DATABASE_URL_CONTAINER must not contain a "
                   "query string")


def test_preflight_rejects_reporting_password_drift(monkeypatch, tmp_path):
    err = _preflight_err(monkeypatch, tmp_path,
                         {"REPORTING_DATABASE_URL_CONTAINER":
                          "postgresql://" + "reporting_user:other_pw@postgres:5432/mpango_erp"})
    assert err == ("REPORTING_DATABASE_URL_CONTAINER password does not match "
                   "REPORTING_USER_PASSWORD")


def test_preflight_accepts_percent_encoded_reporting_password(monkeypatch, tmp_path):
    """A percent-encoded '@' inside the reporting password decodes to the same
    value as REPORTING_USER_PASSWORD and is accepted (literal '+' stays
    literal: unquote does not space-decode)."""
    content = dict(GOOD_ENV)
    content["REPORTING_USER_PASSWORD"] = "r@pt+1"
    content["REPORTING_DATABASE_URL_CONTAINER"] = (
        "postgresql://" + "reporting_user:r%40pt%2B1@postgres:5432/mpango_erp")
    env_path = tmp_path / "backend.env"
    env_path.write_text("\n".join(f"{k}={v}" for k, v in content.items()) + "\n",
                        encoding="utf-8")
    for key in ("DATABASE_URL", "REDIS_URL", "REPORTING_USER_PASSWORD",
                "MPANGO_DB_ADMIN_URL", "MPANGO_DB_MIGRATE_URL",
                "DATABASE_URL_CONTAINER", "REDIS_URL_CONTAINER"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_compose_json())))
    import contextlib
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        pf.run_initial(str(env_path))
    assert stdout.getvalue().strip() == "OK"


def test_preflight_rejects_rendered_reporting_missing(monkeypatch, tmp_path):
    base = _compose_json()
    backend = dict(base["services"]["backend"]["environment"])
    del backend["REPORTING_DATABASE_URL"]
    base["services"]["backend"]["environment"] = backend
    err = _preflight_err(monkeypatch, tmp_path, {}, base)
    assert err == "backend service environment must carry REPORTING_DATABASE_URL"


def test_preflight_rejects_rendered_reporting_non_string(monkeypatch, tmp_path):
    base = _compose_json()
    backend = dict(base["services"]["backend"]["environment"])
    backend["REPORTING_DATABASE_URL"] = 3
    base["services"]["backend"]["environment"] = backend
    err = _preflight_err(monkeypatch, tmp_path, {}, base)
    assert err == "backend service REPORTING_DATABASE_URL must be a string"


def test_preflight_rejects_rendered_reporting_mismatch(monkeypatch, tmp_path):
    base = _compose_json()
    backend = dict(base["services"]["backend"]["environment"])
    backend["REPORTING_DATABASE_URL"] = (
        "postgresql://" + "reporting_user:rup_pw@postgres:5432/otherdb")
    base["services"]["backend"]["environment"] = backend
    err = _preflight_err(monkeypatch, tmp_path, {}, base)
    assert err == ("backend service REPORTING_DATABASE_URL does not match "
                   "backend/.env (REPORTING_DATABASE_URL_CONTAINER)")
