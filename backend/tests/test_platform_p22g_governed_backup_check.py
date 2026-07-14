"""P22-G governed backup.check execution tests -- the first safe governed action.

P22-G-R1 binds the governed completion to a RECORDED P22 execution request
(execution_request_id). These tests cover the binding gate, the honest source
mapping, the audit (carrying the real execution_request_id), the G15 / seam /
P22-B invariants preserved, and the HTTP route (auth, actor anti-spoof, binding
enforcement). See backend/api/v1/platform/p22/governed_execution.py.
"""
# DC-11T0: use run_coroutine to preserve session-scoped event loop
import sys, os; sys.path.insert(0, os.path.dirname(__file__)); from conftest import run_coroutine
import ast
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

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

NOW = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)
TENANT_ID = "b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d"
AUTH_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}
GOV_PATH = "/api/v1/platform/p22/governed-execution/backup-check"


# ---------------------------------------------------------------------------
# Seeding helpers (mirror the P22-E1 / P22-C test discipline).
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


async def _passed_dry_run(approval_id="ap-g", actor="super-exec", tenant_id=None):
    """Seed a happy approval + run a real P22-B dry-run; return the dry_run_id."""
    from api.v1.platform.p22.schemas import ExecutionDryRunRequest

    services.set_approval_resolver(_resolver)
    _seed_approval(approval_id, action_type="backup.check", action_class="read", tenant_id=tenant_id)
    resp = await services.evaluate_dry_run(
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


async def _record_request(approval_id="ap-g", actor="super-exec", tenant_id=None):
    """Seed approval + dry-run + record a P22-B request; return the record response."""
    from api.v1.platform.p22.schemas import ExecutionRequestCreate

    dry = await _passed_dry_run(approval_id=approval_id, actor=actor, tenant_id=tenant_id)
    record = await services.record_execution_request(
        ExecutionRequestCreate(
            durable_approval_id=approval_id,
            action_type="backup.check",
            tenant_id=tenant_id,
            reason="planned backup status review",
            idempotency_key="idem-rec",
            dry_run_ref=dry,
            execution_ack=True,
            execution_mode="sync",
        ),
        actor=actor,
        actor_role="super_admin",
        identity_context="identity_only",
    )
    assert record.result_state == "dry_run_passed", record.block_reasons
    return record


def _governed_request(record, actor="super-exec", **over):
    """A governed request bound to a recorded request (matching fields)."""
    base = dict(
        action_type="backup.check",
        execution_request_id=record.execution_request_id,
        durable_approval_id=record.durable_approval_id,
        tenant_id=record.tenant_id,
        requested_state=None,
        dry_run_ref=record.dry_run_ref,
        execution_ack=True,
        idempotency_key_digest=record.idempotency_key_digest,
        payload_digest=record.payload_digest,
        actor_id=actor,
        actor_role="super_admin",
        identity_context="identity_only",
        correlation_id="corr-gov-1",
    )
    base.update(over)
    return GovernedBackupCheckRequest(**base)


def _source_read(**over):
    base = dict(source_status="unknown", source_summary="unknown", checked_at=NOW)
    base.update(over)
    return BackupCheckSourceRead(**base)


@pytest.fixture(autouse=True)
def _reset_state():
    services.reset_store()
    services.reset_approval_resolver()
    _APPROVALS["by_id"] = {}
    _CURRENT_AUTH["ctx"] = None
    yield
    services.reset_store()
    services.reset_approval_resolver()
    _APPROVALS["by_id"] = {}
    _CURRENT_AUTH["ctx"] = None


def _patch_read(monkeypatch, read):
    async def _fake(db, tenant_id=None, now=None):  # noqa: ANN001
        return read
    monkeypatch.setattr(gov, "read_backup_check_source", _fake)
    return _fake


# ===========================================================================
# Non-execution invariants
# ===========================================================================


class TestNonExecutingInvariants:
    def test_dry_run_does_not_execute(self):
        import asyncio

        from api.v1.platform.p22.schemas import ExecutionDryRunRequest

        services.set_approval_resolver(_resolver)
        _seed_approval(action_type="backup.check", action_class="read")
        resp = run_coroutine(
            services.evaluate_dry_run(
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
        )
        assert resp.executed is False
        assert resp.execution_allowed is False

    def test_module_realizes_only_backup_check(self):
        with pytest.raises(ValidationError):
            GovernedBackupCheckRequest(action_type="tenant.pause")
        with pytest.raises(ValidationError):
            GovernedBackupCheckRequest(action_type="support_mode.on")


# ===========================================================================
# Recorded-request binding (P22-G-R1)
# ===========================================================================


class TestRequestBinding:
    @pytest.mark.asyncio
    async def test_missing_execution_request_id_blocks(self, monkeypatch):
        record = await _record_request()
        req = _governed_request(record).model_copy(update={"execution_request_id": None})
        result = await complete_governed_backup_check(req, db=MagicMock())
        assert result.verdict == "blocked"
        assert result.result_state == "blocked"
        assert "execution_request_required" in result.block_reasons
        assert result.executed is False

    @pytest.mark.asyncio
    async def test_unknown_execution_request_id_blocks(self, monkeypatch):
        record = await _record_request()
        req = _governed_request(record).model_copy(
            update={"execution_request_id": "req-does-not-exist"}
        )
        result = await complete_governed_backup_check(req, db=MagicMock())
        assert "execution_request_not_found" in result.block_reasons
        assert result.executed is False

    @pytest.mark.asyncio
    async def test_mismatched_field_blocks(self, monkeypatch):
        record = await _record_request()
        # Tamper with the tenant_id after binding -> mismatch.
        req = _governed_request(record).model_copy(
            update={"tenant_id": "11111111-1111-4111-8111-111111111111"}
        )
        result = await complete_governed_backup_check(req, db=MagicMock())
        assert "execution_request_mismatch" in result.block_reasons
        assert result.executed is False

    @pytest.mark.asyncio
    async def test_mismatched_actor_blocks(self, monkeypatch):
        record = await _record_request(actor="super-exec")
        req = _governed_request(record, actor="someone-else")
        result = await complete_governed_backup_check(req, db=MagicMock())
        assert "execution_request_mismatch" in result.block_reasons
        assert result.executed is False


# ===========================================================================
# Honest source -> result mapping (governed read completion)
# ===========================================================================


class TestSourceMapping:
    @pytest.mark.asyncio
    async def test_fresh_success_succeeds(self, monkeypatch):
        record = await _record_request()
        _patch_read(monkeypatch, _source_read(source_status="known", source_summary="fresh_success"))
        result = await complete_governed_backup_check(_governed_request(record), db=MagicMock())
        assert result.verdict == "passed"
        assert result.result_state == "succeeded"
        assert result.executed is True
        assert result.source_status == "known"
        assert result.execution_request_id == record.execution_request_id
        assert result.no_tenant_mutated is True
        assert result.execution_allowed is False

    @pytest.mark.asyncio
    async def test_stale_completes_with_warning(self, monkeypatch):
        record = await _record_request()
        _patch_read(monkeypatch, _source_read(source_status="degraded", source_summary="stale"))
        result = await complete_governed_backup_check(_governed_request(record), db=MagicMock())
        assert result.result_state == "completed_with_warning"
        assert result.executed is True
        assert result.warning is not None

    @pytest.mark.asyncio
    async def test_partial_and_failed_carry_redacted_reason(self, monkeypatch):
        record = await _record_request()
        _patch_read(
            monkeypatch,
            _source_read(
                source_status="degraded", source_summary="partial", failure_reason_redacted="backup_incomplete"
            ),
        )
        result = await complete_governed_backup_check(_governed_request(record), db=MagicMock())
        assert result.result_state == "completed_with_warning"
        assert result.failure_reason_redacted == "backup_incomplete"

    @pytest.mark.asyncio
    async def test_in_progress_completes_with_warning(self, monkeypatch):
        record = await _record_request()
        _patch_read(monkeypatch, _source_read(source_status="degraded", source_summary="in_progress"))
        result = await complete_governed_backup_check(_governed_request(record), db=MagicMock())
        assert result.result_state == "completed_with_warning"

    @pytest.mark.asyncio
    async def test_no_source_unknown_never_healthy(self, monkeypatch):
        record = await _record_request()
        _patch_read(monkeypatch, _source_read(source_status="unknown", source_summary="unknown"))
        result = await complete_governed_backup_check(_governed_request(record), db=MagicMock())
        assert result.source_status == "unknown"
        assert result.source_status != "known"
        assert result.executed is True
        assert result.result_state == "completed_with_warning"
        assert result.result_state != "succeeded"

    @pytest.mark.asyncio
    async def test_read_failure_fail_closed(self, monkeypatch):
        record = await _record_request()
        _patch_read(monkeypatch, _source_read(source_status="unknown", source_summary="unavailable"))
        result = await complete_governed_backup_check(_governed_request(record), db=MagicMock())
        assert result.result_state == "failed"
        assert result.executed is False
        assert result.source_status != "known"


# ===========================================================================
# tenant_id propagation
# ===========================================================================


class TestTenantScope:
    @pytest.mark.asyncio
    async def test_tenant_id_propagates(self, monkeypatch):
        record = await _record_request(tenant_id=TENANT_ID)
        captured = {}

        async def _fake(db, tenant_id=None, now=None):  # noqa: ANN001
            captured["tenant_id"] = tenant_id
            return _source_read(source_status="known", source_summary="fresh_success")

        monkeypatch.setattr(gov, "read_backup_check_source", _fake)
        result = await complete_governed_backup_check(_governed_request(record), db=MagicMock())
        assert result.verdict == "passed"
        assert result.tenant_id == TENANT_ID
        assert captured["tenant_id"] == TENANT_ID


# ===========================================================================
# Audit (carries the real execution_request_id)
# ===========================================================================


class TestAudit:
    @pytest.mark.asyncio
    async def test_audit_carries_execution_request_id(self, monkeypatch):
        record = await _record_request()
        _patch_read(
            monkeypatch,
            _source_read(source_status="degraded", source_summary="failed", failure_reason_redacted="backup_incomplete"),
        )
        await complete_governed_backup_check(_governed_request(record), db=MagicMock())
        ev = services.audit_log()[-1]
        assert ev.event_type == "execution_succeeded"
        assert ev.execution_request_id == record.execution_request_id
        assert ev.action_type == "backup.check"
        assert ev.source_status == "degraded"
        assert "no tenant mutation" in (ev.reason_redacted or "").lower()

    @pytest.mark.asyncio
    async def test_audit_denial_for_missing_binding(self, monkeypatch):
        record = await _record_request()
        req = _governed_request(record).model_copy(update={"execution_request_id": None})
        await complete_governed_backup_check(req, db=MagicMock())
        ev = services.audit_log()[-1]
        assert ev.event_type == "execution_denied"
        assert ev.execution_request_id is None

    @pytest.mark.asyncio
    async def test_audit_failure_for_read_error(self, monkeypatch):
        record = await _record_request()
        _patch_read(monkeypatch, _source_read(source_status="unknown", source_summary="unavailable"))
        await complete_governed_backup_check(_governed_request(record), db=MagicMock())
        ev = services.audit_log()[-1]
        assert ev.event_type == "execution_failed"
        assert ev.execution_request_id == record.execution_request_id


# ===========================================================================
# G15 + E3 invariants preserved
# ===========================================================================


class TestInvariantsPreserved:
    def test_g15_static_descriptor_unchanged(self):
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

    @pytest.mark.asyncio
    async def test_e3_source_read_still_honest(self):
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
                    assert not any(s in low for s in forbidden_attr_substrings), f.attr
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
                for tok in forbidden_import_substrings:
                    assert tok not in m.lower(), f"forbidden import {m!r}"

    def test_no_invocation_token_in_text(self):
        src = self._source()
        for tok in (
            "subprocess", "os.system", "os.popen", "os.execv", "os.execve",
            "shell=True", "shell= True", "eval(", "exec(", "import p16", "from p16",
            ".execute(", "SELECT ", "INSERT ", "UPDATE ", "DELETE ", "DROP ",
            "ALTER ", "TRUNCATE ", "pg_dump",
        ):
            assert tok not in src, f"forbidden token {tok!r}"


# ===========================================================================
# Route-level tests (POST /governed-execution/backup-check)
# ===========================================================================


_CURRENT_AUTH: dict = {"ctx": None}


def _auth_ctx(user_id):
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
    _CURRENT_AUTH["ctx"] = _auth_ctx(user_id)
    monkeypatch.setattr(
        "api.context.auth.get_auth_context",
        MagicMock(side_effect=_fake_get_auth_context),
    )


def _route_app():
    from fastapi import FastAPI
    from api.dependencies import get_db, get_platform_db
    from api.v1.platform.p22 import routes as p22_routes

    app = FastAPI()

    async def override():
        yield MagicMock()

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_platform_db] = app.dependency_overrides[get_db]
    app.include_router(p22_routes.router)
    return app


class TestRoute:
    def test_successful_governed_completion(self, monkeypatch):
        import asyncio

        _enable_auth(monkeypatch)
        record = run_coroutine(_record_request(actor="super-exec"))
        monkeypatch.setattr(gov, "read_backup_check_source", AsyncMock(
            return_value=_source_read(source_status="known", source_summary="fresh_success")))
        monkeypatch.setattr("api.v1.platform.p22.routes._write_outcome_audit", AsyncMock(return_value=None))
        payload = _governed_request(record).model_dump()
        payload["actor_id"] = "SPOOFED-ACTOR"  # ignored; authenticated actor wins
        with TestClient(_route_app()) as c:
            r = c.post(GOV_PATH, json=payload, headers=AUTH_HEADERS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["result_state"] == "succeeded"
        assert body["executed"] is True
        assert body["execution_request_id"] == record.execution_request_id
        assert body["actor_id"] == "super-exec"  # not the spoof
        assert body["no_tenant_mutated"] is True

    def test_missing_auth_denied(self, monkeypatch):
        import asyncio

        # No token AND no platform headers -> the guard denies.
        monkeypatch.setattr(
            "api.context.auth.get_auth_context",
            MagicMock(return_value=None),
        )
        record = run_coroutine(_record_request(actor="super-exec"))
        monkeypatch.setattr(gov, "read_backup_check_source", AsyncMock(return_value=_source_read()))
        payload = _governed_request(record).model_dump()
        with TestClient(_route_app()) as c:
            r = c.post(GOV_PATH, json=payload)  # no auth header
        assert r.status_code in (401, 403)

    def test_missing_execution_request_id_blocked(self, monkeypatch):
        import asyncio

        _enable_auth(monkeypatch)
        record = run_coroutine(_record_request(actor="super-exec"))
        monkeypatch.setattr(gov, "read_backup_check_source", AsyncMock(return_value=_source_read()))
        monkeypatch.setattr("api.v1.platform.p22.routes._write_outcome_audit", AsyncMock(return_value=None))
        payload = _governed_request(record).model_dump()
        payload["execution_request_id"] = None
        with TestClient(_route_app()) as c:
            r = c.post(GOV_PATH, json=payload, headers=AUTH_HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["result_state"] == "blocked"
        assert "execution_request_required" in body["block_reasons"]
        assert body["executed"] is False

    def test_mismatched_execution_request_id_blocked(self, monkeypatch):
        import asyncio

        _enable_auth(monkeypatch)
        record = run_coroutine(_record_request(actor="super-exec"))
        monkeypatch.setattr(gov, "read_backup_check_source", AsyncMock(return_value=_source_read()))
        monkeypatch.setattr("api.v1.platform.p22.routes._write_outcome_audit", AsyncMock(return_value=None))
        payload = _governed_request(record).model_dump()
        payload["execution_request_id"] = "req-does-not-exist"
        with TestClient(_route_app()) as c:
            r = c.post(GOV_PATH, json=payload, headers=AUTH_HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["result_state"] == "blocked"
        assert "execution_request_not_found" in body["block_reasons"]

    def test_audit_contains_execution_request_id(self, monkeypatch):
        import asyncio

        _enable_auth(monkeypatch)
        record = run_coroutine(_record_request(actor="super-exec"))
        monkeypatch.setattr(gov, "read_backup_check_source", AsyncMock(
            return_value=_source_read(source_status="known", source_summary="fresh_success")))
        monkeypatch.setattr("api.v1.platform.p22.routes._write_outcome_audit", AsyncMock(return_value=None))
        with TestClient(_route_app()) as c:
            c.post(GOV_PATH, json=_governed_request(record).model_dump(), headers=AUTH_HEADERS)
        ev = services.audit_log()[-1]
        assert ev.execution_request_id == record.execution_request_id
        assert ev.event_type == "execution_succeeded"
