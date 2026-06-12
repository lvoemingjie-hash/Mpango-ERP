"""
Pydantic schemas for P13 Operations Observability Cockpit API.

Aligned to docs/ai/PLATFORM_PRODUCT_P13_OPERATIONS_COCKPIT_CONTRACT.md (P13-A-R1).

Key design decisions:
  - source_status on telemetry-dependent summaries (not bare 0 for unknown).
  - Nullable totals when telemetry is unavailable.
  - Identity-only super_admin in P13-B (deferred roles post-auth gate).
  - No raw payloads, no credentials, no DB internals.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.v1.platform.p10.schemas import (
    ComponentStatus,
    HealthStatus,
    validate_uuid_v4_v7,
)
from pydantic import field_validator

# -- Enum literals matching P13-A-R1 contract --

OpsSourceStatus = Literal["available", "unavailable", "unknown"]

OpsAction = Literal[
    "ops_health_view",
    "ops_error_analysis_view",
    "ops_slow_route_view",
    "ops_resource_view",
    "ops_noisy_neighbor_view",
    "ops_tenant_view",
    "ops_access_denied",
]

OpsViewType = Literal[
    "health",
    "errors",
    "slow_routes",
    "resources",
    "noisy_neighbors",
    "tenant",
]


# -- ErrorRateSummary sub-structures --


class ErrorClassBreakdown(BaseModel):
    """Redacted error class breakdown -- no raw payloads."""

    model_config = ConfigDict(extra="forbid")

    error_class: str = Field(..., description="Redacted error class name")
    count: int = Field(..., ge=0, description="Error count")
    percentage: float = Field(..., ge=0.0, le=100.0, description="Percentage of total")
    sample_correlation_ids: list[str] = Field(
        ..., max_length=5, description="Up to 5 correlation IDs"
    )


class RouteErrorBreakdown(BaseModel):
    """Redacted route error breakdown -- route path only, no query params."""

    model_config = ConfigDict(extra="forbid")

    route: str = Field(..., description="Route path only (no query params)")
    error_count: int = Field(..., ge=0, description="Error count for this route")
    latency_bucket_ms: Optional[int] = Field(
        None, ge=0, description="P95 latency in ms, null if unavailable"
    )
    sample_correlation_ids: list[str] = Field(
        ..., max_length=5, description="Up to 5 correlation IDs"
    )


class TenantErrorBreakdown(BaseModel):
    """Redacted tenant error breakdown -- counts only, no business data."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., description="Tenant UUID")
    tenant_name: Optional[str] = Field(None, description="Display name if available")
    error_count: int = Field(..., ge=0, description="Error count for this tenant")
    top_error_class: Optional[str] = Field(
        None, description="Most frequent error class"
    )

    _validate_tenant_id = field_validator("tenant_id")(validate_uuid_v4_v7)


class ErrorRateSummary(BaseModel):
    """Aggregated error rate summary with source_status semantics.

    source_status controls null vs integer:
      - available: total_errors is an integer >= 0
      - unavailable/unknown: total_errors is null
    """

    model_config = ConfigDict(extra="forbid")

    source_status: OpsSourceStatus = Field(
        ..., description="available, unavailable, or unknown"
    )
    window_minutes: int = Field(..., gt=0, description="Aggregation window")
    total_errors: Optional[int] = Field(
        None, ge=0,
        description="Total errors when available, null when source unavailable",
    )
    error_classes: list[ErrorClassBreakdown] = Field(
        default_factory=list, description="Empty when source unavailable"
    )
    top_routes: list[RouteErrorBreakdown] = Field(
        default_factory=list, description="Empty when source unavailable"
    )
    top_tenants: Optional[list[TenantErrorBreakdown]] = Field(
        None, description="null if actor lacks cross-tenant scope or source unavailable"
    )
    generated_at: datetime = Field(..., description="UTC ISO-8601")

    @model_validator(mode="after")
    def check_source_status_consistency(self) -> "ErrorRateSummary":
        """Enforce source_status / total_errors contract.

        - available: total_errors must be an integer >= 0 (not None).
        - unavailable/unknown: total_errors must be None.
        """
        if self.source_status == "available":
            if self.total_errors is None:
                raise ValueError(
                    "total_errors must be an integer >= 0 when source_status is 'available'"
                )
        else:
            if self.total_errors is not None:
                raise ValueError(
                    f"total_errors must be None when source_status is '{self.source_status}'"
                )
        return self


# -- SlowRouteSummary sub-structures --


class SlowRouteEntry(BaseModel):
    """Redacted slow route entry -- route path only, no query params."""

    model_config = ConfigDict(extra="forbid")

    route: str = Field(..., description="Route path only")
    request_count: int = Field(..., ge=0, description="Request count")
    p50_ms: Optional[int] = Field(None, ge=0, description="P50 latency, null if unavailable")
    p95_ms: Optional[int] = Field(None, ge=0, description="P95 latency, null if unavailable")
    p99_ms: Optional[int] = Field(None, ge=0, description="P99 latency, null if unavailable")
    sample_correlation_ids: list[str] = Field(
        ..., max_length=5, description="Up to 5 correlation IDs"
    )


