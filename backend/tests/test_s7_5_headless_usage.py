"""
S7-5-A3: Headless BI Usage — API Simulation Tests.

Philosophy: "If the frontend can't parse it, we failed."

These tests simulate the complete frontend workflow WITHOUT a database:
1. Fetch: Retrieve a golden report config.
2. Validate: Assert the JSON conforms to the ReportConfig schema.
3. Clone: Extract the config, modify the title, create a new report.
4. Verify: Re-validate the cloned config.

This proves the S7-4 architecture supports complex business report
descriptions and provides perfect mock data for frontend development.

Test Categories:
    1. Schema Contract — ReportConfig strong typing guarantees
    2. Golden Reports — All 3 seed configs are valid and complete
    3. API Simulation — Fetch → Validate → Clone → Verify workflow
    4. Widget Constraints — Type-specific validation rules
    5. Grid Bounds — Layout constraint enforcement
    6. JSON Round-Trip — Serialize → Deserialize fidelity
"""
from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

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
from api.schemas.report import (
    CreateReportRequest,
    ReportResponse,
)
from scripts.seed_bi_assets import (
    CFO_DASHBOARD_CONFIG,
    CFO_DASHBOARD_TITLE,
    CFO_DASHBOARD_DESCRIPTION,
    CFO_DASHBOARD_DOMAIN,
    SALES_TRACKER_CONFIG,
    SALES_TRACKER_TITLE,
    AR_AGING_CONFIG,
    AR_AGING_TITLE,
    GOLDEN_REPORTS,
)
from services.reporting.semantic_layer import (
    ReportDimension,
    ReportMetric,
    TimeGranularity,
    ViewScope,
)


# ============================================================================
# 1. Schema Contract — Strong Typing Guarantees
# ============================================================================

class TestSchemaContract:
    """Verify the ReportConfig schema enforces strong typing."""

    def test_widget_type_is_enum(self):
        """WidgetType must be a valid enum, not arbitrary string."""
        with pytest.raises(ValidationError):
            Widget(
                id="bad", type="sparkline",  # not in WidgetType enum
                title="Bad", position=GridPosition(x=0, y=0, w=6, h=2),
            )

    def test_chart_type_is_enum(self):
        """ChartType must be a valid enum."""
        with pytest.raises(ValidationError):
            VisualizationOptions(chart_type="waterfall")  # not in ChartType

    def test_view_scope_is_enum(self):
        """DataSource.view must be a valid ViewScope enum."""
        with pytest.raises(ValidationError):
            DataSource(
                view="inventory_daily",  # not in ViewScope
                metrics=[ReportMetric.REVENUE],
            )

    def test_metric_is_enum(self):
        """DataSource.metrics must be valid ReportMetric enums."""
        with pytest.raises(ValidationError):
            DataSource(
                view=ViewScope.SALES_DAILY,
                metrics=["gross_margin"],  # not in ReportMetric
            )

    def test_dimension_is_enum(self):
        """DataSource.dimensions must be valid ReportDimension enums."""
        with pytest.raises(ValidationError):
            DataSource(
                view=ViewScope.SALES_DAILY,
                metrics=[ReportMetric.REVENUE],
                dimensions=["product_category"],  # not in ReportDimension
            )

    def test_color_palette_is_enum(self):
        """ColorPalette must be a valid enum."""
        with pytest.raises(ValidationError):
            VisualizationOptions(palette="rainbow")  # not in ColorPalette

    def test_aggregation_is_enum(self):
        """Aggregation must be a valid enum."""
        with pytest.raises(ValidationError):
            DataSource(
                view=ViewScope.SALES_DAILY,
                metrics=[ReportMetric.REVENUE],
                aggregation="median",  # not in Aggregation
            )

    def test_time_granularity_is_enum(self):
        """TimeGranularity must be a valid enum."""
        with pytest.raises(ValidationError):
            DataSource(
                view=ViewScope.SALES_DAILY,
                metrics=[ReportMetric.REVENUE],
                time_granularity="quarter",  # not in TimeGranularity
            )

    def test_refresh_interval_is_enum(self):
        """RefreshInterval must be a valid enum."""
        with pytest.raises(ValidationError):
            ReportSettings(refresh_interval="10s")  # not in RefreshInterval

    def test_schema_version_is_enum(self):
        """SchemaVersion must be a valid enum."""
        with pytest.raises(ValidationError):
            ReportConfig(
                version="2.0",  # not in SchemaVersion
                widgets=[_make_kpi_widget("w1")],
            )


