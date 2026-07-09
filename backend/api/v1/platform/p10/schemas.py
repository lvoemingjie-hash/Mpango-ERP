"""
Pydantic schemas for P10 Platform Product contracts.

Every schema is field-by-field aligned with PLATFORM_PRODUCT_CONTRACTS.md (P10-A-R1).
Nullable fields use Optional. Enum fields use Literal types for exact contract values.

Cross-contract rules enforced here:
  - UUIDs must be version 4 or 7 (validated by pattern).
  - Timestamps must be UTC ISO-8601.
  - Nullable fields return null when unavailable.
  - Non-nullable enums use documented fallbacks.
  - unknown != healthy.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── Enum literals matching PLATFORM_PRODUCT_CONTRACTS.md exactly ──

TenantStatus = Literal[
    "draft", "active", "paused", "suspended", "archived", "unknown"
]

HealthStatus = Literal["healthy", "degraded", "unhealthy", "unknown"]

ComponentStatus = Literal["healthy", "degraded", "down", "unknown"]

OverallStatus = Literal["healthy", "degraded", "down", "unknown"]

SchemaStatus = Literal[
    "exists", "unreachable", "migration_misaligned", "missing", "unknown"
]

ActorRole = Literal["super_admin", "support_operator", "engineering_operator"]

AuditScope = Literal["global", "tenant", "system", "support"]

AuditResult = Literal["allowed", "denied", "failed", "completed", "recorded"]


# ── UUID validation ──

UUID_V4_V7_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[4-7][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def validate_uuid_v4_v7(value: Optional[str]) -> Optional[str]:
    """Validate UUID is version 4 or 7. Reject nil UUIDs and v1 (leaks MAC)."""
    if value is None:
        return value
    if not UUID_V4_V7_PATTERN.match(value):
        raise ValueError(
            f"UUID must be version 4 or 7, got: {value}"
        )
    return value


# P25-EG: Platform read DTOs (TenantSummary, TenantHealth) surface tenant_id from
# legacy product tables (public.wholesalers.id) which may contain non-v4/v7 UUIDs
# (e.g. seeded test rows). A lenient validator accepts any valid UUID-format
# string so the read-only API never 500s on legacy rows. Strict v4/v7 stays in
# force for platform-generated identifiers (audit event_id).
UUID_ANY_VERSION_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def validate_uuid_any_version(value: Optional[str]) -> Optional[str]:
    """Validate UUID format (any version) for platform read DTOs.

    Accepts v1/v4/v7 and other valid UUID-format strings. Non-None values that
    are not valid UUID format are still rejected so slugs/garbage do not leak
    through; callers translate those into clean 404s via _coerce_tenant_id.
    """
    if value is None:
        return value
    if not UUID_ANY_VERSION_PATTERN.match(value):
        raise ValueError(f"Invalid UUID format, got: {value}")
    return value


# ── Sub-structures ──


class ErrorSummary(BaseModel):
    """Redacted error summary — no raw payloads allowed."""

    model_config = ConfigDict(extra="forbid")

    error_class: str = Field(..., description="Redacted error class name")
    count: int = Field(..., ge=1, description="Error count, must be >= 1")
    correlation_ids: list[str] = Field(
        ..., min_length=1, description="At least 1 redacted correlation ID"
    )

    @field_validator("error_class")
    @classmethod
    def no_raw_payload(cls, v: str) -> str:
        if "traceback" in v.lower() or "stack" in v.lower():
            raise ValueError("error_class must not contain raw stack/traceback info")
        return v


class SlowRoute(BaseModel):
    """Redacted slow route — route name only, no full URLs."""

    model_config = ConfigDict(extra="forbid")

    route: str = Field(..., description="Route name only (no query params)")
    latency_bucket_ms: int = Field(..., ge=0, description="Latency bucket in ms")
    count: int = Field(..., ge=1, description="Observation count, must be >= 1")


class FailedJob(BaseModel):
    """Redacted failed job — class name and count only."""

    model_config = ConfigDict(extra="forbid")

    job_class: str = Field(..., description="Job class name only")
    count: int = Field(..., ge=1, description="Failure count, must be >= 1")


class DatabaseConnections(BaseModel):
    """Database connection pool snapshot."""

    model_config = ConfigDict(extra="forbid")

    active: int = Field(..., ge=0)
    idle: int = Field(..., ge=0)
    max: int = Field(..., ge=1)
    saturation_pct: float = Field(..., ge=0.0, le=100.0)


class ActivityCounters(BaseModel):
    """Windowed activity counts — no business details exposed."""

    model_config = ConfigDict(extra="forbid")

    orders: int = Field(..., ge=0)
    inventory_changes: int = Field(..., ge=0)
    invoices: int = Field(..., ge=0)
    payments: int = Field(..., ge=0)
    sync_jobs: int = Field(..., ge=0)


# ── Contract: TenantSummary ──


class TenantSummary(BaseModel):
    """
    Read-only summary of a tenant's operational state.

    Aligned to PLATFORM_PRODUCT_CONTRACTS.md §2.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: Optional[str] = Field(
        None, description="UUID v4/v7, null if registry not yet created"
    )
    tenant_name: Optional[str] = Field(
        None, description="null if registry not yet created"
    )
    tenant_schema: Optional[str] = Field(
        None, description="null if provisioning metadata unavailable"
    )
    status: TenantStatus = Field(
        ..., description="Tenant status, 'unknown' as fallback"
    )
    tier: Optional[str] = Field(
        None, description="null until subscription model exists"
    )
    created_at: Optional[datetime] = Field(
        None, description="null if creation metadata unavailable"
    )
    last_activity_at: Optional[datetime] = Field(
        None, description="null if tenant aggregate not available"
    )
    user_count: Optional[int] = Field(
        None, ge=0, description="null if aggregate unavailable, >= 0 if present"
    )
    health_status: HealthStatus = Field(
        ..., description="'unknown' if health signals unavailable"
    )
    recent_error_count: Optional[int] = Field(
        None, ge=0, description="null if telemetry not instrumented, >= 0 if present"
    )
    support_mode_active: bool = Field(
        ..., description="false if support mode not yet implemented"
    )

    _validate_tenant_id = field_validator("tenant_id")(validate_uuid_any_version)