class SlowRouteSummary(BaseModel):
    """Aggregated slow route summary with source_status semantics."""

    model_config = ConfigDict(extra="forbid")

    source_status: OpsSourceStatus = Field(
        ..., description="available, unavailable, or unknown"
    )
    window_minutes: int = Field(..., gt=0, description="Aggregation window")
    threshold_ms: int = Field(..., gt=0, description="Slow threshold in ms")
    total_slow_requests: Optional[int] = Field(
        None, ge=0,
        description="Total slow requests when available, null when source unavailable",
    )
    routes: list[SlowRouteEntry] = Field(
        default_factory=list, description="Empty when source unavailable"
    )
    generated_at: datetime = Field(..., description="UTC ISO-8601")

    @model_validator(mode="after")
    def check_source_status_consistency(self) -> "SlowRouteSummary":
        """Enforce source_status / total_slow_requests contract.

        - available: total_slow_requests must be an integer >= 0 (not None).
        - unavailable/unknown: total_slow_requests must be None.
        """
        if self.source_status == "available":
            if self.total_slow_requests is None:
                raise ValueError(
                    "total_slow_requests must be an integer >= 0 when source_status is 'available'"
                )
        else:
            if self.total_slow_requests is not None:
                raise ValueError(
                    f"total_slow_requests must be None when source_status is '{self.source_status}'"
                )
        return self


# -- ResourceHealthSummary sub-structures --


class DatabaseHealth(BaseModel):
    """Database connection pool health."""

    model_config = ConfigDict(extra="forbid")

    status: HealthStatus = Field(..., description="healthy, degraded, unhealthy, or unknown")
    connection_pool_active: Optional[int] = Field(
        None, ge=0, description="Active connections, null if unavailable"
    )
    connection_pool_max: Optional[int] = Field(
        None, ge=1, description="Pool max, null if unavailable"
    )
    connection_pool_idle: Optional[int] = Field(
        None, ge=0, description="Idle connections, null if unavailable"
    )
    latency_ms: Optional[int] = Field(
        None, ge=0, description="Average query latency, null if unavailable"
    )


class QueueHealth(BaseModel):
    """Queue health summary."""

    model_config = ConfigDict(extra="forbid")

    status: HealthStatus = Field(..., description="healthy, degraded, unhealthy, or unknown")
    depth: Optional[int] = Field(None, ge=0, description="Queue depth, null if unavailable")
    worker_count: Optional[int] = Field(
        None, ge=0, description="Active workers, null if unavailable"
    )
    oldest_pending_age_s: Optional[int] = Field(
        None, ge=0, description="Oldest pending job age in seconds, null if unavailable"
    )


class ComponentHealth(BaseModel):
    """Generic component health (CPU, memory, disk)."""

    model_config = ConfigDict(extra="forbid")

    status: HealthStatus = Field(..., description="healthy, degraded, unhealthy, or unknown")
    usage_percent: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Usage percentage, null if unavailable"
    )
    detail: Optional[str] = Field(
        None, description="Human-readable note"
    )


class ResourceHealthSummary(BaseModel):
    """Resource health summary covering DB, queue, memory, CPU, disk."""

    model_config = ConfigDict(extra="forbid")

    database: DatabaseHealth = Field(..., description="Database health")
    queue: Optional[QueueHealth] = Field(
        None, description="Queue health, null if no queue configured"
    )
    memory: Optional[ComponentHealth] = Field(
        None, description="Memory health, null if not instrumented"
    )
    cpu: Optional[ComponentHealth] = Field(
        None, description="CPU health, null if not instrumented"
    )
    disk: Optional[ComponentHealth] = Field(
        None, description="Disk health, null if not instrumented"
    )
    generated_at: datetime = Field(..., description="UTC ISO-8601")


# -- NoisyNeighborSummary sub-structures --


class NoisyNeighborEntry(BaseModel):
    """Single tenant in noisy-neighbor analysis -- counts only."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., description="Tenant UUID")
    tenant_name: Optional[str] = Field(None, description="Display name")
    error_count: int = Field(..., ge=0, description="Error count")
    slow_route_count: int = Field(..., ge=0, description="Slow route count")
    impact_score: float = Field(
        ..., ge=0.0, le=1.0, description="Derived impact score 0.0-1.0"
    )
    top_error_class: Optional[str] = Field(None, description="Most frequent error class")
    top_slow_route: Optional[str] = Field(None, description="Most frequent slow route")

    _validate_tenant_id = field_validator("tenant_id")(validate_uuid_v4_v7)


class NoisyNeighborSummary(BaseModel):
    """Noisy-neighbor analysis -- tenants with disproportionate impact."""

    model_config = ConfigDict(extra="forbid")

    window_minutes: int = Field(..., gt=0, description="Aggregation window")
    tenants: list[NoisyNeighborEntry] = Field(
        default_factory=list,
        description="Sorted by impact descending, empty when source unavailable",
    )
    generated_at: datetime = Field(..., description="UTC ISO-8601")
