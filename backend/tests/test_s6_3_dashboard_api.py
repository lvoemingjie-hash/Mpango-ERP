"""
S6-3: Dashboard API & Reporting Facade Tests.

Philosophy: "If it's not in the Enum, it doesn't exist."

Test Cases:
1. Semantic Layer — Enum resolution, invalid metric rejection
2. Registry — Whitelist enforcement, non-rpt table inaccessible
3. SemanticQueryBuilder — Tenant scope, query execution, empty MV graceful degradation
4. Pydantic — Invalid enum values rejected at schema level
5. Cross-view metric rejection — Metric valid globally but not on chosen view
"""
import pytest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from pydantic import ValidationError

from services.reporting.semantic_layer import (
    ViewScope,
    ReportMetric,
    ReportDimension,
    TimeGranularity,
    get_view_registration,
    resolve_metric_column,
    resolve_dimension_column,
    resolve_column,
    get_available_metrics,
    get_available_dimensions,
)
from services.reporting.query_builder import SemanticQueryBuilder
from api.schemas.dashboard import SemanticQueryRequest


# ============================================================================
# 1. Semantic Layer Tests
# ============================================================================

class TestSemanticLayer:
    """Tests for the enum-to-column mapping registry."""

    def test_all_view_scopes_registered(self):
        """Every ViewScope enum value must have a registry entry."""
        for scope in ViewScope:
            reg = get_view_registration(scope)
            assert reg is not None
            assert reg.model is not None

    def test_resolve_revenue_metric(self):
        """ReportMetric.REVENUE resolves to 'daily_revenue' on SALES_DAILY."""
        col = resolve_metric_column(ViewScope.SALES_DAILY, ReportMetric.REVENUE)
        assert col == "daily_revenue"

    def test_resolve_outstanding_balance(self):
        """ReportMetric.OUTSTANDING_BALANCE resolves correctly."""
        col = resolve_metric_column(
            ViewScope.RECEIVABLES_SUMMARY, ReportMetric.OUTSTANDING_BALANCE
        )
        assert col == "outstanding_balance"

    def test_resolve_date_dimension(self):
        """ReportDimension.DATE resolves to 'transaction_date'."""
        col = resolve_dimension_column(ViewScope.SALES_DAILY, ReportDimension.DATE)
        assert col == "transaction_date"

    def test_invalid_metric_on_view_raises(self):
        """Requesting REVENUE on RECEIVABLES_SUMMARY must raise ValueError."""
        with pytest.raises(ValueError, match="not available"):
            resolve_metric_column(
                ViewScope.RECEIVABLES_SUMMARY, ReportMetric.REVENUE
            )

    def test_invalid_dimension_on_view_raises(self):
        """Requesting ENTITY_ID on SALES_DAILY must raise ValueError."""
        with pytest.raises(ValueError, match="not available"):
            resolve_dimension_column(
                ViewScope.SALES_DAILY, ReportDimension.ENTITY_ID
            )

    def test_available_metrics_returns_correct_list(self):
        """get_available_metrics returns only metrics registered for the view."""
        metrics = get_available_metrics(ViewScope.SALES_DAILY)
        assert ReportMetric.REVENUE in metrics
        assert ReportMetric.TRANSACTION_COUNT in metrics
        assert ReportMetric.OUTSTANDING_BALANCE not in metrics

    def test_materialized_flag(self):
        """SALES_DAILY is materialized, RECEIVABLES_SUMMARY is not."""
        assert get_view_registration(ViewScope.SALES_DAILY).is_materialized is True
        assert get_view_registration(ViewScope.RECEIVABLES_SUMMARY).is_materialized is False
        assert get_view_registration(ViewScope.CASH_FLOW_DAILY).is_materialized is False

    def test_resolve_column_unified(self):
        """resolve_column() works for both metrics and dimensions."""
        assert resolve_column(ViewScope.SALES_DAILY, ReportMetric.REVENUE) == "daily_revenue"
        assert resolve_column(ViewScope.SALES_DAILY, ReportDimension.DATE) == "transaction_date"

    def test_resolve_column_rejects_wrong_type(self):
        """resolve_column() raises TypeError for non-enum input."""
        with pytest.raises(TypeError, match="Expected ReportMetric or ReportDimension"):
            resolve_column(ViewScope.SALES_DAILY, "daily_revenue")  # type: ignore


# ============================================================================
# 2. Whitelist / Security Tests
# ============================================================================

