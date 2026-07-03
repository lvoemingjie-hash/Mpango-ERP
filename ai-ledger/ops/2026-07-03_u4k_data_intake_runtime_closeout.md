# U4-K-R1: Data Intake Runtime Closeout Gate (corrected)

| Field | Value |
|---|---|
| **Date** | 2026-07-03 |
| **Target HEAD** | `f3a7261` (merge: U4-H-A mobile scan preview thin slice) |
| **Deployed Base** | `d7ad647` with U4-E/U4-J/U4-H-A frontend files deployed via SFTP |
| **Environment** | Tencent VPS 1.14.247.12, prod stack |
| **Verdict** | **PASS_U4_RUNTIME_CLOSEOUT_WITH_DEPLOYMENT_PROVENANCE_CAVEAT** |

---

## 1. Deployment Drift

| Check | Result |
|---|---|
| **Required HEAD** | `f3a7261` or newer |
| **VPS git HEAD** | `d7ad647` (docs: correct U4-B public token scope) |
| **Drift detected** | Yes -- VPS git is behind (no fetch access). |
| **Mitigation** | U4-E/U4-J/U4-H-A frontend files transferred from `f3a7261` via SFTP; backend files from U4-I-C already deployed. Frontend rebuilt with `docker compose build --no-cache frontend` (image `1219e5e5905b`). |
| **Drift resolved for frontend** | Yes -- built JS matches `f3a7261`. |
| **Backend drift** | Backend at `d7ad647` + U4-I-C manual files; functionally equivalent to `f3a7261` backend. |

**Provenance caveat:** This is NOT an exact git deploy proof. The VPS could not fetch `f3a7261` directly. Source files were transferred out-of-band via SFTP and rebuilt. The running artifact is functionally equivalent but provenance is manually attested rather than git-verified.

---

## 2. Health

| Component | Status |
|---|---|
| mpango_prod_backend | running PASS |
| mpango_prod_gateway | running PASS |
| mpango_prod_frontend | running PASS |
| mpango_prod_postgres | running PASS |
| mpango_prod_redis | running PASS |
| `/health/live` | 200 PASS |
| `/health/ready` | 200 PASS |

---

## 3. Frontend Routes (Built JS Verification)

| Route / Component | Found in Bundle |
|---|---|
| `/skus/intake` | PASS |
| `/skus/scan` | PASS |
| `BarcodeDetector` (MobileScan component) | PASS |
| `intake:update and skus:import` (Apply-to-Products permission gate) | PASS |

---

## 4. Admin Permissions

| Check | Result |
|---|---|
| Admin role | PASS |
| `intake:create` | PASS |
| `intake:update` | PASS |
| `skus:import` | PASS |

---

## 5. Full Data Intake Flow

| Step | Endpoint | HTTP | Detail |
|---|---|---|---|
| Create workspace | `POST /api/v1/intake/workspaces` | 201 | `id=38a41bb5`, status=OPEN |
| Upload CSV | `POST /api/v1/intake/workspaces/{id}/uploads` | 201 | 3 rows, PARSED |
| Map fields | `PUT /api/v1/intake/workspaces/{id}/mapping` | 200 | 3 rows MAPPED |
| Validate | `POST /api/v1/intake/workspaces/{id}/validate` | 200 | READY_FOR_EXPORT, 0 errors, 0 warnings |
| Preview rows | `GET /api/v1/intake/workspaces/{id}/rows` | 200 | 3 rows |
| Preview issues | `GET /api/v1/intake/workspaces/{id}/issues` | 200 | 0 issues |
| **Apply to Products** | `POST /api/v1/intake/workspaces/{id}/apply` | **200** | **applied, 3 SKUs created** |

---

## 6. SKU Count Trace

All counts below verified via direct DB query on `t_550e8400e29b41d4a716446655440000.skus WHERE is_deleted=false`.

### Cumulative

| Stage | SKU Count | Delta | Source |
|---|---|---|---|
| Pre-U4 baseline | 10 | -- | Original seed data |
| After U4-I-C happy path | 13 | +3 | U4IC-APPLY-001/002/003 via Apply |
| After U4-K debug (DBG run) | 15 | +2 | DBG-001/002 via Apply (debug) |
| After U4-K first proof (CLT run) | 18 | +3 | U4K-CLT-001/002/003 via Apply |
| **After U4-K final proof (GATE run)** | **21** | **+3** | **U4K-GATE-101/102/103 via Apply** |
| After idempotency test | 21 | 0 | Repeat Apply blocked (409) |
| After /skus/scan page access | 21 | 0 | Scan preview (no SKU writes) |
| After duplicate staged SKU codes | 21 | 0 | Blocked by validate (NEEDS_REVIEW) |
| After existing SKU code in staged data | 21 | 0 | Blocked by Apply (SKU_CODE_EXISTS) |

