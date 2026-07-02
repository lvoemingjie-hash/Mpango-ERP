# U4-G -- Data Intake Closeout + Next-Slice Planning Gate

**Date**: 2026-07-02
**Type**: Governance / Closeout / Planning (READ-ONLY -- no product code modified)
**Lineage**: `origin/product-dev-recovered` (`e7caa48`)
**Verdict**: `PASS_FOR_CTO_U4G_REVIEW`

---

## 0. Scope & Constraints Honored

| Constraint | Status |
|-----------|--------|
| Only ledger/report docs added/modified | PASS |
| No backend/frontend/migration/deploy code changes | PASS |
| No VPS write operations | PASS |
| No permissions/users/passwords/DB/containers modified | PASS |
| No `product-dev-recovered` push | PASS |

---

## 1. Phase Inventory (U4-A through U4-F)

Evidence reconstructed from `git log origin/product-dev-recovered` and the
ops ledger trail. SHAs are exact merge/feature commits.

### U4-A -- Data Intake Permission & Product Gate Foundation

| Field | Value |
|-------|-------|
| Merge commit | `57e5160 merge: U4-A data intake permission foundation` |
| Feature commit | `4492970 feat(U4-A): permission helper, product gate fix ...` |
| Deliverables | Centralized `can()`/`canAny()`/`isAdmin()` helper; fixed product gate (`inventory:write` -> `skus:create`/`skus:update`); 6 intake permission constants (`intake:read/create/update/approve/export/import_to_erp`); permission seeds in 4 scripts |
| Validation | Frontend: 50/50 pass (19 helper + 8 SKU gate + 23 existing). Backend: 33/33 pass. |
| Runtime proof | N/A (foundation only, no runtime path) |
| Verdict | `PASS_FOR_CTO_U4A_REVIEW` |

### U4-B -- Data Intake Contract Architecture

| Field | Value |
|-------|-------|
| Merge commit | `3d39d4b merge: U4-B data intake contract architecture` |
| Commits | `0c34855 docs: define U4-B data intake contract`; `4aa9b1a docs: correct U4-B public token scope` |
| Deliverables | Contract design document; defined workspace-scoped API as canonical; clarified public token is out-of-scope for MVP (internal logged-in user only) |
| Validation | Document review (no code) |
| Runtime proof | N/A (contract doc only) |
| Verdict | `PASS` (contract accepted, no code) |

### U4-C -- Data Intake Backend Schema Skeleton

| Field | Value |
|-------|-------|
| Merge commit | `958eb21 merge: U4-C data intake backend schema skeleton` |
| Commits | `b6c8973 feat: add intake workspace backend skeleton`; `85811e5 test: prove intake runtime contracts` |
| Deliverables | 4 tenant-scoped models (`IntakeWorkspace`, `IntakeUpload`, `IntakeProductRow`, `IntakeValidationIssue`); Alembic 024 migration; API router skeleton; runtime contract tests |
| Validation | Contract tests pass |
| Runtime proof | N/A at this slice (no runtime flow yet) |
| Verdict | `PASS` |

### U4-D -- Data Intake Parser Preview

| Field | Value |
|-------|-------|
| Merge commit | `5ca1472 merge: U4-D data intake parser preview` |
| Commit | `6e20d87 feat: add intake parser preview` |
| Deliverables | CSV/XLSX parser; upload endpoint; row staging; preview generation |
| Validation | Unit tests pass |
| Runtime proof | N/A (staging-only, no deploy in this slice) |
| Verdict | `PASS` |

### U4-E -- Data Intake Frontend Entry

| Field | Value |
|-------|-------|
| Merge commit | `c89d468 merge: U4-E data intake frontend entry` |
| Commits | `1ef444e feat: add intake frontend entry`; `0942963 fix: sequence intake validation preview reads` |
| Deliverables | Frontend entry point for data intake; validation/preview sequencing fix |
| Validation | Frontend tests pass |
| Runtime proof | N/A (frontend entry, no runtime flow) |
| Verdict | `PASS` |

