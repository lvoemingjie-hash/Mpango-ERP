"""
S6-3: Semantic Layer — Enums, Registry, and Mapping for BI Facade.

Philosophy: "If it's not in the Enum, it doesn't exist."

This module is the SINGLE SOURCE OF TRUTH for what the reporting API can
query. The frontend NEVER sends raw column names — it sends business-semantic
enum values. The backend resolves those enums to SQLAlchemy columns via
the Registry.

Security Model:
- ReportMetric enum → whitelist of queryable metrics
- ReportDimension enum → whitelist of queryable dimensions
- ViewScope enum → whitelist of queryable views (rpt_* / mv_*)
- If a value is not in the enum, Pydantic rejects it at the API boundary.
  The request never reaches the service layer.

Adding a new field:
1. Backend engineer adds it to the Enum
2. Backend engineer adds the mapping in _REGISTRY
3. Frontend can now use it
There is NO other path.
"""
from enum import Enum
from typing import Dict, Any, Type, Union
from dataclasses import dataclass

from sqlalchemy.orm import InspectionAttr

from models.base import Base
from models.reporting import (
    MvSalesDaily,
    RptReceivablesSummary,
    RptCashFlowDaily,
)


# ============================================================================
# 1. View Scope — Which views can be queried
# ============================================================================

class ViewScope(str, Enum):
    """
    Whitelist of queryable reporting views.

    If a view is not listed here, it CANNOT be queried through the API.
    This is the first line of defense: the Registry doesn't even know
    about non-reporting tables.
    """
    #[Constraint Check] Rule #3: Only rpt_* / mv_* views are whitelisted
    SALES_DAILY = "sales_daily"
    RECEIVABLES_SUMMARY = "receivables_summary"
    CASH_FLOW_DAILY = "cash_flow_daily"


# ============================================================================
# 2. Report Metrics — What numbers can be queried
# ============================================================================

class ReportMetric(str, Enum):
    """
    Business-semantic metric identifiers.

    Frontend sends these enum values. Backend resolves them to actual
    SQLAlchemy columns. The frontend NEVER knows the real column name.

    Example:
        Frontend sends: {"metrics": ["REVENUE"]}
        Backend resolves: MvSalesDaily.daily_revenue
    """
    #[Constraint Check] Rule #4: All inputs are whitelisted Enums — NO dynamic strings
    # Sales metrics
    REVENUE = "revenue"
    TRANSACTION_COUNT = "transaction_count"

    # Receivables metrics
    OUTSTANDING_BALANCE = "outstanding_balance"
    RECEIVABLE_ENTRY_COUNT = "receivable_entry_count"

    # Cash flow metrics
    NET_CASH_CHANGE = "net_cash_change"
    RUNNING_BALANCE = "running_balance"
    CASH_TRANSACTION_COUNT = "cash_transaction_count"


# ============================================================================
# 3. Report Dimensions — What axes can be grouped/filtered by
# ============================================================================

class ReportDimension(str, Enum):
    """
    Business-semantic dimension identifiers.

    Dimensions are the axes along which metrics are sliced.
    """
    #[Constraint Check] Rule #4: All inputs are whitelisted Enums — NO dynamic strings
    DATE = "date"
    CURRENCY = "currency"
    ENTITY_ID = "entity_id"
    ENTITY_TYPE = "entity_type"


# ============================================================================
# 4. Granularity — Time bucketing for chart endpoints
# ============================================================================

class TimeGranularity(str, Enum):
    """Time bucketing for trend charts."""
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


# ============================================================================
# 5. The Registry — Enum → SQLAlchemy Column Mapping
# ============================================================================

@dataclass(frozen=True)
class ViewRegistration:
    """
    Registration entry for a reporting view.

    Maps a ViewScope to its SQLAlchemy model and defines which metrics
    and dimensions are available on that view.
    """
    model: Type[Base]
    metrics: Dict[ReportMetric, str]       # Enum → column attribute name
    dimensions: Dict[ReportDimension, str]  # Enum → column attribute name
    is_materialized: bool = False


