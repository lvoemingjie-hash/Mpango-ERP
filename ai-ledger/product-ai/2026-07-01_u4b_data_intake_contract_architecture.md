# U4-B Data Intake Contract and Architecture

**Date**: 2026-07-01
**Branch**: `opencode/u4b-data-intake-contract-architecture-2026-07-01`
**Executor**: OpenCode GPT-5.5
**Verdict**: `PASS_FOR_CTO_U4B_REVIEW`
**Change Type**: `DESIGN_ONLY_NO_RUNTIME_CHANGE`

## 1. Executive Summary

U4 Data Intake is a staging-first customer onboarding surface for catalog data. It accepts CSV/XLSX-first product rows, supports review and cleanup before ERP import, and later bridges into the existing U3 internal SKU import preview/validate/apply pipeline.

U4-B is contract and architecture only. It does not add migrations, runtime code, UI, storage, parser implementation, or deployment changes.

Design principle:

```text
Data Intake stages and reviews customer-provided product data.
ERP SKU Import applies validated SKU rows into ERP.
No U4 endpoint silently writes SKUs directly.
```

## 2. Existing U3 Boundary

U3 is closed as `INTERNAL_SKU_IMPORT_FOUNDATION`.

Existing U3 import contract:

- `POST /api/v1/skus/import/preview`: accepts CSV, creates `import_runs`, returns `import_id`, no SKU writes.
- `POST /api/v1/skus/import/{import_id}/validate`: accepts mapping, returns row-level errors/warnings, no SKU writes.
- `POST /api/v1/skus/import/{import_id}/apply`: applies validated rows into `skus`, gated by `skus:import`.
- Permission: all U3 import endpoints require `skus:import`.
- Storage model: tenant-scoped `import_runs` tracks preview/validate/apply status and JSON snapshots.

U4 must treat U3 as an internal ERP import target, not as the customer-facing intake workspace.

## 3. MVP Bounded Context

### 3.1 ERP Internal SKU Import

Lives in existing U3 code and tables.

Responsibilities:

- Convert a known SKU import CSV into ERP SKUs.
- Validate ERP SKU rules: required `sku_code`, required `name`, unit, duplicate `sku_code`, allowed conflict policy.
- Track import execution using `import_runs`.
- Require `skus:import` for preview/validate/apply.
- Remain the only path that writes final SKU records for U4 MVP handoff.

Non-responsibilities:

- Customer collaboration workspace.
- XLSX parsing.
- Image/barcode/mobile capture.
- Long-running row review workflow.
- Public invite token access.

### 3.2 Data Intake Staging

New U4 bounded context. It should live in the monorepo but be logically external to ERP import.

Responsibilities:

- Create tenant-owned intake workspaces.
- Accept CSV/XLSX uploads.
- Parse and normalize headers.
- Preserve row numbers and source cell values.
- Store staged product rows before ERP import.
- Store validation issues as blocking errors or warnings.
- Support row review, mapping save, validation rerun, and export.
- Generate a SKU import CSV compatible with U3.
- Explicitly push generated CSV to U3 preview only when authorized.
- Support a future mobile scan/photo intake path without committing U4-B to full PWA/offline behavior.

### 3.3 Explicitly Out Of Scope For U4-B

- Database migrations.
- Runtime parser implementation.
- Frontend implementation.
- Direct SKU creation from intake rows.
- Applying U3 imports from U4 without a second explicit action.
- Background job execution.
- Object storage integration.
- Offline sync.
- Full barcode catalog lookup.
- OCR.
- Automatic SKU deduplication across tenants.
- Translation implementation.
- Any code copied from ODK, DHIS2, ChT, InvenTree, Odoo, ERPNext, or other reference systems.

## 4. Proposed Backend Data Contract

All tables are tenant-scoped unless explicitly stated otherwise. Table names below are proposed; U4-B does not create them.

Shared conventions:

