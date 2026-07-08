"""
P13 Operations Observability Cockpit API tests.

Contract-backed tests covering:
  - Response shapes (all P13 schemas)
  - source_status semantics (available + int OK; unavailable + null OK; unavailable + 0 rejected)
  - Permission enforcement (identity-only super_admin, tenant-contextual denied, non-super_admin denied)
  - Redaction (no raw request/response bodies, no secrets/tokens, no DB host/port, no queue payloads)
  - Audit events (ops views write audit, access denied writes audit)
  - Counterexamples (unknown != healthy, null != 0, no raw payloads)
  - Route-level identity (guard active on all endpoints)
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


# -- Helpers --

AUTH_HEADERS = {"X-Platform-Test-Override": "test-platform-override-secret"}
OPERATOR_HEADERS = {"X-Platform-Operator": "test-operator-secret"}

P13_BASE = "/api/v1/platform/p13"


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


def _make_app(mock_db):
    """Build test app with P13 routes and mocked DB."""
    from api.v1.platform.p13.routes import router
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
    """P13-A-R1 contract schema validation."""

    def test_error_rate_summary_source_status_unavailable(self):
        """ErrorRateSummary accepts source_status='unavailable' with null total."""
        from api.v1.platform.p13.schemas import ErrorRateSummary
        summary = ErrorRateSummary(
            source_status="unavailable",
            window_minutes=15,
            total_errors=None,
            error_classes=[],
            top_routes=[],
            top_tenants=None,
            generated_at=datetime.now(timezone.utc),
        )
        assert summary.source_status == "unavailable"
        assert summary.total_errors is None

    def test_error_rate_summary_source_status_available(self):
        """ErrorRateSummary accepts source_status='available' with integer total."""
        from api.v1.platform.p13.schemas import ErrorRateSummary
        summary = ErrorRateSummary(
            source_status="available",
            window_minutes=15,
            total_errors=42,
            error_classes=[],
            top_routes=[],
            top_tenants=None,
            generated_at=datetime.now(timezone.utc),
        )
        assert summary.total_errors == 42

    def test_error_rate_summary_rejects_extra_fields(self):
        """ErrorRateSummary rejects unknown fields."""
        from api.v1.platform.p13.schemas import ErrorRateSummary
        with pytest.raises(Exception):
            ErrorRateSummary(
                source_status="unavailable",
                window_minutes=15,
                total_errors=None,
                generated_at=datetime.now(timezone.utc),
                unexpected_field="bad",
            )

    def test_slow_route_summary_source_status_unavailable(self):
        """SlowRouteSummary accepts source_status='unavailable' with null total."""
        from api.v1.platform.p13.schemas import SlowRouteSummary
        summary = SlowRouteSummary(
            source_status="unavailable",
            window_minutes=15,
            threshold_ms=1000,
            total_slow_requests=None,
            routes=[],
            generated_at=datetime.now(timezone.utc),
        )
        assert summary.total_slow_requests is None

    def test_slow_route_summary_source_status_available(self):
        """SlowRouteSummary accepts source_status='available' with integer total."""
        from api.v1.platform.p13.schemas import SlowRouteSummary
        summary = SlowRouteSummary(
            source_status="available",
            window_minutes=15,
            threshold_ms=1000,
            total_slow_requests=5,
            routes=[],
            generated_at=datetime.now(timezone.utc),
        )
        assert summary.total_slow_requests == 5

    def test_noisy_neighbor_impact_score_range(self):
        """NoisyNeighborEntry rejects impact_score outside 0.0-1.0."""
        from api.v1.platform.p13.schemas import NoisyNeighborEntry
        with pytest.raises(Exception):
            NoisyNeighborEntry(
                tenant_id="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
                error_count=10,
                slow_route_count=3,
                impact_score=2.5,
            )

    def test_resource_health_summary_database_required(self):
        """ResourceHealthSummary requires database field."""
        from api.v1.platform.p13.schemas import ResourceHealthSummary, DatabaseHealth
        db_health = DatabaseHealth(status="unknown")
        summary = ResourceHealthSummary(
            database=db_health,
            generated_at=datetime.now(timezone.utc),
        )
        assert summary.database.status == "unknown"
        assert summary.queue is None
        assert summary.memory is None

    def test_component_health_usage_percent_range(self):
        """ComponentHealth rejects usage_percent > 100.0."""
        from api.v1.platform.p13.schemas import ComponentHealth
        with pytest.raises(Exception):
            ComponentHealth(status="healthy", usage_percent=150.0)

    def test_error_class_breakdown_max_correlation_ids(self):
        """ErrorClassBreakdown enforces max 5 correlation IDs."""
        from api.v1.platform.p13.schemas import ErrorClassBreakdown
        with pytest.raises(Exception):
            ErrorClassBreakdown(
                error_class="TestError",
                count=10,
                percentage=50.0,
                sample_correlation_ids=["id1", "id2", "id3", "id4", "id5", "id6"],
            )

    def test_error_rate_summary_available_rejects_null(self):
        """ErrorRateSummary rejects source_status='available' with total_errors=None."""
        from api.v1.platform.p13.schemas import ErrorRateSummary
        with pytest.raises(Exception, match="total_errors must be an integer"):
            ErrorRateSummary(
                source_status="available",
                window_minutes=15,
                total_errors=None,
                error_classes=[],
                top_routes=[],
                top_tenants=None,
                generated_at=datetime.now(timezone.utc),
            )

    def test_error_rate_summary_unavailable_rejects_int(self):
        """ErrorRateSummary rejects source_status='unavailable' with total_errors=0."""
        from api.v1.platform.p13.schemas import ErrorRateSummary
        with pytest.raises(Exception, match="total_errors must be None"):
            ErrorRateSummary(
                source_status="unavailable",
                window_minutes=15,
                total_errors=0,
                error_classes=[],
                top_routes=[],
                top_tenants=None,
                generated_at=datetime.now(timezone.utc),
            )

    def test_slow_route_summary_available_rejects_null(self):
        """SlowRouteSummary rejects source_status='available' with total_slow_requests=None."""
        from api.v1.platform.p13.schemas import SlowRouteSummary
        with pytest.raises(Exception, match="total_slow_requests must be an integer"):
            SlowRouteSummary(
                source_status="available",
                window_minutes=15,
                threshold_ms=1000,
                total_slow_requests=None,
                routes=[],
                generated_at=datetime.now(timezone.utc),
            )

    def test_slow_route_summary_unavailable_rejects_int(self):
        """SlowRouteSummary rejects source_status='unavailable' with total_slow_requests=0."""
        from api.v1.platform.p13.schemas import SlowRouteSummary
        with pytest.raises(Exception, match="total_slow_requests must be None"):
            SlowRouteSummary(
                source_status="unavailable",
                window_minutes=15,
                threshold_ms=1000,
                total_slow_requests=0,
                routes=[],
                generated_at=datetime.now(timezone.utc),
            )

    def test_error_rate_summary_unknown_rejects_int(self):
        """ErrorRateSummary rejects source_status='unknown' with total_errors=5."""
        from api.v1.platform.p13.schemas import ErrorRateSummary
        with pytest.raises(Exception, match="total_errors must be None"):
            ErrorRateSummary(
                source_status="unknown",
                window_minutes=15,
                total_errors=5,
                error_classes=[],
                top_routes=[],
                top_tenants=None,
                generated_at=datetime.now(timezone.utc),
            )

    def test_slow_route_summary_unknown_rejects_int(self):
        """SlowRouteSummary rejects source_status='unknown' with total_slow_requests=3."""
        from api.v1.platform.p13.schemas import SlowRouteSummary
        with pytest.raises(Exception, match="total_slow_requests must be None"):
            SlowRouteSummary(
                source_status="unknown",
                window_minutes=15,
                threshold_ms=1000,
                total_slow_requests=3,
                routes=[],
                generated_at=datetime.now(timezone.utc),
            )


# ============================================================
# 2. Response Shape Tests
# ============================================================


class TestResponseShapes:
    """Verify P13 endpoints return correct response shapes."""

    def test_ops_health_returns_system_health(self):
        """GET /ops/health returns P10 SystemHealth shape."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/health", headers=AUTH_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "overall_status" in data
        assert "generated_at" in data

    def test_ops_errors_returns_error_rate_summary(self):
        """GET /ops/errors returns ErrorRateSummary shape."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/errors", headers=AUTH_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "source_status" in data
        assert "window_minutes" in data
        assert "total_errors" in data
        assert "error_classes" in data
        assert "top_routes" in data
        assert "generated_at" in data

    def test_ops_slow_routes_returns_slow_route_summary(self):
        """GET /ops/slow-routes returns SlowRouteSummary shape."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/slow-routes", headers=AUTH_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "source_status" in data
        assert "window_minutes" in data
        assert "threshold_ms" in data
        assert "total_slow_requests" in data
        assert "routes" in data
        assert "generated_at" in data

    def test_ops_resources_returns_resource_health(self):
        """GET /ops/resources returns ResourceHealthSummary shape."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/resources", headers=AUTH_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "database" in data
        assert "generated_at" in data
        # P14: database health is now a REAL measured signal, not fabricated 'unknown'.
        assert data["database"]["status"] in ("healthy", "degraded", "unhealthy")
        assert data["database"]["latency_ms"] is not None

    def test_ops_noisy_neighbors_returns_noisy_neighbor_summary(self):
        """GET /ops/noisy-neighbors returns NoisyNeighborSummary shape."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/noisy-neighbors", headers=AUTH_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "window_minutes" in data
        assert "tenants" in data
        assert "generated_at" in data
        assert isinstance(data["tenants"], list)


