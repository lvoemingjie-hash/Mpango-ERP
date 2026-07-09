"""
Request-level tests for Platform Track — operational reporting endpoint.

Tests verify read-only stats API contract using dependency_overrides.

P11-C0: Stats endpoint now requires platform operator credentials.
Tests use X-Platform-Test-Override header in test environment.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta

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

# Ensure test environment for platform guard
os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")


def _make_stats_db():
    """Mock DB returning zero counts for all stats queries."""
    db = MagicMock()
    zero_result = MagicMock()
    zero_result.scalar.return_value = 0
    db.execute = AsyncMock(return_value=zero_result)
    return db


def _make_app(mock_db, auth: str = "platform_admin"):
    """
    Build app with dependency overrides for get_db.

    auth modes:
        "platform_admin" — identity-only super admin (passes RequirePlatformAdmin)
        "contextual"     — contextual token (rejected by RequirePlatformAdmin)
        "none"           — no auth context (rejected, 401)
    """
    app = FastAPI()
    from api.v1.platform.stats import router
    from api.dependencies import get_db, get_platform_db
    from database.session import get_db as db_get_db

    async def override():
        yield mock_db
    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_platform_db] = app.dependency_overrides[get_db]
    app.dependency_overrides[db_get_db] = override
    app.include_router(router)

    if auth == "platform_admin":
        _add_platform_admin_auth(app)
    elif auth == "contextual":
        _add_contextual_auth(app)
    # "none" — no middleware, no auth context

    return app


TEST_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}


def _stats_client():
    return TestClient(_make_app(_make_stats_db()))


# === Guard tests ===

class TestStatsEndpointGuard:

    def test_unauthenticated_denied(self):
        """Unauthenticated request to stats is denied (401)."""
        resp = _stats_client().get("/api/v1/platform/stats/")
        assert resp.status_code == 401

    def test_invalid_test_override_denied(self):
        """Invalid test override is denied (403)."""
        resp = _stats_client().get(
            "/api/v1/platform/stats/",
            headers={"X-Platform-Test-Override": "wrong-secret"},
        )
        assert resp.status_code == 403

    def test_valid_test_override_allowed(self):
        """Valid test override allows access (200)."""
        resp = _stats_client().get("/api/v1/platform/stats/", headers=TEST_HEADERS)
        assert resp.status_code == 200



class TestStatsEndpoint:

    def test_response_shape(self):
        """Response has all expected top-level keys."""
        resp = _stats_client().get("/api/v1/platform/stats/", headers=TEST_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "tenants" in data
        assert "provisioning" in data
        assert "audit" in data
        assert "generated_at" in data

    def test_tenant_keys(self):
        resp = _stats_client().get("/api/v1/platform/stats/", headers=TEST_HEADERS)
        data = resp.json()["tenants"]
        assert "total" in data
        assert "active" in data
        assert "suspended" in data
        assert "other" in data

    def test_provisioning_keys(self):
        resp = _stats_client().get("/api/v1/platform/stats/", headers=TEST_HEADERS)
        data = resp.json()["provisioning"]
        assert "complete" in data
        assert "pending" in data
        assert "failed" in data

    def test_audit_keys(self):
        resp = _stats_client().get("/api/v1/platform/stats/", headers=TEST_HEADERS)
        data = resp.json()["audit"]
        assert "total_entries" in data
        assert "last_24h" in data

    def test_empty_counts(self):
        """When no data, all counts should be 0."""
        resp = _stats_client().get("/api/v1/platform/stats/", headers=TEST_HEADERS)
        data = resp.json()
        assert data["tenants"]["total"] == 0
        assert data["tenants"]["active"] == 0
        assert data["provisioning"]["complete"] == 0
        assert data["audit"]["total_entries"] == 0

    def test_generated_at_is_iso(self):
        resp = _stats_client().get("/api/v1/platform/stats/", headers=TEST_HEADERS)
        generated = resp.json()["generated_at"]
        # Should be parseable ISO format
        datetime.fromisoformat(generated)


class TestStatsReadOnlyContract:

    def test_no_post(self):
        resp = _stats_client().post("/api/v1/platform/stats/", json={}, headers=TEST_HEADERS)
        assert resp.status_code == 405

    def test_no_put(self):
        resp = _stats_client().put("/api/v1/platform/stats/", json={}, headers=TEST_HEADERS)
        assert resp.status_code == 405

    def test_no_patch(self):
        resp = _stats_client().patch("/api/v1/platform/stats/", json={}, headers=TEST_HEADERS)
        assert resp.status_code == 405

    def test_no_delete(self):
        resp = _stats_client().delete("/api/v1/platform/stats/", headers=TEST_HEADERS)
        assert resp.status_code == 405
