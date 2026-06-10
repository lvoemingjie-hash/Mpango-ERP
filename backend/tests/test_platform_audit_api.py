"""
Request-level API tests for Platform Track P0 — platform_audit_logs.

Tests the external read-only API contract including new time-range filtering
and summary endpoints.

P11-C0: All P0 audit endpoints now require platform operator credentials.
Tests use X-Platform-Test-Override header in test environment.
"""
import os
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


# Ensure test environment for platform guard
os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")


def _make_empty_list_result():
    """Mock result set: count=0, items=[], summary=empty."""
    count_result = MagicMock()
    count_result.scalar.return_value = 0
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = []
    # For summary endpoint
    summary_result = MagicMock()
    summary_result.all.return_value = []
    return [count_result, list_result, summary_result]


def _make_404_result():
    """Mock result set: scalar_one_or_none returns None."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    return result


def _make_app(mock_db):
    """Build app with dependency overrides for get_db."""
    app = FastAPI()
    from api.v1.platform.audit import router
    from api.dependencies import get_db
    from database.session import get_db as db_get_db

    async def override():
        yield mock_db
    app.dependency_overrides[get_db] = override
    app.dependency_overrides[db_get_db] = override
    app.include_router(router)
    return app


TEST_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}


def _list_client():
    """Client with mock returning empty list."""
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(side_effect=_make_empty_list_result())
    return TestClient(_make_app(mock_db))


# === Guard tests ===

class TestAuditEndpointGuard:

    def test_unauthenticated_denied_list(self):
        """Unauthenticated request to audit list is denied (401)."""
        resp = _list_client().get("/api/v1/platform/audit/")
        assert resp.status_code == 401

    def test_unauthenticated_denied_summary(self):
        """Unauthenticated request to audit summary is denied (401)."""
        resp = _list_client().get("/api/v1/platform/audit/summary")
        assert resp.status_code == 401

    def test_unauthenticated_denied_detail(self):
        """Unauthenticated request to audit detail is denied (401)."""
        resp = _list_client().get("/api/v1/platform/audit/some-id")
        assert resp.status_code == 401

    def test_invalid_test_override_denied(self):
        """Invalid test override is denied (403)."""
        resp = _list_client().get(
            "/api/v1/platform/audit/",
            headers={"X-Platform-Test-Override": "wrong-secret"},
        )
        assert resp.status_code == 403

    def test_valid_test_override_allowed(self):
        """Valid test override allows access (200)."""
        resp = _list_client().get(
            "/api/v1/platform/audit/",
            headers=TEST_HEADERS,
        )
        assert resp.status_code == 200


# === List endpoint with time-range ===

class TestAuditListEndpoint:

    def test_empty_list(self):
        resp = _list_client().get("/api/v1/platform/audit/", headers=TEST_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_pagination_params(self):
        resp = _list_client().get("/api/v1/platform/audit/", params={"limit": 10, "offset": 5}, headers=TEST_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 5

    def test_filter_by_action(self):
        resp = _list_client().get("/api/v1/platform/audit/", params={"action": "tenant.suspend"}, headers=TEST_HEADERS)
        assert resp.status_code == 200

    def test_filter_by_wholesaler_id(self):
        resp = _list_client().get("/api/v1/platform/audit/", params={"wholesaler_id": "00000000-0000-0000-0000-000000000000"}, headers=TEST_HEADERS)
        assert resp.status_code == 200

    def test_filter_by_actor_type(self):
        resp = _list_client().get("/api/v1/platform/audit/", params={"actor_type": "admin"}, headers=TEST_HEADERS)
        assert resp.status_code == 200

    def test_response_shape(self):
        resp = _list_client().get("/api/v1/platform/audit/", headers=TEST_HEADERS)
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "since" in data
        assert "before" in data


class TestAuditTimeRangeFiltering:

    def test_since_param(self):
        resp = _list_client().get("/api/v1/platform/audit/?since=2026-04-01T00:00:00Z", headers=TEST_HEADERS)
        assert resp.status_code == 200

    def test_before_param(self):
        resp = _list_client().get("/api/v1/platform/audit/?before=2026-04-14T00:00:00Z", headers=TEST_HEADERS)
        assert resp.status_code == 200

    def test_since_and_before_params(self):
        resp = _list_client().get("/api/v1/platform/audit/?since=2026-04-01T00:00:00Z&before=2026-04-14T00:00:00Z", headers=TEST_HEADERS)
        assert resp.status_code == 200

    def test_invalid_since_format(self):
        resp = _list_client().get("/api/v1/platform/audit/?since=invalid", headers=TEST_HEADERS)
        assert resp.status_code == 400
        assert "since" in resp.json()["detail"].lower()

    def test_invalid_before_format(self):
        resp = _list_client().get("/api/v1/platform/audit/?before=invalid", headers=TEST_HEADERS)
        assert resp.status_code == 400
        assert "before" in resp.json()["detail"].lower()

    def test_since_after_before(self):
        resp = _list_client().get("/api/v1/platform/audit/?since=2026-04-14T00:00:00Z&before=2026-04-01T00:00:00Z", headers=TEST_HEADERS)
        assert resp.status_code == 400
        assert "earlier" in resp.json()["detail"].lower()

    def test_range_exceeds_max(self):
        # 91 days exceeds 90-day max
        resp = _list_client().get("/api/v1/platform/audit/?since=2026-01-01T00:00:00Z&before=2026-04-14T00:00:00Z", headers=TEST_HEADERS)
        assert resp.status_code == 400
        assert "90" in resp.json()["detail"]


# === Summary endpoint ===

class TestAuditSummaryEndpoint:

    def test_summary_empty(self):
        resp = _list_client().get("/api/v1/platform/audit/summary", headers=TEST_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "period" in data
        assert "action_counts" in data
        assert "total" in data
        assert data["total"] == 0
        assert data["action_counts"] == {}

    def test_summary_with_time_range(self):
        resp = _list_client().get("/api/v1/platform/audit/summary?since=2026-04-01T00:00:00Z&before=2026-04-14T00:00:00Z", headers=TEST_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"]["since"] is not None
        assert data["period"]["before"] is not None

    def test_summary_invalid_since(self):
        resp = _list_client().get("/api/v1/platform/audit/summary?since=bad", headers=TEST_HEADERS)
        assert resp.status_code == 400

    def test_summary_invalid_range(self):
        resp = _list_client().get("/api/v1/platform/audit/summary?since=2026-04-14T00:00:00Z&before=2026-04-01T00:00:00Z", headers=TEST_HEADERS)
        assert resp.status_code == 400

    def test_summary_range_exceeds_max(self):
        resp = _list_client().get("/api/v1/platform/audit/summary?since=2026-01-01T00:00:00Z&before=2026-04-14T00:00:00Z", headers=TEST_HEADERS)
        assert resp.status_code == 400


# === Detail endpoint ===

class TestAuditDetailEndpoint:

    def test_detail_404(self):
        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=_make_404_result())
        client = TestClient(_make_app(mock_db))
        resp = client.get("/api/v1/platform/audit/00000000-0000-0000-0000-000000000000", headers=TEST_HEADERS)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# === Metadata redaction (P11-R1.3) ===

def _make_entry_with_metadata(metadata: dict):
    """Build a mock PlatformAuditLog entry with given metadata."""
    from uuid import uuid4
    entry = MagicMock()
    entry.id = uuid4()
    entry.actor_type = "admin"
    entry.actor_id = uuid4()
    entry.wholesaler_id = uuid4()
    entry.action = "tenant.update"
    entry.resource = "tenant"
    entry.audit_metadata = metadata
    entry.created_at = datetime.now(timezone.utc)
    return entry


class TestAuditMetadataRedaction:

    def test_list_redacts_password_key(self):
        """List endpoint: password key is removed from audit_metadata."""
        entry = _make_entry_with_metadata({
            "password": "hunter2",
            "safe_key": "visible",
        })
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [entry]

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[count_result, list_result])
        client = TestClient(_make_app(mock_db))

        resp = client.get("/api/v1/platform/audit/", headers=TEST_HEADERS)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        meta = items[0]["audit_metadata"]
        assert "password" not in meta
        assert meta["safe_key"] == "visible"

    def test_list_redacts_token_key(self):
        """List endpoint: token key is removed from audit_metadata."""
        entry = _make_entry_with_metadata({
            "token": "secret-jwt-value",
            "result": "completed",
        })
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [entry]

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[count_result, list_result])
        client = TestClient(_make_app(mock_db))

        resp = client.get("/api/v1/platform/audit/", headers=TEST_HEADERS)
        assert resp.status_code == 200
        meta = resp.json()["items"][0]["audit_metadata"]
        assert "token" not in meta
        assert meta["result"] == "completed"

    def test_list_redacts_nested_sensitive_keys(self):
        """List endpoint: sensitive keys in nested dicts are removed."""
        entry = _make_entry_with_metadata({
            "context": {
                "authorization": "Bearer abc",
                "detail": "some info",
            },
        })
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [entry]

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[count_result, list_result])
        client = TestClient(_make_app(mock_db))

        resp = client.get("/api/v1/platform/audit/", headers=TEST_HEADERS)
        assert resp.status_code == 200
        meta = resp.json()["items"][0]["audit_metadata"]
        assert "authorization" not in meta["context"]
        assert meta["context"]["detail"] == "some info"

    def test_detail_redacts_secret_key(self):
        """Detail endpoint: secret key is removed from audit_metadata."""
        entry = _make_entry_with_metadata({
            "secret": "api-key-123",
            "action_taken": "suspend",
        })
        detail_result = MagicMock()
        detail_result.scalar_one_or_none.return_value = entry

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=detail_result)
        client = TestClient(_make_app(mock_db))

        resp = client.get(f"/api/v1/platform/audit/{entry.id}", headers=TEST_HEADERS)
        assert resp.status_code == 200
        meta = resp.json()["audit_metadata"]
        assert "secret" not in meta
        assert meta["action_taken"] == "suspend"

    def test_detail_redacts_cookie_and_card_keys(self):
        """Detail endpoint: cookie and card keys are both removed."""
        entry = _make_entry_with_metadata({
            "cookie": "session=abc123",
            "card": "4111111111111111",
            "user_email": "test@example.com",
        })
        detail_result = MagicMock()
        detail_result.scalar_one_or_none.return_value = entry

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=detail_result)
        client = TestClient(_make_app(mock_db))

        resp = client.get(f"/api/v1/platform/audit/{entry.id}", headers=TEST_HEADERS)
        assert resp.status_code == 200
        meta = resp.json()["audit_metadata"]
        assert "cookie" not in meta
        assert "card" not in meta
        assert meta["user_email"] == "test@example.com"

    def test_list_redacts_payment_key(self):
        """List endpoint: payment key is removed."""
        entry = _make_entry_with_metadata({
            "payment": {"amount": 100, "ref": "PAY-001"},
            "order_id": "ORD-001",
        })
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [entry]

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(side_effect=[count_result, list_result])
        client = TestClient(_make_app(mock_db))

        resp = client.get("/api/v1/platform/audit/", headers=TEST_HEADERS)
        assert resp.status_code == 200
        meta = resp.json()["items"][0]["audit_metadata"]
        assert "payment" not in meta
        assert meta["order_id"] == "ORD-001"

    def test_detail_handles_null_metadata(self):
        """Detail endpoint: null metadata returns None (not an error)."""
        entry = _make_entry_with_metadata(None)
        entry.audit_metadata = None
        detail_result = MagicMock()
        detail_result.scalar_one_or_none.return_value = entry

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=detail_result)
        client = TestClient(_make_app(mock_db))

        resp = client.get(f"/api/v1/platform/audit/{entry.id}", headers=TEST_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["audit_metadata"] is None


# === Read-only contract ===

class TestReadOnlyContract:

    def test_no_post_on_list(self):
        resp = _list_client().post("/api/v1/platform/audit/", json={}, headers=TEST_HEADERS)
        assert resp.status_code == 405

    def test_no_post_on_summary(self):
        resp = _list_client().post("/api/v1/platform/audit/summary", json={}, headers=TEST_HEADERS)
        assert resp.status_code == 405

    def test_no_post_on_detail(self):
        resp = _list_client().post("/api/v1/platform/audit/some-id", json={}, headers=TEST_HEADERS)
        assert resp.status_code == 405

    def test_no_put_on_list(self):
        resp = _list_client().put("/api/v1/platform/audit/", json={}, headers=TEST_HEADERS)
        assert resp.status_code == 405

    def test_no_put_on_summary(self):
        resp = _list_client().put("/api/v1/platform/audit/summary", json={}, headers=TEST_HEADERS)
        assert resp.status_code == 405

    def test_no_put_on_detail(self):
        resp = _list_client().put("/api/v1/platform/audit/some-id", json={}, headers=TEST_HEADERS)
        assert resp.status_code == 405

    def test_no_patch_on_list(self):
        resp = _list_client().patch("/api/v1/platform/audit/", json={}, headers=TEST_HEADERS)
        assert resp.status_code == 405

    def test_no_patch_on_summary(self):
        resp = _list_client().patch("/api/v1/platform/audit/summary", json={}, headers=TEST_HEADERS)
        assert resp.status_code == 405

    def test_no_patch_on_detail(self):
        resp = _list_client().patch("/api/v1/platform/audit/some-id", json={}, headers=TEST_HEADERS)
        assert resp.status_code == 405

    def test_no_delete_on_list(self):
        resp = _list_client().delete("/api/v1/platform/audit/", headers=TEST_HEADERS)
        assert resp.status_code == 405

    def test_no_delete_on_summary(self):
        resp = _list_client().delete("/api/v1/platform/audit/summary", headers=TEST_HEADERS)
        assert resp.status_code == 405

    def test_no_delete_on_detail(self):
        resp = _list_client().delete("/api/v1/platform/audit/some-id", headers=TEST_HEADERS)
        assert resp.status_code == 405