# ============================================================
# 3. source_status Semantics
# ============================================================


class TestSourceStatusSemantics:
    """Verify unavailable telemetry returns null, not 0."""

    def test_errors_unavailable_total_is_null(self):
        """ErrorRateSummary with unavailable source has total_errors=null, not 0."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/errors", headers=AUTH_HEADERS)
        data = response.json()
        assert data["source_status"] == "unavailable"
        assert data["total_errors"] is None

    def test_errors_unavailable_arrays_are_empty(self):
        """ErrorRateSummary with unavailable source has empty arrays."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/errors", headers=AUTH_HEADERS)
        data = response.json()
        assert data["error_classes"] == []
        assert data["top_routes"] == []

    def test_slow_routes_unavailable_total_is_null(self):
        """SlowRouteSummary with unavailable source has total_slow_requests=null."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/slow-routes", headers=AUTH_HEADERS)
        data = response.json()
        assert data["source_status"] == "unavailable"
        assert data["total_slow_requests"] is None

    def test_noisy_neighbors_unavailable_is_empty_list(self):
        """NoisyNeighborSummary returns empty tenants list when unavailable."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/noisy-neighbors", headers=AUTH_HEADERS)
        data = response.json()
        assert data["tenants"] == []

    def test_resource_db_status_is_measured_not_fabricated(self):
        """P14: Database health is measured (real ping), not fabricated 'unknown'.
        Unmeasured components remain null rather than fabricated."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/resources", headers=AUTH_HEADERS)
        data = response.json()
        db_status = data["database"]["status"]
        assert db_status in ("healthy", "degraded", "unhealthy")
        assert db_status != "unknown"  # now measured, not fabricated
        assert data["database"]["latency_ms"] is not None
        # Unmeasured components stay null (null != fabricated 0/status).
        assert data["queue"] is None
        assert data["memory"] is None
        assert data["cpu"] is None
        assert data["disk"] is None

    def test_resource_optional_components_are_null(self):
        """Queue, memory, CPU, disk are null when not instrumented."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/resources", headers=AUTH_HEADERS)
        data = response.json()
        assert data["queue"] is None
        assert data["memory"] is None
        assert data["cpu"] is None
        assert data["disk"] is None


