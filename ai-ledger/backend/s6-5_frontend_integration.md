# S6-5: Frontend Integration Guide — Reporting & BI API

**Track**: S6-5 (Frontend Integration Guide)
**Date**: 2026-02-07
**Status**: ✅ COMPLETE
**Author**: Backend AI
**Audience**: Frontend developers consuming the Mpango ERP Reporting API
**Depends On**: S6-1 → S6-4 (all complete)

---

## 0. The Golden Rule

> **"If it's not in the Enum, it doesn't exist."**

You **CANNOT** send random strings to the reporting API. Every `view`, `metric`,
and `dimension` value must be one of the pre-defined enum values listed in this
document. If you send an invalid value, the API returns **422 Unprocessable Entity**
immediately — your request never reaches the database.

**Why?** The backend uses a semantic whitelist to prevent SQL injection, unauthorized
table access, and schema drift. The API is a controlled facade, not a generic query
engine.

### How to Add a New Field

You cannot do this from the frontend. The process is:

1. Backend engineer adds the value to the relevant Enum
2. Backend engineer adds the column mapping in the Registry
3. Frontend can now use the new enum value
4. **There is no other path.**

---

## 1. The Semantic Contract — Master Enum Reference

### 1.1 ViewScope (which data source to query)

| Enum Value | Description | Data Freshness |
|------------|-------------|----------------|
| `"sales_daily"` | Daily sales aggregation | ⚡ Materialized view (refreshed periodically, may be slightly stale) |
| `"receivables_summary"` | Outstanding receivables by entity | 🔴 Real-time view |
| `"cash_flow_daily"` | Daily cash inflows/outflows | 🔴 Real-time view |

### 1.2 ReportMetric (what numbers to retrieve)

| Enum Value | Available On | Business Meaning |
|------------|-------------|------------------|
| `"revenue"` | `sales_daily` | Total daily revenue in USD |
| `"transaction_count"` | `sales_daily` | Number of transactions |
| `"outstanding_balance"` | `receivables_summary` | Total amount owed |
| `"receivable_entry_count"` | `receivables_summary` | Number of receivable entries |
| `"net_cash_change"` | `cash_flow_daily` | Net cash inflow/outflow per day |
| `"running_balance"` | `cash_flow_daily` | Cumulative cash position |
| `"cash_transaction_count"` | `cash_flow_daily` | Number of cash transactions |

> **Cross-view rule**: You can only use metrics that belong to the chosen view.
> Requesting `"revenue"` on `"receivables_summary"` returns **422**.

### 1.3 ReportDimension (how to group/slice the data)

| Enum Value | Available On | Meaning |
|------------|-------------|---------|
| `"date"` | `sales_daily`, `cash_flow_daily` | Transaction date |
| `"currency"` | `sales_daily`, `receivables_summary`, `cash_flow_daily` | Reporting currency code |
| `"entity_id"` | `receivables_summary` | Customer/supplier UUID |
| `"entity_type"` | `receivables_summary` | Entity classification |

### 1.4 TimeGranularity (for chart endpoints only)

| Enum Value | Meaning |
|------------|---------|
| `"day"` | Daily data points |
| `"week"` | Weekly aggregation |
| `"month"` | Monthly aggregation |

### 1.5 ExportFormat (for async exports)

| Enum Value | Meaning |
|------------|---------|
| `"csv"` | Comma-separated values |
| `"xlsx"` | Excel spreadsheet |

---

## 2. Authentication & Tenant Context

All reporting endpoints require a valid JWT token. The `tenant_id` is extracted
from the token by the backend — you never send it as a parameter.

```typescript
// Every request must include the Authorization header
const headers = {
  "Authorization": `Bearer ${accessToken}`,
  "Content-Type": "application/json",
};
```

The backend uses the JWT's `tenant_id` to set the database `search_path`.
This means:
- You **cannot** query another tenant's data
- You **cannot** omit the token (returns 401)
- You **cannot** override the tenant via query params (there is no such param)

---

## 3. Response Envelope

Every response follows the same envelope format:

### Success (2xx)

```json
{
  "success": true,
  "data": { ... },
  "message": "optional message",
  "timestamp": "2026-02-07T14:00:00+00:00"
}
```

### Error (4xx / 5xx)

