"""P25-EB integration proofs: P22 resolves durable approvals through the
P20/P21 durable READ path (NO in-memory fallback).

These tests prove the end-to-end alignment introduced in P25-EB:

  durable approval stored through P20/P21 (durable runtime)
    -> P22 dry-run resolves it via the DEFAULT resolver (durable read path)
    -> dry-run passes
    -> execution request recorded
    -> governed backup.check preflight passes

And the fail-closed matrix when the durable read path is unhealthy or returns an
approval that no longer satisfies the preconditions:

  - approval missing (durable read returns None)          -> approval_not_found
  - action mismatch (read returns a different action)     -> action_mismatch_approval
  - non-approved state (read returns pending_review)      -> approval_state_not_approved_execution_blocked
  - storage not ready (_check_durable_readiness = False)  -> approval_not_found (NO memory fallback)
  - read raises (transient db error)                      -> approval_not_found (fail closed)

The DEFAULT resolver (no injected override) is exercised throughout. The P20
durable runtime functions are mocked at the module boundary so the suite is
fully deterministic and free of any real DB / engine / Docker dependency,
while still exercising the real P22 resolution + evaluation code paths.

Aligned to docs/ai/PLATFORM_PRODUCT_P22_CONTROLLED_EXECUTION_V0_CONTRACT.md
(P22-A) and the P25-EB durable approval resolver alignment contract.
"""
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")
os.environ.setdefault("PLATFORM_OPERATOR_SECRET", "test-operator-secret")

from api.v1.platform.p22 import governed_execution as gov  # noqa: E402
from api.v1.platform.p22 import services  # noqa: E402
from api.v1.platform.p22.governed_execution import (  # noqa: E402
    GovernedBackupCheckRequest,
    complete_governed_backup_check,
)
from api.v1.platform.p22.source_probe import BackupCheckSourceRead  # noqa: E402

pytestmark = pytest.mark.unit

P20_READINESS = "api.v1.platform.p20.services._check_durable_readiness"
P20_READ = "api.v1.platform.p20.services.read_durable_approval"


def _durable_record(approval_id="ap-dur-1", **overrides):
    """A P20 DurableApprovalRecord shape (the default resolver maps it)."""
    rec = MagicMock()
    rec.approval_id = approval_id
    rec.state = "approved_execution_blocked"
    rec.quorum_required = 2
    rec.quorum_met = True
    rec.maker = "maker-1"
    rec.checkers = [MagicMock(checker_id="chk-1"), MagicMock(checker_id="chk-2")]
    rec.source_status = "available"  # P20 vocabulary -> P22 'known'
    rec.action_type = "backup.check"
    rec.action_class = "read"
    rec.tenant_id = None
    rec.validation_status = "valid"
    rec.expires_at = "2099-01-01T00:00:00+00:00"
    for k, v in overrides.items():
        setattr(rec, k, v)
    return rec


def _mock_db():
    db = MagicMock()
    ok = MagicMock()
    ok.scalar.return_value = 0
    ok.scalar_one_or_none.return_value = None
    ok.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=ok)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture(autouse=True)
def _reset_p22():
    services.reset_store()
    services.reset_approval_resolver()  # DEFAULT resolver active (no override)
    yield
    services.reset_store()
    services.reset_approval_resolver()


def _ready_and_read(monkeypatch, readiness_ret, read_ret):
    """Wire the durable read path at the P20 module boundary."""
    monkeypatch.setattr(P20_READINESS, AsyncMock(return_value=readiness_ret))
    if isinstance(read_ret, BaseException):
        monkeypatch.setattr(P20_READ, AsyncMock(side_effect=read_ret))
    else:
        monkeypatch.setattr(P20_READ, AsyncMock(return_value=read_ret))


# ===========================================================================
# Happy-path integration: durable approval -> dry-run passes -> recorded
# ===========================================================================