# ============================================================
# 4. Permission Enforcement
# ============================================================


class TestPermissions:
    """Verify guard enforcement on all P13 endpoints."""

    ENDPOINTS = [
        "/ops/health",
        "/ops/errors",
        "/ops/slow-routes",
        "/ops/resources",
        "/ops/noisy-neighbors",
    ]

    def test_no_auth_returns_401(self):
        """All P13 endpoints return 401 without credentials."""
        app = _make_guarded_app()
        client = TestClient(app)
        for ep in self.ENDPOINTS:
            response = client.get(f"{P13_BASE}{ep}")
            assert response.status_code == 401, f"{ep} should return 401"

    def test_test_override_accepted(self):
        """Test override header grants access."""
        app = _make_guarded_app()
        client = TestClient(app)
        for ep in self.ENDPOINTS:
            response = client.get(f"{P13_BASE}{ep}", headers=AUTH_HEADERS)
            assert response.status_code == 200, f"{ep} should accept test override"

    def test_operator_secret_accepted(self):
        """Operator secret header grants access."""
        app = _make_guarded_app()
        client = TestClient(app)
        for ep in self.ENDPOINTS:
            response = client.get(f"{P13_BASE}{ep}", headers=OPERATOR_HEADERS)
            assert response.status_code == 200, f"{ep} should accept operator secret"

    def test_invalid_test_override_returns_403(self):
        """Invalid test override returns 403."""
        app = _make_guarded_app()
        client = TestClient(app)
        bad_headers = {"X-Platform-Test-Override": "wrong-secret"}
        for ep in self.ENDPOINTS:
            response = client.get(f"{P13_BASE}{ep}", headers=bad_headers)
            assert response.status_code == 403, f"{ep} should return 403 for bad override"

    def test_invalid_operator_returns_403(self):
        """Invalid operator secret returns 403."""
        app = _make_guarded_app()
        client = TestClient(app)
        bad_headers = {"X-Platform-Operator": "wrong-secret"}
        for ep in self.ENDPOINTS:
            response = client.get(f"{P13_BASE}{ep}", headers=bad_headers)
            assert response.status_code == 403, f"{ep} should return 403 for bad operator"


