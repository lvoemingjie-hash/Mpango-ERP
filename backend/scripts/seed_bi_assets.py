"""
S7-5-A2: Seed BI Assets — Golden Report Configurations.

This script generates the three "golden reports" that serve as:
1. Reference implementations of the ReportConfig schema.
2. Mock data for frontend development.
3. Seed data for demo/staging environments.

Golden Reports:
    1. CFO Dashboard — Revenue (Bar Chart) + Cash Balance (KPI Card)
    2. Sales Tracker — Daily Sales (Line Chart)
    3. AR Aging — Overdue Invoices (Table)

Usage:
    # Validate configs only (no DB required)
    python -m scripts.seed_bi_assets --validate

    # Insert into DB (requires running database + tenant)
    python -m scripts.seed_bi_assets --tenant-id <uuid> --owner-id <uuid>

All configs are built using the strong-typed ReportConfig schema.
If this script compiles, the configs are valid by construction.
"""
from __future__ import annotations

from core.bi.report_config import (
    Aggregation,
    AxisConfig,
    ChartType,
    ColorPalette,
    DataSource,
    GridLayout,
    GridPosition,
    RefreshInterval,
    ReportConfig,
    ReportSettings,
    SchemaVersion,
    VisualizationOptions,
    Widget,
    WidgetType,
)
from services.reporting.semantic_layer import (
    ReportDimension,
    ReportMetric,
    TimeGranularity,
    ViewScope,
)


# ============================================================================
# 1. CFO Dashboard
# ============================================================================

CFO_DASHBOARD_CONFIG = ReportConfig(
    version=SchemaVersion.V1,
    layout=GridLayout(columns=12, row_height=80, gap=16),
    widgets=[
        # ── Revenue Bar Chart (left half, 2 rows tall) ──
        Widget(
            id="revenue-bar",
            type=WidgetType.CHART,
            title="Monthly Revenue",
            description="Daily revenue aggregated from mv_sales_daily",
            position=GridPosition(x=0, y=0, w=8, h=3),
            data_source=DataSource(
                view=ViewScope.SALES_DAILY,
                metrics=[ReportMetric.REVENUE],
                dimensions=[ReportDimension.DATE],
                time_granularity=TimeGranularity.MONTH,
                aggregation=Aggregation.SUM,
            ),
            visualization=VisualizationOptions(
                chart_type=ChartType.BAR,
                palette=ColorPalette.REVENUE,
                show_legend=True,
                show_grid=True,
                x_axis=AxisConfig(label="Month", format="date"),
                y_axis=AxisConfig(label="Revenue (USD)", format="currency"),
                value_format="currency",
                currency_code="USD",
            ),
        ),
        # ── Cash Balance KPI Card (right side, 1 row) ──
        Widget(
            id="cash-balance-kpi",
            type=WidgetType.KPI,
            title="Cash Balance",
            description="Current running cash balance from rpt_cash_flow_daily",
            position=GridPosition(x=8, y=0, w=4, h=1),
            data_source=DataSource(
                view=ViewScope.CASH_FLOW_DAILY,
                metrics=[ReportMetric.RUNNING_BALANCE],
                aggregation=Aggregation.LATEST,
            ),
            visualization=VisualizationOptions(
                palette=ColorPalette.NEUTRAL,
                value_format="currency",
                currency_code="USD",
            ),
        ),
        # ── Revenue KPI Card (right side, 1 row) ──
        Widget(
            id="revenue-kpi",
            type=WidgetType.KPI,
            title="Total Revenue",
            description="Sum of all daily revenue",
            position=GridPosition(x=8, y=1, w=4, h=1),
            data_source=DataSource(
                view=ViewScope.SALES_DAILY,
                metrics=[ReportMetric.REVENUE],
                aggregation=Aggregation.SUM,
            ),
            visualization=VisualizationOptions(
                palette=ColorPalette.REVENUE,
                value_format="currency",
                currency_code="USD",
            ),
        ),
        # ── Outstanding Receivables KPI (right side, 1 row) ──
        Widget(
            id="ar-kpi",
            type=WidgetType.KPI,
            title="Outstanding Receivables",
            description="Total amount owed by entities",
            position=GridPosition(x=8, y=2, w=4, h=1),
            data_source=DataSource(
                view=ViewScope.RECEIVABLES_SUMMARY,
                metrics=[ReportMetric.OUTSTANDING_BALANCE],
                aggregation=Aggregation.SUM,
            ),
            visualization=VisualizationOptions(
                palette=ColorPalette.EXPENSE,
                value_format="currency",
                currency_code="USD",
            ),
        ),
    ],
    settings=ReportSettings(
        refresh_interval=RefreshInterval.MINUTES_5,
        default_date_range_days=90,
        currency_code="USD",
    ),
)