# ============================================================================
# 2. Golden Reports — All 3 Seed Configs
# ============================================================================

class TestGoldenReports:
    """Verify all golden report configs are valid and complete."""

    def test_cfo_dashboard_valid(self):
        """CFO Dashboard config passes full validation."""
        assert isinstance(CFO_DASHBOARD_CONFIG, ReportConfig)
        assert CFO_DASHBOARD_CONFIG.version == SchemaVersion.V1

    def test_cfo_dashboard_widget_count(self):
        """CFO Dashboard has 4 widgets: bar chart + 3 KPIs."""
        assert len(CFO_DASHBOARD_CONFIG.widgets) == 4

    def test_cfo_dashboard_has_revenue_chart(self):
        """CFO Dashboard contains a revenue bar chart."""
        revenue = _find_widget(CFO_DASHBOARD_CONFIG, "revenue-bar")
        assert revenue is not None
        assert revenue.type == WidgetType.CHART
        assert revenue.visualization.chart_type == ChartType.BAR
        assert revenue.data_source.view == ViewScope.SALES_DAILY
        assert ReportMetric.REVENUE in revenue.data_source.metrics

    def test_cfo_dashboard_has_cash_kpi(self):
        """CFO Dashboard contains a cash balance KPI."""
        cash = _find_widget(CFO_DASHBOARD_CONFIG, "cash-balance-kpi")
        assert cash is not None
        assert cash.type == WidgetType.KPI
        assert cash.data_source.view == ViewScope.CASH_FLOW_DAILY
        assert ReportMetric.RUNNING_BALANCE in cash.data_source.metrics
        assert cash.data_source.aggregation == Aggregation.LATEST

    def test_cfo_dashboard_auto_refresh(self):
        """CFO Dashboard auto-refreshes every 5 minutes."""
        assert CFO_DASHBOARD_CONFIG.settings.refresh_interval == RefreshInterval.MINUTES_5

    def test_sales_tracker_valid(self):
        """Sales Tracker config passes full validation."""
        assert isinstance(SALES_TRACKER_CONFIG, ReportConfig)

    def test_sales_tracker_has_line_chart(self):
        """Sales Tracker contains a daily sales line chart."""
        line = _find_widget(SALES_TRACKER_CONFIG, "daily-sales-line")
        assert line is not None
        assert line.type == WidgetType.CHART
        assert line.visualization.chart_type == ChartType.LINE
        assert line.data_source.time_granularity == TimeGranularity.DAY

    def test_sales_tracker_has_volume_bar(self):
        """Sales Tracker contains a transaction volume bar chart."""
        bar = _find_widget(SALES_TRACKER_CONFIG, "txn-count-bar")
        assert bar is not None
        assert bar.type == WidgetType.CHART
        assert ReportMetric.TRANSACTION_COUNT in bar.data_source.metrics

    def test_ar_aging_valid(self):
        """AR Aging config passes full validation."""
        assert isinstance(AR_AGING_CONFIG, ReportConfig)

    def test_ar_aging_has_table(self):
        """AR Aging contains an overdue invoices table."""
        table = _find_widget(AR_AGING_CONFIG, "ar-aging-table")
        assert table is not None
        assert table.type == WidgetType.TABLE
        assert table.data_source.view == ViewScope.RECEIVABLES_SUMMARY
        assert ReportMetric.OUTSTANDING_BALANCE in table.data_source.metrics
        assert ReportDimension.ENTITY_ID in table.data_source.dimensions

    def test_ar_aging_no_auto_refresh(self):
        """AR Aging is a snapshot — no auto-refresh."""
        assert AR_AGING_CONFIG.settings.refresh_interval == RefreshInterval.OFF

    def test_all_golden_reports_unique_widget_ids(self):
        """Each golden report has unique widget IDs."""
        for report in GOLDEN_REPORTS:
            config = report["config"]
            ids = [w.id for w in config.widgets]
            assert len(ids) == len(set(ids)), f"Duplicate IDs in {report['title']}"

    def test_all_golden_reports_fit_grid(self):
        """All widgets fit within the 12-column grid."""
        for report in GOLDEN_REPORTS:
            config = report["config"]
            cols = config.layout.columns
            for w in config.widgets:
                assert w.position.x + w.position.w <= cols, (
                    f"Widget '{w.id}' in '{report['title']}' exceeds grid"
                )


