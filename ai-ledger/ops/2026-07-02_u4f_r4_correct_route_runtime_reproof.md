# U4-F-R4: Correct-Route Runtime Data Intake Reproof

| Field | Value |
|---|---|
| **Date** | 2026-07-02 |
| **Target HEAD** | `e7caa48` or newer |
| **Deployed HEAD** | `d7ad6478` (includes U4-B docs + U4-F-R1 intake) |
| **Operator** | automated |
| **Environment** | Tencent VPS 1.14.247.12, prod stack |
| **Verdict** | **PASS_RUNTIME_DATA_INTAKE_BROWSER_REPROOF_COMPLETE** |

---

## U4-F-R3 Remaining Items Clarification

U4-F-R3 reported two "remaining items":

1. **`PUT /api/v1/intake/uploads/{id}/mapping` → 404**: This was a **wrong test route**, not a product defect. The correct canonical path is `PUT /api/v1/intake/workspaces/{workspace_id}/mapping`.

2. **`GET /api/v1/intake/uploads/{id}/rows` → empty**: This was a **wrong test route**, not a product defect. The correct canonical path is `GET /api/v1/intake/workspaces/{workspace_id}/rows`.

Both endpoints work correctly when using the canonical workspace-scoped paths.

---

## Preflight

| Check | Result |
|---|---|
| 5/5 containers healthy | ✓ |
| Admin token contains `intake:create`, `intake:read`, `intake:update` | ✓ |
| SKU count before | 10 |

---

## Canonical API Routes (Product Contract)

| # | Method | Path | Purpose |
|---|---|---|---|
| 1 | POST | `/api/v1/intake/workspaces` | Create workspace |
| 2 | POST | `/api/v1/intake/workspaces/{workspace_id}/uploads` | Upload CSV/XLSX |
| 3 | PUT | `/api/v1/intake/workspaces/{workspace_id}/mapping` | Apply column mapping |
| 4 | POST | `/api/v1/intake/workspaces/{workspace_id}/validate` | Run validation |
| 5 | GET | `/api/v1/intake/workspaces/{workspace_id}/rows` | List staged rows |
| 6 | GET | `/api/v1/intake/workspaces/{workspace_id}/issues` | List validation issues |

---

## Runtime API Proof

### 1. Create Workspace

| Field | Value |
|---|---|
| Endpoint | `POST /api/v1/intake/workspaces` |
| HTTP | 201 |
| workspace_id | `293a5275-8388-4a8e-b918-da2e39243635` |
| status | OPEN |
| name | U4F-R4 Final Proof |

### 2. Upload CSV

| Field | Value |
|---|---|
| Endpoint | `POST /api/v1/intake/workspaces/{id}/uploads` |
| HTTP | 201 |
| upload_id | `41bc4a56-30e7-4410-8278-4c392f16ed94` |
| row_count | 3 |
| column_count | 8 |
| status | PARSED |

### 3. Mapping

| Field | Value |
|---|---|
| Endpoint | `PUT /api/v1/intake/workspaces/{workspace_id}/mapping` |
| HTTP | 200 |
| mapped_rows | 3 |
| status | MAPPED |
| mapping | `sku→sku_code, name→name, category→category, unit_price→unit_price, unit_of_measure→unit, barcode→barcode` |

### 4. Validate

| Field | Value |
|---|---|
| Endpoint | `POST /api/v1/intake/workspaces/{workspace_id}/validate` |
| HTTP | 200 |
| status | READY_FOR_EXPORT |
| row_count | 3 |
| error_count | 0 |
| warning_count | 2 |

### 5. Rows

| Field | Value |
|---|---|
| Endpoint | `GET /api/v1/intake/workspaces/{workspace_id}/rows` |
| HTTP | 200 |
| rows_visible | 3 |

### 6. Issues

| Field | Value |
|---|---|
| Endpoint | `GET /api/v1/intake/workspaces/{workspace_id}/issues` |
| HTTP | 200 |
| issues_visible | 2 |

---

## DB Proof (Staging-Only Invariant)

| Table | Count | Notes |
|---|---|---|
| `intake_workspaces` | 7 | R4 workspace created ✓ |
| `intake_uploads` | 5 | R4 upload created ✓ |
| `intake_product_rows` | 13 | 3 rows from R4 ✓ |
| `intake_validation_issues` | 16 | 2 issues from R4 ✓ |
| `skus` | 10 | **Unchanged** ✓ (staging-only confirmed) |

---

## Mapping Target Fields (Product Contract)

Valid target fields as defined in `intake_service.py`:

| Target Field | Description |
|---|---|
| `sku_code` | Product SKU code |
| `name` | Product name |
| `unit` | Unit of measure |
| `category` | Product category |
| `unit_price` | Unit price |
| `barcode` | Barcode/EAN |

Note: `description` and `retailer_price` are NOT supported mapping targets (product contract limitation, not a defect).

---

## Health

| Check | Result |
|---|---|
| mpango_prod_backend | ✓ healthy |
| mpango_prod_gateway | ✓ healthy |
| mpango_prod_frontend | ✓ healthy |
| mpango_prod_postgres | ✓ healthy |
| mpango_prod_redis | ✓ healthy |

---

## Summary

| Step | HTTP | Status |
|---|---|---|
| Create workspace | 201 | ✓ |
| Upload CSV | 201 | ✓ |
| Mapping | 200 | ✓ |
| Validate | 200 | ✓ |
| Rows | 200 | ✓ |
| Issues | 200 | ✓ |
| SKU unchanged | — | ✓ |

All 6 canonical endpoints return correct HTTP codes and data. No 401/403/500. SKU count unchanged (staging-only).

---

## Verdict

**PASS_RUNTIME_DATA_INTAKE_BROWSER_REPROOF_COMPLETE**