class TestWhitelistSecurity:
    """Tests that non-reporting tables are inaccessible."""

    def test_no_user_table_in_registry(self):
        """The User table must NOT be queryable via the reporting facade."""
        for scope in ViewScope:
            reg = get_view_registration(scope)
            tablename = reg.model.__tablename__
            assert tablename.startswith("mv_") or tablename.startswith("rpt_"), (
                f"Registry contains non-reporting table: {tablename}"
            )

    def test_view_scope_enum_is_exhaustive(self):
        """ViewScope must only contain known reporting views."""
        allowed_prefixes = {"sales_daily", "receivables_summary", "cash_flow_daily"}
        for scope in ViewScope:
            assert scope.value in allowed_prefixes, (
                f"Unknown ViewScope: {scope.value}"
            )

    def test_registry_models_are_views(self):
        """All registered models must have is_view=True in table args."""
        for scope in ViewScope:
            reg = get_view_registration(scope)
            info = reg.model.__table_args__.get("info", {})
            assert info.get("is_view") is True, (
                f"Model {reg.model.__tablename__} is not marked as a view"
            )


# ============================================================================
# 3. Pydantic Schema Validation Tests
# ============================================================================

class TestPydanticValidation:
    """Tests that invalid enum values are rejected at the schema level."""

    def test_valid_request_parses(self):
        """A well-formed request should parse without error."""
        req = SemanticQueryRequest(
            view="sales_daily",
            metrics=["revenue", "transaction_count"],
            dimensions=["date"],
            date_from="2026-01-01",
            date_to="2026-01-31",
        )
        assert req.view == ViewScope.SALES_DAILY
        assert ReportMetric.REVENUE in req.metrics

    def test_invalid_view_rejected(self):
        """An unknown view value must be rejected by Pydantic."""
        with pytest.raises(ValidationError) as exc_info:
            SemanticQueryRequest(
                view="users_table",
                metrics=["revenue"],
            )
        assert "view" in str(exc_info.value).lower()

    def test_invalid_metric_rejected(self):
        """An unknown metric value must be rejected by Pydantic."""
        with pytest.raises(ValidationError) as exc_info:
            SemanticQueryRequest(
                view="sales_daily",
                metrics=["total_amount"],  # Not a valid enum
            )
        assert "metrics" in str(exc_info.value).lower() or "input" in str(exc_info.value).lower()

    def test_invalid_dimension_rejected(self):
        """An unknown dimension value must be rejected by Pydantic."""
        with pytest.raises(ValidationError) as exc_info:
            SemanticQueryRequest(
                view="sales_daily",
                metrics=["revenue"],
                dimensions=["user_email"],  # Not a valid enum
            )
        errors = str(exc_info.value).lower()
        assert "dimensions" in errors or "input" in errors

    def test_empty_metrics_rejected(self):
        """At least one metric must be specified."""
        with pytest.raises(ValidationError):
            SemanticQueryRequest(
                view="sales_daily",
                metrics=[],
            )

    def test_limit_bounds(self):
        """Limit must be between 1 and 10000."""
        with pytest.raises(ValidationError):
            SemanticQueryRequest(
                view="sales_daily",
                metrics=["revenue"],
                limit=0,
            )
        with pytest.raises(ValidationError):
            SemanticQueryRequest(
                view="sales_daily",
                metrics=["revenue"],
                limit=99999,
            )

    def test_raw_column_name_rejected(self):
        """
        Frontend sending raw column names like 'daily_revenue' instead of
        the semantic enum 'revenue' must be rejected.
        """
        with pytest.raises(ValidationError):
            SemanticQueryRequest(
                view="sales_daily",
                metrics=["daily_revenue"],  # Raw column name, not enum
            )

    def test_sql_injection_in_view_rejected(self):
        """SQL injection attempts in view field are rejected by enum validation."""
        with pytest.raises(ValidationError):
            SemanticQueryRequest(
                view="sales_daily; DROP TABLE users;--",
                metrics=["revenue"],
            )


# ============================================================================
# 4. SemanticQueryBuilder Integration Tests (require DB)
# ============================================================================

@pytest.mark.asyncio
async def test_query_builder_fetch_kpi_summary(async_session: AsyncSession):
    """
    SemanticQueryBuilder.fetch_kpi_summary returns zeros for empty MV.

    This tests graceful degradation: when the materialized view has no
    data for the current tenant, all metrics return 0 (not null/error).
    """
    builder = SemanticQueryBuilder(
        session=async_session,
        tenant_id="test-tenant-id",
        tenant_schema="t_test",
        view_scope=ViewScope.SALES_DAILY,
    )
    result = await builder.fetch_kpi_summary()

    assert "revenue" in result
    assert "transaction_count" in result
    # Values should be numeric (0 or positive), never None
    assert result["revenue"] is not None
    assert isinstance(result["revenue"], (int, float, Decimal))


