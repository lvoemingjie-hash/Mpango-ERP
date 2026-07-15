"""P22-E3 backup.check read-only source probe tests.

Covers the P22-E3 read-only binding of ``backup.check`` to the PROVEN, MERGED,
TESTED P17-D-C backup / status source (base ``origin/platform-dev`` @ 0955495,
the P17-D-C merge). The probe reuses the P17-D-C durable read path VERBATIM and
maps it to an honest P22 source status; it NEVER executes. See
``backend/api/v1/platform/p22/source_probe.py`` and
``docs/ai/PLATFORM_PRODUCT_P22_E2_BACKUP_STATUS_SOURCE_DISCOVERY.md`` section 6
(the P22-E3 entry gate, option (b): a read-only probe only -- never an execution
success).

Required coverage (task spec):
  - no P17 outcome -> honest unknown, never healthy, non-executing.
  - fresh successful backup -> readable summary, still non-executing.
  - stale success -> stale, never success.
  - failed / partial -> redacted allowlisted reason only.
  - source read failure -> unavailable / fail-closed, never 500.
  - request / dry-run never set execution flags true (regression).
  - no shell / child-process / dump / execution primitives (AST scan).
  - the static backup.check adapter descriptor is UNCHANGED (G15 invariant).
  - read-only: the probe issues no mutation on the session.
  - R1: the guarded read-only route (GET /backup-check/source) is a real runtime
    caller of the probe; fresh success is visible as known, no outcome as unknown,
    read failure as unavailable (no 500); the route is guarded and never executes.

The probe is driven both directly (pure mapper) and end-to-end through a mocked
async session (the same discipline the P17-D-C read test uses). P22-E3-R1 exposes
the probe through a guarded READ-ONLY route (``GET /backup-check/source`` in
``routes.py``); the route tests prove a real runtime caller surfaces the probe and
keep the read non-executing. That route is NOT an execution entry point. Approval
is not execution; a read is not execution.
"""
import ast
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from tests.conftest import run_coroutine
from uuid import UUID

import pytest

os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")
os.environ.setdefault("PLATFORM_OPERATOR_SECRET", "test-operator-secret")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.v1.platform.p22 import source_probe  # noqa: E402
from api.v1.platform.p22.source_probe import (  # noqa: E402
    PROBE_REALIZES_EXECUTION,
    SOURCE_PROBE_PHASE,
    BackupCheckSourceRead,
    read_backup_check_source,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)
TENANT_ID = "b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d"
TID_UUID = UUID(TENANT_ID)


# ---------------------------------------------------------------------------
# Row / session builders (stand-ins for ORM rows; only the attributes read).
# ---------------------------------------------------------------------------


def _outcome(
    *,
    tenant_id=None,
    job_kind="backup_job",
    status="success",
    completed_at=None,
    bytes_written=100,
    failure_reason_code=None,
):
    o = MagicMock()
    o.tenant_id = tenant_id
    o.job_kind = job_kind
    o.status = status
    o.completed_at = completed_at
    o.started_at = completed_at
    o.bytes_written = bytes_written
    o.failure_reason_code = failure_reason_code
    o.source_writer_id = "backup_postgres.sh"
    return o


def _mock_db_with(outcomes, policies):
    """A mocked async session whose two reads return the given rows.

    Mutation hooks (add / commit / flush / delete) are recorded so the read-only
    invariant is assertable. Mirrors the P17-D-C read-test builder.
    """
    db = MagicMock()
    o1 = MagicMock()
    o1.scalars.return_value.all.return_value = outcomes
    o2 = MagicMock()
    o2.scalars.return_value.all.return_value = policies
    db.execute = AsyncMock(side_effect=[o1, o2])
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.delete = MagicMock()
    return db


def _assert_non_executing(read: BackupCheckSourceRead) -> None:
    """Every execution flag is False and the result is never an execution."""
    assert read.realizes_execution is False
    assert read.executed is False
    assert read.execution_started is False
    assert read.execution_allowed is False
    assert read.result_state == "blocked"
    assert read.read_only is True
    assert read.adapter_result == "not_implemented"
    assert read.binding == "read_only_source_probe"
    assert read.action_type == "backup.check"
    assert read.action_class == "read"


# ===========================================================================
# Phase / non-execution markers
# ===========================================================================