CFO_DASHBOARD_TITLE = "CFO Dashboard"
CFO_DASHBOARD_DESCRIPTION = (
    "Executive financial overview: revenue trends, cash position, "
    "and outstanding receivables. Auto-refreshes every 5 minutes."
)
CFO_DASHBOARD_DOMAIN = "finance"


# ============================================================================
# 2. Sales Tracker
# ============================================================================

SALES_TRACKER_CONFIG = ReportConfig(
    version=SchemaVersion.V1,
    layout=GridLayout(columns=12, row_height=80, gap=16),
    widgets=[
        # ── Daily Sales Line Chart (full width, 3 rows) ──
        Widget(
            id="daily-sales-line",
            type=WidgetType.CHART,
            title="Daily Sales Trend",
            description="Revenue per day from mv_sales_daily",
            position=GridPosition(x=0, y=0, w=12, h=3),
            data_source=DataSource(
                view=ViewScope.SALES_DAILY,
                metrics=[ReportMetric.REVENUE],
                dimensions=[ReportDimension.DATE],
                time_granularity=TimeGranularity.DAY,
                aggregation=Aggregation.SUM,
            ),
            visualization=VisualizationOptions(
                chart_type=ChartType.LINE,
                palette=ColorPalette.REVENUE,
                show_legend=False,
                show_grid=True,
                x_axis=AxisConfig(label="Date", format="date"),
                y_axis=AxisConfig(label="Revenue (USD)", format="currency"),
                value_format="currency",
                currency_code="USD",
            ),
        ),
        # ── Transaction Count Bar (full width, 2 rows) ──
        Widget(
            id="txn-count-bar",
            type=WidgetType.CHART,
            title="Transaction Volume",
            description="Number of revenue entries per day",
            position=GridPosition(x=0, y=3, w=12, h=2),
            data_source=DataSource(
                view=ViewScope.SALES_DAILY,
                metrics=[ReportMetric.TRANSACTION_COUNT],
                dimensions=[ReportDimension.DATE],
                time_granularity=TimeGranularity.DAY,
                aggregation=Aggregation.SUM,
            ),
            visualization=VisualizationOptions(
                chart_type=ChartType.BAR,
                palette=ColorPalette.CATEGORICAL,
                show_legend=False,
                show_grid=True,
                x_axis=AxisConfig(label="Date", format="date"),
                y_axis=AxisConfig(label="Transactions", format="number"),
                value_format="number",
            ),
        ),
    ],
    settings=ReportSettings(
        refresh_interval=RefreshInterval.MINUTES_15,
        default_date_range_days=30,
        currency_code="USD",
    ),
)

SALES_TRACKER_TITLE = "Sales Tracker"
SALES_TRACKER_DESCRIPTION = (
    "Daily sales performance: revenue trend line and transaction volume. "
    "Default view is last 30 days."
)
SALES_TRACKER_DOMAIN = "sales"


# ============================================================================
# 3. AR Aging Report
# ============================================================================

