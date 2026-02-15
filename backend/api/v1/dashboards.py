"""
S6-3: Dashboard & Reporting API Router — Controlled BI Facade.

Philosophy: "S6-3 ≠ Generic Query Engine. It is a Controlled BI Semantic Facade."

Architecture (Three-Tier, Strict Separation):

1. KPI Endpoints (GET /dashboards/kpi/*)
   - Hardcoded SQL/View, no user parameters
   - Used for: Dashboard header cards
   - NEVER calls generic SemanticQueryBuilder.build_query()

2. Chart Endpoints (GET /dashboards/charts/*)
   - Limited parameters: date_range + granularity ONLY
   - Metric is hardcoded per endpoint

3. Ad-hoc Analysis (POST /reports/analyze)
   - Calls SemanticQueryBuilder.build_query() with enum-validated input
   - All metrics/dimensions must be in the Enum whitelist

API Contract Compliance (api_contract.md §3):
- All success responses: {"success": true, "data": {...}, "timestamp": "..."}
- All error responses:   {"success": false, "error": {"code": ..., "message": ...}, "timestamp": "..."}

Security:
- Tenant is SCOPE, not filter — derived from JWT via request.state
- View whitelist — only rpt_*/mv_* views registered in the Registry
- Metric/Dimension whitelist — Pydantic rejects unknown enums at 422
- Reporting engine — read-only user, 30s timeout, separate connection pool
"""
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.context.tenant import TenantContext, get_tenant_context
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from api.schemas.dashboard import (
    SemanticQueryRequest,
    KpiCard,
    KpiSummaryData,
    ChartDataPoint,
    ChartData,
    AnalyzeData,
    ViewSchemaData,
    make_success,
    make_error,
)
from database.reporting_session import (
    ReportingSessionLocal,
    REPORTING_CURRENCY_CODE,
)
from services.reporting.semantic_layer import (
    ViewScope,
    ReportMetric,
    ReportDimension,
    TimeGranularity,
    get_view_registration,
    get_available_metrics,
    get_available_dimensions,
)
from services.reporting.query_builder import SemanticQueryBuilder
from core.structured_logging import get_logger

logger = get_logger(__name__)

# ============================================================================
# Routers — Separate prefixes for dashboards vs reports
# ============================================================================

dashboards_router = APIRouter(tags=["dashboards"])
reports_router = APIRouter(tags=["reports"])


# ============================================================================
# Helper: Extract tenant context from request.state
# ============================================================================

def _extract_tenant(request: Request) -> TenantContext:
    """
    Extract validated TenantContext from request.state.

    Tenant is derived from JWT claims by AuthenticationMiddleware.
    It is a SCOPE (search_path), not a filter parameter.
    The frontend CANNOT override or omit this.
    """
    #[Constraint Check] Rule #1: tenant_id comes ONLY from trusted context (request.state)
    return get_tenant_context(request)


def _build_builder(
    session: AsyncSession,
    tenant_ctx: TenantContext,
    view_scope: ViewScope,
) -> SemanticQueryBuilder:
    """
    Factory: create a SemanticQueryBuilder with tenant context.

    Demonstrates how tenant_id flows from request.state → builder constructor.
    """
    #[Constraint Check] Rule #1: tenant_id flows from request.state → builder constructor
    #[Constraint Check] Rule #3: view_scope is a whitelisted ViewScope Enum
    return SemanticQueryBuilder(
        session=session,
        tenant_id=tenant_ctx.tenant_id,
        tenant_schema=tenant_ctx.tenant_schema,
        view_scope=view_scope,
    )


# ============================================================================
# TIER 1: KPI Endpoints — Hardcoded, No Parameters
# ============================================================================

