"""
P20 Durable Approval Governance API tests (P20-B backend skeleton).

Contract-backed, NON-EXECUTING durable approval read / write skeleton with
maker-checker dual-control and quorum. Covers:
  - create durable approval -> pending_review (executed / execution_allowed
    False; execution_gate blocked; action_class + quorum_required set)
  - list (status / action_type / tenant_id filters) + read by approval_id
  - maker-checker separation (maker cannot approve / reject own request)
  - quorum: single approve on a write stays pending_review (quorum_pending);
    a second distinct approver meets quorum -> approved_execution_blocked;
    read action quorum floor is one
  - reject is final / terminal; a rejected approval cannot be approved after
  - distinct checkers: duplicate same-decision idempotent; a flip is a conflict
  - approve never executes; execution_allowed / executed False on every response
  - tenant-contextual super_admin / tenant admin / support_operator /
    engineering_operator denied at the boundary; every P20 endpoint guarded
  - raw secret in reason / metadata redacted; idempotency + correlation never
    echoed raw; the create idempotency_key is stored ONLY as a SHA-256 digest
  - unknown / not-found P18 source handling; available is never fabricated
  - audit payloads carry the P20-A required fields and never raw sensitive values
  - no migration / persistent storage; route registration present; no
    PUT/PATCH/DELETE (no mutation verbs); services source touches no tenant /
    order / payment symbols

Aligned to docs/ai/PLATFORM_PRODUCT_P20_DURABLE_APPROVAL_GOVERNANCE_CONTRACT.md
(P20-A).
"""
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")
os.environ.setdefault("PLATFORM_OPERATOR_SECRET", "test-operator-secret")


# -- Helpers (mirror the P15/P17/P18/P19 test harness) --

AUTH_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}
OPERATOR_HEADERS = {"X-Platform-Operator": "test-operator-secret"}

P20_BASE = "/api/v1/platform/p20"
DURABLE = f"{P20_BASE}/durable-approvals"


def decision_path(approval_id: str) -> str:
    return f"{DURABLE}/{approval_id}/decisions"


def read_path(approval_id: str) -> str:
    return f"{DURABLE}/{approval_id}"


TENANT_ID = "b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d"
OTHER_TENANT_ID = "c3d4e5f6-a7b8-49c0-9d1e-2f3a4b5c6d7e"
FUTURE_EXPIRES = "2099-01-01T00:00:00+00:00"

_ACTIVE_PATCHERS: list = []


def _start_patch(target, new):
    p = patch(target, new=new)
    p.start()
    _ACTIVE_PATCHERS.append(p)
    return p


@pytest.fixture(autouse=True)
def _stop_patches_after_test():
    yield
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


def _make_app(mock_db=None, *, source_status=None):
    """Build an app with the P20 router; reset the store; optionally fix P18 source status."""
    from api.v1.platform.p20 import services
    from api.v1.platform.p20.routes import router
    from api.dependencies import get_db

    services.reset_store()
    app = FastAPI()

    async def override():
        yield mock_db or _mock_db()

    app.dependency_overrides[get_db] = override
    app.include_router(router)

    if source_status is not None:
        _start_patch(
            "api.v1.platform.p18.services._resolve_action_source_status",
            AsyncMock(return_value=source_status),
        )
    return app


def _approval_payload(**overrides):
    base = {
        "action_type": "tenant.pause",
        "tenant_id": TENANT_ID,
        "maker": "maker-a",
        "reason": "routine durable ops approval",
        "idempotency_key": "durable-idem-1",
        "confirm": True,
        "expires_at": FUTURE_EXPIRES,
    }
    base.update(overrides)
    return base


def _decision_payload(**overrides):
    base = {
        "decision": "approve",
        "approver_id": "checker-1",
        "reason": "approved after durable review",
        "idempotency_key": "dec-idem-1",
        "confirm": True,
    }
    base.update(overrides)
    return base