- `id`: UUID primary key, server-generated.
- `tenant_id`: UUID, required, must match auth tenant context.
- `workspace_id`: UUID, required for all workspace-owned records.
- `created_at`, `updated_at`: timestamptz, required.
- `is_deleted`, `deleted_at`: soft-delete fields, default false/null.
- Tenant isolation: every query must filter by tenant schema through the existing tenant DB session and by `workspace_id` where applicable.
- Public token access never bypasses tenant/workspace filters; token resolves to exactly one workspace and scoped capabilities.

### 4.1 `intake_workspaces`

Purpose: customer onboarding container and collaboration boundary.

Fields:

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `id` | uuid | yes | Workspace ID. |
| `tenant_id` | uuid | yes | Owning wholesaler tenant. |
| `name` | varchar(160) | yes | Human label, unique per tenant only if requested later. |
| `description` | text | no | Internal notes. |
| `source_type` | varchar(32) | yes | `CUSTOMER_ONBOARDING`, `CATALOG_REFRESH`, `STOCK_INTAKE`, `MOBILE_SCAN`. |
| `status` | varchar(32) | yes | See lifecycle below. |
| `public_token_hash` | varchar(128) | no | Hash only; never store raw token. |
| `public_token_expires_at` | timestamptz | no | Required if public token is enabled. |
| `public_access_enabled` | boolean | yes | Default false. |
| `created_by` | uuid | no | Internal user. |
| `updated_by` | uuid | no | Internal user. |
| `approved_by` | uuid | no | Internal approver. |
| `approved_at` | timestamptz | no | Approval timestamp. |
| `metadata` | jsonb | no | Customer code, campaign, source tags. |

Status enum:

```text
DRAFT
OPEN
UPLOADED
MAPPED
VALIDATING
NEEDS_REVIEW
READY_FOR_EXPORT
EXPORTED
PUSHED_TO_ERP_PREVIEW
CLOSED
CANCELLED
```

Status rules:

- `DRAFT -> OPEN`: workspace created and ready.
- `OPEN -> UPLOADED`: at least one upload accepted.
- `UPLOADED -> MAPPED`: mapping saved.
- `MAPPED -> VALIDATING -> NEEDS_REVIEW | READY_FOR_EXPORT`.
- `READY_FOR_EXPORT -> EXPORTED`: generated SKU import CSV exists.
- `EXPORTED -> PUSHED_TO_ERP_PREVIEW`: U4 explicitly created a U3 preview import.
- `CLOSED` and `CANCELLED` are terminal for mutation, except audit reads.

### 4.2 `intake_uploads`

Purpose: source file metadata and parser outcome.

Fields:

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `id` | uuid | yes | Upload ID. |
| `tenant_id` | uuid | yes | Owning tenant. |
| `workspace_id` | uuid | yes | FK to intake workspace. |
| `filename` | varchar(255) | yes | Original filename, sanitized for display. |
| `content_type` | varchar(128) | no | Browser-provided content type, not trusted. |
| `file_ext` | varchar(16) | yes | `csv`, `xlsx`. |
| `file_size_bytes` | integer | yes | Enforced against limits. |
| `sha256` | char(64) | yes | Duplicate detection and audit. |
| `storage_key` | varchar(512) | no | Future object storage pointer. U4-C may be null if storing bytes elsewhere is deferred. |
| `status` | varchar(32) | yes | Upload parser lifecycle. |
| `row_count` | integer | yes | Data rows, excluding header. |
| `column_count` | integer | yes | Parsed columns. |
| `headers_raw` | jsonb | yes | Source header strings in original order. |
| `headers_normalized` | jsonb | yes | Normalized header map. |
| `parse_summary` | jsonb | no | Counts and parser decisions. |
| `created_by` | uuid | no | Internal user or null for public token. |

Status enum:

```text
RECEIVED
PARSING
PARSED
PARSE_FAILED
SUPERSEDED
DELETED
```

