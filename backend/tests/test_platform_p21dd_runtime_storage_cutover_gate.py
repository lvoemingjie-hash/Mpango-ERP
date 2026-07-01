"""P21-D-D focused tests: runtime storage cutover gate (P20 service -> durable).

Proves the P21-D-D runtime storage cutover: the P20 durable approval service
now runs against the P21-D-C durable store adapter behind an EXPLICIT readiness
gate, with the in-memory store retained ONLY as an explicit test / dev memory
backend. The cutover is exercised at the SERVICE layer (the gate lives in
``api.v1.platform.p20.services``) and at the ROUTE layer (503 on a not-ready
store), against an EPHEMERAL, self-contained PostgreSQL database (never the
developer ``mpango_erp`` / ``mpango_postgres`` database).

Coverage (the directive's required surface):
  - storage-mode resolver: default DURABLE; env MEMORY; test override precedence;
    closed DurableStoreNotReady vocabulary.
  - readiness gate: ready on a migrated DB; storage_not_ready when the P21-C1
    schema / tables are absent; unavailable when the DB is unreachable.
  - durable create / list / read / decision flow through the DB adapter
    (storage == "durable"), restart-safe across a NEW session / adapter.
  - store NOT ready: create and decision raise DurableStoreNotReady and return a
    503 from the route; they do NOT silently succeed and do NOT write the
    in-memory _STORE (no silent memory fallback in durable mode).
  - degraded path: a store that passes the table check but fails mid-operation
    fails CLOSED to a degraded DurableStoreNotReady.
  - idempotency digest preserved across durable storage; maker-checker identity
    binding enforced; quorum of distinct checkers enforced; approve requires an
    available source; approval NEVER executes (execution_allowed / executed
    False, execution_gate "blocked").
  - memory mode is explicit and marked storage == "memory".
  - the explicit mapper (_from_durable_record) fails CLOSED on a violating record.

Self-contained ephemeral DB: a throwaway ``postgres:15`` container hosts three
databases -- ``p21dd_mig`` (migration 020 applied => ready), ``p21dd_bare``
(bootstrapped prerequisites only => schema missing), and ``p21dd_shell`` (the
five durable table NAMES as empty shells => readiness passes but an insert fails
=> degraded). It REFUSES to run without docker (skip, not fail); when docker is
available every test runs for real.

Approval is not execution, and durability is not execution. The concrete adapter
stays ``is_live_store == False``; the P20 service gate decides durability at
runtime. No P18 action is ever executed.
"""
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from api.v1.platform.p20 import services as p20svc
from api.v1.platform.p21 import adapter as p21a
from api.v1.platform.p21.models import DurableApprovalRequest

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]

os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")
os.environ.setdefault("PLATFORM_OPERATOR_SECRET", "test-operator-secret")

P20_BASE = "/api/v1/platform/p20"
DURABLE = f"{P20_BASE}/durable-approvals"
AUTH_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}

TENANT_ID = "b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d"
FUTURE = datetime(2099, 1, 1, tzinfo=timezone.utc)
REQUIRED_TABLES = (
    "durable_approval_requests",
    "durable_approval_decisions",
    "durable_approval_audit_events",
    "durable_approval_idempotency_keys",
    "durable_approval_retention_jobs",
)


# ---------------------------------------------------------------------------
# Ephemeral, self-contained PostgreSQL (throwaway container; never mpango_erp)
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True, timeout=20)
        return True
    except Exception:
        return False


def _wait_postgres(sync_url: str, timeout: float = 60.0) -> None:
    import psycopg2

    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            conn = psycopg2.connect(sync_url)
            conn.close()
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.5)
    raise RuntimeError(f"postgres container not ready within {timeout}s: {last}")