### U4-F -- Intake Transaction Search Path Fix + Runtime Reproof

| Field | Value |
|-------|-------|
| Merge commit | `e7caa48 merge: U4-F-R1 intake transaction search path fix` |
| Commit | `4b477f0 fix: keep intake writes in tenant transaction` |
| Deliverables | Transaction search_path fix so intake writes land in the correct tenant schema; full runtime reproof chain |
| Validation | R1 fix; R2 runtime reproof (STOP -- RBAC gap); R3 RBAC reconcile + reproof (PASS); R4 correct-route final reproof (PASS) |
| Runtime proof | **COMPLETE** -- see Section 2 |
| Verdict | `PASS_RUNTIME_DATA_INTAKE_BROWSER_REPROOF_COMPLETE` (R4) |

---

## 2. Runtime Truth (U4-F-R4 Final Facts)

The deployed runtime on Tencent VPS `1.14.247.12` (HEAD `d7ad6478`) was proven
end-to-end via the **6 canonical workspace-scoped endpoints**. This is the
authoritative runtime state.

### 2.1 All 6 Canonical Endpoints Pass

| # | Method | Path | HTTP | Result |
|---|--------|------|------|--------|
| 1 | POST | `/api/v1/intake/workspaces` | 201 | workspace created |
| 2 | POST | `/api/v1/intake/workspaces/{id}/uploads` | 201 | 3 rows, 8 cols, PARSED |
| 3 | PUT | `/api/v1/intake/workspaces/{id}/mapping` | 200 | 3 mapped, MAPPED |
| 4 | POST | `/api/v1/intake/workspaces/{id}/validate` | 200 | READY_FOR_EXPORT, 0 errors, 2 warnings |
| 5 | GET | `/api/v1/intake/workspaces/{id}/rows` | 200 | 3 rows visible |
| 6 | GET | `/api/v1/intake/workspaces/{id}/issues` | 200 | 2 issues visible |

No 401/403/500 across the full flow.

### 2.2 Workspace-Scoped API is the Correct Contract

The canonical contract is **workspace-scoped** (`/workspaces/{workspace_id}/...`).
U4-B established this as the single correct API shape. The intake_service uses
`workspace_id` as the lifecycle owner for uploads, mapping, validation, rows,
and issues.

### 2.3 U4-F-R3 404s Were WRONG_TEST_ROUTE (Not Product Defects)

U4-F-R3 reported two "remaining items" as 404s:

- `PUT /api/v1/intake/uploads/{id}/mapping` -> 404
- `GET /api/v1/intake/uploads/{id}/rows` -> empty

**Root cause**: WRONG_TEST_ROUTE. These tests used the **upload-scoped** path,
which is not the product contract. The correct paths are **workspace-scoped**:

- `PUT /api/v1/intake/workspaces/{workspace_id}/mapping` (works)
- `GET /api/v1/intake/workspaces/{workspace_id}/rows` (works)

U4-F-R4 proved both work correctly on the canonical paths. **This is NOT a
product defect** -- the upload-scoped routes do not exist and were never part
of the contract.

### 2.4 SKU Count Unchanged = Staging-Only Confirmed

| Table | R4 Count | Notes |
|-------|----------|-------|
| `intake_workspaces` | 7 | staging |
| `intake_uploads` | 5 | staging |
| `intake_product_rows` | 13 | staging |
| `intake_validation_issues` | 16 | staging |
| `skus` | **10 (unchanged)** | **official catalog untouched** |

All intake data lives in staging tables. The official `skus` table count was 10
before and 10 after the full create->upload->map->validate->rows->issues flow.
**No SKU writes occur.** Staging-only is confirmed.

---

## 3. Current Product Capability (Business Language)

As of U4-F-R4, the Data Intake module allows an **internal logged-in user**
(with `intake:create`/`intake:read`/`intake:update` permissions) to:

1. **Create an intake workspace** -- a named staging area for a batch of
   products to onboard.
2. **Upload a CSV or XLSX file** to that workspace. The parser reads headers and
   stages the rows.