Rules:

- A workspace may have multiple uploads.
- A later upload can supersede earlier staged rows only by explicit action.
- Raw files are immutable after upload.

### 4.3 `intake_product_rows`

Purpose: normalized staged product rows with source provenance.

Fields:

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `id` | uuid | yes | Row ID. |
| `tenant_id` | uuid | yes | Owning tenant. |
| `workspace_id` | uuid | yes | Workspace owner. |
| `upload_id` | uuid | yes | Source upload. |
| `source_row_number` | integer | yes | 1-based spreadsheet row number, preserving original row. |
| `row_index` | integer | yes | 0-based parsed data row index for UI sorting. |
| `raw_values` | jsonb | yes | Source header -> original cell value. |
| `normalized_values` | jsonb | yes | Target field -> normalized value. |
| `mapping_version` | integer | yes | Increment when mapping changes. |
| `sku_code` | varchar(64) | no | Staged value after mapping. |
| `name` | varchar(255) | no | Staged value after mapping. |
| `unit` | varchar(32) | no | Staged value. |
| `category` | varchar(64) | no | Staged value. |
| `unit_price` | numeric(12,2) | no | Optional for SKU import bridge unless ERP requires later. |
| `barcode` | varchar(128) | no | Manual or scanned barcode. |
| `image_asset_id` | uuid | no | Optional FK to minimal asset. |
| `review_status` | varchar(32) | yes | Row review lifecycle. |
| `dedupe_key` | varchar(160) | no | Suggested stable key, not globally unique. |
| `created_by` | uuid | no | Internal or public actor. |
| `updated_by` | uuid | no | Internal or public actor. |

Review status enum:

```text
UNREVIEWED
NEEDS_FIX
FIXED
APPROVED
EXCLUDED
EXPORTED
```

Rules:

- Row order is stable by `(upload_id, row_index)`.
- `source_row_number` must never be recomputed after parse.
- `raw_values` are immutable except for redaction tooling approved later.
- `normalized_values` may change after mapping or manual row review.
- `EXCLUDED` rows are never exported to U3.

### 4.4 `intake_validation_issues`

Purpose: row-level and file-level validation results.

Fields:

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `id` | uuid | yes | Issue ID. |
| `tenant_id` | uuid | yes | Owning tenant. |
| `workspace_id` | uuid | yes | Workspace owner. |
| `upload_id` | uuid | no | Source upload if file-specific. |
| `row_id` | uuid | no | Null for file-level issues. |
| `source_row_number` | integer | no | Duplicate of row source number for stable reports. |
| `severity` | varchar(16) | yes | `ERROR`, `WARNING`, `INFO`. |
| `code` | varchar(64) | yes | Machine-readable issue code. |
| `field` | varchar(128) | no | Target field name if field-specific. |
| `source_header` | varchar(255) | no | Original header when relevant. |
| `message` | text | yes | Human-readable English-first message. |
| `is_blocking` | boolean | yes | True for export blockers. |
| `resolved_at` | timestamptz | no | Null until fixed or ignored. |
| `resolved_by` | uuid | no | Internal user. |

Blocking issue examples:

- Missing required `sku_code` or `name`.
- Duplicate staged `sku_code` inside workspace.
- Duplicate ERP `sku_code` when conflict policy is `fail`.
- XLSX file cannot be parsed.
- Row exceeds field length constraints.

Warning examples:

- Unknown column left unmapped.
- Missing optional `unit` defaulted to `unit`.
- Price has more than two decimals and was rounded only after explicit confirmation.
- Barcode present but not validated against any external catalog.

### 4.5 `intake_assets`

Purpose: minimal metadata for optional image/photo attachment.

