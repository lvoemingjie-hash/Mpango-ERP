"""
S6-3: Dashboard API Schemas — Pydantic Models for Request/Response.

Philosophy: "If it's not in the Enum, it doesn't exist."

These schemas enforce the semantic whitelist at the API boundary.
Invalid enum values are rejected by Pydantic BEFORE reaching the
service layer. The frontend cannot invent new metrics or dimensions.

API Contract Compliance (api_contract.md §3):
- All success responses use: {"success": true, "data": {...}, "timestamp": "..."}
- All error responses use:   {"success": false, "error": {"code": ..., "message": ...}, "timestamp": "..."}
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from services.reporting.semantic_layer import (
    ViewScope,
    ReportMetric,
    ReportDimension,
    TimeGranularity,
)


# ============================================================================
# Request Schemas
# ============================================================================

class SemanticQueryRequest(BaseModel):
    """
    Ad-hoc analysis request (POST /reports/analyze).

    The frontend sends business-semantic enums, NEVER raw column names.
    Pydantic validates the enums — if a value is not in ReportMetric or
    ReportDimension, the request is rejected with a 422 error.
    """
    #[Constraint Check] Rule #4: view MUST be a whitelisted ViewScope Enum — NO dynamic strings
    view: ViewScope = Field(
        ...,
        description="Which reporting view to query (whitelist enforced)"
    )
    #[Constraint Check] Rule #4: metrics MUST be whitelisted ReportMetric Enums — NO dynamic strings
    metrics: list[ReportMetric] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Business metrics to retrieve"
    )
    #[Constraint Check] Rule #4: dimensions MUST be whitelisted ReportDimension Enums — NO dynamic strings
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
    limit: int = Field(
        default=500,
        ge=1,
        le=10000,
        description="Maximum rows to return"
    )

    model_config = {"json_schema_extra": {
        "examples": [{
            "view": "sales_daily",
            "metrics": ["revenue", "transaction_count"],
            "dimensions": ["date", "currency"],
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
            "limit": 500,
        }]
    }}


# ============================================================================
# Inner Data Schemas (nested inside the envelope)
# ============================================================================

class KpiCard(BaseModel):
    """Single KPI card for dashboard header."""
    label: str = Field(..., description="Human-readable metric name")
    value: float = Field(..., description="Metric value (0 if no data)")
    currency: str = Field(default="USD", description="ISO 4217 currency code")
    trend: Optional[str] = Field(
        default=None,
        description="Trend indicator: 'up', 'down', 'flat', or null"
    )


class KpiSummaryData(BaseModel):
    """Inner data for KPI summary response."""
    tenant_id: str
    generated_at: str = Field(..., description="ISO 8601 timestamp")
    cards: list[KpiCard]
    currency: str = Field(default="USD")


class ChartDataPoint(BaseModel):
    """Single data point in a time-series chart."""
    date: str = Field(..., description="ISO 8601 date")
    value: float = Field(..., description="Metric value")
    currency: str = Field(default="USD")


class ChartData(BaseModel):
    """Inner data for chart response."""
    tenant_id: str
    chart_type: str = Field(..., description="Chart identifier")
    granularity: str
    data: list[ChartDataPoint]
    currency: str = Field(default="USD")


class AnalyzeData(BaseModel):
    """Inner data for ad-hoc analysis response."""
    tenant_id: str
    view: str
    row_count: int
    rows: list[dict[str, Any]]
    currency: str = Field(default="USD")
    is_materialized: bool = Field(
        ...,
        description="True if data may be stale (materialized view)"
    )


class ViewSchemaData(BaseModel):
    """Inner data for view schema discovery response."""
    view: str
    is_materialized: bool
    metrics: list[dict[str, str]]
    dimensions: list[dict[str, str]]
    currency: str = Field(default="USD")


# ============================================================================
# API Contract Envelope Responses (§3.1 / §3.3)
# ============================================================================

class SuccessResponse(BaseModel):
    """
    Unified success envelope per api_contract.md §3.1.

    All dashboard/reporting endpoints wrap their data in this envelope.
    """
    success: bool = Field(default=True)
    data: Any
    message: Optional[str] = Field(default=None)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ErrorDetail(BaseModel):
    """Single field-level error detail."""
    field: Optional[str] = None
    message: str
    meta: Optional[dict[str, Any]] = None


class ErrorBody(BaseModel):
    """Error body per api_contract.md §3.3."""
    code: str
    message: str
    details: Optional[list[ErrorDetail]] = None
    available_values: Optional[list[str]] = Field(
        default=None,
        description="Valid enum values if the error is about invalid input"
    )


class ErrorResponse(BaseModel):
    """
    Unified error envelope per api_contract.md §3.3.

    All dashboard/reporting error responses use this format.
    """
    success: bool = Field(default=False)
    error: ErrorBody
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ============================================================================
# Helper: Build envelope responses
# ============================================================================

def make_success(data: Any, message: Optional[str] = None) -> dict[str, Any]:
    """Build a success envelope dict matching api_contract.md §3.1."""
    return {
        "success": True,
        "data": data if isinstance(data, dict) else data.model_dump(),
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def make_error(
    code: str,
    message: str,
    details: Optional[list[dict]] = None,
    available_values: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Build an error envelope dict matching api_contract.md §3.3."""
    error_body: dict[str, Any] = {"code": code, "message": message}
    if details:
        error_body["details"] = details
    if available_values:
        error_body["available_values"] = available_values
    return {
        "success": False,
        "error": error_body,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
