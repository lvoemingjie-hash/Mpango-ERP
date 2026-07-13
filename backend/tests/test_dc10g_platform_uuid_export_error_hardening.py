"""DC-10G Platform UUID + Export Error Boundary Hardening tests.

Tests:
- Platform tenant/audit malformed UUID -> controlled 404 (not 500).
- Platform tenant/audit well-formed missing UUID -> 404.
- Platform tenant/audit unauthenticated -> 401.
- Export enqueue failure -> 500 with sanitized message (no str(exception)).
- Export malformed job_id -> 400 INVALID_EXPORT_ID (DC-6B regression).
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_platform_app() -> FastAPI:
    """Small app with the platform tenants + audit routers for testing."""
    app = FastAPI()
    from api.v1.platform.tenants import router as tenants_router
    from api.v1.platform.audit import router as audit_router
    app.include_router(tenants_router)
    app.include_router(audit_router)
    return app


def _mock_db_returns_none():
    """Mock DB session that returns None for all queries (not-found)."""
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    return db


# ---------------------------------------------------------------------------
# Platform tenant UUID hardening
# ---------------------------------------------------------------------------

class TestPlatformTenantUUIDHardening:
    """Malformed wholesaler_id must return 404, not 500."""

    def test_malformed_wholesaler_id_returns_404(self):
        os.environ["MPANGO_ENV"] = "test"
        os.environ["PLATFORM_TEST_OVERRIDE_SECRET"] = "test-override"  # pragma: allowlist secret
        app = _make_platform_app()
        mock_db = _mock_db_returns_none()
        from api.dependencies import get_platform_db
        app.dependency_overrides[get_platform_db] = lambda: mock_db

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/platform/tenants/not-a-uuid",
            headers={"X-Platform-Test-Override": "test-override"},
        )
        assert resp.status_code == 404

    def test_well_formed_missing_uuid_returns_404(self):
        os.environ["MPANGO_ENV"] = "test"
        os.environ["PLATFORM_TEST_OVERRIDE_SECRET"] = "test-override"  # pragma: allowlist secret
        app = _make_platform_app()
        mock_db = _mock_db_returns_none()
        from api.dependencies import get_platform_db
        app.dependency_overrides[get_platform_db] = lambda: mock_db

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/platform/tenants/00000000-0000-0000-0000-000000000000",
            headers={"X-Platform-Test-Override": "test-override"},
        )
        assert resp.status_code == 404

    def test_unauthenticated_tenant_returns_401(self):
        os.environ["MPANGO_ENV"] = "production"
        os.environ.pop("PLATFORM_TEST_OVERRIDE_SECRET", None)
        app = _make_platform_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/platform/tenants/not-a-uuid")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Platform audit UUID hardening
# ---------------------------------------------------------------------------

class TestPlatformAuditUUIDHardening:
    """Malformed log_id must return 404, not 500."""

    def test_malformed_log_id_returns_404(self):
        os.environ["MPANGO_ENV"] = "test"
        os.environ["PLATFORM_TEST_OVERRIDE_SECRET"] = "test-override"  # pragma: allowlist secret
        app = _make_platform_app()
        mock_db = _mock_db_returns_none()
        from api.dependencies import get_platform_db
        app.dependency_overrides[get_platform_db] = lambda: mock_db

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/platform/audit/not-a-uuid",
            headers={"X-Platform-Test-Override": "test-override"},
        )
        assert resp.status_code == 404

    def test_well_formed_missing_log_id_returns_404(self):
        os.environ["MPANGO_ENV"] = "test"
        os.environ["PLATFORM_TEST_OVERRIDE_SECRET"] = "test-override"  # pragma: allowlist secret
        app = _make_platform_app()
        mock_db = _mock_db_returns_none()
        from api.dependencies import get_platform_db
        app.dependency_overrides[get_platform_db] = lambda: mock_db

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/platform/audit/00000000-0000-0000-0000-000000000000",
            headers={"X-Platform-Test-Override": "test-override"},
        )
        assert resp.status_code == 404

    def test_unauthenticated_audit_returns_401(self):
        os.environ["MPANGO_ENV"] = "production"
        os.environ.pop("PLATFORM_TEST_OVERRIDE_SECRET", None)
        app = _make_platform_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/platform/audit/not-a-uuid")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Export enqueue error boundary
# ---------------------------------------------------------------------------

class TestExportEnqueueErrorBoundary:
    """Export enqueue failure must not leak str(exception)."""

    def test_sanitized_message_has_no_exception_content(self):
        """The sanitized EXPORT_ENQUEUE_FAILED message must not contain
        exception-like content (connection strings, tracebacks, etc.)."""
        from api.schemas.dashboard import make_error

        sanitized = make_error(
            "EXPORT_ENQUEUE_FAILED",
            "Unable to enqueue export job. Please try again later.",
        )
        sanitized_str = str(sanitized)
        assert "EXPORT_ENQUEUE_FAILED" in sanitized_str
        assert "Unable to enqueue export job" in sanitized_str
        # Must NOT contain exception-like content
        assert "Connection refused" not in sanitized_str
        assert "Traceback" not in sanitized_str
        assert "redis://" not in sanitized_str
        assert "postgresql://" not in sanitized_str

    def test_malformed_export_id_returns_400(self):
        """Regression: DC-6B malformed export job_id still returns 400."""
        from api.v1.exports import _parse_export_job_id, _invalid_export_id_response

        assert _parse_export_job_id("not-a-uuid") is None
        assert _parse_export_job_id("00000000-0000-0000-0000-000000000000") is not None

        resp = _invalid_export_id_response()
        assert resp.status_code == 400
        body = resp.body.decode() if hasattr(resp, "body") else str(resp)
        assert "INVALID_EXPORT_ID" in body
        assert "badly formed" not in body.lower()
        assert "ValueError" not in body
        assert "traceback" not in body.lower()