Fields:

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `id` | uuid | yes | Asset ID. |
| `tenant_id` | uuid | yes | Owning tenant. |
| `workspace_id` | uuid | yes | Workspace owner. |
| `row_id` | uuid | no | Optional row link. |
| `asset_type` | varchar(32) | yes | `PRODUCT_PHOTO`, `BARCODE_PHOTO`, `SOURCE_FILE`, `OTHER`. |
| `filename` | varchar(255) | no | Sanitized original name. |
| `content_type` | varchar(128) | no | Validated server-side, not trusted from client. |
| `file_size_bytes` | integer | yes | Enforced limit. |
| `sha256` | char(64) | yes | Integrity and duplicate signal. |
| `storage_key` | varchar(512) | yes | Object store key or local dev storage key. |
| `status` | varchar(32) | yes | `UPLOADED`, `LINKED`, `REJECTED`, `DELETED`. |
| `created_by` | uuid | no | Internal or public actor. |

MVP rule:

- U4-B only defines the asset contract. U4-C/U4-D may stub asset upload metadata but must not promise production image storage until storage policy is approved.

### 4.6 `intake_exports`

Purpose: generated outputs and bridge references into U3.

Fields:

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `id` | uuid | yes | Export ID. |
| `tenant_id` | uuid | yes | Owning tenant. |
| `workspace_id` | uuid | yes | Workspace owner. |
| `export_type` | varchar(32) | yes | `SKU_IMPORT_CSV`, `ISSUE_REPORT_CSV`, `REVIEW_XLSX`. |
| `status` | varchar(32) | yes | Export lifecycle. |
| `row_count` | integer | yes | Rows included. |
| `storage_key` | varchar(512) | no | Export file pointer. |
| `sha256` | char(64) | no | Export file hash. |
| `u3_import_id` | varchar(64) | no | Set only after push to U3 preview succeeds. |
| `generated_by` | uuid | no | Internal user. |
| `generated_at` | timestamptz | yes | Timestamp. |

Status enum:

```text
GENERATING
READY
FAILED
PUSHED_TO_ERP_PREVIEW
SUPERSEDED
```

Rules:

- Export generation never applies SKU rows.
- `u3_import_id` is set only after explicit `push-to-sku-import-preview` call.
- Generated CSV must match U3 expected headers and values.

## 5. Proposed API Contract

Base path proposal:

```text
/api/v1/intake
```

Response envelope should follow existing API convention (`success`, `data`, `timestamp`) unless a later API-wide contract changes it.

Common errors:

| HTTP | Code | Meaning |
|---:|---|---|
| 400 | `INVALID_INPUT` | Malformed request or unsupported value. |
| 401 | `UNAUTHENTICATED` | Missing/invalid auth. |
| 403 | `PERMISSION_DENIED` | Authenticated but missing permission. |
| 404 | `WORKSPACE_NOT_FOUND` | Workspace not visible to caller. |
| 409 | `INVALID_WORKSPACE_STATE` | Operation not allowed in current status. |
| 413 | `FILE_TOO_LARGE` | Upload exceeds limit. |
| 422 | `VALIDATION_FAILED` | Contract-level validation failed. |

### 5.1 Workspace Create

```text
POST /api/v1/intake/workspaces
Permission: intake:create
```

Request:

```json
{
  "name": "Acme onboarding catalog",
  "description": "Initial customer product list",
  "source_type": "CUSTOMER_ONBOARDING",
  "public_access_enabled": false,
  "public_token_expires_at": null,
  "metadata": {"customer_code": "ACME"}
}
```

Response data:

```json
{
  "workspace_id": "uuid",
  "status": "OPEN",
  "name": "Acme onboarding catalog",
  "source_type": "CUSTOMER_ONBOARDING",
  "created_at": "2026-07-01T00:00:00Z"
}
```

### 5.2 Workspace Read/List

```text
GET /api/v1/intake/workspaces?page=1&page_size=20&status=OPEN
Permission: intake:read

GET /api/v1/intake/workspaces/{workspace_id}
Permission: intake:read
```

List response must be paginated. Detail response includes upload counts, row counts, issue counts, latest export, and current status.