AR_AGING_CONFIG = ReportConfig(
    version=SchemaVersion.V1,
    layout=GridLayout(columns=12, row_height=80, gap=16),
    widgets=[
        # ── Overdue Invoices Table (full width, 4 rows) ──
        Widget(
            id="ar-aging-table",
            type=WidgetType.TABLE,
            title="Accounts Receivable — Overdue Invoices",
            description="Outstanding balances by entity from rpt_receivables_summary",
            position=GridPosition(x=0, y=0, w=12, h=4),
            data_source=DataSource(
                view=ViewScope.RECEIVABLES_SUMMARY,
                metrics=[
                    ReportMetric.OUTSTANDING_BALANCE,
                    ReportMetric.RECEIVABLE_ENTRY_COUNT,
                ],
                dimensions=[
                    ReportDimension.ENTITY_ID,
                    ReportDimension.ENTITY_TYPE,
                ],
                aggregation=Aggregation.SUM,
            ),
            visualization=VisualizationOptions(
                palette=ColorPalette.EXPENSE,
                value_format="currency",
                currency_code="USD",
            ),
        ),
        # ── Total Outstanding KPI (half width) ──
        Widget(
            id="total-outstanding-kpi",
            type=WidgetType.KPI,
            title="Total Outstanding",
            description="Sum of all outstanding receivables",
            position=GridPosition(x=0, y=4, w=6, h=1),
            data_source=DataSource(
                view=ViewScope.RECEIVABLES_SUMMARY,
                metrics=[ReportMetric.OUTSTANDING_BALANCE],
                aggregation=Aggregation.SUM,
            ),
            visualization=VisualizationOptions(
                palette=ColorPalette.EXPENSE,
                value_format="currency",
                currency_code="USD",
            ),
        ),
        # ── Entry Count KPI (half width) ──
        Widget(
            id="entry-count-kpi",
            type=WidgetType.KPI,
            title="Total Entries",
            description="Number of receivable ledger entries",
            position=GridPosition(x=6, y=4, w=6, h=1),
            data_source=DataSource(
                view=ViewScope.RECEIVABLES_SUMMARY,
                metrics=[ReportMetric.RECEIVABLE_ENTRY_COUNT],
                aggregation=Aggregation.SUM,
            ),
            visualization=VisualizationOptions(
                palette=ColorPalette.NEUTRAL,
                value_format="number",
            ),
        ),
    ],
    settings=ReportSettings(
        refresh_interval=RefreshInterval.OFF,
        default_date_range_days=90,
        currency_code="USD",
    ),
)

AR_AGING_TITLE = "AR Aging Report"
AR_AGING_DESCRIPTION = (
    "Accounts receivable aging: outstanding balances by entity, "
    "entry counts, and total exposure. No auto-refresh (snapshot view)."
)
AR_AGING_DOMAIN = "finance"


# ============================================================================
# Golden Reports Registry
# ============================================================================

GOLDEN_REPORTS = [
    {
        "title": CFO_DASHBOARD_TITLE,
        "description": CFO_DASHBOARD_DESCRIPTION,
        "domain": CFO_DASHBOARD_DOMAIN,
        "config": CFO_DASHBOARD_CONFIG,
    },
    {
        "title": SALES_TRACKER_TITLE,
        "description": SALES_TRACKER_DESCRIPTION,
        "domain": SALES_TRACKER_DOMAIN,
        "config": SALES_TRACKER_CONFIG,
    },
    {
        "title": AR_AGING_TITLE,
        "description": AR_AGING_DESCRIPTION,
        "domain": AR_AGING_DOMAIN,
        "config": AR_AGING_CONFIG,
    },
]


# ============================================================================
# CLI Entry Point
# ============================================================================

def validate_all() -> None:
    """Validate all golden report configs. Raises on failure."""
    for report in GOLDEN_REPORTS:
        config = report["config"]
        # Round-trip: serialize → deserialize to prove JSON compatibility
        json_str = config.model_dump_json()
        restored = ReportConfig.model_validate_json(json_str)
        assert restored == config, f"Round-trip failed for {report['title']}"
        print(f"  ✓ {report['title']}: {len(config.widgets)} widgets, valid")
    print(f"\nAll {len(GOLDEN_REPORTS)} golden reports validated successfully.")


if __name__ == "__main__":
    import sys

    if "--validate" in sys.argv:
        print("Validating golden report configurations...\n")
        validate_all()
    else:
        print(
            "Usage:\n"
            "  python -m scripts.seed_bi_assets --validate\n"
            "  python -m scripts.seed_bi_assets --tenant-id <uuid> --owner-id <uuid>\n"
        )