3. **Map source columns** to canonical product fields (`sku_code`, `name`,
   `unit`, `category`, `unit_price`, `barcode`). The system records the mapping
   and marks the workspace as `MAPPED`.
4. **Run validation** -- the workspace transitions to `READY_FOR_EXPORT` (or
   `NEEDS_REVIEW` if errors/warnings exist).
5. **Preview staged rows** -- view the normalized rows that would be imported.
6. **Preview validation issues** -- view errors and warnings per row.

**The user CANNOT yet write to the official SKU table.** Intake is a read-only
staging sandbox. No `apply`/`import` step exists.

---

## 4. Explicit Boundaries (What Is NOT Done)

The following are **not** in scope or not yet implemented:

- **No import/apply to official SKU table** -- the staging -> production
  promotion step does not exist. This is the primary gap (see Section 5).
- **No row editing UI** -- staged rows cannot be edited in the browser; the
  user must fix the source file and re-upload.
- **No mobile scan / PWA** -- intake is desktop-browser only; no camera/scan
  capture flow.
- **No image upload/import** -- only CSV and XLSX are parsed. No OCR or image
  ingestion.
- **No public token / external onboarding link** -- intake requires a full
  internal login with JWT. No shareable public link for external contributors.
- **No multilingual UI** -- the interface is English-only.
- **No WhatsApp / agent CLI execution** -- no chatbot or CLI integration for
  intake operations.

---

## 5. Next-Slice Options

### Option 1 -- U4-H: Mobile Scan / PWA Minimal Slice

| Dimension | Detail |
|-----------|--------|
| **User value** | Field agents can scan product barcodes / capture shelf photos and add to an intake workspace from a phone, removing the desktop-only bottleneck. |
| **Scope** | PWA manifest + service worker; camera capture flow; barcode scan -> prefill row; attach to existing workspace. |
| **Non-scope** | Image OCR/parsing (out of MVP); offline queue sync (post-MVP); full row editing. |
| **Data model impact** | Minimal -- reuses existing `IntakeWorkspace`/`IntakeUpload`. May add `source_type='scan'`. |
| **Validation gates** | PWA install test; camera permission flow; scan -> workspace attach E2E; no SKU writes. |
| **Risk level** | MEDIUM -- browser camera APIs vary by device; PWA caching correctness. |
| **STOP conditions** | If camera API cannot reliably scan barcodes on >30% of target devices; if offline conflict with staging invariants. |

### Option 2 -- U4-I: Intake Apply to SKU with Approval Gate

| Dimension | Detail |
|-----------|--------|
| **User value** | Closes the loop: staged intake rows become official SKUs after a human approval step. This is the **#1 missing capability** -- without it, intake is a sandbox that never produces catalog changes. |
| **Scope** | `POST /workspaces/{id}/apply` endpoint (writes to `skus`); approval gate (workspace `OPEN` -> `APPROVED` -> `APPLIED`); RBAC `intake:import_to_erp` + `intake:approve`; atomic apply with rollback; duplicate-SKU detection. |
| **Non-scope** | Row-level approval (workspace-level only for MVP); partial apply; conflict resolution UI (report-only for MVP). |
| **Data model impact** | Adds `APPLIED`/`APPROVED` workspace status transitions; writes to existing `skus` table (no new tables); may add `applied_by`/`applied_at` on workspace (already in model). |
| **Validation gates** | Apply E2E with staging -> official write; SKU count changes by exactly N; rollback on partial failure; idempotency; ledger entry for SKU creation. |
| **Risk level** | HIGH -- first code path that mutates the official catalog from intake. Requires strong atomicity + approval gate + duplicate guards. |
| **STOP conditions** | If any apply leaves orphaned/partial rows; if duplicate SKU codes can be created; if approval gate can be bypassed. |

### Option 3 -- U5-A: Multilingual MVP Foundation

