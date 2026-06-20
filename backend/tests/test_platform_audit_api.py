"""
Request-level API tests for Platform Track P0 — platform_audit_logs.

Tests the external read-only API contract including new time-range filtering
and summary endpoints.

S2-R3 alignment: Platform routes now require RequirePlatformAdmin (identity-only
super admin). Business semantics tests run with a mock platform-admin auth
context via middleware. Separate boundary tests verify 401/403 for
unauthenticated and non-platform-admin requests.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api.context.auth import AuthContext, attach_auth_context
from core.security import TokenPayload


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _platform_admin_token() -> TokenPayload:
    """Identity-only super admin token that passes RequirePlatformAdmin."""
    return TokenPayload(user_id="platform-admin-001", roles=["super_admin"])


def _contextual_admin_token() -> TokenPayload:
    """Contextual token (tenant selected) — fails RequirePlatformAdmin."""
    return TokenPayload(
        user_id="tenant-admin-001",
        tenant_id="00000000-0000-0000-0000-000000000001",
        tenant_schema="t_dev",
        roles=["super_admin"],
    )


def _add_platform_admin_auth(app: FastAPI) -> None:
    """Add middleware that attaches identity-only super admin auth context."""
    @app.middleware("http")
    async def _attach_admin_auth(request: Request, call_next):
        token = _platform_admin_token()
        attach_auth_context(request, AuthContext(token=token, raw_token="test"))
        return await call_next(request)


def _add_contextual_auth(app: FastAPI) -> None:
    """Add middleware that attaches contextual (tenant) auth context."""
    @app.middleware("http")
    async def _attach_ctx_auth(request: Request, call_next):
        token = _contextual_admin_token()
        attach_auth_context(request, AuthContext(token=token, raw_token="test"))
        return await call_next(request)


# ---------------------------------------------------------------------------
# DB + App helpers
# ---------------------------------------------------------------------------

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


def _make_app(mock_db, auth: str = "platform_admin"):
    """
    Build app with dependency overrides for get_db.

    auth modes:
        "platform_admin" — identity-only super admin (passes RequirePlatformAdmin)
        "contextual"     — contextual token (rejected by RequirePlatformAdmin)
        "none"           — no auth context (rejected, 401)
    """
    app = FastAPI()
    from api.v1.platform.audit import router
    from api.dependencies import get_db
    from database.session import get_db as db_get_db

    async def override():
        yield mock_db
    app.dependency_overrides[get_db] = override
    app.dependency_overrides[db_get_db] = override
    app.include_router(router)

    if auth == "platform_admin":
        _add_platform_admin_auth(app)
    elif auth == "contextual":
        _add_contextual_auth(app)

    return app


def _list_client(auth: str = "platform_admin"):
    """Client with mock returning empty list."""
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(side_effect=_make_empty_list_result())
    return TestClient(_make_app(mock_db, auth=auth))


# ===========================================================================
# Boundary tests: auth required
# ===========================================================================

class TestAuditAuthBoundary:

    def test_unauthenticated_list_rejected(self):
        """No auth context on list endpoint -> 401."""
        client = _list_client(auth="none")
        resp = client.get("/api/v1/platform/audit/")
        assert resp.status_code == 401

    def test_contextual_admin_list_rejected(self):
        """Contextual token on list endpoint -> 403."""
        client = _list_client(auth="contextual")
        resp = client.get("/api/v1/platform/audit/")
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "PLATFORM_ADMIN_REQUIRED"

    def test_unauthenticated_summary_rejected(self):
        """No auth context on summary endpoint -> 401."""
        client = _list_client(auth="none")
        resp = client.get("/api/v1/platform/audit/summary")
        assert resp.status_code == 401

    def test_unauthenticated_detail_rejected(self):
        """No auth context on detail endpoint -> 401."""
        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=_make_404_result())
        client = TestClient(_make_app(mock_db, auth="none"))
        resp = client.get("/api/v1/platform/audit/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 401


# ===========================================================================
# Business semantics tests (run with platform admin auth)
# ===========================================================================

# === List endpoint with time-range ===

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
        assert "since" in data
        assert "before" in data


class TestAuditTimeRangeFiltering:

    def test_since_param(self):
        resp = _list_client().get("/api/v1/platform/audit/?since=2026-04-01T00:00:00Z")
        assert resp.status_code == 200

    def test_before_param(self):
        resp = _list_client().get("/api/v1/platform/audit/?before=2026-04-14T00:00:00Z")
        assert resp.status_code == 200

    def test_since_and_before_params(self):
        resp = _list_client().get("/api/v1/platform/audit/?since=2026-04-01T00:00:00Z&before=2026-04-14T00:00:00Z")
        assert resp.status_code == 200

    def test_invalid_since_format(self):
        resp = _list_client().get("/api/v1/platform/audit/?since=invalid")
        assert resp.status_code == 400
        assert "since" in resp.json()["detail"].lower()

    def test_invalid_before_format(self):
        resp = _list_client().get("/api/v1/platform/audit/?before=invalid")
        assert resp.status_code == 400
        assert "before" in resp.json()["detail"].lower()

    def test_since_after_before(self):
        resp = _list_client().get("/api/v1/platform/audit/?since=2026-04-14T00:00:00Z&before=2026-04-01T00:00:00Z")
        assert resp.status_code == 400
        assert "earlier" in resp.json()["detail"].lower()

    def test_range_exceeds_max(self):
        # 91 days exceeds 90-day max
        resp = _list_client().get("/api/v1/platform/audit/?since=2026-01-01T00:00:00Z&before=2026-04-14T00:00:00Z")
        assert resp.status_code == 400
        assert "90" in resp.json()["detail"]


# === Summary endpoint ===

class TestAuditSummaryEndpoint:

    def test_summary_empty(self):
        resp = _list_client().get("/api/v1/platform/audit/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "period" in data
        assert "action_counts" in data
        assert "total" in data
        assert data["total"] == 0
        assert data["action_counts"] == {}

    def test_summary_with_time_range(self):
        resp = _list_client().get("/api/v1/platform/audit/summary?since=2026-04-01T00:00:00Z&before=2026-04-14T00:00:00Z")
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"]["since"] is not None
        assert data["period"]["before"] is not None

    def test_summary_invalid_since(self):
        resp = _list_client().get("/api/v1/platform/audit/summary?since=bad")
        assert resp.status_code == 400

    def test_summary_invalid_range(self):
        resp = _list_client().get("/api/v1/platform/audit/summary?since=2026-04-14T00:00:00Z&before=2026-04-01T00:00:00Z")
        assert resp.status_code == 400

    def test_summary_range_exceeds_max(self):
        resp = _list_client().get("/api/v1/platform/audit/summary?since=2026-01-01T00:00:00Z&before=2026-04-14T00:00:00Z")
        assert resp.status_code == 400


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

    def test_no_post_on_summary(self):
        resp = _list_client().post("/api/v1/platform/audit/summary", json={})
        assert resp.status_code == 405

    def test_no_post_on_detail(self):
        resp = _list_client().post("/api/v1/platform/audit/some-id", json={})
        assert resp.status_code == 405

    def test_no_put_on_list(self):
        resp = _list_client().put("/api/v1/platform/audit/", json={})
        assert resp.status_code == 405

    def test_no_put_on_summary(self):
        resp = _list_client().put("/api/v1/platform/audit/summary", json={})
        assert resp.status_code == 405

    def test_no_put_on_detail(self):
        resp = _list_client().put("/api/v1/platform/audit/some-id", json={})
        assert resp.status_code == 405

    def test_no_patch_on_list(self):
        resp = _list_client().patch("/api/v1/platform/audit/", json={})
        assert resp.status_code == 405

    def test_no_patch_on_summary(self):
        resp = _list_client().patch("/api/v1/platform/audit/summary", json={})
        assert resp.status_code == 405

    def test_no_patch_on_detail(self):
        resp = _list_client().patch("/api/v1/platform/audit/some-id", json={})
        assert resp.status_code == 405

    def test_no_delete_on_list(self):
        resp = _list_client().delete("/api/v1/platform/audit/")
        assert resp.status_code == 405

    def test_no_delete_on_summary(self):
        resp = _list_client().delete("/api/v1/platform/audit/summary")
        assert resp.status_code == 405

    def test_no_delete_on_detail(self):
        resp = _list_client().delete("/api/v1/platform/audit/some-id")
        assert resp.status_code == 405