# ============================================================
# 5. Redaction Verification
# ============================================================


class TestRedaction:
    """Verify no sensitive data in P13 responses."""

    SENSITIVE_PATTERNS = [
        "password",
        "secret",
        "token",
        "cookie",
        "card_number",
        "cvv",
        "authorization",
        "raw_body",
        "request_body",
        "response_body",
        "stack_trace",
        "traceback",
        "host",
        "port",
        "connection_string",
        "dsn",
    ]

    def _check_no_sensitive_data(self, data, path=""):
        """Recursively check data for sensitive patterns."""
        if isinstance(data, dict):
            for key, value in data.items():
                key_lower = key.lower()
                for pattern in self.SENSITIVE_PATTERNS:
                    assert pattern not in key_lower, (
                        f"Sensitive key '{key}' found at {path}.{key}"
                    )
                self._check_no_sensitive_data(value, f"{path}.{key}")
        elif isinstance(data, list):
            for i, item in enumerate(data):
                self._check_no_sensitive_data(item, f"{path}[{i}]")

    def test_errors_no_sensitive_data(self):
        """ErrorRateSummary contains no sensitive keys."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/errors", headers=AUTH_HEADERS)
        self._check_no_sensitive_data(response.json())

    def test_slow_routes_no_sensitive_data(self):
        """SlowRouteSummary contains no sensitive keys."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/slow-routes", headers=AUTH_HEADERS)
        self._check_no_sensitive_data(response.json())

    def test_resources_no_sensitive_data(self):
        """ResourceHealthSummary contains no sensitive keys."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/resources", headers=AUTH_HEADERS)
        self._check_no_sensitive_data(response.json())

    def test_noisy_neighbors_no_sensitive_data(self):
        """NoisyNeighborSummary contains no sensitive keys."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/noisy-neighbors", headers=AUTH_HEADERS)
        self._check_no_sensitive_data(response.json())


# ============================================================
# 6. Audit Event Tests
# ============================================================


