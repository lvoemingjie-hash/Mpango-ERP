"""
Request-level API tests for Platform Track P0 — platform_audit_logs.

Uses synchronous TestClient with FastAPI dependency override for get_db.
Tests the external read-only API contract without real database.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_empty_list_result():
    """Mock result set: count=0, items=[]."""
    count_result = MagicMock()
    count_result.scalar.return_value = 0
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = []
    return [count_result, list_result]


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


def _list_client():
    """Client with mock returning empty list."""
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(side_effect=_make_empty_list_result())
    return TestClient(_make_app(mock_db))


# === List endpoint ===

class TestAuditListEndpoint:

    def test_empty_list(self):
        resp = _list_client().get("/api/v1/platform/audit/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_pagination_params(self):
        resp = _list_client().get("/api/v1/platform/audit/", params={"limit": 10, "offset": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 5

    def test_filter_by_action(self):
        resp = _list_client().get("/api/v1/platform/audit/", params={"action": "tenant.suspend"})
        assert resp.status_code == 200

    def test_filter_by_wholesaler_id(self):
        resp = _list_client().get("/api/v1/platform/audit/", params={"wholesaler_id": "00000000-0000-0000-0000-000000000000"})
        assert resp.status_code == 200

    def test_filter_by_actor_type(self):
        resp = _list_client().get("/api/v1/platform/audit/", params={"actor_type": "admin"})
        assert resp.status_code == 200

    def test_response_shape(self):
        resp = _list_client().get("/api/v1/platform/audit/")
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data


# === Detail endpoint ===

class TestAuditDetailEndpoint:

    def test_detail_404(self):
        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=_make_404_result())
        client = TestClient(_make_app(mock_db))
        resp = client.get("/api/v1/platform/audit/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# === Read-only contract ===

class TestReadOnlyContract:

    def test_no_post_on_list(self):
        resp = _list_client().post("/api/v1/platform/audit/", json={})
        assert resp.status_code == 405

    def test_no_post_on_detail(self):
        resp = _list_client().post("/api/v1/platform/audit/some-id", json={})
        assert resp.status_code == 405

    def test_no_put_on_list(self):
        resp = _list_client().put("/api/v1/platform/audit/", json={})
        assert resp.status_code == 405

    def test_no_put_on_detail(self):
        resp = _list_client().put("/api/v1/platform/audit/some-id", json={})
        assert resp.status_code == 405

    def test_no_patch_on_list(self):
        resp = _list_client().patch("/api/v1/platform/audit/", json={})
        assert resp.status_code == 405

    def test_no_patch_on_detail(self):
        resp = _list_client().patch("/api/v1/platform/audit/some-id", json={})
        assert resp.status_code == 405

    def test_no_delete_on_list(self):
        resp = _list_client().delete("/api/v1/platform/audit/")
        assert resp.status_code == 405

    def test_no_delete_on_detail(self):
        resp = _list_client().delete("/api/v1/platform/audit/some-id")
        assert resp.status_code == 405