class TenantSummaryList(BaseModel):
    """Paginated list of TenantSummary records."""

    items: list[TenantSummary]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)


# ── Contract: TenantHealth ──


class TenantHealth(BaseModel):
    """
    Read-only health assessment for a single tenant.

    Aligned to PLATFORM_PRODUCT_CONTRACTS.md §3.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: Optional[str] = Field(
        None, description="null if registry unavailable"
    )
    tenant_schema: Optional[str] = Field(
        None, description="null if provisioning data unavailable"
    )
    health_status: HealthStatus = Field(
        ..., description="'unknown' as fallback"
    )
    schema_status: Optional[SchemaStatus] = Field(
        None, description="null if DB metadata unavailable"
    )
    last_login_at: Optional[datetime] = Field(
        None, description="null if aggregate unavailable"
    )
    activity_counters: Optional[ActivityCounters] = Field(
        None, description="null if aggregation unavailable"
    )
    recent_errors: Optional[list[ErrorSummary]] = Field(
        None, description="null if logs unavailable"
    )
    slow_routes: Optional[list[SlowRoute]] = Field(
        None, description="null if metrics unavailable"
    )
    failed_jobs: Optional[list[FailedJob]] = Field(
        None, description="null if job telemetry unavailable"
    )
    last_health_check_at: Optional[datetime] = Field(
        None, description="null if no snapshot generated"
    )

    _validate_tenant_id = field_validator("tenant_id")(validate_uuid_any_version)


# ── Contract: SystemHealth ──


class SystemHealth(BaseModel):
    """
    Read-only aggregate health of the entire platform.

    Aligned to PLATFORM_PRODUCT_CONTRACTS.md §4.
    """

    model_config = ConfigDict(extra="forbid")

    overall_status: OverallStatus = Field(
        ..., description="'unknown' as fallback"
    )
    api_status: Optional[ComponentStatus] = Field(
        None, description="null if not instrumented"
    )
    database_status: Optional[ComponentStatus] = Field(
        None, description="null if not instrumented"
    )
    database_connections: Optional[DatabaseConnections] = Field(
        None, description="null if not instrumented"
    )
    queue_status: Optional[ComponentStatus] = Field(
        None, description="null if no queue present"
    )
    cpu_status: Optional[ComponentStatus] = Field(
        None, description="null if not instrumented (local/dev)"
    )
    memory_status: Optional[ComponentStatus] = Field(
        None, description="null if not instrumented (local/dev)"
    )
    disk_status: Optional[ComponentStatus] = Field(
        None, description="null if not instrumented (local/dev)"
    )
    error_rate: Optional[float] = Field(
        None, ge=0.0, description="null if not instrumented, >= 0 if present"
    )
    slow_request_count: Optional[int] = Field(
        None, ge=0, description="null if not instrumented, >= 0 if present"
    )
    generated_at: datetime = Field(
        ..., description="UTC ISO-8601, always available"
    )


# ── Contract: PlatformAuditEvent ──


class PlatformAuditEvent(BaseModel):
    """
    Append-only audit event for platform-level operations.

    Aligned to PLATFORM_PRODUCT_CONTRACTS.md §5.
    Read-only from the API perspective — entries are written by internal services only.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., description="UUID v4/v7, always generated")
    actor_id: Optional[str] = Field(
        None, description="null until platform auth exists"
    )
    actor_role: Optional[ActorRole] = Field(
        None, description="null until platform auth exists"
    )
    tenant_id: Optional[str] = Field(
        None, description="null for global-scope events"
    )
    scope: AuditScope = Field(..., description="Always required")
    action: str = Field(..., description="Always required")
    reason: Optional[str] = Field(
        None,
        description="null for actions not requiring reason; required for support/elevated views",
    )
    result: AuditResult = Field(..., description="Always required")
    metadata_redacted: Optional[dict] = Field(
        None, description="null if no metadata; never raw sensitive payload"
    )
    correlation_id: Optional[str] = Field(
        None, description="null if not yet correlated"
    )
    created_at: datetime = Field(..., description="Always required")

    _validate_event_id = field_validator("event_id")(validate_uuid_v4_v7)
    _validate_tenant_id = field_validator("tenant_id")(validate_uuid_v4_v7)

    @field_validator("reason")
    @classmethod
    def support_scope_requires_reason(cls, v: Optional[str], info) -> Optional[str]:
        """Support scope requires reason even for allowed actions (cross-contract rule)."""
        # This validator only fires on individual event creation.
        # Full cross-field validation is in validate_audit_event().
        return v


