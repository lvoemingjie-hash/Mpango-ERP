"""
S7-5: Headless BI — Report Configuration Contract.

This package contains the strong-typed Pydantic schemas that define
the contract between backend storage and future frontend rendering.
"""
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

__all__ = [
    "Aggregation",
    "AxisConfig",
    "ChartType",
    "ColorPalette",
    "DataSource",
    "GridLayout",
    "GridPosition",
    "RefreshInterval",
    "ReportConfig",
    "ReportSettings",
    "SchemaVersion",
    "VisualizationOptions",
    "Widget",
    "WidgetType",
]
