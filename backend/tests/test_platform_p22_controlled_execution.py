"""
P22 Controlled Execution v0 -- non-executing backend skeleton tests (P22-B).

Contract-backed, NON-EXECUTING skeleton: catalog read, dry-run validator,
execution-request recording, and execution-result read. Nothing is ever
executed; every response carries execution_allowed == False, executed == False,
execution_started == False, and a result_state that is only ever
dry_run_passed | blocked.

Coverage:
  - catalog: exactly seven allowlisted actions; named exclusions present;
    storage == memory; executed False; requires platform auth.
  - dry-run passed for a valid allowlisted action + valid durable approval;
    returns dry_run_id + expected_audit_shape; reversible for paired writes;
    execution_allowed False.
  - dry-run blocked for: approval missing, approval not approved_execution_blocked,
    quorum false, source unknown for a write, action excluded (tenant.pause /
    tenant.resume / lifecycle.transition), action not allowlisted, self-execution,
    checker-execution, action/approval mismatch, missing idempotency key.
  - degraded read: a read against a degraded source is executable with
    source_status degraded (writes still blocked).
  - executor denials: support_operator / engineering_operator /
    tenant-contextual super_admin / tenant admin denied; no-auth 401.
  - execution request: recorded after a passed dry-run + ack; requires
    dry_run_ref; requires execution_ack; requires idempotency_key; blocked when a
    precondition fails; result_state never executing / executed.
  - idempotency: same key + same payload is a replay (original result, no new
    success audit); same key + different payload is a conflict (blocked, audited
    as execution_denied); raw key never stored / returned.
  - redaction: sensitive reason -> [redacted]; sensitive metadata redacted.
  - read / list: list filters; read 404 when missing; read returns redacted record.
  - audit: events redacted; no raw key in any audit field; dry-run emits
    requested + passed/blocked.
  - no-execution invariants: no subprocess / shell / P16-harness / execute call
    tokens in the p22 source; no tenant / payment / product imports; no execute
    function; realized result_state values only dry_run_passed | blocked.

The durable approval is resolved through an injected test resolver (the P22
resolver seam) that returns crafted ApprovalSnapshot objects, so the suite is
fully deterministic and free of any DB / async-engine / Docker dependency. The
default resolver (P20 in-memory read path) is exercised separately.

Aligned to docs/ai/PLATFORM_PRODUCT_P22_CONTROLLED_EXECUTION_V0_CONTRACT.md
(P22-A).
"""
import ast
import json
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")
os.environ.setdefault("PLATFORM_OPERATOR_SECRET", "test-operator-secret")


# -- Constants ----------------------------------------------------------------

AUTH_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}
OPERATOR_HEADERS = {"X-Platform-Operator": "test-operator-secret"}
P22 = "/api/v1/platform/p22/execution"

ALLOWLIST = [
    "support_mode.on",
    "support_mode.off",
    "incident.flag_set",
    "incident.flag_clear",
    "provisioning.recheck",
    "backup.check",
    "backup.restore_test_request",
]
EXECUTING_STATES = {"execution_queued", "executing", "executed", "execution_failed",
                    "compensation_required", "compensation_completed", "cancelled"}

FUTURE = "2099-01-01T00:00:00+00:00"

# Mutable per-request auth context + injected durable-approval snapshots.
_ACTIVE_PATCHERS: list = []
_CURRENT_AUTH: dict = {"ctx": None}
_CURRENT_APPROVALS: dict = {"by_id": {}}


# -- Harness (mirrors the P15/P17/P18/P19/P20 test harness) -------------------


def _start_patch(target, new):
    p = patch(target, new=new)
    p.start()
    _ACTIVE_PATCHERS.append(p)
    return p


@pytest.fixture(autouse=True)
def _reset_p22_state():
    from api.v1.platform.p22 import services

    services.reset_store()
    services.reset_approval_resolver()
    _CURRENT_AUTH["ctx"] = None
    _CURRENT_APPROVALS["by_id"] = {}
    yield
    services.reset_approval_resolver()
    while _ACTIVE_PATCHERS:
        _ACTIVE_PATCHERS.pop().stop()


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


def _auth_ctx(user_id, *, identity_only=True, super_admin=True, roles=None, tenant_id=None):
    t = MagicMock()
    t.user_id = user_id
    t.roles = list(roles if roles is not None else (["super_admin"] if super_admin else []))
    t.tenant_id = tenant_id
    t.tenant_schema = "t_other" if tenant_id else None
    t.is_identity_only = identity_only and not tenant_id
    t.is_super_admin = super_admin
    return MagicMock(token=t)


def _fake_get_auth_context(*args, **kwargs):
    ctx = _CURRENT_AUTH["ctx"]
    if ctx is None:
        raise RuntimeError("no auth context attached")
    return ctx


def _enable_auth():
    _start_patch(
        "api.context.auth.get_auth_context", MagicMock(side_effect=_fake_get_auth_context)
    )


def _as(user_id):
    _CURRENT_AUTH["ctx"] = _auth_ctx(user_id)
    return user_id


def _as_tenant_contextual(user_id):
    _CURRENT_AUTH["ctx"] = _auth_ctx(
        user_id, identity_only=False, super_admin=True, tenant_id="t-ctx-tenant"
    )


def _as_tenant_admin(user_id):
    _CURRENT_AUTH["ctx"] = _auth_ctx(
        user_id, identity_only=False, super_admin=False, roles=["tenant_admin"],
        tenant_id="t-ctx-tenant",
    )


def _as_support(user_id):
    _CURRENT_AUTH["ctx"] = _auth_ctx(
        user_id, identity_only=True, super_admin=False, roles=["support_operator"]
    )


