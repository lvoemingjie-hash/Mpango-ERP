"""P22-G governed backup.check execution tests -- the first safe governed action.

Covers the FIRST realized, SAFE governed action in the P22 v0 program: backup.check
completes a governed READ of the P17-D-C source behind the seam preflight, records a
redacted audit event, and never mutates anything. See
``backend/api/v1/platform/p22/governed_execution.py``.

Required coverage (task spec):
  - dry-run does not execute (regression).
  - unapproved / no valid request -> blocked (executed=False).
  - non-allowlisted action cannot execute (this module is backup.check-only).
  - backup.check fresh success -> succeeded / executed=True.
  - stale / partial / failed / in_progress source -> completed_with_warning.
  - no source -> unknown, never healthy.
  - read failure -> failed, fail-closed, no fabricated healthy.
  - tenant_id propagation.
  - audit event carries executed/result/failure/source + no-tenant-mutation.
  - no subprocess / shell / pg_dump / restore / raw SQL (AST scan).
  - G15 invariant preserved (static backup.check descriptor unchanged).
  - the P22-E3 source read stays non-executing / honest.
"""
import ast
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")
os.environ.setdefault("PLATFORM_OPERATOR_SECRET", "test-operator-secret")

from api.v1.platform.p22 import governed_execution as gov  # noqa: E402
from api.v1.platform.p22 import services  # noqa: E402
from api.v1.platform.p22.governed_execution import (  # noqa: E402
    GovernedBackupCheckRequest,
    GovernedBackupCheckResult,
    complete_governed_backup_check,
)
from api.v1.platform.p22.source_probe import BackupCheckSourceRead  # noqa: E402

pytestmark = pytest.mark.unit

NOW = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
TENANT_ID = "b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d"


# ---------------------------------------------------------------------------
# Seeding helpers (mirror the P22-E1 seam-test discipline).
# ---------------------------------------------------------------------------


_APPROVALS: dict = {"by_id": {}}


def _resolver(approval_id):
    return _APPROVALS["by_id"].get(approval_id)


def _seed_approval(approval_id="ap-g", **overrides):
    from api.v1.platform.p22.services import ApprovalSnapshot

    base = dict(
        approval_id=approval_id,
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
        expires_at="2099-01-01T00:00:00+00:00",
    )
    base.update(overrides)
    snap = ApprovalSnapshot(**base)
    _APPROVALS["by_id"][approval_id] = snap
    return snap


def _passed_dry_run(approval_id="ap-g", actor="super-exec", tenant_id=None):
    """Seed a happy approval + run a real P22-B dry-run; return the dry_run_id."""
    from api.v1.platform.p22.schemas import ExecutionDryRunRequest

    services.set_approval_resolver(_resolver)
    _seed_approval(approval_id, action_type="backup.check", action_class="read", tenant_id=tenant_id)
    resp = services.evaluate_dry_run(
        ExecutionDryRunRequest(
            durable_approval_id=approval_id,
            action_type="backup.check",
            tenant_id=tenant_id,
            reason="planned backup status review",
            idempotency_key="idem-dry",
            execution_mode="sync",
        ),
        actor=actor,
        actor_role="super_admin",
        identity_context="identity_only",
    )
    assert resp.executable is True, resp.block_reasons
    return resp.dry_run_id


def _governed_request(
    approval_id="ap-g",
    dry_run_ref=None,
    actor="super-exec",
    tenant_id=None,
):
    """A governed request with every precondition satisfied."""
    return GovernedBackupCheckRequest(
        action_type="backup.check",
        durable_approval_id=approval_id,
        tenant_id=tenant_id,
        requested_state=None,
        dry_run_ref=dry_run_ref,
        execution_ack=True,
        idempotency_key_digest=services._digest("idem-gov"),
        payload_digest=services._digest("payload-gov"),
        actor_id=actor,
        actor_role="super_admin",
        identity_context="identity_only",
        correlation_id="corr-gov-1",
    )


def _source_read(**over):
    """Construct a BackupCheckSourceRead (the proven P22-E3 source shape)."""
    base = dict(
        source_status="unknown",
        source_summary="unknown",
        checked_at=NOW,
    )
    base.update(over)
    return BackupCheckSourceRead(**base)


