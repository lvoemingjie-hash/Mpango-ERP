# S6-4: Async Export Engine — Ops Ledger

**Track**: S6-4 (Async Export Engine)
**Date**: 2026-02-07
**Status**: ✅ COMPLETE
**Author**: Backend AI
**Depends On**: S6-3 (Dashboard API) — ✅ COMPLETE, S4 (Job Queue) — ✅ COMPLETE

---

## 1. Objective

Implement async file exports (CSV/XLSX) where users can download large datasets
without blocking the API. The export worker reuses `SemanticQueryBuilder` directly
— no SQL is rewritten.

### Key Design Decisions

1. **Reuse S6-3 Logic** — Export worker calls `SemanticQueryBuilder.build_query()` + `execute()`
2. **Context Propagation** — `tenant_id` is serialized from HTTP context into the Job Payload
3. **Memory Safety** — `fetchmany(1000)` streaming, never full result set in RAM
4. **Defense in Depth** — Worker re-validates tenant_id and enums from string values

---

## 2. Architecture: Context Propagation Chain

```
Frontend (authenticated)
    │
    ▼
POST /api/v1/exports (HTTP context, JWT)
    │
    ├── Extract tenant_id from request.state (JWT claims)
    ├── Validate enums via Pydantic (ExportRequest)
    ├── Build ExportJobPayload.from_request(request, tenant_id, tenant_schema, user_id)
    ├── Enqueue "export_report" job via S4 Job Queue
    └── Return 202 Accepted with job_id
    │
    ▼
S4 Job Queue (detached worker)
    │
    ├── Deserialize ExportJobPayload(**payload_dict)
    ├── Re-validate tenant_id (MUST NOT be empty)
    ├── Re-validate ViewScope, ReportMetric, ReportDimension from strings
    ├── Construct SemanticQueryBuilder(session, tenant_id, tenant_schema, view_scope)
    ├── builder.build_query(metrics, dimensions, date_from, date_to, limit)
    ├── builder._ensure_tenant_scope()  →  SET LOCAL search_path
    ├── Stream rows via fetchmany(1000) → write CSV/XLSX
    └── Write metadata sidecar (.meta.json)
    │
    ▼
GET /api/v1/exports/{job_id} (poll status)
    │
    ├── Read sys_jobs table for status
    ├── Verify tenant ownership (payload.tenant_id == request tenant_id)
    └── Return download_url when completed
    │
    ▼
GET /api/v1/exports/{job_id}/download (serve file)
    │
    ├── Verify tenant ownership
    ├── Read file path from metadata sidecar
    └── Return FileResponse
```

---

## 3. Constraint Compliance

| Rule | Constraint | Enforcement Point | Status |
|------|-----------|-------------------|--------|
| **#1** | `tenant_id` from trusted context only | `_extract_tenant()` reads `request.state` | ✅ |
| **#1** | `tenant_id` survives HTTP → Worker hop | `ExportJobPayload.from_request()` serializes it | ✅ |
| **#1** | Worker rejects empty `tenant_id` | `ExportJobPayload.tenant_id_must_not_be_empty` validator | ✅ |
| **#1** | `SET LOCAL search_path` before query | `SemanticQueryBuilder._ensure_tenant_scope()` | ✅ |
| **#1** | Download verifies tenant ownership | Status + download endpoints check `payload.tenant_id` | ✅ |
| **#3** | Target tables `rpt_*`/`mv_*` only | Worker re-validates `ViewScope` enum | ✅ |
| **#4** | All inputs whitelisted Enums | `ExportRequest` Pydantic + worker re-validation | ✅ |

---

## 4. Memory Safety

| Concern | Solution |
|---------|----------|
| Full result set in RAM | `fetchmany(1000)` streaming batches |
| Large XLSX in memory | `openpyxl write_only=True` mode |
| Unbounded row count | `MAX_EXPORT_ROWS = 500,000` hard cap |
| File accumulation | Metadata sidecar enables future cleanup job |

---

## 5. API Endpoints

| Method | Path | Parameters | Response |
|--------|------|-----------|----------|
| `POST` | `/api/v1/exports` | `ExportRequest` body | 202 + `ExportStatusData` |
| `GET` | `/api/v1/exports/{job_id}` | Path param | `ExportStatusData` |
| `GET` | `/api/v1/exports/{job_id}/download` | Path param | `FileResponse` (CSV/XLSX) |