# The Registry: the ONLY place where enums meet database columns.
# If it's not here, it doesn't exist to the API.
_REGISTRY: Dict[ViewScope, ViewRegistration] = {

    #[Constraint Check] Rule #3: Target table is mv_sales_daily (mv_* prefix)
    #[Constraint Check] Rule #3: REVENUE → MvSalesDaily.daily_revenue (reporting column)
    #[Constraint Check] Rule #3: DATE → transaction_date (never created_at)
    #[Constraint Check] Rule #3: CURRENCY → reporting_currency_code
    ViewScope.SALES_DAILY: ViewRegistration(
        model=MvSalesDaily,
        is_materialized=True,
        metrics={
            ReportMetric.REVENUE: "daily_revenue",
            ReportMetric.TRANSACTION_COUNT: "transaction_count",
        },
        dimensions={
            ReportDimension.DATE: "transaction_date",
            ReportDimension.CURRENCY: "reporting_currency_code",
        },
    ),

    #[Constraint Check] Rule #3: Target table is rpt_receivables_summary (rpt_* prefix)
    ViewScope.RECEIVABLES_SUMMARY: ViewRegistration(
        model=RptReceivablesSummary,
        is_materialized=False,
        metrics={
            ReportMetric.OUTSTANDING_BALANCE: "outstanding_balance",
            ReportMetric.RECEIVABLE_ENTRY_COUNT: "entry_count",
        },
        dimensions={
            ReportDimension.ENTITY_ID: "entity_id",
            ReportDimension.ENTITY_TYPE: "entity_type",
            ReportDimension.CURRENCY: "reporting_currency_code",
        },
    ),

    #[Constraint Check] Rule #3: Target table is rpt_cash_flow_daily (rpt_* prefix)
    #[Constraint Check] Rule #3: DATE → transaction_date (never created_at)
    ViewScope.CASH_FLOW_DAILY: ViewRegistration(
        model=RptCashFlowDaily,
        is_materialized=False,
        metrics={
            ReportMetric.NET_CASH_CHANGE: "net_change",
            ReportMetric.RUNNING_BALANCE: "running_balance",
            ReportMetric.CASH_TRANSACTION_COUNT: "transaction_count",
        },
        dimensions={
            ReportDimension.DATE: "transaction_date",
            ReportDimension.CURRENCY: "reporting_currency_code",
        },
    ),
}


# ============================================================================
# 6. Registry Access Functions
# ============================================================================

def get_view_registration(scope: ViewScope) -> ViewRegistration:
    """
    Get the registration for a view scope.

    Raises:
        ValueError: If the scope is not registered (should never happen
                    if ViewScope enum is in sync with _REGISTRY).
    """
    reg = _REGISTRY.get(scope)
    if reg is None:
        raise ValueError(
            f"ViewScope '{scope.value}' is not registered. "
            f"Available: {[s.value for s in _REGISTRY]}"
        )
    return reg


def resolve_metric_column(scope: ViewScope, metric: ReportMetric) -> str:
    """
    Resolve a semantic metric to its SQLAlchemy column attribute name.

    Raises:
        ValueError: If the metric is not available on this view.
    """
    reg = get_view_registration(scope)
    col_name = reg.metrics.get(metric)
    if col_name is None:
        raise ValueError(
            f"Metric '{metric.value}' is not available on view '{scope.value}'. "
            f"Available metrics: {[m.value for m in reg.metrics]}"
        )
    return col_name


def resolve_dimension_column(scope: ViewScope, dimension: ReportDimension) -> str:
    """
    Resolve a semantic dimension to its SQLAlchemy column attribute name.

    Raises:
        ValueError: If the dimension is not available on this view.
    """
    reg = get_view_registration(scope)
    col_name = reg.dimensions.get(dimension)
    if col_name is None:
        raise ValueError(
            f"Dimension '{dimension.value}' is not available on view '{scope.value}'. "
            f"Available dimensions: {[d.value for d in reg.dimensions]}"
        )
    return col_name


def get_available_metrics(scope: ViewScope) -> list[ReportMetric]:
    """List all metrics available on a view."""
    return list(get_view_registration(scope).metrics.keys())


def get_available_dimensions(scope: ViewScope) -> list[ReportDimension]:
    """List all dimensions available on a view."""
    return list(get_view_registration(scope).dimensions.keys())


def resolve_column(
    scope: ViewScope,
    enum_val: Union[ReportMetric, ReportDimension],
) -> str:
    """
    Unified resolver: map ANY semantic enum (metric or dimension) to a
    SQLAlchemy column attribute name on the view's model.

    This is the single entry-point the QueryBuilder uses. It prevents
    "semantic drift" — Revenue ALWAYS resolves to `daily_revenue`,
    never to `transaction_amount` or any other column.

    Args:
        scope: The target view (whitelist enforced)
        enum_val: A ReportMetric or ReportDimension enum value

    Returns:
        The column attribute name (str) on the SQLAlchemy model

    Raises:
        ValueError: If the enum is not registered on the given view
        TypeError: If enum_val is neither ReportMetric nor ReportDimension
    """
    if isinstance(enum_val, ReportMetric):
        return resolve_metric_column(scope, enum_val)
    elif isinstance(enum_val, ReportDimension):
        return resolve_dimension_column(scope, enum_val)
    else:
        raise TypeError(
            f"Expected ReportMetric or ReportDimension, got {type(enum_val).__name__}"
        )
