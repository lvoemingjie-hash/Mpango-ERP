# U4-L: Data Intake Final Closeout Packet

| Field | Value |
|---|---|
| **Date** | 2026-07-03 |
| **Base** | `origin/product-dev-recovered` at `f3a7261` |
| **HEAD** | `84f9629` U4-K-R1 |
| **Branch** | `u4k-closeout-2026-07-03` |
| **Verdict** | **PASS_FOR_CTO_U4L_REVIEW** |

---

## 1. U4 Phase Inventory

| Phase | Verdict | Type | Summary |
|---|---|---|---|
| **U4-A** Permission Foundation | `PASS_FOR_CTO_U4A_REVIEW` | Code | Fixed incorrect `inventory:write` product gate to `skus:create`/`skus:update`/`skus:import`. Added centralized permission helper (`can()`). Declared `intake:*` and `skus:*` permission constants. Seeded admin with `intake:create`, `intake:update`, `skus:import`. |
| **U4-B** Contract Architecture | `PASS_FOR_CTO_U4B_REVIEW_AFTER_R1` | Docs | Defined staging-first intake architecture (workspace -> upload -> map -> validate -> apply). R1 corrected public token scope: deferred to U4-G/U4-H with `public.intake_public_tokens` registry contract. CTO slicing decisions recorded. |
| **U4-C** Backend Schema Skeleton | `PASS_FOR_CTO_U4C_REVIEW` | Code | Created tenant migrations for `intake_workspaces`, `intake_uploads`, `intake_product_rows`, `intake_validation_issues`. Added workspace create/list/detail routes only. No upload, parser, mapping, validate, rows, or issues endpoints -- those belong to U4-D. |
| **U4-D** Parser Preview | `PASS_FOR_CTO_U4D_REVIEW` | Code | CSV/XLSX parser with header normalization, `source_row_number` provenance, `raw_values` preservation. Upload, mapping, validate, rows, and issues endpoints built on U4-C staging tables. Mapping route with field-to-column assignment. Validate route with duplicate SKU code detection. Rows/issues preview endpoints. |
| **U4-E** Frontend Entry | Merged into `f3a7261` | Code | `/skus/intake` frontend route with workspace creation, upload (CSV/XLSX), field mapping UI, validation trigger, rows/issues table preview. Integrates with U4-D backend. |
| **U4-F** Runtime Transaction/Search-Path Fix | `PASS_FOR_CTO_REVIEW` | Code | Root cause: route-level `db.commit()` reset `SET LOCAL search_path`. Fix: replaced `db.commit()` with `await db.flush()` in 4 write endpoints. R4 confirmed full browser flow passes. |
| **U4-G** Planning Gate | -- | Docs | Planning gate for U4 closeout strategy. |
| **U4-I** Apply Audit/Service/Runtime Proof | `PASS_RUNTIME_INTAKE_APPLY_API_PROOF` | Code + Docs | U4-I-B1: apply audit schema contract (apply_status, applied_at, applied_by, apply_result on intake_workspaces). U4-I-B2: POST /apply service with idempotency (409), fail-closed for invalid status, blocking issues, duplicate/existing SKU codes. U4-I-C: runtime proof -- 3 SKUs created, idempotency blocking, duplicate/existing SKU code blocking. |
| **U4-J** Frontend Apply Button | `PASS_FOR_CTO_U4J_REVIEW` | Code | Apply-to-Products UI with permission gate (`intake:update` + `skus:import`), confirmation dialog, success feedback, friendly error messages for all fail-closed states. |
| **U4-H** Mobile Scan Preview | Merged into `f3a7261` | Code | `/skus/scan` route with BarcodeDetector API (Chrome/Edge/Android WebView) + manual barcode/SKU text input fallback. Preview-only -- no write path. 0 SKU delta verified in runtime. Entry gated on `intake:create OR intake:update` (canUseIntake). No `skus:import` requirement. |
| **U4-K** Runtime Closeout | `PASS_U4_RUNTIME_CLOSEOUT_WITH_DEPLOYMENT_PROVENANCE_CAVEAT` | Ops | 5/5 containers healthy. Full flow verified on prod: create -> upload CSV -> map -> validate -> preview -> Apply creates SKUs. Idempotency (409), scan preview (0 delta), duplicate codes blocked, existing SKU codes blocked. SKU count trace: 10 -> 21. |