def _identity_super_admin_token():
    t = MagicMock()
    t.user_id = "identity-super-admin"
    t.roles = ["super_admin"]
    t.tenant_id = None
    t.tenant_schema = None
    t.is_identity_only = True
    t.is_super_admin = True
    return t


def _tenant_contextual_super_admin_token():
    t = MagicMock()
    t.user_id = "contextual-super-admin"
    t.roles = ["super_admin"]
    t.tenant_id = OTHER_TENANT_ID
    t.tenant_schema = "t_other"
    t.is_identity_only = False
    t.is_super_admin = True
    return t


def _tenant_admin_token():
    t = MagicMock()
    t.user_id = "tenant-admin-user"
    t.roles = ["tenant_admin"]
    t.tenant_id = OTHER_TENANT_ID
    t.tenant_schema = "t_other"
    t.is_identity_only = False
    t.is_super_admin = False
    return t


def _support_operator_token():
    t = MagicMock()
    t.user_id = "support-op"
    t.roles = ["support_operator"]
    t.tenant_id = None
    t.tenant_schema = None
    t.is_identity_only = True
    t.is_super_admin = False
    return t


def _engineering_operator_token():
    t = MagicMock()
    t.user_id = "eng-op"
    t.roles = ["engineering_operator"]
    t.tenant_id = None
    t.tenant_schema = None
    t.is_identity_only = True
    t.is_super_admin = False
    return t


def _create_approval(client, **overrides):
    """Create a durable approval and return (approval_id, body)."""
    body = client.post(DURABLE, headers=AUTH_HEADERS, json=_approval_payload(**overrides)).json()
    return body.get("approval_id"), body


def _decide(client, approval_id, **overrides):
    return client.post(decision_path(approval_id), headers=AUTH_HEADERS, json=_decision_payload(**overrides)).json()


# ============================================================
# 1. Create durable approval
# ============================================================