def _as_engineering(user_id):
    _CURRENT_AUTH["ctx"] = _auth_ctx(
        user_id, identity_only=True, super_admin=False, roles=["engineering_operator"]
    )


def _as_no_auth():
    _CURRENT_AUTH["ctx"] = None


# -- Durable approval snapshots (injected via the P22 resolver seam) ----------


def _resolver(approval_id):
    return _CURRENT_APPROVALS["by_id"].get(approval_id)


def _seed(approval_id="ap-1", **overrides):
    """Seed a durable-approval snapshot with happy-path defaults."""
    from api.v1.platform.p22.services import ApprovalSnapshot

    base = dict(
        approval_id=approval_id,
        state="approved_execution_blocked",
        quorum_required=2,
        quorum_met=True,
        maker="maker-1",
        checker_ids=["checker-1", "checker-2"],
        source_status="known",
        action_type="support_mode.on",
        action_class="write",
        tenant_id=None,
        validation_status="valid",
        expires_at=FUTURE,
    )
    base.update(overrides)
    snap = ApprovalSnapshot(**base)
    _CURRENT_APPROVALS["by_id"][approval_id] = snap
    return snap


def _make_app():
    from api.dependencies import get_db
    from api.v1.platform.p22 import services
    from api.v1.platform.p22.routes import router

    services.reset_store()
    services.set_approval_resolver(_resolver)
    app = FastAPI()

    async def override():
        yield _mock_db()

    app.dependency_overrides[get_db] = override
    app.include_router(router)
    return app


def _client(authed=True, as_user="super-exec"):
    """Build a TestClient. authed=True enables the mutable actor harness as super-exec."""
    if authed:
        _enable_auth()
        _as(as_user)
    return TestClient(_make_app())


def _dry_run_payload(approval_id="ap-1", action_type="support_mode.on", **over):
    payload = {
        "durable_approval_id": approval_id,
        "action_type": action_type,
        "reason": "planned support window",
        "idempotency_key": "idem-dry-1",
        "execution_mode": "sync",
    }
    payload.update(over)
    return payload


def _request_payload(approval_id="ap-1", action_type="support_mode.on", dry_run_ref=None, **over):
    payload = {
        "durable_approval_id": approval_id,
        "action_type": action_type,
        "reason": "planned support window",
        "idempotency_key": "idem-req-1",
        "dry_run_ref": dry_run_ref,
        "execution_ack": True,
        "execution_mode": "sync",
    }
    payload.update(over)
    return payload


