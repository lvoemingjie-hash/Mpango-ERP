"""MPANGO-MVP-INVARIANTS-F1 — DB fixture role-separation integration tests.

CTO-AUTH-MPANGO-MVP-INVARIANTS-F1-DB-FIXTURE-ROLE-CLOSURE-2026-09-08.

Three-identity contract under test (support module, committed fixture):

- bootstrap/migration identity: container ``POSTGRES_USER``, bound to
  ``MPANGO_INVARIANTS_R0_MIGRATION_DATABASE_URL``; runs the real 001..037 in
  a subprocess;
- test-session identity: the user in ``TEST_DATABASE_URL`` (==
  ``DATABASE_URL``); a separate ordinary role (no SUPERUSER/CREATEROLE/
  CREATEDB/REPLICATION, no memberships); the ONLY identity the application
  engine, AsyncSessionLocal and the product bootstrap ever use;
- reporting identity: ``reporting_role``/``reporting_user`` created by
  migration 011 (read-only; created by the migration, not by this suite).

Nodes in this file:

1. POSITIVE — the real ``r0_task_database`` session fixture (the SAME
   committed fixture the formal matrices consume; runnable standalone)
   drives a full real lifecycle: fixture stages (ownership/binding,
   migration-identity live proof, run-identity live proof, real migration,
   head==037 via the run connection, post-migration privilege readiness) →
   ``TenantIdentity.create`` → real seed/read → ``TenantIdentity.drop`` →
   residue proof. Both live identities and the run role's capability row are
   recorded as evidence.
2. WRONG TARGET — migration URL pointed at a wrong host/port/database/user
   (and a wrong container / owner label) must refuse BEFORE any subprocess
   launch: the subprocess launch counter stays zero.
3. WRONG IDENTITY — the run session pointing at the bootstrap/migration
   user, or TEST_DATABASE_URL != DATABASE_URL, must refuse before any test
   write; the live engine binding helper must reject an engine bound to
   another user.
4. SUBPROCESS CONTRACT — the migration subprocess receives ONLY the
   migration URL as its DATABASE_URL; the parent process environment is
   untouched.

Everything DB-touching goes through the committed support module — there is
no readiness-only copy of the migration or verification logic. Permission
negatives (weak migration identity / weak run role) and the three mutations
are executed as separately-env'd development runs recorded in the
REPAIR_LEDGER, not as in-file green paths.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.mpango_invariants_r0_support import (
    CONTAINER_ENV_VAR,
    MIGRATION_LOG_ENV_VAR,
    MIGRATION_URL_ENV_VAR,
    OWNER_LABEL_ENV_VAR,
    GuardRefused,
    _assert_engine_binding,
    _parse_pg_url,
    r0_task_database,  # noqa: F401 - importing registers the session fixture
    run_public_migrations,
    seed_sku_with_stock,
    stock_on_hand,
    tenant_session,
    verify_task_database_ownership_sync,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("r0_task_database")]


class _Completed:
    """Minimal stand-in for a successful subprocess result."""

    def __init__(self):
        self.returncode = 0
        self.stdout = ""
        self.stderr = ""


def _env_snapshot() -> dict:
    return {
        CONTAINER_ENV_VAR: os.environ.get(CONTAINER_ENV_VAR, ""),
        OWNER_LABEL_ENV_VAR: os.environ.get(OWNER_LABEL_ENV_VAR, ""),
        "TEST_DATABASE_URL": os.environ.get("TEST_DATABASE_URL", ""),
        "DATABASE_URL": os.environ.get("DATABASE_URL", ""),
        MIGRATION_URL_ENV_VAR: os.environ.get(MIGRATION_URL_ENV_VAR, ""),
    }


def _restore_env(snapshot: dict) -> None:
    for key, value in snapshot.items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


class _LaunchCounter:
    """Counts MIGRATION subprocess launches, delegating everything else.

    Only ``python -m alembic ...`` invocations are intercepted (counted, no
    execution); every other subprocess call — e.g. the guard's own
    ``docker inspect`` — is delegated to the real implementation so the
    wrong-target refusals stay backed by real container evidence.

    R1 (CTO F1): the candidate's ``run_public_migrations`` calls
    ``subprocess.run(argv, ...)`` POSITIONALLY — ``__call__`` receives
    ``args == (argv,)``. The argv is unpacked from the FIRST positional
    argument (or the ``args=`` keyword); anything else (empty/malformed)
    is delegated uncounted rather than guessed at, so no call shape can be
    miscounted as a migration or silently swallowed.
    """

    def __init__(self, original_run):
        self.launches = 0
        self.delegated = 0
        self._original_run = original_run

    @staticmethod
    def _extract_argv(args, kwargs):
        argv = kwargs.get("args")
        if argv is None and len(args) == 1:
            argv = args[0]
        elif argv is None:
            argv = None
        return argv

    @classmethod
    def _is_migration(cls, args, kwargs) -> bool:
        argv = cls._extract_argv(args, kwargs)
        if not isinstance(argv, (list, tuple)):
            return False
        argv = list(argv)
        return len(argv) >= 3 and argv[1:3] == ["-m", "alembic"]

    def __call__(self, *args, **kwargs):
        if self._is_migration(args, kwargs):
            self.launches += 1
            return _Completed()
        self.delegated += 1
        return self._original_run(*args, **kwargs)


# ---------------------------------------------------------------------------
# 1. POSITIVE: full real lifecycle through the committed session fixture
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_f1_positive_role_separated_full_lifecycle(r0_task_database):
    """[POSITIVE — expected PASS] Migration/run identities, separated, drive
    the real fixture end to end.

    正控: the same committed ``r0_task_database`` fixture the formal matrices
    consume performs ownership + binding + BOTH live identity proofs, the
    real 001..037 migration (via the migration subprocess), the head check on
    the run connection and the post-migration privilege readiness — then a
    REAL tenant lifecycle runs on the run identity (bootstrap DDL, seed
    write/read, teardown) and leaves zero residue.
    证据: migration identity facts (session_user == declared bootstrap user,
    on the declared db, PG16) and run identity facts (session_user ==
    declared run user; ordinary role flags; zero memberships) are recorded
    into the pytest output for the ledger.
    目标缺陷: none (control for the F1 role-closure contract).
    环境前提: task env with all three declarations (container/owner/run URL/
    migration URL); run role provisioned per REPAIR_LEDGER §privileges.
    执行入口: the committed session fixture + TenantIdentity/tenant_session
    helpers (no readiness-only copy of anything).
    未覆盖范围: reporting identity behaviour (read-only enforcement is
    migration 011's contract, exercised by its own suites).
    """
    from tests.mpango_invariants_r0_support import (
        TenantIdentity,
        verify_migration_identity_live,
    )

    migration_url = os.environ[MIGRATION_URL_ENV_VAR].strip()
    run_url = r0_task_database

    mig_user = _parse_pg_url(migration_url)[3]
    run_user = _parse_pg_url(run_url)[3]
    assert mig_user != run_user, (
        "F1_ROLE_CONTRACT: migration and run identities must be distinct."
    )

    # Record BOTH live identities as evidence (the fixture already verified
    # them; re-probing here also proves the declarations are re-derivable).
    mig_facts = await verify_migration_identity_live(migration_url)
    print(
        f"\nF1 EVIDENCE migration identity: db={mig_facts['database']} "
        f"session_user={mig_facts['session_user']} "
        f"current_user={mig_facts['current_user']}"
    )
    async with tenant_session("public") as db:
        row = (
            await db.execute(
                text(
                    "SELECT current_database(), session_user, current_user, "
                    "rolsuper, rolcreatedb, rolcreaterole, rolreplication "
                    "FROM pg_roles WHERE rolname = session_user"
                )
            )
        ).one()
        print(
            f"F1 EVIDENCE run identity: db={row[0]} session_user={row[1]} "
            f"current_user={row[2]} caps(login/super/createdb/createrole/"
            f"replication-expect false)={row[3]!r},{row[4]!r},{row[5]!r},{row[6]!r}"
        )
        assert row[1] == run_user and row[2] == run_user, (
            "F1_ROLE_CONTRACT: the run session must stay on the declared "
            f"identity, got {row[1]!r}/{row[2]!r}."
        )
        assert not (row[3] or row[4] or row[5] or row[6]), (
            "F1_ROLE_CONTRACT: run identity must not hold privileged flags."
        )
        head = (
            await db.execute(text("SELECT version_num FROM public.alembic_version"))
        ).scalar_one()
    assert head == "037_payment_declarations_schema", (
        f"F1_ROLE_CONTRACT: run connection must verify head 037, got {head!r}."
    )

    # Real tenant lifecycle ON THE RUN IDENTITY.
    identity = await TenantIdentity().create()
    try:
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            await seed_sku_with_stock(
                db, sku_code="F1ROLE", quantity_on_hand=Decimal("3")
            )
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            assert await stock_on_hand(db, sku_code="F1ROLE") == Decimal("3.00"), (
                "F1 ROLE lifecycle: seeded stock must read back on the run identity."
            )
    finally:
        await identity.drop()
    async with tenant_session("public") as db:
        gone = (
            await db.execute(
                text("SELECT count(*) FROM information_schema.schemata WHERE schema_name = :s"),
                {"s": identity.schema},
            )
        ).scalar_one()
        pubs = (
            await db.execute(
                text("SELECT count(*) FROM public.wholesalers WHERE id = :w"),
                {"w": identity.wholesaler_id},
            )
        ).scalar_one()
    assert gone == 0 and pubs == 0, (
        "F1 ROLE lifecycle: teardown must leave zero residue."
    )


# ---------------------------------------------------------------------------
# 2. WRONG TARGET: refuse before any migration subprocess launch
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("label", ["host", "port", "database", "user"])
async def test_f1_guard_migration_wrong_target_refuses_pre_launch(label):
    """[NEGATIVE — expected PASS via refusal] Migration URL pointed at a
    wrong target must refuse with ZERO subprocess launches.

    错目标: the declared migration URL is mutated to a wrong host/port/
    database/user against the SAME declared task container; the sync guard
    must refuse (binding/mapping checks) BEFORE the migration subprocess is
    ever started — proven by a launch counter patched into the real
    ``run_public_migrations`` path.
    环境前提: the real task container declaration (docker inspect runs for
    real); subprocess execution intercepted ONLY to count launches.
    执行入口: verify_task_database_ownership_sync (the fixture's own guard).
    未覆盖范围: live wrong-host connections (refusal is pre-connection by
    design — port/container binding makes a foreign target unrepresentable).
    """
    import tests.mpango_invariants_r0_support as support
    from urllib.parse import urlsplit, urlunsplit

    snapshot = _env_snapshot()
    original_run = support.subprocess.run
    counter = _LaunchCounter(original_run)
    support.subprocess.run = counter
    try:
        base = snapshot[MIGRATION_URL_ENV_VAR]
        parts = urlsplit(base.replace("postgresql+asyncpg://", "postgresql://", 1))
        userinfo, _, hostport = parts.netloc.rpartition("@")
        host, _, port = hostport.partition(":")
        if label == "host":
            host = "127.0.0.99"  # loopback-shaped but not the declared target
        elif label == "port":
            port = str(int(port or "5432") + 1)
        elif label == "user":
            password = userinfo.partition(":")[2]
            userinfo = f"wrong_migration_user:{password}" if password else "wrong_migration_user"
        netloc = f"{userinfo}@{host}:{port}" if port else f"{userinfo}@{host}"
        path = "/definitely_not_the_task_db" if label == "database" else parts.path
        mutated = urlunsplit((parts.scheme, netloc, path, parts.query, parts.fragment))
        assert mutated != base, "mutation must actually change the URL"
        os.environ[MIGRATION_URL_ENV_VAR] = mutated
        with pytest.raises(GuardRefused) as excinfo:
            verify_task_database_ownership_sync()
        assert counter.launches == 0, (
            "F1_WRONG_TARGET: no migration subprocess may start when the "
            f"migration URL has a wrong {label}; launch count "
            f"{counter.launches}."
        )
        assert "GUARD_REFUSED_DATABASE_OWNERSHIP" in str(excinfo.value), (
            f"F1_WRONG_TARGET: refusal must be the ownership guard, got "
            f"{excinfo.value!s:.200}"
        )
    finally:
        support.subprocess.run = original_run
        _restore_env(snapshot)


@pytest.mark.integration
async def test_f1_guard_wrong_container_and_owner_refuse_pre_launch():
    """[NEGATIVE — expected PASS via refusal] Wrong container / owner label
    refuse before any migration subprocess launch."""
    import tests.mpango_invariants_r0_support as support

    snapshot = _env_snapshot()
    original_run = support.subprocess.run
    counter = _LaunchCounter(original_run)
    support.subprocess.run = counter
    try:
        os.environ[CONTAINER_ENV_VAR] = "not-a-real-container-zzz"
        with pytest.raises(GuardRefused, match="GUARD_REFUSED_DATABASE_OWNERSHIP"):
            verify_task_database_ownership_sync()
        os.environ[CONTAINER_ENV_VAR] = snapshot[CONTAINER_ENV_VAR]
        os.environ[OWNER_LABEL_ENV_VAR] = "someone-elses-task"
        with pytest.raises(GuardRefused, match="GUARD_REFUSED_DATABASE_OWNERSHIP"):
            verify_task_database_ownership_sync()
        assert counter.launches == 0, (
            "F1_WRONG_TARGET: container/owner refusals must happen before "
            "any migration subprocess launch."
        )
    finally:
        support.subprocess.run = original_run
        _restore_env(snapshot)


# ---------------------------------------------------------------------------
# 3. WRONG IDENTITY: run session must never be the bootstrap identity
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_f1_guard_run_identity_bootstrap_refuses_pre_write():
    """[NEGATIVE — expected PASS via refusal] TEST/DATABASE URL carrying the
    bootstrap/migration user must refuse before any test write (zero
    subprocess launches)."""
    import tests.mpango_invariants_r0_support as support

    snapshot = _env_snapshot()
    original_run = support.subprocess.run
    counter = _LaunchCounter(original_run)
    support.subprocess.run = counter
    try:
        migration_url = snapshot[MIGRATION_URL_ENV_VAR]
        mig_user = _parse_pg_url(migration_url)[3]
        run_url = snapshot["TEST_DATABASE_URL"]
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(run_url.replace("postgresql+asyncpg://", "postgresql://", 1))
        userinfo, _, hostport = parts.netloc.rpartition("@")
        password = userinfo.partition(":")[2]
        new_userinfo = f"{mig_user}:{password}" if password else mig_user
        as_bootstrap = urlunsplit(
            (parts.scheme, f"{new_userinfo}@{hostport}", parts.path, parts.query, parts.fragment)
        )
        os.environ["TEST_DATABASE_URL"] = as_bootstrap
        os.environ["DATABASE_URL"] = as_bootstrap
        with pytest.raises(GuardRefused, match="migration/bootstrap user"):
            verify_task_database_ownership_sync()
        assert counter.launches == 0
    finally:
        support.subprocess.run = original_run
        _restore_env(snapshot)


@pytest.mark.integration
async def test_f1_guard_engine_bound_to_foreign_user_refuses():
    """[NEGATIVE — expected PASS via refusal] The engine-binding helper must
    reject an engine URL bound to anything but the declared run user
    (bootstrap or undeclared) — the fixture's real check, fed directly."""

    class _FakeURL:
        def __init__(self, host, port, database, username):
            self.host = host
            self.port = port
            self.database = database
            self.username = username

    host, port, dbname, run_user = _parse_pg_url(os.environ["TEST_DATABASE_URL"])
    for foreign in (os.environ[MIGRATION_URL_ENV_VAR].split("://", 1)[1].split(":", 1)[0], "undeclared_user"):
        with pytest.raises(GuardRefused, match="not the declared test-session user"):
            _assert_engine_binding(
                _FakeURL(host, port, dbname, foreign),
                host=host, port=port, dbname=dbname, username=run_user,
            )
    # The correct binding passes.
    _assert_engine_binding(
        _FakeURL(host, port, dbname, run_user),
        host=host, port=port, dbname=dbname, username=run_user,
    )


# ---------------------------------------------------------------------------
# 4. SUBPROCESS CONTRACT: only the migration URL crosses the process boundary
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_f1_migration_subprocess_env_carries_only_migration_url(monkeypatch):
    """[CONTRACT — expected PASS] The migration subprocess receives the
    migration URL as its DATABASE_URL; the parent environment is untouched.

    执行入口: the real ``run_public_migrations`` (subprocess execution
    intercepted ONLY to capture the child env; the real end-to-end migration
    is proven by the positive lifecycle node).
    """
    import tests.mpango_invariants_r0_support as support

    monkeypatch.delenv(MIGRATION_LOG_ENV_VAR, raising=False)
    migration_url = os.environ[MIGRATION_URL_ENV_VAR].strip()
    parent_before = dict(os.environ)
    captured = {}

    def capturing_run(*args, **kwargs):
        captured["argv"] = list(args[0])
        captured["env"] = dict(kwargs.get("env") or {})
        return _Completed()

    original_run = support.subprocess.run
    support.subprocess.run = capturing_run
    try:
        run_public_migrations(migration_url)
    finally:
        support.subprocess.run = original_run
    assert captured["env"].get("DATABASE_URL") == migration_url, (
        "F1_SUBPROCESS_CONTRACT: the migration child must receive exactly "
        "the declared migration URL as DATABASE_URL (never the run-session "
        "URL, never alembic.ini defaults)."
    )
    assert captured["argv"][1:4] == ["-m", "alembic", "upgrade"], (
        "F1_SUBPROCESS_CONTRACT: expected the alembic upgrade subprocess."
    )
    assert dict(os.environ) == parent_before, (
        "F1_SUBPROCESS_CONTRACT: the parent process environment must remain "
        "untouched (no global env switching)."
    )


# ---------------------------------------------------------------------------
# 5. SANITIZATION (CTO F2): the refusal CONTENT must carry no task secret
# ---------------------------------------------------------------------------

_SYNTH_MIG_PW = "s3cr3tpw"  # pragma: allowlist secret  -- synthetic; these nodes
_SYNTH_REP_PW = "repPw9xZ"  # pragma: allowlist secret  -- prove it gets stripped


def _synthetic_secret_env(monkeypatch, *, migration_url, reporting_pw):
    """Declare a fully synthetic task env for sanitizer-content tests."""
    monkeypatch.setenv(MIGRATION_URL_ENV_VAR, migration_url)
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://run:runpw@127.0.0.1:1/inv")  # pragma: allowlist secret
    monkeypatch.setenv("DATABASE_URL", "postgresql://run:runpw@127.0.0.1:1/inv")  # pragma: allowlist secret
    monkeypatch.setenv("REPORTING_USER_PASSWORD", reporting_pw)


class _Failed:
    returncode = 1

    def __init__(self, stdout, stderr):
        self.stdout = stdout
        self.stderr = stderr


def _capture_refusal(monkeypatch, *, result, migration_url) -> str:
    """Run the REAL run_public_migrations against a fake subprocess result
    and return the FULL exception text for content assertions. The evidence
    log env is removed so fake results never pollute the task's migration
    evidence file."""
    import tests.mpango_invariants_r0_support as support

    monkeypatch.delenv(MIGRATION_LOG_ENV_VAR, raising=False)

    original_run = support.subprocess.run
    support.subprocess.run = lambda *a, **k: result
    try:
        with pytest.raises(GuardRefused) as excinfo:
            run_public_migrations(migration_url)
        return str(excinfo.value)
    finally:
        support.subprocess.run = original_run


@pytest.mark.integration
def test_f1_sanitization_url_password_absent_from_refusal(monkeypatch):
    """[CONTRACT — expected PASS] Both output channels: the migration URL's
    password (raw AND URL-encoded form) must be absent from the refusal text
    while the category stays GUARD_REFUSED_MIGRATION."""
    url = f"postgresql://mig:{_SYNTH_MIG_PW}@127.0.0.1:5432/inv"
    from urllib.parse import quote_plus

    encoded = quote_plus(_SYNTH_MIG_PW)
    _synthetic_secret_env(monkeypatch, migration_url=url, reporting_pw=_SYNTH_REP_PW)
    text = _capture_refusal(
        monkeypatch,
        result=_Failed(
            stdout=f"running against {url} ...",
            stderr=f"connect failed for postgresql://mig:{encoded}@127.0.0.1:5432/inv",
        ),
        migration_url=url,
    )
    assert "GUARD_REFUSED_MIGRATION" in text
    assert _SYNTH_MIG_PW not in text and encoded not in text, (
        "F1_SANITIZATION: the migration URL password (raw or URL-encoded) "
        f"must not survive in the refusal text: {text[:200]!r}"
    )
    assert "mig:s3cr3tpw" not in text, (
        "F1_SANITIZATION: URL user:password shape must be redacted."
    )


@pytest.mark.integration
def test_f1_sanitization_reporting_password_absent_from_refusal(monkeypatch):
    """[CONTRACT — expected PASS] An INDEPENDENT reporting password (as
    embedded by migration 011's CREATE USER ... PASSWORD SQL in an error)
    must be absent from the refusal text."""
    url = f"postgresql://mig:{_SYNTH_MIG_PW}@127.0.0.1:5432/inv"
    _synthetic_secret_env(monkeypatch, migration_url=url, reporting_pw=_SYNTH_REP_PW)
    text = _capture_refusal(
        monkeypatch,
        result=_Failed(
            stdout="alembic running 011_s6_p_reporting_role",
            stderr=(
                "sqlalchemy.exc.ProgrammingError: ... CREATE USER "
                f"reporting_user WITH PASSWORD '{_SYNTH_REP_PW}' ... failed"
            ),
        ),
        migration_url=url,
    )
    assert "GUARD_REFUSED_MIGRATION" in text
    assert _SYNTH_REP_PW not in text, (
        "F1_SANITIZATION: REPORTING_USER_PASSWORD (SQL-embedded form) must "
        f"not survive in the refusal text: {text[:200]!r}"
    )


@pytest.mark.integration
def test_f1_sanitization_timeout_branch_sanitized(monkeypatch):
    """[CONTRACT — expected PASS] The TIMEOUT exit follows the same strategy:
    partial output carried by TimeoutExpired is sanitized and categorized —
    constructed offline (no long-running process is started)."""
    import subprocess as _subprocess

    url = f"postgresql://mig:{_SYNTH_MIG_PW}@127.0.0.1:5432/inv"
    _synthetic_secret_env(monkeypatch, migration_url=url, reporting_pw=_SYNTH_REP_PW)
    expired = _subprocess.TimeoutExpired(
        cmd=["python", "-m", "alembic", "upgrade", "head"],
        timeout=300,
    )
    expired.stdout = f"partial stdout ... {url} ..."
    expired.stderr = f"partial stderr ... password '{_SYNTH_REP_PW}' ..."
    import tests.mpango_invariants_r0_support as support

    monkeypatch.delenv(MIGRATION_LOG_ENV_VAR, raising=False)
    original_run = support.subprocess.run

    def raise_timeout(*a, **k):
        raise expired

    support.subprocess.run = raise_timeout
    try:
        with pytest.raises(GuardRefused) as excinfo:
            run_public_migrations(url)
        text = str(excinfo.value)
    finally:
        support.subprocess.run = original_run
    assert "GUARD_REFUSED_MIGRATION" in text and "TIMED OUT" in text
    assert _SYNTH_MIG_PW not in text and _SYNTH_REP_PW not in text, (
        "F1_SANITIZATION: the timeout exit must sanitize partial output the "
        f"same way as the rc!=0 branch: {text[:200]!r}"
    )

# ---------------------------------------------------------------------------
# 6. COUNTER FORMS (CTO F1) and REAL fixture-order wrong-target proof
# ---------------------------------------------------------------------------

class _NoIODelegate:
    """Offline sentinel executor: records delegations, executes nothing."""

    def __init__(self):
        self.delegated = 0

    def __call__(self, *args, **kwargs):
        self.delegated += 1
        return _Completed()


def test_f1_counter_records_positional_argv_migration_call():
    """[COUNTER — expected PASS] ``subprocess.run(argv, ...)`` (the form the
    candidate's run_public_migrations actually uses) counts as ONE migration
    launch and does NOT reach the delegate."""
    counter = _LaunchCounter(_NoIODelegate())
    argv = [r"C:\python\python.exe", "-m", "alembic", "upgrade", "head"]
    counter(argv, cwd="x", capture_output=True)
    assert counter.launches == 1, (
        f"F1_COUNTER: positional-argv migration call must count 1, got {counter.launches}"
    )
    assert counter.delegated == 0, (
        "F1_COUNTER: a counted migration must NOT be forwarded to the real executor."
    )


def test_f1_counter_records_keyword_args_migration_call():
    """[COUNTER — expected PASS] ``subprocess.run(args=argv, ...)`` counts
    the same way."""
    counter = _LaunchCounter(_NoIODelegate())
    argv = ["/usr/bin/python", "-m", "alembic", "upgrade", "head"]
    counter(args=argv, cwd="x")
    assert counter.launches == 1 and counter.delegated == 0


def test_f1_counter_delegates_non_migration_once():
    """[COUNTER — expected PASS] A non-migration command (docker inspect
    shape) is delegated exactly once and never counted as a migration."""
    delegate = _NoIODelegate()
    counter = _LaunchCounter(delegate)
    counter(["docker", "inspect", "--format", "{{json .}}", "c"], capture_output=True)
    counter(args=["docker", "ps"], text=True)
    assert counter.launches == 0
    assert counter.delegated == 2 and delegate.delegated == 2


def test_f1_counter_malformed_shapes_delegate_uncounted():
    """[COUNTER — expected PASS] Unclassifiable call shapes delegate (never
    guessed into the migration bucket, never swallowed)."""
    delegate = _NoIODelegate()
    counter = _LaunchCounter(delegate)
    counter()
    counter(args=None)
    counter("python")  # bare string, not an argv list
    counter(args=42)
    assert counter.launches == 0, "malformed shapes must never count as migrations"
    assert counter.delegated == 4


@pytest.mark.integration
async def test_f1_wrong_target_refused_before_migration_in_real_fixture_order(monkeypatch):
    """[ORDERING — expected PASS via refusal] The REAL fixture stage order:
    the guard refuses a wrong migration target BEFORE any migration launch.

    Drives ``_r0_task_database_stages`` — the exact function pytest executes
    for the session fixture — under a mutated (wrong-database) migration URL
    with an offline launch sentinel. The refusal must surface as the
    ownership GuardRefused with ZERO migration launches; the sentinel also
    proves docker inspect delegations may happen (guard evidence) while the
    migration never starts. The wrong target never reaches any real
    database. NOTE (scope): this counts launches from the start of the REAL
    stage sequence — it does not claim anything about other pytest sessions.
    """
    import tests.mpango_invariants_r0_support as support
    from tests.mpango_invariants_r0_support import _r0_task_database_stages

    snapshot = _env_snapshot()
    sentinel = _LaunchCounter(_NoIODelegate())
    original_run = support.subprocess.run
    support.subprocess.run = sentinel
    base = snapshot[MIGRATION_URL_ENV_VAR]
    # Mutate to a wrong DATABASE on the same host/port (binding violation).
    mutated = base.rsplit("/", 1)[0] + "/definitely_not_the_task_db"
    assert mutated != base
    monkeypatch.setenv(MIGRATION_URL_ENV_VAR, mutated)
    try:
        with pytest.raises(GuardRefused, match="GUARD_REFUSED_DATABASE_OWNERSHIP"):
            stages = _r0_task_database_stages()
            try:
                await stages.__anext__()
            finally:
                await stages.aclose()
        assert sentinel.launches == 0, (
            "F1_ORDERING: through the REAL fixture stage order, a wrong "
            "migration target must be refused BEFORE any migration launch "
            f"(launches={sentinel.launches})."
        )
    finally:
        support.subprocess.run = original_run
        _restore_env(snapshot)