class TestAuditEvents:
    """Verify P13 ops views write audit events.

    Audit is best-effort via append_audit_entry (imported inside service).
    We patch append_audit_entry and verify it is called with correct action.
    """

    def _make_audited_app(self):
        """Build app with patched append_audit_entry that tracks calls."""
        mock_db = _mock_db()
        app = _make_app(mock_db)
        return app, mock_db

    def test_ops_health_writes_audit(self):
        """GET /ops/health writes ops_health_view audit."""
        app, mock_db = self._make_audited_app()
        with patch("api.v1.platform.p13.services.append_audit_entry", new_callable=AsyncMock) as mock_audit:
            client = TestClient(app)
            response = client.get(f"{P13_BASE}/ops/health", headers=AUTH_HEADERS)
            assert response.status_code == 200
            mock_audit.assert_called()
            call_kwargs = mock_audit.call_args
            assert call_kwargs[1]["action"] == "ops_health_view"

    def test_ops_errors_writes_audit(self):
        """GET /ops/errors writes ops_error_analysis_view audit."""
        app, mock_db = self._make_audited_app()
        with patch("api.v1.platform.p13.services.append_audit_entry", new_callable=AsyncMock) as mock_audit:
            client = TestClient(app)
            response = client.get(f"{P13_BASE}/ops/errors", headers=AUTH_HEADERS)
            assert response.status_code == 200
            mock_audit.assert_called()
            call_kwargs = mock_audit.call_args
            assert call_kwargs[1]["action"] == "ops_error_analysis_view"

    def test_ops_slow_routes_writes_audit(self):
        """GET /ops/slow-routes writes ops_slow_route_view audit."""
        app, mock_db = self._make_audited_app()
        with patch("api.v1.platform.p13.services.append_audit_entry", new_callable=AsyncMock) as mock_audit:
            client = TestClient(app)
            response = client.get(f"{P13_BASE}/ops/slow-routes", headers=AUTH_HEADERS)
            assert response.status_code == 200
            mock_audit.assert_called()
            call_kwargs = mock_audit.call_args
            assert call_kwargs[1]["action"] == "ops_slow_route_view"

    def test_ops_resources_writes_audit(self):
        """GET /ops/resources writes ops_resource_view audit."""
        app, mock_db = self._make_audited_app()
        with patch("api.v1.platform.p13.services.append_audit_entry", new_callable=AsyncMock) as mock_audit:
            client = TestClient(app)
            response = client.get(f"{P13_BASE}/ops/resources", headers=AUTH_HEADERS)
            assert response.status_code == 200
            mock_audit.assert_called()
            call_kwargs = mock_audit.call_args
            assert call_kwargs[1]["action"] == "ops_resource_view"

    def test_ops_noisy_neighbors_writes_audit(self):
        """GET /ops/noisy-neighbors writes ops_noisy_neighbor_view audit."""
        app, mock_db = self._make_audited_app()
        with patch("api.v1.platform.p13.services.append_audit_entry", new_callable=AsyncMock) as mock_audit:
            client = TestClient(app)
            response = client.get(f"{P13_BASE}/ops/noisy-neighbors", headers=AUTH_HEADERS)
            assert response.status_code == 200
            mock_audit.assert_called()
            call_kwargs = mock_audit.call_args
            assert call_kwargs[1]["action"] == "ops_noisy_neighbor_view"

    def test_access_denied_no_auth_writes_audit(self):
        """No-auth request writes ops_access_denied audit with scope=operations."""
        app, mock_db = self._make_audited_app()
        with patch("services.platform_audit_service.append_audit_entry", new_callable=AsyncMock) as mock_audit:
            client = TestClient(app)
            response = client.get(f"{P13_BASE}/ops/errors")
            assert response.status_code in (401, 403)
            mock_audit.assert_called()
            call_kwargs = mock_audit.call_args[1]
            assert call_kwargs["action"] == "ops_access_denied"
            meta = call_kwargs["audit_metadata"]
            assert meta["scope"] == "operations"
            assert "path" in meta
            assert "/ops/errors" in meta["path"]

    def test_access_denied_wrong_secret_writes_audit(self):
        """Wrong secret request writes ops_access_denied audit."""
        app, mock_db = self._make_audited_app()
        with patch("services.platform_audit_service.append_audit_entry", new_callable=AsyncMock) as mock_audit:
            client = TestClient(app)
            response = client.get(
                f"{P13_BASE}/ops/errors",
                headers={"X-Platform-Test-Override": "wrong-secret"},
            )
            assert response.status_code == 403
            mock_audit.assert_called()
            call_kwargs = mock_audit.call_args[1]
            assert call_kwargs["action"] == "ops_access_denied"
            meta = call_kwargs["audit_metadata"]
            assert meta["scope"] == "operations"
            assert "path" in meta


# ============================================================
# 7. Query Parameter Tests
# ============================================================


class TestQueryParams:
    """Verify query parameter handling."""

    def test_errors_custom_window(self):
        """GET /ops/errors accepts custom window parameter."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/errors?window=60", headers=AUTH_HEADERS)
        assert response.status_code == 200
        assert response.json()["window_minutes"] == 60

    def test_slow_routes_custom_threshold(self):
        """GET /ops/slow-routes accepts custom threshold parameter."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/slow-routes?threshold=2000", headers=AUTH_HEADERS)
        assert response.status_code == 200
        assert response.json()["threshold_ms"] == 2000

    def test_errors_rejects_zero_window(self):
        """GET /ops/errors rejects window=0."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/errors?window=0", headers=AUTH_HEADERS)
        assert response.status_code == 422

    def test_slow_routes_rejects_zero_threshold(self):
        """GET /ops/slow-routes rejects threshold=0."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/slow-routes?threshold=0", headers=AUTH_HEADERS)
        assert response.status_code == 422


