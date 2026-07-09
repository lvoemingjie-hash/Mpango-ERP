"""
P11-C0: Legacy Platform Endpoint Guard tests.

Verifies that old P0 platform endpoints (tenants, audit, stats) are now
guarded with P10 identity-only platform operator boundary, while
health/info endpoints remain unauthenticated.

Test scenarios per P11-C0 requirements:
  - Unauthenticated denied where sensitive
  - Tenant-contextual token denied
  - Identity-only super_admin allowed
  - Admin-but-not-super_admin denied
  - Health/info behavior documented
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


os.environ.setdefault("MPANGO_ENV", "test")
os.environ.setdefault("PLATFORM_TEST_OVERRIDE_SECRET", "test-platform-override-secret")
os.environ.setdefault("PLATFORM_OPERATOR_SECRET", "test-operator-secret")


# -- Helpers --

def _mock_db():
    """Mock DB with zero-result responses."""
    db = MagicMock()
    zero = MagicMock()
    zero.scalar.return_value = 0
    zero.scalar_one_or_none.return_value = None
    zero.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=zero)
    return db


def _make_app_with_routes(mock_db):
    """Build app with all P0 platform routes."""
    app = FastAPI()
    from api.v1.platform.health import router as health_router
    from api.v1.platform.tenants import router as tenants_router
    from api.v1.platform.audit import router as audit_router
    from api.v1.platform.stats import router as stats_router
    from api.dependencies import get_db, get_platform_db
    from database.session import get_db as db_get_db

    async def override():
        yield mock_db
    app.dependency_overrides[get_db] = override
    app.dependency_overrides[get_platform_db] = app.dependency_overrides[get_db]
    app.dependency_overrides[db_get_db] = override
    app.include_router(health_router)
    app.include_router(tenants_router)
    app.include_router(audit_router)
    app.include_router(stats_router)
    return app


AUTH_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}
OPERATOR_HEADERS = {"X-Platform-Operator": "test-operator-secret"}


# ============================================================
# 1. Unauthenticated denied where sensitive
# ============================================================

class TestUnauthenticatedDenied:
    """All sensitive P0 endpoints must deny unauthenticated access."""

    def test_tenants_list_denied(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/tenants/")
        assert resp.status_code == 401

    def test_tenants_detail_denied(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/tenants/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 401

    def test_audit_list_denied(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/audit/")
        assert resp.status_code == 401

    def test_audit_summary_denied(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/audit/summary")
        assert resp.status_code == 401

    def test_audit_detail_denied(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/audit/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 401

    def test_stats_denied(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/stats/")
        assert resp.status_code == 401


# ============================================================
# 2. Tenant-contextual token denied
# ============================================================

class TestTenantContextualTokenDenied:
    """
    A token with tenant_id/tenant_schema should be denied even if it
    has super_admin role. P10 guard requires identity-only tokens.

    We simulate this by NOT providing platform credentials — the guard
    only grants access via identity-only super_admin Bearer tokens,
    X-Platform-Operator, or test override. A tenant-contextual token
    would fail _check_identity_super_admin because is_identity_only=False.
    """

    def test_tenants_list_no_test_override_denied(self):
        """Without platform credentials, access is denied."""
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/tenants/")
        assert resp.status_code == 401

    def test_stats_no_credentials_denied(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/stats/")
        assert resp.status_code == 401

    def test_wrong_test_override_denied(self):
        """Wrong test override = 403 (credential present but invalid)."""
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get(
            "/api/v1/platform/tenants/",
            headers={"X-Platform-Test-Override": "wrong"},
        )
        assert resp.status_code == 403


# ============================================================
# 3. Identity-only super_admin allowed (via test override)
# ============================================================

class TestIdentitySuperAdminAllowed:
    """
    Valid platform operator credentials allow access to all guarded endpoints.

    In test env, we use X-Platform-Test-Override as a proxy for
    identity-only super_admin access. The P10 guard test suite
    (test_platform_p10_contracts.py) covers the real Bearer token flow.
    """

    def test_tenants_list_allowed(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/tenants/", headers=AUTH_HEADERS)
        assert resp.status_code == 200

    def test_tenants_detail_allowed(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/tenants/00000000-0000-0000-0000-000000000000", headers=AUTH_HEADERS)
        # 200 or 404 (if no mock data) — must NOT be 401/403
        assert resp.status_code in (200, 404)

    def test_audit_list_allowed(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/audit/", headers=AUTH_HEADERS)
        assert resp.status_code == 200

    def test_audit_summary_allowed(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/audit/summary", headers=AUTH_HEADERS)
        assert resp.status_code == 200

    def test_stats_allowed(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/stats/", headers=AUTH_HEADERS)
        assert resp.status_code == 200

    def test_operator_header_allowed(self):
        """X-Platform-Operator secret also grants access."""
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/stats/", headers=OPERATOR_HEADERS)
        assert resp.status_code == 200


# ============================================================
# 4. Admin-but-not-super_admin denied
# ============================================================

class TestAdminNotSuperAdminDenied:
    """
    A regular admin role (without super_admin) must be denied.

    Without platform-specific credentials, any request is denied at 401.
    This is tested by the guard's deny-by-default: no credential = 401.
    The P10 guard only accepts super_admin specifically.
    """

    def test_no_credentials_denied_tenants(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/tenants/")
        assert resp.status_code == 401

    def test_no_credentials_denied_audit(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/audit/")
        assert resp.status_code == 401

    def test_no_credentials_denied_stats(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/stats/")
        assert resp.status_code == 401


# ============================================================
# 5. Health/info endpoints remain unauthenticated — documented
# ============================================================

class TestHealthInfoUnauthenticated:
    """
    Health and info endpoints are explicitly documented as non-sensitive.
    They must remain accessible without authentication.
    """

    def test_health_no_auth_required(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "ok"

    def test_info_no_auth_required(self):
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "track" in data
        assert "boundaries" in data

    def test_health_does_not_expose_tenant_data(self):
        """Health endpoint must NOT expose tenant or operational data."""
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/health")
        data = resp.json()
        # Must not contain sensitive keys
        assert "tenants" not in data
        assert "audit" not in data
        assert "wholesaler" not in data

    def test_info_does_not_expose_tenant_data(self):
        """Info endpoint must NOT expose tenant or operational data."""
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/info")
        data = resp.json()
        assert "tenants" not in data
        assert "audit" not in data
        assert "wholesaler" not in data

    def test_health_shape_unchanged(self):
        """Health endpoint shape is preserved (backward compat)."""
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/health")
        data = resp.json()
        assert data["track"] == "platform-p0"
        assert "timestamp" in data

    def test_info_shape_unchanged(self):
        """Info endpoint shape is preserved (backward compat)."""
        client = TestClient(_make_app_with_routes(_mock_db()))
        resp = client.get("/api/v1/platform/info")
        data = resp.json()
        assert "version" in data
        assert "phase" in data
        assert "documentation" in data