```json
{
  "success": false,
  "error": {
    "code": "METRIC_NOT_AVAILABLE",
    "message": "Metric 'revenue' is not available on view 'receivables_summary'",
    "available_values": ["outstanding_balance", "receivable_entry_count"]
  },
  "timestamp": "2026-02-07T14:00:00+00:00"
}
```

**Frontend pattern**: Always check `response.success` first, then read `response.data`
or `response.error`.

```typescript
const res = await fetch("/api/v1/dashboards/kpi/summary", { headers });
const json = await res.json();

if (json.success) {
  renderDashboard(json.data);
} else {
  showError(json.error.code, json.error.message);
}
```

---

## 4. Dashboard Widget Patterns

### 4.1 KPI Cards — `GET /api/v1/dashboards/kpi/summary`

**Use for**: Dashboard header cards (Total Revenue, Outstanding Receivables, Net Cash).

**Parameters**: None. The metrics are hardcoded by the backend.

```typescript
// No parameters needed — just call it
const res = await api.get("/api/v1/dashboards/kpi/summary");
```

**Response shape**:

```json
{
  "success": true,
  "data": {
    "tenant_id": "550e8400-...",
    "generated_at": "2026-02-07T14:00:00+00:00",
    "cards": [
      { "label": "Total Revenue",            "value": 125430.50, "currency": "USD", "trend": null },
      { "label": "Outstanding Receivables",   "value": 45200.00,  "currency": "USD", "trend": null },
      { "label": "Net Cash Position",         "value": 80230.50,  "currency": "USD", "trend": null }
    ],
    "currency": "USD"
  },
  "timestamp": "2026-02-07T14:00:00+00:00"
}
```

**React example**:

```tsx
function KpiCards() {
  const { data, isLoading } = useQuery("kpi-summary", () =>
    api.get("/api/v1/dashboards/kpi/summary")
  );

  if (isLoading) return <Skeleton count={3} />;

  return (
    <div className="grid grid-cols-3 gap-4">
      {data?.data.cards.map((card) => (
        <KpiCard
          key={card.label}
          label={card.label}
          value={card.value}
          currency={card.currency}
        />
      ))}
    </div>
  );
}
```

---

### 4.2 Charts — `GET /api/v1/dashboards/charts/{chart-type}`

**Use for**: Time-series line/bar charts.

**Available chart endpoints**:

| Endpoint | Metric (hardcoded) | Description |
|----------|-------------------|-------------|
| `GET /api/v1/dashboards/charts/sales-trend` | Revenue | Daily/weekly/monthly revenue trend |
| `GET /api/v1/dashboards/charts/cash-flow` | Net Cash Change | Daily/weekly/monthly cash flow |

**Query parameters**:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `date_from` | `YYYY-MM-DD` | none (all time) | Start date (inclusive) |
| `date_to` | `YYYY-MM-DD` | none (all time) | End date (inclusive) |
| `granularity` | `day` \| `week` \| `month` | `day` | Time bucketing |

```typescript
// Sales trend for January 2026, weekly
const res = await api.get("/api/v1/dashboards/charts/sales-trend", {
  params: {
    date_from: "2026-01-01",
    date_to: "2026-01-31",
    granularity: "week",
  },
});
```

**Response shape**:

```json
{
  "success": true,
  "data": {
    "tenant_id": "550e8400-...",
    "chart_type": "sales_trend",
    "granularity": "week",
    "data": [
      { "date": "2026-01-01", "value": 31250.00, "currency": "USD" },
      { "date": "2026-01-08", "value": 28900.50, "currency": "USD" },
      { "date": "2026-01-15", "value": 33100.00, "currency": "USD" },
      { "date": "2026-01-22", "value": 32180.00, "currency": "USD" }
    ],
    "currency": "USD"
  },
  "timestamp": "2026-02-07T14:00:00+00:00"
}
```

**Recharts example**:

```tsx
function SalesTrend({ dateFrom, dateTo, granularity }) {
  const { data } = useQuery(
    ["sales-trend", dateFrom, dateTo, granularity],
    () => api.get("/api/v1/dashboards/charts/sales-trend", {
      params: { date_from: dateFrom, date_to: dateTo, granularity },
    })
  );

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data?.data.data}>
        <XAxis dataKey="date" />
        <YAxis />
        <Tooltip formatter={(v) => `$${v.toLocaleString()}`} />
        <Line type="monotone" dataKey="value" stroke="#3b82f6" />
      </LineChart>
    </ResponsiveContainer>
  );
}
```

