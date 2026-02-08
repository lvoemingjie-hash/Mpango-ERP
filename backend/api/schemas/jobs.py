"""
S6-4: Export Job Schemas — Pydantic Models for Async Export Requests.

Philosophy: "The export request is captured in HTTP context. The worker
reconstructs it from a serialized payload. tenant_id MUST survive the hop."

Context Propagation:
    POST /exports (HTTP context, JWT-authenticated)
        → ExportRequest (Pydantic validates enums at boundary)
        → ExportJobPayload (serializable dict for S4 Job Queue)
        → export_worker (detached worker, reconstructs tenant context)

Security:
    - tenant_id and tenant_schema are serialized INTO the payload at the
      API layer (from request.state, which comes from JWT).
    - The worker MUST reject payloads missing tenant_id.
    - All view/metric/dimension fields are enum values (strings), re-validated
      by the worker before constructing SemanticQueryBuilder.
"""
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from services.reporting.semantic_layer import (
    ViewScope,
    ReportMetric,
    ReportDimension,
)


# ============================================================================
# Export Format Enum
# ============================================================================

class ExportFormat(str, Enum):
    """Supported export file formats."""
    CSV = "csv"
    XLSX = "xlsx"


# ============================================================================
# API Request Schema (received by POST /exports)
# ============================================================================

class ExportRequest(BaseModel):
    """
    Export request from the frontend.

    Same semantic contract as SemanticQueryRequest (S6-3), plus format.
    All fields are whitelisted enums — no dynamic strings.
    """
    #[Constraint Check] Rule #4: view MUST be a whitelisted ViewScope Enum
    view: ViewScope = Field(
        ...,
        description="Which reporting view to export (whitelist enforced)"
    )
    #[Constraint Check] Rule #4: metrics MUST be whitelisted ReportMetric Enums
    metrics: list[ReportMetric] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Business metrics to export"
    )
    #[Constraint Check] Rule #4: dimensions MUST be whitelisted ReportDimension Enums
    dimensions: Optional[list[ReportDimension]] = Field(
        default=None,
        max_length=5,
        description="Grouping dimensions (optional)"
    )
    date_from: Optional[date] = Field(
        default=None,
        description="Start date filter (inclusive)"
    )
    date_to: Optional[date] = Field(
        default=None,
        description="End date filter (inclusive)"
    )
    format: ExportFormat = Field(
        default=ExportFormat.CSV,
        description="Output file format: csv or xlsx"
    )
    limit: int = Field(
        default=50000,
        ge=1,
        le=500000,
        description="Maximum rows to export (higher cap than ad-hoc)"
    )

    model_config = {"json_schema_extra": {
        "examples": [{
            "view": "sales_daily",
            "metrics": ["revenue", "transaction_count"],
            "dimensions": ["date", "currency"],
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "format": "csv",
            "limit": 50000,
        }]
    }}


# ============================================================================
# Job Payload Schema (serialized into S4 Job Queue)
# ============================================================================

class ExportJobPayload(BaseModel):
    """
    Serializable payload for the S4 Job Queue.

    This is what gets stored in public.sys_jobs.payload (JSON column).
    It MUST contain tenant_id and tenant_schema so the detached worker
    can reconstruct the tenant context without an HTTP request.

    Context Propagation Chain:
        JWT → request.state → TenantContext → ExportJobPayload → Worker
    """
    #[Constraint Check] Rule #1: tenant_id serialized from trusted HTTP context
    tenant_id: str = Field(
        ...,
        description="Tenant UUID from JWT claims (propagated to worker)"
    )
    tenant_schema: str = Field(
        ...,
        description="Tenant schema name (e.g., 't_abc123') for search_path"
    )
    user_id: str = Field(
        ...,
        description="Requesting user UUID (for audit trail)"
    )

    # Query parameters (enum values as strings for JSON serialization)
    view: str = Field(..., description="ViewScope enum value")
    metrics: list[str] = Field(..., description="ReportMetric enum values")
    dimensions: Optional[list[str]] = Field(
        default=None,
        description="ReportDimension enum values"
    )
    date_from: Optional[str] = Field(
        default=None,
        description="ISO date string"
    )
    date_to: Optional[str] = Field(
        default=None,
        description="ISO date string"
    )
    format: str = Field(default="csv", description="csv or xlsx")
    limit: int = Field(default=50000)

    @field_validator("tenant_id")
    @classmethod
    def tenant_id_must_not_be_empty(cls, v: str) -> str:
        """
        #[Constraint Check] Rule #1: Reject empty tenant_id.
        If the worker receives a payload without tenant_id, it would
        query the wrong schema (or public). This MUST NOT happen.
        """
        if not v or not v.strip():
            raise ValueError("tenant_id MUST NOT be empty in export payload")
        return v

    @field_validator("tenant_schema")
    @classmethod
    def tenant_schema_must_be_prefixed(cls, v: str) -> str:
        """Validate tenant schema has the expected prefix."""
        if not v or not v.startswith("t_"):
            raise ValueError(
                f"tenant_schema must start with 't_', got: '{v}'"
            )
        return v

    @classmethod
    def from_request(
        cls,
        request: "ExportRequest",
        tenant_id: str,
        tenant_schema: str,
        user_id: str,
    ) -> "ExportJobPayload":
        """
        Build a job payload from an HTTP request + tenant context.

        This is the ONLY approved way to create a payload. It captures
        the tenant context from the authenticated HTTP layer and serializes
        it alongside the query parameters.
        """
        return cls(
            tenant_id=tenant_id,
            tenant_schema=tenant_schema,
            user_id=user_id,
            view=request.view.value,
            metrics=[m.value for m in request.metrics],
            dimensions=[d.value for d in request.dimensions] if request.dimensions else None,
            date_from=request.date_from.isoformat() if request.date_from else None,
            date_to=request.date_to.isoformat() if request.date_to else None,
            format=request.format.value,
            limit=request.limit,
        )


# ============================================================================
# API Response Schemas
# ============================================================================

class ExportStatusData(BaseModel):
    """Inner data for export status response."""
    job_id: str
    status: str = Field(..., description="pending, running, completed, failed")
    format: str
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    download_url: Optional[str] = Field(
        default=None,
        description="Relative URL to download the file (available when completed)"
    )
    row_count: Optional[int] = Field(
        default=None,
        description="Number of rows exported (available when completed)"
    )
    file_size_bytes: Optional[int] = Field(
        default=None,
        description="File size in bytes (available when completed)"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message (available when failed)"
    )