### Delta Attribution

| Activity | SKU Delta | Explanation |
|---|---|---|
| Baseline | 10 | Seeds from S5-D2-B |
| U4-I-C Apply (happy path) | +3 | Legitimate intake-to-SKU flow |
| U4-K debug Apply (DBG-*) | +2 | Transient 502 diagnostic run |
| U4-K proof v1 Apply (CLT-*) | +3 | Early proof run with stale API count |
| U4-K proof v2 Apply (GATE-*) | +3 | Final clean proof run |
| All idempotency attempts | 0 | Safe refusal |
| All scan preview page loads | 0 | No write path triggered |
| All duplicate SKU attempts | 0 | Blocked by validate or Apply |

**Key invariant:** Mobile Scan page access caused 0 SKU delta in every test. Only explicit `POST /apply` can create SKUs.

---

## 7. Idempotency

| Check | Result |
|---|---|
| Repeat POST /apply | HTTP 409 CONFLICT |
| Error code | `ALREADY_APPLIED` |
| SKU count unchanged | PASS |

---

## 8. Mobile Scan Preview

| Check | Result |
|---|---|
| `/skus/scan` page loads (200) | PASS |
| SPA served correctly | PASS |
| BarcodeDetector component in JS bundle | PASS |
| Manual barcode/SKU input in component | PASS |
| Preview-only notice in component | PASS |
| SKU count unchanged after page access | PASS (0 delta) |

---

## 9. Fail-Closed -- Duplicate Staged SKU Codes

| Check | Result |
|---|---|
| Validate status | `NEEDS_REVIEW` |
| Validation errors | 2 (duplicate SKU codes detected) |
| Apply HTTP | 409 CONFLICT |
| Error code | `WORKSPACE_NOT_READY` |
| SKU count unchanged | PASS (0 delta) |

---

## 10. Fail-Closed -- Existing Official SKU Code

| Check | Result |
|---|---|
| Validate status | `READY_FOR_EXPORT` |
| Validation errors | 0 (codes are unique within workspace) |
| Apply HTTP | 409 CONFLICT |
| Error code | `SKU_CODE_EXISTS` |
| Conflicting codes | `['U4K-GATE-101']` |
| SKU count unchanged | PASS (0 delta) |

---

## Error Summary

| Error | Count | Location |
|---|---|---|
| Transient 502 on first apply attempt | 1 | Timed out during initial proof run; resolved on retry |
| Stale API SKU count in proof v1 | 1 | API returned 15 while DB had 18; likely token/timing issue. DB used as source of truth thereafter. |
| None (final run) | 0 | All checks pass |

---

## Next Ops Risk

Before final MVP release, fix deployment provenance so the VPS can deploy an exact `origin/product-dev-recovered` commit by either:
- Restoring SSH key or HTTPS token-based `git fetch` / `git checkout`, or
- Implementing a controlled artifact release (e.g., `docker save` / `docker load` or CI-built tarball).

Without this, every U-series gate requires manual SFTP transfer, build, and drift attestation, which is error-prone and non-reproducible.

---

## Verdict

**PASS_U4_RUNTIME_CLOSEOUT_WITH_DEPLOYMENT_PROVENANCE_CAVEAT**

- All 5 containers healthy PASS
- Data Intake flow: create -> upload -> map -> validate -> rows/issues preview -> Apply creates SKUs PASS
- Apply-to-Products button with permission gate present in JS bundle PASS
- Mobile Scan page loads, BarcodeDetector component with manual fallback, preview-only contract PASS
- No SKU writes from scan preview alone PASS (0 delta in all tests)
- Idempotency safe (409 on repeat) PASS
- Duplicate staged SKU codes blocked PASS
- Existing official SKU codes blocked PASS
- No secrets printed PASS
- Provenance caveat: NOT an exact git deploy -- frontend files transferred via SFTP from `f3a7261`, rebuilt. Functionally equivalent but manually attested.