---

### 4.3 Ad-hoc Analysis — `POST /api/v1/reports/analyze`

**Use for**: Custom data tables, filtered reports, drill-down views.

This is the most flexible endpoint. You choose the view, metrics, and dimensions.
But **every value must be a valid enum**.

**Request body**:

```json
{
  "view": "sales_daily",
  "metrics": ["revenue", "transaction_count"],
  "dimensions": ["date", "currency"],
  "date_from": "2026-01-01",
  "date_to": "2026-01-31",
  "limit": 500
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `view` | ViewScope enum | ✅ | Must be one of the 3 views |
| `metrics` | ReportMetric[] | ✅ | 1–10 items, must belong to the chosen view |
| `dimensions` | ReportDimension[] | ❌ | 0–5 items, must belong to the chosen view |
| `date_from` | `YYYY-MM-DD` | ❌ | Inclusive start |
| `date_to` | `YYYY-MM-DD` | ❌ | Inclusive end |
| `limit` | integer | ❌ | 1–10,000 (default: 500) |

**Response shape**:

```json
{
  "success": true,
  "data": {
    "tenant_id": "550e8400-...",
    "view": "sales_daily",
    "row_count": 31,
    "rows": [
      { "transaction_date": "2026-01-01", "reporting_currency_code": "USD", "daily_revenue": 4150.00, "transaction_count": 12 },
      { "transaction_date": "2026-01-02", "reporting_currency_code": "USD", "daily_revenue": 3890.50, "transaction_count": 8 }
    ],
    "currency": "USD",
    "is_materialized": true
  },
  "timestamp": "2026-02-07T14:00:00+00:00"
}
```

> **Note**: `is_materialized: true` means the data may be slightly stale
> (materialized view is refreshed periodically). Consider showing a
> "Last refreshed: ..." indicator in the UI.

**Building a filter UI**:

```typescript
// TypeScript enum mirrors for type safety
const VIEW_OPTIONS = ["sales_daily", "receivables_summary", "cash_flow_daily"] as const;

const METRICS_BY_VIEW = {
  sales_daily:          ["revenue", "transaction_count"],
  receivables_summary:  ["outstanding_balance", "receivable_entry_count"],
  cash_flow_daily:      ["net_cash_change", "running_balance", "cash_transaction_count"],
} as const;

const DIMENSIONS_BY_VIEW = {
  sales_daily:          ["date", "currency"],
  receivables_summary:  ["entity_id", "entity_type", "currency"],
  cash_flow_daily:      ["date", "currency"],
} as const;