@pytest.mark.asyncio
async def test_query_builder_fetch_all_receivables(async_session: AsyncSession):
    """
    SemanticQueryBuilder.fetch_all returns rows from rpt_receivables_summary.
    """
    builder = SemanticQueryBuilder(
        session=async_session,
        tenant_id="test-tenant-id",
        tenant_schema="t_test",
        view_scope=ViewScope.RECEIVABLES_SUMMARY,
    )
    rows = await builder.fetch_all(
        metrics=[ReportMetric.OUTSTANDING_BALANCE],
        dimensions=[ReportDimension.ENTITY_ID, ReportDimension.ENTITY_TYPE],
    )

    # Should return a list of dicts with semantic keys
    assert isinstance(rows, list)
    if rows:
        first = rows[0]
        assert "entity_id" in first
        assert "entity_type" in first
        assert "outstanding_balance" in first


@pytest.mark.asyncio
async def test_query_builder_fetch_time_series(async_session: AsyncSession):
    """
    SemanticQueryBuilder.fetch_time_series returns date-ordered data.
    """
    builder = SemanticQueryBuilder(
        session=async_session,
        tenant_id="test-tenant-id",
        tenant_schema="t_test",
        view_scope=ViewScope.CASH_FLOW_DAILY,
    )
    data = await builder.fetch_time_series(
        metric=ReportMetric.NET_CASH_CHANGE,
        granularity=TimeGranularity.DAY,
    )

    assert isinstance(data, list)
    if data:
        point = data[0]
        assert "date" in point
        assert "value" in point
        assert "currency" in point
        assert point["currency"] == "USD"


@pytest.mark.asyncio
async def test_query_builder_empty_mv_returns_zeros(async_session: AsyncSession):
    """
    When mv_sales_daily has no data, fetch_kpi_summary returns 0s.

    This is the graceful degradation requirement from S6-3 Step 4.
    """
    # Use a schema that likely has no revenue data
    builder = SemanticQueryBuilder(
        session=async_session,
        tenant_id="test-tenant-id",
        tenant_schema="t_test",
        view_scope=ViewScope.SALES_DAILY,
    )
    result = await builder.fetch_kpi_summary()

    # Even if empty, values must be numeric, never None
    for key, val in result.items():
        assert val is not None, f"KPI '{key}' returned None — must return 0"


@pytest.mark.asyncio
async def test_query_builder_cross_view_metric_raises(async_session: AsyncSession):
    """
    Requesting a metric that exists globally but not on the chosen view
    must raise ValueError.
    """
    builder = SemanticQueryBuilder(
        session=async_session,
        tenant_id="test-tenant-id",
        tenant_schema="t_test",
        view_scope=ViewScope.SALES_DAILY,
    )
    with pytest.raises(ValueError, match="not available"):
        await builder.fetch_all(
            metrics=[ReportMetric.OUTSTANDING_BALANCE],  # Not on SALES_DAILY
        )


@pytest.mark.asyncio
async def test_query_builder_reporting_user_access(ensure_reporting_user_password):
    """
    Verify the reporting_user can execute queries through the builder.
    """
    import os
    _rpt_pw = os.environ.get("REPORTING_USER_PASSWORD", "CHANGE_ME")
    _db_host = os.environ.get("POSTGRES_HOST", "postgres")
    engine = create_async_engine(
        f"postgresql+asyncpg://reporting_user:{_rpt_pw}@{_db_host}:5432/mpango_erp"
    )
    factory = async_sessionmaker(engine, class_=AsyncSession)

    async with factory() as session:
        # Must set tenant_schema in session.info to satisfy global tenant filter
        session.info["tenant_schema"] = "t_test"

        builder = SemanticQueryBuilder(
            session=session,
            tenant_id="test-tenant-id",
            tenant_schema="t_test",
            view_scope=ViewScope.RECEIVABLES_SUMMARY,
        )
        rows = await builder.fetch_all(
            metrics=[ReportMetric.OUTSTANDING_BALANCE],
            dimensions=[ReportDimension.ENTITY_ID],
        )
        assert isinstance(rows, list)

    await engine.dispose()
