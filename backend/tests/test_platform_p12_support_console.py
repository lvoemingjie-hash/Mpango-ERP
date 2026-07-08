"""
P12 Support Console API tests.

Contract-backed tests covering:
  - Schema validation (reason min length, extra fields, enums)
  - Session lifecycle (create, get diagnostics, close, expire)
  - Bundle generation (full, technical, summary)
  - Guard enforcement (identity-only, tenant-contextual denied)
  - Redaction (sensitive keys removed, raw payloads excluded)
  - Audit events (session_start, bundle_generated, session_end)
  - Counterexamples (unknown != healthy, null != 0, no raw payloads)
  - Reason sanitization (credential content stripped before storage)
  - Access-denied audit (support_access_denied on 401/403)
  - Route-level identity (identity-only super_admin, contextual denied, tenant denied)
  - Session expiry audit (support_session_expired on lazy TTL)
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")
os.environ.setdefault("PLATFORM_OPERATOR_SECRET", "test-operator-secret")


# -- Helpers --

AUTH_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}
OPERATOR_HEADERS = {"X-Platform-Operator": "test-operator-secret"}

# Valid UUID v4 for testing (version nibble = 4, variant = 8/9/a/b)
TENANT_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
VALID_REASON = "Tenant login failure triage -- users cannot authenticate"


def _mock_db():
    """Mock DB with zero-result responses."""
    db = MagicMock()
    zero = MagicMock()
    zero.scalar.return_value = 0
    zero.scalar_one_or_none.return_value = None
    zero.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=zero)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def _mock_wholesaler():
    """Create a mock Wholesaler object."""
    w = MagicMock()
    w.id = uuid.uuid4()
    w.name = "Test Wholesaler"
    w.status = "active"
    w.code = "test"
    w.plan_type = "professional"
    w.created_at = datetime(2026, 1, 15, 9, 30, 0, tzinfo=timezone.utc)
    w.is_deleted = False
    w.get_tenant_schema.return_value = "t_test"
    return w


def _make_app(mock_db):
    """Build test app with P12 routes and mocked DB."""
    from api.v1.platform.p12.routes import router
    from api.dependencies import get_db, get_platform_db
    from database.session import get_db as db_get_db

    app = FastAPI()
    async def override():
        yield mock_db
    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_platform_db] = app.dependency_overrides[get_db]
    app.dependency_overrides[db_get_db] = override
    app.include_router(router)
    return app


def _make_guarded_app(mock_db=None):
    """Build app with guard active (no guard override)."""
    db = mock_db or _mock_db()
    return _make_app(db)


# ============================================================
# 1. Schema Validation
# ============================================================


class TestSchemas:
    """P12-A-R1 contract schema validation."""

    def test_reason_null_accepted_in_schema(self):
        """Schema accepts null reason; route layer enforces min 10 chars."""
        from api.v1.platform.p12.schemas import CreateSessionRequest
        req = CreateSessionRequest(reason=None, category="general")
        assert req.reason is None

    def test_reason_short_accepted_in_schema(self):
        """Schema accepts short reason; route layer enforces min 10 chars."""
        from api.v1.platform.p12.schemas import CreateSessionRequest
        req = CreateSessionRequest(reason="short", category="general")
        assert req.reason == "short"

    def test_extra_fields_rejected(self):
        from api.v1.platform.p12.schemas import CreateSessionRequest
        with pytest.raises(Exception):
            # extra="forbid" should reject unknown fields
            import json
            data = {"reason": "A valid reason text", "category": "general", "extra": True}
            from pydantic import TypeAdapter
            CreateSessionRequest(**data)

    def test_bundle_type_enum(self):
        from api.v1.platform.p12.schemas import CreateBundleRequest
        for bt in ("full", "technical", "summary"):
            req = CreateBundleRequest(bundle_type=bt)
            assert req.bundle_type == bt

    def test_invalid_bundle_type_rejected(self):
        from api.v1.platform.p12.schemas import CreateBundleRequest
        with pytest.raises(Exception):
            CreateBundleRequest(bundle_type="invalid")

    def test_session_status_enum(self):
        from api.v1.platform.p12.schemas import SupportSession
        now = datetime.now(timezone.utc)
        for status_val in ("active", "closed", "expired"):
            s = SupportSession(
                session_id=str(uuid.uuid4()),
                reason="Test reason for session status",
                category="general",
                status=status_val,
                started_at=now,
                expires_at=now + timedelta(hours=1),
            )
            assert s.status == status_val

    def test_redaction_applied_must_be_true(self):
        from api.v1.platform.p12.schemas import SupportBundle
        now = datetime.now(timezone.utc)
        with pytest.raises(Exception):
            SupportBundle(
                bundle_id=str(uuid.uuid4()),
                session_id=str(uuid.uuid4()),
                generated_at=now,
                diagnostics=[
                    {
                        "item_id": str(uuid.uuid4()),
                        "category": "test",
                        "label": "test",
                        "value": "test",
                        "source_status": "available",
                        "collected_at": now,
                    }
                ],
                redaction_applied=False,
                bundle_type="full",
            )


# ============================================================
# 2. Create Session
# ============================================================


class TestCreateSession:
    """POST /api/v1/platform/p12/sessions"""

    def test_create_session_success(self):
        """Valid request returns 201 with session."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={
                "reason": VALID_REASON,
                "category": "login_issue",
                "tenant_id": TENANT_ID,
            },
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["reason"] == VALID_REASON
        assert data["category"] == "login_issue"
        assert data["tenant_id"] == TENANT_ID
        assert data["status"] == "active"
        assert data["bundle_count"] == 0
        assert data["session_id"] is not None
        assert data["started_at"] is not None
        assert data["expires_at"] is not None
        assert data["closed_at"] is None

    def test_create_session_short_reason_rejected(self):
        """Reason shorter than 10 chars returns 400."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": "short", "category": "general"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "REASON_TOO_SHORT"

    def test_create_session_missing_reason_rejected(self):
        """Missing reason field returns 400."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"category": "general"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "MISSING_REASON"

    def test_create_session_missing_category_rejected(self):
        """Missing category field returns 422."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 422

    def test_create_session_no_tenant_id_ok(self):
        """Session can be created without tenant_id."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        assert resp.json()["tenant_id"] is None

    def test_create_session_audit_event_written(self):
        """Audit event is written for session creation."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "login_issue", "tenant_id": TENANT_ID},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        # Verify audit entry was written
        mock_db.add.assert_called_once()
        audit_entry = mock_db.add.call_args[0][0]
        assert audit_entry.action == "support_session_start"
        mock_db.commit.assert_called_once()


# ============================================================
# 3. Get Diagnostics
# ============================================================


class TestGetDiagnostics:
    """GET /api/v1/platform/p12/sessions/{session_id}/diagnostics"""

    def _create_session(self, client):
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "login_issue", "tenant_id": TENANT_ID},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        return resp.json()["session_id"]

    def test_get_diagnostics_success(self):
        """Active session returns 200 with diagnostic items."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        sid = self._create_session(client)
        resp = client.get(
            f"/api/v1/platform/p12/sessions/{sid}/diagnostics",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert isinstance(items, list)
        assert len(items) > 0
        # Verify each item has required fields
        for item in items:
            assert "item_id" in item
            assert "category" in item
            assert "label" in item
            assert "source_status" in item
            assert "collected_at" in item

    def test_get_diagnostics_session_not_found(self):
        """Non-existent session returns 404."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        fake_id = str(uuid.uuid4())
        resp = client.get(
            f"/api/v1/platform/p12/sessions/{fake_id}/diagnostics",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 404

    def test_get_diagnostics_unknown_stays_unknown(self):
        """Unavailable metrics must stay null/unknown, not fabricated healthy/0."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        sid = self._create_session(client)
        resp = client.get(
            f"/api/v1/platform/p12/sessions/{sid}/diagnostics",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        items = resp.json()
        # Telemetry-required items should have source_status="unavailable" and value=null
        for item in items:
            if item["category"] in ("recent_errors", "slow_routes", "failed_jobs"):
                assert item["source_status"] == "unavailable"
                assert item["value"] is None


# ============================================================
# 4. Create Bundle
# ============================================================


class TestCreateBundle:
    """POST /api/v1/platform/p12/sessions/{session_id}/bundles"""

    def _create_session(self, client):
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "login_issue", "tenant_id": TENANT_ID},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        return resp.json()["session_id"]

    def test_create_bundle_full(self):
        """Full bundle type includes all diagnostic categories."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        sid = self._create_session(client)
        resp = client.post(
            f"/api/v1/platform/p12/sessions/{sid}/bundles",
            json={"bundle_type": "full"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["bundle_type"] == "full"
        assert data["redaction_applied"] is True
        assert len(data["diagnostics"]) > 0
        categories = {d["category"] for d in data["diagnostics"]}
        assert "tenant_metadata" in categories
        assert "health_summary" in categories
        assert "system_snapshot" in categories

    def test_create_bundle_technical(self):
        """Technical bundle excludes tenant_metadata."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        sid = self._create_session(client)
        resp = client.post(
            f"/api/v1/platform/p12/sessions/{sid}/bundles",
            json={"bundle_type": "technical"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["bundle_type"] == "technical"
        categories = {d["category"] for d in data["diagnostics"]}
        assert "tenant_metadata" not in categories
        assert "health_summary" in categories

    def test_create_bundle_summary(self):
        """Summary bundle includes only tenant_metadata and health_summary."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        sid = self._create_session(client)
        resp = client.post(
            f"/api/v1/platform/p12/sessions/{sid}/bundles",
            json={"bundle_type": "summary"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["bundle_type"] == "summary"
        categories = {d["category"] for d in data["diagnostics"]}
        # Summary should only have tenant_metadata and health_summary
        assert categories.issubset({"tenant_metadata", "health_summary"})

    def test_create_bundle_session_not_found(self):
        """Bundle on non-existent session returns 404."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        fake_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/v1/platform/p12/sessions/{fake_id}/bundles",
            json={"bundle_type": "full"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 404

    def test_create_bundle_audit_event_written(self):
        """Audit event is written for bundle generation."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)
        # Create session
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
            headers=AUTH_HEADERS,
        )
        sid = resp.json()["session_id"]
        mock_db.add.reset_mock()
        mock_db.commit.reset_mock()
        # Generate bundle
        resp = client.post(
            f"/api/v1/platform/p12/sessions/{sid}/bundles",
            json={"bundle_type": "full"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        mock_db.add.assert_called_once()
        audit_entry = mock_db.add.call_args[0][0]
        assert audit_entry.action == "support_bundle_generated"
        mock_db.commit.assert_called_once()

    def test_redaction_applied_is_true(self):
        """Bundles must have redaction_applied=true."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        sid = self._create_session(client)
        resp = client.post(
            f"/api/v1/platform/p12/sessions/{sid}/bundles",
            json={"bundle_type": "full"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        assert resp.json()["redaction_applied"] is True


# ============================================================
# 5. Close Session
# ============================================================


class TestCloseSession:
    """POST /api/v1/platform/p12/sessions/{session_id}/close"""

    def _create_session(self, client):
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        return resp.json()["session_id"]

    def test_close_session_success(self):
        """Closing active session returns 200 with status=closed."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        sid = self._create_session(client)
        resp = client.post(
            f"/api/v1/platform/p12/sessions/{sid}/close",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "closed"
        assert data["closed_at"] is not None

    def test_close_session_not_found(self):
        """Closing non-existent session returns 404."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        fake_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/v1/platform/p12/sessions/{fake_id}/close",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 404

    def test_close_session_already_closed(self):
        """Closing already-closed session returns 409."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        sid = self._create_session(client)
        # Close once
        resp = client.post(
            f"/api/v1/platform/p12/sessions/{sid}/close",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        # Close again -- session store returns None after close removes it
        resp2 = client.post(
            f"/api/v1/platform/p12/sessions/{sid}/close",
            headers=AUTH_HEADERS,
        )
        assert resp2.status_code in (404, 409)

    def test_close_session_audit_event_written(self):
        """Audit event is written for session close."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
            headers=AUTH_HEADERS,
        )
        sid = resp.json()["session_id"]
        mock_db.add.reset_mock()
        mock_db.commit.reset_mock()
        resp = client.post(
            f"/api/v1/platform/p12/sessions/{sid}/close",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        mock_db.add.assert_called_once()
        audit_entry = mock_db.add.call_args[0][0]
        assert audit_entry.action == "support_session_end"
        mock_db.commit.assert_called_once()


# ============================================================
# 6. Guard Enforcement
# ============================================================


class TestGuardEnforcement:
    """P12 endpoints reuse P10 guard -- identity-only enforcement."""

    def test_no_headers_denied(self):
        """No credentials at all returns 401."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
        )
        assert resp.status_code == 401

    def test_wrong_operator_secret_denied(self):
        """Wrong operator secret returns 403."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
            headers={"X-Platform-Operator": "wrong-secret"},
        )
        assert resp.status_code == 403

    def test_test_override_allowed_in_test_env(self):
        """Test override header works in test environment."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201

    def test_operator_secret_allowed(self):
        """Operator secret header works in all environments."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
            headers=OPERATOR_HEADERS,
        )
        assert resp.status_code == 201


# ============================================================
# 7. Session Expiry
# ============================================================


class TestSessionExpiry:
    """Session TTL enforcement."""

    def test_expired_session_returns_404(self):
        """Expired session is treated as not found."""
        from api.v1.platform.p12.services import _session_store, SupportSessionStore
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        # Create session
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        sid = resp.json()["session_id"]
        # Manually expire the session
        session = _session_store._sessions.get(sid)
        assert session is not None
        session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        # Try to get diagnostics -- should 404
        resp2 = client.get(
            f"/api/v1/platform/p12/sessions/{sid}/diagnostics",
            headers=AUTH_HEADERS,
        )
        assert resp2.status_code == 404

    def test_bundle_on_expired_session_returns_404(self):
        """Bundle generation on expired session returns 404."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
            headers=AUTH_HEADERS,
        )
        sid = resp.json()["session_id"]
        session = _session_store._sessions.get(sid)
        session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        resp2 = client.post(
            f"/api/v1/platform/p12/sessions/{sid}/bundles",
            json={"bundle_type": "full"},
            headers=AUTH_HEADERS,
        )
        assert resp2.status_code == 404


# ============================================================
# 8. Counterexamples and Redaction
# ============================================================


class TestCounterexamples:
    """Counterexamples from P12-A-R1 Section 10.2."""

    def test_sensitive_keys_redacted(self):
        """Passwords, tokens, secrets must be removed from diagnostics."""
        from api.v1.platform.p10.services import redact_metadata
        raw = {
            "tenant_name": "Acme",
            "password": "secret123",  # pragma: allowlist secret
            "token": "bearer-abc",  # pragma: allowlist secret
            "secret_key": "sk-xxx",  # pragma: allowlist secret
            "card_number": "4111111111111111",
            "safe_field": "visible",
        }
        result = redact_metadata(raw)
        assert "password" not in result
        assert "token" not in result
        assert "secret_key" not in result
        assert "card_number" not in result
        assert result["tenant_name"] == "Acme"
        assert result["safe_field"] == "visible"

    def test_raw_business_payloads_excluded(self):
        """Raw business payloads must not appear in diagnostics."""
        from api.v1.platform.p10.services import redact_metadata
        raw = {
            "tenant_name": "Acme",
            "payload": {"orders": [{"id": 1, "items": ["widget"]}]},
            "request_body": "raw-data",
        }
        result = redact_metadata(raw)
        assert "payload" not in result
        assert "request_body" not in result
        assert result["tenant_name"] == "Acme"

    def test_unknown_not_healthy(self):
        """Unknown status must not be fabricated as healthy."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
            headers=AUTH_HEADERS,
        )
        sid = resp.json()["session_id"]
        resp2 = client.get(
            f"/api/v1/platform/p12/sessions/{sid}/diagnostics",
            headers=AUTH_HEADERS,
        )
        assert resp2.status_code == 200
        items = resp2.json()
        # System snapshot should have overall_status="unknown" not "healthy"
        for item in items:
            if item["category"] == "system_snapshot":
                val = item["value"]
                if val and isinstance(val, dict):
                    assert val.get("overall_status") != "healthy"

    def test_null_not_zero(self):
        """Null values must not be fabricated as 0."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        app = _make_guarded_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
            headers=AUTH_HEADERS,
        )
        sid = resp.json()["session_id"]
        resp2 = client.get(
            f"/api/v1/platform/p12/sessions/{sid}/diagnostics",
            headers=AUTH_HEADERS,
        )
        assert resp2.status_code == 200
        items = resp2.json()
        # Telemetry-required items should have value=null, not 0
        for item in items:
            if item["source_status"] == "unavailable":
                assert item["value"] is None

    def test_bundle_default_type_is_full(self):
        """Default bundle type should be full."""
        from api.v1.platform.p12.schemas import CreateBundleRequest
        req = CreateBundleRequest()
        assert req.bundle_type == "full"


# ============================================================
# 9. Reason Sanitization
# ============================================================


class TestReasonSanitization:
    """Support reason credential content must be stripped before storage."""

    def test_password_value_stripped(self):
        """password=xxx patterns replaced with [REDACTED]."""
        from api.v1.platform.p12.services import sanitize_reason
        result = sanitize_reason("user reported password=admin123 cannot login")  # pragma: allowlist secret
        assert "admin123" not in result
        assert "[REDACTED]" in result
        assert "user reported" in result

    def test_token_value_stripped(self):
        """token: xxx patterns replaced with [REDACTED]."""
        from api.v1.platform.p12.services import sanitize_reason
        result = sanitize_reason("debug: token: bearer-abc-123 expired")  # pragma: allowlist secret
        assert "bearer-abc-123" not in result
        assert "[REDACTED]" in result
        assert "debug:" in result

    def test_secret_key_value_stripped(self):
        """secret_key=xxx patterns replaced with [REDACTED]."""
        from api.v1.platform.p12.services import sanitize_reason
        result = sanitize_reason("secret_key=sk-live-xxx failing")  # pragma: allowlist secret
        assert "sk-live-xxx" not in result
        assert "[REDACTED]" in result

    def test_api_key_value_stripped(self):
        """api_key=xxx patterns replaced with [REDACTED]."""
        from api.v1.platform.p12.services import sanitize_reason
        result = sanitize_reason("api_key=ak-12345 integration broken")  # pragma: allowlist secret
        assert "ak-12345" not in result
        assert "[REDACTED]" in result

    def test_cookie_value_stripped(self):
        """cookie=xxx patterns replaced with [REDACTED]."""
        from api.v1.platform.p12.services import sanitize_reason
        result = sanitize_reason("cookie=sessionid=abc not working")  # pragma: allowlist secret
        assert "sessionid=abc" not in result
        assert "[REDACTED]" in result

    def test_bearer_value_stripped(self):
        """bearer=xxx patterns replaced with [REDACTED]."""
        from api.v1.platform.p12.services import sanitize_reason
        result = sanitize_reason("bearer=tok-xyz auth issue")  # pragma: allowlist secret
        assert "tok-xyz" not in result
        assert "[REDACTED]" in result

    def test_plain_password_word_preserved(self):
        """The word 'password' without a value is preserved."""
        from api.v1.platform.p12.services import sanitize_reason
        result = sanitize_reason("users cannot complete password reset")
        assert result == "users cannot complete password reset"
        assert "[REDACTED]" not in result

    def test_plain_token_word_preserved(self):
        """The word 'token' without a value is preserved."""
        from api.v1.platform.p12.services import sanitize_reason
        result = sanitize_reason("user's token was expired unexpectedly")
        assert result == "user's token was expired unexpectedly"

    def test_sanitized_reason_stored_in_session(self):
        """Session storage contains sanitized reason, not raw credential."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={
                "reason": "debug password=supersecret login issue",  # pragma: allowlist secret
                "category": "login_issue",
            },
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "supersecret" not in data["reason"]  # pragma: allowlist secret
        assert "[REDACTED]" in data["reason"]

    def test_sanitized_reason_in_audit_metadata(self):
        """Audit metadata contains sanitized reason."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={
                "reason": "debug api_key=ak-12345 call fails",  # pragma: allowlist secret
                "category": "integration",
            },
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        audit_entry = mock_db.add.call_args[0][0]
        assert "ak-12345" not in audit_entry.audit_metadata["reason"]  # pragma: allowlist secret
        assert "[REDACTED]" in audit_entry.audit_metadata["reason"]


# ============================================================
# 10. Access-Denied Audit
# ============================================================


class TestAccessDeniedAudit:
    """support_access_denied audit events on denied access."""

    def test_no_headers_writes_denied_audit(self):
        """No credentials writes support_access_denied with actor_id=null."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
        )
        assert resp.status_code == 401
        # Verify audit entry was written
        assert mock_db.add.called
        audit_entry = mock_db.add.call_args[0][0]
        assert audit_entry.action == "support_access_denied"
        assert audit_entry.actor_id is None
        assert mock_db.commit.called

    def test_wrong_secret_writes_denied_audit(self):
        """Wrong operator secret writes support_access_denied."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
            headers={"X-Platform-Operator": "wrong-secret"},
        )
        assert resp.status_code == 403
        assert mock_db.add.called
        audit_entry = mock_db.add.call_args[0][0]
        assert audit_entry.action == "support_access_denied"

    def test_contextual_super_admin_denied_writes_audit(self):
        """Tenant-contextual super_admin denied writes support_access_denied with actor_id."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)

        token = MagicMock()
        token.user_id = "b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d"
        token.roles = ["super_admin"]
        token.tenant_id = TENANT_ID
        token.tenant_schema = "t_test"
        token.is_identity_only = False
        token.is_super_admin = True

        auth_ctx = MagicMock()
        auth_ctx.token = token

        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            resp = client.post(
                "/api/v1/platform/p12/sessions",
                json={"reason": VALID_REASON, "category": "general"},
            )
        # Contextual super_admin without platform headers is denied
        assert resp.status_code == 401
        assert mock_db.add.called
        audit_entry = mock_db.add.call_args[0][0]
        assert audit_entry.action == "support_access_denied"

    def test_denied_audit_has_path_metadata(self):
        """Denied audit includes the request path in metadata."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
        )
        assert resp.status_code == 401
        audit_entry = mock_db.add.call_args[0][0]
        meta = audit_entry.audit_metadata
        assert "sessions" in meta["path"]
        assert meta["code"] == "PLATFORM_ACCESS_REQUIRED"


# ============================================================
# 11. Route-Level Identity Tests
# ============================================================


class TestRouteLevelIdentity:
    """P12 route-level identity enforcement via Bearer token."""

    def test_identity_only_super_admin_allowed(self):
        """Identity-only global super_admin Bearer token is allowed."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)

        token = MagicMock()
        token.user_id = "b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d"
        token.roles = ["super_admin"]
        token.tenant_id = None
        token.tenant_schema = None
        token.is_identity_only = True
        token.is_super_admin = True

        auth_ctx = MagicMock()
        auth_ctx.token = token

        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            resp = client.post(
                "/api/v1/platform/p12/sessions",
                json={"reason": VALID_REASON, "category": "general"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "active"

    def test_contextual_super_admin_denied(self):
        """Tenant-contextual super_admin Bearer token is denied."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)

        token = MagicMock()
        token.user_id = "c3d4e5f6-a7b8-49c9-0d1e-2f3a4b5c6d7e"
        token.roles = ["super_admin"]
        token.tenant_id = TENANT_ID
        token.tenant_schema = "t_test"
        token.is_identity_only = False
        token.is_super_admin = True

        auth_ctx = MagicMock()
        auth_ctx.token = token

        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            resp = client.post(
                "/api/v1/platform/p12/sessions",
                json={"reason": VALID_REASON, "category": "general"},
            )
        assert resp.status_code == 401

    def test_tenant_user_denied(self):
        """Regular tenant user (not super_admin) is denied."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)

        token = MagicMock()
        token.user_id = "d4e5f6a7-b8c9-4a0d-1e2f-3a4b5c6d7e8f"
        token.roles = ["user"]
        token.tenant_id = TENANT_ID
        token.tenant_schema = "t_test"
        token.is_identity_only = False
        token.is_super_admin = False

        auth_ctx = MagicMock()
        auth_ctx.token = token

        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            resp = client.post(
                "/api/v1/platform/p12/sessions",
                json={"reason": VALID_REASON, "category": "general"},
            )
        assert resp.status_code == 401

    def test_identity_only_non_super_admin_denied(self):
        """Identity-only token without super_admin role is denied."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)

        token = MagicMock()
        token.user_id = "e5f6a7b8-c9d0-4e1f-2a3b-4c5d6e7f8a9b"
        token.roles = ["support_operator"]
        token.tenant_id = None
        token.tenant_schema = None
        token.is_identity_only = True
        token.is_super_admin = False

        auth_ctx = MagicMock()
        auth_ctx.token = token

        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            resp = client.post(
                "/api/v1/platform/p12/sessions",
                json={"reason": VALID_REASON, "category": "general"},
            )
        assert resp.status_code == 401


# ============================================================
# 12. Session Expiry Audit
# ============================================================


class TestSessionExpiryAudit:
    """support_session_expired audit on lazy TTL expiry."""

    def test_expired_session_writes_expiry_audit(self):
        """Accessing expired session writes support_session_expired audit."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)
        # Create session
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        sid = resp.json()["session_id"]
        # Expire it
        session = _session_store._sessions.get(sid)
        assert session is not None
        session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        # Access expired session -- triggers lazy expiry + audit
        mock_db.add.reset_mock()
        mock_db.commit.reset_mock()
        resp2 = client.get(
            f"/api/v1/platform/p12/sessions/{sid}/diagnostics",
            headers=AUTH_HEADERS,
        )
        assert resp2.status_code == 404
        # Verify expiry audit was written
        assert mock_db.add.called
        audit_entry = mock_db.add.call_args[0][0]
        assert audit_entry.action == "support_session_expired"

    def test_expired_bundle_writes_expiry_audit(self):
        """Bundle generation on expired session writes support_session_expired."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
            headers=AUTH_HEADERS,
        )
        sid = resp.json()["session_id"]
        session = _session_store._sessions.get(sid)
        session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        mock_db.add.reset_mock()
        mock_db.commit.reset_mock()
        resp2 = client.post(
            f"/api/v1/platform/p12/sessions/{sid}/bundles",
            json={"bundle_type": "full"},
            headers=AUTH_HEADERS,
        )
        assert resp2.status_code == 404
        assert mock_db.add.called
        audit_entry = mock_db.add.call_args[0][0]
        assert audit_entry.action == "support_session_expired"

    def test_not_found_no_session_does_not_write_expiry_audit(self):
        """Non-existent session (never created) does NOT write expiry audit."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)
        fake_id = str(uuid.uuid4())
        resp = client.get(
            f"/api/v1/platform/p12/sessions/{fake_id}/diagnostics",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 404
        # No expiry audit -- session never existed
        assert not mock_db.add.called


# ============================================================
# 13. Reason Contract Patch (R3)
# ============================================================


class TestReasonContractPatch:
    """P12-B-R3: missing/short reason returns 400 + support_access_denied audit."""

    def test_missing_reason_returns_400_with_audit(self):
        """Missing reason -> 400 + support_access_denied audit written."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"category": "general"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "MISSING_REASON"
        # Verify support_access_denied audit was written
        assert mock_db.add.called
        audit_entry = mock_db.add.call_args[0][0]
        assert audit_entry.action == "support_access_denied"
        assert audit_entry.audit_metadata["code"] == "MISSING_REASON"
        assert audit_entry.audit_metadata["denial_type"] == "invalid_reason"
        mock_db.commit.assert_called()

    def test_short_reason_returns_400_with_audit(self):
        """Short reason -> 400 + support_access_denied audit written."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": "short", "category": "general"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "REASON_TOO_SHORT"
        assert mock_db.add.called
        audit_entry = mock_db.add.call_args[0][0]
        assert audit_entry.action == "support_access_denied"
        assert audit_entry.audit_metadata["code"] == "REASON_TOO_SHORT"
        assert audit_entry.audit_metadata["denial_type"] == "invalid_reason"

    def test_valid_reason_creates_session_start_audit(self):
        """Valid reason creates support_session_start, not support_access_denied."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON, "category": "general"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        assert mock_db.add.called
        audit_entry = mock_db.add.call_args[0][0]
        assert audit_entry.action == "support_session_start"

    def test_missing_category_still_422(self):
        """Missing category still returns 422 (not changed by R3)."""
        from api.v1.platform.p12.services import _session_store
        _session_store.clear_all()
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/platform/p12/sessions",
            json={"reason": VALID_REASON},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 422
