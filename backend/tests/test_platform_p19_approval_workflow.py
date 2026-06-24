"""
P19 Controlled Action Approval Workflow API tests (P19-B backend skeleton).

Contract-backed, NON-EXECUTING approval read / write skeleton. Covers:
  - create approval request -> pending_review (executed / execution_allowed False)
  - list queue + read by approval_id
  - approve -> execution_blocked; reject -> rejected (reject is final)
  - approved does not execute; execution_allowed False on every response
  - tenant-contextual super_admin denied; tenant admin denied; unauthenticated 401;
    non-super_admin denied; every P19 endpoint guarded
  - expired approval cannot be approved
  - rejected approval cannot be re-approved (final)
  - duplicate same decision idempotent; conflicting decision fails
  - raw secret in reason / metadata redacted (value leakage, not just key)
  - idempotency / correlation values not echoed raw
  - unknown P18 source_status cannot approve; action_id not found denied;
    available is never fabricated
  - no migration / persistent storage; route registration present
  - audit payloads never carry raw sensitive values

Aligned to docs/ai/PLATFORM_PRODUCT_P19_APPROVAL_WORKFLOW_CONTRACT.md (P19-A).
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


# -- Helpers (mirror the P15/P17/P18 test harness) --

AUTH_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}
OPERATOR_HEADERS = {"X-Platform-Operator": "test-operator-secret"}

P19_BASE = "/api/v1/platform/p19"
APPROVALS = f"{P19_BASE}/approvals"


def decision_path(approval_id: str) -> str:
    return f"{APPROVALS}/{approval_id}/decision"


def read_path(approval_id: str) -> str:
    return f"{APPROVALS}/{approval_id}"


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
    """Build an app with the P19 router; reset the store; optionally fix P18 source status."""
    from api.v1.platform.p19 import services
    from api.v1.platform.p19.routes import router
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
        "requested_by": "ops-super-admin",
        "reason": "routine ops approval",
        "idempotency_key": "appr-idem-1",
        "confirm": True,
        "expires_at": FUTURE_EXPIRES,
    }
    base.update(overrides)
    return base


def _decision_payload(**overrides):
    base = {
        "decision": "approve",
        "reviewed_by": "reviewer-super-admin",
        "reason": "approved after review",
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


def _non_super_admin_token():
    t = MagicMock()
    t.user_id = "eng-operator"
    t.roles = ["engineering_operator"]
    t.tenant_id = None
    t.tenant_schema = None
    t.is_identity_only = True
    t.is_super_admin = False
    return t


def _create_approval(client, **overrides):
    """Create an approval and return (approval_id, body)."""
    body = client.post(APPROVALS, headers=AUTH_HEADERS, json=_approval_payload(**overrides)).json()
    return body.get("approval_id"), body


# ============================================================
# 1. Create approval request
# ============================================================


class TestCreateApproval:
    def test_create_records_at_pending_review(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(APPROVALS, headers=AUTH_HEADERS, json=_approval_payload())
        assert r.status_code == 200
        body = r.json()
        assert body["result"] == "recorded"
        assert body["state"] == "pending_review"
        assert body["approval_id"] is not None
        assert body["execution_allowed"] is False
        assert body["executed"] is False
        assert body["redaction_applied"] is True
        assert body["storage"] == "memory"
        assert body["action_type"] == "tenant.pause"

    def test_create_missing_reason_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(APPROVALS, headers=AUTH_HEADERS, json=_approval_payload(reason="")).json()
        assert body["result"] == "denied"
        assert body["approval_id"] is None

    def test_create_missing_idempotency_key_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            APPROVALS, headers=AUTH_HEADERS, json=_approval_payload(idempotency_key="")
        ).json()
        assert body["result"] == "denied"

    def test_create_without_confirmation_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(APPROVALS, headers=AUTH_HEADERS, json=_approval_payload(confirm=False)).json()
        assert body["result"] == "denied"

    def test_create_past_expires_at_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            APPROVALS,
            headers=AUTH_HEADERS,
            json=_approval_payload(expires_at="2000-01-01T00:00:00+00:00"),
        ).json()
        assert body["result"] == "denied"

    def test_create_unknown_action_type_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            APPROVALS,
            headers=AUTH_HEADERS,
            json=_approval_payload(action_type="not.a.real.action", action_id=None),
        ).json()
        assert body["result"] in ("denied", "not_found")


# ============================================================
# 2. Read + list
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

    def test_list_queue_returns_records(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        _create_approval(client, idempotency_key="a")
        _create_approval(client, idempotency_key="b")
        r = client.get(APPROVALS, headers=AUTH_HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 2
        assert body["storage"] == "memory"
        assert body["executed"] is False
        assert len(body["items"]) == 2
        for item in body["items"]:
            assert item["execution_allowed"] is False


# ============================================================
# 3. Approve / reject lifecycle
# ============================================================


class TestApproveRejectLifecycle:
    def test_approve_resolves_to_execution_blocked(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        approval_id, _ = _create_approval(client)
        r = client.post(decision_path(approval_id), headers=AUTH_HEADERS, json=_decision_payload())
        assert r.status_code == 200
        body = r.json()
        assert body["result"] == "approved"
        assert body["state"] == "execution_blocked"
        assert body["decision"] == "approve"
        assert body["execution_allowed"] is False
        assert body["executed"] is False
        assert body["reviewed_by"] == "reviewer-super-admin"
        assert body["reviewed_at"] is not None

    def test_reject_sets_rejected(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        approval_id, _ = _create_approval(client)
        r = client.post(
            decision_path(approval_id),
            headers=AUTH_HEADERS,
            json=_decision_payload(decision="reject"),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["result"] == "rejected"
        assert body["state"] == "rejected"
        assert body["decision"] == "reject"
        assert body["execution_allowed"] is False


# ============================================================
# 4. Safety invariants
# ============================================================


class TestSafetyInvariants:
    def test_approved_does_not_execute(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        approval_id, _ = _create_approval(client)
        body = client.post(
            decision_path(approval_id), headers=AUTH_HEADERS, json=_decision_payload()
        ).json()
        assert body["state"] == "execution_blocked"
        assert body["executed"] is False
        assert body["execution_allowed"] is False

    def test_execution_allowed_false_on_every_response(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        approval_id, create_body = _create_approval(client)
        approve_body = client.post(
            decision_path(approval_id), headers=AUTH_HEADERS, json=_decision_payload()
        ).json()
        read_body = client.get(read_path(approval_id), headers=AUTH_HEADERS).json()
        list_body = client.get(APPROVALS, headers=AUTH_HEADERS).json()
        for b in (create_body, approve_body, read_body):
            assert b["execution_allowed"] is False
            assert b["executed"] is False
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
        r = client.post(APPROVALS, json=_approval_payload())
        assert r.status_code == 401

    def test_unauthenticated_decision_denied_401(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(decision_path("any"), json=_decision_payload())
        assert r.status_code == 401

    def test_wrong_test_override_denied_403(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        r = client.post(
            APPROVALS, json=_approval_payload(),
            headers={"X-Platform-Test-Override": "wrong"},
        )
        assert r.status_code == 403

    def test_tenant_contextual_super_admin_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        auth_ctx = MagicMock()
        auth_ctx.token = _tenant_contextual_super_admin_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.post(APPROVALS, json=_approval_payload())
        assert r.status_code in (401, 403)

    def test_tenant_admin_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        auth_ctx = MagicMock()
        auth_ctx.token = _tenant_admin_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.post(APPROVALS, json=_approval_payload())
        assert r.status_code in (401, 403)

    def test_non_super_admin_identity_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        auth_ctx = MagicMock()
        auth_ctx.token = _non_super_admin_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.post(APPROVALS, json=_approval_payload())
        assert r.status_code in (401, 403)

    def test_identity_only_super_admin_allowed(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        auth_ctx = MagicMock()
        auth_ctx.token = _identity_super_admin_token()
        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            r = client.post(APPROVALS, json=_approval_payload())
        assert r.status_code == 200

    def test_all_p19_endpoints_guarded(self):
        """Every P19 endpoint must deny an unauthenticated caller (401)."""
        app = _make_app(source_status="available")
        client = TestClient(app)
        # No credentials on any of the four endpoints -> 401.
        assert client.post(APPROVALS, json=_approval_payload()).status_code == 401
        assert client.get(APPROVALS).status_code == 401
        assert client.get(read_path("x")).status_code == 401
        assert client.post(decision_path("x"), json=_decision_payload()).status_code == 401


# ============================================================
# 6. Expiry
# ============================================================


class TestExpiry:
    def test_expired_approval_cannot_be_approved(self):
        from api.v1.platform.p19 import services

        app = _make_app(source_status="available")
        client = TestClient(app)
        approval_id, _ = _create_approval(client)
        # Drive the expiry sweep with a far-future now -> pending -> expired.
        services.sweep_expired(now=datetime(3000, 1, 1, tzinfo=timezone.utc))
        body = client.post(
            decision_path(approval_id), headers=AUTH_HEADERS, json=_decision_payload()
        ).json()
        assert body["result"] == "expired"
        assert body["state"] == "expired"
        assert body["execution_allowed"] is False


# ============================================================
# 7. Reject is final
# ============================================================


class TestRejectFinal:
    def test_rejected_approval_cannot_be_approved(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        approval_id, _ = _create_approval(client)
        first = client.post(
            decision_path(approval_id),
            headers=AUTH_HEADERS,
            json=_decision_payload(decision="reject", idempotency_key="dec-reject"),
        ).json()
        assert first["state"] == "rejected"
        second = client.post(
            decision_path(approval_id),
            headers=AUTH_HEADERS,
            json=_decision_payload(decision="approve", idempotency_key="dec-approve-after"),
        ).json()
        assert second["result"] == "conflict"
        assert second["state"] == "rejected"


# ============================================================
# 8. Decision idempotency
# ============================================================


class TestDecisionIdempotency:
    def test_duplicate_same_decision_idempotent(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        approval_id, _ = _create_approval(client)
        first = client.post(
            decision_path(approval_id),
            headers=AUTH_HEADERS,
            json=_decision_payload(idempotency_key="dec-same"),
        ).json()
        assert first["result"] == "approved"
        second = client.post(
            decision_path(approval_id),
            headers=AUTH_HEADERS,
            json=_decision_payload(idempotency_key="dec-same"),
        ).json()
        assert second["result"] == "duplicate"
        assert second["state"] == "execution_blocked"
        assert second["execution_allowed"] is False

    def test_conflicting_decision_fails(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        approval_id, _ = _create_approval(client)
        first = client.post(
            decision_path(approval_id),
            headers=AUTH_HEADERS,
            json=_decision_payload(idempotency_key="dec-first"),
        ).json()
        assert first["result"] == "approved"
        # A second approve with a DIFFERENT idempotency_key is a conflict.
        second = client.post(
            decision_path(approval_id),
            headers=AUTH_HEADERS,
            json=_decision_payload(idempotency_key="dec-second"),
        ).json()
        assert second["result"] == "conflict"


# ============================================================
# 9. Redaction (value leakage, not just key leakage)
# ============================================================


class TestRedaction:
    def test_raw_secret_in_reason_redacted(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            APPROVALS,
            headers=AUTH_HEADERS,
            json=_approval_payload(
                reason="db password=hunter2 please approve",  # pragma: allowlist secret
                idempotency_key="appr-secret-reason",
            ),
        ).json()
        assert body["reason"] == "[redacted]"
        serialized = str(body)
        assert "hunter2" not in serialized

    def test_raw_secret_in_metadata_redacted(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            APPROVALS,
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
        # Metadata is not echoed on the record at all; no raw secret leaks.
        serialized = str(body)
        assert "hunter2" not in serialized
        assert "10.0.0.5" not in serialized
        assert "5432" not in serialized

    def test_idempotency_and_correlation_not_echoed_raw(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            APPROVALS,
            headers=AUTH_HEADERS,
            json=_approval_payload(
                idempotency_key="token=super-secret-val",  # pragma: allowlist secret
                correlation_id="postgres://u:p@db.internal:6432/x",  # pragma: allowlist secret
            ),
        ).json()
        assert body["idempotency_key"] == "[redacted]"
        assert body["correlation_id"] == "[redacted]"
        serialized = str(body)
        assert "super-secret-val" not in serialized
        assert "db.internal" not in serialized
        assert "6432" not in serialized

    def test_audit_payload_never_carries_raw_secret(self):
        from api.v1.platform.p19 import services

        app = _make_app(source_status="available")
        client = TestClient(app)
        client.post(
            APPROVALS,
            headers=AUTH_HEADERS,
            json=_approval_payload(
                reason="creds token=OH-NO-SECRET",  # pragma: allowlist secret
                idempotency_key="appr-audit-secret",
            ),
        )
        for event in services.audit_log():
            assert "OH-NO-SECRET" not in str(event.reason)
            assert event.redaction_applied is True

    def test_audit_helper_redacts_raw_reason_value(self):
        """_build_approval_audit_event redacts reason internally (P19-B-R1):
        a raw 'password=...' / 'token=...' value becomes '[redacted]'."""
        from api.v1.platform.p19.services import _build_approval_audit_event

        raws = [
            "password=hunter2",  # pragma: allowlist secret
            "token=abc123",  # pragma: allowlist secret
        ]
        for raw in raws:
            ev = _build_approval_audit_event(
                event_type="approval_requested",
                actor="ops",
                identity_context="identity_only",
                tenant_id=TENANT_ID,
                action_id=None,
                approval_id="appr-1",
                decision=None,
                reason=raw,
            )
            assert ev.redaction_applied is True
            assert ev.reason == "[redacted]"
            assert raw not in ev.reason

    def test_emit_does_not_leak_raw_reason_into_audit_log(self):
        """_emit applies redaction internally (P19-B-R1) so a raw reason value
        fed straight to _emit never reaches audit_log."""
        from api.v1.platform.p19 import services

        services.reset_store()
        services._emit(
            event_type="approval_requested",
            actor="ops",
            identity_context="identity_only",
            tenant_id=TENANT_ID,
            action_id=None,
            approval_id="appr-x",
            decision=None,
            reason="password=leaked-secret",  # pragma: allowlist secret
            now=datetime(2026, 6, 24, tzinfo=timezone.utc),
        )
        for ev in services.audit_log():
            assert "leaked-secret" not in ev.reason
            assert ev.reason == "[redacted]"
            assert ev.redaction_applied is True


# ============================================================
# 9b. R1 security: raw idempotency key never stored (digest only)
# ============================================================


class TestR1DigestStorage:
    """P19-B-R1: the RAW idempotency_key is never stored in the store, in a
    record slot, or in an audit event. Only its SHA-256 digest is stored, and
    the response echoes the sanitized (redacted) key. Duplicate / conflict
    semantics are unchanged."""

    def test_raw_create_key_not_in_store_index_or_slot(self):
        import hashlib

        from api.v1.platform.p19 import services

        app = _make_app(source_status="available")
        client = TestClient(app)
        raw = "my-raw-create-key"
        approval_id, body = _create_approval(client, idempotency_key=raw)
        assert body["result"] == "recorded"
        # The raw key is NOT a key in the create-key index.
        assert raw not in services._STORE_BY_CREATE_KEY
        # The stored create_key slot is a 64-hex digest, not the raw key.
        rec = services._STORE[approval_id]
        assert rec.create_key != raw
        assert rec.create_key == hashlib.sha256(raw.encode("utf-8")).hexdigest()
        assert all(c in "0123456789abcdef" for c in rec.create_key)

    def test_raw_decision_key_not_stored(self):
        from api.v1.platform.p19 import services

        app = _make_app(source_status="available")
        client = TestClient(app)
        approval_id, _ = _create_approval(client, idempotency_key="create-k")
        raw_dec = "my-raw-decision-key"
        body = client.post(
            decision_path(approval_id),
            headers=AUTH_HEADERS,
            json=_decision_payload(idempotency_key=raw_dec),
        ).json()
        assert body["result"] == "approved"
        rec = services._STORE[approval_id]
        assert rec.decision_key != raw_dec
        assert all(c in "0123456789abcdef" for c in (rec.decision_key or ""))
        assert len(rec.decision_key or "") == 64

    def test_create_duplicate_same_payload_idempotent(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        first = client.post(
            APPROVALS, headers=AUTH_HEADERS, json=_approval_payload(idempotency_key="dup-k")
        ).json()
        assert first["result"] == "recorded"
        second = client.post(
            APPROVALS, headers=AUTH_HEADERS, json=_approval_payload(idempotency_key="dup-k")
        ).json()
        assert second["result"] == "duplicate"
        assert second["approval_id"] == first["approval_id"]

    def test_create_conflict_different_payload_fails(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        first = client.post(
            APPROVALS,
            headers=AUTH_HEADERS,
            json=_approval_payload(idempotency_key="conf-k", reason="reason A"),
        ).json()
        assert first["result"] == "recorded"
        second = client.post(
            APPROVALS,
            headers=AUTH_HEADERS,
            json=_approval_payload(idempotency_key="conf-k", reason="reason B"),
        ).json()
        assert second["result"] == "conflict"

    def test_response_echoes_sanitized_key_never_raw_or_digest(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            APPROVALS,
            headers=AUTH_HEADERS,
            json=_approval_payload(idempotency_key="token=raw-secret-key"),  # pragma: allowlist secret
        ).json()
        # Echoed idempotency_key is sanitized (redacted): never the raw key,
        # never the 64-char digest.
        assert body["idempotency_key"] == "[redacted]"
        assert "raw-secret-key" not in str(body)


# ============================================================
# 10. P18 validation boundary
# ============================================================


class TestP18Boundary:
    def test_unknown_p18_source_status_cannot_approve(self):
        # No source_status patch -> P18 resolver returns "unknown" (default).
        app = _make_app()
        client = TestClient(app)
        approval_id, create_body = _create_approval(client, idempotency_key="appr-unknown-src")
        # Creation succeeds (records the honest unknown source) ...
        assert create_body["state"] == "pending_review"
        assert create_body["source_status"] == "unknown"
        # ... but the approve is denied.
        body = client.post(
            decision_path(approval_id), headers=AUTH_HEADERS, json=_decision_payload()
        ).json()
        assert body["result"] == "denied"
        assert body["state"] == "pending_review"
        assert body["execution_allowed"] is False

    def test_action_id_not_found_denied(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        body = client.post(
            APPROVALS,
            headers=AUTH_HEADERS,
            json=_approval_payload(
                action_id="00000000-0000-0000-0000-000000000000",
                action_type=None,
                idempotency_key="appr-missing-action",
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
            created_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
        )
        app = _make_app()
        client = TestClient(app)
        with patch("api.v1.platform.p18.services.get_stored_request", return_value=fake):
            body = client.post(
                APPROVALS,
                headers=AUTH_HEADERS,
                json=_approval_payload(
                    action_id="p18-recorded-1",
                    action_type=None,
                    idempotency_key="appr-by-action-id",
                ),
            ).json()
        assert body["result"] == "recorded"
        assert body["source_status"] == "available"
        assert body["action_type"] == "tenant.pause"

    def test_available_is_never_fabricated(self):
        # When the P18 source is unknown, the record stores "unknown", not "available".
        app = _make_app()
        client = TestClient(app)
        _, body = _create_approval(client, idempotency_key="appr-no-fabricate")
        assert body["source_status"] == "unknown"


# ============================================================
# 11. No mutation / persistent storage + route registration
# ============================================================


class TestNoMutationAndRegistration:
    EXPECTED_PATHS = {
        f"{APPROVALS}",
        f"{APPROVALS}/{{approval_id}}",
        f"{APPROVALS}/{{approval_id}}/decision",
    }

    def test_p19_router_registers_expected_routes(self):
        from api.v1.platform.p19.routes import router

        paths = {route.path for route in router.routes}
        assert self.EXPECTED_PATHS <= paths
        # The resource root supports POST (create) and GET (list); two routes
        # share the path, so aggregate methods across all routes at that path.
        root_methods: set = set()
        for r in router.routes:
            if r.path == APPROVALS:
                root_methods |= set(r.methods)
        assert "POST" in root_methods
        assert "GET" in root_methods
        # No mutating-by-effect methods beyond POST (no PUT/PATCH/DELETE).
        for route in router.routes:
            for method in route.methods:
                assert method in {"GET", "POST"}

    def test_storage_is_in_memory_no_persistence(self):
        app = _make_app(source_status="available")
        client = TestClient(app)
        _create_approval(client, idempotency_key="p1")
        queue = client.get(APPROVALS, headers=AUTH_HEADERS).json()
        assert queue["storage"] == "memory"
        for item in queue["items"]:
            assert item["storage"] == "memory"

    def test_no_p19_migration_or_alembic_files(self):
        import glob
        import os

        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p19_migrations = []
        for pattern in ("**/migrations/**", "**/alembic/**"):
            for path in glob.glob(os.path.join(backend_dir, pattern), recursive=True):
                if "p19" in os.path.basename(path).lower():
                    p19_migrations.append(path)
        assert p19_migrations == []
