"""Runtime readiness-gate contract tests
(CTO-AUTH-ORDER-R2-DB-AUTHORITY-INTEGRATION-R1-R3-TOPOLOGY-AND-READINESS-CLOSURE-2026-09-19).

The backend entrypoint's readiness gate must refuse a database that has
mere connectivity but has not completed the five-stage setup (wrong/absent
migration head, missing tenant bootstrap state, broken guard/public
contracts), and must accept the completed five-stage state.  The gate is
executed EXACTLY as the entrypoint runs it: the python heredoc is extracted
from the committed docker-entrypoint.sh and piped to `python -` with only
DATABASE_URL (and DEFAULT_TENANT_SCHEMA) set.

Opt-in (MPANGO_ALLOW_TEMP_DB_CREATE=1): the scenarios run against
disposable databases on the test server; nothing here is formal
acceptance evidence.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid

import pytest

from tests.test_combined_setup_authority_contract import (
    BACKEND_DIR,
    _SandboxServer,
    _admin_connect,
    _requires_temp_db,
    _run_provisioner,
    _scenario_env,
)

ENTRYPOINT = BACKEND_DIR / "docker-entrypoint.sh"


def _gate_source() -> str:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    match = re.search(r"python - <<'PY'\n(.*?)\nPY", text, re.DOTALL)
    assert match is not None, "entrypoint readiness gate not found"
    return match.group(1)


def _run_gate(database_url: str, tenant: str = "t_dev") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-"],
        input=_gate_source(),
        env={**os.environ,
             "DATABASE_URL": database_url,
             "DEFAULT_TENANT_SCHEMA": tenant,
             "MPANGO_ENV": "test"},
        capture_output=True, text=True, timeout=300, cwd=str(BACKEND_DIR),
    )


@pytest.fixture(scope="module")
def five_stage_database():
    """A disposable database that has completed the product five-stage
    sequence: provision -> alembic 001..039 -> grants -> verify -> runtime
    bootstrap of the default tenant."""
    server = _SandboxServer()
    suffix = uuid.uuid4().hex[:8]
    mig_role, app_role = f"mpango_migrate_{suffix}", f"mpango_app_{suffix}"
    mig_pw, app_pw = f"pw_{suffix}_m", f"pw_{suffix}_a"
    sandbox_db = f"test_readiness_{suffix}"
    env = _scenario_env(server, sandbox_db, mig_role, app_role, mig_pw, app_pw)
    result = _run_provisioner(["--provision"], env)
    assert result.returncode == 0, result.stderr
    mig_url = server.url_for(db=sandbox_db, user=mig_role, password=mig_pw)
    app_url = server.url_for(db=sandbox_db, user=app_role, password=app_pw)
    # cluster-global role accommodation (test-env only; documented in the
    # combined-contract suite)
    conn = server.conn()
    with conn.cursor() as cur:
        for role in ("reporting_role", "reporting_user"):
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
            if cur.fetchone():
                cur.execute(f"GRANT {role} TO {mig_role} WITH ADMIN OPTION")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=600,
        env={**os.environ, "DATABASE_URL": mig_url,
             "REPORTING_USER_PASSWORD": f"rup_{suffix}", "MPANGO_ENV": "test"})
    assert result.returncode == 0, result.stderr[-2000:]
    result = _run_provisioner(["--apply-grants"], env)
    assert result.returncode == 0, result.stderr
    result = _run_provisioner(["--verify"], env)
    assert result.returncode == 0, result.stderr
    # phase 5: runtime bootstrap of the default tenant
    result = subprocess.run(
        [sys.executable, "scripts/bootstrap_tenant_schema.py", "t_dev"],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=300,
        env={**os.environ, "DATABASE_URL": app_url, "MPANGO_ENV": "test",
             "SECRET_KEY": "gate_fixture_secret_key_value"})
    assert result.returncode == 0, result.stderr[-2000:]
    yield {"app_url": app_url, "mig_url": mig_url, "db": sandbox_db,
           "server": server}
    try:
        server.drop_db(sandbox_db)
        server.drop_role(app_role)
        server.drop_role(mig_role)
    except Exception:
        pass


@_requires_temp_db
def test_gate_refuses_database_without_completed_setup():
    """Mere connectivity is not readiness: a database with no migration
    history, or at the wrong migration head, is refused by the committed
    gate with a named reason and a non-zero exit."""
    server = _SandboxServer()
    suffix = uuid.uuid4().hex[:8]
    db = f"test_readiness_empty_{suffix}"
    try:
        server.sql(f'CREATE DATABASE "{db}"')
        # (a) database exists, nothing provisioned: alembic_version missing
        result = _run_gate(server.admin_db_url(db))
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "REFUSED" in combined or "not ready" in combined
        assert "Starting Uvicorn" not in combined

        # (b) wrong head: create the version table at a wrong revision
        # (connected TO the target database — cross-database DDL is impossible)
        probe = _admin_connect(server.admin_db_url(db))
        try:
            with probe.cursor() as cur:
                cur.execute("CREATE TABLE public.alembic_version "
                            "(version_num VARCHAR(128) NOT NULL)")
                cur.execute("INSERT INTO public.alembic_version VALUES "
                            "('038_catalog_identity_vertical_slice')")
        finally:
            probe.close()
        result = _run_gate(server.admin_db_url(db))
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "requires exactly '039_order_credit_holds'" in combined
        assert "Starting Uvicorn" not in combined
    finally:
        server.drop_db(db)


@_requires_temp_db
def test_gate_accepts_completed_five_stage_state(five_stage_database):
    app_url = five_stage_database["app_url"]
    result = _run_gate(app_url)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "five-stage setup contract verified" in result.stdout
    assert "Starting Uvicorn" not in result.stdout  # the gate is not the runtime


@_requires_temp_db
def test_gate_refuses_missing_tenant_bootstrap_state(five_stage_database):
    """The completed-migrations database without the default tenant
    bootstrap (phase 5) is still not ready — the gate names the missing
    tenant state."""
    from tests.test_combined_setup_authority_contract import _admin_connect
    server = five_stage_database["server"]
    db = five_stage_database["db"]
    admin = _admin_connect(server.admin_db_url(db))
    try:
        with admin.cursor() as cur:
            cur.execute('DROP TABLE IF EXISTS "t_dev".order_credit_holds')
    finally:
        admin.close()
    result = _run_gate(five_stage_database["app_url"])
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "default tenant bootstrap state missing" in combined
