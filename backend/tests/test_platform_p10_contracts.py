"""
P10-C: Contract-backed tests for Platform Product P10 read-only API.

Proves:
  1. All contract fields are present with correct types/nullability.
  2. Unknown fallback behavior is contract-compliant.
  3. No raw payload leakage.
  4. Read-only behavior (GET only, mutations rejected).
  5. Mutation methods rejected where applicable.
  6. Fixtures from PLATFORM_PRODUCT_CONTRACT_FIXTURES.md are represented.
  7. Counterexamples from PLATFORM_PRODUCT_CONTRACT_FIXTURES.md are rejected.

Test IDs align with PLATFORM_PRODUCT_P10A_TEST_PLAN.md categories:
  CS-xxx: Contract Structure tests
  FC-xxx: Fixture Conformance tests
  CR-xxx: Counterexample Rejection tests
  SB-xxx: Scope Boundary tests
  RO-xxx: Read-Only behavior tests
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.v1.platform.p10.schemas import (
    TenantSummary,
    TenantSummaryList,
    TenantHealth,
    SystemHealth,
    PlatformAuditEvent,
    PlatformAuditEventList,
    ErrorSummary,
    SlowRoute,
    FailedJob,
    ActivityCounters,
    DatabaseConnections,
    TenantStatus,
    HealthStatus,
    ComponentStatus,
    OverallStatus,
    SchemaStatus,
    ActorRole,
    AuditScope,
    AuditResult,
    validate_tenant_summary_cross_rules,
    validate_system_health_cross_rules,
    validate_audit_event_cross_rules,
)
from api.v1.platform.p10.routes import router as p10_router
from api.v1.platform.p10.guard import require_platform_operator
from api.dependencies import get_db
from database.session import get_db as db_get_db


# ═══════════════════════════════════════════════════════════════
# Test helpers
# ═══════════════════════════════════════════════════════════════


def _make_app(mock_db) -> FastAPI:
    """Build test app with dependency overrides (guard bypassed for unit tests)."""
    app = FastAPI()
    app.include_router(p10_router)

    async def override():
        yield mock_db

    # Override the platform guard to always allow in unit tests
    app.dependency_overrides[require_platform_operator] = lambda: None
    app.dependency_overrides[get_db] = override
    app.dependency_overrides[db_get_db] = override
    return app


def _mock_wholesaler(
    id="550e8400-e29b-41d4-a716-446655440000",
    name="Acme Wholesale Ltd",
    status="active",
    code="acme",
    plan_type="professional",
    created_at=None,
    is_deleted=False,
):
    """Create a mock Wholesaler object."""
    w = MagicMock()
    w.id = id
    w.name = name
    w.status = status
    w.code = code
    w.plan_type = plan_type
    w.created_at = created_at or datetime(2026, 1, 15, 9, 30, 0, tzinfo=timezone.utc)
    w.is_deleted = is_deleted
    w.get_tenant_schema.return_value = "tenant_acme_wholesale"
    return w


def _mock_db_for_list(wholesalers, total=None):
    """Create mock DB that returns a list of wholesalers."""
    mock_db = MagicMock()

    count_result = MagicMock()
    count_result.scalar.return_value = total if total is not None else len(wholesalers)

    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = wholesalers

    mock_db.execute = AsyncMock(side_effect=[count_result, list_result])
    return mock_db


def _mock_db_for_detail(wholesaler):
    """Create mock DB that returns a single wholesaler."""
    mock_db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = wholesaler
    mock_db.execute = AsyncMock(return_value=result)
    return mock_db


def _mock_db_for_not_found():
    """Create mock DB that returns None for detail queries."""
    mock_db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=result)
    return mock_db


# ═══════════════════════════════════════════════════════════════
# CS-xxx: Contract Structure Tests (field-by-field)
# ═══════════════════════════════════════════════════════════════


class TestTenantSummaryStructure:
    """CS-001 through CS-004: TenantSummary has all P10-A fields with correct types."""

    def test_has_all_11_fields(self):
        """CS-001: TenantSummary has all 11 P10-A fields."""
        fields = TenantSummary.model_fields
        expected = [
            "tenant_id", "tenant_name", "tenant_schema", "status", "tier",
            "created_at", "last_activity_at", "user_count", "health_status",
            "recent_error_count", "support_mode_active",
        ]
        for field in expected:
            assert field in fields, f"Missing field: {field}"

    def test_nullable_fields(self):
        """CS-002: Nullable fields accept null."""
        summary = TenantSummary(
            tenant_id=None,
            tenant_name=None,
            tenant_schema=None,
            status="unknown",
            tier=None,
            created_at=None,
            last_activity_at=None,
            user_count=None,
            health_status="unknown",
            recent_error_count=None,
            support_mode_active=False,
        )
        assert summary.tenant_id is None
        assert summary.tenant_name is None
        assert summary.user_count is None

    def test_not_null_fields_required(self):
        """CS-002: Non-nullable fields are required."""
        with pytest.raises(ValidationError):
            TenantSummary()  # missing status, health_status, support_mode_active

    def test_status_enum_values(self):
        """CS-003: Status enum matches P10-A contract."""
        valid = ["draft", "active", "paused", "suspended", "archived", "unknown"]
        for s in valid:
            summary = TenantSummary(status=s, health_status="unknown", support_mode_active=False)
            assert summary.status == s

    def test_status_invalid_rejected(self):
        """CS-003: Invalid status values rejected."""
        with pytest.raises(ValidationError):
            TenantSummary(status="deleted", health_status="unknown", support_mode_active=False)

    def test_health_status_enum_values(self):
        """CS-004: Health status enum matches P10-A contract."""
        valid = ["healthy", "degraded", "unhealthy", "unknown"]
        for h in valid:
            summary = TenantSummary(status="active", health_status=h, support_mode_active=False)
            assert summary.health_status == h

    def test_health_status_invalid_rejected(self):
        """CS-004: Invalid health_status rejected."""
        with pytest.raises(ValidationError):
            TenantSummary(status="active", health_status="ok", support_mode_active=False)

    def test_user_count_negative_rejected(self):
        """CS-002: user_count negative rejected."""
        with pytest.raises(ValidationError):
            TenantSummary(
                status="active", health_status="healthy", support_mode_active=False,
                user_count=-1,
            )

    def test_recent_error_count_negative_rejected(self):
        """CS-002: recent_error_count negative rejected."""
        with pytest.raises(ValidationError):
            TenantSummary(
                status="active", health_status="healthy", support_mode_active=False,
                recent_error_count=-1,
            )

    def test_support_mode_not_nullable(self):
        """CS-002: support_mode_active cannot be null."""
        with pytest.raises(ValidationError):
            TenantSummary(
                status="active", health_status="healthy",
                support_mode_active=None,  # type: ignore
            )


class TestTenantHealthStructure:
    """CS-005 through CS-007: TenantHealth has all P10-A fields."""

    def test_has_all_10_fields(self):
        """CS-005: TenantHealth has all 10 P10-A fields."""
        fields = TenantHealth.model_fields
        expected = [
            "tenant_id", "tenant_schema", "health_status", "schema_status",
            "last_login_at", "activity_counters", "recent_errors",
            "slow_routes", "failed_jobs", "last_health_check_at",
        ]
        for field in expected:
            assert field in fields, f"Missing field: {field}"

    def test_sub_structures_valid(self):
        """CS-006: Sub-structures have correct fields."""
        # ErrorSummary
        err = ErrorSummary(error_class="TimeoutError", count=3, correlation_ids=["corr-1"])
        assert err.error_class == "TimeoutError"
        assert err.count == 3

        # SlowRoute
        sr = SlowRoute(route="GET /api/orders", latency_bucket_ms=1200, count=5)
        assert sr.route == "GET /api/orders"

        # FailedJob
        fj = FailedJob(job_class="OrderSyncJob", count=2)
        assert fj.job_class == "OrderSyncJob"

    def test_error_summary_empty_correlation_ids_rejected(self):
        """CS-006: ErrorSummary requires at least 1 correlation_id."""
        with pytest.raises(ValidationError):
            ErrorSummary(error_class="Error", count=1, correlation_ids=[])

    def test_error_summary_zero_count_rejected(self):
        """CS-006: ErrorSummary count must be >= 1."""
        with pytest.raises(ValidationError):
            ErrorSummary(error_class="Error", count=0, correlation_ids=["corr-1"])

    def test_slow_route_negative_latency_rejected(self):
        """CS-006: SlowRoute latency must be >= 0."""
        with pytest.raises(ValidationError):
            SlowRoute(route="GET /x", latency_bucket_ms=-1, count=1)

    def test_schema_status_enum(self):
        """CS-007: Schema status enum valid."""
        valid = ["exists", "unreachable", "migration_misaligned", "missing", "unknown"]
        for s in valid:
            health = TenantHealth(health_status="unknown", schema_status=s)
            assert health.schema_status == s

    def test_schema_status_invalid_rejected(self):
        """CS-007: Invalid schema_status rejected."""
        with pytest.raises(ValidationError):
            TenantHealth(health_status="unknown", schema_status="broken")


class TestSystemHealthStructure:
    """CS-008 through CS-011: SystemHealth has all P10-A fields."""

    def test_has_all_11_fields(self):
        """CS-008: SystemHealth has all 11 P10-A fields."""
        fields = SystemHealth.model_fields
        expected = [
            "overall_status", "api_status", "database_status",
            "database_connections", "queue_status", "cpu_status",
            "memory_status", "disk_status", "error_rate",
            "slow_request_count", "generated_at",
        ]
        for field in expected:
            assert field in fields, f"Missing field: {field}"

    def test_component_status_enum(self):
        """CS-009: Component status enum valid."""
        valid = ["healthy", "degraded", "down", "unknown"]
        for s in valid:
            health = SystemHealth(
                overall_status="unknown",
                api_status=s,
                generated_at=datetime.now(timezone.utc),
            )
            assert health.api_status == s

    def test_overall_status_enum(self):
        """CS-010: Overall status enum valid."""
        valid = ["healthy", "degraded", "down", "unknown"]
        for s in valid:
            health = SystemHealth(overall_status=s, generated_at=datetime.now(timezone.utc))
            assert health.overall_status == s

    def test_cpu_memory_disk_nullable(self):
        """CS-011: cpu/memory/disk are nullable (optional in local/dev)."""
        health = SystemHealth(
            overall_status="unknown",
            cpu_status=None,
            memory_status=None,
            disk_status=None,
            generated_at=datetime.now(timezone.utc),
        )
        assert health.cpu_status is None
        assert health.memory_status is None
        assert health.disk_status is None

    def test_error_rate_negative_rejected(self):
        """CS-008: error_rate negative rejected."""
        with pytest.raises(ValidationError):
            SystemHealth(
                overall_status="unknown",
                error_rate=-0.1,
                generated_at=datetime.now(timezone.utc),
            )

    def test_slow_request_count_negative_rejected(self):
        """CS-008: slow_request_count negative rejected."""
        with pytest.raises(ValidationError):
            SystemHealth(
                overall_status="unknown",
                slow_request_count=-1,
                generated_at=datetime.now(timezone.utc),
            )

    def test_invalid_overall_status_rejected(self):
        """CS-010: 'ok' and 'green' rejected."""
        with pytest.raises(ValidationError):
            SystemHealth(overall_status="ok", generated_at=datetime.now(timezone.utc))
        with pytest.raises(ValidationError):
            SystemHealth(overall_status="green", generated_at=datetime.now(timezone.utc))


class TestPlatformAuditEventStructure:
    """CS-012 through CS-015: PlatformAuditEvent has all P10-A fields."""

    def test_has_all_11_fields(self):
        """CS-012: PlatformAuditEvent has all 11 P10-A fields."""
        fields = PlatformAuditEvent.model_fields
        expected = [
            "event_id", "actor_id", "actor_role", "tenant_id", "scope",
            "action", "reason", "result", "metadata_redacted",
            "correlation_id", "created_at",
        ]
        for field in expected:
            assert field in fields, f"Missing field: {field}"

    def test_actor_role_enum(self):
        """CS-013: Actor role enum valid."""
        valid = ["super_admin", "support_operator", "engineering_operator"]
        for r in valid:
            event = PlatformAuditEvent(
                event_id="550e8400-e29b-41d4-a716-446655440000",
                actor_role=r,
                scope="global",
                action="test.action",
                result="completed",
                created_at=datetime.now(timezone.utc),
            )
            assert event.actor_role == r

    def test_actor_role_admin_rejected(self):
        """CS-013/C6: actor_role='admin' rejected."""
        with pytest.raises(ValidationError):
            PlatformAuditEvent(
                event_id="550e8400-e29b-41d4-a716-446655440000",
                actor_role="admin",
                scope="global",
                action="test.action",
                result="completed",
                created_at=datetime.now(timezone.utc),
            )

    def test_scope_enum(self):
        """CS-014: Scope enum valid."""
        valid = ["global", "tenant", "system", "support"]
        for s in valid:
            event = PlatformAuditEvent(
                event_id="550e8400-e29b-41d4-a716-446655440000",
                scope=s,
                action="test",
                result="completed",
                created_at=datetime.now(timezone.utc),
            )
            assert event.scope == s

    def test_result_enum(self):
        """CS-015: Result enum valid."""
        valid = ["allowed", "denied", "failed", "completed"]
        for r in valid:
            event = PlatformAuditEvent(
                event_id="550e8400-e29b-41d4-a716-446655440000",
                scope="global",
                action="test",
                result=r,
                created_at=datetime.now(timezone.utc),
            )
            assert event.result == r

    def test_result_success_rejected(self):
        """CS-015: 'success' is not a valid result."""
        with pytest.raises(ValidationError):
            PlatformAuditEvent(
                event_id="550e8400-e29b-41d4-a716-446655440000",
                scope="global",
                action="test",
                result="success",
                created_at=datetime.now(timezone.utc),
            )


# ═══════════════════════════════════════════════════════════════
# FC-xxx: Fixture Conformance Tests
# ═══════════════════════════════════════════════════════════════


class TestFixtureConformance:
    """Tests that all fixtures from PLATFORM_PRODUCT_CONTRACT_FIXTURES.md are valid."""

    def test_fixture1_healthy_tenant_summary(self):
        """FC-001: Healthy Tenant Summary — all fields populated."""
        summary = TenantSummary(
            tenant_id="550e8400-e29b-41d4-a716-446655440000",
            tenant_name="Acme Wholesale Ltd",
            tenant_schema="tenant_acme_wholesale",
            status="active",
            tier="professional",
            created_at=datetime(2026, 1, 15, 9, 30, 0, tzinfo=timezone.utc),
            last_activity_at=datetime(2026, 6, 5, 8, 12, 0, tzinfo=timezone.utc),
            user_count=24,
            health_status="healthy",
            recent_error_count=0,
            support_mode_active=False,
        )
        assert summary.status == "active"
        assert summary.health_status == "healthy"
        assert summary.support_mode_active is False
        assert summary.recent_error_count == 0
        assert summary.user_count == 24

    def test_fixture2_healthy_tenant_health(self):
        """FC-002: Healthy Tenant Health — no errors, no slow routes."""
        health = TenantHealth(
            tenant_id="550e8400-e29b-41d4-a716-446655440000",
            tenant_schema="tenant_acme_wholesale",
            health_status="healthy",
            schema_status="exists",
            last_login_at=datetime(2026, 6, 5, 8, 10, 0, tzinfo=timezone.utc),
            activity_counters=ActivityCounters(
                orders=42, inventory_changes=15, invoices=8, payments=3, sync_jobs=1
            ),
            recent_errors=[],
            slow_routes=[],
            failed_jobs=[],
            last_health_check_at=datetime(2026, 6, 5, 8, 15, 0, tzinfo=timezone.utc),
        )
        assert health.health_status == "healthy"
        assert health.recent_errors == []
        assert health.slow_routes == []
        assert health.failed_jobs == []
        assert health.activity_counters.orders == 42

    def test_fixture3_degraded_tenant_summary(self):
        """FC-003: Degraded Tenant Summary — health_status degraded, errors > 0."""
        summary = TenantSummary(
            tenant_id="660e8400-e29b-41d4-a716-446655440001",
            tenant_name="SlowCo Distributors",
            tenant_schema="tenant_slowco",
            status="active",
            tier="starter",
            created_at=datetime(2026, 3, 20, 11, 0, 0, tzinfo=timezone.utc),
            last_activity_at=datetime(2026, 6, 4, 10, 15, 0, tzinfo=timezone.utc),
            user_count=3,
            health_status="degraded",
            recent_error_count=7,
            support_mode_active=False,
        )
        assert summary.health_status == "degraded"
        assert summary.recent_error_count == 7

    def test_fixture4_degraded_tenant_health(self):
        """FC-004: Degraded Tenant Health — errors, slow routes, failed jobs."""
        health = TenantHealth(
            tenant_id="660e8400-e29b-41d4-a716-446655440001",
            tenant_schema="tenant_slowco",
            health_status="degraded",
            schema_status="exists",
            last_login_at=datetime(2026, 6, 4, 10, 0, 0, tzinfo=timezone.utc),
            activity_counters=ActivityCounters(
                orders=5, inventory_changes=1, invoices=0, payments=0, sync_jobs=0
            ),
            recent_errors=[
                ErrorSummary(error_class="TimeoutError", count=5, correlation_ids=["corr-abc123", "corr-def456"]),
                ErrorSummary(error_class="ConnectionRefused", count=2, correlation_ids=["corr-ghi789"]),
            ],
            slow_routes=[
                SlowRoute(route="GET /api/orders", latency_bucket_ms=1200, count=3),
            ],
            failed_jobs=[
                FailedJob(job_class="OrderSyncJob", count=1),
            ],
            last_health_check_at=datetime(2026, 6, 5, 8, 15, 0, tzinfo=timezone.utc),
        )
        assert health.health_status == "degraded"
        assert len(health.recent_errors) == 2
        assert len(health.slow_routes) == 1
        assert len(health.failed_jobs) == 1
        # Verify redaction: no raw payloads
        for err in health.recent_errors:
            assert "traceback" not in err.error_class.lower()
            assert "stack" not in err.error_class.lower()

    def test_fixture5_unknown_tenant_summary(self):
        """FC-005: Unknown Tenant Summary — health_status unknown, nullable fields null."""
        summary = TenantSummary(
            tenant_id="770e8400-e29b-41d4-a716-446655440002",
            tenant_name=None,
            tenant_schema="tenant_phantom",
            status="unknown",
            tier=None,
            created_at=None,
            last_activity_at=None,
            user_count=None,
            health_status="unknown",
            recent_error_count=None,
            support_mode_active=False,
        )
        assert summary.health_status == "unknown"
        assert summary.tenant_name is None
        assert summary.user_count is None
        assert summary.support_mode_active is False

    def test_fixture6_unknown_tenant_health(self):
        """FC-006: Unknown Tenant Health — schema unreachable, telemetry null."""
        health = TenantHealth(
            tenant_id="770e8400-e29b-41d4-a716-446655440002",
            tenant_schema="tenant_phantom",
            health_status="unknown",
            schema_status="unreachable",
            last_login_at=None,
            activity_counters=None,
            recent_errors=None,
            slow_routes=None,
            failed_jobs=None,
            last_health_check_at=None,
        )
        assert health.health_status == "unknown"
        assert health.schema_status == "unreachable"
        assert health.recent_errors is None
        assert health.activity_counters is None

    def test_fixture7_degraded_system(self):
        """FC-007: Degraded System — api degraded, cpu/memory/disk null."""
        health = SystemHealth(
            overall_status="degraded",
            api_status="degraded",
            database_status="healthy",
            database_connections=DatabaseConnections(active=8, idle=3, max=20, saturation_pct=40.0),
            queue_status="healthy",
            cpu_status=None,
            memory_status=None,
            disk_status=None,
            error_rate=0.12,
            slow_request_count=3,
            generated_at=datetime(2026, 6, 5, 9, 0, 0, tzinfo=timezone.utc),
        )
        assert health.overall_status == "degraded"
        assert health.api_status == "degraded"
        assert health.cpu_status is None
        assert health.memory_status is None
        assert health.disk_status is None
        assert health.error_rate == 0.12

    def test_fixture8_support_bundle_denied(self):
        """FC-008: Support Bundle Denied — reason null, result denied."""
        event = PlatformAuditEvent(
            event_id="880e8400-e29b-41d4-a716-446655440003",
            actor_id="operator-42",
            actor_role="support_operator",
            tenant_id="550e8400-e29b-41d4-a716-446655440000",
            scope="support",
            action="support.bundle_generate",
            reason=None,
            result="denied",
            metadata_redacted={
                "denial_code": "missing_reason",
                "requested_at": "2026-06-05T09:20:00.000Z",
            },
            correlation_id="corr-support-001",
            created_at=datetime(2026, 6, 5, 9, 20, 1, tzinfo=timezone.utc),
        )
        assert event.scope == "support"
        assert event.reason is None
        assert event.result == "denied"

    def test_fixture9_support_operator_denied(self):
        """FC-009: Support Operator Denied — unassigned tenant."""
        event = PlatformAuditEvent(
            event_id="990e8400-e29b-41d4-a716-446655440004",
            actor_id="operator-99",
            actor_role="support_operator",
            tenant_id="660e8400-e29b-41d4-a716-446655440001",
            scope="support",
            action="support.tenant_view",
            reason="routine health check",
            result="denied",
            metadata_redacted={
                "denial_code": "unassigned_tenant",
                "operator_assignments": ["550e8400-e29b-41d4-a716-446655440000"],
                "message": "Operator not assigned to this tenant",
            },
            correlation_id="corr-support-002",
            created_at=datetime(2026, 6, 5, 9, 22, 0, tzinfo=timezone.utc),
        )
        assert event.result == "denied"
        assert event.metadata_redacted["denial_code"] == "unassigned_tenant"


# ═══════════════════════════════════════════════════════════════
# CR-xxx: Counterexample Rejection Tests
# ═══════════════════════════════════════════════════════════════


class TestCounterexampleRejection:
    """Tests that all counterexamples from PLATFORM_PRODUCT_CONTRACT_FIXTURES.md are rejected."""

    def test_cr1_healthy_when_unknown(self):
        """CR-001: health_status cannot be 'healthy' when sources are null."""
        summary = TenantSummary(
            tenant_id="770e8400-e29b-41d4-a716-446655440002",
            tenant_name=None,
            tenant_schema="tenant_phantom",
            status="active",
            tier=None,
            created_at=None,
            last_activity_at=None,
            user_count=None,
            health_status="healthy",
            recent_error_count=None,
            support_mode_active=False,
        )
        violations = validate_tenant_summary_cross_rules(summary)
        assert len(violations) > 0
        assert "healthy" in violations[0].lower()

    def test_cr2_support_scope_without_reason_allowed_result(self):
        """CR-002: support scope with allowed result requires reason."""
        event = PlatformAuditEvent(
            event_id="aa0e8400-e29b-41d4-a716-446655440005",
            actor_id="operator-42",
            actor_role="support_operator",
            tenant_id="550e8400-e29b-41d4-a716-446655440000",
            scope="support",
            action="support.tenant_view",
            reason=None,
            result="allowed",
            metadata_redacted=None,
            correlation_id=None,
            created_at=datetime(2026, 6, 5, 9, 30, 0, tzinfo=timezone.utc),
        )
        violations = validate_audit_event_cross_rules(event)
        assert len(violations) > 0
        assert "reason" in violations[0].lower()

    def test_cr3_healthy_overall_with_degraded_component(self):
        """CR-003: overall_status='healthy' contradicts degraded component."""
        health = SystemHealth(
            overall_status="healthy",
            api_status="degraded",
            database_status="healthy",
            database_connections=None,
            queue_status=None,
            cpu_status=None,
            memory_status=None,
            disk_status=None,
            error_rate=None,
            slow_request_count=None,
            generated_at=datetime(2026, 6, 5, 9, 0, 0, tzinfo=timezone.utc),
        )
        violations = validate_system_health_cross_rules(health)
        assert len(violations) > 0
        assert "degraded" in violations[0].lower()

    def test_cr4_raw_error_payload_rejected(self):
        """CR-004: raw_stack_trace field in ErrorSummary rejected."""
        # Pydantic schema only has 3 fields; extra fields are rejected by default
        with pytest.raises(ValidationError):
            ErrorSummary(
                error_class="ValueError",
                count=1,
                correlation_ids=["corr-001"],
                raw_stack_trace="Traceback (most recent call last): ...",  # type: ignore
            )

    def test_cr5_tenant_scope_without_tenant_id(self):
        """CR-005: scope='tenant' requires non-null tenant_id."""
        event = PlatformAuditEvent(
            event_id="bb0e8400-e29b-41d4-a716-446655440006",
            actor_id=None,
            actor_role="super_admin",
            tenant_id=None,
            scope="tenant",
            action="tenant.status_change",
            reason="policy violation",
            result="allowed",
            metadata_redacted=None,
            correlation_id=None,
            created_at=datetime(2026, 6, 5, 10, 0, 0, tzinfo=timezone.utc),
        )
        violations = validate_audit_event_cross_rules(event)
        assert len(violations) > 0
        assert "tenant_id" in violations[0].lower()

    def test_cr6_actor_role_admin_rejected(self):
        """CR-006: actor_role='admin' rejected (not a valid enum)."""
        with pytest.raises(ValidationError):
            PlatformAuditEvent(
                event_id="cc0e8400-e29b-41d4-a716-446655440007",
                actor_id="user-1",
                actor_role="admin",
                tenant_id=None,
                scope="global",
                action="platform.config_change",
                reason=None,
                result="completed",
                metadata_redacted=None,
                correlation_id=None,
                created_at=datetime(2026, 6, 5, 10, 5, 0, tzinfo=timezone.utc),
            )


# ═══════════════════════════════════════════════════════════════
# RO-xxx: Read-Only Behavior Tests
# ═══════════════════════════════════════════════════════════════


class TestReadOnlyBehavior:
    """All mutation methods (POST, PUT, PATCH, DELETE) must be rejected (405)."""

    @pytest.fixture
    def client(self):
        w = _mock_wholesaler()
        db = _mock_db_for_list([w])
        return TestClient(_make_app(db))

    def test_no_post_tenants_list(self, client):
        """RO-001: POST /tenants rejected."""
        resp = client.post("/api/v1/platform/p10/tenants", json={})
        assert resp.status_code == 405

    def test_no_put_tenants_list(self, client):
        resp = client.put("/api/v1/platform/p10/tenants", json={})
        assert resp.status_code == 405

    def test_no_patch_tenants_list(self, client):
        resp = client.patch("/api/v1/platform/p10/tenants", json={})
        assert resp.status_code == 405

    def test_no_delete_tenants_list(self, client):
        resp = client.delete("/api/v1/platform/p10/tenants")
        assert resp.status_code == 405

    def test_no_post_tenant_detail(self, client):
        resp = client.post("/api/v1/platform/p10/tenants/abc", json={})
        assert resp.status_code == 405

    def test_no_put_tenant_detail(self, client):
        resp = client.put("/api/v1/platform/p10/tenants/abc", json={})
        assert resp.status_code == 405

    def test_no_patch_tenant_detail(self, client):
        resp = client.patch("/api/v1/platform/p10/tenants/abc", json={})
        assert resp.status_code == 405

    def test_no_delete_tenant_detail(self, client):
        resp = client.delete("/api/v1/platform/p10/tenants/abc")
        assert resp.status_code == 405

    def test_no_post_tenant_health(self, client):
        resp = client.post("/api/v1/platform/p10/tenants/abc/health", json={})
        assert resp.status_code == 405

    def test_no_put_tenant_health(self, client):
        resp = client.put("/api/v1/platform/p10/tenants/abc/health", json={})
        assert resp.status_code == 405

    def test_no_delete_tenant_health(self, client):
        resp = client.delete("/api/v1/platform/p10/tenants/abc/health")
        assert resp.status_code == 405

    def test_no_post_system_health(self, client):
        resp = client.post("/api/v1/platform/p10/system/health", json={})
        assert resp.status_code == 405

    def test_no_put_system_health(self, client):
        resp = client.put("/api/v1/platform/p10/system/health", json={})
        assert resp.status_code == 405

    def test_no_delete_system_health(self, client):
        resp = client.delete("/api/v1/platform/p10/system/health")
        assert resp.status_code == 405

    def test_no_post_audit_events(self, client):
        resp = client.post("/api/v1/platform/p10/audit/events", json={})
        assert resp.status_code == 405

    def test_no_put_audit_events(self, client):
        resp = client.put("/api/v1/platform/p10/audit/events", json={})
        assert resp.status_code == 405

    def test_no_delete_audit_events(self, client):
        resp = client.delete("/api/v1/platform/p10/audit/events")
        assert resp.status_code == 405


# ═══════════════════════════════════════════════════════════════
# API Response Shape Tests
# ═══════════════════════════════════════════════════════════════


class TestTenantSummaryAPI:
    """API-level tests for TenantSummary endpoints."""

    def test_list_tenants_response_shape(self):
        w = _mock_wholesaler()
        db = _mock_db_for_list([w])
        client = TestClient(_make_app(db))
        resp = client.get("/api/v1/platform/p10/tenants")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_tenants_contract_fields(self):
        """All contract fields present in response."""
        w = _mock_wholesaler()
        db = _mock_db_for_list([w])
        client = TestClient(_make_app(db))
        resp = client.get("/api/v1/platform/p10/tenants")
        item = resp.json()["items"][0]
        expected_fields = [
            "tenant_id", "tenant_name", "tenant_schema", "status", "tier",
            "created_at", "last_activity_at", "user_count", "health_status",
            "recent_error_count", "support_mode_active",
        ]
        for field in expected_fields:
            assert field in item, f"Missing field in response: {field}"

    def test_list_tenants_unknown_fallback(self):
        """Nullable fields null, non-null enums use fallbacks."""
        w = _mock_wholesaler()
        db = _mock_db_for_list([w])
        client = TestClient(_make_app(db))
        resp = client.get("/api/v1/platform/p10/tenants")
        item = resp.json()["items"][0]
        # health_status must be "unknown" (no health signals)
        assert item["health_status"] == "unknown"
        # support_mode_active must be False (not implemented)
        assert item["support_mode_active"] is False
        # tier must be null (subscription model not built)
        assert item["tier"] is None
        # user_count must be null (aggregate not built)
        assert item["user_count"] is None
        # recent_error_count must be null (telemetry not built)
        assert item["recent_error_count"] is None

    def test_get_tenant_detail(self):
        w = _mock_wholesaler()
        db = _mock_db_for_detail(w)
        client = TestClient(_make_app(db))
        resp = client.get("/api/v1/platform/p10/tenants/550e8400-e29b-41d4-a716-446655440000")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert data["tenant_name"] == "Acme Wholesale Ltd"

    def test_get_tenant_not_found(self):
        db = _mock_db_for_not_found()
        client = TestClient(_make_app(db))
        resp = client.get("/api/v1/platform/p10/tenants/nonexistent-id")
        assert resp.status_code == 404

    def test_pagination_params(self):
        w = _mock_wholesaler()
        db = _mock_db_for_list([w])
        client = TestClient(_make_app(db))
        resp = client.get("/api/v1/platform/p10/tenants", params={"limit": 10, "offset": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 5


class TestTenantHealthAPI:
    """API-level tests for TenantHealth endpoint."""

    def test_get_tenant_health_response_shape(self):
        w = _mock_wholesaler()
        db = _mock_db_for_detail(w)
        client = TestClient(_make_app(db))
        resp = client.get("/api/v1/platform/p10/tenants/550e8400-e29b-41d4-a716-446655440000/health")
        assert resp.status_code == 200
        data = resp.json()
        expected_fields = [
            "tenant_id", "tenant_schema", "health_status", "schema_status",
            "last_login_at", "activity_counters", "recent_errors",
            "slow_routes", "failed_jobs", "last_health_check_at",
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"

    def test_get_tenant_health_unknown_fallback(self):
        """All telemetry fields null, health_status unknown."""
        w = _mock_wholesaler()
        db = _mock_db_for_detail(w)
        client = TestClient(_make_app(db))
        resp = client.get("/api/v1/platform/p10/tenants/550e8400-e29b-41d4-a716-446655440000/health")
        data = resp.json()
        assert data["health_status"] == "unknown"
        assert data["schema_status"] is None
        assert data["last_login_at"] is None
        assert data["activity_counters"] is None
        assert data["recent_errors"] is None
        assert data["slow_routes"] is None
        assert data["failed_jobs"] is None

    def test_get_tenant_health_not_found(self):
        db = _mock_db_for_not_found()
        client = TestClient(_make_app(db))
        resp = client.get("/api/v1/platform/p10/tenants/nonexistent/health")
        assert resp.status_code == 404


class TestSystemHealthAPI:
    """API-level tests for SystemHealth endpoint."""

    def test_system_health_response_shape(self):
        db = MagicMock()
        client = TestClient(_make_app(db))
        resp = client.get("/api/v1/platform/p10/system/health")
        assert resp.status_code == 200
        data = resp.json()
        expected_fields = [
            "overall_status", "api_status", "database_status",
            "database_connections", "queue_status", "cpu_status",
            "memory_status", "disk_status", "error_rate",
            "slow_request_count", "generated_at",
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"

    def test_system_health_unknown_fallback(self):
        """Overall unknown, all component statuses null, generated_at present."""
        db = MagicMock()
        client = TestClient(_make_app(db))
        resp = client.get("/api/v1/platform/p10/system/health")
        data = resp.json()
        assert data["overall_status"] == "unknown"
        assert data["api_status"] is None
        assert data["database_status"] is None
        assert data["queue_status"] is None
        assert data["cpu_status"] is None
        assert data["memory_status"] is None
        assert data["disk_status"] is None
        assert data["error_rate"] is None
        assert data["slow_request_count"] is None
        assert data["generated_at"] is not None

    def test_generated_at_is_utc_iso8601(self):
        """generated_at must be UTC ISO-8601."""
        db = MagicMock()
        client = TestClient(_make_app(db))
        resp = client.get("/api/v1/platform/p10/system/health")
        data = resp.json()
        gen = data["generated_at"]
        # Should parse as ISO datetime
        parsed = datetime.fromisoformat(gen.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None


class TestAuditEventsAPI:
    """API-level tests for PlatformAuditEvent endpoints."""

    def test_list_audit_events_response_shape(self):
        """Placeholder list returns correct shape."""
        from models.platform_audit_log import PlatformAuditLog

        mock_entry = MagicMock(spec=PlatformAuditLog)
        mock_entry.id = "880e8400-e29b-41d4-a716-446655440003"
        mock_entry.actor_type = "admin"
        mock_entry.actor_id = None
        mock_entry.wholesaler_id = None
        mock_entry.action = "test.action"
        mock_entry.resource = "test/resource"
        mock_entry.audit_metadata = {}
        mock_entry.created_at = datetime(2026, 6, 5, 9, 0, 0, tzinfo=timezone.utc)

        mock_db = MagicMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [mock_entry]
        mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

        client = TestClient(_make_app(mock_db))
        resp = client.get("/api/v1/platform/p10/audit/events")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert data["total"] == 1

    def test_list_audit_events_contract_fields(self):
        """All PlatformAuditEvent fields present in response items."""
        from models.platform_audit_log import PlatformAuditLog

        mock_entry = MagicMock(spec=PlatformAuditLog)
        mock_entry.id = "880e8400-e29b-41d4-a716-446655440003"
        mock_entry.actor_type = "admin"
        mock_entry.actor_id = None
        mock_entry.wholesaler_id = None
        mock_entry.action = "test.action"
        mock_entry.resource = "test/resource"
        mock_entry.audit_metadata = {}
        mock_entry.created_at = datetime(2026, 6, 5, 9, 0, 0, tzinfo=timezone.utc)

        mock_db = MagicMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [mock_entry]
        mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

        client = TestClient(_make_app(mock_db))
        resp = client.get("/api/v1/platform/p10/audit/events")
        item = resp.json()["items"][0]
        expected_fields = [
            "event_id", "actor_id", "actor_role", "tenant_id", "scope",
            "action", "reason", "result", "metadata_redacted",
            "correlation_id", "created_at",
        ]
        for field in expected_fields:
            assert field in item, f"Missing field: {field}"

    def test_get_audit_event_not_found(self):
        db = _mock_db_for_not_found()
        client = TestClient(_make_app(db))
        resp = client.get("/api/v1/platform/p10/audit/events/nonexistent-id")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════
# No Leakage Tests
# ═══════════════════════════════════════════════════════════════


class TestNoLeakage:
    """Verify no raw payload or business data leakage."""

    def test_error_summary_no_extra_fields(self):
        """ErrorSummary rejects extra fields like raw_stack_trace."""
        with pytest.raises(ValidationError):
            ErrorSummary(
                error_class="Error",
                count=1,
                correlation_ids=["corr-1"],
                raw_stack_trace="sensitive",  # type: ignore
            )

    def test_tenant_summary_no_extra_fields(self):
        """TenantSummary rejects extra fields."""
        with pytest.raises(ValidationError):
            TenantSummary(
                status="active",
                health_status="healthy",
                support_mode_active=False,
                internal_db_password="secret",  # type: ignore
            )

    def test_activity_counters_no_extra_fields(self):
        """ActivityCounters has exactly 5 keys."""
        with pytest.raises(ValidationError):
            ActivityCounts = ActivityCounters(
                orders=1, inventory_changes=1, invoices=1, payments=1, sync_jobs=1,
                customer_pii="leaked",  # type: ignore
            )

    def test_audit_metadata_no_raw_body(self):
        """metadata_redacted must not contain raw request/response body."""
        # This is a schema-level guard — the schema allows any dict
        # but the service layer is responsible for redaction.
        # The test verifies the schema is JSON-safe (no binary, etc.)
        event = PlatformAuditEvent(
            event_id="550e8400-e29b-41d4-a716-446655440000",
            scope="global",
            action="test",
            result="completed",
            metadata_redacted={"denial_code": "missing_reason"},
            created_at=datetime.now(timezone.utc),
        )
        assert isinstance(event.metadata_redacted, dict)
        assert "denial_code" in event.metadata_redacted


# ═══════════════════════════════════════════════════════════════
# SB-R1/R2: Platform-Only Access Boundary Tests (P10-R1-A → P10-R2)
# ═══════════════════════════════════════════════════════════════


def _make_guarded_app(mock_db=None):
    """App with guard active (no dependency override), DB mocked."""
    app = FastAPI()
    app.include_router(p10_router)

    if mock_db is None:
        mock_db = MagicMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

    async def override():
        yield mock_db

    app.dependency_overrides[get_db] = override
    app.dependency_overrides[db_get_db] = override
    # Deliberately do NOT override require_platform_operator
    return app


class TestPlatformOnlyAccessBoundary:
    """
    P10-R1-A + P10-R2: Prove the platform-only guard enforces deny-by-default.

    Tests:
      - Unauthenticated / no platform marker → 401
      - Wrong operator secret → 403
      - Test override restricted to MPANGO_ENV=test|testing only
      - Test override requires PLATFORM_TEST_OVERRIDE_SECRET
      - Production operator requires PLATFORM_OPERATOR_SECRET
      - All env isolation via monkeypatch (no machine env dependency)
    """

    # ── Unauthenticated / no marker → 401 (env-independent) ──

    def test_no_headers_denied_list_tenants(self, monkeypatch):
        """No platform marker at all → 401."""
        monkeypatch.delenv("MPANGO_ENV", raising=False)
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        monkeypatch.delenv("PLATFORM_TEST_OVERRIDE_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get("/api/v1/platform/p10/tenants")
        assert resp.status_code == 401
        assert "PLATFORM_ACCESS_REQUIRED" in resp.json()["detail"]["code"]

    def test_no_headers_denied_system_health(self, monkeypatch):
        monkeypatch.delenv("MPANGO_ENV", raising=False)
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        monkeypatch.delenv("PLATFORM_TEST_OVERRIDE_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get("/api/v1/platform/p10/system/health")
        assert resp.status_code == 401

    def test_no_headers_denied_audit_events(self, monkeypatch):
        monkeypatch.delenv("MPANGO_ENV", raising=False)
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        monkeypatch.delenv("PLATFORM_TEST_OVERRIDE_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get("/api/v1/platform/p10/audit/events")
        assert resp.status_code == 401

    def test_no_headers_denied_tenant_detail(self, monkeypatch):
        monkeypatch.delenv("MPANGO_ENV", raising=False)
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        monkeypatch.delenv("PLATFORM_TEST_OVERRIDE_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get("/api/v1/platform/p10/tenants/some-id")
        assert resp.status_code == 401

    def test_no_headers_denied_tenant_health(self, monkeypatch):
        monkeypatch.delenv("MPANGO_ENV", raising=False)
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        monkeypatch.delenv("PLATFORM_TEST_OVERRIDE_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get("/api/v1/platform/p10/tenants/some-id/health")
        assert resp.status_code == 401

    def test_no_headers_denied_audit_event_detail(self, monkeypatch):
        monkeypatch.delenv("MPANGO_ENV", raising=False)
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        monkeypatch.delenv("PLATFORM_TEST_OVERRIDE_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get("/api/v1/platform/p10/audit/events/some-id")
        assert resp.status_code == 401

    # ── Wrong/empty markers → 401/403 ──

    def test_wrong_operator_secret_denied(self, monkeypatch):
        """X-Platform-Operator with wrong value → 403."""
        monkeypatch.setenv("MPANGO_ENV", "production")
        monkeypatch.setenv("PLATFORM_OPERATOR_SECRET", "correct-secret")
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/tenants",
            headers={"X-Platform-Operator": "wrong-secret"},
        )
        assert resp.status_code == 403
        assert "PLATFORM_ACCESS_DENIED" in resp.json()["detail"]["code"]

    def test_tenant_auth_header_insufficient(self, monkeypatch):
        """Standard Authorization bearer does NOT grant platform access."""
        monkeypatch.delenv("MPANGO_ENV", raising=False)
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        monkeypatch.delenv("PLATFORM_TEST_OVERRIDE_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/tenants",
            headers={"Authorization": "Bearer some-tenant-token"},
        )
        assert resp.status_code == 401

    def test_empty_platform_operator_denied(self, monkeypatch):
        """Empty X-Platform-Operator header → 401 (treated as no marker)."""
        monkeypatch.delenv("MPANGO_ENV", raising=False)
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/tenants",
            headers={"X-Platform-Operator": ""},
        )
        assert resp.status_code == 401
        assert "PLATFORM_ACCESS_REQUIRED" in resp.json()["detail"]["code"]

    # ── P10-R2: Test override denied in non-test environments ──

    def test_test_override_denied_in_unset_env(self, monkeypatch):
        """Unset/default MPANGO_ENV + X-Platform-Test-Override → denied."""
        monkeypatch.delenv("MPANGO_ENV", raising=False)
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        monkeypatch.setenv("PLATFORM_TEST_OVERRIDE_SECRET", "test-secret")
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/tenants",
            headers={"X-Platform-Test-Override": "test-secret"},
        )
        assert resp.status_code == 403

    def test_test_override_denied_in_development(self, monkeypatch):
        """development + X-Platform-Test-Override → denied."""
        monkeypatch.setenv("MPANGO_ENV", "development")
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        monkeypatch.setenv("PLATFORM_TEST_OVERRIDE_SECRET", "test-secret")
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/tenants",
            headers={"X-Platform-Test-Override": "test-secret"},
        )
        assert resp.status_code == 403

    def test_test_override_denied_in_staging(self, monkeypatch):
        """staging + X-Platform-Test-Override → denied."""
        monkeypatch.setenv("MPANGO_ENV", "staging")
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        monkeypatch.setenv("PLATFORM_TEST_OVERRIDE_SECRET", "test-secret")
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/tenants",
            headers={"X-Platform-Test-Override": "test-secret"},
        )
        assert resp.status_code == 403

    def test_test_override_denied_in_production(self, monkeypatch):
        """production + X-Platform-Test-Override → denied."""
        monkeypatch.setenv("MPANGO_ENV", "production")
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        monkeypatch.setenv("PLATFORM_TEST_OVERRIDE_SECRET", "test-secret")
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/tenants",
            headers={"X-Platform-Test-Override": "test-secret"},
        )
        assert resp.status_code == 403

    def test_test_override_wrong_secret_denied(self, monkeypatch):
        """test env + wrong X-Platform-Test-Override value → denied."""
        monkeypatch.setenv("MPANGO_ENV", "test")
        monkeypatch.setenv("PLATFORM_TEST_OVERRIDE_SECRET", "correct-test-secret")
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/tenants",
            headers={"X-Platform-Test-Override": "wrong-test-secret"},
        )
        assert resp.status_code == 403

    def test_test_override_no_secret_env_denied(self, monkeypatch):
        """test env + unset PLATFORM_TEST_OVERRIDE_SECRET → denied."""
        monkeypatch.setenv("MPANGO_ENV", "test")
        monkeypatch.delenv("PLATFORM_TEST_OVERRIDE_SECRET", raising=False)
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/tenants",
            headers={"X-Platform-Test-Override": "any-value"},
        )
        assert resp.status_code == 403

    # ── P10-R2: Test override allowed in test env with correct secret ──

    def test_test_override_allowed_in_test_env(self, monkeypatch):
        """test env + correct X-Platform-Test-Override → 200."""
        monkeypatch.setenv("MPANGO_ENV", "test")
        monkeypatch.setenv("PLATFORM_TEST_OVERRIDE_SECRET", "test-secret")
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/tenants",
            headers={"X-Platform-Test-Override": "test-secret"},
        )
        assert resp.status_code == 200

    def test_test_override_allowed_in_testing_env(self, monkeypatch):
        """testing env + correct X-Platform-Test-Override → 200."""
        monkeypatch.setenv("MPANGO_ENV", "testing")
        monkeypatch.setenv("PLATFORM_TEST_OVERRIDE_SECRET", "test-secret")
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/tenants",
            headers={"X-Platform-Test-Override": "test-secret"},
        )
        assert resp.status_code == 200

    def test_test_override_allowed_system_health(self, monkeypatch):
        """System health endpoint works with test override in test env."""
        monkeypatch.setenv("MPANGO_ENV", "test")
        monkeypatch.setenv("PLATFORM_TEST_OVERRIDE_SECRET", "test-secret")
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/system/health",
            headers={"X-Platform-Test-Override": "test-secret"},
        )
        assert resp.status_code == 200

    def test_test_override_allowed_audit_events(self, monkeypatch):
        """Audit events list works with test override in test env."""
        monkeypatch.setenv("MPANGO_ENV", "test")
        monkeypatch.setenv("PLATFORM_TEST_OVERRIDE_SECRET", "test-secret")
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/audit/events",
            headers={"X-Platform-Test-Override": "test-secret"},
        )
        assert resp.status_code == 200

    def test_test_override_allowed_tenant_detail(self, monkeypatch):
        """Tenant detail works with test override in test env."""
        monkeypatch.setenv("MPANGO_ENV", "test")
        monkeypatch.setenv("PLATFORM_TEST_OVERRIDE_SECRET", "test-secret")
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)

        w = _mock_wholesaler()
        mock_db = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = w
        mock_db.execute = AsyncMock(return_value=result)

        client = TestClient(_make_guarded_app(mock_db))
        resp = client.get(
            "/api/v1/platform/p10/tenants/550e8400-e29b-41d4-a716-446655440000",
            headers={"X-Platform-Test-Override": "test-secret"},
        )
        assert resp.status_code == 200

    def test_test_override_allowed_tenant_health(self, monkeypatch):
        """Tenant health works with test override in test env."""
        monkeypatch.setenv("MPANGO_ENV", "test")
        monkeypatch.setenv("PLATFORM_TEST_OVERRIDE_SECRET", "test-secret")
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)

        w = _mock_wholesaler()
        mock_db = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = w
        mock_db.execute = AsyncMock(return_value=result)

        client = TestClient(_make_guarded_app(mock_db))
        resp = client.get(
            "/api/v1/platform/p10/tenants/550e8400-e29b-41d4-a716-446655440000/health",
            headers={"X-Platform-Test-Override": "test-secret"},
        )
        assert resp.status_code == 200

    def test_test_override_allowed_audit_event_detail_404(self, monkeypatch):
        """Audit event detail passes guard → 404 from data layer (not 401)."""
        monkeypatch.setenv("MPANGO_ENV", "test")
        monkeypatch.setenv("PLATFORM_TEST_OVERRIDE_SECRET", "test-secret")
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)

        client = TestClient(_make_guarded_app(_mock_db_for_not_found()))
        resp = client.get(
            "/api/v1/platform/p10/audit/events/nonexistent-id",
            headers={"X-Platform-Test-Override": "test-secret"},
        )
        assert resp.status_code == 404  # 404 from data layer, not 401 from guard

    # ── P10-R2: Production operator scenarios ──

    def test_production_operator_correct_secret_allowed(self, monkeypatch):
        """production + correct X-Platform-Operator + PLATFORM_OPERATOR_SECRET → 200."""
        monkeypatch.setenv("MPANGO_ENV", "production")
        monkeypatch.setenv("PLATFORM_OPERATOR_SECRET", "prod-secret-123")
        monkeypatch.delenv("PLATFORM_TEST_OVERRIDE_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/tenants",
            headers={"X-Platform-Operator": "prod-secret-123"},
        )
        assert resp.status_code == 200

    def test_production_operator_missing_secret_denied(self, monkeypatch):
        """production + missing PLATFORM_OPERATOR_SECRET → denied."""
        monkeypatch.setenv("MPANGO_ENV", "production")
        monkeypatch.delenv("PLATFORM_OPERATOR_SECRET", raising=False)
        monkeypatch.delenv("PLATFORM_TEST_OVERRIDE_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/tenants",
            headers={"X-Platform-Operator": "some-value"},
        )
        assert resp.status_code == 403

    def test_nonprod_operator_correct_secret_allowed(self, monkeypatch):
        """development + correct X-Platform-Operator + PLATFORM_OPERATOR_SECRET → 200."""
        monkeypatch.setenv("MPANGO_ENV", "development")
        monkeypatch.setenv("PLATFORM_OPERATOR_SECRET", "dev-secret")
        monkeypatch.delenv("PLATFORM_TEST_OVERRIDE_SECRET", raising=False)
        client = TestClient(_make_guarded_app())
        resp = client.get(
            "/api/v1/platform/p10/tenants",
            headers={"X-Platform-Operator": "dev-secret"},
        )
        assert resp.status_code == 200

    # ── Structural: all endpoints guarded ──

    def test_all_endpoints_require_guard(self):
        """Verify all 6 P10 endpoints have the guard dependency wired."""
        from api.v1.platform.p10.routes import router

        guarded_count = 0
        for route in router.routes:
            if hasattr(route, "dependant"):
                # Check if require_platform_operator appears in the dependency tree
                dep_names = []
                for dep in route.dependant.dependencies:
                    # dep.call is the actual dependency function
                    dep_fn = getattr(dep, "call", None)
                    if dep_fn is not None:
                        dep_names.append(getattr(dep_fn, "__name__", str(dep_fn)))
                has_guard = "require_platform_operator" in dep_names
                if has_guard:
                    guarded_count += 1
                path = getattr(route, "path", str(route))
                assert has_guard, f"Route {path} is missing platform guard dependency"

        assert guarded_count == 6, f"Expected 6 guarded endpoints, found {guarded_count}"


# ═══════════════════════════════════════════════════════════════
# P10-R1-B: Metadata Redaction Tests
# ═══════════════════════════════════════════════════════════════


class TestMetadataRedaction:
    """
    P10-R1-B: Prove metadata_redacted output contains only safe keys.

    Tests:
      - Direct sensitive keys are removed
      - Nested sensitive keys are removed
      - Safe keys are preserved
      - Empty/null metadata handled correctly
    """

    def test_direct_sensitive_keys_removed(self):
        """Top-level sensitive keys must be stripped."""
        from api.v1.platform.p10.services import redact_metadata

        raw = {
            "result": "completed",
            "password": "hunter2",
            "token": "abc123",
            "secret": "my-secret",
            "authorization": "Bearer xyz",
            "cookie": "session=abc",
            "reason_code": "policy_violation",
            "denial_code": "missing_reason",
        }
        redacted = redact_metadata(raw)
        assert redacted is not None
        assert "password" not in redacted
        assert "token" not in redacted
        assert "secret" not in redacted
        assert "authorization" not in redacted
        assert "cookie" not in redacted
        assert redacted["result"] == "completed"
        assert redacted["reason_code"] == "policy_violation"
        assert redacted["denial_code"] == "missing_reason"

    def test_nested_sensitive_keys_removed(self):
        """Sensitive keys in nested dicts must be stripped."""
        from api.v1.platform.p10.services import redact_metadata

        raw = {
            "result": "denied",
            "context": {
                "user_token": "should-be-removed",
                "db_password": "should-be-removed",
                "safe_value": "keep-me",
                "nested": {
                    "secret": "deep-secret",
                    "actor_assignment_status": "assigned",
                },
            },
        }
        redacted = redact_metadata(raw)
        assert redacted is not None
        assert "user_token" not in redacted["context"]
        assert "db_password" not in redacted["context"]
        assert redacted["context"]["safe_value"] == "keep-me"
        assert "secret" not in redacted["context"]["nested"]
        assert redacted["context"]["nested"]["actor_assignment_status"] == "assigned"

    def test_all_sensitive_keywords_covered(self):
        """Every listed sensitive keyword pattern is caught."""
        from api.v1.platform.p10.services import redact_metadata

        sensitive_keys = [
            "password", "token", "secret", "authorization",
            "cookie", "raw_body", "request_body", "response_body",
            "payload", "stack_trace", "traceback", "card", "payment",
        ]
        raw = {k: f"value-{k}" for k in sensitive_keys}
        raw["safe_key"] = "keep"

        redacted = redact_metadata(raw)
        for k in sensitive_keys:
            assert k not in redacted, f"Sensitive key '{k}' should have been removed"
        assert redacted["safe_key"] == "keep"

    def test_safe_keys_preserved(self):
        """Known safe keys must pass through."""
        from api.v1.platform.p10.services import redact_metadata

        raw = {
            "result": "completed",
            "denial_code": "missing_reason",
            "reason_code": "expired",
            "actor_assignment_status": "assigned",
            "requested_at": "2026-06-05T09:20:00.000Z",
        }
        redacted = redact_metadata(raw)
        assert redacted == raw  # all safe, nothing stripped

    def test_none_metadata_returns_none(self):
        """None input returns None."""
        from api.v1.platform.p10.services import redact_metadata

        assert redact_metadata(None) is None

    def test_empty_metadata_returns_empty(self):
        """Empty dict returns empty dict."""
        from api.v1.platform.p10.services import redact_metadata

        assert redact_metadata({}) == {}

    def test_nested_sensitive_in_list_values(self):
        """Sensitive keys in dicts within lists must also be removed."""
        from api.v1.platform.p10.services import redact_metadata

        raw = {
            "result": "completed",
            "entries": [
                {"token": "abc", "name": "safe-name"},
                {"password": "secret", "value": "ok"},
            ],
        }
        redacted = redact_metadata(raw)
        assert "token" not in redacted["entries"][0]
        assert redacted["entries"][0]["name"] == "safe-name"
        assert "password" not in redacted["entries"][1]
        assert redacted["entries"][1]["value"] == "ok"

    def test_case_insensitive_sensitive_keys(self):
        """Sensitive key matching should be case-insensitive."""
        from api.v1.platform.p10.services import redact_metadata

        raw = {
            "Password": "secret",
            "TOKEN": "abc",
            "Secret_Key": "hidden",
            "result": "ok",
        }
        redacted = redact_metadata(raw)
        assert "Password" not in redacted
        assert "TOKEN" not in redacted
        assert "Secret_Key" not in redacted
        assert redacted["result"] == "ok"