// When user selects a view, update the available metrics/dimensions
function onViewChange(view: string) {
  setAvailableMetrics(METRICS_BY_VIEW[view]);
  setAvailableDimensions(DIMENSIONS_BY_VIEW[view]);
}
```

**Or use the discovery endpoint** to get this dynamically:

```typescript
// GET /api/v1/reports/schema/{view_scope}
const schema = await api.get(`/api/v1/reports/schema/sales_daily`);
// schema.data.metrics = [{ key: "revenue", column: "daily_revenue" }, ...]
// schema.data.dimensions = [{ key: "date", column: "transaction_date" }, ...]
```

---

### 4.4 Schema Discovery — `GET /api/v1/reports/schema/{view_scope}`

**Use for**: Dynamically building filter/query forms.

Returns the available metrics and dimensions for a given view. Use this instead
of hardcoding the enum lists in the frontend (recommended for future-proofing).

```typescript
const res = await api.get("/api/v1/reports/schema/sales_daily");
```

**Response**:

```json
{
  "success": true,
  "data": {
    "view": "sales_daily",
    "is_materialized": true,
    "metrics": [
      { "key": "revenue", "column": "daily_revenue" },
      { "key": "transaction_count", "column": "transaction_count" }
    ],
    "dimensions": [
      { "key": "date", "column": "transaction_date" },
      { "key": "currency", "column": "reporting_currency_code" }
    ],
    "currency": "USD"
  }
}
```

---

## 5. The Export Flow (Async)

Exports allow downloading large datasets as CSV or XLSX files. Because exports
can take time (large data, file generation), they run **asynchronously** via a
background job queue.

### 5.1 Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                        FRONTEND                                  │
│                                                                  │
│  1. User clicks "Export"                                         │
│     │                                                            │
│     ▼                                                            │
│  POST /api/v1/exports                                            │
│  Body: { view, metrics, dimensions, date_from, date_to, format } │
│     │                                                            │
│     ▼                                                            │
│  ← 202 Accepted  { job_id: "abc-123", status: "pending" }       │
│     │                                                            │
│     ▼                                                            │
│  2. Show spinner / toast: "Export in progress..."                 │
│     │                                                            │
│     ▼  (poll every 2–5 seconds)                                  │
│  GET /api/v1/exports/abc-123                                     │
│     │                                                            │
│     ├── status: "pending"  → keep polling                        │
│     ├── status: "running"  → keep polling, maybe show progress   │
│     ├── status: "failed"   → show error toast, stop polling      │
│     │                                                            │
│     └── status: "completed"                                      │
│         download_url: "/api/v1/exports/abc-123/download"         │
│         row_count: 15000                                         │
│         file_size_bytes: 524288                                   │
│         │                                                        │
│         ▼                                                        │
│  3. Show "Download Ready" button                                 │
│     │                                                            │
│     ▼                                                            │
│  GET /api/v1/exports/abc-123/download                            │
│     │                                                            │
│     ▼                                                            │
│  ← File download (CSV or XLSX)                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 Step 1: Create Export

```typescript
const res = await api.post("/api/v1/exports", {
  view: "sales_daily",
  metrics: ["revenue", "transaction_count"],
  dimensions: ["date", "currency"],
  date_from: "2026-01-01",
  date_to: "2026-06-30",
  format: "csv",       // or "xlsx"
  limit: 50000,        // max 500,000
});

// res.status === 202
const jobId = res.data.data.job_id;
// → "550e8400-e29b-41d4-a716-446655440000"
```

### 5.3 Step 2: Poll Status

```typescript
async function pollExportStatus(jobId: string): Promise<ExportStatus> {
  const POLL_INTERVAL_MS = 3000;  // 3 seconds
  const MAX_POLLS = 100;          // 5 minutes max

  for (let i = 0; i < MAX_POLLS; i++) {
    const res = await api.get(`/api/v1/exports/${jobId}`);
    const status = res.data.data;

    switch (status.status) {
      case "completed":
        return status;  // has download_url, row_count, file_size_bytes

      case "failed":
        throw new Error(status.error || "Export failed");

      case "pending":
      case "running":
        await sleep(POLL_INTERVAL_MS);
        break;
    }
  }
  throw new Error("Export timed out");
}
```

### 5.4 Step 3: Download File

```typescript
function downloadExport(jobId: string, format: string) {
  // Use window.open or anchor tag for file download
  const url = `/api/v1/exports/${jobId}/download`;

  const a = document.createElement("a");
  a.href = url;
  a.download = `export.${format}`;
  // Note: if auth is required, use fetch + blob instead:
  fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    .then(res => res.blob())
    .then(blob => {
      const blobUrl = URL.createObjectURL(blob);
      a.href = blobUrl;
      a.click();
      URL.revokeObjectURL(blobUrl);
    });
}
```

### 5.5 UI State Machine

```typescript
type ExportState =
  | { phase: "idle" }
  | { phase: "submitting" }
  | { phase: "polling"; jobId: string }
  | { phase: "ready"; jobId: string; rowCount: number; fileSize: number }
  | { phase: "error"; message: string };