| Dimension | Detail |
|-----------|--------|
| **User value** | Users can switch the UI language (English/Swahili), broadening accessibility for non-English-speaking staff and retailers. |
| **Scope** | i18n library integration; extract all user-facing strings; English + Swahili translation files; language switcher in settings; persist preference. |
| **Non-scope** | RTL layout (no RTL languages in MVP); backend message localization; dynamic language loading. |
| **Data model impact** | None (UI-only). |
| **Validation gates** | No untranslated strings in primary views; language switch persists across reload; no layout breakage. |
| **Risk level** | LOW -- purely additive UI work, no data/logic changes. |
| **STOP conditions** | If string extraction misses >5% of primary-view strings; if Swahili translations are incomplete/unverified by a native speaker. |

---

## 6. CTO Recommendation

### Recommendation: **U4-I (Intake Apply to SKU with Approval Gate) FIRST**

**Rationale** (ranked by weight):

1. **Real user pain**: The Data Intake module currently lets users stage
   products but **cannot produce a single SKU**. A feature that lets users do
   everything except the final commit is the most frustrating possible state.
   Closing this loop is the highest-value, highest-urgency next step.

2. **MVP usability**: Without `apply`, intake is a demo, not a product. With
   `apply` + approval gate, intake becomes a usable onboarding workflow that
   delivers measurable business value (faster catalog setup, fewer manual
   entry errors).

3. **Dependency ordering**: U4-H (mobile scan) and U5-A (i18n) are both
   additive UX improvements that **depend on the apply step being valuable**.
   Scanning products into a sandbox that never writes to the catalog is low
   value. Multilingual UI on a non-functional feature is low value. Doing U4-I
   first makes both subsequent slices more meaningful.

4. **Risk is manageable**: The HIGH risk is mitigated by the existing
   atomic-transaction infrastructure (proven in S5-D4B for payments) and the
   approval gate (workspace must be `APPROVED` before `apply`). The STOP
   conditions are well-defined and testable.

**Order**: **U4-I -> U4-H -> U5-A**. U4-I closes the core loop; U4-H adds the
mobile capture channel once the loop works; U5-A broadens language reach once
the product is functionally complete.

---

## 7. Harness Requirements (Next-Slice AI Team Execution)

For U4-I (and subsequent slices), the executing agent MUST adhere to:

| Requirement | Detail |
|-------------|--------|
| **Isolated branch** | `opencode/u4i-...` or `codebuddy/u4i-...` from latest `origin/product-dev-recovered`. Never commit to `product-dev-recovered`. |
| **GitNexus** | Run `gitnexus analyze` if index is stale; run `gitnexus impact` on every symbol before edit; run `gitnexus detect_changes` before commit. |
| **No `product-dev-recovered` push** | Push isolated branch only. Use `git push -u origin HEAD:refs/heads/<branch>` for first publication. |
| **No deploy unless explicitly requested** | Local test/commit only. Deploy requires explicit CTO instruction. |
| **Required tests** | Unit tests for the new apply/approve logic; integration test for staging -> official write; rollback test for partial failure; duplicate-SKU guard test. |
| **Required runtime proof** | If the apply flow touches a deployed path, a full runtime proof on the VPS is required: workspace create -> upload -> map -> validate -> approve -> apply -> verify SKU count increased by exactly N -> verify ledger entry exists. |
| **No secrets in report** | Ledger reports must not contain passwords, tokens, or connection strings. Use redacted placeholders. |
| **Atomicity** | Apply must be a single transaction: either all N rows write to `skus` or none do. No partial applies. |

---

## 8. Quality Gates (This Report)

| Check | Status |
|-------|--------|
| `git diff --check` | PASS |
| ASCII / mojibake scan on report | PASS |
| Secret scan on report | PASS (no credentials, only SHAs and host IP from public ledger) |
| Only report file added (no code changes) | PASS |

---

## 9. Verdict

```
PASS_FOR_CTO_U4G_REVIEW
```

The U4 Data Intake phase (U4-A through U4-F) is closed out with runtime truth
established (6/6 endpoints pass, staging-only confirmed, SKU catalog untouched).
The primary gap (no apply step) is identified, and U4-I is recommended as the
next slice to close the core loop.