# ============================================================================
# 3. API Simulation — Fetch → Validate → Clone → Verify
# ============================================================================

class TestApiSimulation:
    """
    Simulate the complete frontend workflow.

    Since we're in Pure Backend phase (no running server), we simulate
    the API by directly working with the Pydantic models. This proves
    the data flow works end-to-end.
    """

    def test_fetch_cfo_dashboard(self):
        """
        Step 1: FETCH — Simulate GET /api/bi/assets/reports/{id}.

        The API returns a ReportResponse with config as a dict (JSONB).
        The frontend receives this JSON and must parse it.
        """
        # Simulate what the API returns (config is serialized to dict)
        api_response = _simulate_report_response(
            title=CFO_DASHBOARD_TITLE,
            description=CFO_DASHBOARD_DESCRIPTION,
            domain=CFO_DASHBOARD_DOMAIN,
            config=CFO_DASHBOARD_CONFIG,
        )

        assert api_response.title == CFO_DASHBOARD_TITLE
        assert isinstance(api_response.config, dict)
        assert "widgets" in api_response.config
        assert "layout" in api_response.config

    def test_validate_fetched_config(self):
        """
        Step 2: VALIDATE — Frontend parses the JSON back into ReportConfig.

        This proves the JSON round-trip preserves all type information.
        """
        api_response = _simulate_report_response(
            title=CFO_DASHBOARD_TITLE,
            description=CFO_DASHBOARD_DESCRIPTION,
            domain=CFO_DASHBOARD_DOMAIN,
            config=CFO_DASHBOARD_CONFIG,
        )

        # Frontend parses the config dict back into ReportConfig
        parsed_config = ReportConfig.model_validate(api_response.config)

        assert parsed_config.version == SchemaVersion.V1
        assert len(parsed_config.widgets) == 4
        assert parsed_config.settings.refresh_interval == RefreshInterval.MINUTES_5

        # Verify specific widget data source bindings survived round-trip
        revenue = _find_widget(parsed_config, "revenue-bar")
        assert revenue.data_source.view == ViewScope.SALES_DAILY
        assert revenue.data_source.metrics == [ReportMetric.REVENUE]
        assert revenue.visualization.chart_type == ChartType.BAR

    def test_clone_and_modify(self):
        """
        Step 3: CLONE — Extract config, modify title, create new report.

        Simulates: user clicks "Clone" on CFO Dashboard, renames it,
        and POSTs to /api/bi/assets/reports.
        """
        # Fetch original
        api_response = _simulate_report_response(
            title=CFO_DASHBOARD_TITLE,
            description=CFO_DASHBOARD_DESCRIPTION,
            domain=CFO_DASHBOARD_DOMAIN,
            config=CFO_DASHBOARD_CONFIG,
        )

        # Parse config from API response
        original_config = ReportConfig.model_validate(api_response.config)

        # Clone: deep copy the config dict, modify title
        cloned_config_dict = json.loads(original_config.model_dump_json())

        # Validate the clone is a valid ReportConfig
        cloned_config = ReportConfig.model_validate(cloned_config_dict)

        # Build the POST request
        create_request = CreateReportRequest(
            title="My CFO Dash",
            description="Cloned from CFO Dashboard with personal tweaks",
            domain="finance",
            config=cloned_config,
            acl=["role:finance"],
        )

        assert create_request.title == "My CFO Dash"
        assert create_request.domain == "finance"
        assert len(create_request.config.widgets) == 4
        assert create_request.acl == ["role:finance"]

    def test_verify_cloned_report(self):
        """
        Step 4: VERIFY — Simulate fetching the cloned report back.

        After POST, the frontend GETs the new report and validates
        the stored config matches what was sent.
        """
        # Build the clone request
        original_config = ReportConfig.model_validate(
            CFO_DASHBOARD_CONFIG.model_dump()
        )
        create_request = CreateReportRequest(
            title="My CFO Dash",
            description="Cloned from CFO Dashboard",
            domain="finance",
            config=original_config,
        )

        # Simulate: POST succeeds, then GET returns the stored report
        stored_response = _simulate_report_response(
            title=create_request.title,
            description=create_request.description,
            domain=create_request.domain,
            config=create_request.config,
        )

        # Verify the stored config matches
        stored_config = ReportConfig.model_validate(stored_response.config)
        assert stored_config == original_config
        assert stored_response.title == "My CFO Dash"

    def test_full_workflow_all_golden_reports(self):
        """
        Full workflow for ALL golden reports: fetch → validate → clone → verify.
        """
        for report in GOLDEN_REPORTS:
            # 1. Fetch
            response = _simulate_report_response(
                title=report["title"],
                description=report["description"],
                domain=report["domain"],
                config=report["config"],
            )

            # 2. Validate
            parsed = ReportConfig.model_validate(response.config)
            assert len(parsed.widgets) >= 1

            # 3. Clone
            cloned = ReportConfig.model_validate_json(parsed.model_dump_json())
            create_req = CreateReportRequest(
                title=f"Clone of {report['title']}",
                description=f"Cloned: {report['description']}",
                domain=report["domain"],
                config=cloned,
            )
            assert create_req.title.startswith("Clone of")

            # 4. Verify
            stored = _simulate_report_response(
                title=create_req.title,
                description=create_req.description,
                domain=create_req.domain,
                config=create_req.config,
            )
            final = ReportConfig.model_validate(stored.config)
            assert final == parsed