@dashboards_router.get(
    "/kpi/summary",
    summary="Dashboard KPI Summary",
    description=(
        "Returns pre-defined KPI cards for the dashboard header. "
        "No user parameters — metrics are hardcoded by the backend. "
        "Empty materialized views return 0 (graceful degradation)."
    ),
)
async def get_kpi_summary(
    request: Request,
    token: TokenPayload = Depends(RequirePermission("dashboards:read")),
) -> JSONResponse:
    """
    TIER 1: Hardcoded KPI summary.

    Returns:
    - Total Revenue (from mv_sales_daily — materialized, may be stale)
    - Total Outstanding Receivables (from rpt_receivables_summary — real-time)
    - Net Cash Position (from rpt_cash_flow_daily — real-time)

    These are NOT configurable by the frontend. To add a new KPI card,
    a backend engineer must modify this endpoint.

    Tenant is extracted from request.state (set by AuthenticationMiddleware).
    """
    tenant_ctx: TenantContext = _extract_tenant(request)

    async with ReportingSessionLocal() as session:
        try:
            cards: list[dict[str, Any]] = []

            #[Constraint Check] Rule #1: KPI uses Builder to enforce tenant isolation consistently
            # --- Revenue KPI (Materialized View — may be stale) ---
            revenue_builder = _build_builder(session, tenant_ctx, ViewScope.SALES_DAILY)
            revenue_data = await revenue_builder.fetch_kpi_summary()
            cards.append(KpiCard(
                label="Total Revenue",
                value=float(revenue_data.get("revenue", 0)),
                currency=REPORTING_CURRENCY_CODE,
            ).model_dump())

            # --- Receivables KPI (Real-time View) ---
            ar_builder = _build_builder(session, tenant_ctx, ViewScope.RECEIVABLES_SUMMARY)
            ar_data = await ar_builder.fetch_kpi_summary()
            cards.append(KpiCard(
                label="Outstanding Receivables",
                value=float(ar_data.get("outstanding_balance", 0)),
                currency=REPORTING_CURRENCY_CODE,
            ).model_dump())

            # --- Cash Position KPI (Real-time View) ---
            cash_builder = _build_builder(session, tenant_ctx, ViewScope.CASH_FLOW_DAILY)
            cash_data = await cash_builder.fetch_kpi_summary()
            cards.append(KpiCard(
                label="Net Cash Position",
                value=float(cash_data.get("running_balance", 0)),
                currency=REPORTING_CURRENCY_CODE,
            ).model_dump())

            data = KpiSummaryData(
                tenant_id=tenant_ctx.tenant_id,
                generated_at=datetime.now(timezone.utc).isoformat(),
                cards=[KpiCard(**c) for c in cards],
                currency=REPORTING_CURRENCY_CODE,
            )
            return JSONResponse(content=make_success(data))

        except Exception as e:
            logger.error(
                f"KPI summary failed: {e}",
                extra={"tenant_id": tenant_ctx.tenant_id, "error": str(e)}
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=make_error("KPI_QUERY_FAILED", str(e)),
            )


# ============================================================================
# TIER 2: Chart Endpoints — Limited Parameters (date_range + granularity)
# ============================================================================

@dashboards_router.get(
    "/charts/sales-trend",
    summary="Sales Revenue Trend",
    description=(
        "Time-series of daily revenue. Parameters limited to date range "
        "and granularity. The metric (revenue) is hardcoded."
    ),
)
async def get_sales_trend(
    request: Request,
    date_from: Optional[date] = Query(default=None, description="Start date"),
    date_to: Optional[date] = Query(default=None, description="End date"),
    granularity: TimeGranularity = Query(
        default=TimeGranularity.DAY, description="day, week, or month"
    ),
    token: TokenPayload = Depends(RequirePermission("dashboards:read")),
) -> JSONResponse:
    """
    TIER 2: Sales trend chart.

    Metric is hardcoded to REVENUE. Frontend can only control the
    date range and time granularity. No metric selection allowed.
    """
    tenant_ctx: TenantContext = _extract_tenant(request)

    async with ReportingSessionLocal() as session:
        try:
            builder = _build_builder(session, tenant_ctx, ViewScope.SALES_DAILY)
            raw_data = await builder.fetch_time_series(
                metric=ReportMetric.REVENUE,
                date_from=date_from,
                date_to=date_to,
                granularity=granularity,
            )

            data = ChartData(
                tenant_id=tenant_ctx.tenant_id,
                chart_type="sales_trend",
                granularity=granularity.value,
                data=[
                    ChartDataPoint(
                        date=str(point["date"]),
                        value=float(point["value"]) if point["value"] is not None else 0.0,
                        currency=point["currency"],
                    )
                    for point in raw_data
                ],
                currency=REPORTING_CURRENCY_CODE,
            )
            return JSONResponse(content=make_success(data))

        except Exception as e:
            logger.error(
                f"Sales trend chart failed: {e}",
                extra={"tenant_id": tenant_ctx.tenant_id, "error": str(e)}
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=make_error("CHART_QUERY_FAILED", str(e)),
            )


@dashboards_router.get(
    "/charts/cash-flow",
    summary="Cash Flow Trend",
    description=(
        "Time-series of daily net cash change. Parameters limited to "
        "date range and granularity."
    ),
)
async def get_cash_flow_trend(
    request: Request,
    date_from: Optional[date] = Query(default=None, description="Start date"),
    date_to: Optional[date] = Query(default=None, description="End date"),
    granularity: TimeGranularity = Query(
        default=TimeGranularity.DAY, description="day, week, or month"
    ),
    token: TokenPayload = Depends(RequirePermission("dashboards:read")),
) -> JSONResponse:
    """TIER 2: Cash flow trend chart. Metric hardcoded to NET_CASH_CHANGE."""
    tenant_ctx: TenantContext = _extract_tenant(request)

    async with ReportingSessionLocal() as session:
        try:
            builder = _build_builder(session, tenant_ctx, ViewScope.CASH_FLOW_DAILY)
            raw_data = await builder.fetch_time_series(
                metric=ReportMetric.NET_CASH_CHANGE,
                date_from=date_from,
                date_to=date_to,
                granularity=granularity,
            )

            data = ChartData(
                tenant_id=tenant_ctx.tenant_id,
                chart_type="cash_flow",
                granularity=granularity.value,
                data=[
                    ChartDataPoint(
                        date=str(point["date"]),
                        value=float(point["value"]) if point["value"] is not None else 0.0,
                        currency=point["currency"],
                    )
                    for point in raw_data
                ],
                currency=REPORTING_CURRENCY_CODE,
            )
            return JSONResponse(content=make_success(data))

        except Exception as e:
            logger.error(
                f"Cash flow chart failed: {e}",
                extra={"tenant_id": tenant_ctx.tenant_id, "error": str(e)}
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=make_error("CHART_QUERY_FAILED", str(e)),
            )