@pytest.fixture(autouse=True)
def _reset_state():
    services.reset_store()
    services.reset_approval_resolver()
    _APPROVALS["by_id"] = {}
    yield
    services.reset_store()
    services.reset_approval_resolver()
    _APPROVALS["by_id"] = {}


def _patch_read(monkeypatch, read):
    """Patch the read used by the governed layer to a controlled value."""
    async def _fake(db, tenant_id=None, now=None):  # noqa: ANN001
        return read
    monkeypatch.setattr(gov, "read_backup_check_source", _fake)
    return _fake


# ===========================================================================
# Dry-run / non-execution regression
# ===========================================================================


class TestNonExecutingInvariants:
    def test_dry_run_does_not_execute(self):
        # The dry-run is a precondition validator; it never executes.
        from api.v1.platform.p22.schemas import ExecutionDryRunRequest

        services.set_approval_resolver(_resolver)
        _seed_approval(action_type="backup.check", action_class="read")
        resp = services.evaluate_dry_run(
            ExecutionDryRunRequest(
                durable_approval_id="ap-g",
                action_type="backup.check",
                reason="review",
                idempotency_key="idem-dry",
                execution_mode="sync",
            ),
            actor="super-exec",
            actor_role="super_admin",
            identity_context="identity_only",
        )
        assert resp.executed is False
        assert resp.execution_allowed is False
        assert resp.execution_started is False

    def test_module_realizes_only_backup_check(self):
        # The governed request is pinned to backup.check -- the single realized
        # action. A non-allowlisted action cannot be constructed / cannot execute.
        with pytest.raises(ValidationError):
            GovernedBackupCheckRequest(action_type="tenant.pause")
        with pytest.raises(ValidationError):
            GovernedBackupCheckRequest(action_type="support_mode.on")


# ===========================================================================
# Preflight gating: unapproved / no valid request -> blocked (fail-closed)
# ===========================================================================

class TestPreflightBlocking:
    async def test_unapproved_request_is_blocked_not_executed(self, monkeypatch):
        # No approval seeded -> preflight blocks; the read is never reached.
        called = {"read": False}

        async def _fake(db, tenant_id=None, now=None):  # noqa: ANN001
            called["read"] = True
            return _source_read()

        monkeypatch.setattr(gov, "read_backup_check_source", _fake)
        services.set_approval_resolver(_resolver)  # no approval in store
        result = await complete_governed_backup_check(_governed_request(), db=MagicMock())
        assert result.verdict == "blocked"
        assert result.result_state == "blocked"
        assert result.executed is False
        assert called["read"] is False  # fail closed; read never ran
        assert result.audit_recorded is True

    async def test_missing_dry_run_ref_is_blocked(self, monkeypatch):
        services.set_approval_resolver(_resolver)
        _seed_approval(action_type="backup.check", action_class="read")
        result = await complete_governed_backup_check(
            _governed_request(dry_run_ref=None), db=MagicMock()
        )
        assert result.verdict == "blocked"
        assert "dry_run_required" in result.block_reasons or "dry_run_invalid" in result.block_reasons
        assert result.executed is False

    async def test_missing_ack_is_blocked(self, monkeypatch):
        dry = _passed_dry_run()
        req = _governed_request(dry_run_ref=dry)
        req = req.model_copy(update={"execution_ack": False})
        result = await complete_governed_backup_check(req, db=MagicMock())
        assert result.verdict == "blocked"
        assert "execution_ack_required" in result.block_reasons
        assert result.executed is False


# ===========================================================================
# Honest source -> result mapping (the governed read completion)
# ===========================================================================