# ============================================================================
# 4. Widget Constraints — Type-Specific Validation
# ============================================================================

class TestWidgetConstraints:
    """Verify type-specific widget validation rules."""

    def test_chart_requires_data_source(self):
        """CHART widget without data_source is rejected."""
        with pytest.raises(ValidationError, match="CHART widget requires a data_source"):
            Widget(
                id="bad-chart", type=WidgetType.CHART, title="Bad",
                position=GridPosition(x=0, y=0, w=6, h=2),
                data_source=None,
                visualization=VisualizationOptions(chart_type=ChartType.BAR),
            )

    def test_chart_requires_chart_type(self):
        """CHART widget without chart_type is rejected."""
        with pytest.raises(ValidationError, match="CHART widget requires visualization.chart_type"):
            Widget(
                id="bad-chart", type=WidgetType.CHART, title="Bad",
                position=GridPosition(x=0, y=0, w=6, h=2),
                data_source=DataSource(
                    view=ViewScope.SALES_DAILY,
                    metrics=[ReportMetric.REVENUE],
                ),
                visualization=VisualizationOptions(chart_type=None),
            )

    def test_kpi_requires_data_source(self):
        """KPI widget without data_source is rejected."""
        with pytest.raises(ValidationError, match="KPI widget requires a data_source"):
            Widget(
                id="bad-kpi", type=WidgetType.KPI, title="Bad",
                position=GridPosition(x=0, y=0, w=4, h=1),
                data_source=None,
            )

    def test_table_requires_data_source(self):
        """TABLE widget without data_source is rejected."""
        with pytest.raises(ValidationError, match="TABLE widget requires a data_source"):
            Widget(
                id="bad-table", type=WidgetType.TABLE, title="Bad",
                position=GridPosition(x=0, y=0, w=12, h=3),
                data_source=None,
            )

    def test_text_requires_content_or_source(self):
        """TEXT widget without static_content or data_source is rejected."""
        with pytest.raises(ValidationError, match="TEXT widget requires"):
            Widget(
                id="bad-text", type=WidgetType.TEXT, title="Bad",
                position=GridPosition(x=0, y=0, w=6, h=1),
                data_source=None,
                static_content=None,
            )

    def test_text_with_static_content_valid(self):
        """TEXT widget with static_content is valid."""
        w = Widget(
            id="note", type=WidgetType.TEXT, title="Note",
            position=GridPosition(x=0, y=0, w=6, h=1),
            static_content="This report shows Q4 financials.",
        )
        assert w.static_content == "This report shows Q4 financials."


# ============================================================================
# 5. Grid Bounds — Layout Constraint Enforcement
# ============================================================================

class TestGridBounds:
    """Verify grid boundary enforcement."""

    def test_widget_exceeds_grid_rejected(self):
        """Widget that exceeds grid columns is rejected."""
        with pytest.raises(ValidationError, match="exceeds grid bounds"):
            ReportConfig(
                layout=GridLayout(columns=12),
                widgets=[
                    _make_kpi_widget("w1", x=10, w=4),  # 10+4=14 > 12
                ],
            )

    def test_widget_fits_grid_accepted(self):
        """Widget that fits within grid is accepted."""
        config = ReportConfig(
            layout=GridLayout(columns=12),
            widgets=[
                _make_kpi_widget("w1", x=8, w=4),  # 8+4=12 == 12, OK
            ],
        )
        assert len(config.widgets) == 1

    def test_duplicate_widget_ids_rejected(self):
        """Duplicate widget IDs within a report are rejected."""
        with pytest.raises(ValidationError, match="Duplicate widget IDs"):
            ReportConfig(
                widgets=[
                    _make_kpi_widget("same-id", x=0),
                    _make_kpi_widget("same-id", x=6),
                ],
            )