class TestHappyPathDurableResolution:
    @pytest.mark.asyncio
    async def test_dry_run_passes_through_default_durable_resolver(self, monkeypatch):
        """A durable approval resolved through the DEFAULT resolver (durable read
        path) passes the P22 dry-run -- no injected test override is used."""
        from api.v1.platform.p22.schemas import ExecutionDryRunRequest

        _ready_and_read(monkeypatch, (True, "ready"), _durable_record("ap-dur-1"))
        resp = await services.evaluate_dry_run(
            ExecutionDryRunRequest(
                durable_approval_id="ap-dur-1",
                action_type="backup.check",
                reason="planned backup status review",
                idempotency_key="idem-dry-1",
                execution_mode="sync",
            ),
            actor="super-exec",
            actor_role="super_admin",
            identity_context="identity_only",
            db=_mock_db(),
        )
        assert resp.executable is True, resp.block_reasons
        assert resp.verdict == "passed"
        assert resp.dry_run_id is not None
        # source_status 'available' (P20) -> 'known' (P22) via the durable read.
        assert resp.source_status == "known"

    @pytest.mark.asyncio
    async def test_execution_request_recorded_after_durable_dry_run(self, monkeypatch):
        """After a durable-resolved dry-run passes, the execution request is
        recorded at dry_run_passed (never executing)."""
        from api.v1.platform.p22.schemas import ExecutionDryRunRequest, ExecutionRequestCreate

        _ready_and_read(monkeypatch, (True, "ready"), _durable_record("ap-dur-1"))
        dry = await services.evaluate_dry_run(
            ExecutionDryRunRequest(
                durable_approval_id="ap-dur-1",
                action_type="backup.check",
                reason="planned backup status review",
                idempotency_key="idem-dry-2",
                execution_mode="sync",
            ),
            actor="super-exec",
            actor_role="super_admin",
            identity_context="identity_only",
            db=_mock_db(),
        )
        rec = await services.record_execution_request(
            ExecutionRequestCreate(
                durable_approval_id="ap-dur-1",
                action_type="backup.check",
                reason="planned backup status review",
                idempotency_key="idem-rec-2",
                dry_run_ref=dry.dry_run_id,
                execution_ack=True,
                execution_mode="sync",
            ),
            actor="super-exec",
            actor_role="super_admin",
            identity_context="identity_only",
            db=_mock_db(),
        )
        assert rec.result_state == "dry_run_passed", rec.block_reasons
        assert rec.executed is False
        assert rec.execution_allowed is False
        assert rec.execution_started is False
        assert rec.execution_request_id is not None

    @pytest.mark.asyncio
    async def test_governed_backup_check_preflight_passes(self, monkeypatch):
        """The governed backup.check preflight passes when the durable approval
        is resolved (ready + approved) and a matching recorded request is bound."""
        from api.v1.platform.p22.schemas import ExecutionDryRunRequest, ExecutionRequestCreate

        _ready_and_read(monkeypatch, (True, "ready"), _durable_record("ap-dur-1"))
        dry = await services.evaluate_dry_run(
            ExecutionDryRunRequest(
                durable_approval_id="ap-dur-1",
                action_type="backup.check",
                reason="planned backup status review",
                idempotency_key="idem-dry-3",
                execution_mode="sync",
            ),
            actor="super-exec",
            actor_role="super_admin",
            identity_context="identity_only",
            db=_mock_db(),
        )
        record = await services.record_execution_request(
            ExecutionRequestCreate(
                durable_approval_id="ap-dur-1",
                action_type="backup.check",
                reason="planned backup status review",
                idempotency_key="idem-rec-3",
                dry_run_ref=dry.dry_run_id,
                execution_ack=True,
                execution_mode="sync",
            ),
            actor="super-exec",
            actor_role="super_admin",
            identity_context="identity_only",
            db=_mock_db(),
        )
        # The governed read content is fresh success -> completed.
        monkeypatch.setattr(
            gov,
            "read_backup_check_source",
            AsyncMock(
                return_value=BackupCheckSourceRead(
                    source_status="known",
                    source_summary="fresh_success",
                    checked_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
                )
            ),
        )
        result = await complete_governed_backup_check(
            GovernedBackupCheckRequest(
                action_type="backup.check",
                execution_request_id=record.execution_request_id,
                durable_approval_id="ap-dur-1",
                tenant_id=None,
                requested_state=None,
                dry_run_ref=record.dry_run_ref,
                execution_ack=True,
                idempotency_key_digest=record.idempotency_key_digest,
                payload_digest=record.payload_digest,
                actor_id="super-exec",
                actor_role="super_admin",
                identity_context="identity_only",
                correlation_id="corr-p25eb-1",
            ),
            db=_mock_db(),
        )
        assert result.verdict == "passed", result.block_reasons
        assert result.result_state == "succeeded"
        assert result.executed is True
        assert result.no_tenant_mutated is True
        assert result.execution_request_id == record.execution_request_id