class TestProbeIsNonExecuting:
    def test_phase_marker(self):
        assert SOURCE_PROBE_PHASE == "P22-E3-backup-check-read-only-source-binding"

    def test_probe_marker_realizes_no_execution(self):
        assert PROBE_REALIZES_EXECUTION is False

    def test_unavailable_result_is_non_executing(self):
        read = source_probe._unavailable_read(NOW)
        _assert_non_executing(read)
        assert read.source_status == "unknown"
        assert read.source_summary == "unavailable"

    def test_result_model_pins_all_execution_flags_false(self):
        # Even constructed directly, the model can never carry an execution flag
        # True (the literals / defaults forbid it).
        read = BackupCheckSourceRead(
            source_status="unknown", source_summary="unknown", checked_at=NOW
        )
        _assert_non_executing(read)


# ===========================================================================
# G15 invariant: the static backup.check adapter descriptor is UNCHANGED
# (P22-E3 is additive -- it adds a probe, it does not realize the adapter).
# ===========================================================================


class TestStaticDescriptorUnchanged:
    def test_backup_check_descriptor_still_not_implemented(self):
        from api.v1.platform.p22.adapters import (
            _BACKUP_SOURCE_NOT_WIRED,
            _build_descriptor,
            _source_status_for,
        )

        status, reason = _source_status_for("backup.check")
        assert status == "unknown"
        assert reason == _BACKUP_SOURCE_NOT_WIRED
        desc = _build_descriptor("backup.check")
        assert desc.adapter_result == "not_implemented"
        assert desc.source_status == "unknown"
        assert desc.realizes_execution is False

    def test_seam_descriptor_resolution_unchanged(self):
        from api.v1.platform.p22.adapters import resolve_adapter_descriptor

        desc = resolve_adapter_descriptor("backup.check")
        assert desc is not None
        assert desc.realizes_execution is False
        assert desc.adapter_result == "not_implemented"


# ===========================================================================
# Honest source mapping (end-to-end through the proven P17 read path)
# ===========================================================================


class TestSourceMapping:
    async def test_no_outcome_is_unknown_never_healthy(self):
        # No outcome rows at all -> the loader resolves 'unknown'; the probe
        # reports unknown / unknown, never healthy, non-executing.
        db = _mock_db_with([], [])
        read = await read_backup_check_source(db, TENANT_ID, now=NOW)
        assert read.source_status == "unknown"
        assert read.source_summary == "unknown"
        assert read.last_backup_status is None
        assert read.reason is not None
        assert read.source_status != "known"
        _assert_non_executing(read)

    async def test_fresh_success_is_known_readable_summary(self):
        row = _outcome(
            tenant_id=TID_UUID,
            status="success",
            completed_at=NOW - timedelta(hours=2),
            bytes_written=2048,
        )
        db = _mock_db_with([row], [])
        read = await read_backup_check_source(db, TENANT_ID, now=NOW)
        assert read.source_summary == "fresh_success"
        assert read.source_status == "known"
        assert read.last_backup_status == "success"
        assert read.last_backup_at == NOW - timedelta(hours=2)
        assert read.export_available is True
        assert read.p17_backup_source_status == "available"
        _assert_non_executing(read)

    async def test_stale_success_is_stale_never_success(self):
        # A 'success' completed 48h ago is past the 24h freshness window; P17
        # downgrades it to 'stale' and the probe reports stale / degraded.
        row = _outcome(
            tenant_id=TID_UUID,
            status="success",
            completed_at=NOW - timedelta(hours=48),
            bytes_written=2048,
        )
        db = _mock_db_with([row], [])
        read = await read_backup_check_source(db, TENANT_ID, now=NOW)
        assert read.source_summary == "stale"
        assert read.source_status == "degraded"
        assert read.last_backup_status == "stale"
        assert read.last_backup_status != "success"
        assert read.source_status != "known"
        _assert_non_executing(read)

    async def test_failed_carries_allowlisted_reason_only(self):
        row = _outcome(
            tenant_id=TID_UUID,
            status="failed",
            completed_at=NOW - timedelta(hours=1),
            bytes_written=None,
            failure_reason_code="backup_incomplete",
        )
        db = _mock_db_with([row], [])
        read = await read_backup_check_source(db, TENANT_ID, now=NOW)
        assert read.source_summary == "failed"
        assert read.source_status == "degraded"
        # Allowlisted code only -- never the raw exception / log / command line.
        assert read.failure_reason_redacted == "backup_incomplete"
        from api.v1.platform.p17.schemas import BACKUP_FAILURE_REASONS

        assert read.failure_reason_redacted in BACKUP_FAILURE_REASONS
        assert read.export_available is False
        _assert_non_executing(read)

    async def test_partial_carries_allowlisted_reason_only(self):
        row = _outcome(
            tenant_id=TID_UUID,
            status="partial",
            completed_at=NOW - timedelta(hours=1),
            bytes_written=10,
            failure_reason_code="backup_incomplete",
        )
        db = _mock_db_with([row], [])
        read = await read_backup_check_source(db, TENANT_ID, now=NOW)
        assert read.source_summary == "partial"
        assert read.source_status == "degraded"
        assert read.failure_reason_redacted == "backup_incomplete"
        _assert_non_executing(read)

    async def test_raw_failure_reason_is_collapsed_to_unknown(self):
        # A writer that tried to persist a raw stack trace is collapsed by P17's
        # redact_failure_reason to 'unknown'; the probe carries the allowlisted
        # value and never the raw text.
        raw = "Traceback (most recent call last): OperationalError at host:5432"
        row = _outcome(
            tenant_id=TID_UUID,
            status="failed",
            completed_at=NOW - timedelta(hours=1),
            failure_reason_code=raw,
        )
        db = _mock_db_with([row], [])
        read = await read_backup_check_source(db, TENANT_ID, now=NOW)
        assert read.failure_reason_redacted == "unknown"
        assert "Traceback" not in (read.failure_reason_redacted or "")

    async def test_in_progress_is_degraded(self):
        row = _outcome(
            tenant_id=TID_UUID,
            status="in_progress",
            completed_at=None,
        )
        db = _mock_db_with([row], [])
        read = await read_backup_check_source(db, TENANT_ID, now=NOW)
        assert read.source_summary == "in_progress"
        assert read.source_status == "degraded"
        assert read.source_status != "known"