---

## 2. Current User-Facing Capability

The deployed VPS (1.14.247.12) exposes a complete Data Intake user journey for internal admin users:

### Upload & Parse

CSV (UTF-8, UTF-8-sig) and XLSX (first non-empty sheet, openpyxl) files uploaded to an intake workspace. Headers normalized deterministically; repeated headers disambiguated. `source_row_number` and `raw_values` preserved for provenance.

### Field Mapping

User maps uploaded columns to canonical product fields (sku_code, product_name, price, stock, etc.). Mapping is persisted and can be updated before validation.

### Validate

Workspace is validated: duplicate SKU codes within the staged data produce `NEEDS_REVIEW` status with per-row issues. Validation also checks field-level constraints (required fields, data types). Status must be `READY_FOR_EXPORT` with 0 blocking issues before apply is available.

### Preview Rows & Issues

Rows endpoint returns staged rows with mapped field values. Issues endpoint returns validation errors/warnings with source row references. Both available before and after validation.

### Apply to Products

- Permission-gated: user must have both `intake:update` and `skus:import`.
- Confirmation dialog before execution.
- Creates official SKU records from staged intake rows.
- Returns 200 with `created_count` and `created_sku_codes`.
- Idempotent: repeat apply returns 409 `ALREADY_APPLIED`.
- Fail-closed: `WORKSPACE_NOT_READY` (if validate not passed), `BLOCKING_ISSUES`, `DUPLICATE_STAGED_SKU_CODE`, `SKU_CODE_EXISTS`.

### Mobile Scan Preview

- Route: `/skus/scan`
- Uses `BarcodeDetector` API on supported browsers (Chrome, Edge, Android WebView).
- Manual text input fallback for Firefox, Safari, desktop.
- Preview-only: detected/entered barcodes are displayed but not written to any backend.
- Permission: entry shown via `canUseIntake` (user has `intake:create` OR `intake:update`). No `skus:import` requirement for scan preview.

---

## 3. Runtime Truth

### U4-K Verdict

```
PASS_U4_RUNTIME_CLOSEOUT_WITH_DEPLOYMENT_PROVENANCE_CAVEAT
```

All checks pass on the deployed VPS environment:

| Check | Result |
|---|---|
| All 5 containers healthy | PASS |
| Create -> upload -> map -> validate -> rows/issues preview -> Apply to Products | PASS (3 SKUs created) |
| Apply button with permission gate in JS bundle | PASS |
| Mobile scan page loads, BarcodeDetector + manual fallback | PASS |
| No SKU writes from scan preview alone | PASS (0 delta) |
| Idempotency (repeat apply = 409) | PASS |
| Duplicate staged SKU codes blocked | PASS |
| Existing official SKU codes blocked | PASS |
| SKU count: 10 (baseline) -> 21 (final) | PASS |
| No secrets printed in any report | PASS |

### Provenance Caveat (Critical)

The deployed VPS git HEAD is `d7ad647`, not the target `f3a7261`. VPS cannot fetch from GitHub (SSH permission denied, GnuTLS recv error -110). Mitigation:

- U4-E, U4-J, U4-H-A frontend files transferred from `f3a7261` via local->SFTP pipe.
- Backend files from U4-I-C deployed at earlier sprint.
- Frontend rebuilt: image `1219e5e5905b`.
- Running artifact is **functionally equivalent** to `f3a7261` but provenance is **manually attested**, not git-verified.

This means:
- Every deploy requires manual SFTP + rebuild + attestation.
- No `git revert` safety -- if `d7ad647` and `f3a7261` diverge further, the SFTP patch set must be recomputed manually.
- Any future U-series gate will inherit this provenance debt.

---

## 4. Explicit Remaining Gaps

### 4.1 Exact Git Deploy on VPS -- NOT FIXED

VPS still cannot `git fetch` or `git checkout` from GitHub. All deployments require manual SFTP transfer and drift attestation. This is the single highest-risk item before any production release.

### 4.2 Mobile Scan -- Preview Only, Not Scan-to-Staging

The `/skus/scan` page displays detected barcodes and allows manual entry, but there is no write path. A user cannot scan a barcode and have it automatically populate an intake workspace or staging row. The U4-H contract explicitly deferred this to a future phase.

### 4.3 No Image Upload / Product Photo Intake

