# U4-I-C: Runtime Intake Apply API Proof

| Field | Value |
|---|---|
| **Date** | 2026-07-02 |
| **Target HEAD** | `e3d92c8` merge: U4-I-B2 intake apply service |
| **Deployed Base** | `d7ad6478` + U4-I apply files + schema migration |
| **Operator** | automated |
| **Environment** | Tencent VPS 1.14.247.12, prod stack |
| **Verdict** | **PASS_RUNTIME_INTAKE_APPLY_API_PROOF** |

---

## Preflight

| Check | Result |
|---|---|
| **Target HEAD** | `e3d92c8` (merge: U4-I-B2 intake apply service) |
| **Local fetch** | `FETCH_HEAD = e3d92c8` ✓ |
| **DB backup** | `/tmp/u4ic_pre_deploy_20260702.sql.gz` (21,403 bytes, sha256 `ec4d88f...`) |
| **5/5 containers healthy** | ✓ |
| **Token permissions** | `intake:create` ✓, `intake:read` ✓, `intake:update` ✓, `skus:import` ✓ |
| **SKU count before** | 10 |

---

## Deploy

| Step | Result |
|---|---|
| Files transferred from `e3d92c8` via SFTP (6 files) | ✓ |
| Backend rebuilt | ✓ |
| Backend healthy after 5s | ✓ |
| Gateway recreated | ✓ |
| `/health/live` | 200 ✓ |
| `/health/ready` | 200 ✓ |
| `intake_apply_service.py` in container | ✓ |
| `POST /api/v1/intake/workspaces/{ws_id}/apply` registered | ✓ |

### DB Migration Applied

| Column | Table | Status |
|---|---|---|
| `apply_status` | `intake_workspaces` | ✓ |
| `applied_at` | `intake_workspaces` | ✓ |
| `applied_by` | `intake_workspaces` | ✓ |
| `apply_result` | `intake_workspaces` | ✓ |
| `apply_status` | `intake_product_rows` | ✓ |
| `target_sku_id` | `intake_product_rows` | ✓ |
| `apply_error` | `intake_product_rows` | ✓ |
| `apply_error_code` | `intake_product_rows` | ✓ |
| `apply_error_message` | `intake_product_rows` | ✓ |

### Image

| Component | Image ID |
|---|---|
| mpango-erp-backend | `5e27c615f9fd` |

---

## Scenario 1: Happy Path — 3 New SKUs

| Step | Endpoint | HTTP | Result |
|---|---|---|---|
| Create workspace | `POST /api/v1/intake/workspaces` | 201 | `workspace_id=0bb8ad0e` |
| Upload CSV | `POST /api/v1/intake/workspaces/{id}/uploads` | 201 | 3 rows, PARSED |
| Mapping | `PUT /api/v1/intake/workspaces/{id}/mapping` | 200 | 3 rows MAPPED |
| Validate | `POST /api/v1/intake/workspaces/{id}/validate` | 200 | READY_FOR_EXPORT, 0 errors |
| Apply | `POST /api/v1/intake/workspaces/{id}/apply` | 200 | **applied**, 3 SKUs created |

### Apply Response

```json
{
  "workspace_id": "0bb8ad0e-...",
  "apply_status": "applied",
  "created_count": 3,
  "row_count": 3,
  "created_sku_ids": ["c4e26a57-...", "578c38f1-...", "5d331f5f-..."]
}
```

### DB Audit Verification

| Audit Field | Result |
|---|---|
| `apply_status` = `applied` | ✓ |
| `applied_at` IS NOT NULL | ✓ |
| `applied_by` IS NOT NULL | ✓ |
| `apply_result->>'created_count'` = 3 | ✓ |
| `apply_result->>'row_count'` = 3 | ✓ |
| Row `apply_status` = `applied` | ✓ (all 3 rows) |
| Row `target_sku_id` IS NOT NULL | ✓ (all 3 rows) |
| Rows endpoint | ✓ 3 rows visible |
| Issues endpoint | ✓ 0 issues |

---

## Scenario 2: Idempotency — Repeat Apply

| Check | Result |
|---|---|
| Repeat apply | HTTP 409 |
| Error code | `ALREADY_APPLIED` |
| Message | "Intake workspace has already been applied" |
| SKU count | 13 (unchanged) ✓ |

---

## Scenario 3: Fail-Closed — Duplicate Staged SKU Codes

| Check | Result |
|---|---|
| Validate | `NEEDS_REVIEW`, 2 errors (duplicate SKU codes detected) |
| Apply | HTTP 409 |
| Error code | `WORKSPACE_NOT_READY` |
| Message | "Workspace must be READY_FOR_EXPORT before apply" |
| SKU count | 13 (unchanged) ✓ |
| **No SKUs written** | ✓ |

---

## Scenario 4: Fail-Closed — Existing Official SKU Code

| Check | Result |
|---|---|
| Validate (existing SKU `U4IC-APPLY-001` in staged data) | `READY_FOR_EXPORT`, 0 errors |
| Apply | HTTP 409 |
| Error code | `SKU_CODE_EXISTS` |
| Message | "One or more staged sku_code values already exist" |
| SKU codes | `['U4IC-APPLY-001']` |
| SKU count | 13 (unchanged) ✓ |
| **No SKUs written** | ✓ |

---

## SKU Count Progression

| Stage | SKU Count | Delta |
|---|---|---|
| Before | 10 | — |
| After happy path apply | 13 | +3 ✓ |
| After idempotency | 13 | 0 ✓ |
| After duplicate SKU codes | 13 | 0 ✓ |
| After existing SKU code | 13 | 0 ✓ |

---

## Health

| Check | Status |
|---|---|
| mpango_prod_backend | ✓ healthy |
| mpango_prod_gateway | ✓ healthy |
| mpango_prod_frontend | ✓ healthy |
| mpango_prod_postgres | ✓ healthy |
| mpango_prod_redis | ✓ healthy |

---

## Error Handling Summary

| Error | HTTP | Behavior |
|---|---|---|
| `ALREADY_APPLIED` | 409 | Safe idempotent refusal |
| `WORKSPACE_NOT_READY` | 409 | Prevents apply with validation errors |
| `SKU_CODE_EXISTS` | 409 | Prevents duplicate SKU creation, lists conflicting codes |

---

## Files

| File | Purpose |
|---|---|
| `ai-ledger/ops/2026-07-02_u4ic_runtime_intake_apply_api_proof.md` | This report |

---

## Verdict

**PASS_RUNTIME_INTAKE_APPLY_API_PROOF**

- Apply creates official SKUs from staged intake rows ✓
- Workspace/row audit fields populated correctly ✓
- Repeat apply safe (409, no duplicates) ✓
- Duplicate staged SKU codes blocked (409, no SKUs written) ✓
- Existing official SKU code blocked (409, no SKUs written) ✓
- No secrets printed, no direct DB writes, no code changes ✓