# ===========================================================================
# Fail-closed: a source read failure never raises and never fabricates health
# ===========================================================================


class TestFailClosed:
    async def test_read_exception_returns_unavailable_no_500(self):
        # The session read raises -> the probe degrades to unavailable / unknown,
        # never raises (no 500), never a fabricated healthy status.
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("backup table unreachable"))
        read = await read_backup_check_source(db, TENANT_ID, now=NOW)
        assert read.source_summary == "unavailable"
        assert read.source_status == "unknown"
        assert read.source_status != "known"
        assert read.reason is not None
        _assert_non_executing(read)

    async def test_loader_returns_none_is_unavailable(self):
        # The P17 loader returns None on a read failure -> unavailable for all.
        db = MagicMock()
        ok = MagicMock()
        ok.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=ok)
        # Force the loader's degrade path by making the first read raise after a
        # successful-looking setup is impossible; instead patch the loader.
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                source_probe,
                "_load_backup_status_map",
                AsyncMock(return_value=None),
            )
            read = await read_backup_check_source(db, TENANT_ID, now=NOW)
        assert read.source_summary == "unavailable"
        assert read.source_status == "unknown"
        _assert_non_executing(read)


# ===========================================================================
# Read-only: the probe issues no mutation on the session
# ===========================================================================


class TestReadOnly:
    async def test_probe_performs_no_session_mutations(self):
        row = _outcome(
            tenant_id=TID_UUID,
            status="success",
            completed_at=NOW - timedelta(hours=1),
            bytes_written=512,
        )
        db = _mock_db_with([row], [])
        await read_backup_check_source(db, TENANT_ID, now=NOW)
        db.add.assert_not_called()
        db.commit.assert_not_called()
        db.flush.assert_not_called()
        db.delete.assert_not_called()

    async def test_platform_wide_read_uses_platform_fallback(self):
        # tenant_id None reads the platform-wide outcome via the loader's own
        # platform-fallback resolution (read-only).
        plat = _outcome(
            tenant_id=None,
            status="success",
            completed_at=NOW - timedelta(hours=1),
            bytes_written=256,
        )
        db = _mock_db_with([plat], [])
        read = await read_backup_check_source(db, None, now=NOW)
        assert read.source_summary == "fresh_success"
        assert read.source_status == "known"
        _assert_non_executing(read)


