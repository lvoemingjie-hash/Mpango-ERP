"""
P7-0 + S7-4: Governance Registry — The Manifest of All BI Assets.

Philosophy: "If it's not registered here, it doesn't exist to management."

This module is the single source of truth for all governed BI assets in
Mpango ERP. It transforms Phase 6's implicit code-level objects (views,
metrics, dimensions) into explicit, addressable governance assets.

Resolution Chain (S7-4):
    1. Static Lookup (GOVERNANCE_REGISTRY dict)  — O(1), always first
    2. LRU Cache (in-memory, max 1024 entries)   — O(1), avoids DB
    3. DynamicResolver.resolve(urn, tenant_id)   — async DB query

    Static assets (system-wide) are ALWAYS resolved from the dict.
    Dynamic assets (tenant-created) go through cache → resolver.
    This ensures backwards compatibility: all existing code works unchanged.

Relationship to Semantic Layer (S6-3):
    semantic_layer.py  →  "What can the query engine access?"
    registry.py        →  "What does management know exists?"

    These are deliberately separate concerns:
    - The semantic layer is a security boundary (whitelist enforcement).
    - The governance registry is a visibility boundary (asset catalog).
    - An asset in the registry that is NOT in the semantic layer is
      a "planned" or "deprecated" asset — visible but not queryable.

🔒 S7-4-C4 (CTO Mandate, Frozen):
    Cache Invalidation Canon — these events MUST trigger invalidation:
    1. Asset CRUD (create/update/delete)  → invalidate(urn)
    2. ACL change                         → invalidate(urn)
    3. Owner change                       → invalidate(urn)
    4. Tenant deletion                    → invalidate_tenant(tenant_id)

Boot Contract Compliance:
- New file in core/governance/ (no modification to frozen core/ files)
- No database changes (in-memory registry only)
- No imports from api.v1, api.middleware, or api.dependencies
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from core.governance.models import (
    BIAction,
    BIAsset,
    BIDomain,
    BiUrn,
    DataFreshness,
    ResourceType,
)
from core.governance.resolver import AssetResolver, NullResolver

logger = logging.getLogger("mpango.governance.registry")


# ============================================================================
# 1. Helper — Asset factory for concise registration
# ============================================================================

def _asset(
    resource_type: ResourceType,
    domain: BIDomain,
    identifier: str,
    display_name: str,
    description: str = "",
    freshness: DataFreshness = DataFreshness.REAL_TIME,
    source_phase: str = "S6",
    semantic_ref: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> BIAsset:
    """Factory for creating a system-wide BIAsset with a well-formed URN."""
    return BIAsset(
        urn=BiUrn(
            resource_type=resource_type,
            domain=domain,
            identifier=identifier,
        ),
        display_name=display_name,
        description=description,
        freshness=freshness,
        source_phase=source_phase,
        semantic_ref=semantic_ref,
        tags=tags or [],
    )


# ============================================================================
# 2. View Assets — Database reporting objects (rpt_* / mv_*)
# ============================================================================

VIEW_MV_SALES_DAILY = _asset(
    resource_type=ResourceType.VIEW,
    domain=BIDomain.SALES,
    identifier="mv_sales_daily",
    display_name="Daily Sales Revenue",
    description=(
        "Materialized view aggregating daily revenue from ledger entries. "
        "Grain: one row per calendar day. Refreshed every 15 minutes via "
        "S4 job queue. Source: ledger_entries WHERE account_type = 'revenue'."
    ),
    freshness=DataFreshness.NEAR_REAL_TIME,
    source_phase="S6-2",
    semantic_ref="ViewScope.SALES_DAILY",
    tags=["materialized", "revenue", "daily", "s6-2"],
)

VIEW_RPT_RECEIVABLES = _asset(
    resource_type=ResourceType.VIEW,
    domain=BIDomain.FINANCE,
    identifier="rpt_receivables_summary",
    display_name="Accounts Receivable Summary",
    description=(
        "Real-time view of outstanding receivables by entity. "
        "Grain: one row per (entity_id, entity_type). "
        "Source: ledger_entries WHERE account_type = 'receivable'."
    ),
    freshness=DataFreshness.REAL_TIME,
    source_phase="S6-1",
    semantic_ref="ViewScope.RECEIVABLES_SUMMARY",
    tags=["real-time", "receivables", "ar", "s6-1"],
)

VIEW_RPT_CASH_FLOW = _asset(
    resource_type=ResourceType.VIEW,
    domain=BIDomain.FINANCE,
    identifier="rpt_cash_flow_daily",
    display_name="Daily Cash Flow",
    description=(
        "Real-time view of daily cash inflows/outflows with running balance. "
        "Grain: one row per calendar day. "
        "Source: ledger_entries WHERE account_type = 'cash'."
    ),
    freshness=DataFreshness.REAL_TIME,
    source_phase="S6-1",
    semantic_ref="ViewScope.CASH_FLOW_DAILY",
    tags=["real-time", "cash-flow", "daily", "s6-1"],
)


# ============================================================================
# 3. Metric Assets — Individual measurable quantities
# ============================================================================

METRIC_REVENUE = _asset(
    resource_type=ResourceType.METRIC,
    domain=BIDomain.SALES,
    identifier="revenue",
    display_name="Revenue",
    description="Total daily revenue in reporting currency (USD). ABS(SUM(amount)).",
    freshness=DataFreshness.NEAR_REAL_TIME,
    source_phase="S6-3",
    semantic_ref="ReportMetric.REVENUE",
    tags=["kpi", "revenue", "sales"],
)

METRIC_TRANSACTION_COUNT = _asset(
    resource_type=ResourceType.METRIC,
    domain=BIDomain.SALES,
    identifier="transaction_count",
    display_name="Transaction Count",
    description="Number of revenue entries per day.",
    freshness=DataFreshness.NEAR_REAL_TIME,
    source_phase="S6-3",
    semantic_ref="ReportMetric.TRANSACTION_COUNT",
    tags=["volume", "sales"],
)

METRIC_OUTSTANDING_BALANCE = _asset(
    resource_type=ResourceType.METRIC,
    domain=BIDomain.FINANCE,
    identifier="outstanding_balance",
    display_name="Outstanding Receivables",
    description="Total amount owed by entities. SUM(amount), positive = owed to us.",
    freshness=DataFreshness.REAL_TIME,
    source_phase="S6-3",
    semantic_ref="ReportMetric.OUTSTANDING_BALANCE",
    tags=["kpi", "receivables", "ar"],
)

METRIC_RECEIVABLE_ENTRY_COUNT = _asset(
    resource_type=ResourceType.METRIC,
    domain=BIDomain.FINANCE,
    identifier="receivable_entry_count",
    display_name="Receivable Entry Count",
    description="Number of receivable ledger entries per entity.",
    freshness=DataFreshness.REAL_TIME,
    source_phase="S6-3",
    semantic_ref="ReportMetric.RECEIVABLE_ENTRY_COUNT",
    tags=["volume", "receivables"],
)

METRIC_NET_CASH_CHANGE = _asset(
    resource_type=ResourceType.METRIC,
    domain=BIDomain.FINANCE,
    identifier="net_cash_change",
    display_name="Net Cash Change",
    description="Daily net cash inflow/outflow. Positive = inflow, negative = outflow.",
    freshness=DataFreshness.REAL_TIME,
    source_phase="S6-3",
    semantic_ref="ReportMetric.NET_CASH_CHANGE",
    tags=["kpi", "cash-flow"],
)

METRIC_RUNNING_BALANCE = _asset(
    resource_type=ResourceType.METRIC,
    domain=BIDomain.FINANCE,
    identifier="running_balance",
    display_name="Running Cash Balance",
    description="Cumulative cash position up to a given date.",
    freshness=DataFreshness.REAL_TIME,
    source_phase="S6-3",
    semantic_ref="ReportMetric.RUNNING_BALANCE",
    tags=["kpi", "cash-flow", "cumulative"],
)

METRIC_CASH_TRANSACTION_COUNT = _asset(
    resource_type=ResourceType.METRIC,
    domain=BIDomain.FINANCE,
    identifier="cash_transaction_count",
    display_name="Cash Transaction Count",
    description="Number of cash ledger entries per day.",
    freshness=DataFreshness.REAL_TIME,
    source_phase="S6-3",
    semantic_ref="ReportMetric.CASH_TRANSACTION_COUNT",
    tags=["volume", "cash-flow"],
)


# ============================================================================
# 4. Dashboard Assets — Composed views (S6-3 Tier 1 & 2)
# ============================================================================

DASHBOARD_EXECUTIVE = _asset(
    resource_type=ResourceType.DASHBOARD,
    domain=BIDomain.EXECUTIVE,
    identifier="executive_summary",
    display_name="Executive Summary Dashboard",
    description=(
        "Top-level KPI dashboard with Revenue, Outstanding Receivables, "
        "and Net Cash Position cards. Backed by GET /dashboards/kpi/summary."
    ),
    freshness=DataFreshness.NEAR_REAL_TIME,
    source_phase="S6-3",
    tags=["dashboard", "kpi", "executive"],
)

DASHBOARD_SALES_TREND = _asset(
    resource_type=ResourceType.DASHBOARD,
    domain=BIDomain.SALES,
    identifier="sales_trend",
    display_name="Sales Revenue Trend",
    description=(
        "Time-series chart of daily/weekly/monthly revenue. "
        "Backed by GET /dashboards/charts/sales-trend."
    ),
    freshness=DataFreshness.NEAR_REAL_TIME,
    source_phase="S6-3",
    tags=["chart", "trend", "revenue"],
)

DASHBOARD_CASH_FLOW_TREND = _asset(
    resource_type=ResourceType.DASHBOARD,
    domain=BIDomain.FINANCE,
    identifier="cash_flow_trend",
    display_name="Cash Flow Trend",
    description=(
        "Time-series chart of daily/weekly/monthly net cash change. "
        "Backed by GET /dashboards/charts/cash-flow."
    ),
    freshness=DataFreshness.REAL_TIME,
    source_phase="S6-3",
    tags=["chart", "trend", "cash-flow"],
)


# ============================================================================
# 5. Report Assets — Ad-hoc analysis (S6-3 Tier 3)
# ============================================================================

REPORT_ADHOC_SALES = _asset(
    resource_type=ResourceType.REPORT,
    domain=BIDomain.SALES,
    identifier="adhoc_sales_analysis",
    display_name="Ad-hoc Sales Analysis",
    description=(
        "Flexible tabular report on sales_daily view. User selects metrics "
        "and dimensions via POST /reports/analyze. Enum-validated."
    ),
    freshness=DataFreshness.NEAR_REAL_TIME,
    source_phase="S6-3",
    tags=["report", "adhoc", "sales"],
)

REPORT_ADHOC_RECEIVABLES = _asset(
    resource_type=ResourceType.REPORT,
    domain=BIDomain.FINANCE,
    identifier="adhoc_receivables_analysis",
    display_name="Ad-hoc Receivables Analysis",
    description=(
        "Flexible tabular report on receivables_summary view. "
        "User selects metrics and dimensions via POST /reports/analyze."
    ),
    freshness=DataFreshness.REAL_TIME,
    source_phase="S6-3",
    tags=["report", "adhoc", "receivables"],
)

REPORT_ADHOC_CASH_FLOW = _asset(
    resource_type=ResourceType.REPORT,
    domain=BIDomain.FINANCE,
    identifier="adhoc_cash_flow_analysis",
    display_name="Ad-hoc Cash Flow Analysis",
    description=(
        "Flexible tabular report on cash_flow_daily view. "
        "User selects metrics and dimensions via POST /reports/analyze."
    ),
    freshness=DataFreshness.REAL_TIME,
    source_phase="S6-3",
    tags=["report", "adhoc", "cash-flow"],
)


# ============================================================================
# 6. Export Template Assets — Async export configurations (S6-4)
# ============================================================================

EXPORT_SALES_CSV = _asset(
    resource_type=ResourceType.EXPORT_TEMPLATE,
    domain=BIDomain.SALES,
    identifier="sales_daily_csv",
    display_name="Sales Daily Export (CSV)",
    description=(
        "Async CSV export of sales_daily data. Triggered via POST /exports. "
        "Uses fetchmany(1000) streaming for memory safety."
    ),
    freshness=DataFreshness.NEAR_REAL_TIME,
    source_phase="S6-4",
    tags=["export", "csv", "sales", "async"],
)

EXPORT_SALES_XLSX = _asset(
    resource_type=ResourceType.EXPORT_TEMPLATE,
    domain=BIDomain.SALES,
    identifier="sales_daily_xlsx",
    display_name="Sales Daily Export (Excel)",
    description=(
        "Async XLSX export of sales_daily data. Uses openpyxl write_only mode."
    ),
    freshness=DataFreshness.NEAR_REAL_TIME,
    source_phase="S6-4",
    tags=["export", "xlsx", "sales", "async"],
)


# ============================================================================
# 7. GOVERNANCE_REGISTRY — The Static Master Manifest
# ============================================================================

GOVERNANCE_REGISTRY: dict[str, BIAsset] = {}
"""
The static governance manifest. Keyed by URN string.

