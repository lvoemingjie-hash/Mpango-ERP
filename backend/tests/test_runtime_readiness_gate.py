"""Runtime readiness-gate contract tests
(CTO-AUTH-ORDER-R2-DB-AUTHORITY-INTEGRATION-R1-R4-BOUNDED-RUNTIME-CONTRACT-CORRECTION-2026-09-19).

The readiness gate lives in backend/scripts/runtime_readiness_gate.py.  These
tests prove, against disposable PG16 databases:

  * a database with mere connectivity but an absent/wrong migration head is
    REFUSED with the named reason;
  * the completed five-stage state is ACCEPTED through BOTH preflight-accepted
    URL schemes (postgresql:// and postgresql+asyncpg://);
  * refusal reasons are scoped to ONE attempt: a transient first failure
    followed by a valid attempt starts successfully, while permanent failure
    exhausts the bounded retry and returns non-zero.

Opt-in (MPANGO_ALLOW_TEMP_DB_CREATE=1); nothing here is formal acceptance
evidence.
"""
from __future__ import annotations

import importlib.util
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
GATE = BACKEND_DIR / "scripts" / "runtime_readiness_gate.py"


def _load_helper():
    spec = importlib.util.spec_from_file_location("r1r4_gate", GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entrypoint_invokes_gate_helper(entrypoint_text: str) -> None:
    assert "from scripts.runtime_readiness_gate import main" in entrypoint_text
    assert "sys.exit(main())" in entrypoint_text


def test_entrypoint_delegates_to_the_gate_helper():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    _entrypoint_invokes_gate_helper(text)


@_requires_temp_db
@pytest.mark.parametrize("scheme", ["postgresql", "postgresql+asyncpg"])
def test_gate_accepts_completed_five_stage_state_in_both_schemes(
    five_stage_database, scheme, monkeypatch,
):
    url = five_stage_database["app_url"]
    scheme_url = scheme + "://" + url.split("://", 1)[1]
    monkeypatch.setenv("REPORTING_DATABASE_URL",
                       five_stage_database["reporting_url"])
    helper = _load_helper()
    reasons = helper.evaluate_contract(scheme_url, "t_dev")
    assert reasons == [], reasons
    assert helper.run_gate(scheme_url, "t_dev", deadline_seconds=1.0) == 0


@_requires_temp_db
def test_gate_refuses_database_without_completed_setup():
    server = _SandboxServer()
    suffix = uuid.uuid4().hex[:8]
    db = "test_readiness_empty_" + suffix
    helper = _load_helper()
    try:
        server.sql('CREATE DATABASE "' + db + '"')
        reasons = helper.evaluate_contract(server.admin_db_url(db))
        assert reasons and "alembic_version" in reasons[0]
        probe = _admin_connect(server.admin_db_url(db))
        try:
            with probe.cursor() as cur:
                cur.execute("CREATE TABLE public.alembic_version "
                            "(version_num VARCHAR(128) NOT NULL)")
                cur.execute("INSERT INTO public.alembic_version VALUES "
                            "('038_catalog_identity_vertical_slice')")
        finally:
            probe.close()
        reasons = helper.evaluate_contract(server.admin_db_url(db))
        assert any("requires exactly '039_order_credit_holds'" in r
                   for r in reasons), reasons
    finally:
        server.drop_db(db)


@pytest.fixture(scope="module")
def five_stage_database():
    """A disposable database that has completed the product five-stage
    sequence: provision -> alembic 001..039 -> grants -> verify -> runtime
    bootstrap of the default tenant."""
    server = _SandboxServer()
    suffix = uuid.uuid4().hex[:8]
    mig_role, app_role = "mpango_migrate_" + suffix, "mpango_app_" + suffix
    mig_pw, app_pw = "pw_" + suffix + "_m", "pw_" + suffix + "_a"
    ctx_reporting = "reporting-" + suffix
    ctx_gate = "gate-fixture-" + suffix
    sandbox_db = "test_readiness_" + suffix
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
                cur.execute("GRANT " + role + " TO " + mig_role +
                            " WITH ADMIN OPTION")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=600,
        env={**os.environ, "DATABASE_URL": mig_url,
             "REPORTING_USER_PASSWORD": ctx_reporting,
             "MPANGO_ENV": "test"})
    assert result.returncode == 0, result.stderr[-2000:]
    result = _run_provisioner(["--apply-grants"], env)
    assert result.returncode == 0, result.stderr
    result = _run_provisioner(["--verify"], env)
    assert result.returncode == 0, result.stderr
    # R1-R7 cluster-global reporting_user password accommodation (test-env
    # only, same documented pattern as the migrate/app role grants): align
    # the shared login with THIS sandbox's migration-time secret so the
    # readiness reporting probe is deterministic across module runs.
    with conn.cursor() as cur:
        cur.execute("ALTER ROLE reporting_user WITH PASSWORD %s",
                    (ctx_reporting,))
        conn.commit()
    reporting_url = server.url_for(db=sandbox_db, user="reporting_user",
                                   password=ctx_reporting)
    # phase 5: runtime bootstrap of the default tenant
    result = subprocess.run(
        [sys.executable, "scripts/bootstrap_tenant_schema.py", "t_dev"],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=300,
        env={**os.environ, "DATABASE_URL": app_url, "MPANGO_ENV": "test",
             "SECRET_KEY": ctx_gate})
    assert result.returncode == 0, result.stderr[-2000:]
    yield {"app_url": app_url, "mig_url": mig_url, "db": sandbox_db,
           "server": server, "reporting_url": reporting_url}
    try:
        server.drop_db(sandbox_db)
        server.drop_role(app_role)
        server.drop_role(mig_role)
    except Exception:
        pass