# ===========================================================================
# Regression: the P22 dry-run / request flow never sets execution flags true
# for backup.check (a passed dry-run is a precondition, not an execution).
# ===========================================================================


@pytest.fixture(autouse=True)
def _reset_p22_state():
    from api.v1.platform.p22 import services

    services.reset_store()
    services.reset_approval_resolver()
    _CURRENT_AUTH["ctx"] = None
    yield
    services.reset_store()
    services.reset_approval_resolver()
    _CURRENT_AUTH["ctx"] = None


class TestDryRunAndRequestNeverExecute:
    def _seed_read_approval(self):
        from api.v1.platform.p22.services import ApprovalSnapshot, set_approval_resolver

        snapshot = ApprovalSnapshot(
            approval_id="ap-bc",
            state="approved_execution_blocked",
            quorum_required=2,
            quorum_met=True,
            maker="maker-1",
            checker_ids=["checker-1", "checker-2"],
            source_status="known",
            action_type="backup.check",
            action_class="read",
            tenant_id=None,
            validation_status="valid",
            expires_at=NOW + timedelta(hours=1),
        )
        approvals = {"ap-bc": snapshot}
        set_approval_resolver(lambda aid: approvals.get(aid))
        return snapshot

    def test_backup_check_dry_run_never_sets_execution_flags(self):
        import asyncio

        from api.v1.platform.p22.schemas import ExecutionDryRunRequest
        from api.v1.platform.p22.services import evaluate_dry_run

        self._seed_read_approval()
        request = ExecutionDryRunRequest(
            durable_approval_id="ap-bc",
            action_type="backup.check",
            tenant_id=None,
            reason="read-only backup status check",
            idempotency_key="probe-key-1",
            execution_mode="sync",
        )
        resp = run_coroutine(
            evaluate_dry_run(
                request,
                actor="exec-1",
                actor_role="super_admin",
                identity_context="identity_only",
            )
        )
        # A passed dry-run for a read against a known source is a PRECONDITION,
        # not an execution: the execution flags stay False regardless.
        assert resp.execution_allowed is False
        assert resp.executed is False
        assert resp.execution_started is False
        # The read source does not block (reads may proceed against known); the
        # verdict may be passed, but it is still never an execution.
        assert resp.verdict in ("passed", "blocked")

    def test_backup_check_request_never_sets_execution_flags(self):
        import asyncio

        from api.v1.platform.p22.schemas import (
            ExecutionDryRunRequest,
            ExecutionRequestCreate,
        )
        from api.v1.platform.p22.services import evaluate_dry_run, record_execution_request

        self._seed_read_approval()
        dry_request = ExecutionDryRunRequest(
            durable_approval_id="ap-bc",
            action_type="backup.check",
            tenant_id=None,
            reason="read-only backup status check",
            idempotency_key="probe-key-2",
            execution_mode="sync",
        )
        dry = run_coroutine(
            evaluate_dry_run(
                dry_request,
                actor="exec-1",
                actor_role="super_admin",
                identity_context="identity_only",
            )
        )
        req = ExecutionRequestCreate(
            durable_approval_id="ap-bc",
            action_type="backup.check",
            tenant_id=None,
            reason="read-only backup status check",
            idempotency_key="probe-key-2",
            dry_run_ref=dry.dry_run_id,
            execution_ack=True,
            execution_mode="sync",
        )
        resp = run_coroutine(
            record_execution_request(
                req,
                actor="exec-1",
                actor_role="super_admin",
                identity_context="identity_only",
            )
        )
        assert resp.execution_allowed is False
        assert resp.executed is False
        assert resp.execution_started is False
        assert resp.result_state in ("dry_run_passed", "blocked")


# ===========================================================================
# No execution primitives: AST scan of the new source_probe module (mirrors the
# P22-E1 no-execution invariant scan).
# ===========================================================================