# ============================================================
# 8. Counterexample Validation
# ============================================================


class TestCounterexamples:
    """Verify counterexamples from P13-A-R1 contract are handled correctly."""

    def test_ce01_tenant_contextual_token_denied(self):
        """CE-01: Tenant-contextual super_admin is denied."""
        # Real route-level identity test in TestRouteLevelIdentity below.
        # Here we confirm the endpoint exists and rejects no-auth.
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/errors")
        assert response.status_code in (401, 403)

    def test_ce04_ping_failure_is_unhealthy_not_fabricated_healthy(self):
        """CE-04 (P14): when the DB ping fails, status is 'unhealthy' -- never a fabricated 'healthy'."""
        failing_db = _mock_db()
        failing_db.execute = AsyncMock(side_effect=Exception("db unreachable"))
        app = _make_app(failing_db)
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/resources", headers=AUTH_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["database"]["status"] == "unhealthy"
        assert data["database"]["status"] != "healthy"
        assert data["database"]["latency_ms"] is None  # null != 0; no fabricated latency

    def test_ce05_unavailable_not_zero(self):
        """CE-05: Error total is null (not 0) when telemetry uninstrumented."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/errors", headers=AUTH_HEADERS)
        data = response.json()
        assert data["source_status"] == "unavailable"
        assert data["total_errors"] is None
        assert data["total_errors"] != 0

    def test_ce14_no_mutation_capability(self):
        """CE-14: All P13 endpoints are GET-only (no mutation)."""
        app = _make_guarded_app()
        client = TestClient(app)
        for ep in ["/ops/errors", "/ops/slow-routes", "/ops/resources", "/ops/noisy-neighbors"]:
            # POST should be rejected (405)
            response = client.post(f"{P13_BASE}{ep}", headers=AUTH_HEADERS)
            assert response.status_code == 405, f"POST {ep} should be 405"


# ============================================================
# 9. Route-Level Identity Tests
# ============================================================


class TestRouteLevelIdentity:
    """P13 route-level identity enforcement via Bearer/auth context.

    Reuses P10/P12 auth_context injection pattern:
      - identity-only super_admin Bearer token allowed
      - tenant-contextual super_admin denied
      - non-super_admin identity denied
    """

    def test_identity_only_super_admin_allowed(self):
        """Identity-only global super_admin Bearer/auth context is allowed."""
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
            response = client.get(f"{P13_BASE}/ops/errors")
        assert response.status_code == 200
        data = response.json()
        assert "source_status" in data

    def test_contextual_super_admin_denied(self):
        """Tenant-contextual super_admin Bearer/auth context is denied."""
        mock_db = _mock_db()
        app = _make_app(mock_db)
        client = TestClient(app)

        token = MagicMock()
        token.user_id = "c3d4e5f6-a7b8-49c9-0d1e-2f3a4b5c6d7e"
        token.roles = ["super_admin"]
        token.tenant_id = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
        token.tenant_schema = "t_test"
        token.is_identity_only = False
        token.is_super_admin = True

        auth_ctx = MagicMock()
        auth_ctx.token = token

        with patch("api.context.auth.get_auth_context", return_value=auth_ctx):
            response = client.get(f"{P13_BASE}/ops/errors")
        assert response.status_code in (401, 403)

    def test_non_super_admin_denied(self):
        """Identity-only token without super_admin role is denied."""
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
            response = client.get(f"{P13_BASE}/ops/errors")
        assert response.status_code in (401, 403)

    def test_identity_only_super_admin_allowed_all_endpoints(self):
        """Identity-only super_admin is allowed on ALL P13 endpoints."""
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
            for ep in ["/ops/health", "/ops/errors", "/ops/slow-routes", "/ops/resources", "/ops/noisy-neighbors"]:
                response = client.get(f"{P13_BASE}{ep}")
                assert response.status_code == 200, f"{ep} should allow identity-only super_admin"


# ============================================================
# 10. P14-B Real Database Health Adapter
# ============================================================


class TestP14DatabaseHealthAdapter:
    """P14-B: real read-only DB health (ping latency + engine pool stats).

    Covers: real source used when available, unhealthy fallback on ping error,
    pool-status parsing, no sensitive payloads, unavailable_reason surfaced,
    and no mutation routes.
    """

    def test_database_health_uses_real_ping(self):
        """_database_health runs a SELECT 1 and records measured latency + status."""
        import asyncio
        from api.v1.platform.p13.services import _database_health

        db = _mock_db()
        health = asyncio.run(_database_health(db))
        # The mock execute resolves without error -> measured healthy with latency.
        assert health.status == "healthy"
        assert isinstance(health.latency_ms, int) and health.latency_ms >= 0
        # Pool introspection on a MagicMock returns non-string -> honest nulls.
        assert health.connection_pool_active is None
        assert health.connection_pool_idle is None
        assert health.connection_pool_max is None

    def test_database_health_unhealthy_on_ping_error(self):
        """When the DB ping raises, status is unhealthy and latency is null."""
        import asyncio
        from api.v1.platform.p13.services import _database_health

        db = _mock_db()
        db.execute = AsyncMock(side_effect=RuntimeError("connection refused"))
        health = asyncio.run(_database_health(db))
        assert health.status == "unhealthy"
        assert health.latency_ms is None  # null, never fabricated 0

    def test_parse_pool_status_queuepool(self):
        """_parse_pool_status parses a real QueuePool.status() string."""
        from api.v1.platform.p13.services import _parse_pool_status

        status_text = (
            "Pool size: 5 Connections in pool: 2 "
            "Current Overflow: 3 Current Checked out connections: 1"
        )
        active, idle, mx = _parse_pool_status(status_text)
        assert active == 1   # checked out
        assert idle == 2     # in pool
        assert mx == 8       # size(5) + overflow(3)

    def test_parse_pool_status_garbage_returns_none(self):
        """Non-string / unparseable input falls back to honest None triple."""
        from api.v1.platform.p13.services import _parse_pool_status

        assert _parse_pool_status(None) == (None, None, None)
        assert _parse_pool_status("") == (None, None, None)
        assert _parse_pool_status("not a pool status string") == (None, None, None)

    def test_resources_surfaces_real_pool_when_available(self):
        """When the engine pool reports stats, the endpoint surfaces them."""
        pool = MagicMock()
        pool.status.return_value = (
            "Pool size: 10 Connections in pool: 4 "
            "Current Overflow: 0 Current Checked out connections: 2"
        )
        bind = MagicMock()
        bind.pool = pool
        db = _mock_db()
        db.bind = bind
        app = _make_app(db)
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/resources", headers=AUTH_HEADERS)
        data = response.json()
        assert data["database"]["connection_pool_active"] == 2
        assert data["database"]["connection_pool_idle"] == 4
        assert data["database"]["connection_pool_max"] == 10

    def test_resources_no_sensitive_payload(self):
        """Real DB health response leaks no host/port/DSN/credentials."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/resources", headers=AUTH_HEADERS)
        body = response.json()
        dumped = str(body).lower()
        for forbidden in ("host", "port", "dsn", "password", "secret", "credential", "connection_string"):
            assert forbidden not in dumped, f"sensitive token '{forbidden}' leaked in resources response"

    def test_unavailable_reason_surfaced_on_errors(self):
        """P14: /ops/errors surfaces unavailable_reason for the UI."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/errors", headers=AUTH_HEADERS)
        data = response.json()
        assert data["source_status"] == "unavailable"
        assert isinstance(data.get("unavailable_reason"), str) and data["unavailable_reason"]

    def test_unavailable_reason_surfaced_on_slow_routes(self):
        """P14: /ops/slow-routes surfaces unavailable_reason for the UI."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/slow-routes", headers=AUTH_HEADERS)
        data = response.json()
        assert data["source_status"] == "unavailable"
        assert isinstance(data.get("unavailable_reason"), str) and data["unavailable_reason"]

    def test_unavailable_reason_surfaced_on_noisy_neighbors(self):
        """P14: /ops/noisy-neighbors surfaces unavailable_reason for the UI."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.get(f"{P13_BASE}/ops/noisy-neighbors", headers=AUTH_HEADERS)
        data = response.json()
        assert isinstance(data.get("unavailable_reason"), str) and data["unavailable_reason"]

    def test_resources_is_read_only(self):
        """P14-B: real DB health is still read-only (no mutation route)."""
        app = _make_guarded_app()
        client = TestClient(app)
        response = client.post(f"{P13_BASE}/ops/resources", headers=AUTH_HEADERS)
        assert response.status_code == 405