def _bootstrap(sync_url: str) -> None:
    """Test-only DB init mirroring database/init.sql (self-contained repro)."""
    import psycopg2

    conn = psycopg2.connect(sync_url)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'alembic_version')"
        )
        has_av = cur.fetchone()[0]
        if has_av:
            cur.execute(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'alembic_version' "
                "AND column_name = 'version_num'"
            )
            row = cur.fetchone()
            length = row[0] if row else 0
            if length is None or length < 128:
                cur.execute(
                    "ALTER TABLE public.alembic_version "
                    "ALTER COLUMN version_num TYPE varchar(128)"
                )
        else:
            cur.execute(
                "CREATE TABLE public.alembic_version "
                "(version_num varchar(128) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
            )
        cur.execute("CREATE SCHEMA IF NOT EXISTS t_dev")
    finally:
        cur.close()
        conn.close()


def _create_database(admin_sync_url: str, new_db: str) -> None:
    """CREATE DATABASE via an autocommit admin connection (cannot run in a txn)."""
    import psycopg2

    conn = psycopg2.connect(admin_sync_url)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (new_db,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{new_db}"')
    finally:
        cur.close()
        conn.close()


def _make_shell_tables(sync_url: str) -> None:
    """Create the five durable table NAMES as empty shells (no columns/enums).

    Readiness counts these as present, but an adapter INSERT fails (wrong
    columns / missing enums) -> exercises the degraded fail-closed path.
    """
    import psycopg2

    conn = psycopg2.connect(sync_url)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        for t in REQUIRED_TABLES:
            cur.execute(f'CREATE TABLE IF NOT EXISTS public."{t}" (x int)')
    finally:
        cur.close()
        conn.close()


def _restore_env(snapshot: dict) -> None:
    """Restore os.environ keys captured before a fixture mutated them.

    Test isolation: the durable integration fixtures point DATABASE_URL (and
    setdefault REPORTING_USER_PASSWORD) at a throwaway container, then tear the
    container down. Without restoring, later suites in the same pytest process
    read a dead DATABASE_URL and error. A None snapshot value means the key was
    absent and is popped; otherwise the prior value is restored.
    """
    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(scope="module")
def durable_urls():
    """One throwaway container hosting three databases (mig / bare / shell)."""
    # Snapshot the env BEFORE this fixture mutates it, so the finally can restore
    # it (test isolation -- no leaked dead DATABASE_URL to later suites).
    _env = {
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "REPORTING_USER_PASSWORD": os.environ.get("REPORTING_USER_PASSWORD"),
    }
    if not _docker_available():
        pytest.skip("docker not available; cannot start an ephemeral postgres container")
    container = f"p21dd-ephemeral-{uuid4().hex[:10]}"
    subprocess.run(["docker", "rm", "-f", container], capture_output=True)
    run = subprocess.run(
        [
            "docker", "run", "-d", "--name", container,
            "-e", "POSTGRES_PASSWORD=p21dd",  # pragma: allowlist secret
            "-e", "POSTGRES_DB=p21dd_mig",
            "-P", "postgres:15",
        ],
        capture_output=True, text=True, timeout=180,
    )
    if run.returncode != 0:
        pytest.skip(f"could not start ephemeral postgres container: {run.stderr.strip()}")
    try:
        port_out = subprocess.run(
            ["docker", "port", container, "5432/tcp"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if not port_out:
            pytest.skip("could not resolve ephemeral postgres host port")
        host_port = port_out.splitlines()[0].rsplit(":", 1)[1]
        mig_async = f"postgresql+asyncpg://postgres:p21dd@127.0.0.1:{host_port}/p21dd_mig"  # pragma: allowlist secret
        mig_sync = f"postgresql://postgres:p21dd@127.0.0.1:{host_port}/p21dd_mig"  # pragma: allowlist secret
        admin_sync = f"postgresql://postgres:p21dd@127.0.0.1:{host_port}/postgres"  # pragma: allowlist secret
        # Refuse any chance of landing on the developer DB.
        for u in (mig_async, mig_sync, admin_sync):
            assert "mpango_erp" not in u.lower()
            assert "mpango_postgres" not in u.lower()
        _wait_postgres(mig_sync)
        _bootstrap(mig_sync)
        # Create + bootstrap the bare and shell databases (no migration on them).
        _create_database(admin_sync, "p21dd_bare")
        bare_sync = f"postgresql://postgres:p21dd@127.0.0.1:{host_port}/p21dd_bare"  # pragma: allowlist secret
        _wait_postgres(bare_sync)
        _bootstrap(bare_sync)
        _create_database(admin_sync, "p21dd_shell")
        shell_sync = f"postgresql://postgres:p21dd@127.0.0.1:{host_port}/p21dd_shell"  # pragma: allowlist secret
        _wait_postgres(shell_sync)
        _bootstrap(shell_sync)
        _make_shell_tables(shell_sync)
        # Run migration 020 (head) on the migrated database only.
        os.environ["DATABASE_URL"] = mig_async
        os.environ.setdefault("REPORTING_USER_PASSWORD", "ephemeral_reporting_pw")
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        command.upgrade(cfg, "head")
        yield {
            "mig_async": mig_async,
            "mig_sync": mig_sync,
            "bare_async": f"postgresql+asyncpg://postgres:p21dd@127.0.0.1:{host_port}/p21dd_bare",  # pragma: allowlist secret
            "shell_async": f"postgresql+asyncpg://postgres:p21dd@127.0.0.1:{host_port}/p21dd_shell",  # pragma: allowlist secret
        }
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
        _restore_env(_env)  # test isolation: do not leak the throwaway DATABASE_URL


@pytest.fixture(scope="module")
async def mig_engine(durable_urls):
    eng = create_async_engine(durable_urls["mig_async"], future=True)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture(scope="module")
async def bare_engine(durable_urls):
    eng = create_async_engine(durable_urls["bare_async"], future=True)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture(scope="module")
async def shell_engine(durable_urls):
    eng = create_async_engine(durable_urls["shell_async"], future=True)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture(autouse=True)
async def _mode_and_clean():
    """Default to DURABLE mode; clear any leaked in-memory state per test."""
    p20svc.set_storage_mode("durable")
    p20svc.reset_store()
    yield
    p20svc.set_storage_mode(None)


@pytest.fixture(autouse=True)
async def _truncate_migrated(mig_engine):
    """Clean durable tables before each test (isolated, deterministic)."""
    async with mig_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE public.durable_approval_decisions, "
                "public.durable_approval_retention_jobs, "
                "public.durable_approval_audit_events, "
                "public.durable_approval_idempotency_keys, "
                "public.durable_approval_requests CASCADE"
            )
        )
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session(engine) -> AsyncSession:
    session = AsyncSession(engine, expire_on_commit=False)
    try:
        from db.tenant_filter import mark_session_as_system

        mark_session_as_system(session, reason="p21dd_cutover_test")
    except Exception:
        pass
    return session


def _enable_available_source(monkeypatch) -> None:
    """Patch the P18 source resolver to 'available' so approve can reach quorum."""
    async def _available(action_type, tenant_id, db):  # noqa: ANN001
        return "available"

    monkeypatch.setattr(
        "api.v1.platform.p18.services._resolve_action_source_status", _available
    )


async def _create(session, **over):
    kw = dict(
        action_id=None, tenant_id=TENANT_ID, action_type="tenant.pause", maker=None,
        reason="planned durable approval for maintenance", idempotency_key="create-A",
        expires_at=FUTURE, durable_retain_until=FUTURE, confirm=True, correlation_id=None,
        metadata=None, actor="maker-1", actor_role="super_admin", identity_context="identity_only",
        db=session,
    )
    kw.update(over)
    return await p20svc.create_durable_approval(**kw)


async def _decide(approval_id, session, **over):
    kw = dict(
        decision="approve", approver_id=None, reason="approved after durable review",
        idempotency_key="decide-Z", confirm=True, correlation_id=None, metadata=None,
        actor="checker-2", actor_role="super_admin", identity_context="identity_only", db=session,
    )
    kw.update(over)
    return await p20svc.submit_decision(approval_id, **kw)


async def _count(session, model) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


# ---------------------------------------------------------------------------
# 1. Storage-mode resolver + closed vocabulary (pure; no DB)
# ---------------------------------------------------------------------------


class TestStorageModeResolver:
    def test_default_mode_is_durable(self, monkeypatch):
        monkeypatch.delenv("MPANGO_P20_DURABLE_APPROVAL_STORAGE", raising=False)
        p20svc.set_storage_mode(None)
        assert p20svc.get_storage_mode() == p20svc.STORAGE_MODE_DURABLE

    def test_env_memory_flag_selects_memory(self, monkeypatch):
        monkeypatch.setenv("MPANGO_P20_DURABLE_APPROVAL_STORAGE", "memory")
        p20svc.set_storage_mode(None)
        assert p20svc.get_storage_mode() == p20svc.STORAGE_MODE_MEMORY
        # Any other value stays durable (no silent memory activation).
        monkeypatch.setenv("MPANGO_P20_DURABLE_APPROVAL_STORAGE", "auto")
        assert p20svc.get_storage_mode() == p20svc.STORAGE_MODE_DURABLE

    def test_override_takes_precedence_over_env(self, monkeypatch):
        monkeypatch.setenv("MPANGO_P20_DURABLE_APPROVAL_STORAGE", "memory")
        p20svc.set_storage_mode("durable")
        assert p20svc.get_storage_mode() == "durable"
        p20svc.set_storage_mode(None)

    def test_set_storage_mode_rejects_unknown_mode(self):
        with pytest.raises(ValueError):
            p20svc.set_storage_mode("redis")
        p20svc.set_storage_mode(None)

    def test_durable_store_not_ready_closed_vocabulary(self):
        for code in ("storage_not_ready", "unavailable", "degraded"):
            exc = p20svc.DurableStoreNotReady(code, "x")
            assert exc.code == code
        with pytest.raises(ValueError):
            p20svc.DurableStoreNotReady("totally_invented_code")


# ---------------------------------------------------------------------------
# 2. Readiness gate (ready / storage_not_ready / unavailable)
# ---------------------------------------------------------------------------


class TestReadinessGate:
    async def test_ready_on_migrated_db(self, mig_engine):
        async with _session(mig_engine) as session:
            ready, code = await p20svc._check_durable_readiness(session)
        assert ready is True
        assert code == "ready"

    async def test_storage_not_ready_when_schema_missing(self, bare_engine):
        async with _session(bare_engine) as session:
            ready, code = await p20svc._check_durable_readiness(session)
        assert ready is False
        assert code == "storage_not_ready"

    async def test_unavailable_when_db_unreachable(self):
        # A closed port: the information_schema query cannot run -> unavailable.
        eng = create_async_engine(
            "postgresql+asyncpg://postgres:x@127.0.0.1:9/p21dd_nope",  # pragma: allowlist secret
            future=True,
        )
        try:
            async with _session(eng) as session:
                ready, code = await p20svc._check_durable_readiness(session)
            assert ready is False
            assert code == "unavailable"
        finally:
            await eng.dispose()

    async def test_shell_schema_passes_table_count(self, shell_engine):
        # Five shell table NAMES exist -> the count check passes (the subsequent
        # operation then fails, exercising the degraded path elsewhere).
        async with _session(shell_engine) as session:
            ready, code = await p20svc._check_durable_readiness(session)
        assert ready is True
        assert code == "ready"


# ---------------------------------------------------------------------------
# 3. Durable create / read / list / decision through the DB adapter
# ---------------------------------------------------------------------------


class TestDurableHappyPath:
    async def test_create_records_durable_and_no_execution(self, mig_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        async with _session(mig_engine) as session:
            rec = await _create(session)
        assert rec.result == "recorded"
        assert rec.state == "pending_review"
        assert rec.storage == "durable"
        assert rec.execution_allowed is False
        assert rec.executed is False
        assert rec.execution_gate == "blocked"
        assert rec.redaction_applied is True
        assert rec.action_class == "write"
        assert rec.quorum_required == 2
        assert rec.maker == "maker-1"  # bound to the authenticated actor
        assert rec.approval_id is not None

    async def test_create_persists_to_durable_table(self, mig_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        async with _session(mig_engine) as session:
            rec = await _create(session)
            approval_id = rec.approval_id
        async with _session(mig_engine) as session:
            assert await _count(session, DurableApprovalRequest) == 1
            row = (
                await session.execute(
                    select(DurableApprovalRequest).where(
                        DurableApprovalRequest.approval_id == approval_id
                    )
                )
            ).scalar_one()
            assert row.storage_class == "durable"
            assert row.execution_allowed is False
            assert row.executed is False
            assert row.execution_gate == "blocked"

    async def test_durable_read_returns_record(self, mig_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        async with _session(mig_engine) as session:
            created = await _create(session)
            approval_id = created.approval_id
            read = await p20svc.read_durable_approval(approval_id, db=session)
        assert read is not None
        assert read.approval_id == approval_id
        assert read.storage == "durable"
        assert read.executed is False

    async def test_durable_read_not_found_returns_none(self, mig_engine):
        async with _session(mig_engine) as session:
            read = await p20svc.read_durable_approval(str(uuid4()), db=session)
        assert read is None

    async def test_durable_list_filters_and_marks_durable(self, mig_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        async with _session(mig_engine) as session:
            await _create(session, idempotency_key="k-a")
            await _create(session, idempotency_key="k-b", actor="maker-2")
            queue = await p20svc.list_durable_approvals(db=session)
        assert queue.total == 2
        assert queue.storage == "durable"
        assert queue.executed is False
        assert all(it.storage == "durable" for it in queue.items)
        assert all(it.execution_allowed is False for it in queue.items)


# ---------------------------------------------------------------------------
# 4. Restart / reload proof (NEW session reads persisted state)
# ---------------------------------------------------------------------------


class TestRestartSafety:
    async def test_create_survives_new_session(self, mig_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        # Session A: create + one approve, then close (simulated restart).
        async with _session(mig_engine) as session_a:
            created = await _create(session_a, actor="maker-1")
            approval_id = created.approval_id
            await _decide(approval_id, session_a, actor="checker-2", idempotency_key="d1")
        # Session B (NEW): the durable read returns the persisted state.
        async with _session(mig_engine) as session_b:
            read = await p20svc.read_durable_approval(approval_id, db=session_b)
        assert read is not None
        assert read.approval_id == approval_id
        assert read.state == "pending_review"  # survived restart
        assert len(read.checkers) == 1
        assert read.checkers[0].checker_id == "checker-2"
        # The in-memory store was NEVER used (no silent memory fallback).
        assert approval_id not in p20svc._STORE


# ---------------------------------------------------------------------------
# 5. Idempotency digest preserved across durable storage
# ---------------------------------------------------------------------------


class TestDurableIdempotency:
    async def test_duplicate_create_returns_original(self, mig_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        async with _session(mig_engine) as session:
            first = await _create(session, idempotency_key="dup-k")
            second = await _create(session, idempotency_key="dup-k")
        assert first.result == "recorded"
        assert second.result == "duplicate"
        assert second.approval_id == first.approval_id
        async with _session(mig_engine) as session:
            assert await _count(session, DurableApprovalRequest) == 1

    async def test_create_conflict_on_same_key_different_payload(self, mig_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        async with _session(mig_engine) as session:
            first = await _create(session, idempotency_key="conf-k", reason="reason A")
            conflict = await _create(session, idempotency_key="conf-k", reason="reason B")
        assert first.result == "recorded"
        assert conflict.result == "conflict"

    async def test_create_key_digest_only_no_raw_in_db(self, mig_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        raw = "super-secret-create-key-123456"  # pragma: allowlist secret
        async with _session(mig_engine) as session:
            rec = await _create(session, idempotency_key=raw)
            assert rec.idempotency_key_digest == p21a._digest(raw)
        async with _session(mig_engine) as session:
            blob = (
                await session.execute(
                    text("SELECT row_to_json(t)::text FROM public.durable_approval_requests t")
                )
            ).scalar_one()
            assert raw not in blob


# ---------------------------------------------------------------------------
# 6. Maker-checker + quorum + source-honesty on the durable path
# ---------------------------------------------------------------------------


class TestDurableDualControl:
    async def test_maker_cannot_self_decide(self, mig_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        async with _session(mig_engine) as session:
            created = await _create(session, actor="maker-1")
            self_dec = await _decide(created.approval_id, session, actor="maker-1")
        assert self_dec.result == "denied"
        assert self_dec.storage == "durable"

    async def test_quorum_requires_two_distinct_checkers(self, mig_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        async with _session(mig_engine) as session:
            created = await _create(session, actor="maker-1")
            aid = created.approval_id
            first = await _decide(aid, session, actor="checker-2", idempotency_key="d1")
            second = await _decide(aid, session, actor="checker-3", idempotency_key="d2")
        assert first.result == "quorum_pending"
        assert second.result == "approved"
        assert second.state == "approved_execution_blocked"
        assert second.quorum_met is True
        assert second.executed is False  # quorum still does NOT execute
        assert second.execution_allowed is False
        ids = {c.checker_id for c in second.checkers}
        assert ids == {"checker-2", "checker-3"}
        assert "maker-1" not in ids

    async def test_reject_is_final(self, mig_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        async with _session(mig_engine) as session:
            created = await _create(session, actor="maker-1")
            aid = created.approval_id
            rej = await _decide(aid, session, actor="checker-2", decision="reject", idempotency_key="r1")
            later = await _decide(aid, session, actor="checker-3", decision="approve", idempotency_key="a1")
        assert rej.result == "rejected"
        assert rej.state == "rejected"
        assert later.result == "conflict"

    async def test_approve_denied_against_unknown_source(self, mig_engine, monkeypatch):
        # Patch the resolver to 'unknown' -> source-honesty denies the approve.
        async def _unknown(action_type, tenant_id, db):  # noqa: ANN001
            return "unknown"

        monkeypatch.setattr(
            "api.v1.platform.p18.services._resolve_action_source_status", _unknown
        )
        async with _session(mig_engine) as session:
            created = await _create(session, actor="maker-1")
            assert created.validation_status == "source_unknown"  # stored honestly
            approve = await _decide(created.approval_id, session, actor="checker-2")
        assert approve.result == "denied"  # source-honesty: unknown cannot approve

    async def test_payload_approver_mismatch_denied(self, mig_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        async with _session(mig_engine) as session:
            created = await _create(session, actor="maker-1")
            spoof = await _decide(
                created.approval_id, session, actor="checker-2", approver_id="evil-checker",
            )
        assert spoof.result == "denied"


# ---------------------------------------------------------------------------
# 7. Store NOT ready -> fail CLOSED, no silent memory fallback
# ---------------------------------------------------------------------------


class TestStoreNotReady:
    async def test_create_raises_and_writes_no_memory(self, bare_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        async with _session(bare_engine) as session:
            with pytest.raises(p20svc.DurableStoreNotReady) as ei:
                await _create(session)
        assert ei.value.code == "storage_not_ready"
        # No silent memory fallback: the in-memory store stayed empty.
        assert p20svc._STORE == {}
        assert p20svc._STORE_BY_CREATE_KEY == {}

    async def test_decision_raises_and_writes_no_memory(self, mig_engine, bare_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        # Create on the ready store first so the approval exists durably.
        async with _session(mig_engine) as session:
            created = await _create(session, actor="maker-1")
            approval_id = created.approval_id
        # A decision against the NOT-ready bare store fails closed.
        async with _session(bare_engine) as session:
            with pytest.raises(p20svc.DurableStoreNotReady) as ei:
                await _decide(approval_id, session, actor="checker-2")
        assert ei.value.code == "storage_not_ready"
        assert p20svc._STORE == {}

    async def test_read_and_list_raise_when_not_ready(self, bare_engine):
        async with _session(bare_engine) as session:
            with pytest.raises(p20svc.DurableStoreNotReady):
                await p20svc.read_durable_approval(str(uuid4()), db=session)
            with pytest.raises(p20svc.DurableStoreNotReady):
                await p20svc.list_durable_approvals(db=session)

    async def test_no_silent_memory_fallback_record_returned(self, bare_engine, monkeypatch):
        """A not-ready durable create must not return a storage='memory' record."""
        _enable_available_source(monkeypatch)
        async with _session(bare_engine) as session:
            with pytest.raises(p20svc.DurableStoreNotReady):
                rec = await _create(session)
                # If this line is reached the gate failed closed incorrectly.
                assert rec.storage != "memory"

    async def test_not_ready_leaks_no_raw_key_or_reason(self, bare_engine, monkeypatch):
        """The gate failure must never echo the raw idempotency_key / reason, and
        must not write the in-memory store (no silent memory fallback)."""
        _enable_available_source(monkeypatch)
        raw_key = "super-secret-not-ready-key-99"  # pragma: allowlist secret
        secret_reason = "creds token=OH-NO-SECRET"  # pragma: allowlist secret
        async with _session(bare_engine) as session:
            with pytest.raises(p20svc.DurableStoreNotReady) as ei:
                await _create(session, idempotency_key=raw_key, reason=secret_reason)
        blob = str(ei.value) + ei.value.code + (ei.value.reason or "")
        assert raw_key not in blob
        assert "OH-NO-SECRET" not in blob
        assert raw_key not in p20svc._STORE_BY_CREATE_KEY
        assert p20svc._STORE == {}


# ---------------------------------------------------------------------------
# 8. Degraded path (readiness passes, operation fails) -> fail CLOSED
# ---------------------------------------------------------------------------


class TestDegradedPath:
    async def test_create_degraded_when_op_fails_after_readiness(self, shell_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        async with _session(shell_engine) as session:
            with pytest.raises(p20svc.DurableStoreNotReady) as ei:
                await _create(session)
        assert ei.value.code == "degraded"
        assert p20svc._STORE == {}


# ---------------------------------------------------------------------------
# 9. Explicit memory mode (test / dev) is marked storage='memory'
# ---------------------------------------------------------------------------


class TestExplicitMemoryMode:
    async def test_memory_mode_uses_in_memory_store(self, mig_engine):
        p20svc.set_storage_mode("memory")
        p20svc.reset_store()
        # The memory backend does not touch the DB; a mock db is fine.
        from unittest.mock import AsyncMock, MagicMock

        db = MagicMock()
        ok = MagicMock()
        ok.scalar.return_value = 0
        ok.scalar_one_or_none.return_value = None
        ok.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=ok)
        queue = await p20svc.list_durable_approvals(db=db)
        assert queue.storage == "memory"
        assert queue.total == 0
        p20svc.set_storage_mode(None)


# ---------------------------------------------------------------------------
# 10. Explicit mapper fails CLOSED on a violating record
# ---------------------------------------------------------------------------


class TestMapperFailClosed:
    def test_mapper_rejects_execution_allowed_true(self):
        from api.v1.platform.p20.schemas import DurableApprovalRecord

        bad = DurableApprovalRecord(
            storage="durable", execution_allowed=True, executed=False,
            execution_gate="blocked", redaction_applied=True,
        )
        with pytest.raises(p20svc.DurableStoreNotReady) as ei:
            p20svc._from_durable_record(bad)
        assert ei.value.code == "degraded"

    def test_mapper_rejects_memory_storage_record(self):
        from api.v1.platform.p20.schemas import DurableApprovalRecord

        bad = DurableApprovalRecord(storage="memory")  # default invariants hold
        with pytest.raises(p20svc.DurableStoreNotReady):
            p20svc._from_durable_record(bad)


# ---------------------------------------------------------------------------
# 11. Route layer: 503 when not ready; durable + 404 when ready
# ---------------------------------------------------------------------------


_CURRENT_AUTH: dict = {"ctx": None}
_ROUTE_PATCHERS: list = []


def _auth_ctx(uid):
    t = MagicMock()
    t.user_id = uid
    t.roles = ["super_admin"]
    t.tenant_id = None
    t.tenant_schema = None
    t.is_identity_only = True
    t.is_super_admin = True
    return MagicMock(token=t)


def _fake_get_auth_context(*a, **k):
    if _CURRENT_AUTH["ctx"] is None:
        raise RuntimeError("no auth context attached")
    return _CURRENT_AUTH["ctx"]


def _enable_auth():
    p = patch("api.context.auth.get_auth_context", MagicMock(side_effect=_fake_get_auth_context))
    p.start()
    _ROUTE_PATCHERS.append(p)


def _as(uid):
    _CURRENT_AUTH["ctx"] = _auth_ctx(uid)


def _route_app(url):
    """Build a P20-router app whose get_db yields sessions on a FRESH engine.

    The engine is created here (not the module-scoped async-engine fixture) so it
    binds to TestClient's own event loop -- the module engines are bound to the
    pytest-asyncio session loop and cannot be reused from a sync TestClient test.
    """
    from api.dependencies import get_db
    from api.v1.platform.p20.routes import router

    engine = create_async_engine(url, future=True)
    app = FastAPI()

    async def override():
        session = AsyncSession(engine, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()

    app.dependency_overrides[get_db] = override
    app.include_router(router)
    return app


def _payload(**over):
    base = {
        "action_type": "tenant.pause",
        "tenant_id": TENANT_ID,
        "reason": "routine durable approval",
        "idempotency_key": "route-1",
        "confirm": True,
        "expires_at": "2099-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


@pytest.fixture(autouse=True)
def _reset_route_auth():
    _CURRENT_AUTH["ctx"] = None
    yield
    while _ROUTE_PATCHERS:
        _ROUTE_PATCHERS.pop().stop()


class TestRouteLayer:
    def test_create_returns_503_when_store_not_ready(self, durable_urls):
        p20svc.set_storage_mode("durable")
        app = _route_app(durable_urls["bare_async"])
        client = TestClient(app)
        r = client.post(DURABLE, headers=AUTH_HEADERS, json=_payload())
        assert r.status_code == 503
        detail = r.json()["detail"]
        assert detail["code"] == "storage_not_ready"
        assert detail["storage"] == "durable"

    def test_read_returns_503_when_store_not_ready(self, durable_urls):
        p20svc.set_storage_mode("durable")
        app = _route_app(durable_urls["bare_async"])
        client = TestClient(app)
        r = client.get(f"{DURABLE}/some-id", headers=AUTH_HEADERS)
        assert r.status_code == 503

    def test_durable_create_persists_when_ready(self, durable_urls, monkeypatch):
        _enable_available_source(monkeypatch)
        p20svc.set_storage_mode("durable")
        app = _route_app(durable_urls["mig_async"])
        _enable_auth()
        _as("maker-route")
        client = TestClient(app)
        r = client.post(DURABLE, json=_payload(idempotency_key="route-ready"))
        assert r.status_code == 200
        body = r.json()
        assert body["result"] == "recorded"
        assert body["storage"] == "durable"
        assert body["execution_allowed"] is False
        assert body["executed"] is False

    def test_durable_read_not_found_returns_404(self, durable_urls):
        p20svc.set_storage_mode("durable")
        app = _route_app(durable_urls["mig_async"])
        client = TestClient(app)
        r = client.get(f"{DURABLE}/{uuid4()}", headers=AUTH_HEADERS)
        assert r.status_code == 404