### 5.3 Public Token Summary

```text
GET /api/v1/intake/public/{token}/summary
Permission: public token only, no bearer token required
```

Rules:

- Token must be opaque, random, time-limited, and stored only as a hash.
- Token resolves to exactly one tenant/workspace.
- Summary response must not expose internal user IDs, tenant internals, SKU import IDs, or other workspaces.
- Public token can read summary and submit uploads only if workspace status permits it.

Response data:

```json
{
  "workspace_id": "uuid",
  "workspace_name": "Acme onboarding catalog",
  "status": "OPEN",
  "allowed_file_types": ["csv", "xlsx"],
  "max_file_size_bytes": 10485760,
  "max_rows": 5000,
  "required_fields": ["sku_code", "name"],
  "optional_fields": ["unit", "category", "unit_price", "barcode", "image"]
}
```

### 5.4 Upload CSV/XLSX

```text
POST /api/v1/intake/workspaces/{workspace_id}/uploads
Permission: intake:create or valid public token with upload capability
Content-Type: multipart/form-data
```

Form fields:

- `file`: required CSV/XLSX.
- `source_label`: optional short label.
- `replace_existing`: optional boolean, default false.

Response data:

```json
{
  "upload_id": "uuid",
  "workspace_id": "uuid",
  "status": "PARSED",
  "filename": "products.xlsx",
  "row_count": 128,
  "column_count": 9,
  "headers_raw": ["Item Code", "Description", "Unit"],
  "headers_normalized": ["item_code", "description", "unit"],
  "sample_rows": [
    {"source_row_number": 2, "raw_values": {"Item Code": "A-001"}}
  ]
}
```

### 5.5 Mapping Save

```text
PUT /api/v1/intake/workspaces/{workspace_id}/mapping
Permission: intake:update
```

Request:

```json
{
  "upload_id": "uuid",
  "mapping": {
    "Item Code": "sku_code",
    "Description": "name",
    "Unit": "unit",
    "Barcode": "barcode"
  },
  "defaults": {
    "unit": "unit"
  }
}
```

Rules:

- Mapping keys are source headers.
- Mapping values are allowed intake target fields.
- Unknown/unmapped columns may be stored in `normalized_values.custom_attributes` later, but U4 MVP should not forward them to U3 unless explicitly mapped to an ERP field.

### 5.6 Validate

```text
POST /api/v1/intake/workspaces/{workspace_id}/validate
Permission: intake:update
```

Request:

```json
{
  "upload_id": "uuid",
  "conflict_policy": "WARN_DUPLICATES"
}
```

Response data:

```json
{
  "workspace_id": "uuid",
  "status": "NEEDS_REVIEW",
  "total_rows": 128,
  "valid_rows": 112,
  "error_rows": 6,
  "warning_rows": 10,
  "issues": [
    {
      "issue_id": "uuid",
      "source_row_number": 17,
      "severity": "ERROR",
      "code": "MISSING_REQUIRED_FIELD",
      "field": "sku_code",
      "message": "SKU code is required",
      "is_blocking": true
    }
  ]
}
```

### 5.7 Row Review

```text
GET /api/v1/intake/workspaces/{workspace_id}/rows?page=1&page_size=50&status=NEEDS_FIX
Permission: intake:read

PATCH /api/v1/intake/workspaces/{workspace_id}/rows/{row_id}
Permission: intake:update
```

Patch request:

```json
{
  "normalized_values": {
    "sku_code": "A-001",
    "name": "Cooking Oil 1L",
    "unit": "bottle",
    "barcode": "616000000001"
  },
  "review_status": "FIXED"
}
```

Rules:

- Patch never edits `raw_values`.
- Patch must revalidate only affected row or mark workspace requiring revalidation.
- `EXCLUDED` rows cannot be exported unless explicitly re-included.

### 5.8 Generate SKU Import CSV