class TestNoExecutionPrimitives:
    def _source(self):
        path = source_probe.__file__
        with open(path, "r", encoding="utf-8") as fh:
            return path, fh.read()

    def test_no_subprocess_shell_or_execution_call_tokens(self):
        forbidden_bare = {"eval", "exec", "system", "popen", "run"}
        forbidden_os_attrs = {"system", "popen", "execv", "execve"}
        forbidden_attr_substrings = (
            "harness", "execute_action", "run_action", "dispatch_action",
            "drain_queue", "start_worker", "invoke_harness",
        )
        _path, src = self._source()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    assert f.id not in forbidden_bare, f"forbidden bare call {f.id!r}"
                elif isinstance(f, ast.Attribute):
                    dotted = _ast_dotted(f.value)
                    assert not dotted.startswith("subprocess"), "forbidden subprocess call"
                    assert not (dotted == "os" and f.attr in forbidden_os_attrs), (
                        f"forbidden os.{f.attr}"
                    )
                    low = f.attr.lower()
                    assert not any(s in low for s in forbidden_attr_substrings), (
                        f"forbidden execution attr {f.attr!r}"
                    )
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) \
                            and kw.value.value is True:
                        raise AssertionError("shell=True forbidden")

    def test_no_forbidden_imports(self):
        forbidden_import_substrings = (
            "subprocess", "p16", "product", "order", "payment", "invoice",
            "customer", "inventory", "ledger", "billing",
        )
        _path, src = self._source()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                mods.append(node.module or "")
            for m in mods:
                low = m.lower()
                for tok in forbidden_import_substrings:
                    assert tok not in low, f"forbidden import {m!r}"

    def test_no_invocation_token_in_text(self):
        # Defensive raw-text proof on the new module (broader than the seam /
        # adapters text scan): no external-process / shell / eval / SQL token.
        _path, src = self._source()
        tokens = (
            "subprocess", "os.system", "os.popen", "os.execv", "os.execve",
            "shell=True", "shell= True", "eval(", "exec(", "import p16", "from p16",
            ".execute(", "SELECT ", "INSERT ", "UPDATE ", "DELETE ", "DROP ",
            "ALTER ", "TRUNCATE ", "pg_dump",
        )
        for tok in tokens:
            assert tok not in src, f"forbidden token {tok!r} in source_probe.py"

    def test_source_probe_exposes_no_generic_executor_name(self):
        forbidden = ("execute", "execute_action", "run_action", "dispatch", "drain",
                     "invoke", "invoke_harness", "start_worker", "run")
        public = {n for n in dir(source_probe) if not n.startswith("_")}
        for name in forbidden:
            assert name not in public, f"forbidden executor name {name!r}"


# -- helper reused by the AST scan -------------------------------------------


def _ast_dotted(node):
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


# ===========================================================================
# R1: the probe is surfaced through a real P22 runtime read path
# (GET /api/v1/platform/p22/backup-check/source). Proves a NON-TEST runtime
# caller of read_backup_check_source and that fresh / unknown / unavailable
# reads are visible to operators through the guarded P22 API without executing
# anything.
# ===========================================================================


AUTH_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}
SOURCE_PATH = "/api/v1/platform/p22/backup-check/source"

_CURRENT_AUTH: dict = {"ctx": None}


def _auth_ctx(user_id="super-exec"):
    """Return an identity-only super_admin auth context for P10 guard."""
    t = MagicMock()
    t.user_id = user_id
    t.roles = ["super_admin"]
    t.tenant_id = None
    t.tenant_schema = None
    t.is_identity_only = True
    t.is_super_admin = True
    ctx = MagicMock()
    ctx.token = t
    return ctx


def _fake_get_auth_context(*args, **kwargs):
    return _CURRENT_AUTH["ctx"]


def _enable_auth(monkeypatch, user_id="super-exec"):
    """Patch get_auth_context so the P10 guard sees an identity-only super_admin."""
    _CURRENT_AUTH["ctx"] = _auth_ctx(user_id)
    monkeypatch.setattr(
        "api.context.auth.get_auth_context",
        MagicMock(side_effect=_fake_get_auth_context),
    )


def _app_with_outcomes(monkeypatch, outcomes, policies):
    """A TestClient app whose session reads the given outcome/policy rows.

    The best-effort outcome audit is patched to a no-op so the mock session is
    only exercised by the (read-only) P17 source loader the probe reuses.
    """
    from api.dependencies import get_db, get_platform_db
    from api.v1.platform.p22 import routes as p22_routes

    monkeypatch.setattr(p22_routes, "_write_outcome_audit", AsyncMock(return_value=None))
    app = FastAPI()

    async def override():
        yield _mock_db_with(outcomes, policies)

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_platform_db] = app.dependency_overrides[get_db]
    app.include_router(p22_routes.router)
    return app