def _passed_dry_run(c, approval_id="ap-1", action_type="support_mode.on", **seed_over):
    """Seed a happy approval, run a dry-run, assert passed, return the response json."""
    _seed(approval_id, action_type=action_type, **seed_over)
    r = c.post(f"{P22}/dry-run", json=_dry_run_payload(approval_id, action_type),
               headers=AUTH_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["executable"] is True
    assert body["verdict"] == "passed"
    return body


# ============================================================================
# Catalog
# ============================================================================


def test_catalog_returns_exactly_seven_allowlisted_actions():
    with _client() as c:
        r = c.get(f"{P22}/catalog", headers=AUTH_HEADERS)
    assert r.status_code == 200
    body = r.json()
    types = [i["action_type"] for i in body["items"]]
    assert types == ALLOWLIST
    assert body["total"] == 7


def test_catalog_named_excluded_actions_listed():
    with _client() as c:
        body = c.get(f"{P22}/catalog", headers=AUTH_HEADERS).json()
    excluded = {e["action_type"] for e in body["exclusions"]}
    # The three explicitly excluded lifecycle actions are named.
    assert {"tenant.pause", "tenant.resume", "lifecycle.transition"} <= excluded
    # Real restore, schema migration, data deletion, payment/billing, shell/SQL/script
    # are all represented in the exclusion list.
    assert any("restore" in e for e in excluded)
    assert any("migration" in e for e in excluded)
    assert any("deletion" in e for e in excluded)
    assert any("payment" in e for e in excluded)
    assert any("shell" in e for e in excluded)


def test_catalog_storage_memory_and_not_executed():
    with _client() as c:
        body = c.get(f"{P22}/catalog", headers=AUTH_HEADERS).json()
    assert body["storage"] == "memory"
    assert body["executed"] is False
    # No excluded action appears in the allowlist items.
    assert all(i["action_type"] in ALLOWLIST for i in body["items"])


def test_catalog_requires_platform_credentials():
    # No auth harness enabled and no credential header -> 401 at the P10 guard.
    with TestClient(_make_app()) as c:
        r = c.get(f"{P22}/catalog")  # no header
    assert r.status_code == 401


# ============================================================================
# Dry-run passed
# ============================================================================


def test_dry_run_passed_for_valid_write():
    with _client() as c:
        body = _passed_dry_run(c, "ap-1", "support_mode.on")
    assert body["dry_run_id"] is not None
    assert body["execution_allowed"] is False
    assert body["executed"] is False
    assert body["execution_started"] is False


def test_dry_run_passed_for_read_action():
    with _client() as c:
        body = _passed_dry_run(c, "ap-r", "provisioning.recheck",
                               action_class="read", source_status="known")
    assert body["executable"] is True
    assert body["verdict"] == "passed"


def test_dry_run_passed_returns_expected_audit_shape_field_names_only():
    with _client() as c:
        body = _passed_dry_run(c)
    shape = body["expected_audit_shape"]
    assert "execution_dry_run_requested" in shape
    assert "execution_dry_run_passed" in shape
    # Field NAMES only: no reason value, no secret, no raw payload leaks into the shape.
    blob = json.dumps(shape)
    assert "planned support window" not in blob
    assert "idem-dry-1" not in blob


def test_dry_run_reversible_for_paired_writes_not_reads():
    with _client() as c:
        on = _passed_dry_run(c, "ap-on", "support_mode.on")
        read = _passed_dry_run(c, "ap-r", "provisioning.recheck",
                               action_class="read", source_status="known")
    assert on["reversible"] is True
    assert read["reversible"] is False


# ============================================================================
# Dry-run blocked
# ============================================================================


def test_dry_run_blocked_when_approval_missing():
    with _client() as c:
        # No _seed -> resolver returns None -> approval_not_found.
        r = c.post(f"{P22}/dry-run", json=_dry_run_payload("ghost"), headers=AUTH_HEADERS)
    body = r.json()
    assert body["executable"] is False
    assert body["verdict"] == "blocked"
    assert "approval_not_found" in body["block_reasons"]


def test_dry_run_blocked_when_approval_not_approved_state():
    with _client() as c:
        _seed("ap-1", state="pending_review")
        r = c.post(f"{P22}/dry-run", json=_dry_run_payload("ap-1"), headers=AUTH_HEADERS)
    assert "approval_state_not_approved_execution_blocked" in r.json()["block_reasons"]


def test_dry_run_blocked_when_quorum_false():
    with _client() as c:
        _seed("ap-1", quorum_met=False)
        r = c.post(f"{P22}/dry-run", json=_dry_run_payload("ap-1"), headers=AUTH_HEADERS)
    assert "quorum_not_met" in r.json()["block_reasons"]


def test_dry_run_blocked_when_source_unknown_for_write():
    with _client() as c:
        _seed("ap-1", source_status="unknown")
        r = c.post(f"{P22}/dry-run", json=_dry_run_payload("ap-1"), headers=AUTH_HEADERS)
    assert "source_unknown_for_write" in r.json()["block_reasons"]


def test_dry_run_blocked_when_action_excluded_tenant_pause():
    with _client() as c:
        _seed("ap-1", action_type="tenant.pause")
        r = c.post(f"{P22}/dry-run", json=_dry_run_payload("ap-1", "tenant.pause"),
                   headers=AUTH_HEADERS)
    body = r.json()
    assert body["executable"] is False
    assert "action_excluded" in body["block_reasons"]


def test_dry_run_blocked_when_action_excluded_lifecycle_transition():
    with _client() as c:
        _seed("ap-1", action_type="lifecycle.transition")
        r = c.post(f"{P22}/dry-run",
                   json=_dry_run_payload("ap-1", "lifecycle.transition"),
                   headers=AUTH_HEADERS)
    assert "action_excluded" in r.json()["block_reasons"]


def test_dry_run_blocked_when_action_not_allowlisted():
    with _client() as c:
        r = c.post(f"{P22}/dry-run",
                   json=_dry_run_payload("ap-1", "orders.refund"),
                   headers=AUTH_HEADERS)
    assert "action_not_allowlisted" in r.json()["block_reasons"]


def test_dry_run_blocked_when_self_execution():
    with _client() as c:
        # The authenticated executor is "super-exec"; make it the maker.
        _seed("ap-1", maker="super-exec")
        r = c.post(f"{P22}/dry-run", json=_dry_run_payload("ap-1"), headers=AUTH_HEADERS)
    assert "self_execution_forbidden" in r.json()["block_reasons"]


def test_dry_run_blocked_when_checker_execution():
    with _client() as c:
        # The authenticated executor is "super-exec"; make it one of the checkers.
        _seed("ap-1", checker_ids=["checker-1", "super-exec"])
        r = c.post(f"{P22}/dry-run", json=_dry_run_payload("ap-1"), headers=AUTH_HEADERS)
    assert "checker_execution_forbidden" in r.json()["block_reasons"]


def test_dry_run_blocked_when_action_mismatch_approval():
    with _client() as c:
        # Approval is for support_mode.off; request tries support_mode.on.
        _seed("ap-1", action_type="support_mode.off")
        r = c.post(f"{P22}/dry-run", json=_dry_run_payload("ap-1", "support_mode.on"),
                   headers=AUTH_HEADERS)
    assert "action_mismatch_approval" in r.json()["block_reasons"]


def test_dry_run_blocked_when_idempotency_key_missing():
    with _client() as c:
        _seed("ap-1")
        payload = _dry_run_payload("ap-1")
        payload["idempotency_key"] = ""
        r = c.post(f"{P22}/dry-run", json=payload, headers=AUTH_HEADERS)
    assert "idempotency_key_required" in r.json()["block_reasons"]


# ============================================================================
# Degraded read
# ============================================================================


def test_dry_run_degraded_read_is_executable():
    with _client() as c:
        _seed("ap-r", action_type="provisioning.recheck", action_class="read",
              source_status="degraded")
        r = c.post(f"{P22}/dry-run",
                   json=_dry_run_payload("ap-r", "provisioning.recheck"),
                   headers=AUTH_HEADERS)
    body = r.json()
    assert body["executable"] is True
    assert body["source_status"] == "degraded"


def test_dry_run_write_against_degraded_source_blocked():
    # A write may NEVER take the degraded path (P22-A 10.4 / C24).
    with _client() as c:
        _seed("ap-1", source_status="degraded")
        r = c.post(f"{P22}/dry-run", json=_dry_run_payload("ap-1"), headers=AUTH_HEADERS)
    body = r.json()
    assert body["executable"] is False
    assert "source_unknown_for_write" in body["block_reasons"]


# ============================================================================
# Executor denials
# ============================================================================


def test_dry_run_support_operator_denied_as_executor():
    # The operator secret passes the transport guard in ANY env (it is the
    # production-valid machine credential); the executor precondition then reads
    # the authenticated support_operator identity and blocks it. This keeps the
    # test deterministic regardless of MPANGO_ENV (the test-override header only
    # satisfies the guard in test|testing env).
    with _client() as c:  # _client() already _as("super-exec"); override below.
        _as_support("sup-1")
        _seed("ap-1")
        r = c.post(f"{P22}/dry-run", json=_dry_run_payload("ap-1"), headers=OPERATOR_HEADERS)
    assert r.status_code == 200  # guard passed via operator secret
    assert "executor_not_identity_super_admin" in r.json()["block_reasons"]


def test_dry_run_engineering_operator_denied_as_executor():
    with _client() as c:
        _as_engineering("eng-1")
        _seed("ap-1")
        r = c.post(f"{P22}/dry-run", json=_dry_run_payload("ap-1"), headers=OPERATOR_HEADERS)
    assert r.status_code == 200
    assert "executor_not_identity_super_admin" in r.json()["block_reasons"]


def test_dry_run_tenant_contextual_super_admin_denied():
    with _client() as c:
        _as_tenant_contextual("super-ctx")
        _seed("ap-1")
        r = c.post(f"{P22}/dry-run", json=_dry_run_payload("ap-1"), headers=OPERATOR_HEADERS)
    assert r.status_code == 200
    assert "executor_not_identity_super_admin" in r.json()["block_reasons"]


def test_dry_run_tenant_admin_denied():
    with _client() as c:
        _as_tenant_admin("tadmin-1")
        _seed("ap-1")
        r = c.post(f"{P22}/dry-run", json=_dry_run_payload("ap-1"), headers=OPERATOR_HEADERS)
    body = r.json()
    assert r.status_code == 200
    assert body["executable"] is False
    assert "executor_not_identity_super_admin" in body["block_reasons"]


def test_operator_secret_without_identity_actor_denied():
    # The operator secret passes the transport guard, but there is no authenticated
    # identity-only super_admin actor -> the executor precondition fails.
    _enable_auth()
    _as_no_auth()
    app = _make_app()
    with TestClient(app) as c:
        _seed("ap-1")
        r = c.post(f"{P22}/dry-run", json=_dry_run_payload("ap-1"), headers=OPERATOR_HEADERS)
    assert r.status_code == 200  # guard passed via operator secret
    assert "executor_not_identity_super_admin" in r.json()["block_reasons"]


# ============================================================================
# Execution request
# ============================================================================


def test_request_recorded_after_passed_dry_run():
    with _client() as c:
        dry = _passed_dry_run(c, "ap-1", "support_mode.on")
        r = c.post(f"{P22}/requests",
                   json=_request_payload("ap-1", "support_mode.on", dry["dry_run_id"]),
                   headers=AUTH_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["execution_request_id"] is not None
    assert body["result_state"] == "dry_run_passed"
    assert body["result"] == "recorded"
    assert body["executed"] is False
    assert body["execution_started"] is False
    assert body["execution_allowed"] is False


def test_request_requires_dry_run_ref():
    with _client() as c:
        _seed("ap-1")
        r = c.post(f"{P22}/requests",
                   json=_request_payload("ap-1", "support_mode.on", dry_run_ref=None),
                   headers=AUTH_HEADERS)
    body = r.json()
    assert body["result_state"] == "blocked"
    assert "dry_run_required" in body["block_reasons"]


def test_request_requires_execution_ack():
    with _client() as c:
        dry = _passed_dry_run(c)
        r = c.post(f"{P22}/requests",
                   json=_request_payload("ap-1", "support_mode.on", dry["dry_run_id"],
                                         execution_ack=False),
                   headers=AUTH_HEADERS)
    body = r.json()
    assert body["result_state"] == "blocked"
    assert "execution_ack_required" in body["block_reasons"]


def test_request_requires_idempotency_key():
    with _client() as c:
        dry = _passed_dry_run(c)
        payload = _request_payload("ap-1", "support_mode.on", dry["dry_run_id"])
        payload["idempotency_key"] = ""
        r = c.post(f"{P22}/requests", json=payload, headers=AUTH_HEADERS)
    assert "idempotency_key_required" in r.json()["block_reasons"]


def test_request_blocked_when_precondition_revalidated_fails():
    with _client() as c:
        dry = _passed_dry_run(c)  # ap-1 approved at dry-run time
        # The approval expires / changes state between dry-run and request.
        _seed("ap-1", state="expired")
        r = c.post(f"{P22}/requests",
                   json=_request_payload("ap-1", "support_mode.on", dry["dry_run_id"]),
                   headers=AUTH_HEADERS)
    body = r.json()
    assert body["result_state"] == "blocked"
    assert "approval_state_not_approved_execution_blocked" in body["block_reasons"]
    assert body["execution_request_id"] is None  # not recorded


def test_request_result_state_never_executing_or_executed():
    with _client() as c:
        dry = _passed_dry_run(c)
        body = c.post(f"{P22}/requests",
                      json=_request_payload("ap-1", "support_mode.on", dry["dry_run_id"]),
                      headers=AUTH_HEADERS).json()
    assert body["result_state"] == "dry_run_passed"
    assert body["result_state"] not in EXECUTING_STATES


# ============================================================================
# Idempotency + raw-key secrecy
# ============================================================================


def test_idempotency_replay_same_payload_returns_original():
    with _client() as c:
        dry = _passed_dry_run(c)
        payload = _request_payload("ap-1", "support_mode.on", dry["dry_run_id"],
                                   idempotency_key="k-replay")
        first = c.post(f"{P22}/requests", json=payload, headers=AUTH_HEADERS).json()
        second = c.post(f"{P22}/requests", json=payload, headers=AUTH_HEADERS).json()
    # A replay returns the original execution_request_id and result, with no new
    # success audit event (P22-A 9 / C20).
    assert second["execution_request_id"] == first["execution_request_id"]
    assert second["result_state"] == first["result_state"]
    assert _audit_event_types().count("execution_requested") == 1


def test_idempotency_replay_does_not_double_record():
    with _client() as c:
        dry = _passed_dry_run(c)
        payload = _request_payload("ap-1", "support_mode.on", dry["dry_run_id"],
                                   idempotency_key="k-replay-2")
        c.post(f"{P22}/requests", json=payload, headers=AUTH_HEADERS)
        c.post(f"{P22}/requests", json=payload, headers=AUTH_HEADERS)
        listed = c.get(f"{P22}/requests", headers=AUTH_HEADERS).json()
    assert listed["total"] == 1  # replay did not create a second record


def test_idempotency_conflict_different_payload():
    with _client() as c:
        # Request 1: support_mode.on against ap-1.
        dry1 = _passed_dry_run(c, "ap-1", "support_mode.on")
        c.post(f"{P22}/requests",
               json=_request_payload("ap-1", "support_mode.on", dry1["dry_run_id"],
                                     idempotency_key="k-conflict"),
               headers=AUTH_HEADERS)
        # Request 2: SAME key, DIFFERENT payload (incident.flag_set against ap-2).
        dry2 = _passed_dry_run(c, "ap-2", "incident.flag_set")
        r = c.post(f"{P22}/requests",
                   json=_request_payload("ap-2", "incident.flag_set", dry2["dry_run_id"],
                                         idempotency_key="k-conflict"),
                   headers=AUTH_HEADERS)
    body = r.json()
    assert body["result_state"] == "blocked"
    assert body["result"] == "conflict"
    assert "idempotency_conflict" in body["block_reasons"]
    assert body["execution_request_id"] is None  # the conflicting request was not recorded
    # The conflict is audited as an execution_denied event.
    assert "execution_denied" in _audit_event_types()


def test_raw_idempotency_key_never_stored_or_returned():
    secret_key = "RAW-SECRET-IDEM-KEY-12345"  # pragma: allowlist secret
    with _client() as c:
        dry = _passed_dry_run(c)
        body = c.post(f"{P22}/requests",
                      json=_request_payload("ap-1", "support_mode.on", dry["dry_run_id"],
                                            idempotency_key=secret_key),
                      headers=AUTH_HEADERS).json()
        listed = c.get(f"{P22}/requests", headers=AUTH_HEADERS).json()
    # The raw key never appears in the create response.
    assert secret_key not in json.dumps(body)
    # A digest IS returned (digest-only, never the raw key).
    assert body["idempotency_key_digest"]
    assert body["idempotency_key_digest"] != secret_key
    # The raw key never appears in the listed record or any audit event.
    assert secret_key not in json.dumps(listed)
    assert secret_key not in json.dumps([e.model_dump() for e in _audit_log_raw()], default=str)


# ============================================================================
# Redaction
# ============================================================================


def test_sensitive_reason_redacted_on_dry_run():
    with _client() as c:
        _seed("ap-1")
        payload = _dry_run_payload("ap-1")
        payload["reason"] = "rotate db; password=hunter2 dsn=postgres://u:p@host:5432"  # pragma: allowlist secret
        body = c.post(f"{P22}/dry-run", json=payload, headers=AUTH_HEADERS).json()
    # The response does not echo the reason field, and audit never holds the raw value.
    assert "hunter2" not in json.dumps(body)
    assert "hunter2" not in json.dumps([e.model_dump() for e in _audit_log_raw()], default=str)


def test_sensitive_metadata_redacted_on_request():
    with _client() as c:
        dry = _passed_dry_run(c)
        payload = _request_payload("ap-1", "support_mode.on", dry["dry_run_id"])
        payload["metadata"] = {"db_password": "s3cr3t", "note": "ok"}  # pragma: allowlist secret
        body = c.post(f"{P22}/requests", json=payload, headers=AUTH_HEADERS).json()
    md = body["metadata_redacted"]
    assert md["db_password"] == "[redacted]"
    assert md["note"] == "ok"
    assert "s3cr3t" not in json.dumps(body)


# ============================================================================
# Read / list
# ============================================================================


def test_list_execution_requests_filters_by_result_state():
    with _client() as c:
        dry = _passed_dry_run(c)
        c.post(f"{P22}/requests",
               json=_request_payload("ap-1", "support_mode.on", dry["dry_run_id"]),
               headers=AUTH_HEADERS)
        listed = c.get(f"{P22}/requests?result_state=dry_run_passed",
                       headers=AUTH_HEADERS).json()
    assert listed["total"] == 1
    assert listed["storage"] == "memory"
    assert listed["executed"] is False


def test_read_execution_request_404_when_missing():
    with _client() as c:
        r = c.get(f"{P22}/requests/does-not-exist", headers=AUTH_HEADERS)
    assert r.status_code == 404


def test_read_execution_request_returns_redacted_record():
    with _client() as c:
        dry = _passed_dry_run(c)
        created = c.post(f"{P22}/requests",
                         json=_request_payload("ap-1", "support_mode.on", dry["dry_run_id"],
                                               idempotency_key="k-read"),
                         headers=AUTH_HEADERS).json()
        rid = created["execution_request_id"]
        body = c.get(f"{P22}/requests/{rid}", headers=AUTH_HEADERS).json()
    assert body["execution_request_id"] == rid
    assert body["result_state"] == "dry_run_passed"
    assert body["executed"] is False
    assert "k-read" not in json.dumps(body)  # raw key never returned on read


# ============================================================================
# Audit shape
# ============================================================================


def test_dry_run_emits_requested_plus_passed_or_blocked():
    with _client() as c:
        _passed_dry_run(c)  # passed
        types_passed = _audit_event_types()
    assert "execution_dry_run_requested" in types_passed
    assert "execution_dry_run_passed" in types_passed

    with _client() as c:
        _seed("ap-1", state="pending_review")
        c.post(f"{P22}/dry-run", json=_dry_run_payload("ap-1"), headers=AUTH_HEADERS)
        types_blocked = _audit_event_types()
    assert "execution_dry_run_blocked" in types_blocked


def test_audit_events_redacted_and_carry_no_raw_key():
    secret = "audit-raw-key-XYZ"  # pragma: allowlist secret
    with _client() as c:
        _seed("ap-1")
        payload = _dry_run_payload("ap-1")
        payload["idempotency_key"] = secret
        payload["reason"] = "token=abc123 secret-value"  # pragma: allowlist secret
        c.post(f"{P22}/dry-run", json=payload, headers=AUTH_HEADERS)
    for e in _audit_log_raw():
        assert e.redaction_applied is True
        dump = json.dumps(e.model_dump(), default=str)
        assert secret not in dump
        assert "abc123" not in dump
        assert "secret-value" not in dump


# ============================================================================
# No-execution invariants (source + behavior)
# ============================================================================


def _p22_source_files():
    import api.v1.platform.p22 as pkg
    import os

    base = os.path.dirname(pkg.__file__)
    for name in ("__init__.py", "schemas.py", "services.py", "routes.py"):
        path = os.path.join(base, name)
        with open(path, "r", encoding="utf-8") as fh:
            yield path, fh.read()


def _ast_dotted(node):
    """Reconstruct a dotted attribute path (e.g. os.system -> 'os'). Best-effort."""
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def test_no_subprocess_shell_or_harness_call_tokens_in_p22_source():
    """No code-execution call / harness token appears in any p22 AST.

    Scanned via ``ast`` (imports + call expressions), so docstring / comment
    mentions of 'harness' / 'shell' in negation statements do not match. Matches
    EXACT bare-call names (eval / exec / system / popen) and qualified calls
    (subprocess.*, os.system / os.popen), shell=True kwargs, and any call whose
    attribute name references the harness / action-execution surface.
    """
    forbidden_bare = {"eval", "exec", "system", "popen", "run"}
    forbidden_os_attrs = {"system", "popen", "execv", "execve"}
    forbidden_attr_substrings = (
        "harness", "execute_action", "run_action", "dispatch_action",
        "drain_queue", "start_worker", "invoke_harness",
    )
    for path, src in _p22_source_files():
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    assert f.id not in forbidden_bare, (
                        f"forbidden bare call {f.id!r} in {os.path.basename(path)}"
                    )
                elif isinstance(f, ast.Attribute):
                    dotted = _ast_dotted(f.value)
                    if dotted.startswith("subprocess"):
                        raise AssertionError(f"forbidden subprocess call in {path}")
                    if dotted == "os" and f.attr in forbidden_os_attrs:
                        raise AssertionError(f"forbidden os.{f.attr} call in {path}")
                    low = f.attr.lower()
                    assert not any(s in low for s in forbidden_attr_substrings), (
                        f"forbidden execution attr {f.attr!r} in {os.path.basename(path)}"
                    )
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) \
                            and kw.value.value is True:
                        raise AssertionError(f"shell=True forbidden in {path}")


def test_no_tenant_payment_or_product_imports_in_p22_source():
    forbidden_import_substrings = (
        "subprocess", "p16", "product", "order", "payment", "invoice",
        "customer", "inventory", "ledger", "billing",
    )
    for _path, src in _p22_source_files():
        tree = ast.parse(src)
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                mods.append(node.module or "")
            for m in mods:
                low = m.lower()
                assert not any(tok in low for tok in forbidden_import_substrings), (
                    f"forbidden import {m!r} in p22 source"
                )


def test_no_execute_function_and_non_execution_markers_false():
    from api.v1.platform.p22 import services
    from api.v1.platform.p22 import P22_EXECUTES

    forbidden_names = ("execute", "execute_action", "run_action", "dispatch",
                       "drain", "invoke", "invoke_harness", "start_worker", "run")
    public = [n for n in dir(services) if not n.startswith("_")]
    for name in forbidden_names:
        assert name not in public, f"forbidden execution function {name!r} exposed by p22.services"
    assert services.EXECUTION_ALLOWED is False
    assert services.EXECUTED is False
    assert services.EXECUTION_STARTED is False
    assert P22_EXECUTES is False
    assert services.REALIZED_RESULT_STATES == frozenset({"dry_run_passed", "blocked"})


def test_no_executing_result_state_ever_assigned():
    """Across a recorded request and a blocked request, result_state is never an
    executing / executed state."""
    with _client() as c:
        dry = _passed_dry_run(c)
        recorded = c.post(f"{P22}/requests",
                          json=_request_payload("ap-1", "support_mode.on", dry["dry_run_id"]),
                          headers=AUTH_HEADERS).json()
        _seed("ap-1", state="pending_review")
        blocked = c.post(f"{P22}/requests",
                         json=_request_payload("ap-1", "support_mode.on", dry["dry_run_id"],
                                               idempotency_key="k-bl"),
                         headers=AUTH_HEADERS).json()
    assert recorded["result_state"] not in EXECUTING_STATES
    assert blocked["result_state"] not in EXECUTING_STATES


def test_default_resolver_returns_none_without_db_session():
    """The default resolver performs NO durable read when there is no db session.

    A None db short-circuits to None before touching the durable runtime. This
    is the fail-closed contract: P22 never invents an approval without the
    durable read path available.
    """
    from api.v1.platform.p22 import services as p22

    import asyncio

    async def _go():
        return await p22._default_resolve_approval("ap-1", db=None)

    assert asyncio.run(_go()) is None


def test_default_resolver_returns_none_without_approval_id():
    """An empty / None approval_id short-circuits to None (no durable read)."""
    from api.v1.platform.p22 import services as p22

    import asyncio

    async def _go():
        return await p22._default_resolve_approval(None, db=_mock_db())

    assert asyncio.run(_go()) is None


def test_default_resolver_fails_closed_when_storage_not_ready_no_memory_fallback():
    """The default resolver fails CLOSED when durable storage is not ready.

    This is the P25-EB core proof: even when the OLD P20 in-memory store holds
    the approval, the default resolver returns None (blocked) as long as the
    durable runtime readiness check fails. There is NO fallback to the in-memory
    store -- the durable read path is the only resolution route.
    """
    from api.v1.platform.p22 import services as p22

    # Seed the OLD P20 in-memory store so a fallback WOULD resolve it if one
    # existed. The assertion below proves no such fallback exists.
    from api.v1.platform.p18 import services as p18
    from api.v1.platform.p20 import services as p20

    p20.reset_store()
    p18.reset_store()
    p20.set_storage_mode("memory")
    try:
        import asyncio

        async def _seed_memory():
            with patch(
                "api.v1.platform.p18.services._resolve_action_source_status",
                AsyncMock(return_value="available"),
            ):
                rec = await p20.create_durable_approval(
                    action_id=None, tenant_id=None, action_type="support_mode.on",
                    maker="maker-1", reason="ok", idempotency_key="open-1",
                    expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
                    durable_retain_until=None, confirm=True, correlation_id=None,
                    metadata=None, db=None, actor="maker-1", actor_role="super_admin",
                    identity_context="identity_only",
                )
                await p20.submit_decision(
                    rec.approval_id, decision="approve", approver_id="chk-1", reason="ok",
                    idempotency_key="dec-1", confirm=True, correlation_id=None, metadata=None,
                    actor="chk-1", actor_role="super_admin", identity_context="identity_only",
                    db=None,
                )
                await p20.submit_decision(
                    rec.approval_id, decision="approve", approver_id="chk-2", reason="ok",
                    idempotency_key="dec-2", confirm=True, correlation_id=None, metadata=None,
                    actor="chk-2", actor_role="super_admin", identity_context="identity_only",
                    db=None,
                )
                return rec.approval_id

        approval_id = asyncio.run(_seed_memory())

        # Durable readiness returns NOT ready -> resolver must return None even
        # though the in-memory store holds the approval (NO memory fallback).
        db = _mock_db()
        with patch(
            "api.v1.platform.p20.services._check_durable_readiness",
            AsyncMock(return_value=(False, "storage_not_ready")),
        ):
            with patch(
                "api.v1.platform.p20.services.read_durable_approval",
                AsyncMock(return_value=None),
            ) as _read_mock:

                async def _go():
                    return await p22._default_resolve_approval(approval_id, db=db)

                snap = asyncio.run(_go())
            # read_durable_approval was NEVER called (readiness gate stopped it).
            assert _read_mock.await_count == 0
        assert snap is None  # blocked -- no memory fallback
    finally:
        p20.set_storage_mode(None)
        p20.reset_store()
        p18.reset_store()


def test_default_resolver_reads_durable_path_when_ready():
    """When durable storage IS ready, the resolver reads via read_durable_approval
    and maps the P20 record into an ApprovalSnapshot (state / quorum / source /
    action fields). This proves the durable read path is the resolution route."""
    from api.v1.platform.p22 import services as p22

    db = _mock_db()
    fake_rec = MagicMock()
    fake_rec.approval_id = "ap-durable-1"
    fake_rec.state = "approved_execution_blocked"
    fake_rec.quorum_required = 2
    fake_rec.quorum_met = True
    fake_rec.maker = "maker-1"
    fake_rec.checkers = [MagicMock(checker_id="chk-1"), MagicMock(checker_id="chk-2")]
    fake_rec.source_status = "available"  # P20 vocabulary -> P22 'known'
    fake_rec.action_type = "support_mode.on"
    fake_rec.action_class = "write"
    fake_rec.tenant_id = None
    fake_rec.validation_status = "valid"
    fake_rec.expires_at = FUTURE

    import asyncio

    with patch(
        "api.v1.platform.p20.services._check_durable_readiness",
        AsyncMock(return_value=(True, "ready")),
    ):
        with patch(
            "api.v1.platform.p20.services.read_durable_approval",
            AsyncMock(return_value=fake_rec),
        ):

            async def _go():
                return await p22._default_resolve_approval("ap-durable-1", db=db)

            snap = asyncio.run(_go())
    assert snap is not None
    assert snap.approval_id == "ap-durable-1"
    assert snap.state == "approved_execution_blocked"
    assert snap.quorum_met is True
    assert snap.quorum_required == 2
    assert snap.maker == "maker-1"
    assert snap.checker_ids == ["chk-1", "chk-2"]
    assert snap.source_status == "known"  # 'available' -> 'known'
    assert snap.action_type == "support_mode.on"


def test_default_resolver_returns_none_when_durable_read_missing():
    """Durable storage ready but read returns None (approval absent) -> None."""
    from api.v1.platform.p22 import services as p22

    db = _mock_db()
    import asyncio

    with patch(
        "api.v1.platform.p20.services._check_durable_readiness",
        AsyncMock(return_value=(True, "ready")),
    ):
        with patch(
            "api.v1.platform.p20.services.read_durable_approval",
            AsyncMock(return_value=None),
        ):

            async def _go():
                return await p22._default_resolve_approval("ghost", db=db)

            assert asyncio.run(_go()) is None


def test_default_resolver_returns_none_when_durable_read_raises():
    """Durable storage ready but read raises -> fail closed (None), never propagates."""
    from api.v1.platform.p22 import services as p22

    db = _mock_db()
    import asyncio

    with patch(
        "api.v1.platform.p20.services._check_durable_readiness",
        AsyncMock(return_value=(True, "ready")),
    ):
        with patch(
            "api.v1.platform.p20.services.read_durable_approval",
            AsyncMock(side_effect=RuntimeError("transient db error")),
        ):

            async def _go():
                return await p22._default_resolve_approval("ap-1", db=db)

            assert asyncio.run(_go()) is None


# ============================================================================
# P22-B-R1: precondition target binding + required confirmation fields
# ============================================================================


def test_dry_run_target_mismatch_tenant_blocked():
    # Approval is scoped to tenant-A; the dry-run targets tenant-B -> blocked.
    # Reproduces CTO finding #1 (target binding was missing).
    with _client() as c:
        _seed("ap-1", tenant_id="tenant-A")
        payload = _dry_run_payload("ap-1")
        payload["tenant_id"] = "tenant-B"
        body = c.post(f"{P22}/dry-run", json=payload, headers=AUTH_HEADERS).json()
    assert body["executable"] is False
    assert body["verdict"] == "blocked"
    assert "target_mismatch_approval" in body["block_reasons"]
    assert body["executed"] is False
    assert body["execution_allowed"] is False
    assert body["execution_started"] is False


def test_dry_run_matching_tenant_passes():
    # Same tenant on approval and request -> no target_mismatch (regression guard).
    with _client() as c:
        _seed("ap-1", tenant_id="tenant-A")
        payload = _dry_run_payload("ap-1")
        payload["tenant_id"] = "tenant-A"
        body = c.post(f"{P22}/dry-run", json=payload, headers=AUTH_HEADERS).json()
    assert body["executable"] is True
    assert "target_mismatch_approval" not in body["block_reasons"]


def test_dry_run_missing_reason_blocked():
    with _client() as c:
        _seed("ap-1")
        payload = _dry_run_payload("ap-1")
        payload["reason"] = ""
        body = c.post(f"{P22}/dry-run", json=payload, headers=AUTH_HEADERS).json()
    assert body["executable"] is False
    assert "reason_required" in body["block_reasons"]


def test_dry_run_invalid_execution_mode_blocked():
    with _client() as c:
        _seed("ap-1")
        payload = _dry_run_payload("ap-1")
        payload["execution_mode"] = "realtime"  # invalid
        body = c.post(f"{P22}/dry-run", json=payload, headers=AUTH_HEADERS).json()
    assert body["executable"] is False
    assert "execution_mode_required" in body["block_reasons"]


def test_dry_run_missing_execution_mode_blocked():
    with _client() as c:
        _seed("ap-1")
        payload = _dry_run_payload("ap-1")
        payload["execution_mode"] = None  # missing
        r = c.post(f"{P22}/dry-run", json=payload, headers=AUTH_HEADERS)
    assert r.status_code == 200  # shaped blocked response, not a 422/500
    assert "execution_mode_required" in r.json()["block_reasons"]


def test_request_missing_reason_blocked():
    with _client() as c:
        dry = _passed_dry_run(c)
        payload = _request_payload("ap-1", "support_mode.on", dry["dry_run_id"])
        payload["reason"] = ""
        body = c.post(f"{P22}/requests", json=payload, headers=AUTH_HEADERS).json()
    assert body["result_state"] == "blocked"
    assert "reason_required" in body["block_reasons"]
    assert body["execution_request_id"] is None  # not recorded


def test_request_invalid_execution_mode_blocked():
    with _client() as c:
        dry = _passed_dry_run(c)
        payload = _request_payload("ap-1", "support_mode.on", dry["dry_run_id"])
        payload["execution_mode"] = "async"  # invalid
        body = c.post(f"{P22}/requests", json=payload, headers=AUTH_HEADERS).json()
    assert body["result_state"] == "blocked"
    assert "execution_mode_required" in body["block_reasons"]
    assert body["execution_request_id"] is None


def test_blocked_responses_non_executing_and_audit_redacted():
    # CTO R1 bullet 6: a blocked request stays non-executing and the denial audit
    # is redacted (no raw reason leaks via the denial path).
    with _client() as c:
        dry = _passed_dry_run(c)
        # Sensitive reason (redacts to [redacted], still non-empty) but missing
        # execution_ack -> blocked; the denial audit must not carry the raw value.
        payload = _request_payload("ap-1", "support_mode.on", dry["dry_run_id"],
                                   reason="token=abc123 deny",  # pragma: allowlist secret
                                   execution_ack=False)
        body = c.post(f"{P22}/requests", json=payload, headers=AUTH_HEADERS).json()
        audit_dump = json.dumps([e.model_dump() for e in _audit_log_raw()], default=str)
    assert body["result_state"] == "blocked"
    assert body["executed"] is False
    assert body["execution_allowed"] is False
    assert body["execution_started"] is False
    assert "abc123" not in audit_dump
    assert "execution_ack_required" in body["block_reasons"]


# ============================================================================
# Helpers for audit inspection
# ============================================================================


def _audit_log_raw():
    """Return the live in-memory execution audit log (must be called within a
    client scope / before fixture teardown)."""
    from api.v1.platform.p22 import services

    return services.audit_log()


def _audit_event_types():
    return [e.event_type for e in _audit_log_raw()]