```text
POST /api/v1/intake/workspaces/{workspace_id}/exports/sku-import-csv
Permission: intake:export
```

Rules:

- Requires zero blocking issues.
- Excludes rows with `review_status=EXCLUDED`.
- Generates U3-compatible CSV headers.
- Does not call U3 preview automatically unless caller uses the next endpoint.

Response data:

```json
{
  "export_id": "uuid",
  "status": "READY",
  "row_count": 112,
  "download_url": "/api/v1/intake/workspaces/{workspace_id}/exports/{export_id}/download"
}
```

### 5.9 Push To Existing SKU Import Preview

```text
POST /api/v1/intake/workspaces/{workspace_id}/exports/{export_id}/push-to-sku-import-preview
Permission: intake:import_to_erp and skus:import
```

Rules:

- Requires `intake:import_to_erp` and `skus:import`.
- Requires export status `READY`.
- Calls existing U3 preview path semantics.
- Returns U3 `import_id` and leaves final U3 validate/apply as explicit follow-up actions.
- Must not call U3 apply.

Response data:

```json
{
  "workspace_id": "uuid",
  "export_id": "uuid",
  "u3_import_id": "import_opaque_id",
  "next_step": "Run SKU import validate/apply through existing U3 flow"
}
```

## 6. File and Parser Contract

### 6.1 Supported File Types

MVP requirements:

- CSV: required.
- XLSX: required.
- XLS: out of scope unless explicitly approved.
- Password-protected XLSX: reject with `UNSUPPORTED_PROTECTED_FILE`.
- Multi-sheet XLSX: MVP reads first non-empty sheet by default and reports sheet name; explicit sheet selection can be U4-D if feasible.

### 6.2 Limits

Initial limits proposal:

| Limit | MVP Value | Error Code |
|---|---:|---|
| Max file size | 10 MB | `FILE_TOO_LARGE` |
| Max rows | 5,000 data rows | `ROW_LIMIT_EXCEEDED` |
| Max columns | 100 columns | `COLUMN_LIMIT_EXCEEDED` |
| Max cell length | 2,000 chars raw | `CELL_TOO_LARGE` |
| Max header length | 255 chars | `HEADER_TOO_LARGE` |
| Max image upload | 5 MB per image later | `ASSET_TOO_LARGE` |

Limits are intentionally conservative to keep request-time parsing safe. Large-file streaming/background jobs can be a later slice.

### 6.3 Header Normalization

Normalization must be deterministic and audited:

```text
trim whitespace
normalize Unicode only if parser library returns Unicode strings; do not transliterate in U4-B
lowercase ASCII letters
replace spaces, hyphens, and slashes with underscore
collapse repeated underscores
preserve original header in headers_raw
deduplicate collisions with suffix _2, _3
```

Example:

```text
"Item Code" -> "item_code"
"Item-Code" -> "item_code_2" if collision exists
```

### 6.4 Row Number Preservation

CSV:

- Header row is row 1.
- First data row is source row 2.
- Blank trailing rows are ignored and counted in parser summary.
- Blank interior rows are staged or ignored only by explicit parser rule; MVP proposal is to stage them with blocking `EMPTY_ROW` if any neighboring rows contain data.

XLSX:

- Preserve original worksheet row numbers.
- Hidden rows are parsed in MVP unless excluded later by an explicit option.
- Formula cells use cached values only; if no cached value is available, return blocking `UNSUPPORTED_FORMULA_CELL` for affected cells.

### 6.5 Blocking Errors vs Warnings

Blocking errors prevent `READY_FOR_EXPORT`:

- Required field missing.
- Duplicate staged `sku_code` among exportable rows.
- Invalid field length or numeric type.
- Parser failed.
- No header row detected.
- No data rows detected.

Warnings do not block export:

- Optional field missing.
- Extra unmapped column.
- Unknown barcode format.
- Unit default applied.
- Potential duplicate name with different SKU code.