def _app_with_failing_read(monkeypatch):
    """A TestClient app whose session read raises (source read failure)."""
    from api.dependencies import get_db, get_platform_db
    from api.v1.platform.p22 import routes as p22_routes

    monkeypatch.setattr(p22_routes, "_write_outcome_audit", AsyncMock(return_value=None))
    app = FastAPI()

    async def override():
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("backup table unreachable"))
        yield db

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_platform_db] = app.dependency_overrides[get_db]
    app.include_router(p22_routes.router)
    return app


class TestRouteSurfacesProbe:
    """R1: a real P22 runtime entry point calls and surfaces read_backup_check_source."""

    def test_route_is_a_runtime_caller_of_the_probe(self, monkeypatch):
        # Direct proof: spy on read_backup_check_source at the routes module
        # (the name the route awaits) and assert the route called it.
        from api.dependencies import get_db, get_platform_db
        from api.v1.platform.p22 import routes as p22_routes

        _enable_auth(monkeypatch)
        captured: dict = {}

        async def _spy(db, tenant_id=None, now=None):
            captured["called"] = True
            captured["tenant_id"] = tenant_id
            return BackupCheckSourceRead(
                source_status="known", source_summary="fresh_success", checked_at=NOW
            )

        monkeypatch.setattr(p22_routes, "read_backup_check_source", _spy)
        monkeypatch.setattr(p22_routes, "_write_outcome_audit", AsyncMock(return_value=None))
        app = FastAPI()

        async def override():
            yield _mock_db_with([], [])

        app.dependency_overrides[get_db] = override
        app.dependency_overrides[get_platform_db] = app.dependency_overrides[get_db]
        app.include_router(p22_routes.router)

        with TestClient(app) as c:
            r = c.get(SOURCE_PATH + "?tenant_id=" + TENANT_ID, headers=AUTH_HEADERS)

        assert r.status_code == 200
        assert captured.get("called") is True
        assert captured.get("tenant_id") == TENANT_ID
        body = r.json()
        assert body["source_status"] == "known"
        assert body["source_summary"] == "fresh_success"

    def test_fresh_success_visible_as_known(self, monkeypatch):
        _enable_auth(monkeypatch)
        row = _outcome(
            tenant_id=TID_UUID,
            status="success",
            completed_at=datetime.now(timezone.utc) - timedelta(hours=2),
            bytes_written=2048,
        )
        with TestClient(_app_with_outcomes(monkeypatch, [row], [])) as c:
            body = c.get(SOURCE_PATH + "?tenant_id=" + TENANT_ID, headers=AUTH_HEADERS).json()
        assert body["source_status"] == "known"
        assert body["source_summary"] == "fresh_success"
        assert body["last_backup_status"] == "success"
        # Surfaced through the route, still fully non-executing.
        assert body["executed"] is False
        assert body["execution_allowed"] is False
        assert body["execution_started"] is False
        assert body["realizes_execution"] is False
        assert body["result_state"] == "blocked"
        assert body["adapter_result"] == "not_implemented"

    def test_no_outcome_visible_as_unknown_never_healthy(self, monkeypatch):
        _enable_auth(monkeypatch)
        with TestClient(_app_with_outcomes(monkeypatch, [], [])) as c:
            body = c.get(SOURCE_PATH + "?tenant_id=" + TENANT_ID, headers=AUTH_HEADERS).json()
        assert body["source_status"] == "unknown"
        assert body["source_summary"] == "unknown"
        assert body["source_status"] != "known"

    def test_read_failure_is_fail_closed_unavailable_no_500(self, monkeypatch):
        _enable_auth(monkeypatch)
        with TestClient(_app_with_failing_read(monkeypatch)) as c:
            r = c.get(SOURCE_PATH + "?tenant_id=" + TENANT_ID, headers=AUTH_HEADERS)
        assert r.status_code == 200  # fail-closed, never a 500
        body = r.json()
        assert body["source_summary"] == "unavailable"
        assert body["source_status"] == "unknown"

    def test_route_requires_platform_operator(self, monkeypatch):
        # No auth header -> the P10 guard denies (401/403); the route is guarded
        # by the same surface as the rest of P22.
        with TestClient(_app_with_outcomes(monkeypatch, [], [])) as c:
            r = c.get(SOURCE_PATH + "?tenant_id=" + TENANT_ID)  # no auth header
        assert r.status_code in (401, 403)