# ============================================================================
# TIER 3: Ad-hoc Analysis — SemanticQueryBuilder with Enum Validation
# ============================================================================

@reports_router.post(
    "/analyze",
    summary="Ad-hoc Semantic Analysis",
    description=(
        "Execute a semantic query against a whitelisted reporting view. "
        "All metrics and dimensions MUST be valid enum values. "
        "Invalid values are rejected with 422 before reaching the query engine."
    ),
)
async def analyze_report(
    request: Request,
    body: SemanticQueryRequest,
    token: TokenPayload = Depends(RequirePermission("reports:analyze")),
) -> JSONResponse:
    """
    TIER 3: Ad-hoc analysis via SemanticQueryBuilder.

    The frontend sends:
    - view: ViewScope enum (e.g., "sales_daily")
    - metrics: list of ReportMetric enums (e.g., ["revenue"])
    - dimensions: list of ReportDimension enums (e.g., ["date"])

    Pydantic validates all enums at the boundary. If any value is not
    in the enum, the request is rejected with 422. The query builder
    never sees invalid input.

    The builder's build_query() method iterates the enums and resolves
    each to a SQLAlchemy column via the semantic layer Registry.
    """
    tenant_ctx: TenantContext = _extract_tenant(request)

    # Cross-view validation: metric must be available on the chosen view
    registration = get_view_registration(body.view)
    for metric in body.metrics:
        if metric not in registration.metrics:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content=make_error(
                    code="METRIC_NOT_AVAILABLE",
                    message=(
                        f"Metric '{metric.value}' is not available on "
                        f"view '{body.view.value}'"
                    ),
                    available_values=[m.value for m in registration.metrics],
                ),
            )

    if body.dimensions:
        for dim in body.dimensions:
            if dim not in registration.dimensions:
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content=make_error(
                        code="DIMENSION_NOT_AVAILABLE",
                        message=(
                            f"Dimension '{dim.value}' is not available on "
                            f"view '{body.view.value}'"
                        ),
                        available_values=[d.value for d in registration.dimensions],
                    ),
                )

    async with ReportingSessionLocal() as session:
        try:
            builder = _build_builder(session, tenant_ctx, body.view)

            #[Constraint Check] Rule #4: build_query() only accepts whitelisted Enums
            stmt = builder.build_query(
                metrics=body.metrics,
                dimensions=body.dimensions,
                date_from=body.date_from,
                date_to=body.date_to,
                limit=body.limit,
            )
            rows = await builder.execute(stmt)

            data = AnalyzeData(
                tenant_id=tenant_ctx.tenant_id,
                view=body.view.value,
                row_count=len(rows),
                rows=rows,
                currency=REPORTING_CURRENCY_CODE,
                is_materialized=registration.is_materialized,
            )
            return JSONResponse(content=make_success(data))

        except ValueError as e:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content=make_error("SEMANTIC_ERROR", str(e)),
            )
        except Exception as e:
            logger.error(
                f"Ad-hoc analysis failed: {e}",
                extra={
                    "tenant_id": tenant_ctx.tenant_id,
                    "view": body.view.value,
                    "error": str(e),
                }
            )
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=make_error("ANALYSIS_FAILED", str(e)),
            )


# ============================================================================
# Metadata Endpoint — Discover available metrics/dimensions
# ============================================================================

@reports_router.get(
    "/schema/{view_scope}",
    summary="View Schema Discovery",
    description=(
        "Returns the available metrics and dimensions for a reporting view. "
        "Frontend uses this to build dynamic query forms."
    ),
)
async def get_view_schema(
    view_scope: ViewScope,
    token: TokenPayload = Depends(RequirePermission("reports:read")),
) -> JSONResponse:
    """
    Returns the semantic schema for a view — what can be queried.

    This is the contract between frontend and backend:
    - Frontend reads this schema to know what enums to send
    - Backend defines this schema via the Registry
    - If a metric is not listed here, it cannot be queried
    """
    registration = get_view_registration(view_scope)
    data = ViewSchemaData(
        view=view_scope.value,
        is_materialized=registration.is_materialized,
        metrics=[
            {"key": m.value, "column": col}
            for m, col in registration.metrics.items()
        ],
        dimensions=[
            {"key": d.value, "column": col}
            for d, col in registration.dimensions.items()
        ],
        currency=REPORTING_CURRENCY_CODE,
    )
    return JSONResponse(content=make_success(data))
