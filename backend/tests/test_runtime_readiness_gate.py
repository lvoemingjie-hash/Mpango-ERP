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


_MISSING_VERIFIER = object()  # sentinel: the role was ABSENT pre-fixture

_REPORTING_MEMBER = "reporting_user"
_REPORTING_CONTAINER = "reporting_role"


def _snapshot_membership(cur, member=_REPORTING_MEMBER,
                         role=_REPORTING_CONTAINER):
    """Read-only snapshot of the (member <- role) membership rows.

    The granting role is resolved through pg_roles - never a regrole::text
    cast handed back to an Identifier - and all three grant options are
    kept, so the snapshot is exactly what a grantor-aware restore has to
    reproduce."""
    cur.execute(
        "SELECT grn.rolname, g.admin_option, g.inherit_option, g.set_option "
        "FROM pg_auth_members g "
        "JOIN pg_roles m ON m.oid = g.member "
        "JOIN pg_roles r ON r.oid = g.roleid "
        "JOIN pg_roles grn ON grn.oid = g.grantor "
        "WHERE m.rolname = %s AND r.rolname = %s ORDER BY 1",
        (member, role))
    return [tuple(row) for row in cur.fetchall()]


def _membership_options(admin, inherit, set_):
    """All three membership booleans, always stated explicitly.

    PostgreSQL 16 keeps the CURRENT value of an option that a GRANT omits,
    so a correction that spells out only INHERIT and SET cannot turn an
    existing ADMIN TRUE back into ADMIN FALSE.  Every correction therefore
    names ADMIN, INHERIT and SET, in that order."""
    return ["ADMIN " + ("TRUE" if admin else "FALSE"),
            "INHERIT " + ("TRUE" if inherit else "FALSE"),
            "SET " + ("TRUE" if set_ else "FALSE")]


def _reconcile_membership(cur, member, role, wanted):
    """Bring the (member <- role) membership rows exactly back to `wanted`.

    PostgreSQL 16 records every membership against the granting role, so
    each statement is issued with SET ROLE against the RECORDED grantor
    name; a plain administrator REVOKE cannot remove a membership recorded
    against a different grantor and is therefore never used.  Returns the
    statements that were executed (empty when the set already matches)."""
    from psycopg2 import sql as pg_sql

    current = _snapshot_membership(cur, member, role)
    executed = []
    for grantor in sorted({r[0] for r in current} - {r[0] for r in wanted}):
        cur.execute(pg_sql.SQL("SET ROLE {}").format(
            pg_sql.Identifier(grantor)))
        cur.execute(pg_sql.SQL("REVOKE {} FROM {}").format(
            pg_sql.Identifier(role), pg_sql.Identifier(member)))
        cur.execute("RESET ROLE")
        executed.append(f"REVOKE {role} FROM {member} GRANTED BY {grantor}")
    for grantor, admin, inherit, set_ in wanted:
        if (grantor, admin, inherit, set_) in current:
            continue
        options = _membership_options(admin, inherit, set_)
        cur.execute(pg_sql.SQL("SET ROLE {}").format(
            pg_sql.Identifier(grantor)))
        cur.execute(pg_sql.SQL("GRANT {} TO {}").format(
            pg_sql.Identifier(role), pg_sql.Identifier(member))
            + pg_sql.SQL(" WITH " + ", ".join(options)))
        cur.execute("RESET ROLE")
        executed.append(f"GRANT {role} TO {member} WITH {', '.join(options)}"
                        f" GRANTED BY {grantor}")
    return executed


def _libpq_dsn(dsn: str) -> str:
    """A SQLAlchemy-style URL ('postgresql+asyncpg://...') is normalised to
    the plain form psycopg2/libpq accepts.  Without this the probe never
    reaches the server at all and would report a client-side parse error
    where an authentication outcome is required."""
    scheme, sep, rest = dsn.partition("://")
    if sep and "+" in scheme:
        return scheme.split("+", 1)[0] + sep + rest
    return dsn


def _dsn_login_identity(dsn: str):
    """The login name the environment reporting DSN authenticates as, or
    None when the DSN does not name one."""
    scheme, sep, rest = dsn.partition("://")
    if not sep:
        return None
    netloc = rest.split("/", 1)[0]
    if "@" not in netloc:
        return None
    return netloc.rsplit("@", 1)[0].split(":", 1)[0] or None


