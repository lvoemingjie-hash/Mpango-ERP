"""P21-D-C focused tests: concrete durable approval store adapter (DB read/write).

Drives the concrete :class:`DurableApprovalStoreAdapter` (the P21-D-C runtime
implementation) against an EPHEMERAL, self-contained PostgreSQL database and
proves the durable adapter mirrors the P20-B in-memory service logic exactly
while persisting every operation as a single atomic, restart-safe transaction.

Self-contained ephemeral DB: the module-scoped fixture starts its OWN throwaway
``postgres:15`` container (never the developer ``mpango_erp`` database, never a
shared DB), bootstraps the test-only prerequisites (pgcrypto, widened
``public.alembic_version``, ``t_dev``), runs the already-merged migration
``020_durable_approval_store`` (the public durable tables / enums), and tears the
container down on finish. It REFUSES to run without docker (skip, not fail);
when docker is available (the validation environment) every test runs for real.

Coverage (the directive's required surface):
  - create persists request + audit + idempotency, transactionally consistent;
  - create idempotent replay (duplicate) and key-mismatch conflict;
  - decision persists checker row + audit + idempotency;
  - duplicate decision (same checker, same decision) is idempotent;
  - conflict (same checker flips) is rejected;
  - maker-checker separation (self-decision denied, never persisted);
  - reject is final (terminal; later approve denied);
  - source-honesty (approve against an unknown source is denied; the unknown
    source is stored verbatim, never fabricated available);
  - no-execution invariant (execution_allowed / executed always False,
    execution_gate always "blocked", on every record AND every StoreResult);
  - restart-safety (a NEW adapter instance on a NEW session reads the persisted
    state back unchanged; sequence_no ordering is preserved);
  - P21-D-D wires P20 services to this adapter behind an explicit readiness
    gate (durable default; in-memory retained as explicit test / dev backend);
    the dedicated P21-D-D cutover suite proves the gated wiring end to end.

Plus durability hygiene: store_version increments on transitions; per-approval
audit sequence_no is monotonic; the raw idempotency key is never persisted
(digest-only); a raw secret in the reason is redacted before persistence.

Approval is not execution, and durability is not execution. The concrete adapter
is exercised here directly; P21-D-D wires it behind the runtime readiness gate
(``is_live_store`` stays False -- the adapter never self-elects as the live
store; the P20 service gate decides that at runtime).
"""
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.async_test_utils import run_alembic_upgrade

from api.v1.platform.p21 import adapter as p21a
from api.v1.platform.p21.models import (
    DurableApprovalAuditEvent,
    DurableApprovalDecision,
    DurableApprovalIdempotencyKey,
    DurableApprovalRequest,
)

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
PUBLIC = "public"

