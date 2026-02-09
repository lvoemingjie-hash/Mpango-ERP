"""
S7-5: ReportConfig — The Headless BI Contract.

Philosophy: "If it's not in the Enum, the frontend can't render it."

This module defines the SINGLE SOURCE OF TRUTH for what a BI report
configuration looks like. It is the contract between the backend
(which stores and validates) and the future frontend (which renders).

Every field that could be a free-form string is instead a strong-typed
Enum. This ensures:
1. Backend rejects invalid configs at the Pydantic boundary.
2. Frontend can exhaustively switch on widget types, chart types, etc.
3. No garbage data enters sys_reports.config JSONB.

Architecture:
    ReportConfig
    ├── version: SchemaVersion (for future migrations)
    ├── layout: GridLayout
    │   └── columns: int (grid column count)
    ├── widgets: list[Widget]
    │   ├── id: str (unique within report)
    │   ├── type: WidgetType (chart | kpi | table | text)
    │   ├── title: str
    │   ├── position: GridPosition (x, y, w, h)
    │   ├── data_source: DataSource (view_scope + metrics + dimensions)
    │   └── visualization: VisualizationOptions (chart_type, colors, axis)
    └── settings: ReportSettings (refresh, theme, etc.)

Data Source Binding:
    Widget.data_source references S6 semantic layer enums:
    - ViewScope → which reporting view to query
    - ReportMetric → which columns to SELECT
    - ReportDimension → which axes to GROUP BY

    This creates a direct, type-safe link from the report config
    to the query engine. The frontend sends the config, the backend
    resolves it to SQL via SemanticQueryBuilder.

🔒 S7-5-C1: All enum values match S6 semantic layer exactly.
    ReportMetric, ReportDimension, ViewScope are re-exported here
    for schema completeness, but defined in services/reporting/semantic_layer.py.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from services.reporting.semantic_layer import (
    ReportDimension,
    ReportMetric,
    TimeGranularity,
    ViewScope,
)


# ============================================================================
# 1. Schema Version — Forward Compatibility
# ============================================================================

class SchemaVersion(str, Enum):
    """
    Report config schema version.

    When the schema evolves, add a new version here.
    The backend can then migrate old configs to new format.
    """
    V1 = "1.0"


# ============================================================================
# 2. Widget Type — What kind of component to render
# ============================================================================

class WidgetType(str, Enum):
    """
    Exhaustive list of renderable widget types.

    The frontend MUST handle every value in this enum.
    If a new widget type is needed, it is added here first,
    then the frontend implements the renderer.
    """
    CHART = "chart"
    KPI = "kpi"
    TABLE = "table"
    TEXT = "text"


# ============================================================================
# 3. Chart Type — Visualization subtype for CHART widgets
# ============================================================================

class ChartType(str, Enum):
    """
    Chart visualization subtypes.

    Only applicable when WidgetType == CHART.
    """
    BAR = "bar"
    LINE = "line"
    AREA = "area"
    PIE = "pie"
    DONUT = "donut"
    STACKED_BAR = "stacked_bar"


# ============================================================================
# 4. Color Palette — Pre-defined color schemes
# ============================================================================

class ColorPalette(str, Enum):
    """
    Named color palettes for chart rendering.

    Each palette maps to a set of hex colors defined by the frontend
    theme. The backend only stores the palette name, not the colors.
    """
    DEFAULT = "default"
    REVENUE = "revenue"          # Greens — growth/money
    EXPENSE = "expense"          # Reds — cost/loss
    NEUTRAL = "neutral"          # Grays — informational
    CATEGORICAL = "categorical"  # Multi-color — distinct categories
    SEQUENTIAL = "sequential"    # Single-hue gradient — magnitude


# ============================================================================
# 5. Aggregation — How to reduce multiple values
# ============================================================================

class Aggregation(str, Enum):
    """
    Aggregation functions for metric display.

    Applied when a widget needs to reduce a time series to a single
    value (e.g., KPI card showing "Total Revenue").
    """
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    LATEST = "latest"  # Most recent value (for running balances)


# ============================================================================
# 6. Grid Position — Widget placement on the layout grid
# ============================================================================

class GridPosition(BaseModel):
    """
    Widget position and size on a CSS Grid / dashboard grid.

    Uses a 12-column grid system (standard for dashboards).
    (x, y) is the top-left cell. (w, h) is the span.
    """
    x: int = Field(
        ..., ge=0, lt=12,
        description="Column start (0-indexed, 12-column grid)",
    )
    y: int = Field(
        ..., ge=0,
        description="Row start (0-indexed, grows downward)",
    )
    w: int = Field(
        ..., ge=1, le=12,
        description="Column span (1-12)",
    )
    h: int = Field(
        ..., ge=1, le=8,
        description="Row span (1-8)",
    )


# ============================================================================
# 7. Data Source — Binds a widget to S6 semantic layer
# ============================================================================

class DataSource(BaseModel):
    """
    Binds a widget to the S6 semantic query engine.

    This is the bridge between the report config and the query builder.
    Every field references an S6 enum, creating a type-safe pipeline:

        ReportConfig → DataSource → SemanticQueryBuilder → SQL

    The frontend sends the DataSource as part of the widget config.
    The backend resolves it to a SQL query via the semantic layer.
    """
    view: ViewScope = Field(
        ...,
        description="Which reporting view to query (S6 ViewScope enum)",
    )
    metrics: list[ReportMetric] = Field(
        ...,
        min_length=1,
        description="Metrics to SELECT (S6 ReportMetric enum)",
    )
    dimensions: list[ReportDimension] = Field(
        default_factory=list,
        description="Dimensions to GROUP BY (S6 ReportDimension enum)",
    )
    time_granularity: Optional[TimeGranularity] = Field(
        default=None,
        description="Time bucketing for trend charts (day/week/month)",
    )
    aggregation: Aggregation = Field(
        default=Aggregation.SUM,
        description="How to aggregate metrics (for KPI single-value display)",
    )


# ============================================================================
# 8. Visualization Options — How to render the data
# ============================================================================

class AxisConfig(BaseModel):
    """Configuration for a chart axis."""
    label: str = Field(
        default="",
        max_length=128,
        description="Axis label text",
    )
    format: str = Field(
        default="number",
        description="Value format: 'number', 'currency', 'percent', 'date'",
    )


class VisualizationOptions(BaseModel):
    """
    Rendering options for a widget.

    Only chart_type is required for CHART widgets.
    KPI/TABLE/TEXT widgets may ignore most of these.
    """
    chart_type: Optional[ChartType] = Field(
        default=None,
        description="Chart subtype (required for WidgetType.CHART)",
    )
    palette: ColorPalette = Field(
        default=ColorPalette.DEFAULT,
        description="Color palette for the visualization",
    )
    show_legend: bool = Field(
        default=True,
        description="Whether to show the chart legend",
    )
    show_grid: bool = Field(
        default=True,
        description="Whether to show grid lines",
    )
    x_axis: Optional[AxisConfig] = Field(
        default=None,
        description="X-axis configuration (for charts)",
    )
    y_axis: Optional[AxisConfig] = Field(
        default=None,
        description="Y-axis configuration (for charts)",
    )
    value_format: str = Field(
        default="number",
        description="Value display format: 'number', 'currency', 'percent'",
    )
    currency_code: str = Field(
        default="USD",
        max_length=3,
        description="ISO 4217 currency code for currency formatting",
    )


# ============================================================================
# 9. Widget — A single renderable component
# ============================================================================

class Widget(BaseModel):
    """
    A single widget in a report layout.

    Each widget has:
    - A unique ID (for frontend keying and state management)
    - A strong-typed type (what to render)
    - A grid position (where to render)
    - A data source (what data to fetch)
    - Visualization options (how to render)

    The widget is self-contained: given a Widget object, the frontend
    has everything it needs to render it without additional API calls
    for configuration.
    """
    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Unique widget ID within the report (kebab-case or snake_case)",
    )
    type: WidgetType = Field(
        ...,
        description="Widget type determines the renderer",
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Widget display title",
    )
    description: str = Field(
        default="",
        max_length=512,
        description="Optional widget description / subtitle",
    )
    position: GridPosition = Field(
        ...,
        description="Grid placement (x, y, w, h)",
    )
    data_source: Optional[DataSource] = Field(
        default=None,
        description="Data binding to S6 semantic layer. "
                    "Required for chart/kpi/table. Optional for text.",
    )
    visualization: VisualizationOptions = Field(
        default_factory=VisualizationOptions,
        description="Rendering options",
    )
    static_content: Optional[str] = Field(
        default=None,
        max_length=4096,
        description="Static text/markdown content (for TEXT widgets only)",
    )

    @model_validator(mode="after")
    def validate_widget_constraints(self) -> "Widget":
        """Enforce type-specific constraints."""
        # CHART widgets MUST have a chart_type
        if self.type == WidgetType.CHART:
            if self.data_source is None:
                raise ValueError("CHART widget requires a data_source")
            if self.visualization.chart_type is None:
                raise ValueError("CHART widget requires visualization.chart_type")

        # KPI widgets MUST have a data_source
        if self.type == WidgetType.KPI:
            if self.data_source is None:
                raise ValueError("KPI widget requires a data_source")

        # TABLE widgets MUST have a data_source
        if self.type == WidgetType.TABLE:
            if self.data_source is None:
                raise ValueError("TABLE widget requires a data_source")

        # TEXT widgets SHOULD have static_content
        if self.type == WidgetType.TEXT:
            if self.static_content is None and self.data_source is None:
                raise ValueError(
                    "TEXT widget requires either static_content or data_source"
                )

        return self


# ============================================================================
# 10. Grid Layout — Top-level layout definition
# ============================================================================

class GridLayout(BaseModel):
    """
    Dashboard grid layout configuration.

    Uses a 12-column grid system. Widgets are placed on this grid
    using their GridPosition (x, y, w, h).
    """
    columns: int = Field(
        default=12,
        ge=1,
        le=24,
        description="Number of grid columns (standard: 12)",
    )
    row_height: int = Field(
        default=80,
        ge=40,
        le=200,
        description="Height of each grid row in pixels",
    )
    gap: int = Field(
        default=16,
        ge=0,
        le=48,
        description="Gap between grid cells in pixels",
    )


# ============================================================================
# 11. Report Settings — Global report configuration
# ============================================================================

class RefreshInterval(str, Enum):
    """Auto-refresh intervals for live dashboards."""
    OFF = "off"
    SECONDS_30 = "30s"
    MINUTES_1 = "1m"
    MINUTES_5 = "5m"
    MINUTES_15 = "15m"


class ReportSettings(BaseModel):
    """Global settings that apply to the entire report."""
    refresh_interval: RefreshInterval = Field(
        default=RefreshInterval.OFF,
        description="Auto-refresh interval for live data",
    )
    default_date_range_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Default date range in days for time-based widgets",
    )
    currency_code: str = Field(
        default="USD",
        max_length=3,
        description="Default currency for the report",
    )


# ============================================================================
# 12. ReportConfig — THE CONTRACT
# ============================================================================

class ReportConfig(BaseModel):
    """
    S7-5: The Headless BI Report Configuration Contract.

    This is the top-level schema stored in sys_reports.config (JSONB).
    It is the SINGLE SOURCE OF TRUTH for what a report looks like,
    what data it needs, and how to render it.

    The contract guarantees:
    1. Every widget type is a known WidgetType enum value.
    2. Every data source references valid S6 semantic layer enums.
    3. Every chart has a valid ChartType.
    4. Every position fits on the grid.
    5. Widget IDs are unique within the report.

    Usage:
        # Validate a config from DB
        config = ReportConfig.model_validate(json_from_db)

        # Serialize for API response
        config.model_dump()

        # Create programmatically
        config = ReportConfig(
            layout=GridLayout(columns=12),
            widgets=[Widget(...)],
        )
    """
    version: SchemaVersion = Field(
        default=SchemaVersion.V1,
        description="Schema version for forward compatibility",
    )
    layout: GridLayout = Field(
        default_factory=GridLayout,
        description="Grid layout configuration",
    )
    widgets: list[Widget] = Field(
        ...,
        min_length=1,
        description="At least one widget is required",
    )
    settings: ReportSettings = Field(
        default_factory=ReportSettings,
        description="Global report settings",
    )

    @field_validator("widgets")
    @classmethod
    def validate_unique_widget_ids(cls, v: list[Widget]) -> list[Widget]:
        """Ensure all widget IDs are unique within the report."""
        ids = [w.id for w in v]
        if len(ids) != len(set(ids)):
            duplicates = [wid for wid in ids if ids.count(wid) > 1]
            raise ValueError(
                f"Duplicate widget IDs found: {set(duplicates)}. "
                f"Each widget must have a unique ID."
            )
        return v

    @model_validator(mode="after")
    def validate_grid_bounds(self) -> "ReportConfig":
        """Ensure all widgets fit within the grid columns."""
        cols = self.layout.columns
        for w in self.widgets:
            if w.position.x + w.position.w > cols:
                raise ValueError(
                    f"Widget '{w.id}' exceeds grid bounds: "
                    f"x({w.position.x}) + w({w.position.w}) = "
                    f"{w.position.x + w.position.w} > columns({cols})"
                )
        return self