The intake pipeline handles CSV/XLSX structured data only. There is no `intake_assets` table, no photo upload endpoint, no image association with product rows or SKUs. This was deferred per CTO decision in U4-B.

### 4.4 No Public Intake Link / Token

All intake routes require an authenticated admin session. There is no public intake endpoint (e.g., `POST /api/v1/intake/public/{token}`) for external suppliers or vendors to submit product data without logging in. U4-B R1 explicitly deferred this, noting it requires a `public.intake_public_tokens` registry.

### 4.5 No Multilingual UI

The entire Data Intake UI is in English only. No i18n framework or language switching exists.

---

## 5. Recommended Next Phase

### OPS-D1: Exact Deployment Provenance Fix (BEFORE final MVP release)

**Priority: CRITICAL**

Restore git fetch/checkout capability on the VPS, OR implement a controlled artifact release pipeline. Options:

1. Restore SSH key-based GitHub access (generate new deploy key with read-only access).
2. Or switch to HTTPS + personal access token for `git fetch`.
3. Or implement `docker save` / `docker load` artifact workflow: build images locally, transfer tarball, load on VPS.
4. Or implement CI build server that pushes signed artifacts to VPS via rsync/SFTP with SHA-256 manifest verification.

Without this, every future deploy is manual, error-prone, and non-reproducible.

### U5-A: Multilingual MVP Path (AFTER U4 closeout)

**Priority: MEDIUM**

Add i18n support to the frontend. This is the natural next user-facing feature after Data Intake capability is closed. Scope:

- i18n framework selection (react-i18next or similar).
- English + Chinese (zh-CN) initial language pair.
- Translation of Data Intake UI + admin panels.
- Language switcher in navigation.

### U4-H-B: Scan-to-Staging (Optional, after U5-A planning)

**Priority: LOW**

Extend Mobile Scan from preview-only to scan-to-staging:

- Create `POST /api/v1/intake/workspaces/{id}/scan` endpoint.
- Accept detected barcode + optional manual fields, insert as a single-row staging add.
- Update `/skus/scan` UI with a "Send to Workspace" action.
- Requires CTO prioritization of scan workflow over other features.

---

## 6. Merge / Readiness Recommendation

| Criterion | Status |
|---|---|
| All U4 code phases merged to `product-dev-recovered` | PASS (`f3a7261` merge commit exists) |
| Full user-facing intake flow on VPS | PASS |
| Runtime closeout gate passed | PASS (with provenance caveat) |
| All fail-closed paths verified | PASS |
| Idempotency verified | PASS |
| 0 SKU delta from scan preview | PASS |
| No secrets leaked | PASS |
| Deployment provenance automated | **FAIL** |
| Public internet exposure safe | N/A (no public auth required yet) |

### Recommendation

**U4 can be marked FUNCTIONALLY_CLOSED_FOR_MVP_DATA_INTAKE.**

The Data Intake feature is complete, tested, and runtime-proven for internal admin users. All MVP-scoped capability (CSV/XLSX upload -> map -> validate -> Apply to Products) works end-to-end. The Mobile Scan preview is present and verified read-only.

**U4 is NOT PRODUCTION_RELEASE_CLOSED** until OPS-D1 (exact deployment provenance fix) is resolved. The manual SFTP deploy process is acceptable for dev/UAT but is a release blocker for production:

1. Cannot `git revert` to roll back.
2. Drift between VPS git state and deployed state is manually attested, not verified.
3. Every hotfix or patch requires the same manual SFTP + rebuild procedure.
4. No audit trail of "which git commit is currently running" -- only "which git commit the frontend image was built from."

---

## 7. Verdict

**PASS_FOR_CTO_U4L_REVIEW**

- Complete U4 phase inventory: 11 phases, all accounted for.
- User-facing capability documented: upload, map, validate, preview, apply, scan preview.
- Runtime truth captured: full flow passes, provenance caveat clearly explained.
- Remaining gaps documented: 5 items with OPS-D1 as critical.
- Next phases recommended: OPS-D1 > U5-A > U4-H-B.
- Merge readiness: FUNCTIONALLY_CLOSED_FOR_MVP_DATA_INTAKE, not PRODUCTION_RELEASE_CLOSED.

---

*Report generated 2026-07-03. Base: `origin/product-dev-recovered` at `f3a7261`. Docs only -- no product code changes, no deploy, no push.*