class TestSourceMapping:
    async def test_fresh_success_succeeds(self, monkeypatch):
        dry = _passed_dry_run()
        _patch_read(
            monkeypatch,
            _source_read(
                source_status="known",
                source_summary="fresh_success",
                last_backup_status="success",
            ),
        )
        result = await complete_governed_backup_check(
            _governed_request(dry_run_ref=dry), db=MagicMock()
        )
        assert result.verdict == "passed"
        assert result.result_state == "succeeded"
        assert result.executed is True
        assert result.source_status == "known"
        assert result.source_summary == "fresh_success"
        assert result.no_tenant_mutated is True
        assert result.execution_allowed is False

    async def test_stale_completes_with_warning(self, monkeypatch):
        dry = _passed_dry_run()
        _patch_read(
            monkeypatch,
            _source_read(source_status="degraded", source_summary="stale", last_backup_status="stale"),
        )
        result = await complete_governed_backup_check(
            _governed_request(dry_run_ref=dry), db=MagicMock()
        )
        assert result.result_state == "completed_with_warning"
        assert result.executed is True
        assert result.source_status == "degraded"
        assert result.warning is not None
        assert result.result_state != "succeeded"

    async def test_partial_completes_with_redacted_reason(self, monkeypatch):
        dry = _passed_dry_run()
        _patch_read(
            monkeypatch,
            _source_read(
                source_status="degraded",
                source_summary="partial",
                last_backup_status="partial",
                failure_reason_redacted="backup_incomplete",
            ),
        )
        result = await complete_governed_backup_check(
            _governed_request(dry_run_ref=dry), db=MagicMock()
        )
        assert result.result_state == "completed_with_warning"
        assert result.executed is True
        assert result.failure_reason_redacted == "backup_incomplete"

    async def test_failed_backup_completes_with_warning(self, monkeypatch):
        dry = _passed_dry_run()
        _patch_read(
            monkeypatch,
            _source_read(
                source_status="degraded",
                source_summary="failed",
                last_backup_status="failed",
                failure_reason_redacted="backup_incomplete",
            ),
        )
        result = await complete_governed_backup_check(
            _governed_request(dry_run_ref=dry), db=MagicMock()
        )
        assert result.result_state == "completed_with_warning"
        assert result.executed is True  # the governed READ completed
        assert result.source_status == "degraded"
        assert result.failure_reason_redacted == "backup_incomplete"

    async def test_in_progress_completes_with_warning(self, monkeypatch):
        dry = _passed_dry_run()
        _patch_read(
            monkeypatch,
            _source_read(source_status="degraded", source_summary="in_progress"),
        )
        result = await complete_governed_backup_check(
            _governed_request(dry_run_ref=dry), db=MagicMock()
        )
        assert result.result_state == "completed_with_warning"
        assert result.source_status == "degraded"

    async def test_no_source_unknown_never_healthy(self, monkeypatch):
        dry = _passed_dry_run()
        _patch_read(
            monkeypatch,
            _source_read(source_status="unknown", source_summary="unknown"),
        )
        result = await complete_governed_backup_check(
            _governed_request(dry_run_ref=dry), db=MagicMock()
        )
        assert result.source_status == "unknown"
        assert result.source_status != "known"
        # The read completed (executed) but honestly reports the source is unknown.
        assert result.executed is True
        assert result.result_state == "completed_with_warning"
        assert result.result_state != "succeeded"

    async def test_read_failure_fail_closed_no_fake_healthy(self, monkeypatch):
        dry = _passed_dry_run()
        _patch_read(
            monkeypatch,
            _source_read(
                source_status="unknown",
                source_summary="unavailable",
                reason="Backup source read failed; status is unavailable.",
            ),
        )
        result = await complete_governed_backup_check(
            _governed_request(dry_run_ref=dry), db=MagicMock()
        )
        assert result.result_state == "failed"
        assert result.executed is False  # the read did NOT complete
        assert result.source_status == "unknown"
        assert result.source_status != "known"


# ===========================================================================
# tenant_id propagation
# ===========================================================================


class TestTenantScope:
    async def test_tenant_id_propagates_and_binds(self, monkeypatch):
        dry = _passed_dry_run(tenant_id=TENANT_ID)
        captured = {}

        async def _fake(db, tenant_id=None, now=None):  # noqa: ANN001
            captured["tenant_id"] = tenant_id
            return _source_read(source_status="known", source_summary="fresh_success")

        monkeypatch.setattr(gov, "read_backup_check_source", _fake)
        result = await complete_governed_backup_check(
            _governed_request(dry_run_ref=dry, tenant_id=TENANT_ID), db=MagicMock()
        )
        assert result.verdict == "passed"
        assert result.tenant_id == TENANT_ID
        assert captured["tenant_id"] == TENANT_ID

    async def test_tenant_mismatch_blocks(self, monkeypatch):
        # Dry-run bound to TENANT_ID but governed request uses a different tenant.
        dry = _passed_dry_run(tenant_id=TENANT_ID)
        other = "11111111-1111-4111-8111-111111111111"
        result = await complete_governed_backup_check(
            _governed_request(dry_run_ref=dry, tenant_id=other), db=MagicMock()
        )
        assert result.verdict == "blocked"
        assert result.executed is False


