# S6-3: Dashboard API & Reporting Facade — Ops Ledger

**Track**: S6-3 (Dashboard API & Reporting Facade)
**Date**: 2026-02-07
**Status**: ✅ COMPLETE (v3 — Canonical Constraints Enforced)
**Author**: Backend AI
**Depends On**: S6-2 (Materialized Views) — ✅ COMPLETE

---

## 0. API Contract Compliance Audit

Before implementation, the existing `api_contract.md` and `openapi.yaml` were
reviewed for conflicts. Two issues were found and resolved:

| # | Conflict | Resolution |
|---|----------|------------|
| 1 | **Response Envelope** — Contract §3.1 requires `{"success": true, "data": {...}, "timestamp": "..."}`. Original S6-3 returned flat objects. | All endpoints now use `make_success()` / `make_error()` envelope helpers. |
| 2 | **Error Format** — Contract §3.3 requires `{"success": false, "error": {"code": ..., "message": ...}, "timestamp": "..."}`. Original used raw `HTTPException.detail`. | All errors now use `JSONResponse` + `make_error()` with contract-compliant structure. |

No conflicts found with: path prefix (`/api/v1/`), JWT auth, tenant-from-claims.

### 0.2 CANONICAL_CONSTRAINTS.md Enforcement Audit

All four constraint rules were audited and verified. `#[Constraint Check]` comments
mark every enforcement point in the codebase.

| Rule | Constraint | Enforcement Point | Status |
|------|-----------|-------------------|--------|
| **#1** | `tenant_id` ONLY from trusted context; `SET LOCAL search_path` before execution | `_extract_tenant()` reads `request.state`; `_ensure_tenant_scope()` calls `SET LOCAL` | ✅ |
| **#1** | KPI endpoint must use Builder for isolation | `get_kpi_summary()` calls `_build_builder()` → `fetch_kpi_summary()` | ✅ |
| **#3** | Target tables MUST be `rpt_*` or `mv_*` | `ViewScope` enum + `_REGISTRY` only contain `mv_sales_daily`, `rpt_receivables_summary`, `rpt_cash_flow_daily` | ✅ |
| **#3** | Time filtering MUST use `transaction_date` | `ReportDimension.DATE` → `transaction_date` in all views; `build_query()` filters on this column | ✅ |
| **#3** | Currency filtering MUST use `reporting_currency_code` | `ReportDimension.CURRENCY` → `reporting_currency_code` in all views | ✅ |
| **#3** | Violation: `created_at` or `ledger_entries` directly | Neither appears anywhere in reporting code | ✅ |
| **#4** | All inputs must be whitelisted Enums; NO dynamic strings | `SemanticQueryRequest` uses `ViewScope`, `ReportMetric`, `ReportDimension` Pydantic fields | ✅ |

**Column Mapping Verification** (per constraint spec):
- `ReportMetric.REVENUE` → `MvSalesDaily.daily_revenue` ✅ (model column is `daily_revenue`, line 63 of `reporting.py`)
- `ReportDimension.DATE` → `MvSalesDaily.transaction_date` ✅

---

## 1. Objective

Implement a **Controlled BI Semantic Facade** — not a generic query engine.
The frontend consumes business-semantic enums, never raw column names or SQL.

### CTO Directives (Strictly Enforced)

1. **S6-3 ≠ Generic Query Engine** — It is a controlled BI facade
2. **Whitelist Mechanism** — Only `rpt_*` / `mv_*` views are queryable
3. **Semantic Mapping** — All metrics/dimensions are backend Enums
4. **Tenant as Scope** — `tenant_id` is not a filter, it's the execution context

---

## 2. Architecture: Three-Tier API