class TestCreate:
    def test_create_records_at_pending_review(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(DURABLE, headers=AUTH_HEADERS, json=_approval_payload())
        assert r.status_code == 200
        body = r.json()
        assert body["result"] == "recorded"
        assert body["state"] == "pending_review"
        assert body["approval_id"] is not None
        assert body["execution_allowed"] is False
        assert body["executed"] is False
        assert body["execution_gate"] == "blocked"
        assert body["redaction_applied"] is True
        assert body["storage"] == "memory"
        assert body["action_type"] == "tenant.pause"
        assert body["maker"] == "maker-a"

    def test_create_sets_action_class_and_quorum_for_write(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(DURABLE, headers=AUTH_HEADERS, json=_approval_payload()).json()
        assert body["action_class"] == "write"
        assert body["quorum_required"] == 2
        assert body["quorum_met"] is False

    def test_create_read_action_quorum_one(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            DURABLE,
            headers=AUTH_HEADERS,
            json=_approval_payload(action_type="provisioning.recheck", idempotency_key="read-1"),
        ).json()
        assert body["action_class"] == "read"
        assert body["quorum_required"] == 1

    def test_create_write_request_action_quorum_two(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            DURABLE,
            headers=AUTH_HEADERS,
            json=_approval_payload(
                action_type="backup.restore_test_request", idempotency_key="wr-1"
            ),
        ).json()
        assert body["action_class"] == "write_request"
        assert body["quorum_required"] == 2

    def test_create_missing_reason_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(DURABLE, headers=AUTH_HEADERS, json=_approval_payload(reason="")).json()
        assert body["result"] == "denied"
        assert body["approval_id"] is None

    def test_create_missing_idempotency_key_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            DURABLE, headers=AUTH_HEADERS, json=_approval_payload(idempotency_key="")
        ).json()
        assert body["result"] == "denied"

    def test_create_missing_maker_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(DURABLE, headers=AUTH_HEADERS, json=_approval_payload(maker="")).json()
        assert body["result"] == "denied"

    def test_create_without_confirmation_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(DURABLE, headers=AUTH_HEADERS, json=_approval_payload(confirm=False)).json()
        assert body["result"] == "denied"

    def test_create_past_expires_at_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            DURABLE,
            headers=AUTH_HEADERS,
            json=_approval_payload(expires_at="2000-01-01T00:00:00+00:00"),
        ).json()
        assert body["result"] == "denied"

    def test_create_unknown_action_type_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            DURABLE,
            headers=AUTH_HEADERS,
            json=_approval_payload(action_type="not.a.real.action", action_id=None),
        ).json()
        assert body["result"] in ("denied", "not_found")

    def test_create_carries_request_digest(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(DURABLE, headers=AUTH_HEADERS, json=_approval_payload()).json()
        assert body["request_digest"] is not None
        assert len(body["request_digest"]) == 64
        assert all(c in "0123456789abcdef" for c in body["request_digest"])


# ============================================================
# 2. Read + list (with filters)
# ============================================================


class TestReadAndList:
    def test_read_by_approval_id(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        approval_id, _ = _create_approval(client)
        r = client.get(read_path(approval_id), headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert r.json()["approval_id"] == approval_id

    def test_read_unknown_returns_404(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.get(read_path("does-not-exist"), headers=AUTH_HEADERS)
        assert r.status_code == 404

    def test_list_returns_records(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        _create_approval(client, idempotency_key="a")
        _create_approval(client, idempotency_key="b")
        r = client.get(DURABLE, headers=AUTH_HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 2
        assert body["storage"] == "memory"
        assert body["executed"] is False
        for item in body["items"]:
            assert item["execution_allowed"] is False

    def test_list_filter_by_status(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client, idempotency_key="a")
        # move 'a' to rejected via a checker reject
        _decide(client, aid, decision="reject", approver_id="checker-x", idempotency_key="rx")
        _create_approval(client, idempotency_key="b")  # stays pending_review
        pending = client.get(DURABLE, headers=AUTH_HEADERS, params={"status": "pending_review"}).json()
        rejected = client.get(DURABLE, headers=AUTH_HEADERS, params={"status": "rejected"}).json()
        assert pending["total"] == 1 and pending["items"][0]["state"] == "pending_review"
        assert rejected["total"] == 1 and rejected["items"][0]["state"] == "rejected"

    def test_list_filter_by_action_type(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        _create_approval(client, idempotency_key="a", action_type="tenant.pause")
        _create_approval(client, idempotency_key="b", action_type="provisioning.recheck")
        body = client.get(
            DURABLE, headers=AUTH_HEADERS, params={"action_type": "tenant.pause"}
        ).json()
        assert body["total"] == 1
        assert body["items"][0]["action_type"] == "tenant.pause"

    def test_list_filter_by_tenant_id(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        _create_approval(client, idempotency_key="a", tenant_id=TENANT_ID)
        _create_approval(client, idempotency_key="b", tenant_id=OTHER_TENANT_ID)
        body = client.get(
            DURABLE, headers=AUTH_HEADERS, params={"tenant_id": TENANT_ID}
        ).json()
        assert body["total"] == 1
        assert body["items"][0]["tenant_id"] == TENANT_ID


# ============================================================
# 3. Dual-control: maker-checker + quorum
# ============================================================


class TestDualControl:
    def test_single_approve_on_write_stays_pending(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client)
        body = _decide(client, aid, approver_id="checker-1", idempotency_key="d1")
        assert body["result"] == "quorum_pending"
        assert body["state"] == "pending_review"
        assert body["quorum_met"] is False
        assert body["execution_allowed"] is False
        assert len(body["checkers"]) == 1

    def test_second_distinct_approver_meets_quorum(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client)
        first = _decide(client, aid, approver_id="checker-1", idempotency_key="d1")
        assert first["result"] == "quorum_pending"
        second = _decide(client, aid, approver_id="checker-2", idempotency_key="d2")
        assert second["result"] == "approved"
        assert second["state"] == "approved_execution_blocked"
        assert second["quorum_met"] is True
        assert second["decision"] == "approve"
        assert second["execution_allowed"] is False
        assert len(second["checkers"]) == 2

    def test_maker_cannot_approve_own_request(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client)  # maker = maker-a
        body = _decide(client, aid, approver_id="maker-a", idempotency_key="self")
        assert body["result"] == "denied"
        assert body["state"] == "pending_review"
        assert body["execution_allowed"] is False
        assert len(body["checkers"]) == 0

    def test_maker_cannot_reject_own_request(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client)
        body = _decide(client, aid, decision="reject", approver_id="maker-a", idempotency_key="self-r")
        assert body["result"] == "denied"
        assert body["state"] == "pending_review"

    def test_reject_by_checker_is_terminal(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client)
        body = _decide(client, aid, decision="reject", approver_id="checker-1", idempotency_key="r1")
        assert body["result"] == "rejected"
        assert body["state"] == "rejected"
        assert body["decision"] == "reject"
        assert body["execution_allowed"] is False

    def test_rejected_cannot_be_approved_after(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client)
        _decide(client, aid, decision="reject", approver_id="checker-1", idempotency_key="r1")
        body = _decide(client, aid, decision="approve", approver_id="checker-2", idempotency_key="a-after")
        assert body["result"] == "conflict"
        assert body["state"] == "rejected"

    def test_same_checker_duplicate_approve_idempotent(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client)
        _decide(client, aid, approver_id="checker-1", idempotency_key="d1")
        body = _decide(client, aid, approver_id="checker-1", idempotency_key="d1b")
        assert body["result"] == "duplicate"
        assert body["state"] == "pending_review"
        assert len(body["checkers"]) == 1

    def test_same_checker_flip_decision_conflict(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client)
        _decide(client, aid, decision="approve", approver_id="checker-1", idempotency_key="d1")
        body = _decide(client, aid, decision="reject", approver_id="checker-1", idempotency_key="d1f")
        assert body["result"] == "conflict"
        assert body["state"] == "pending_review"

    def test_read_action_single_approver_meets_quorum(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client, action_type="provisioning.recheck", idempotency_key="rd-1")
        body = _decide(client, aid, approver_id="checker-1", idempotency_key="d1")
        assert body["result"] == "approved"
        assert body["state"] == "approved_execution_blocked"
        assert body["quorum_met"] is True

    def test_write_request_quorum_two_restore_test(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(
            client, action_type="backup.restore_test_request", idempotency_key="rt-1"
        )
        first = _decide(client, aid, approver_id="checker-1", idempotency_key="d1")
        assert first["result"] == "quorum_pending"
        second = _decide(client, aid, approver_id="checker-2", idempotency_key="d2")
        assert second["result"] == "approved"
        assert second["state"] == "approved_execution_blocked"
        # restore_test_request stays request-only (no execution, not "executed")
        assert second["executed"] is False
        assert second["execution_allowed"] is False

    def test_distinct_checkers_recorded_in_checkers_list(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client)
        _decide(client, aid, approver_id="checker-1", idempotency_key="d1")
        body = _decide(client, aid, approver_id="checker-2", idempotency_key="d2")
        ids = {c["checker_id"] for c in body["checkers"]}
        assert ids == {"checker-1", "checker-2"}
        # maker never appears among checkers
        assert "maker-a" not in ids

    def test_quorum_met_reject_after_is_conflict(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client)
        _decide(client, aid, approver_id="checker-1", idempotency_key="d1")
        _decide(client, aid, approver_id="checker-2", idempotency_key="d2")  # quorum met
        body = _decide(client, aid, decision="reject", approver_id="checker-3", idempotency_key="d3")
        assert body["result"] == "conflict"
        assert body["state"] == "approved_execution_blocked"


# ============================================================
# 4. Safety invariants
# ============================================================


class TestSafetyInvariants:
    def test_approved_does_not_execute(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client)
        _decide(client, aid, approver_id="checker-1", idempotency_key="d1")
        body = _decide(client, aid, approver_id="checker-2", idempotency_key="d2")
        assert body["state"] == "approved_execution_blocked"
        assert body["executed"] is False
        assert body["execution_allowed"] is False

    def test_execution_allowed_false_on_every_response(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, create_body = _create_approval(client)
        _decide(client, aid, approver_id="checker-1", idempotency_key="d1")
        approve_body = _decide(client, aid, approver_id="checker-2", idempotency_key="d2")
        read_body = client.get(read_path(aid), headers=AUTH_HEADERS).json()
        list_body = client.get(DURABLE, headers=AUTH_HEADERS).json()
        for b in (create_body, approve_body, read_body):
            assert b["execution_allowed"] is False
            assert b["executed"] is False
            assert b["execution_gate"] == "blocked"
        for item in list_body["items"]:
            assert item["execution_allowed"] is False
            assert item["executed"] is False


# ============================================================
# 5. Permissions (guard reuse)
# ============================================================


class TestPermissions:
    def test_unauthenticated_create_denied_401(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(DURABLE, json=_approval_payload())
        assert r.status_code == 401

    def test_unauthenticated_decision_denied_401(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(decision_path("any"), json=_decision_payload())
        assert r.status_code == 401

    def test_all_p20_endpoints_guarded(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        assert client.post(DURABLE, json=_approval_payload()).status_code == 401
        assert client.get(DURABLE).status_code == 401
        assert client.get(read_path("x")).status_code == 401
        assert client.post(decision_path("x"), json=_decision_payload()).status_code == 401

    def test_tenant_contextual_super_admin_denied_create(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        auth_ctx = MagicMock()
        auth_ctx.token = _tenant_contextual_super_admin_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.post(DURABLE, json=_approval_payload())
        assert r.status_code in (401, 403)

    def test_tenant_contextual_super_admin_denied_decision(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client)
        auth_ctx = MagicMock()
        auth_ctx.token = _tenant_contextual_super_admin_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.post(decision_path(aid), json=_decision_payload())
        assert r.status_code in (401, 403)

    def test_tenant_admin_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        auth_ctx = MagicMock()
        auth_ctx.token = _tenant_admin_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.post(DURABLE, json=_approval_payload())
        assert r.status_code in (401, 403)

    def test_support_operator_denied_create(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        auth_ctx = MagicMock()
        auth_ctx.token = _support_operator_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.post(DURABLE, json=_approval_payload())
        assert r.status_code in (401, 403)

    def test_engineering_operator_denied_decision(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client)
        auth_ctx = MagicMock()
        auth_ctx.token = _engineering_operator_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.post(decision_path(aid), json=_decision_payload())
        assert r.status_code in (401, 403)

    def test_identity_only_super_admin_allowed(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        auth_ctx = MagicMock()
        auth_ctx.token = _identity_super_admin_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.post(DURABLE, json=_approval_payload())
        assert r.status_code == 200


# ============================================================
# 6. Idempotency digest-only (raw key never stored / echoed)
# ============================================================


class TestIdempotencyDigest:
    def test_raw_create_key_not_in_store_only_digest(self):
        import hashlib

        from api.v1.platform.p20 import services

        app = _make_app(source_status="available")
        client = TestClient(app)
        raw = "my-raw-create-key"
        aid, body = _create_approval(client, idempotency_key=raw)
        assert body["result"] == "recorded"
        assert raw not in services._STORE_BY_CREATE_KEY
        rec = services._STORE[aid]
        assert rec.create_key == hashlib.sha256(raw.encode("utf-8")).hexdigest()
        assert rec.idempotency_key_digest == hashlib.sha256(raw.encode("utf-8")).hexdigest()
        assert all(c in "0123456789abcdef" for c in rec.create_key)

    def test_response_echoes_digest_not_raw_key(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        raw = "super-raw-secret-create-key"  # pragma: allowlist secret
        body = client.post(
            DURABLE, headers=AUTH_HEADERS, json=_approval_payload(idempotency_key=raw)
        ).json()
        assert body["idempotency_key_digest"] is not None
        assert len(body["idempotency_key_digest"]) == 64
        # the raw key is never present anywhere in the response
        assert raw not in str(body)

    def test_create_duplicate_same_payload_idempotent(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        first = client.post(
            DURABLE, headers=AUTH_HEADERS, json=_approval_payload(idempotency_key="dup-k")
        ).json()
        second = client.post(
            DURABLE, headers=AUTH_HEADERS, json=_approval_payload(idempotency_key="dup-k")
        ).json()
        assert first["result"] == "recorded"
        assert second["result"] == "duplicate"
        assert second["approval_id"] == first["approval_id"]

    def test_create_conflict_different_payload_fails(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        first = client.post(
            DURABLE,
            headers=AUTH_HEADERS,
            json=_approval_payload(idempotency_key="conf-k", reason="reason A"),
        ).json()
        second = client.post(
            DURABLE,
            headers=AUTH_HEADERS,
            json=_approval_payload(idempotency_key="conf-k", reason="reason B"),
        ).json()
        assert first["result"] == "recorded"
        assert second["result"] == "conflict"


# ============================================================
# 7. Redaction (value leakage)
# ============================================================


class TestRedaction:
    def test_raw_secret_in_reason_redacted(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            DURABLE,
            headers=AUTH_HEADERS,
            json=_approval_payload(
                reason="db password=hunter2 please approve",  # pragma: allowlist secret
                idempotency_key="appr-secret-reason",
            ),
        ).json()
        assert body["reason"] == "[redacted]"
        assert "hunter2" not in str(body)

    def test_raw_secret_in_metadata_not_leaked(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            DURABLE,
            headers=AUTH_HEADERS,
            json=_approval_payload(
                idempotency_key="appr-secret-md",
                metadata={
                    "note": "ok to keep",
                    "password": "hunter2",  # pragma: allowlist secret
                    "dsn": "postgres://u:p@10.0.0.5:5432/db",  # pragma: allowlist secret
                    "nested": {"token": "abc"},  # pragma: allowlist secret
                },
            ),
        ).json()
        serialized = str(body)
        assert "hunter2" not in serialized
        assert "10.0.0.5" not in serialized
        assert "5432" not in serialized

    def test_decision_reason_redacted(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client, idempotency_key="c1")
        body = _decide(
            client,
            aid,
            approver_id="checker-1",
            idempotency_key="d1",
            reason="creds token=OH-NO-SECRET",  # pragma: allowlist secret
        )
        # checker reason is redacted in the checkers log
        for c in body["checkers"]:
            assert "OH-NO-SECRET" not in str(c)
            assert c["reason_redacted"] == "[redacted]"

    def test_idempotency_and_correlation_not_echoed_raw(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            DURABLE,
            headers=AUTH_HEADERS,
            json=_approval_payload(
                idempotency_key="token=super-secret-val",  # pragma: allowlist secret
                correlation_id="postgres://u:p@db.internal:6432/x",  # pragma: allowlist secret
            ),
        ).json()
        assert body["correlation_id"] == "[redacted]"
        serialized = str(body)
        assert "super-secret-val" not in serialized
        assert "db.internal" not in serialized
        assert "6432" not in serialized

    def test_audit_payload_never_carries_raw_secret(self):
        from api.v1.platform.p20 import services

        app = _make_app(source_status="available")
        client = TestClient(app)
        client.post(
            DURABLE,
            headers=AUTH_HEADERS,
            json=_approval_payload(
                reason="creds token=OH-NO-SECRET",  # pragma: allowlist secret
                idempotency_key="appr-audit-secret",
            ),
        )
        for event in services.audit_log():
            assert "OH-NO-SECRET" not in str(event.reason_redacted)
            assert event.redaction_applied is True

    def test_audit_helper_redacts_raw_reason_value(self):
        from api.v1.platform.p20.services import _build_audit_event

        for raw in ("password=hunter2", "token=abc123"):  # pragma: allowlist secret
            ev = _build_audit_event(
                event_type="approval_opened",
                actor_id="ops",
                actor_role="super_admin",
                identity_context="identity_only",
                tenant_id=TENANT_ID,
                action_id=None,
                approval_id="appr-1",
                decision=None,
                previous_status=None,
                next_status="pending_review",
                reason=raw,
            )
            assert ev.redaction_applied is True
            assert ev.reason_redacted == "[redacted]"
            assert raw not in ev.reason_redacted


# ============================================================
# 8. Audit contract (required fields + quorum event)
# ============================================================


class TestAuditContract:
    REQUIRED = (
        "event_id",
        "approval_id",
        "action_id",
        "actor_id",
        "actor_role",
        "identity_context",
        "decision",
        "previous_status",
        "next_status",
        "reason_redacted",
        "created_at",
        "request_digest",
        "redaction_applied",
    )

    def test_opened_event_carries_all_required_fields(self):
        from api.v1.platform.p20 import services

        app = _make_app(source_status="available")
        client = TestClient(app)
        _create_approval(client, idempotency_key="aud-1")
        opened = [e for e in services.audit_log() if e.event_type == "approval_opened"]
        assert opened, "expected an approval_opened event"
        ev = opened[0]
        for field in self.REQUIRED:
            assert hasattr(ev, field), f"audit event missing required field {field}"
        assert ev.next_status == "pending_review"
        assert ev.quorum_required == 2

    def test_quorum_met_event_emitted(self):
        from api.v1.platform.p20 import services

        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client, idempotency_key="aud-2")
        _decide(client, aid, approver_id="checker-1", idempotency_key="d1")
        _decide(client, aid, approver_id="checker-2", idempotency_key="d2")
        quorum = [e for e in services.audit_log() if e.event_type == "approval_quorum_met"]
        assert len(quorum) == 1
        assert quorum[0].next_status == "approved_execution_blocked"
        assert quorum[0].quorum_met is True

    def test_decision_recorded_and_rejected_events_emitted(self):
        from api.v1.platform.p20 import services

        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client, idempotency_key="aud-3")
        _decide(client, aid, decision="reject", approver_id="checker-1", idempotency_key="d1")
        types = [e.event_type for e in services.audit_log()]
        assert "approval_decision_recorded" in types
        assert "approval_rejected" in types

    def test_denial_emits_audit_event(self):
        from api.v1.platform.p20 import services

        app = _make_app(source_status="available")
        client = TestClient(app)
        aid, _ = _create_approval(client, idempotency_key="aud-4")
        _decide(client, aid, approver_id="maker-a", idempotency_key="self")  # self-approval denied
        denied = [e for e in services.audit_log() if e.event_type == "approval_denied"]
        assert len(denied) >= 1


# ============================================================
# 9. P18 validation boundary
# ============================================================


class TestP18Boundary:
    def test_unknown_source_cannot_approve(self):
        # No source_status patch -> P18 resolver returns "unknown" (default).
        app = _make_app()
        client = TestClient(app)
        aid, create_body = _create_approval(client, idempotency_key="unk-src")
        assert create_body["state"] == "pending_review"
        assert create_body["source_status"] == "unknown"
        assert create_body["validation_status"] == "source_unknown"
        body = _decide(client, aid, approver_id="checker-1", idempotency_key="d1")
        assert body["result"] == "denied"
        assert body["state"] == "pending_review"
        assert body["execution_allowed"] is False

    def test_action_id_not_found_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            DURABLE,
            headers=AUTH_HEADERS,
            json=_approval_payload(
                action_id="00000000-0000-0000-0000-000000000000",
                action_type=None,
                idempotency_key="missing-action",
            ),
        ).json()
        assert body["result"] in ("denied", "not_found")
        assert body["approval_id"] is None

    def test_action_id_found_uses_p18_source_status(self):
        from api.v1.platform.p18.schemas import ActionRequestResponse

        fake = ActionRequestResponse(
            action_type="tenant.pause",
            result="accepted",
            executed=False,
            dry_run=False,
            message="recorded",
            reason="ok",
            idempotency_key="p18-key",
            requested_state=None,
            previous_state=None,
            source_status="available",
            created_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
        )
        app = _make_app()
        client = TestClient(app)
        with patch("api.v1.platform.p18.services.get_stored_request", return_value=fake):
            body = client.post(
                DURABLE,
                headers=AUTH_HEADERS,
                json=_approval_payload(
                    action_id="p18-recorded-1",
                    action_type=None,
                    idempotency_key="by-action-id",
                ),
            ).json()
        assert body["result"] == "recorded"
        assert body["source_status"] == "available"
        assert body["action_type"] == "tenant.pause"
        assert body["validation_status"] == "valid"

    def test_available_is_never_fabricated(self):
        app = _make_app()
        client = TestClient(app)
        _, body = _create_approval(client, idempotency_key="no-fab")
        assert body["source_status"] == "unknown"


# ============================================================
# 10. No mutation / persistent storage + registration + scope
# ============================================================


class TestNoMutationAndRegistration:
    EXPECTED_PATHS = {
        f"{DURABLE}",
        f"{DURABLE}/{{approval_id}}",
        f"{DURABLE}/{{approval_id}}/decisions",
    }

    def test_p20_router_registers_expected_routes(self):
        from api.v1.platform.p20.routes import router

        paths = {route.path for route in router.routes}
        assert self.EXPECTED_PATHS <= paths
        root_methods: set = set()
        for r in router.routes:
            if r.path == DURABLE:
                root_methods |= set(r.methods)
        assert "POST" in root_methods
        assert "GET" in root_methods
        # No mutating-by-effect verbs beyond GET/POST (no PUT/PATCH/DELETE).
        for route in router.routes:
            for method in route.methods:
                assert method in {"GET", "POST"}

    def test_storage_is_in_memory_no_persistence(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        _create_approval(client, idempotency_key="p1")
        queue = client.get(DURABLE, headers=AUTH_HEADERS).json()
        assert queue["storage"] == "memory"
        for item in queue["items"]:
            assert item["storage"] == "memory"

    def test_no_p20_migration_or_alembic_files(self):
        import glob
        import os

        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p20_migrations = []
        for pattern in ("**/migrations/**", "**/alembic/**"):
            for path in glob.glob(os.path.join(backend_dir, pattern), recursive=True):
                if "p20" in os.path.basename(path).lower():
                    p20_migrations.append(path)
        assert p20_migrations == []

    def test_services_source_touches_no_tenant_business_symbols(self):
        """The P20 service layer must not import or reference tenant business
        code (orders / payments / invoices / inventory / ledgers) -- durable
        approvals record decisions only and never mutate tenant data."""
        import os

        services_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "api",
            "v1",
            "platform",
            "p20",
            "services.py",
        )
        with open(services_file, "r", encoding="utf-8") as fh:
            src = fh.read()
        forbidden = [
            "from api.v1.orders",
            "from api.v1.payments",
            "import orders",
            "import payments",
            "import inventory",
            "wholesaler",
            "tenant_order",
            "create_order",
            "update_invoice",
        ]
        for token in forbidden:
            assert token not in src, f"P20 services must not reference tenant business symbol: {token}"

    def test_approve_never_calls_p18_execute_or_sets_executed(self):
        """A quorum-met approve must not invoke any P18 execution path; the P18
        executed flag is never set. (Services never reference execute paths.)"""
        import os

        services_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "api",
            "v1",
            "platform",
            "p20",
            "services.py",
        )
        with open(services_file, "r", encoding="utf-8") as fh:
            src = fh.read()
        for token in ("execute_action", "run_action", "apply_action", "dispatch", "executed = True"):
            assert token not in src, f"P20 services must not reference execution path: {token}"