### Example: Create Export

```json
POST /api/v1/exports
{
    "view": "sales_daily",
    "metrics": ["revenue", "transaction_count"],
    "dimensions": ["date", "currency"],
    "date_from": "2026-01-01",
    "date_to": "2026-01-31",
    "format": "csv",
    "limit": 50000
}
```

### Response (202 Accepted)

```json
{
    "success": true,
    "data": {
        "job_id": "550e8400-...",
        "status": "pending",
        "format": "csv",
        "created_at": "2026-02-07T14:00:00+00:00"
    },
    "timestamp": "2026-02-07T14:00:00+00:00"
}
```

### Poll Status (completed)

```json
{
    "success": true,
    "data": {
        "job_id": "550e8400-...",
        "status": "completed",
        "format": "csv",
        "download_url": "/api/v1/exports/550e8400-.../download",
        "row_count": 31,
        "file_size_bytes": 2048
    },
    "timestamp": "2026-02-07T14:00:05+00:00"
}
```

---

## 6. Test Results (33/33 Passed)

### ExportJobPayload Validation (6)

```
✅ test_valid_payload_creates_successfully
✅ test_empty_tenant_id_rejected
✅ test_whitespace_tenant_id_rejected
✅ test_invalid_tenant_schema_prefix_rejected
✅ test_from_request_factory
✅ test_payload_is_json_serializable
```

### ExportRequest Pydantic Validation (7)

```
✅ test_valid_request_parses
✅ test_invalid_view_rejected
✅ test_invalid_metric_rejected
✅ test_invalid_format_rejected
✅ test_empty_metrics_rejected
✅ test_limit_bounds
✅ test_xlsx_format_accepted
```

### Export Worker (3)

```
✅ test_worker_rejects_empty_tenant_id
✅ test_worker_rejects_invalid_view
✅ test_worker_rejects_invalid_metric
```

### CSV Streaming (3)

```
✅ test_csv_writer_produces_valid_file
✅ test_csv_writer_handles_empty_result
✅ test_csv_writer_streams_in_batches
```

### Metadata Sidecar (2)

```
✅ test_write_and_read_metadata
✅ test_read_nonexistent_metadata_returns_none
```

### Context Propagation Chain (2)

```
✅ test_full_chain_preserves_tenant_id
✅ test_chain_rejects_tampered_tenant_id
```

### Response Schema (3)

```
✅ test_pending_status
✅ test_completed_status_with_metadata
✅ test_failed_status_with_error
```

### Value Serialization (7)

```
✅ test_serialize_decimal
✅ test_serialize_date
✅ test_serialize_datetime
✅ test_serialize_none
✅ test_serialize_uuid
✅ test_serialize_string_passthrough
✅ test_serialize_int_passthrough
```

### Regression Tests (S6-3: 27/27 still passing)

```
✅ All 27 S6-3 tests pass with no regressions
```

---

## 7. Files Changed

| File | Purpose |
|------|---------|
| `backend/api/schemas/jobs.py` | ExportRequest, ExportJobPayload, ExportStatusData schemas |
| `backend/jobs/export_jobs.py` | Export worker: streaming CSV/XLSX generation |
| `backend/api/v1/exports.py` | Export API router: POST, GET status, GET download |
| `backend/api/app.py` | Router registration (exports_router) |
| `backend/main.py` | Job handler registration + `get_job_queue()` accessor |
| `backend/tests/test_s6_4_async_exports.py` | 33 tests |
| `ai-ledger/backend/s6-4_async_exports.md` | This document |

---

## 8. Security Notes

### Violation Prevention

| Threat | Prevention |
|--------|-----------|
| Worker runs without tenant_id | `ExportJobPayload` validator rejects empty string |
| Worker queries wrong schema | `SET LOCAL search_path` enforced by `SemanticQueryBuilder` |
| User downloads another tenant's export | Status + download endpoints verify `payload.tenant_id` |
| Frontend sends raw column names | `ExportRequest` Pydantic rejects non-enum values |
| Worker receives tampered enums | Worker re-validates `ViewScope`, `ReportMetric`, `ReportDimension` |

### File Storage

Currently writes to `backend/exports/` on local disk. For production:
- Replace with S3/GCS object store
- Add signed URL generation for downloads
- Add TTL-based cleanup job for expired exports

---

**Document Status**: ✅ COMPLETE
**Last Updated**: 2026-02-07