```
┌─────────────────────────────────────────────────────────────────┐
│                    DASHBOARD API (S6-3)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  TIER 1: KPI Endpoints                                          │
│  GET /api/v1/dashboards/kpi/summary                             │
│  ├── Hardcoded metrics (no user params)                         │
│  ├── Used for: Dashboard header cards                           │
│  └── NEVER calls SemanticQueryBuilder                           │
│                                                                 │
│  TIER 2: Chart Endpoints                                        │
│  GET /api/v1/dashboards/charts/sales-trend                      │
│  GET /api/v1/dashboards/charts/cash-flow                        │
│  ├── Limited params: date_range + granularity ONLY              │
│  ├── Metric is hardcoded per endpoint                           │
│  └── Used for: Dashboard trend charts                           │
│                                                                 │
│  TIER 3: Ad-hoc Analysis                                        │
│  POST /api/v1/reports/analyze                                   │
│  ├── Calls SemanticQueryBuilder                                 │
│  ├── All metrics/dimensions validated via Enum whitelist        │
│  └── Used for: Advanced reporting page                          │
│                                                                 │
│  Discovery:                                                     │
│  GET /api/v1/reports/schema/{view_scope}                        │
│  └── Returns available metrics/dimensions for a view            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Semantic Layer

### 3.1 Enums

| Enum | Purpose | Values |
|------|---------|--------|
| `ViewScope` | Whitelist of queryable views | `sales_daily`, `receivables_summary`, `cash_flow_daily` |
| `ReportMetric` | Business metric identifiers | `revenue`, `transaction_count`, `outstanding_balance`, `receivable_entry_count`, `net_cash_change`, `running_balance`, `cash_transaction_count` |
| `ReportDimension` | Grouping/filter axes | `date`, `currency`, `entity_id`, `entity_type` |
| `TimeGranularity` | Chart time bucketing | `day`, `week`, `month` |

### 3.2 Registry Mapping

| ViewScope | Metric Enum | → Column |
|-----------|-------------|----------|
| `SALES_DAILY` | `REVENUE` | `MvSalesDaily.daily_revenue` |
| `SALES_DAILY` | `TRANSACTION_COUNT` | `MvSalesDaily.transaction_count` |
| `RECEIVABLES_SUMMARY` | `OUTSTANDING_BALANCE` | `RptReceivablesSummary.outstanding_balance` |
| `RECEIVABLES_SUMMARY` | `RECEIVABLE_ENTRY_COUNT` | `RptReceivablesSummary.entry_count` |
| `CASH_FLOW_DAILY` | `NET_CASH_CHANGE` | `RptCashFlowDaily.net_change` |
| `CASH_FLOW_DAILY` | `RUNNING_BALANCE` | `RptCashFlowDaily.running_balance` |
| `CASH_FLOW_DAILY` | `CASH_TRANSACTION_COUNT` | `RptCashFlowDaily.transaction_count` |

### 3.3 How "Semantic Drift" is Prevented

Revenue is ALWAYS resolved to `MvSalesDaily.daily_revenue` via the Registry.
There is no code path where it could accidentally resolve to `transaction_amount`
or any other column. The mapping is frozen in `_REGISTRY` and only changeable
by a backend engineer modifying `semantic_layer.py`.

---

## 4. Security Model

### 4.1 Non-Reporting Table Rejection

If the frontend tries to query the `User` table or `orders` table:

1. **ViewScope enum** — Only `sales_daily`, `receivables_summary`, `cash_flow_daily` exist
2. **Pydantic validation** — `view="users"` → 422 Unprocessable Entity
3. **Registry** — Only `mv_*` / `rpt_*` models are registered
4. **The request never reaches the database**

### 4.2 Tenant Isolation

- `tenant_schema` is derived from JWT claims (via `TenantContext`)
- `SemanticQueryBuilder` ALWAYS calls `SET LOCAL search_path` before any query
- There is no method to skip or override tenant scoping
- The builder constructor requires `tenant_schema` — it's not optional

### 4.3 Input Validation Layers

```
Frontend Request
    │
    ▼
[Pydantic] ── Invalid enum? → 422 (never reaches service)
    │
    ▼
[Router] ── Cross-view metric? → 422 (metric not on this view)
    │
    ▼
[SemanticQueryBuilder] ── Resolves enum → column via Registry
    │
    ▼
[Reporting Engine] ── Read-only user, 30s timeout
```

### 4.4 Empty Materialized View Handling

When `mv_sales_daily` has no data (not yet refreshed):

- `fetch_kpi_summary()` uses `COALESCE(SUM(col), 0)` → returns `0.0000`
- Never returns `null` or raises an error
- Frontend always receives valid numeric values

---

## 5. API Endpoints

### TIER 1: KPI

| Method | Path | Parameters | Response |
|--------|------|-----------|----------|
| `GET` | `/api/v1/dashboards/kpi/summary` | None | `KpiSummaryResponse` with 3 cards |

**Cards returned**:
- Total Revenue (from `mv_sales_daily`)
- Outstanding Receivables (from `rpt_receivables_summary`)
- Net Cash Position (from `rpt_cash_flow_daily`)

### TIER 2: Charts

| Method | Path | Parameters | Response |
|--------|------|-----------|----------|
| `GET` | `/api/v1/dashboards/charts/sales-trend` | `date_from`, `date_to`, `granularity` | `ChartResponse` |
| `GET` | `/api/v1/dashboards/charts/cash-flow` | `date_from`, `date_to`, `granularity` | `ChartResponse` |

### TIER 3: Ad-hoc

| Method | Path | Body | Response |
|--------|------|------|----------|
| `POST` | `/api/v1/reports/analyze` | `SemanticQueryRequest` | `AnalyzeResponse` |
| `GET` | `/api/v1/reports/schema/{view_scope}` | Path param | Schema discovery |

### Example: Ad-hoc Request

```json
POST /api/v1/reports/analyze
{
    "view": "sales_daily",
    "metrics": ["revenue", "transaction_count"],
    "dimensions": ["date", "currency"],
    "date_from": "2026-01-01",
    "date_to": "2026-01-31",
    "limit": 500
}
```

### Example: What Gets Rejected

```json
// ❌ Invalid view — Pydantic rejects at 422
{"view": "users_table", "metrics": ["revenue"]}