# ===========================================================================
# Fail-closed matrix: the durable read path gates every resolution
# ===========================================================================


class TestFailClosedMatrix:
    @pytest.mark.asyncio
    async def test_missing_approval_blocks(self, monkeypatch):
        """Durable storage ready but read returns None -> approval_not_found."""
        from api.v1.platform.p22.schemas import ExecutionDryRunRequest

        _ready_and_read(monkeypatch, (True, "ready"), None)
        resp = await services.evaluate_dry_run(
            ExecutionDryRunRequest(
                durable_approval_id="ghost",
                action_type="backup.check",
                reason="review",
                idempotency_key="idem-miss",
                execution_mode="sync",
            ),
            actor="super-exec",
            actor_role="super_admin",
            identity_context="identity_only",
            db=_mock_db(),
        )
        assert resp.executable is False
        assert "approval_not_found" in resp.block_reasons

    @pytest.mark.asyncio
    async def test_action_mismatch_blocks(self, monkeypatch):
        """The durable record is for a DIFFERENT action -> action_mismatch."""
        from api.v1.platform.p22.schemas import ExecutionDryRunRequest

        # Record is for support_mode.on; the dry-run requests backup.check.
        _ready_and_read(
            monkeypatch,
            (True, "ready"),
            _durable_record("ap-dur-1", action_type="support_mode.on", action_class="write"),
        )
        resp = await services.evaluate_dry_run(
            ExecutionDryRunRequest(
                durable_approval_id="ap-dur-1",
                action_type="backup.check",
                reason="review",
                idempotency_key="idem-mismatch",
                execution_mode="sync",
            ),
            actor="super-exec",
            actor_role="super_admin",
            identity_context="identity_only",
            db=_mock_db(),
        )
        assert resp.executable is False
        assert "action_mismatch_approval" in resp.block_reasons

    @pytest.mark.asyncio
    async def test_non_approved_state_blocks(self, monkeypatch):
        """The durable record is at pending_review -> not approved_execution_blocked."""
        from api.v1.platform.p22.schemas import ExecutionDryRunRequest

        _ready_and_read(
            monkeypatch,
            (True, "ready"),
            _durable_record("ap-dur-1", state="pending_review", quorum_met=False),
        )
        resp = await services.evaluate_dry_run(
            ExecutionDryRunRequest(
                durable_approval_id="ap-dur-1",
                action_type="backup.check",
                reason="review",
                idempotency_key="idem-pending",
                execution_mode="sync",
            ),
            actor="super-exec",
            actor_role="super_admin",
            identity_context="identity_only",
            db=_mock_db(),
        )
        assert resp.executable is False
        assert "approval_state_not_approved_execution_blocked" in resp.block_reasons
        assert "quorum_not_met" in resp.block_reasons

    @pytest.mark.asyncio
    async def test_storage_not_ready_blocks_with_no_memory_fallback(self, monkeypatch):
        """When durable storage is NOT ready, the default resolver returns None
        (approval_not_found) even though it could have fallen back to an
        in-memory store. There is NO memory fallback -- fail closed."""
        from api.v1.platform.p22.schemas import ExecutionDryRunRequest

        # Readiness False; the read mock is never reached but is wired to prove
        # it is NOT consulted past the readiness gate.
        read_mock = AsyncMock(return_value=_durable_record("ap-dur-1"))
        monkeypatch.setattr(P20_READINESS, AsyncMock(return_value=(False, "storage_not_ready")))
        monkeypatch.setattr(P20_READ, read_mock)
        resp = await services.evaluate_dry_run(
            ExecutionDryRunRequest(
                durable_approval_id="ap-dur-1",
                action_type="backup.check",
                reason="review",
                idempotency_key="idem-notready",
                execution_mode="sync",
            ),
            actor="super-exec",
            actor_role="super_admin",
            identity_context="identity_only",
            db=_mock_db(),
        )
        assert resp.executable is False
        assert "approval_not_found" in resp.block_reasons
        # The read was NEVER called -- the readiness gate stopped resolution.
        assert read_mock.await_count == 0

    @pytest.mark.asyncio
    async def test_read_raise_fail_closed(self, monkeypatch):
        """Durable storage ready but the read raises -> fail closed (None)."""
        from api.v1.platform.p22.schemas import ExecutionDryRunRequest

        _ready_and_read(
            monkeypatch,
            (True, "ready"),
            RuntimeError("transient connection error"),
        )
        resp = await services.evaluate_dry_run(
            ExecutionDryRunRequest(
                durable_approval_id="ap-dur-1",
                action_type="backup.check",
                reason="review",
                idempotency_key="idem-raise",
                execution_mode="sync",
            ),
            actor="super-exec",
            actor_role="super_admin",
            identity_context="identity_only",
            db=_mock_db(),
        )
        assert resp.executable is False
        assert "approval_not_found" in resp.block_reasons

    @pytest.mark.asyncio
    async def test_no_db_session_blocks(self, monkeypatch):
        """Without a db session, the default resolver performs NO durable read
        and returns None -> approval_not_found (fail closed)."""
        from api.v1.platform.p22.schemas import ExecutionDryRunRequest

        # Readiness/read wired but must NOT be consulted when db is None.
        read_mock = AsyncMock(return_value=_durable_record("ap-dur-1"))
        monkeypatch.setattr(P20_READINESS, AsyncMock(return_value=(True, "ready")))
        monkeypatch.setattr(P20_READ, read_mock)
        resp = await services.evaluate_dry_run(
            ExecutionDryRunRequest(
                durable_approval_id="ap-dur-1",
                action_type="backup.check",
                reason="review",
                idempotency_key="idem-nodb",
                execution_mode="sync",
            ),
            actor="super-exec",
            actor_role="super_admin",
            identity_context="identity_only",
            db=None,
        )
        assert resp.executable is False
        assert "approval_not_found" in resp.block_reasons
        assert read_mock.await_count == 0


# ===========================================================================
# Non-execution invariants hold through the durable path
# ===========================================================================


class TestNonExecutionInvariants:
    @pytest.mark.asyncio
    async def test_durable_resolved_dry_run_never_executes(self, monkeypatch):
        from api.v1.platform.p22.schemas import ExecutionDryRunRequest

        _ready_and_read(monkeypatch, (True, "ready"), _durable_record("ap-dur-1"))
        resp = await services.evaluate_dry_run(
            ExecutionDryRunRequest(
                durable_approval_id="ap-dur-1",
                action_type="backup.check",
                reason="review",
                idempotency_key="idem-inv",
                execution_mode="sync",
            ),
            actor="super-exec",
            actor_role="super_admin",
            identity_context="identity_only",
            db=_mock_db(),
        )
        assert resp.executed is False
        assert resp.execution_allowed is False
        assert resp.execution_started is False
        assert resp.result_state not in {
            "executing", "executed", "execution_failed",
            "compensation_required", "compensation_completed", "cancelled",
        } if hasattr(resp, "result_state") else True
