# S7-5: Operational Views — Headless BI Schema Definition

**Status**: ✅ Complete
**Date**: 2026-02-09
**Depends On**: S7-4 (Tenant-Scoped Assets), S6-3 (Semantic Layer)

---

## 1. Objective

Define and validate the `ReportConfig` JSON schema as the contract between
backend storage and future frontend rendering. Seed three "golden reports"
that serve as reference implementations, mock data, and type definitions.

**Key Principle**: "If it's not in the Enum, the frontend can't render it."

---

## 2. Architecture — The ReportConfig Contract

```
ReportConfig (core/bi/report_config.py)
├── version: SchemaVersion          ← forward compatibility
├── layout: GridLayout
│   ├── columns: int (1-24, default 12)
│   ├── row_height: int (40-200px)
│   └── gap: int (0-48px)
├── widgets: list[Widget]           ← min 1, unique IDs
│   ├── id: str (kebab/snake_case)
│   ├── type: WidgetType            ← CHART | KPI | TABLE | TEXT
│   ├── title: str
│   ├── position: GridPosition      ← x, y, w, h on grid
│   ├── data_source: DataSource     ← binds to S6 semantic layer
│   │   ├── view: ViewScope         ← S6 enum
│   │   ├── metrics: [ReportMetric] ← S6 enum
│   │   ├── dimensions: [ReportDimension] ← S6 enum
│   │   ├── time_granularity: TimeGranularity
│   │   └── aggregation: Aggregation
│   ├── visualization: VisualizationOptions
│   │   ├── chart_type: ChartType   ← BAR | LINE | AREA | PIE | DONUT | STACKED_BAR
│   │   ├── palette: ColorPalette   ← DEFAULT | REVENUE | EXPENSE | ...
│   │   ├── x_axis / y_axis: AxisConfig
│   │   └── value_format: str
│   └── static_content: str         ← TEXT widgets only
└── settings: ReportSettings
    ├── refresh_interval: RefreshInterval
    ├── default_date_range_days: int
    └── currency_code: str
```

### Strong Typing Guarantees

| Field | Type | Prevents |
|-------|------|----------|
| `Widget.type` | `WidgetType` enum | Unknown widget types |
| `DataSource.view` | `ViewScope` enum | Querying non-reporting tables |
| `DataSource.metrics` | `ReportMetric` enum | Invalid column references |
| `DataSource.dimensions` | `ReportDimension` enum | Invalid GROUP BY axes |
| `visualization.chart_type` | `ChartType` enum | Unknown chart renderers |
| `visualization.palette` | `ColorPalette` enum | Invalid color schemes |
| `DataSource.aggregation` | `Aggregation` enum | Unknown aggregation functions |

### Widget Validation Rules

| Widget Type | data_source | chart_type | static_content |
|-------------|-------------|------------|----------------|
| CHART | **required** | **required** | — |
| KPI | **required** | — | — |
| TABLE | **required** | — | — |
| TEXT | optional | — | required if no data_source |

### Grid Constraints

- 12-column grid (configurable 1-24)
- `x + w <= columns` enforced at model level
- Widget IDs must be unique within a report

---

## 3. Golden Reports

| # | Report | Domain | Widgets | Key Data Sources |
|---|--------|--------|---------|------------------|
| 1 | **CFO Dashboard** | finance | 4 (bar chart + 3 KPIs) | SALES_DAILY, CASH_FLOW_DAILY, RECEIVABLES_SUMMARY |
| 2 | **Sales Tracker** | sales | 2 (line chart + bar chart) | SALES_DAILY |
| 3 | **AR Aging** | finance | 3 (table + 2 KPIs) | RECEIVABLES_SUMMARY |

All configs are defined in `scripts/seed_bi_assets.py` using the strong-typed
schema. They pass JSON round-trip validation (serialize → deserialize → equal).

---

## 4. S6 Semantic Layer Binding

The `DataSource` model creates a direct, type-safe link from report config
to the S6 query engine:

```
ReportConfig.Widget.data_source
    ├── view: ViewScope.SALES_DAILY
    ├── metrics: [ReportMetric.REVENUE]
    └── dimensions: [ReportDimension.DATE]
            │
            ▼
SemanticQueryBuilder.build_query()
    ├── resolve_metric_column(SALES_DAILY, REVENUE) → "daily_revenue"
    └── resolve_dimension_column(SALES_DAILY, DATE) → "transaction_date"
            │
            ▼
SELECT transaction_date, daily_revenue FROM mv_sales_daily ...
```

---

## 5. Test Coverage (225 tests total)

| Category | Count | File | Description |
|----------|-------|------|-------------|
| S7-1 Policy Engine | 55 | `test_s7_1_policy.py` | Evaluation order, role matrix |
| S7-2+S7-3 Enforcement+Audit | 38 | `test_s7_2_enforcement.py` | HTTP enforcement, audit |
| S7-4 Core (Owner+ACL+Registry) | 54 | `test_s7_4_tenant_assets.py` | Owner bypass, ACL, cache |
| S7-4-T3 (Resolver+Schemas+API) | 36 | `test_s7_4_t3_resolver_api.py` | URN parsing, row→asset |
| **S7-5 Headless Usage** | **42** | `test_s7_5_headless_usage.py` | Schema, golden reports, API sim |

### S7-5 Test Breakdown

| Category | Count | Description |
|----------|-------|-------------|
| Schema Contract | 11 | All enum fields reject invalid strings |
| Golden Reports | 12 | 3 reports valid, widget types, data sources, grid fit |
| API Simulation | 5 | Fetch → Validate → Clone → Verify workflow |
| Widget Constraints | 6 | Type-specific validation (chart needs chart_type, etc.) |
| Grid Bounds | 3 | Overflow rejected, fit accepted, duplicate IDs rejected |
| JSON Round-Trip | 5 | Serialize → deserialize fidelity, enum string values |

**Full regression**: 225/225 passed in 1.16s.

---

## 6. Files

| File | Action | Description |
|------|--------|-------------|
| `core/bi/__init__.py` | **NEW** | Package init, re-exports all schema types |
| `core/bi/report_config.py` | **NEW** | ReportConfig contract (12 Pydantic models, 8 enums) |
| `scripts/seed_bi_assets.py` | **NEW** | 3 golden report configs + validation CLI |
| `tests/test_s7_5_headless_usage.py` | **NEW** | 42 tests: schema, golden, API sim, constraints |
| `api/schemas/report.py` | **MODIFIED** | Swapped weak ReportConfig → strong-typed import |
| `tests/test_s7_4_t3_resolver_api.py` | **MODIFIED** | Updated to use new strong-typed schema |

---

## 7. Schema Evolution Strategy

- `SchemaVersion.V1` is the current version.
- When the schema evolves, add `V2` to the enum.
- The backend can migrate old configs: `if version == V1: migrate_to_v2(config)`.
- Frontend checks `config.version` and renders accordingly.