// Recommended UI for each state:
// idle       → "Export" button enabled
// submitting → "Export" button disabled + spinner
// polling    → Toast: "Generating export..." with spinner
// ready      → Toast: "Export ready! 15,000 rows (512 KB)" + Download button
// error      → Toast: "Export failed: {message}" with retry button
```

### 5.6 Export Request Constraints

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `view` | ViewScope enum | ✅ | Same 3 views as analyze |
| `metrics` | ReportMetric[] | ✅ | 1–10 items, must belong to view |
| `dimensions` | ReportDimension[] | ❌ | 0–5 items |
| `date_from` | `YYYY-MM-DD` | ❌ | Inclusive start |
| `date_to` | `YYYY-MM-DD` | ❌ | Inclusive end |
| `format` | `"csv"` \| `"xlsx"` | ❌ | Default: `"csv"` |
| `limit` | integer | ❌ | 1–500,000 (default: 50,000) |

---

## 6. Error Handling Reference

### 6.1 HTTP Status Codes

| Code | Meaning | Frontend Action |
|------|---------|-----------------|
| **200** | Success | Read `response.data` |
| **202** | Export job accepted | Start polling with `job_id` |
| **401** | Unauthorized (missing/invalid JWT) | Redirect to login |
| **403** | Forbidden (tenant mismatch) | Show "Access denied" — user may be trying to access another tenant's data |
| **404** | Resource not found | Show "Not found" (e.g., export job doesn't exist or belongs to another tenant) |
| **409** | Conflict (export not ready) | Export is still running — keep polling |
| **422** | Unprocessable Entity | **Invalid enum value** — check your request payload |
| **500** | Internal Server Error | Show generic error, log for debugging |

### 6.2 Common 422 Errors and How to Fix Them

#### Invalid View

```json
// You sent: { "view": "users_table" }
// Response:
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Input should be 'sales_daily', 'receivables_summary' or 'cash_flow_daily'"
  }
}
```

**Fix**: Use one of the 3 valid ViewScope values.

#### Invalid Metric

```json
// You sent: { "metrics": ["daily_revenue"] }  ← raw column name!
// Response:
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Input should be 'revenue', 'transaction_count', 'outstanding_balance', ..."
  }
}
```

**Fix**: Use the business-semantic enum value (`"revenue"`), not the database
column name (`"daily_revenue"`).

#### Metric Not Available on View

```json
// You sent: { "view": "receivables_summary", "metrics": ["revenue"] }
// Response:
{
  "success": false,
  "error": {
    "code": "METRIC_NOT_AVAILABLE",
    "message": "Metric 'revenue' is not available on view 'receivables_summary'",
    "available_values": ["outstanding_balance", "receivable_entry_count"]
  }
}
```

**Fix**: Use a metric that belongs to the chosen view. Check the
`available_values` array in the error response, or call the schema
discovery endpoint first.

#### Dimension Not Available on View

```json
// You sent: { "view": "sales_daily", "dimensions": ["entity_id"] }
// Response:
{
  "success": false,
  "error": {
    "code": "DIMENSION_NOT_AVAILABLE",
    "message": "Dimension 'entity_id' is not available on view 'sales_daily'",
    "available_values": ["date", "currency"]
  }
}
```

**Fix**: Use a dimension that belongs to the chosen view.

### 6.3 The 403 Forbidden Case

A 403 means the backend detected a tenant mismatch. This should **never happen**
in normal usage because the tenant is derived from the JWT. If you see this:

1. The user's JWT may have expired — refresh the token
2. The user may be trying to access an export created by a different tenant
3. There may be a bug in token handling — check the `Authorization` header

### 6.4 Defensive Frontend Pattern

```typescript
async function safeApiCall<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (err) {
    if (err.response?.status === 401) {
      // Token expired → redirect to login
      router.push("/login");
    } else if (err.response?.status === 422) {
      // Invalid enum → show the available values
      const available = err.response.data?.error?.available_values;
      if (available) {
        showToast(`Valid options: ${available.join(", ")}`, "warning");
      } else {
        showToast(err.response.data?.error?.message, "error");
      }
    } else if (err.response?.status === 403) {
      showToast("Access denied. Please re-login.", "error");
    } else {
      showToast("Something went wrong. Please try again.", "error");
    }
    throw err;
  }
}
```

---

## 7. Complete Endpoint Reference

| Method | Path | Tier | Parameters | Response |
|--------|------|------|-----------|----------|
| `GET` | `/api/v1/dashboards/kpi/summary` | 1 (KPI) | None | `KpiSummaryData` |
| `GET` | `/api/v1/dashboards/charts/sales-trend` | 2 (Chart) | `date_from`, `date_to`, `granularity` | `ChartData` |
| `GET` | `/api/v1/dashboards/charts/cash-flow` | 2 (Chart) | `date_from`, `date_to`, `granularity` | `ChartData` |
| `POST` | `/api/v1/reports/analyze` | 3 (Ad-hoc) | JSON body: `SemanticQueryRequest` | `AnalyzeData` |
| `GET` | `/api/v1/reports/schema/{view_scope}` | Meta | Path param: ViewScope | `ViewSchemaData` |
| `POST` | `/api/v1/exports` | Export | JSON body: `ExportRequest` | 202 + `ExportStatusData` |
| `GET` | `/api/v1/exports/{job_id}` | Export | Path param | `ExportStatusData` |
| `GET` | `/api/v1/exports/{job_id}/download` | Export | Path param | File (CSV/XLSX) |

---

## 8. TypeScript Type Definitions

Copy these into your frontend codebase for type safety:

```typescript
// ============================================================
// Enum mirrors (must match backend exactly)
// ============================================================

