"""P21-E focused tests: durable approval runtime closeout / readiness proof.

P21-E is the closeout / proof / hardening slice for the P21 durable approval
runtime. It adds no new feature: it STRENGTHENS the existing proof surface for
the directive's restart-safety, end-to-end route, and failure-mode requirements,
and re-verifies the no-execution / no-silent-memory-fallback invariants at the
layers not previously exercised (the full ROUTE lifecycle; the restart boundary
for LIST and for a quorum-reaching DECISION; the route-level 503 leak surface;
and the durable adapter source for execution-path references).

Pre-existing coverage this builds on (verified, exact files):
  - test_platform_p21dd_runtime_storage_cutover_gate.py -- service-layer gate,
    readiness (ready / storage_not_ready / unavailable / degraded), restart READ,
    digest idempotency, maker-checker / quorum / source-honesty, store-not-ready
    fail-closed (no silent memory fallback), explicit memory mode, mapper fail
    closed, and route-layer 503 / 404.
  - test_platform_p21_durable_approval_adapter_implementation.py -- concrete
    adapter create / decide / quorum, restart read-back, raw-key-never-persisted,
    raw-reason-redacted-before-persistence, no-execution invariant across the
    lifecycle, and the P20 -> adapter wiring.
  - test_platform_p20_durable_approval_governance.py -- in-memory governance,
    identity binding, dual-control, permissions, redaction, no-execution.

This module closes the remaining P21-E gaps:
  - Restart-safety: LIST finds the record after a session restart, and a DECISION
    that reaches quorum works across the restart boundary (create in session A;
    list / decide in a NEW session B -- a real adapter / session recreate).
  - End-to-end route proof: the FULL durable lifecycle at the route layer (POST
    create -> GET queue -> GET by id -> POST decision x2 -> quorum), proving
    executed=False / execution_allowed=False / execution_gate="blocked" at every
    step, NO silent memory fallback through the whole lifecycle, the frontend
    response shape, and route-level reason redaction on the durable path.
  - Failure-mode at the route layer: a storage_not_ready 503 leaks no raw
    idempotency_key / raw reason in the response body, and an unreachable DB
    returns code "unavailable" / 503.
  - No-execution source invariant extended to the durable adapter source.

Self-contained ephemeral DB (mirrors the P21-D-D / P21-D-C suites): a throwaway
``postgres:15`` container hosts ``p21e_mig`` (migration 020 head => ready) and
``p21e_bare`` (bootstrapped prerequisites only => schema missing => not ready).
It REFUSES to run without docker (skip, not fail); when docker is available
(the validation environment) every test runs for real. It NEVER touches the
developer ``mpango_erp`` / ``mpango_postgres`` database.

Approval is not execution, and durability is not execution. No P18 action is
ever executed; no tenant / P17 registry data is mutated; this slice adds no
migration, no auth/RBAC rewrite, and no frontend.
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
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from api.v1.platform.p20 import services as p20svc
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
FUTURE_ISO = "2099-01-01T00:00:00+00:00"
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


@pytest.fixture(scope="module")
def durable_urls():
    """One throwaway container hosting two databases (mig ready / bare not ready)."""
    if not _docker_available():
        pytest.skip("docker not available; cannot start an ephemeral postgres container")
    container = f"p21e-ephemeral-{uuid4().hex[:10]}"
    subprocess.run(["docker", "rm", "-f", container], capture_output=True)
    run = subprocess.run(
        [
            "docker", "run", "-d", "--name", container,
            "-e", "POSTGRES_PASSWORD=p21e",  # pragma: allowlist secret
            "-e", "POSTGRES_DB=p21e_mig",
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
        mig_async = f"postgresql+asyncpg://postgres:p21e@127.0.0.1:{host_port}/p21e_mig"  # pragma: allowlist secret
        mig_sync = f"postgresql://postgres:p21e@127.0.0.1:{host_port}/p21e_mig"  # pragma: allowlist secret
        admin_sync = f"postgresql://postgres:p21e@127.0.0.1:{host_port}/postgres"  # pragma: allowlist secret
        # Refuse any chance of landing on the developer DB.
        for u in (mig_async, mig_sync, admin_sync):
            assert "mpango_erp" not in u.lower()
            assert "mpango_postgres" not in u.lower()
        _wait_postgres(mig_sync)
        _bootstrap(mig_sync)
        # Create + bootstrap the bare database (no migration on it -> not ready).
        _create_database(admin_sync, "p21e_bare")
        bare_sync = f"postgresql://postgres:p21e@127.0.0.1:{host_port}/p21e_bare"  # pragma: allowlist secret
        _wait_postgres(bare_sync)
        _bootstrap(bare_sync)
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
            "bare_async": f"postgresql+asyncpg://postgres:p21e@127.0.0.1:{host_port}/p21e_bare",  # pragma: allowlist secret
        }
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)


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
# Service-layer helpers
# ---------------------------------------------------------------------------


def _session(engine) -> AsyncSession:
    session = AsyncSession(engine, expire_on_commit=False)
    try:
        from db.tenant_filter import mark_session_as_system

        mark_session_as_system(session, reason="p21e_closeout_test")
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


# ---------------------------------------------------------------------------
# Route-layer helpers (mirror the P21-D-D route harness)
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


def _route_app(url, *, connect_args=None):
    """Build a P20-router app whose get_db yields sessions on a FRESH engine.

    The engine is created here (not the module-scoped async-engine fixture) so it
    binds to TestClient's own event loop -- the module engines are bound to the
    pytest-asyncio session loop and cannot be reused from a sync TestClient test.
    NullPool gives each request a fresh connection so a multi-request lifecycle
    (POST -> GET -> GET -> POST) never reuses a stale pooled connection.
    """
    from api.dependencies import get_db
    from api.v1.platform.p20.routes import router

    engine_kw = {"future": True, "poolclass": NullPool}
    if connect_args is not None:
        engine_kw["connect_args"] = connect_args
    engine = create_async_engine(url, **engine_kw)
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
        "expires_at": FUTURE_ISO,
    }
    base.update(over)
    return base


def _decision_payload(**over):
    base = {
        "decision": "approve",
        "reason": "approved after durable route review",
        "idempotency_key": "decide-1",
        "confirm": True,
    }
    base.update(over)
    return base


@pytest.fixture(autouse=True)
def _reset_route_auth():
    _CURRENT_AUTH["ctx"] = None
    yield
    while _ROUTE_PATCHERS:
        _ROUTE_PATCHERS.pop().stop()


# ---------------------------------------------------------------------------
# 1. Restart-safety closeout (LIST + quorum-reaching DECISION across restart)
# ---------------------------------------------------------------------------


class TestRestartSafetyCloseout:
    async def test_list_finds_record_after_session_restart(self, mig_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        # Session A: create, then close (simulated restart).
        async with _session(mig_engine) as session_a:
            created = await _create(session_a, actor="maker-1")
            approval_id = created.approval_id
        # Session B (NEW): a durable LIST still finds the persisted record.
        async with _session(mig_engine) as session_b:
            queue = await p20svc.list_durable_approvals(db=session_b)
        assert queue.storage == "durable"
        assert queue.total >= 1
        assert any(it.approval_id == approval_id for it in queue.items)
        match = next(it for it in queue.items if it.approval_id == approval_id)
        assert match.state == "pending_review"
        assert match.storage == "durable"
        assert match.executed is False
        # The in-memory store was NEVER used (no silent memory fallback).
        assert approval_id not in p20svc._STORE
        assert p20svc._STORE == {}

    async def test_decision_reaches_quorum_across_restart_boundary(self, mig_engine, monkeypatch):
        _enable_available_source(monkeypatch)
        # Session A: create only, then close (the restart boundary).
        async with _session(mig_engine) as session_a:
            created = await _create(session_a, actor="maker-1")
            approval_id = created.approval_id
        # Session B (NEW): decisions recorded AFTER the restart still work and
        # reach quorum against the persisted record.
        async with _session(mig_engine) as session_b:
            first = await _decide(approval_id, session_b, actor="checker-2", idempotency_key="d1")
            second = await _decide(approval_id, session_b, actor="checker-3", idempotency_key="d2")
        assert first.result == "quorum_pending"
        assert second.result == "approved"
        assert second.state == "approved_execution_blocked"
        assert second.quorum_met is True
        # Quorum still does NOT execute.
        assert second.executed is False
        assert second.execution_allowed is False
        assert second.execution_gate == "blocked"
        ids = {c.checker_id for c in second.checkers}
        assert ids == {"checker-2", "checker-3"}
        assert "maker-1" not in ids
        # No silent memory fallback: the in-memory store stayed empty.
        assert p20svc._STORE == {}


# ---------------------------------------------------------------------------
# 2. End-to-end route proof (full lifecycle; no execution; no memory fallback)
# ---------------------------------------------------------------------------


class TestRouteLayerEndToEndCloseout:
    def test_full_durable_lifecycle_route_layer(self, durable_urls, monkeypatch):
        _enable_available_source(monkeypatch)
        p20svc.set_storage_mode("durable")
        app = _route_app(durable_urls["mig_async"])
        _enable_auth()
        client = TestClient(app)

        # POST create -> 200 recorded durable.
        _as("maker-1")
        created = client.post(
            DURABLE, headers=AUTH_HEADERS, json=_payload(idempotency_key="life-create")
        ).json()
        assert created["result"] == "recorded"
        assert created["storage"] == "durable"
        assert created["execution_allowed"] is False
        assert created["executed"] is False
        approval_id = created["approval_id"]

        # GET queue -> sees the durable record.
        q_resp = client.get(DURABLE, headers=AUTH_HEADERS)
        assert q_resp.status_code == 200, q_resp.text
        q = q_resp.json()
        assert q["storage"] == "durable"
        assert q["executed"] is False
        assert any(it["approval_id"] == approval_id for it in q["items"])

        # GET by id -> returns the durable record, nothing executed.
        got = client.get(f"{DURABLE}/{approval_id}", headers=AUTH_HEADERS).json()
        assert got["approval_id"] == approval_id
        assert got["state"] == "pending_review"
        assert got["storage"] == "durable"
        assert got["executed"] is False
        assert got["execution_allowed"] is False
        assert got["execution_gate"] == "blocked"

        # POST decision (checker-2) -> quorum pending, no execution.
        _as("checker-2")
        d1 = client.post(
            f"{DURABLE}/{approval_id}/decisions",
            headers=AUTH_HEADERS, json=_decision_payload(idempotency_key="d-2"),
        ).json()
        assert d1["result"] == "quorum_pending"
        assert d1["executed"] is False
        assert d1["execution_allowed"] is False

        # POST decision (checker-3) -> quorum met -> approved_execution_blocked.
        _as("checker-3")
        d2 = client.post(
            f"{DURABLE}/{approval_id}/decisions",
            headers=AUTH_HEADERS, json=_decision_payload(idempotency_key="d-3"),
        ).json()
        assert d2["result"] == "approved"
        assert d2["state"] == "approved_execution_blocked"
        assert d2["quorum_met"] is True
        # Quorum met still does NOT execute (approval is not execution).
        assert d2["executed"] is False
        assert d2["execution_allowed"] is False
        assert d2["execution_gate"] == "blocked"
        ids = {c["checker_id"] for c in d2["checkers"]}
        assert ids == {"checker-2", "checker-3"}
        assert "maker-1" not in ids

        # No silent memory fallback through the entire route lifecycle.
        assert p20svc._STORE == {}

    def test_route_create_redacts_secret_reason_on_durable_path(self, durable_urls, monkeypatch):
        _enable_available_source(monkeypatch)
        p20svc.set_storage_mode("durable")
        app = _route_app(durable_urls["mig_async"])
        _enable_auth()
        _as("maker-r")
        client = TestClient(app)
        body = client.post(
            DURABLE,
            headers=AUTH_HEADERS,
            json=_payload(
                reason="db password=hunter2 please approve",  # pragma: allowlist secret
                idempotency_key="redact-route",
            ),
        ).json()
        assert body["result"] == "recorded"
        assert body["storage"] == "durable"
        assert body["reason"] == "[redacted]"
        assert "hunter2" not in str(body)
        # Persistence-level redaction (the raw secret never reaches the durable
        # table row) is proven by the P21-D-C adapter suite
        # (test_raw_secret_reason_redacted_before_persistence); this test adds the
        # durable ROUTE-layer response redaction that was not previously covered.

    def test_route_create_response_shape_frontend_compatible(self, durable_urls, monkeypatch):
        _enable_available_source(monkeypatch)
        p20svc.set_storage_mode("durable")
        app = _route_app(durable_urls["mig_async"])
        _enable_auth()
        _as("maker-shape")
        client = TestClient(app)
        body = client.post(
            DURABLE, headers=AUTH_HEADERS, json=_payload(idempotency_key="shape-1")
        ).json()
        # The P20 frontend contract fields are all present and correctly typed.
        for field in (
            "approval_id", "action_type", "action_class", "state", "maker", "maker_at",
            "checkers", "quorum_required", "quorum_met", "decision", "reason",
            "request_digest", "idempotency_key_digest", "expires_at", "durable_retain_until",
            "execution_allowed", "execution_gate", "redaction_applied", "storage",
            "retention_class", "validation_status", "source_status", "result", "message",
            "executed", "created_at", "updated_at",
        ):
            assert field in body, f"frontend contract field missing: {field}"
        assert body["storage"] == "durable"
        assert body["action_class"] == "write"
        assert body["quorum_required"] == 2
        assert body["execution_allowed"] is False
        assert body["executed"] is False
        assert body["execution_gate"] == "blocked"
        assert body["redaction_applied"] is True
        assert body["state"] == "pending_review"


# ---------------------------------------------------------------------------
# 3. Route-layer failure mode (503 leak surface; unreachable DB)
# ---------------------------------------------------------------------------


class TestRouteLayerFailureModeCloseout:
    def test_route_503_storage_not_ready_leaks_no_raw_key_or_reason(self, durable_urls):
        p20svc.set_storage_mode("durable")
        app = _route_app(durable_urls["bare_async"])  # schema missing -> not ready
        client = TestClient(app)
        raw_key = "super-secret-not-ready-route-key-7"  # pragma: allowlist secret
        secret_reason = "creds token=OH-NO-ROUTE-SECRET"  # pragma: allowlist secret
        r = client.post(
            DURABLE,
            headers=AUTH_HEADERS,
            json=_payload(idempotency_key=raw_key, reason=secret_reason),
        )
        assert r.status_code == 503
        detail = r.json()["detail"]
        assert detail["code"] == "storage_not_ready"
        assert detail["storage"] == "durable"
        # The failure response must never echo the raw key / raw secret reason.
        blob = r.text
        assert raw_key not in blob
        assert "OH-NO-ROUTE-SECRET" not in blob
        # No silent memory fallback: the not-ready durable create wrote nothing.
        assert p20svc._STORE == {}
        assert p20svc._STORE_BY_CREATE_KEY == {}

    def test_route_503_unavailable_when_db_unreachable(self, durable_urls):
        p20svc.set_storage_mode("durable")
        # A closed local port: the information_schema readiness query cannot run
        # -> unavailable -> 503 (fail closed, never a memory success).
        closed = "postgresql+asyncpg://postgres:x@127.0.0.1:9/p21e_nope"  # pragma: allowlist secret
        app = _route_app(closed, connect_args={"timeout": 8})
        client = TestClient(app)
        r = client.post(DURABLE, headers=AUTH_HEADERS, json=_payload())
        assert r.status_code == 503
        assert r.json()["detail"]["code"] == "unavailable"
        assert p20svc._STORE == {}


# ---------------------------------------------------------------------------
# 4. No-execution source invariant extended to the durable adapter source
# ---------------------------------------------------------------------------


class TestNoExecutionSourceInvariantCloseout:
    def test_durable_runtime_source_references_no_execution_path(self):
        """Static proof (mirrors the P20-B governance scan, extended to the
        durable adapter): neither the P20 service nor the P21-D-C concrete
        adapter source references an execution entry point or sets an
        executed / execution_allowed truth. Approval is not execution and
        durability is not execution."""
        sources = [
            BACKEND_DIR / "api" / "v1" / "platform" / "p20" / "services.py",
            BACKEND_DIR / "api" / "v1" / "platform" / "p21" / "adapter.py",
        ]
        for src in sources:
            text_src = src.read_text(encoding="utf-8")
            for token in (
                "execute_action", "run_action", "apply_action",
                "executed = True", "execution_allowed = True",
            ):
                assert token not in text_src, (
                    f"{src.name} must not reference an execution path: {token}"
                )
        # The concrete adapter only calls the P18 redaction / sanitization
        # helpers; it never reaches a P18 execute / dispatch entry point.
        adapter_src = (BACKEND_DIR / "api" / "v1" / "platform" / "p21" / "adapter.py").read_text(
            encoding="utf-8"
        )
        p18_calls = {
            line.split("_p18.", 1)[1].split("(", 1)[0].split(".", 1)[0]
            for line in adapter_src.splitlines()
            if "_p18." in line
        }
        execute_symbols = {"execute_action", "run_action", "apply_action", "dispatch_action"}
        assert not (p18_calls & execute_symbols), (
            f"adapter must not call any P18 execute symbol: {p18_calls & execute_symbols}"
        )
