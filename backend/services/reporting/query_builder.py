"""
S6-3: Semantic Query Builder — Controlled BI Query Construction.

Philosophy: "The frontend asks in business language. The backend translates."

This builder takes validated semantic queries (enums only) and constructs
safe SQLAlchemy 2.0 queries against whitelisted reporting views. It enforces:

1. Tenant isolation — search_path is ALWAYS set, no opt-out
2. View whitelist — only registered rpt_*/mv_* views are queryable
3. Metric/Dimension whitelist — only registered enums resolve to columns
4. No raw SQL — all queries are built via SQLAlchemy ORM select()

Security: If a metric or dimension is not in the Registry, the query
builder raises ValueError. But in practice, Pydantic validation at the
API layer rejects invalid enums before they reach this code.

Usage:
    builder = SemanticQueryBuilder(
        session=session,
        tenant_id="550e8400-...",
        tenant_schema="t_550e8400...",
        view_scope=ViewScope.SALES_DAILY,
    )
    stmt = builder.build_query(
        metrics=[ReportMetric.REVENUE],
        dimensions=[ReportDimension.DATE],
    )
    rows = await builder.execute(stmt)
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, Sequence, Type, Union

from sqlalchemy import Select, select, func, text, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from services.reporting.semantic_layer import (
    ViewScope,
    ReportMetric,
    ReportDimension,
    TimeGranularity,
    get_view_registration,
    resolve_column,
    ViewRegistration,
)
from core.structured_logging import get_logger

logger = get_logger(__name__)


class SemanticQueryBuilder:
    """
    Controlled query builder for reporting views.

    Tenant is a SCOPE, not a filter. The builder sets search_path
    to the tenant schema before any query executes. There is no
    method to skip or override this.

    Key design:
    - Constructor receives tenant_id (validated context, not raw string)
    - build_query() iterates frontend enums → resolves via semantic layer
    - execute() sets tenant scope then runs the built statement
    """

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: str,
        tenant_schema: str,
        view_scope: ViewScope,
    ) -> None:
        """
        Initialize the builder.

        Args:
            session: Reporting-engine async session (read-only).
            tenant_id: Validated tenant UUID string from TenantContext.
            tenant_schema: Validated tenant schema (e.g., "t_abc123").
            view_scope: Which reporting view to query (whitelist enforced).

        Raises:
            ValueError: If view_scope is not registered in the Registry.
        """
        #[Constraint Check] Rule #1: tenant_id captured at init from trusted context, immutable
        self._session: AsyncSession = session
        self._tenant_id: str = tenant_id
        self._tenant_schema: str = tenant_schema
        self._view_scope: ViewScope = view_scope
        #[Constraint Check] Rule #3: Only rpt_*/mv_* views pass get_view_registration()
        self._registration: ViewRegistration = get_view_registration(view_scope)
        self._model: Type = self._registration.model
        self._scope_applied: bool = False

    # ------------------------------------------------------------------
    # Tenant Scope (mandatory, non-optional)
    # ------------------------------------------------------------------

    async def _ensure_tenant_scope(self) -> None:
        """
        Set search_path to the tenant schema. ALWAYS called before query.
        This is not optional. There is no way to query without a tenant.
        Idempotent within a session.
        """
        if not self._scope_applied:
            #[Constraint Check] Rule #1: SET LOCAL search_path before ANY query execution
            await self._session.execute(
                text(f'SET LOCAL search_path TO "{self._tenant_schema}", public')
            )
            self._scope_applied = True

    # ------------------------------------------------------------------
    # Column Resolution (delegates to semantic_layer.resolve_column)
    # ------------------------------------------------------------------

    def _get_sa_column(
        self, enum_val: Union[ReportMetric, ReportDimension]
    ) -> InstrumentedAttribute:
        """
        Resolve a semantic enum to a live SQLAlchemy column object.

        Uses resolve_column() from the semantic layer, then getattr()
        on the model. This is the ONLY path from enum to column.
        """
        attr_name: str = resolve_column(self._view_scope, enum_val)
        col = getattr(self._model, attr_name, None)
        if col is None:
            raise ValueError(
                f"Column '{attr_name}' not found on model "
                f"'{self._model.__tablename__}'"
            )
        return col

    # ------------------------------------------------------------------
    # build_query() — The core method
    # ------------------------------------------------------------------

    def build_query(
        self,
        metrics: list[ReportMetric],
        dimensions: Optional[list[ReportDimension]] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 1000,
    ) -> Select:
        """
        Build a SQLAlchemy 2.0 SELECT statement from semantic enums.

        Iterates the frontend-supplied Metrics and Dimensions, resolves
        each through the Registry to a concrete SQLAlchemy column, and
        assembles a type-safe query. No raw SQL is ever constructed.

        Args:
            metrics: Business metrics to select (resolved via Registry).
            dimensions: Grouping dimensions (resolved via Registry).
            date_from: Optional start date filter (on DATE dimension).
            date_to: Optional end date filter (on DATE dimension).
            limit: Max rows (safety cap, hard max 10000).

        Returns:
            A SQLAlchemy Select statement ready for execute().

        Raises:
            ValueError: If any metric/dimension is not on this view.
        """
        # Resolve dimensions → SQLAlchemy columns
        dim_columns: list[InstrumentedAttribute] = []
        if dimensions:
            for d in dimensions:
                dim_columns.append(self._get_sa_column(d))

        # Resolve metrics → SQLAlchemy columns
        metric_columns: list[InstrumentedAttribute] = []
        for m in metrics:
            metric_columns.append(self._get_sa_column(m))

        # Build SELECT: dimensions first, then metrics
        stmt: Select = select(*dim_columns, *metric_columns)

        #[Constraint Check] Rule #3: Time filtering MUST use transaction_date (never created_at)
        if date_from or date_to:
            date_attr = self._registration.dimensions.get(ReportDimension.DATE)
            if date_attr:
                date_col = getattr(self._model, date_attr)
                if date_from:
                    stmt = stmt.where(cast(date_col, Date) >= date_from)
                if date_to:
                    stmt = stmt.where(cast(date_col, Date) <= date_to)

        # Safety cap
        stmt = stmt.limit(min(limit, 10000))

        return stmt

    def build_kpi_query(self) -> Select:
        """
        Build an aggregation query for KPI summary (Tier 1).

        Returns COALESCE(SUM(col), 0) for every registered metric.
        Guarantees non-null results even on empty materialized views.
        """
        agg_columns = []
        for metric, col_name in self._registration.metrics.items():
            col = getattr(self._model, col_name)
            agg_columns.append(
                func.coalesce(func.sum(col), 0).label(metric.value)
            )
        return select(*agg_columns)

    def build_time_series_query(
        self,
        metric: ReportMetric,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        granularity: TimeGranularity = TimeGranularity.DAY,
    ) -> Select:
        """
        Build a time-series query for chart endpoints (Tier 2).

        Args:
            metric: The single metric to chart.
            date_from: Start date.
            date_to: End date.
            granularity: Time bucketing (day/week/month).

        Returns:
            SELECT statement with (date, value) columns ordered by date.
        """
        metric_col = self._get_sa_column(metric)
        date_col = self._get_sa_column(ReportDimension.DATE)

        if granularity == TimeGranularity.DAY:
            stmt = select(
                cast(date_col, Date).label("date"),
                metric_col.label("value"),
            )
        else:
            trunc_fn = func.date_trunc(granularity.value, date_col)
            stmt = select(
                trunc_fn.label("date"),
                func.sum(metric_col).label("value"),
            ).group_by(trunc_fn)

        if date_from:
            stmt = stmt.where(cast(date_col, Date) >= date_from)
        if date_to:
            stmt = stmt.where(cast(date_col, Date) <= date_to)

        stmt = stmt.order_by(text("date"))
        return stmt

    # ------------------------------------------------------------------
    # execute() — Runs the built query with tenant scope
    # ------------------------------------------------------------------

    async def execute(self, stmt: Select) -> list[dict[str, Any]]:
        """
        Execute a built statement with tenant scope enforced.

        Sets search_path, runs the query, and returns results as
        a list of dicts with semantic keys.
        """
        #[Constraint Check] Rule #1: Tenant scope enforced before every query
        await self._ensure_tenant_scope()
        result = await self._session.execute(stmt)
        rows = result.fetchall()
        columns = result.keys()
        return [
            {col: self._serialize(val) for col, val in zip(columns, row)}
            for row in rows
        ]

    async def execute_scalar_row(self, stmt: Select) -> dict[str, Any]:
        """
        Execute a statement expecting a single aggregate row.

        Used by KPI endpoints. Returns zeros on empty result (graceful
        degradation for un-refreshed materialized views).
        """
        #[Constraint Check] Rule #1: Tenant scope enforced before every query
        await self._ensure_tenant_scope()
        result = await self._session.execute(stmt)
        row = result.fetchone()
        columns = list(result.keys())

        if row is None:
            return {col: 0.0 for col in columns}

        return {
            col: self._serialize(val)
            for col, val in zip(columns, row)
        }

    # ------------------------------------------------------------------
    # Convenience wrappers (backward-compatible with existing tests)
    # ------------------------------------------------------------------

    async def fetch_all(
        self,
        metrics: list[ReportMetric],
        dimensions: Optional[list[ReportDimension]] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Convenience: build + execute an ad-hoc query."""
        stmt = self.build_query(metrics, dimensions, date_from, date_to, limit)
        return await self.execute(stmt)

    async def fetch_kpi_summary(self) -> dict[str, Any]:
        """Convenience: build + execute a KPI aggregation."""
        stmt = self.build_kpi_query()
        return await self.execute_scalar_row(stmt)

    async def fetch_time_series(
        self,
        metric: ReportMetric,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        granularity: TimeGranularity = TimeGranularity.DAY,
    ) -> list[dict[str, Any]]:
        """Convenience: build + execute a time-series query."""
        stmt = self.build_time_series_query(metric, date_from, date_to, granularity)
        rows = await self.execute(stmt)
        return [
            {
                "date": row.get("date"),
                "value": row.get("value"),
                "currency": "USD",
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def is_materialized(self) -> bool:
        """Whether the underlying view is a materialized view."""
        return self._registration.is_materialized

    @staticmethod
    def _serialize(val: Any) -> Any:
        """Serialize a value for JSON response."""
        if isinstance(val, Decimal):
            return float(val)
        if isinstance(val, (date, datetime)):
            return val.isoformat()
        if hasattr(val, 'hex'):  # UUID
            return str(val)
        return val