type ViewScope = "sales_daily" | "receivables_summary" | "cash_flow_daily";

type ReportMetric =
  | "revenue"
  | "transaction_count"
  | "outstanding_balance"
  | "receivable_entry_count"
  | "net_cash_change"
  | "running_balance"
  | "cash_transaction_count";

type ReportDimension = "date" | "currency" | "entity_id" | "entity_type";

type TimeGranularity = "day" | "week" | "month";

type ExportFormat = "csv" | "xlsx";

// ============================================================
// Request types
// ============================================================

interface AnalyzeRequest {
  view: ViewScope;
  metrics: ReportMetric[];
  dimensions?: ReportDimension[];
  date_from?: string;  // YYYY-MM-DD
  date_to?: string;    // YYYY-MM-DD
  limit?: number;      // 1–10,000
}

interface ExportRequest {
  view: ViewScope;
  metrics: ReportMetric[];
  dimensions?: ReportDimension[];
  date_from?: string;
  date_to?: string;
  format?: ExportFormat;
  limit?: number;      // 1–500,000
}

// ============================================================
// Response types
// ============================================================

interface ApiResponse<T> {
  success: boolean;
  data: T;
  message?: string;
  timestamp: string;
}

interface ApiError {
  success: false;
  error: {
    code: string;
    message: string;
    details?: Array<{ field?: string; message: string }>;
    available_values?: string[];
  };
  timestamp: string;
}

interface KpiCard {
  label: string;
  value: number;
  currency: string;
  trend: "up" | "down" | "flat" | null;
}

interface KpiSummaryData {
  tenant_id: string;
  generated_at: string;
  cards: KpiCard[];
  currency: string;
}

interface ChartDataPoint {
  date: string;
  value: number;
  currency: string;
}

interface ChartData {
  tenant_id: string;
  chart_type: string;
  granularity: string;
  data: ChartDataPoint[];
  currency: string;
}

interface AnalyzeData {
  tenant_id: string;
  view: string;
  row_count: number;
  rows: Record<string, any>[];
  currency: string;
  is_materialized: boolean;
}

interface ExportStatusData {
  job_id: string;
  status: "pending" | "running" | "completed" | "failed";
  format: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  download_url?: string;
  row_count?: number;
  file_size_bytes?: number;
  error?: string;
}

interface ViewSchemaData {
  view: string;
  is_materialized: boolean;
  metrics: Array<{ key: string; column: string }>;
  dimensions: Array<{ key: string; column: string }>;
  currency: string;
}
```

---

## 9. Quick-Start Checklist

- [ ] Copy TypeScript types from §8 into your project
- [ ] Implement the `safeApiCall` error handler from §6.4
- [ ] Build KPI cards using `GET /kpi/summary` (§4.1)
- [ ] Build sales trend chart using `GET /charts/sales-trend` (§4.2)
- [ ] Build cash flow chart using `GET /charts/cash-flow` (§4.2)
- [ ] Build the ad-hoc analysis table using `POST /reports/analyze` (§4.3)
- [ ] Use schema discovery `GET /reports/schema/{view}` for dynamic filter forms (§4.4)
- [ ] Implement the async export flow with polling (§5)
- [ ] Handle 422 errors by showing `available_values` to the user (§6.2)
- [ ] Show `is_materialized` indicator when data may be stale

---

**Document Status**: ✅ COMPLETE — Final artifact for Phase 6
**Last Updated**: 2026-02-07