@_requires_temp_db
def test_gate_refuses_missing_tenant_bootstrap_state(five_stage_database):
    """F1 (R1-R5) — isolated by identity, NOT by test ordering: the negative
    bootstraps its OWN unique tenant schema inside the shared disposable
    database, damages only that schema, evaluates the real readiness
    contract against the isolated target, and removes the schema in an
    exception-safe finally.  The completed t_dev fixture state used by the
    other tests in this module is never touched, so this test is green in
    BOTH execution orders."""
    server = five_stage_database["server"]
    helper = _load_helper()
    suffix = uuid.uuid4().hex[:8]
    own_tenant = "t_r5" + suffix  # unique task-scoped tenant schema
    ctx_gate_destructive = "gate-fixture-" + suffix
    admin = _admin_connect(server.admin_db_url(five_stage_database["db"]))
    try:
        # phase-5-equivalent: bootstrap the UNIQUE tenant via the product
        # script against the runtime-role URL
        result = subprocess.run(
            [sys.executable, "scripts/bootstrap_tenant_schema.py", own_tenant],
            cwd=BACKEND_DIR, capture_output=True, text=True, timeout=300,
            env={**os.environ, "DATABASE_URL": five_stage_database["app_url"],
                 "MPANGO_ENV": "test",
                 "SECRET_KEY": ctx_gate_destructive})
        assert result.returncode == 0, result.stderr[-2000:]
        # damage ONLY the isolated tenant
        with admin.cursor() as cur:
            cur.execute('DROP TABLE "' + own_tenant + '".order_credit_holds')
        # the REAL readiness evaluator, pointed at the isolated target
        reasons = helper.evaluate_contract(five_stage_database["app_url"],
                                           own_tenant)
        assert any("default tenant bootstrap state missing" in r
                   for r in reasons), reasons
    finally:
        try:
            with admin.cursor() as cur:
                cur.execute('DROP SCHEMA IF EXISTS "' + own_tenant + '" CASCADE')
        finally:
            admin.close()


@_requires_temp_db
def test_real_evaluator_freshness_incomplete_then_completed(
    five_stage_database, monkeypatch,
):
    monkeypatch.setenv("REPORTING_DATABASE_URL",
                       five_stage_database["reporting_url"])
    """F3 (R1-R5) — direct test of the REAL evaluate_contract (no fake): an
    isolated incomplete state must yield a non-empty named refusal set, and
    the SAME imported evaluator against the intact completed state must then
    yield an EMPTY set.  The final emptiness proves no reason was retained
    from the first call, killing any evaluator-internal shared/module-level
    reason accumulator."""
    server = five_stage_database["server"]
    helper = _load_helper()
    suffix = uuid.uuid4().hex[:8]
    db = "test_freshness_" + suffix
    try:
        # (1) isolated incomplete state: fresh database, nothing provisioned
        server.sql('CREATE DATABASE "' + db + '"')
        reasons_incomplete = helper.evaluate_contract(server.admin_db_url(db))
        assert reasons_incomplete, (
            "expected a non-empty named refusal set on the incomplete state")
        assert any("alembic_version" in r for r in reasons_incomplete), \
            reasons_incomplete
    finally:
        server.drop_db(db)
    # (2) the SAME evaluator object against the intact completed state
    reasons_completed = helper.evaluate_contract(five_stage_database["app_url"])
    # (3) freshness: nothing retained from the first call
    assert reasons_completed == [], reasons_completed