class PlatformAuditEventList(BaseModel):
    """Paginated list of PlatformAuditEvent records."""

    items: list[PlatformAuditEvent]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)


# ── Cross-contract validation helpers ──


def validate_tenant_summary_cross_rules(summary: TenantSummary) -> list[str]:
    """Validate cross-contract rules for TenantSummary. Returns list of violations."""
    violations: list[str] = []
    # C1: health_status cannot be "healthy" when all data sources are unknown
    if (
        summary.health_status == "healthy"
        and summary.recent_error_count is None
        and summary.last_activity_at is None
        and summary.user_count is None
    ):
        violations.append(
            "health_status cannot be 'healthy' when all health data sources are null"
        )
    return violations


def validate_system_health_cross_rules(health: SystemHealth) -> list[str]:
    """Validate cross-contract rules for SystemHealth. Returns list of violations."""
    violations: list[str] = []
    # C3: overall_status must not be "healthy" when any component is degraded/down
    if health.overall_status == "healthy":
        components = [
            health.api_status,
            health.database_status,
            health.queue_status,
            health.cpu_status,
            health.memory_status,
            health.disk_status,
        ]
        for c in components:
            if c in ("degraded", "down"):
                violations.append(
                    f"overall_status cannot be 'healthy' when a component is '{c}'"
                )
                break
    return violations


def validate_audit_event_cross_rules(event: PlatformAuditEvent) -> list[str]:
    """Validate cross-contract rules for PlatformAuditEvent. Returns list of violations."""
    violations: list[str] = []

    # C2: support scope with allowed/completed result requires reason
    if event.scope == "support" and event.result in ("allowed", "completed"):
        if event.reason is None:
            violations.append(
                "scope='support' with result='allowed'/'completed' requires reason"
            )

    # C5: tenant scope requires tenant_id
    if event.scope == "tenant" and event.tenant_id is None:
        violations.append("scope='tenant' requires non-null tenant_id")

    return violations