// ❌ Raw column name — Pydantic rejects at 422
{"view": "sales_daily", "metrics": ["daily_revenue"]}

// ❌ SQL injection — Pydantic rejects at 422
{"view": "sales_daily; DROP TABLE users;--", "metrics": ["revenue"]}

// ❌ Cross-view metric — Router rejects at 422
{"view": "sales_daily", "metrics": ["outstanding_balance"]}
```

---

## 6. Test Results (27/27 Passed)

### Semantic Layer Tests (10)

```
✅ test_all_view_scopes_registered
✅ test_resolve_revenue_metric
✅ test_resolve_outstanding_balance
✅ test_resolve_date_dimension
✅ test_invalid_metric_on_view_raises
✅ test_invalid_dimension_on_view_raises
✅ test_available_metrics_returns_correct_list
✅ test_materialized_flag
✅ test_resolve_column_unified          (NEW: resolve_column() for metrics + dimensions)
✅ test_resolve_column_rejects_wrong_type (NEW: TypeError on non-enum input)
```

### Whitelist Security Tests (3)

```
✅ test_no_user_table_in_registry
✅ test_view_scope_enum_is_exhaustive
✅ test_registry_models_are_views
```

### Pydantic Validation Tests (8)

```
✅ test_valid_request_parses
✅ test_invalid_view_rejected
✅ test_invalid_metric_rejected
✅ test_invalid_dimension_rejected
✅ test_empty_metrics_rejected
✅ test_limit_bounds
✅ test_raw_column_name_rejected
✅ test_sql_injection_in_view_rejected
```

### Integration Tests (6)

```
✅ test_query_builder_fetch_kpi_summary
✅ test_query_builder_fetch_all_receivables
✅ test_query_builder_fetch_time_series
✅ test_query_builder_empty_mv_returns_zeros
✅ test_query_builder_cross_view_metric_raises
✅ test_query_builder_reporting_user_access
```

### Regression Tests (S6-2: 5/5 still passing)

```
✅ test_mv_sales_daily_staleness_then_refresh
✅ test_advisory_lock_prevents_double_refresh
✅ test_mv_sales_daily_has_unique_index
✅ test_receivables_summary_is_realtime
✅ test_mv_sales_daily_accessible_by_reporting_user
```

---

## 7. Files Changed

| File | Purpose |
|------|---------|
| `backend/services/reporting/__init__.py` | Package init |
| `backend/services/reporting/semantic_layer.py` | Enums, Registry, mapping functions |
| `backend/services/reporting/query_builder.py` | SemanticQueryBuilder |
| `backend/api/schemas/dashboard.py` | Pydantic request/response schemas |
| `backend/api/v1/dashboards.py` | Three-tier API router |
| `backend/api/app.py` | Router registration |
| `backend/tests/test_s6_3_dashboard_api.py` | 27 tests |
| `ai-ledger/backend/s6-3_dashboard_api.md` | This document |

---

## 8. Frontend Developer Contract

> **"In this system, if you want to query a new field, you must ask the backend
> engineer to add it to the Enum first. You cannot invent parameters in the URL."**

### How to Add a New Metric

1. Backend adds the value to `ReportMetric` enum in `semantic_layer.py`
2. Backend adds the mapping in `_REGISTRY` (enum → column)
3. Frontend can now use the new enum value in requests
4. **There is no other path.**

### How to Add a New View

1. Backend creates the SQL view/materialized view (migration)
2. Backend creates the SQLAlchemy model in `reporting.py`
3. Backend adds `ViewScope` enum value
4. Backend registers the view in `_REGISTRY`
5. Frontend can now query the new view
6. **There is no other path.**

---

---

## 9. Downstream: S6-4 Async Export Engine

**Status**: ✅ COMPLETE (2026-02-07)
**Ledger**: [`ai-ledger/backend/s6-4_async_exports.md`](s6-4_async_exports.md)

S6-4 reuses `SemanticQueryBuilder` directly for async CSV/XLSX exports.
The export worker reconstructs tenant context from the serialized job payload
and enforces the same `SET LOCAL search_path` isolation. 33 tests passed,
27 S6-3 regression tests still passing.

---

**Document Status**: ✅ COMPLETE (v3 — Canonical Constraints Enforced)
**Last Updated**: 2026-02-07