def _probe_dsn(dsn: str) -> str:
    """Outcome of a REAL authentication attempt through the environment
    reporting DSN: 'ok' on success, otherwise the exception class name.

    This is the only credential-level connection this fixture can prove.
    A SCRAM verifier is not a client password, so replaying the captured
    verifier would not authenticate anything and is not used as evidence.
    The verifier is checked separately, byte-for-byte, in the catalog."""
    import psycopg2

    try:
        conn = psycopg2.connect(_libpq_dsn(dsn), connect_timeout=10)
    except Exception as exc:
        return type(exc).__name__
    conn.close()
    return "ok"


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
    bootstrap of the default tenant.

    R1-R7-R2-R1-R1-R2B fixture trust (CTO-AUTH-ORDER-R2-DBAUTH-R1R7R2R1R1-
    R2B-FIXTURE-TRUST-2026-09-21) with the R2C preflight boundary
    (CTO-AUTH-ORDER-R2-DBAUTH-R2C-PREFLIGHT-ZERO-WRITE-2026-09-21).  The
    shared cluster login reporting_user is captured as THREE independent
    pre-state facts - whether the role exists, its pg_authid verifier, and
    every reporting_user <- reporting_role membership row with its grantor
    and grant options.  Absence is never folded into a NULL verifier: an
    absent role is _MISSING_VERIFIER, a present role without a password is
    None.

    PREFLIGHT, and why it sits outside the write lifecycle.  The pre-state
    capture and the credential proof run BEFORE the try/finally that owns
    every write.  A refusal therefore never reaches provisioning or
    teardown at all: the refusal is not merely residue-free, it performs no
    write, because the write lifecycle is never entered.  While the
    preflight is running the fixture issues read-only SQL only - the
    server-side statement trace recorded with counterexample B is the
    evidence for that, and the before/after snapshots are supplementary.

    CREDENTIAL PROOF.  When the login exists, the environment reporting DSN
    must authenticate as it FOR REAL, and it must do so BEFORE this fixture
    writes anything; any other outcome - a different login name, a parse
    error, a rejected password, an unreachable server - refuses the run
    outright.  After teardown the same DSN must authenticate again, so the
    check is a positive proof on both sides rather than an equality between
    two possibly identical failures.  The captured SCRAM verifier is never
    replayed as a client password: a verifier is not a password and such an
    attempt would prove nothing.  The verifier is checked separately and
    byte-for-byte in the catalog.  When the role was absent pre-fixture the
    fixture claims ONLY catalog-absence restoration and makes no credential
    login claim at all.

    MEMBERSHIP.  Corrections are issued only through the RECORDED grantor
    (PostgreSQL 16 tracks memberships per grantor, so a plain administrator
    REVOKE is a no-op) and always state ADMIN, INHERIT and SET explicitly,
    because an omitted option keeps its current value and would leave an
    existing ADMIN TRUE in place.

    TEARDOWN runs in a fixed order, every step on its own fresh admin
    connection that is explicitly committed, rolled back and closed:
    restore the credential, remove the sandbox database, put the membership
    set back through the recorded grantor and drop the sandbox roles, then
    re-check the verifier, the membership set and the credential login.
    Nothing is swallowed and nothing is left to process exit or to a
    DROP ROLE side effect: every cleanup and every check appends to
    teardown_errors, and any entry fails the module as an ERROR."""
    server = _SandboxServer()
    suffix = uuid.uuid4().hex[:8]
    mig_role, app_role = "mpango_migrate_" + suffix, "mpango_app_" + suffix
    mig_pw, app_pw = "pw_" + suffix + "_m", "pw_" + suffix + "_a"
    ctx_reporting = "reporting-" + suffix
    ctx_gate = "gate-fixture-" + suffix
    sandbox_db = "test_readiness_" + suffix
    env = _scenario_env(server, sandbox_db, mig_role, app_role, mig_pw, app_pw)
    original_role_exists = False
    original_verifier = _MISSING_VERIFIER
    original_membership = []
    original_dsn = os.environ.get("REPORTING_DATABASE_URL") or None
    credential_login = "NOT_APPLICABLE_ROLE_ABSENT"
    credential_login_proven = False
    # ---- PREFLIGHT: read-only, outside the write lifecycle --------------
    # Nothing below this point runs if the preflight refuses, so a refusal
    # cannot commit an ALTER, DROP, GRANT, REVOKE or pg_terminate_backend.
    capture_conn = _admin_connect(server.admin_db_url("postgres"))
    try:
        with capture_conn.cursor() as cur:
            cur.execute("SELECT rolpassword FROM pg_authid "
                        "WHERE rolname = %s", (_REPORTING_MEMBER,))
            row = cur.fetchone()
            original_role_exists = row is not None
            if original_role_exists:
                original_verifier = row[0]
            original_membership = _snapshot_membership(cur)
    finally:
        capture_conn.rollback()
        capture_conn.close()
    if original_role_exists:
        if original_dsn is None:
            pytest.fail(
                "five_stage_database: reporting_user exists but "
                "REPORTING_DATABASE_URL is not set, so the original "
                "reporting credential cannot be proven before the fixture "
                "writes anything")
        dsn_identity = _dsn_login_identity(original_dsn)
        if dsn_identity != _REPORTING_MEMBER:
            pytest.fail(
                "five_stage_database: REPORTING_DATABASE_URL authenticates "
                f"as {dsn_identity!r}, not {_REPORTING_MEMBER!r}, so it does "
                "not prove the reporting credential")
        original_dsn_outcome = _probe_dsn(original_dsn)
        if original_dsn_outcome != "ok":
            pytest.fail(
                "five_stage_database: the REPORTING_DATABASE_URL login "
                f"FAILED before any write ({original_dsn_outcome}); refusing "
                "to run, because a fixture that cannot prove the original "
                "credential cannot prove it restored it")
        credential_login = "PROVEN_BEFORE_WRITE"
        credential_login_proven = True
    # ---- WRITE LIFECYCLE: entered only after the preflight succeeded ----
    try:
        # phase 1: provision (admin) - the sandbox database does NOT
        # pre-exist; the product creates it owned by the migration authority
        result = _run_provisioner(["--provision"], env)
        assert result.returncode == 0, result.stderr
        mig_url = server.url_for(db=sandbox_db, user=mig_role, password=mig_pw)
        app_url = server.url_for(db=sandbox_db, user=app_role, password=app_pw)
        # cluster-global role accommodation (test-env only; same documented
        # pattern as the combined-contract suite).  On PostgreSQL 16 the
        # migration's GRANT/ALTER ROLE against the shared reporting_role
        # needs ADMIN OPTION on it, and the shared login is aligned with
        # THIS sandbox's migration-time secret so the read-only reporting
        # probe is deterministic.  The connection is explicitly rolled back
        # and closed and nothing here outlives this block.
        accommodation_conn = _admin_connect(server.admin_db_url("postgres"))
        try:
            from psycopg2 import sql as pg_sql
            with accommodation_conn.cursor() as cur:
                for role in (_REPORTING_CONTAINER, _REPORTING_MEMBER):
                    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s",
                                (role,))
                    if cur.fetchone():
                        cur.execute(pg_sql.SQL("GRANT {} TO {}").format(
                            pg_sql.Identifier(role),
                            pg_sql.Identifier(mig_role))
                            + pg_sql.SQL(" WITH ADMIN OPTION"))
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s",
                            (_REPORTING_MEMBER,))
                if cur.fetchone():
                    cur.execute("ALTER ROLE reporting_user WITH PASSWORD %s",
                                (ctx_reporting,))
            accommodation_conn.commit()
        finally:
            accommodation_conn.rollback()
            accommodation_conn.close()
        # phase 2: migrations 001..039 as the migration authority
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR, capture_output=True, text=True, timeout=600,
            env={**os.environ, "DATABASE_URL": mig_url,
                 "REPORTING_USER_PASSWORD": ctx_reporting,
                 "MPANGO_ENV": "test"})
        assert result.returncode == 0, result.stderr[-2000:]
        # phase 3: minimum grants as the migration authority
        result = _run_provisioner(["--apply-grants"], env)
        assert result.returncode == 0, result.stderr
        # phase 4: read-only verification
        result = _run_provisioner(["--verify"], env)
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert '"ok": true' in result.stdout
        reporting_url = server.url_for(db=sandbox_db, user=_REPORTING_MEMBER,
                                       password=ctx_reporting)
        # phase 5: runtime bootstrap of the default tenant
        result = subprocess.run(
            [sys.executable, "scripts/bootstrap_tenant_schema.py", "t_dev"],
            cwd=BACKEND_DIR, capture_output=True, text=True, timeout=300,
            env={**os.environ, "DATABASE_URL": app_url, "MPANGO_ENV": "test",
                 "SECRET_KEY": ctx_gate})
        assert result.returncode == 0, result.stderr[-2000:]
        yield {"app_url": app_url, "mig_url": mig_url, "db": sandbox_db,
               "server": server, "reporting_url": reporting_url,
               "original_role_exists": original_role_exists,
               "original_verifier": original_verifier,
               "original_membership": original_membership,
               "credential_login": credential_login}
    finally:
        teardown_errors = []
        # (1) restore the credential of the shared login.  An absent role
        #     stays absent - removing it belongs to step (2b), after the
        #     sandbox objects that depend on it are gone.
        try:
            cred_conn = _admin_connect(server.admin_db_url("postgres"))
            try:
                with cred_conn.cursor() as cur:
                    if original_role_exists:
                        if original_verifier is None:
                            cur.execute("ALTER ROLE reporting_user "
                                        "WITH PASSWORD NULL")
                        else:
                            cur.execute("ALTER ROLE reporting_user "
                                        "WITH PASSWORD %s",
                                        (original_verifier,))
                cred_conn.commit()
            finally:
                cred_conn.rollback()
                cred_conn.close()
        except Exception as exc:
            teardown_errors.append(
                f"credential restore: {type(exc).__name__}: {exc}")
        # (2a) remove the sandbox database
        try:
            db_conn = _admin_connect(server.admin_db_url("postgres"))
            try:
                with db_conn.cursor() as cur:
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM "
                        "pg_stat_activity WHERE datname = %s "
                        "AND pid <> pg_backend_pid()", (sandbox_db,))
                    cur.execute(f'DROP DATABASE IF EXISTS "{sandbox_db}"')
                db_conn.commit()
            finally:
                db_conn.rollback()
                db_conn.close()
        except Exception as exc:
            teardown_errors.append(
                f"sandbox database drop: {type(exc).__name__}: {exc}")
        # (2b) put the membership set back through the recorded grantor and
        #      drop every role this fixture created.  The migration records
        #      its own grant against THIS run's migration authority, so the
        #      grantor-aware revoke has to happen before that role can be
        #      dropped at all.
        try:
            role_conn = _admin_connect(server.admin_db_url("postgres"))
            try:
                with role_conn.cursor() as cur:
                    _reconcile_membership(cur, _REPORTING_MEMBER,
                                          _REPORTING_CONTAINER,
                                          original_membership)
                    if not original_role_exists:
                        cur.execute('DROP ROLE IF EXISTS "reporting_user"')
                    for role in (app_role, mig_role):
                        cur.execute(f'DROP ROLE IF EXISTS "{role}"')
                role_conn.commit()
            finally:
                role_conn.rollback()
                role_conn.close()
        except Exception as exc:
            teardown_errors.append(
                f"sandbox role cleanup: {type(exc).__name__}: {exc}")
        # (3) verifier check on a fresh connection: existence AND verifier
        try:
            check_conn = _admin_connect(server.admin_db_url("postgres"))
            try:
                with check_conn.cursor() as cur:
                    cur.execute("SELECT rolpassword FROM pg_authid "
                                "WHERE rolname = %s", (_REPORTING_MEMBER,))
                    verified_row = cur.fetchone()
            finally:
                check_conn.rollback()
                check_conn.close()
            if not original_role_exists and verified_row is not None:
                teardown_errors.append(
                    "verifier check: reporting_user still exists but the "
                    "role was absent before the fixture ran")
            elif original_role_exists and verified_row is None:
                teardown_errors.append(
                    "verifier check: reporting_user is missing but the role "
                    "existed before the fixture ran")
            elif original_role_exists and verified_row[0] != original_verifier:
                teardown_errors.append(
                    "verifier check: reporting_user verifier is not "
                    "byte-equal to the captured pre-fixture state")
        except Exception as exc:
            teardown_errors.append(
                f"verifier check: {type(exc).__name__}: {exc}")
        # (4) membership check on a fresh connection: read-only catalog
        try:
            set_conn = _admin_connect(server.admin_db_url("postgres"))
            try:
                with set_conn.cursor() as cur:
                    restored_membership = _snapshot_membership(cur)
            finally:
                set_conn.rollback()
                set_conn.close()
            if restored_membership != original_membership:
                teardown_errors.append(
                    "membership check: the reporting_user <- reporting_role "
                    "membership rows are not identical to the pre-fixture "
                    f"state (pre={original_membership} "
                    f"post={restored_membership})")
        except Exception as exc:
            teardown_errors.append(
                f"membership check: {type(exc).__name__}: {exc}")
        # (5) credential login check.  Only a login PROVEN before the
        #     fixture's first write is re-proven here; when the role was
        #     absent pre-fixture the fixture claims catalog-absence
        #     restoration only and deliberately makes no login claim.
        try:
            if credential_login_proven:
                dsn_outcome = _probe_dsn(original_dsn)
                if dsn_outcome != "ok":
                    teardown_errors.append(
                        "original-credential connection: the environment "
                        "reporting DSN does not authenticate after teardown "
                        f"({dsn_outcome}), but it did before any write")
        except Exception as exc:
            teardown_errors.append(
                f"original-credential connection: "
                f"{type(exc).__name__}: {exc}")
        if teardown_errors:
            pytest.fail("five_stage_database teardown failures: "
                        + " | ".join(teardown_errors))


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
    """R1-R7-R2-R1-R1 membership refusal, R2D isolation closure (CTO-AUTH-
    ORDER-R2-DBAUTH-R2D-D-PARTITION-ISOLATION-2026-09-21).

    Two independent parts, and neither may damage the shared canonical
    reporting_user membership.

    Part 1 - the PostgreSQL 16 R4 reproduction on TASK-SPECIFIC roles.  A
    scratch container, a scratch grantor and a scratch member are created
    for this invocation alone; the scratch grantor records the membership,
    a plain administrator REVOKE is shown not to remove it, and every
    scratch object is dropped in an unconditional finally.  The shared
    reporting_user membership is never touched here, so this reproduction
    can no longer fail on - or pollute - cluster state left by other
    nodes: the precondition it depends on now belongs entirely to this
    test.

    Part 2 - the real gate refusal against the real reporting identity.
    The precondition (the canonical membership exists) is checked while
    still read-only, BEFORE any write.  The first membership write - the
    grantor-aware revoke of the canonical grant - then happens inside the
    try whose finally unconditionally restores the recorded facts through
    the recorded grantor with explicit ADMIN/INHERIT/SET options and
    verifies the restoration on a fresh connection.  A restore failure
    raises even when the body passed (fail-closed), and a body error is
    re-raised after a verified restore.  No membership write is ever
    executed outside this boundary, so an assertion can no longer leave
    the canonical membership revoked for the nodes that follow."""
    from psycopg2 import sql as pg_sql

    monkeypatch.setenv("REPORTING_DATABASE_URL",
                       five_stage_database["reporting_url"])
    server = five_stage_database["server"]
    admin_db_url = server.admin_db_url(five_stage_database["db"])
    member = _REPORTING_MEMBER
    role = _REPORTING_CONTAINER

    # ---- part 1: R4 reproduction on task-specific scratch roles --------
    suffix = uuid.uuid4().hex[:8]
    container = "r2d_probe_container_" + suffix
    probe_grantor = "r2d_probe_grantor_" + suffix
    probe_member = "r2d_probe_member_" + suffix
    reproduced = None
    setup_error = None
    conn = _admin_connect(admin_db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(pg_sql.SQL("CREATE ROLE {} NOLOGIN").format(
                pg_sql.Identifier(container)))
            cur.execute(pg_sql.SQL("CREATE ROLE {} NOLOGIN").format(
                pg_sql.Identifier(probe_grantor)))
            cur.execute(pg_sql.SQL("CREATE ROLE {} NOLOGIN").format(
                pg_sql.Identifier(probe_member)))
            cur.execute(pg_sql.SQL("GRANT {} TO {} WITH ADMIN OPTION").format(
                pg_sql.Identifier(container),
                pg_sql.Identifier(probe_grantor)))
            cur.execute(pg_sql.SQL("SET ROLE {}").format(
                pg_sql.Identifier(probe_grantor)))
            cur.execute(pg_sql.SQL("GRANT {} TO {}").format(
                pg_sql.Identifier(container), pg_sql.Identifier(probe_member)))
            cur.execute("RESET ROLE")
            # the R4 reproduction itself: a plain administrator REVOKE
            # against a membership recorded by ANOTHER grantor
            cur.execute(pg_sql.SQL("REVOKE {} FROM {}").format(
                pg_sql.Identifier(container),
                pg_sql.Identifier(probe_member)))
            cur.execute("SELECT pg_has_role(%s, %s, 'MEMBER')",
                        (probe_member, container))
            reproduced = cur.fetchone()[0]
    except Exception as exc:
        setup_error = exc
    finally:
        conn.rollback()
        conn.close()
    # unconditional scratch cleanup: the scratch membership is revoked
    # through its recorded grantor and every scratch role is dropped,
    # whatever the setup did or did not do
    scratch_errors = []
    try:
        cleanup = _admin_connect(admin_db_url)
        try:
            with cleanup.cursor() as cur:
                cur.execute(pg_sql.SQL("SET ROLE {}").format(
                    pg_sql.Identifier(probe_grantor)))
                cur.execute(pg_sql.SQL("REVOKE {} FROM {}").format(
                    pg_sql.Identifier(container),
                    pg_sql.Identifier(probe_member)))
                cur.execute("RESET ROLE")
                for name in (probe_member, probe_grantor, container):
                    cur.execute(pg_sql.SQL("DROP ROLE {}").format(
                        pg_sql.Identifier(name)))
            cleanup.commit()
        finally:
            cleanup.rollback()
            cleanup.close()
    except Exception as exc:
        scratch_errors.append(f"{type(exc).__name__}: {exc}")
    # the reproduction is judged only AFTER the scratch cleanup, so a
    # failure here leaves nothing behind either way
    problems = []
    if setup_error is not None:
        problems.append(f"scratch setup: "
                        f"{type(setup_error).__name__}: {setup_error}")
    if reproduced is not True:
        problems.append(
            "R4 reproduction failed on task-specific roles: the plain "
            "administrator REVOKE unexpectedly removed a membership "
            "recorded by another grantor")
    if scratch_errors:
        problems.append("scratch cleanup: " + " | ".join(scratch_errors))
    assert not problems, " | ".join(problems)

    # ---- part 2: the real refusal inside an unconditional restore ------
    # read-only precondition, before any write: the canonical membership
    # must exist, otherwise the revoke below would be a no-op and the
    # named refusal would prove nothing about the restore
    probe = _admin_connect(admin_db_url)
    try:
        with probe.cursor() as cur:
            facts = _snapshot_membership(cur)
    finally:
        probe.rollback()
        probe.close()
    assert facts, (
        "precondition failed before any write: the canonical "
        f"{member} <- {role} membership does not exist")

    body_error = None
    restore_error = None
    restored = None
    restored_has_role = None
    try:
        conn = _admin_connect(admin_db_url)
        try:
            with conn.cursor() as cur:
                # FIRST membership write of this test - already inside the
                # boundary whose finally restores the recorded facts
                _reconcile_membership(cur, member, role, [])
            conn.commit()
        finally:
            conn.rollback()
            conn.close()
        conn = _admin_connect(admin_db_url)
        try:
            with conn.cursor() as cur:
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
        finally:
            conn.rollback()
            conn.close()
        assert direct_rows == 0 and not has_role, (
            f"post-revoke preconditions failed: direct_rows={direct_rows}, "
            f"pg_has_role={has_role}")
        helper = _load_helper()
        reasons = helper.evaluate_contract(
            five_stage_database["app_url"], "t_dev")
        assert reasons and "lacks reporting_role membership" in reasons[-1], \
            reasons
    except Exception as exc:
        body_error = exc
    finally:
        try:
            conn = _admin_connect(admin_db_url)
            try:
                with conn.cursor() as cur:
                    _reconcile_membership(cur, member, role, facts)
                conn.commit()
            finally:
                conn.rollback()
                conn.close()
            conn = _admin_connect(admin_db_url)
            try:
                with conn.cursor() as cur:
                    restored = _snapshot_membership(cur)
                    cur.execute("SELECT pg_has_role(%s, %s, 'MEMBER')",
                                (member, role))
                    restored_has_role = cur.fetchone()[0]
            finally:
                conn.rollback()
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
    if restored != facts or (facts and restored_has_role is not True):
        detail = (f"restore verification mismatch: pre={facts} "
                  f"post={restored} pg_has_role={restored_has_role}")
        if body_error is not None:
            raise AssertionError(detail + "; body error also present: "
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