## 7. Mobile/PWA Mini-Slice Contract

U4-G should be a thin mobile-friendly path, not a full offline mobile product.

Initial route proposal:

```text
/intake/mobile/:workspaceId
/intake/mobile/:workspaceId/scan
/intake/mobile/:workspaceId/photo
/intake/mobile/:workspaceId/review
```

Capabilities:

- Phone camera barcode scan using browser APIs where available.
- Manual barcode input fallback is mandatory.
- Product photo capture/upload stub uses `intake_assets` metadata contract.
- Scan creates or updates staged `intake_product_rows`, not SKUs.
- Public token access can be supported later but must remain workspace-scoped.

Out of scope for U4-B/U4-G initial slice:

- Offline deferred sync.
- Background upload queue.
- Push notifications.
- Native app.
- External barcode database lookup.
- OCR from shelf labels.

## 8. Permission Contract

New permissions:

| Permission | Meaning |
|---|---|
| `intake:read` | View workspaces, uploads, rows, issues, exports. |
| `intake:create` | Create workspaces and uploads. |
| `intake:update` | Save mappings, edit staged rows, resolve issues. |
| `intake:approve` | Mark workspace ready for export/import review. |
| `intake:export` | Generate and download exports. |
| `intake:import_to_erp` | Push generated export into U3 SKU import preview. |

Final ERP import requirement:

```text
Push to U3 preview requires intake:import_to_erp + skus:import.
U3 validate/apply continue to require skus:import.
```

Role template proposal:

| Role Template | Intake Permissions | Existing ERP Permissions |
|---|---|---|
| `admin` | all intake permissions | includes `skus:import` |
| `catalog_manager` | read/create/update/approve/export/import_to_erp | should include `skus:import` |
| `sales_rep` | read/create/update for assigned workspace only later | no `skus:import` by default |
| `warehouse_operator` | read/create/update for stock/mobile rows later | no `skus:import` by default |
| `finance_operator` | read only | no `skus:import` by default |
| `manager` | read/approve/export | no `skus:import` unless explicitly granted |

Bootstrap note:

- U4-C should add these permissions consistently to seed scripts only after CTO approves schema/API implementation.
- U4-B does not modify seed scripts.

## 9. Multilingual Preparation

U4-B does not implement translation.

Language posture:

- English first for product UI and API error messages.
- Chinese dev review notes allowed in planning/review artifacts, not required in runtime strings.
- Swahili glossary later, after U4-H customer proof clarifies field language.

U5 first string domains impacted by U4:

- Workspace statuses: draft, open, uploaded, mapped, validating, needs review, ready for export, exported, pushed to ERP preview, closed, cancelled.
- Upload errors: empty file, file too large, unsupported file type, parse failed, protected file unsupported.
- Mapping UI: source column, target field, required field, optional field, default value.
- Validation issues: missing required field, duplicate SKU code, invalid price, unmapped column, invalid barcode.
- Row review: approved, needs fix, excluded, fixed.
- Export/import: generate SKU import CSV, push to ERP preview, import requires approval.
- Mobile capture: scan barcode, enter manually, take product photo, upload pending.
- Permissions/empty states: no access, workspace not found, token expired.

## 10. Risk Register