This is the source of truth for SYSTEM-WIDE BI assets.
Tenant-created assets are resolved dynamically via the AssetResolver.

To register a new system asset:
1. Define it as a module-level constant above.
2. Add it to _ALL_ASSETS below.
3. It will be automatically indexed by URN in GOVERNANCE_REGISTRY.
"""

_ALL_ASSETS: list[BIAsset] = [
    # Views (database objects)
    VIEW_MV_SALES_DAILY,
    VIEW_RPT_RECEIVABLES,
    VIEW_RPT_CASH_FLOW,
    # Metrics (measurable quantities)
    METRIC_REVENUE,
    METRIC_TRANSACTION_COUNT,
    METRIC_OUTSTANDING_BALANCE,
    METRIC_RECEIVABLE_ENTRY_COUNT,
    METRIC_NET_CASH_CHANGE,
    METRIC_RUNNING_BALANCE,
    METRIC_CASH_TRANSACTION_COUNT,
    # Dashboards (composed views)
    DASHBOARD_EXECUTIVE,
    DASHBOARD_SALES_TREND,
    DASHBOARD_CASH_FLOW_TREND,
    # Reports (ad-hoc analysis)
    REPORT_ADHOC_SALES,
    REPORT_ADHOC_RECEIVABLES,
    REPORT_ADHOC_CASH_FLOW,
    # Export templates (async extraction)
    EXPORT_SALES_CSV,
    EXPORT_SALES_XLSX,
]

# Build the registry index
for _asset_obj in _ALL_ASSETS:
    _urn_key = _asset_obj.urn_string
    if _urn_key in GOVERNANCE_REGISTRY:
        raise RuntimeError(
            f"Duplicate URN in governance registry: '{_urn_key}'. "
            f"Each asset must have a unique URN."
        )
    GOVERNANCE_REGISTRY[_urn_key] = _asset_obj


# ============================================================================
# 8. Dynamic Resolution Layer (S7-4)
# ============================================================================

_LRU_CACHE_MAX_SIZE = 1024

# Thread-safe dynamic asset cache: urn -> BIAsset
_dynamic_cache: dict[str, BIAsset] = {}
_dynamic_cache_lock = threading.Lock()

# The registered resolver (default: NullResolver = static-only mode)
_resolver: AssetResolver = NullResolver()


def register_resolver(resolver: AssetResolver) -> None:
    """
    Register a dynamic asset resolver.

    Called at app startup to enable dynamic resolution of tenant-created
    assets. If not called, the registry operates in static-only mode
    (backwards compatible).

    Args:
        resolver: An object implementing the AssetResolver protocol.
    """
    global _resolver
    _resolver = resolver
    logger.info("dynamic_resolver_registered", extra={
        "resolver_type": type(resolver).__name__,
    })


def get_resolver() -> AssetResolver:
    """Return the currently registered resolver (for direct async calls)."""
    return _resolver


# ============================================================================
# 9. Cache Invalidation (🔒 S7-4-C4)
# ============================================================================

def invalidate_asset(urn: str) -> None:
    """
    Invalidate a single cached dynamic asset by URN.

    🔒 S7-4-C4: Called after asset CRUD, ACL change, or owner change.

    Args:
        urn: The URN string to invalidate.
    """
    with _dynamic_cache_lock:
        removed = _dynamic_cache.pop(urn, None)
    if removed is not None:
        logger.debug("cache_invalidated", extra={"urn": urn})


def invalidate_tenant(tenant_id: str) -> None:
    """
    Invalidate ALL cached dynamic assets for a tenant.

    🔒 S7-4-C4: Called after tenant deletion or bulk tenant operations.

    Args:
        tenant_id: The tenant whose assets should be evicted.
    """
    with _dynamic_cache_lock:
        keys_to_remove = [
            urn for urn, asset in _dynamic_cache.items()
            if asset.tenant_id == tenant_id
        ]
        for key in keys_to_remove:
            del _dynamic_cache[key]
    if keys_to_remove:
        logger.debug("cache_tenant_invalidated", extra={
            "tenant_id": tenant_id,
            "evicted_count": len(keys_to_remove),
        })


def invalidate_all() -> None:
    """
    Invalidate the entire dynamic asset cache.

    Called after schema migrations or emergency cache flush.
    """
    with _dynamic_cache_lock:
        count = len(_dynamic_cache)
        _dynamic_cache.clear()
    logger.info("cache_full_invalidation", extra={"evicted_count": count})


def _cache_put(urn: str, asset: BIAsset) -> None:
    """Add an asset to the dynamic cache with LRU eviction."""
    with _dynamic_cache_lock:
        # Simple LRU: if at capacity, remove oldest entry
        if len(_dynamic_cache) >= _LRU_CACHE_MAX_SIZE and urn not in _dynamic_cache:
            oldest_key = next(iter(_dynamic_cache))
            del _dynamic_cache[oldest_key]
        _dynamic_cache[urn] = asset


def _cache_get(urn: str) -> Optional[BIAsset]:
    """Look up an asset in the dynamic cache."""
    with _dynamic_cache_lock:
        asset = _dynamic_cache.get(urn)
        if asset is not None:
            # Move to end (most recently used) for LRU behavior
            _dynamic_cache.pop(urn)
            _dynamic_cache[urn] = asset
        return asset


# ============================================================================
# 10. Lookup Functions (upgraded for S7-4)
# ============================================================================

def get_asset(urn: str) -> BIAsset:
    """
    Look up a governed asset by its URN string (synchronous, static only).

    This is the original P7-0 lookup function. It searches ONLY the static
    registry. For dynamic resolution (tenant assets), use get_asset_async().

    Args:
        urn: Full URN (e.g., "urn:bi:view:sales:mv_sales_daily")

    Returns:
        The registered BIAsset.

    Raises:
        KeyError: If the URN is not in the static registry.
    """
    asset = GOVERNANCE_REGISTRY.get(urn)
    if asset is None:
        raise KeyError(
            f"Asset not found in governance registry: '{urn}'. "
            f"Registered URNs: {list(GOVERNANCE_REGISTRY.keys())}"
        )
    return asset


async def get_asset_async(
    urn: str,
    tenant_id: Optional[str] = None,
) -> BIAsset:
    """
    Look up a governed asset by URN with full resolution chain (S7-4).

    Resolution order:
        1. Static registry (GOVERNANCE_REGISTRY dict)
        2. Dynamic cache (LRU, max 1024 entries)
        3. Registered resolver (async DB query)

    Args:
        urn: Full URN (e.g., "urn:bi:report:sales:my_custom_report")
        tenant_id: Optional tenant context for dynamic resolution.
                   🔒 S7-4-C1: tenant_id is context, NOT part of URN.

    Returns:
        The resolved BIAsset.

    Raises:
        KeyError: If the URN is not found in any source.
    """
    # Step 1: Static registry (always first, O(1))
    static_asset = GOVERNANCE_REGISTRY.get(urn)
    if static_asset is not None:
        return static_asset

    # Step 2: Dynamic cache (O(1))
    cached_asset = _cache_get(urn)
    if cached_asset is not None:
        return cached_asset

    # Step 3: Dynamic resolver (async)
    resolved_asset = await _resolver.resolve(urn, tenant_id)
    if resolved_asset is not None:
        _cache_put(urn, resolved_asset)
        return resolved_asset

    raise KeyError(
        f"Asset not found in any source: '{urn}'. "
        f"Checked: static registry ({len(GOVERNANCE_REGISTRY)} assets), "
        f"dynamic cache, registered resolver ({type(_resolver).__name__})."
    )


def list_assets(
    resource_type: Optional[ResourceType] = None,
    domain: Optional[BIDomain] = None,
    tag: Optional[str] = None,
) -> list[BIAsset]:
    """
    List static governed assets with optional filters.

    Note: This only lists STATIC (system) assets. For tenant assets,
    use list_assets_async() which also queries the resolver.

    Args:
        resource_type: Filter by asset type (e.g., ResourceType.METRIC).
        domain: Filter by business domain (e.g., BIDomain.FINANCE).
        tag: Filter by tag (e.g., "kpi").

    Returns:
        List of matching BIAsset objects.
    """
    results = list(GOVERNANCE_REGISTRY.values())

    if resource_type is not None:
        results = [a for a in results if a.urn.resource_type == resource_type]

    if domain is not None:
        results = [a for a in results if a.urn.domain == domain]

    if tag is not None:
        results = [a for a in results if tag in a.tags]

    return results


async def list_assets_async(
    tenant_id: Optional[str] = None,
    resource_type: Optional[ResourceType] = None,
    domain: Optional[BIDomain] = None,
    tag: Optional[str] = None,
) -> list[BIAsset]:
    """
    List all governed assets (static + dynamic) with optional filters (S7-4).

    Combines static system assets with tenant-created dynamic assets.

    Args:
        tenant_id: If provided, also includes tenant-created assets.
        resource_type: Filter by asset type.
        domain: Filter by business domain.
        tag: Filter by tag.

    Returns:
        Combined list of matching BIAsset objects.
    """
    # Start with static assets
    results = list_assets(
        resource_type=resource_type,
        domain=domain,
        tag=tag,
    )

    # Add dynamic assets if tenant_id is provided
    if tenant_id is not None:
        dynamic_assets = await _resolver.resolve_by_tenant(
            tenant_id, resource_type
        )
        # Apply additional filters
        if domain is not None:
            dynamic_assets = [
                a for a in dynamic_assets if a.urn.domain == domain
            ]
        if tag is not None:
            dynamic_assets = [
                a for a in dynamic_assets if tag in a.tags
            ]
        results.extend(dynamic_assets)

    return results


def list_urns() -> list[str]:
    """Return all static registered URN strings, sorted."""
    return sorted(GOVERNANCE_REGISTRY.keys())


def asset_count() -> int:
    """Total number of static registered assets."""
    return len(GOVERNANCE_REGISTRY)


def dynamic_cache_size() -> int:
    """Current number of entries in the dynamic asset cache."""
    with _dynamic_cache_lock:
        return len(_dynamic_cache)