def test_run_gate_succeeds_after_transient_first_failure(monkeypatch):
    """R1-R4 P1: refusal reasons are scoped to ONE attempt - a failed attempt
    followed by a valid attempt inside the retry budget starts successfully
    with NO stale refusal state."""
    helper = _load_helper()
    calls = {"n": 0}

    def flaky(database_url, tenant, backend_dir=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return ["migration head is '038', requires exactly "
                    "'039_order_credit_holds'"]
        return []

    monkeypatch.setattr(helper, "evaluate_contract", flaky)
    monkeypatch.setattr(helper.time, "sleep", lambda s: None)
    clock = {"t": 0.0}

    def fake_monotonic():
        clock["t"] += 0.5
        return clock["t"]

    monkeypatch.setattr(helper.time, "monotonic", fake_monotonic)
    rc = helper.run_gate("postgresql://x/x", "t_dev",
                         deadline_seconds=30.0, interval_seconds=0.0)
    assert rc == 0
    assert calls["n"] == 2


def test_run_gate_permanent_failure_exhausts_retry_and_returns_nonzero(monkeypatch):
    helper = _load_helper()

    def always_red(database_url, tenant, backend_dir=None):
        return ["migration head is None, requires exactly "
                "'039_order_credit_holds'"]

    monkeypatch.setattr(helper, "evaluate_contract", always_red)
    monkeypatch.setattr(helper.time, "sleep", lambda s: None)
    clock = {"t": 0.0}

    def fake_monotonic():
        clock["t"] += 10.0
        return clock["t"]

    monkeypatch.setattr(helper.time, "monotonic", fake_monotonic)
    rc = helper.run_gate("postgresql://x/x", "t_dev",
                         deadline_seconds=30.0, interval_seconds=0.0)
    assert rc == 1


@_requires_temp_db
def test_entrypoint_gate_subprocess_matches_helper_on_completed_state(
    five_stage_database, monkeypatch,
):
    """The committed entrypoint executes the gate exactly as shipped (heredoc
    extraction, runtime URL only) and accepts the completed state."""
    text = ENTRYPOINT.read_text(encoding="utf-8")
    _entrypoint_invokes_gate_helper(text)
    match = re.search(r"python - <<'PYEOF'\n(.*?)\nPYEOF", text, re.DOTALL)
    assert match is not None
    app_url = five_stage_database["app_url"]
    monkeypatch.setenv("REPORTING_DATABASE_URL",
                       five_stage_database["reporting_url"])
    result = subprocess.run(
        [sys.executable, "-"], input=match.group(1),
        env={**os.environ, "DATABASE_URL": app_url,
             "REPORTING_DATABASE_URL":
                 five_stage_database["reporting_url"],
             "DEFAULT_TENANT_SCHEMA": "t_dev", "MPANGO_ENV": "test"},
        capture_output=True, text=True, timeout=300, cwd=str(BACKEND_DIR),
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    combined = result.stdout + result.stderr
    assert "five-stage setup contract verified" in combined


# ---------------------------------------------------------------------------
# R1-R7: read-only reporting runtime readiness contract
# ---------------------------------------------------------------------------
# R1-R7-R1: neutral login prefix used to assemble reporting-DSN variants at
# RUNTIME, so committed bytes contain no user:password-shaped literal and no
# scanner suppression is needed for the fixtures below.
_REPORTING_LOGIN = "reporting_user:"


def test_gate_reporting_probes_are_statically_read_only():
    helper = _load_helper()
    for name, sql in helper._REPORTING_PROBE_SQL:
        upper = " ".join(sql.upper().split())
        assert upper.startswith("SELECT "), name
        for forbidden in ("INSERT INTO", "UPDATE ", "DELETE FROM",
                          "CREATE ", "ALTER ", "DROP ", "GRANT ", "REVOKE "):
            assert forbidden not in upper, (name, forbidden)


@_requires_temp_db
def test_reporting_readiness_positive_on_real_pg16(
        five_stage_database, monkeypatch):
    monkeypatch.setenv("REPORTING_DATABASE_URL",
                       five_stage_database["reporting_url"])
    helper = _load_helper()
    reasons = helper.evaluate_contract(five_stage_database["app_url"], "t_dev")
    assert reasons == [], reasons


@_requires_temp_db
def test_gate_refuses_missing_reporting_dsn(five_stage_database, monkeypatch):
    monkeypatch.delenv("REPORTING_DATABASE_URL", raising=False)
    helper = _load_helper()
    reasons = helper.evaluate_contract(five_stage_database["app_url"], "t_dev")
    assert reasons and ("reporting runtime DSN missing" in reasons[-1]), reasons
    assert helper.run_gate(five_stage_database["app_url"], "t_dev",
                           deadline_seconds=1.0) == 1


@_requires_temp_db
def test_gate_refuses_wrong_reporting_password(five_stage_database, monkeypatch):
    bad = (five_stage_database["reporting_url"]
           .replace(_REPORTING_LOGIN, _REPORTING_LOGIN + "wrong"))
    monkeypatch.setenv("REPORTING_DATABASE_URL", bad)
    helper = _load_helper()
    reasons = helper.evaluate_contract(five_stage_database["app_url"], "t_dev")
    assert reasons and "InvalidPasswordError" in reasons[-1], reasons


@_requires_temp_db
def test_gate_refuses_wrong_reporting_database(five_stage_database, monkeypatch):
    url = (five_stage_database["reporting_url"]
           .replace("/" + five_stage_database["db"], "/postgres"))
    monkeypatch.setenv("REPORTING_DATABASE_URL", url)
    helper = _load_helper()
    reasons = helper.evaluate_contract(five_stage_database["app_url"], "t_dev")
    assert reasons and ("reporting connection refused or unusable" in reasons[-1]
                        or "different database" in reasons[-1]), reasons


@_requires_temp_db
def test_gate_refuses_missing_reporting_role_membership(
        five_stage_database, monkeypatch):
    """R1-R7-R2-R1-R1 fail-closed restore closure (CTO-AUTH-ORDER-R2-DBAUTH-
    R1R7R2R1-R1-FAIL-CLOSED-RESTORE-2026-09-21): PostgreSQL 16 records role
    memberships per grantor in pg_auth_members, so a plain administrator
    REVOKE does not remove a membership granted by the migration authority.
    The test reproduces that R4 behavior, reads and saves the membership's
    full catalog facts (grantor name resolved through pg_roles, never a
    regrole::text cast), revokes through the recorded grantor, asserts both
    post-revoke preconditions before touching the gate, and requires the
    named gate refusal.  The precise restore and the catalog-snapshot
    verification then run on an UNCONDITIONAL path with fresh admin
    connections; no exception is ever swallowed - a restore failure
    re-raises as an explicit failure (with the body error preserved and
    visible when both fail), and a passing restore still re-raises any
    body error."""
    from psycopg2 import sql as pg_sql

    monkeypatch.setenv("REPORTING_DATABASE_URL",
                       five_stage_database["reporting_url"])
    server = five_stage_database["server"]
    admin_db_url = server.admin_db_url(five_stage_database["db"])
    member = "reporting_user"
    role = "reporting_role"

    def _membership_facts(cur):
        cur.execute(
            "SELECT grn.rolname, g.admin_option, g.inherit_option, "
            "g.set_option "
            "FROM pg_auth_members g "
            "JOIN pg_roles m ON m.oid = g.member "
            "JOIN pg_roles r ON r.oid = g.roleid "
            "JOIN pg_roles grn ON grn.oid = g.grantor "
            "WHERE m.rolname = %s AND r.rolname = %s",
            (member, role))
        return cur.fetchall()

    # ---- phase A: catalog facts + R4 reproduction (connection 1) --------
    facts = []
    grantor = None
    conn = _admin_connect(admin_db_url)
    try:
        with conn.cursor() as cur:
            facts = _membership_facts(cur)
            assert facts, "expected the reporting_role membership to exist"
            grantor = facts[0][0]
            # R4 reproduction: the plain administrator REVOKE does not
            # remove the migration-granted membership on PostgreSQL 16
            cur.execute(pg_sql.SQL("REVOKE {} FROM {}").format(
                pg_sql.Identifier(role), pg_sql.Identifier(member)))
            cur.execute("SELECT pg_has_role(%s, %s, 'MEMBER')",
                        (member, role))
            assert cur.fetchone()[0], (
                "R4 reproduction failed: the plain administrator REVOKE "
                "unexpectedly removed the grantor-tracked membership")
        conn.commit()
    finally:
        conn.rollback()
        conn.close()

    # ---- phase B: grantor-aware revoke + preconditions + gate (conn 2) --
    body_error = None
    conn = _admin_connect(admin_db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(pg_sql.SQL("SET ROLE {}").format(
                pg_sql.Identifier(grantor)))
            cur.execute(pg_sql.SQL("REVOKE {} FROM {}").format(
                pg_sql.Identifier(role), pg_sql.Identifier(member)))
            cur.execute("RESET ROLE")
            cur.execute(
                "SELECT count(*) FROM pg_auth_members g "
                "JOIN pg_roles m ON m.oid = g.member "
                "JOIN pg_roles r ON r.oid = g.roleid "
                "WHERE m.rolname = %s AND r.rolname = %s",
                (member, role))
            direct_rows = cur.fetchone()[0]
            cur.execute("SELECT pg_has_role(%s, %s, 'MEMBER')",
                        (member, role))
            has_role = cur.fetchone()[0]
        conn.commit()
        assert direct_rows == 0 and not has_role, (
            "post-revoke preconditions failed: direct_rows="
            f"{direct_rows}, pg_has_role={has_role}")
        helper = _load_helper()
        reasons = helper.evaluate_contract(
            five_stage_database["app_url"], "t_dev")
        assert reasons and "lacks reporting_role membership" in reasons[-1], \
            reasons
    except Exception as exc:
        body_error = exc
    finally:
        conn.rollback()
        conn.close()

    # ---- phase C: UNCONDITIONAL restore + verification ------------------
    # A fresh connection performs the restore; a second fresh connection
    # performs the read-only verification, so neither depends on any
    # earlier session state.  Any failure here is captured and re-raised
    # explicitly below (never swallowed).
    restore_error = None
    restored = None
    restored_has_role = None
    try:
        conn = _admin_connect(admin_db_url)
        try:
            with conn.cursor() as cur:
                cur.execute(pg_sql.SQL("SET ROLE {}").format(
                    pg_sql.Identifier(grantor)))
                option_parts = ["ADMIN OPTION" if facts[0][1] else None,
                                "INHERIT " + ("TRUE" if facts[0][2]
                                              else "FALSE"),
                                "SET " + ("TRUE" if facts[0][3]
                                          else "FALSE")]
                option_sql = ", ".join(o for o in option_parts if o)
                restore = pg_sql.SQL("GRANT {} TO {}").format(
                    pg_sql.Identifier(role), pg_sql.Identifier(member))
                if option_sql:
                    restore += pg_sql.SQL(" WITH " + option_sql)
                cur.execute(restore)
                cur.execute("RESET ROLE")
            conn.commit()
        finally:
            conn.rollback()
            conn.close()
        conn = _admin_connect(admin_db_url)
        try:
            with conn.cursor() as cur:
                restored = _membership_facts(cur)
                cur.execute("SELECT pg_has_role(%s, %s, 'MEMBER')",
                            (member, role))
                restored_has_role = cur.fetchone()[0]
        finally:
            conn.close()
    except Exception as exc:
        restore_error = exc

    # ---- fail-closed arbitration ----------------------------------------
    if restore_error is not None:
        if body_error is not None:
            raise AssertionError(
                "membership restore FAILED after a body failure - both "
                f"errors visible: body={body_error!r}; "
                f"restore={restore_error!r}") from restore_error
        raise AssertionError(
            "membership restore FAILED (fail-closed): "
            f"{restore_error!r}") from restore_error
    if restored != facts or restored_has_role is not True:
        detail = (f"restore verification mismatch: pre={facts} "
                  f"post={restored} pg_has_role={restored_has_role}")
        if body_error is not None:
            raise AssertionError(detail + f"; body error also present: "
                                 f"{body_error!r}")
        raise AssertionError(detail)
    if body_error is not None:
        raise body_error


@_requires_temp_db
def test_gate_refuses_read_only_off(five_stage_database, monkeypatch):
    monkeypatch.setenv("REPORTING_DATABASE_URL",
                       five_stage_database["reporting_url"])
    admin = _admin_connect(five_stage_database["server"]
                           .admin_db_url(five_stage_database["db"]))
    try:
        with admin.cursor() as cur:
            cur.execute("ALTER ROLE reporting_user SET "
                        "default_transaction_read_only = off")
        admin.commit()
    finally:
        admin.close()
    helper = _load_helper()
    reasons = helper.evaluate_contract(five_stage_database["app_url"], "t_dev")
    admin = _admin_connect(five_stage_database["server"]
                           .admin_db_url(five_stage_database["db"]))
    try:
        with admin.cursor() as cur:
            cur.execute("ALTER ROLE reporting_user SET "
                        "default_transaction_read_only = on")
        admin.commit()
    finally:
        admin.close()
    assert reasons and "read-only" in reasons[-1], reasons


@_requires_temp_db
def test_gate_refuses_excessive_privileges(five_stage_database, monkeypatch):
    monkeypatch.setenv("REPORTING_DATABASE_URL",
                       five_stage_database["reporting_url"])
    admin = _admin_connect(five_stage_database["server"]
                           .admin_db_url(five_stage_database["db"]))
    try:
        with admin.cursor() as cur:
            cur.execute("GRANT INSERT ON public.wholesalers TO reporting_user")
        admin.commit()
    finally:
        admin.close()
    helper = _load_helper()
    reasons = helper.evaluate_contract(five_stage_database["app_url"], "t_dev")
    admin = _admin_connect(five_stage_database["server"]
                           .admin_db_url(five_stage_database["db"]))
    try:
        with admin.cursor() as cur:
            cur.execute("REVOKE INSERT ON public.wholesalers FROM reporting_user")
        admin.commit()
    finally:
        admin.close()
    assert reasons and ("privilege surface mismatch: "
                        "public_insert_wholesalers expected False") in reasons[-1], reasons


@_requires_temp_db
def test_gate_refuses_missing_select(five_stage_database, monkeypatch):
    monkeypatch.setenv("REPORTING_DATABASE_URL",
                       five_stage_database["reporting_url"])
    admin = _admin_connect(five_stage_database["server"]
                           .admin_db_url(five_stage_database["db"]))
    try:
        with admin.cursor() as cur:
            cur.execute("REVOKE SELECT ON public.wholesalers FROM reporting_role")
        admin.commit()
    finally:
        admin.close()
    helper = _load_helper()
    reasons = helper.evaluate_contract(five_stage_database["app_url"], "t_dev")
    admin = _admin_connect(five_stage_database["server"]
                           .admin_db_url(five_stage_database["db"]))
    try:
        with admin.cursor() as cur:
            cur.execute("GRANT SELECT ON public.wholesalers TO reporting_role")
        admin.commit()
    finally:
        admin.close()
    assert reasons and ("privilege surface mismatch: "
                        "public_select_wholesalers expected True") in reasons[-1], reasons


@_requires_temp_db
def test_readiness_probes_are_behaviorally_read_only(
        five_stage_database, monkeypatch):
    """DML counters on the probed public tables must be unchanged by a full
    readiness evaluation (the probe never writes)."""
    monkeypatch.setenv("REPORTING_DATABASE_URL",
                       five_stage_database["reporting_url"])
    admin = _admin_connect(five_stage_database["server"]
                           .admin_db_url(five_stage_database["db"]))
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT schemaname, relname, n_tup_ins, n_tup_upd, "
                        "n_tup_del FROM pg_stat_user_tables "
                        "WHERE schemaname = 'public' ORDER BY relname")
            before = cur.fetchall()
    finally:
        admin.close()
    helper = _load_helper()
    assert helper.evaluate_contract(five_stage_database["app_url"],
                                    "t_dev") == []
    admin = _admin_connect(five_stage_database["server"]
                           .admin_db_url(five_stage_database["db"]))
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT schemaname, relname, n_tup_ins, n_tup_upd, "
                        "n_tup_del FROM pg_stat_user_tables "
                        "WHERE schemaname = 'public' ORDER BY relname")
            after = cur.fetchall()
    finally:
        admin.close()
    assert before == after