# ===========================================================================
# Audit
# ===========================================================================


class TestAudit:
    async def test_audit_records_completion_fields(self, monkeypatch):
        dry = _passed_dry_run()
        _patch_read(
            monkeypatch,
            _source_read(
                source_status="degraded",
                source_summary="failed",
                failure_reason_redacted="backup_incomplete",
            ),
        )
        correlation = "corr-gov-1"
        req = _governed_request(dry_run_ref=dry)
        req = req.model_copy(update={"correlation_id": correlation})
        result = await complete_governed_backup_check(req, db=MagicMock())
        assert result.audit_recorded is True

        events = services.audit_log()
        assert len(events) >= 1
        ev = events[-1]
        assert ev.event_type == "execution_succeeded"  # the governed read completed
        assert ev.action_type == "backup.check"
        assert ev.result_state == "executed"  # P22-A coarse state for a completed read
        assert ev.source_status == "degraded"
        assert ev.correlation_id == correlation
        assert ev.idempotency_key_digest == services._digest("idem-gov")
        # The audit reason explicitly states no tenant mutation occurred.
        assert "no tenant mutation" in (ev.reason_redacted or "").lower()

    async def test_audit_records_denial_for_blocked_preflight(self, monkeypatch):
        services.set_approval_resolver(_resolver)  # no approval
        await complete_governed_backup_check(_governed_request(), db=MagicMock())
        ev = services.audit_log()[-1]
        assert ev.event_type == "execution_denied"
        assert ev.result_state == "blocked"

    async def test_audit_records_failure_for_read_error(self, monkeypatch):
        dry = _passed_dry_run()
        _patch_read(
            monkeypatch,
            _source_read(source_status="unknown", source_summary="unavailable"),
        )
        await complete_governed_backup_check(_governed_request(dry_run_ref=dry), db=MagicMock())
        ev = services.audit_log()[-1]
        assert ev.event_type == "execution_failed"
        assert ev.result_state == "execution_failed"


# ===========================================================================
# G15 invariant preserved + E3 source read unchanged
# ===========================================================================


class TestInvariantsPreserved:
    def test_g15_static_descriptor_unchanged(self):
        # P22-G is additive: the static backup.check adapter descriptor stays
        # not_implemented / source_unknown / realizes_execution=False (G15).
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

    async def test_e3_source_read_still_honest(self, monkeypatch):
        # The P22-E3 source probe is unchanged: a no-outcome read is unknown, the
        # route semantics are intact.
        from api.v1.platform.p22.source_probe import read_backup_check_source

        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("unreadable"))
        read = await read_backup_check_source(db, TENANT_ID, now=NOW)
        assert read.source_summary == "unavailable"
        assert read.source_status == "unknown"
        assert read.executed is False


# ===========================================================================
# No execution primitives (AST scan of the new governed module)
# ===========================================================================


class TestNoExecutionPrimitives:
    def _source(self):
        with open(gov.__file__, "r", encoding="utf-8") as fh:
            return fh.read()

    def test_no_subprocess_shell_or_execution_call_tokens(self):
        forbidden_bare = {"eval", "exec", "system", "popen", "run"}
        forbidden_attr_substrings = (
            "harness", "execute_action", "run_action", "dispatch_action",
            "drain_queue", "start_worker", "invoke_harness",
        )
        src = self._source()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    assert f.id not in forbidden_bare, f"forbidden bare call {f.id!r}"
                elif isinstance(f, ast.Attribute):
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
        src = self._source()
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
        src = self._source()
        tokens = (
            "subprocess", "os.system", "os.popen", "os.execv", "os.execve",
            "shell=True", "shell= True", "eval(", "exec(", "import p16", "from p16",
            ".execute(", "SELECT ", "INSERT ", "UPDATE ", "DELETE ", "DROP ",
            "ALTER ", "TRUNCATE ", "pg_dump",
        )
        for tok in tokens:
            assert tok not in src, f"forbidden token {tok!r} in governed_execution.py"