| Risk | Severity | Notes | Mitigation |
|---|---|---|---|
| License/reference risk | High | ODK/DHIS2/ChT/InvenTree/Odoo/ERPNext are useful references but code must not be copied. | Clean-room design; use product needs and existing Mpango contracts only. |
| Customer data quality | High | Customer spreadsheets will have missing SKU codes, inconsistent units, duplicates, and free-text noise. | Staging-first review, blocking vs warning issues, row-level edits. |
| Image storage | Medium | Product photos introduce storage cost, access control, retention, malware scanning. | U4-B defines metadata only; U4-G can stub; production storage requires separate approval. |
| Tenant isolation | Critical | Intake rows can contain customer catalog and pricing-sensitive data. | Tenant-scoped tables, workspace ID filters, public token resolves to one workspace only. |
| Public token workspace access | High | Leaked token could allow unauthorized upload/read. | Hash tokens, expiry, least-capability token, rate limit, no cross-workspace data, audit events. |
| Large spreadsheet performance | Medium | XLSX parsing can consume memory/CPU. | Conservative size/row limits, later background parsing if needed. |
| Import duplication | High | Duplicate staged rows or ERP SKU codes can cause catalog corruption. | Dedupe issues, explicit conflict policy, U3 preview/validate before apply. |
| Silent ERP import | Critical | Customer staging could accidentally write SKUs without review. | Contract forbids direct SKU writes from U4; push only to U3 preview. |
| Parser ambiguity | Medium | Header normalization collisions can map wrong fields. | Preserve raw headers, collision suffixing, explicit mapping save. |
| Mobile camera compatibility | Medium | Browser barcode APIs vary by device. | Manual input fallback required. |

## 11. Tests-As-Contract Proposal

U4-B does not add runtime tests. U4-C/U4-D should add static and contract tests before implementation changes.

Proposed U4-C tests:

- Static migration/model contract for all proposed tables and indexes.
- Permission seed completeness for `intake:*` permissions.
- No intake router endpoint uses only `skus:import` except push-to-U3 path.
- Public token columns store hash only, not raw token.

Proposed U4-D parser tests:

- CSV parses headers, preserves row numbers, and returns sample rows.
- XLSX parses first sheet, preserves row numbers, and rejects protected/invalid files.
- Header normalization collision behavior is deterministic.
- Limits produce expected error codes.
- Blocking errors prevent export readiness; warnings do not.

Proposed U4-E frontend contract tests:

- Workspace shell never shows direct apply-to-ERP action.
- Push-to-ERP preview action is hidden without both `intake:import_to_erp` and `skus:import`.
- Row review preserves source row number and raw values.

## 12. Implementation Slicing Proposal

### U4-C Backend Schema Skeleton

- Add migration and ORM models for intake tables after CTO approval.
- Add permission seeds for `intake:*`.
- Add read/create workspace endpoints and static contract tests.
- No parser yet.

### U4-D Parser/Preview

- Implement CSV/XLSX parser boundary.
- Add upload endpoint, row staging, mapping save, validation issue generation.
- Keep exports disabled until validation and review contracts are stable.

### U4-E Frontend Workspace Shell

- Workspace list/detail.
- Upload form.
- Mapping screen.
- Row review table.
- Permission-aware actions.

### U4-F Bulk Stock Intake

- Extend staging contract for stock quantities and warehouse context.
- Do not mix stock intake with product SKU import unless export type is explicit.

### U4-G Mobile Scan/PWA Thin Slice

- Mobile route shell.
- Barcode scan with manual fallback.
- Photo capture/upload metadata stub.
- No offline sync.

### U4-H Runtime Customer Proof

- Use a real customer-style CSV/XLSX.
- Prove workspace isolation.
- Prove staged validation and row review.
- Generate U3-compatible CSV.
- Push to U3 preview.
- Do not apply into ERP unless separately approved for the proof.

## 13. CTO Review Questions

1. Should U4-C implement all six proposed tables at once, or split assets/exports into later migrations?
2. Should public token uploads be in MVP, or internal-only workspaces first?
3. Should XLSX multi-sheet selection be MVP or first-sheet-only?
4. Should generated U3 CSV include only `sku_code`, `name`, `unit`, or also `category`/`unit_price` when present?
5. Should `catalog_manager` receive `skus:import` by default, or require admin assignment?

## 14. Final Statement

This branch is `DESIGN_ONLY_NO_RUNTIME_CHANGE`.

No migrations, routers, models, services, parser code, frontend files, deployment files, or seed scripts are changed in U4-B.