# ============================================================================
# 6. JSON Round-Trip — Serialize → Deserialize Fidelity
# ============================================================================

class TestJsonRoundTrip:
    """Verify JSON serialization preserves all type information."""

    def test_cfo_dashboard_round_trip(self):
        """CFO Dashboard survives JSON round-trip."""
        _assert_round_trip(CFO_DASHBOARD_CONFIG)

    def test_sales_tracker_round_trip(self):
        """Sales Tracker survives JSON round-trip."""
        _assert_round_trip(SALES_TRACKER_CONFIG)

    def test_ar_aging_round_trip(self):
        """AR Aging survives JSON round-trip."""
        _assert_round_trip(AR_AGING_CONFIG)

    def test_enum_values_in_json(self):
        """Enum values are serialized as strings, not objects."""
        json_str = CFO_DASHBOARD_CONFIG.model_dump_json()
        data = json.loads(json_str)

        # Check top-level enums
        assert data["version"] == "1.0"

        # Check widget-level enums
        revenue_widget = next(w for w in data["widgets"] if w["id"] == "revenue-bar")
        assert revenue_widget["type"] == "chart"
        assert revenue_widget["visualization"]["chart_type"] == "bar"
        assert revenue_widget["visualization"]["palette"] == "revenue"
        assert revenue_widget["data_source"]["view"] == "sales_daily"
        assert revenue_widget["data_source"]["metrics"] == ["revenue"]
        assert revenue_widget["data_source"]["time_granularity"] == "month"

    def test_config_to_dict_for_jsonb(self):
        """Config can be serialized to dict for JSONB storage."""
        config_dict = CFO_DASHBOARD_CONFIG.model_dump()
        assert isinstance(config_dict, dict)
        assert isinstance(config_dict["widgets"], list)
        assert isinstance(config_dict["layout"], dict)

        # This dict is what goes into sys_reports.config (JSONB)
        # Verify it can be re-parsed
        restored = ReportConfig.model_validate(config_dict)
        assert restored == CFO_DASHBOARD_CONFIG


# ============================================================================
# Helpers
# ============================================================================

def _find_widget(config: ReportConfig, widget_id: str) -> Widget | None:
    """Find a widget by ID in a ReportConfig."""
    for w in config.widgets:
        if w.id == widget_id:
            return w
    return None


def _make_kpi_widget(
    wid: str, x: int = 0, y: int = 0, w: int = 4, h: int = 1,
) -> Widget:
    """Create a minimal valid KPI widget for tests."""
    return Widget(
        id=wid,
        type=WidgetType.KPI,
        title="Test KPI",
        position=GridPosition(x=x, y=y, w=w, h=h),
        data_source=DataSource(
            view=ViewScope.SALES_DAILY,
            metrics=[ReportMetric.REVENUE],
        ),
    )


def _simulate_report_response(
    title: str,
    description: str,
    domain: str,
    config: ReportConfig,
) -> ReportResponse:
    """
    Simulate what the API returns for GET /api/bi/assets/reports/{id}.

    The API serializes ReportConfig to a dict (JSONB) in the response.
    This helper mimics that serialization.
    """
    report_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    return ReportResponse(
        id=report_id,
        urn=f"urn:bi:report:{domain}:{report_id}",
        title=title,
        description=description,
        domain=domain,
        config=config.model_dump(),  # JSONB serialization
        owner_id=owner_id,
        acl=[],
        created_at=now,
        updated_at=now,
    )


def _assert_round_trip(config: ReportConfig) -> None:
    """Assert a ReportConfig survives JSON round-trip."""
    json_str = config.model_dump_json()
    restored = ReportConfig.model_validate_json(json_str)
    assert restored == config

    # Also test dict round-trip (JSONB path)
    config_dict = config.model_dump()
    restored_dict = ReportConfig.model_validate(config_dict)
    assert restored_dict == config