TENANT_ID = "b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d"
ACTION_ID = "11111111-1111-4111-8111-111111111111"
OTHER_ACTION_ID = "22222222-2222-4222-8222-222222222222"
FUTURE = datetime(2099, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Ephemeral, self-contained PostgreSQL (throwaway container; never mpango_erp)
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    try:
        subprocess.run(
            ["docker", "--version"], capture_output=True, check=True, timeout=20
        )
        return True
    except Exception:
        return False


def _wait_postgres(sync_url: str, timeout: float = 45.0) -> None:
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
def durable_db_url():
    """Start a throwaway postgres:15 container and run migration 020 (sync)."""
    # Snapshot the env BEFORE this fixture mutates it, so the finally can restore
    # it (test isolation -- no leaked dead DATABASE_URL to later suites).
    _env = {
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "REPORTING_USER_PASSWORD": os.environ.get("REPORTING_USER_PASSWORD"),
    }
    if not _docker_available():
        pytest.skip("docker not available; cannot start an ephemeral postgres container")
    container = f"p21dc-ephemeral-{uuid4().hex[:10]}"
    subprocess.run(["docker", "rm", "-f", container], capture_output=True)
    run = subprocess.run(
        [
            "docker", "run", "-d", "--name", container,
            "-e", "POSTGRES_PASSWORD=p21dc",
            "-e", "POSTGRES_DB=p21dc",
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
        # Throwaway local container credentials (never the developer DB); marked
        # allowlist so the basic-auth-shaped URL does not trip detect-secrets.
        async_url = f"postgresql+asyncpg://postgres:p21dc@127.0.0.1:{host_port}/p21dc"  # pragma: allowlist secret
        sync_url = f"postgresql://postgres:p21dc@127.0.0.1:{host_port}/p21dc"  # pragma: allowlist secret
        # Refuse any chance of landing on the developer DB.
        assert "mpango_erp" not in async_url.lower()
        _wait_postgres(sync_url)
        _bootstrap(sync_url)
        os.environ["DATABASE_URL"] = async_url
        os.environ.setdefault("REPORTING_USER_PASSWORD", "ephemeral_reporting_pw")
        from alembic.config import Config

        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        run_alembic_upgrade(cfg, "head")  # public-mode; creates durable tables
        yield {"async_url": async_url, "sync_url": sync_url, "container": container}
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)
        _restore_env(_env)  # test isolation: do not leak the throwaway DATABASE_URL


@pytest.fixture(scope="module")
async def engine(durable_db_url):
    eng = create_async_engine(durable_db_url["async_url"], future=True)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture(autouse=True)
async def _truncate(engine):
    """Clean durable tables before each test (isolated, deterministic)."""
    async with engine.begin() as conn:
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


def create_kwargs(**over):
    base = dict(
        action_id=ACTION_ID,
        tenant_id=TENANT_ID,
        action_type="tenant.pause",
        source_status="available",
        action_class="write",
        maker=None,
        reason="planned tenant pause for maintenance",
        idempotency_key="create-key-A",
        expires_at=FUTURE,
        durable_retain_until=FUTURE,
        confirm=True,
        correlation_id=None,
        metadata=None,
        actor="maker-1",
        actor_role="super_admin",
        identity_context="identity_only",
        retention_class="standard",
    )
    base.update(over)
    return base


def decide_kwargs(**over):
    base = dict(
        decision="approve",
        approver_id=None,
        reason="looks good to approve",
        idempotency_key="decide-key-Z",
        confirm=True,
        correlation_id=None,
        metadata=None,
        actor="checker-2",
        actor_role="super_admin",
        identity_context="identity_only",
    )
    base.update(over)
    return base


def _session(engine) -> AsyncSession:
    # expire_on_commit=False so create can read post-commit attributes; the
    # adapter's fetches use populate_existing() to bypass the identity map.
    session = AsyncSession(engine, expire_on_commit=False)
    # The durable tables are public-schema / system-scope; bypass the project's
    # global tenant guardrail for direct assertion queries (the adapter marks its
    # own session system-scope in __init__).
    try:
        from db.tenant_filter import mark_session_as_system

        mark_session_as_system(session, reason="p21_durable_approval_store_test")
    except Exception:
        pass
    return session


async def _count(session: AsyncSession, model) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def _scan_table_text(session: AsyncSession, table: str) -> str:
    res = await session.execute(
        text(f"SELECT row_to_json(t)::text AS j FROM public.{table} t")
    )
    return "\n".join(r[0] for r in res.fetchall())


async def _audit_event_types(session: AsyncSession, approval_id) -> list:
    res = await session.execute(
        select(DurableApprovalAuditEvent.event_type, DurableApprovalAuditEvent.sequence_no)
        .where(DurableApprovalAuditEvent.approval_id == approval_id)
        .order_by(DurableApprovalAuditEvent.sequence_no)
    )
    return [r[0] for r in res.fetchall()]


# ---------------------------------------------------------------------------
# Surface / phase
# ---------------------------------------------------------------------------


def test_concrete_adapter_is_not_live_store_and_implements_base_surface():
    assert p21a.DurableApprovalStoreAdapter.is_live_store is False
    assert p21a.DURABLE_ADAPTER_IMPLEMENTATION_PHASE == "P21-D-C-implementation"
    for required in ("create_request", "get_request", "list_requests", "submit_decision"):
        assert required in p21a.IMPLEMENTED_METHODS
        assert callable(getattr(p21a.DurableApprovalStoreAdapter, required))


async def test_retention_and_export_methods_remain_deferred(engine):
    adapter = p21a.DurableApprovalStoreAdapter(_session(engine))
    with pytest.raises(p21a.StoreNotImplementedError):
        await adapter.expire_due_requests(datetime.now(timezone.utc))
    with pytest.raises(p21a.StoreNotImplementedError):
        await adapter.purge_eligible_records(datetime.now(timezone.utc))
    with pytest.raises(p21a.StoreNotImplementedError):
        await adapter.export_record("x", None)
    await adapter._session.close()


# ---------------------------------------------------------------------------
# create: persist request + audit + idempotency; transactional; no-execution
# ---------------------------------------------------------------------------


async def test_create_persists_request_audit_idempotency_and_no_execution(engine):
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        res = await adapter.create_request(**create_kwargs())
    assert res.ok is True
    assert res.restart_safe is True
    assert res.execution_allowed is False
    assert res.executed is False
    assert res.storage_class == "durable"
    rec = res.value
    assert rec.result == "recorded"
    assert rec.state == "pending_review"
    assert rec.execution_allowed is False
    assert rec.executed is False
    assert rec.execution_gate == "blocked"
    assert rec.storage == "durable"
    assert rec.action_class == "write"
    assert rec.quorum_required == 2  # write floor
    assert rec.quorum_met is False
    approval_id = rec.approval_id

    # Persisted: 1 request, >=1 audit (approval_opened), 1 open idempotency row.
    async with _session(engine) as session:
        assert await _count(session, DurableApprovalRequest) == 1
        assert await _count(session, DurableApprovalAuditEvent) >= 1
        assert await _count(session, DurableApprovalIdempotencyKey) == 1
        req = (
            await session.execute(
                select(DurableApprovalRequest).where(DurableApprovalRequest.approval_id == approval_id)
            )
        ).scalar_one()
        assert req.state == "pending_review"
        assert req.execution_allowed is False
        assert req.executed is False
        assert req.execution_gate == "blocked"
        assert req.storage_class == "durable"
        assert req.store_version == 1
        assert req.redaction_applied is True
        assert req.source_status == "valid"  # available -> valid
        assert req.validation_status == "valid"
        assert req.idempotency_key_digest == p21a._digest("create-key-A")  # digest only
        idem = (
            await session.execute(select(DurableApprovalIdempotencyKey))
        ).scalar_one()
        assert idem.scope_key == "open"
        assert idem.idempotency_key_digest == p21a._digest("create-key-A")
        assert idem.result_ref is not None


async def test_create_idempotent_replay_returns_duplicate(engine):
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        first = await adapter.create_request(**create_kwargs())
        second = await adapter.create_request(**create_kwargs(idempotency_key="create-key-A"))
    assert first.ok and second.ok
    assert first.value.result == "recorded"
    assert second.value.result == "duplicate"
    assert second.value.approval_id == first.value.approval_id  # original returned
    async with _session(engine) as session:
        assert await _count(session, DurableApprovalRequest) == 1  # no new row


async def test_create_conflict_on_same_key_different_payload(engine):
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        first = await adapter.create_request(**create_kwargs())
        # same idempotency key, different (redacted) reason -> conflict
        conflict = await adapter.create_request(
            **create_kwargs(idempotency_key="create-key-A", reason="a different reason entirely")
        )
    assert first.ok
    assert conflict.ok is False
    assert conflict.error.code == "decision_conflict"
    async with _session(engine) as session:
        assert await _count(session, DurableApprovalRequest) == 1  # nothing new persisted


async def test_create_denials_persist_no_request_row(engine):
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        # no authenticated actor -> denied
        r1 = await adapter.create_request(**create_kwargs(actor=None))
        # missing reason -> denied
        r2 = await adapter.create_request(**create_kwargs(reason="   "))
        # confirm false -> denied
        r3 = await adapter.create_request(**create_kwargs(confirm=False))
        # past expires_at -> denied
        r4 = await adapter.create_request(**create_kwargs(expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc)))
    for r in (r1, r2, r3, r4):
        assert r.ok is False
        assert r.execution_allowed is False
        assert r.executed is False
    async with _session(engine) as session:
        assert await _count(session, DurableApprovalRequest) == 0  # no request persisted


# ---------------------------------------------------------------------------
# decide: persist checker row + audit + idempotency
# ---------------------------------------------------------------------------


async def test_decision_persists_checker_audit_idempotency(engine):
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        created = await adapter.create_request(**create_kwargs())
        approval_id = created.value.approval_id
        dec = await adapter.submit_decision(approval_id, **decide_kwargs(actor="checker-2"))
    assert dec.ok is True
    assert dec.value.result == "quorum_pending"  # 1 of 2 distinct approve checkers
    assert dec.value.state == "pending_review"
    assert dec.value.quorum_met is False
    assert dec.value.execution_allowed is False
    assert dec.value.executed is False
    async with _session(engine) as session:
        assert await _count(session, DurableApprovalDecision) == 1
        assert await _count(session, DurableApprovalIdempotencyKey) == 2  # open + decide
        d = (await session.execute(select(DurableApprovalDecision))).scalar_one()
        assert d.checker_actor_id == "checker-2"
        assert d.decision == "approve"
        assert d.confirm is True
        assert d.idempotency_key_digest == p21a._digest("decide-key-Z")
        # decision row linked to a real audit event
        assert d.audit_event_id is not None
        types = await _audit_event_types(session, approval_id)
        assert "approval_decision_recorded" in types


async def test_duplicate_decision_same_checker_is_idempotent(engine):
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        created = await adapter.create_request(**create_kwargs())
        approval_id = created.value.approval_id
        first = await adapter.submit_decision(approval_id, **decide_kwargs(actor="checker-2"))
        dup = await adapter.submit_decision(approval_id, **decide_kwargs(actor="checker-2"))
    assert first.ok and dup.ok
    assert dup.value.result == "duplicate"
    async with _session(engine) as session:
        assert await _count(session, DurableApprovalDecision) == 1  # no second row


async def test_conflict_checker_flip_is_rejected(engine):
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        created = await adapter.create_request(**create_kwargs())
        approval_id = created.value.approval_id
        first = await adapter.submit_decision(approval_id, **decide_kwargs(actor="checker-2", decision="approve"))
        flip = await adapter.submit_decision(
            approval_id,
            **decide_kwargs(actor="checker-2", decision="reject", idempotency_key="decide-key-flip"),
        )
    assert first.ok
    assert flip.ok is False
    assert flip.error.code == "decision_conflict"
    async with _session(engine) as session:
        assert await _count(session, DurableApprovalDecision) == 1  # only the first landed


# ---------------------------------------------------------------------------
# maker-checker
# ---------------------------------------------------------------------------


async def test_maker_checker_denies_self_decision_and_persists_nothing(engine):
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        created = await adapter.create_request(**create_kwargs(actor="maker-1"))
        approval_id = created.value.approval_id
        # same actor as maker -> self-decision denied
        self_dec = await adapter.submit_decision(
            approval_id, **decide_kwargs(actor="maker-1", decision="approve")
        )
    assert self_dec.ok is False
    assert self_dec.error.code == "self_decision_denied"
    async with _session(engine) as session:
        assert await _count(session, DurableApprovalDecision) == 0


# ---------------------------------------------------------------------------
# reject is final
# ---------------------------------------------------------------------------


async def test_reject_is_final_blocks_later_approve(engine):
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        created = await adapter.create_request(**create_kwargs(actor="maker-1"))
        approval_id = created.value.approval_id
        rej = await adapter.submit_decision(
            approval_id, **decide_kwargs(actor="checker-2", decision="reject", idempotency_key="k-rej")
        )
        later = await adapter.submit_decision(
            approval_id, **decide_kwargs(actor="checker-3", decision="approve", idempotency_key="k-approve")
        )
    assert rej.ok and rej.value.result == "rejected"
    assert rej.value.state == "rejected"
    assert rej.value.execution_allowed is False
    assert later.ok is False
    assert later.error.code == "decision_conflict"
    async with _session(engine) as session:
        req = (
            await session.execute(
                select(DurableApprovalRequest).where(DurableApprovalRequest.approval_id == approval_id)
            )
        ).scalar_one()
        assert req.state == "rejected"  # reject is final / terminal
        assert req.decision == "reject"
        types = await _audit_event_types(session, approval_id)
        assert "approval_rejected" in types


# ---------------------------------------------------------------------------
# source-honesty
# ---------------------------------------------------------------------------


async def test_source_honesty_blocks_approve_against_unknown_source(engine):
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        # unknown source -> stored verbatim (never fabricated available)
        created = await adapter.create_request(**create_kwargs(source_status="unknown", actor="maker-1"))
        approval_id = created.value.approval_id
        # response maps the durable "unknown" back to the P20 "unknown" vocabulary
        assert created.value.source_status == "unknown"
        assert created.value.validation_status == "source_unknown"
        approve = await adapter.submit_decision(
            approval_id, **decide_kwargs(actor="checker-2", decision="approve", idempotency_key="k-a")
        )
    assert approve.ok is False
    assert approve.error.code == "unknown_source"
    async with _session(engine) as session:
        assert await _count(session, DurableApprovalDecision) == 0  # approve did not land
        req = (await session.execute(select(DurableApprovalRequest))).scalar_one()
        assert req.source_status == "unknown"  # stored verbatim, not upgraded to valid


# ---------------------------------------------------------------------------
# quorum met -> approved_execution_blocked (still no execution)
# ---------------------------------------------------------------------------


async def test_quorum_met_persists_approved_execution_blocked(engine):
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        created = await adapter.create_request(**create_kwargs(actor="maker-1"))
        approval_id = created.value.approval_id
        first = await adapter.submit_decision(
            approval_id, **decide_kwargs(actor="checker-2", idempotency_key="k-1")
        )
        second = await adapter.submit_decision(
            approval_id, **decide_kwargs(actor="checker-3", idempotency_key="k-2")
        )
    assert first.value.result == "quorum_pending"
    assert second.ok and second.value.result == "approved"
    assert second.value.state == "approved_execution_blocked"
    assert second.value.quorum_met is True
    # NO EXECUTION even at quorum
    assert second.value.execution_allowed is False
    assert second.value.executed is False
    assert second.value.execution_gate == "blocked"
    async with _session(engine) as session:
        req = (
            await session.execute(
                select(DurableApprovalRequest).where(DurableApprovalRequest.approval_id == approval_id)
            )
        ).scalar_one()
        assert req.state == "approved_execution_blocked"
        assert req.execution_allowed is False
        assert req.executed is False
        assert req.quorum_met is True
        assert req.store_version == 2  # bumped exactly once on the transition
        assert req.decision == "approve"
        types = await _audit_event_types(session, approval_id)
        assert "approval_quorum_met" in types


# ---------------------------------------------------------------------------
# restart-safety: a NEW adapter instance on a NEW session reads state back
# ---------------------------------------------------------------------------


async def test_restart_safety_new_adapter_reads_back(engine):
    # Adapter A / session A: create + one approve, then close (simulated restart).
    async with _session(engine) as session_a:
        adapter_a = p21a.DurableApprovalStoreAdapter(session_a)
        created = await adapter_a.create_request(**create_kwargs(actor="maker-1"))
        approval_id = created.value.approval_id
        await adapter_a.submit_decision(
            approval_id, **decide_kwargs(actor="checker-2", idempotency_key="k-1")
        )
    # Adapter B / session B: brand-new instance reads the persisted state back.
    async with _session(engine) as session_b:
        adapter_b = p21a.DurableApprovalStoreAdapter(session_b)
        read = await adapter_b.get_request(approval_id)
    assert read.ok
    rec = read.value
    assert rec.approval_id == approval_id
    assert rec.state == "pending_review"  # survived restart
    assert rec.quorum_met is False
    assert rec.quorum_required == 2
    assert len(rec.checkers) == 1  # the one approve survived
    assert rec.checkers[0].checker_id == "checker-2"
    assert rec.checkers[0].decision == "approve"
    assert rec.execution_allowed is False
    assert rec.executed is False
    # Continue toward quorum on the new instance; that transition also persists.
    async with _session(engine) as session_c:
        adapter_c = p21a.DurableApprovalStoreAdapter(session_c)
        second = await adapter_c.submit_decision(
            approval_id, **decide_kwargs(actor="checker-3", idempotency_key="k-2")
        )
    assert second.ok and second.value.result == "approved"
    assert second.value.state == "approved_execution_blocked"


async def test_audit_sequence_no_monotonic_across_restart(engine):
    async with _session(engine) as session_a:
        adapter_a = p21a.DurableApprovalStoreAdapter(session_a)
        created = await adapter_a.create_request(**create_kwargs(actor="maker-1"))
        approval_id = created.value.approval_id
    async with _session(engine) as session_b:
        res = await session_b.execute(
            select(DurableApprovalAuditEvent.sequence_no)
            .where(DurableApprovalAuditEvent.approval_id == approval_id)
            .order_by(DurableApprovalAuditEvent.sequence_no)
        )
        seqs = [r[0] for r in res.fetchall()]
    assert seqs == [1]  # approval_opened at sequence_no 1; preserved after restart


# ---------------------------------------------------------------------------
# read / list
# ---------------------------------------------------------------------------


async def test_get_request_not_found(engine):
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        res = await adapter.get_request(str(uuid4()))
    assert res.ok is False
    assert res.error.code == "not_found"


async def test_list_requests_filters_and_pagination(engine):
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        await adapter.create_request(
            **create_kwargs(action_id=ACTION_ID, action_type="tenant.pause", idempotency_key="k-a", actor="maker-1")
        )
        await adapter.create_request(
            **create_kwargs(
                action_id=OTHER_ACTION_ID, action_type="provisioning.recheck",
                action_class="read", source_status="available", idempotency_key="k-b", actor="maker-1",
            )
        )
        allq = await adapter.list_requests({})
        paused = await adapter.list_requests({"action_type": "tenant.pause"})
        page = await adapter.list_requests({}, limit=1, offset=0)
    assert allq.ok and allq.value.total == 2
    assert allq.value.executed is False
    assert allq.value.storage == "durable"
    assert all(it.execution_allowed is False for it in allq.value.items)
    assert paused.ok and paused.value.total == 1
    assert page.ok and page.value.total == 2 and len(page.value.items) == 1


# ---------------------------------------------------------------------------
# durability hygiene: digest-only + redaction-before-persistence
# ---------------------------------------------------------------------------


async def test_raw_idempotency_key_never_persisted(engine):
    raw_create_key = "super-secret-create-key-123456"
    raw_decide_key = "super-secret-decide-key-789012"
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        created = await adapter.create_request(
            **create_kwargs(idempotency_key=raw_create_key, actor="maker-1")
        )
        await adapter.submit_decision(
            created.value.approval_id,
            **decide_kwargs(actor="checker-2", idempotency_key=raw_decide_key),
        )
    async with _session(engine) as session:
        for table in (
            "durable_approval_requests",
            "durable_approval_decisions",
            "durable_approval_audit_events",
            "durable_approval_idempotency_keys",
        ):
            blob = await _scan_table_text(session, table)
            assert raw_create_key not in blob, f"raw create key leaked in {table}"
            assert raw_decide_key not in blob, f"raw decide key leaked in {table}"


async def test_raw_secret_reason_redacted_before_persistence(engine):
    # Deliberate secret fixture proving redaction-before-persistence; allowlisted.
    secret_reason = "rotate because password=hunter2 and token=abc123"  # pragma: allowlist secret
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        created = await adapter.create_request(
            **create_kwargs(reason=secret_reason, actor="maker-1", idempotency_key="k-r")
        )
    # The redacted reason is echoed on the record (never the raw secret).
    assert created.value.reason == "[redacted]"
    async with _session(engine) as session:
        for table in (
            "durable_approval_requests",
            "durable_approval_audit_events",
        ):
            blob = await _scan_table_text(session, table)
            assert "hunter2" not in blob, f"raw secret leaked in {table}"
            assert "abc123" not in blob, f"raw secret leaked in {table}"


# ---------------------------------------------------------------------------
# no-execution invariant: every StoreResult across the lifecycle stays False
# ---------------------------------------------------------------------------


async def test_no_execution_invariant_across_lifecycle(engine):
    outcomes: list = []
    async with _session(engine) as session:
        adapter = p21a.DurableApprovalStoreAdapter(session)
        created = await adapter.create_request(**create_kwargs(actor="maker-1"))
        approval_id = created.value.approval_id
        outcomes.append(created)
        outcomes.append(await adapter.submit_decision(
            approval_id, **decide_kwargs(actor="checker-2", idempotency_key="k-1")))
        outcomes.append(await adapter.submit_decision(
            approval_id, **decide_kwargs(actor="checker-3", idempotency_key="k-2")))
        outcomes.append(await adapter.get_request(approval_id))
    for res in outcomes:
        assert res.execution_allowed is False
        assert res.executed is False
        if res.ok and res.value is not None and hasattr(res.value, "execution_allowed"):
            assert res.value.execution_allowed is False
            assert res.value.executed is False
            assert res.value.execution_gate == "blocked"


# ---------------------------------------------------------------------------
# P21-D-D cutover wiring: P20 services reference this adapter behind the
# readiness gate; routes translate a gate failure to 503 and reach the store
# only through services (no direct p21 import); app.py registers no p21 router.
# ---------------------------------------------------------------------------


def _read(rel: str) -> str:
    path = (BACKEND_DIR / rel).resolve()
    assert path.is_file(), f"expected file missing: {path}"
    return path.read_text(encoding="utf-8")


def test_p20_services_wire_durable_adapter_and_retain_memory_backend():
    src = _read("api/v1/platform/p20/services.py")
    # The cutover: services reference the concrete adapter + the readiness gate.
    assert "api.v1.platform.p21.adapter" in src
    assert "DurableApprovalStoreAdapter" in src
    assert "DurableStoreNotReady" in src
    # The in-memory backend is retained as the explicit memory fallback.
    assert "_STORE" in src
    assert "_STORE_BY_CREATE_KEY" in src
    assert "_AUDIT_LOG" in src
    assert 'storage="memory"' in src or 'storage = "memory"' in src


def test_p20_routes_reach_durable_store_via_services_only():
    src = _read("api/v1/platform/p20/routes.py")
    assert "DurableStoreNotReady" in src
    # Routes never import the durable adapter directly -- only via services.
    for token in ("api.v1.platform.p21", "DurableApprovalStoreAdapter", "p21.adapter", "p21.models"):
        assert token not in src, f"P20 routes must not import durable adapter directly: {token}"


def test_app_does_not_register_durable_adapter_router():
    src = _read("api/app.py")
    assert "platform.p21" not in src
    assert "DurableApprovalStoreAdapter" not in src
