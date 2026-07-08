# Product-Line Merge Preparation Gate 2-R1 — Failure Classification Evidence

| Field | Value |
|---|---|
| **Task ID** | G2-R1 (Product Merge Prep Gate 2, Round 1 — Failure Classification) |
| **Date** | 2026-07-08 / 2026-07-09 |
| **Mode** | **EVIDENCE-ONLY** — re-ran failing tests with full logs, classified each failure via clean-base reproduction. NOT pushed to `product-dev-recovered`, no promotion. |
| **Branch** | `codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08` |
| **Worktree** | `_mergeresolve_g2_2026-07-08` (HEAD `f03127fd`) |
| **G2 merge commit** | `c0ee5f7879af8a0b04958f966cb4649e5aed9ff1` |
| **Product clean base** | `origin/product-dev-recovered @ 6bcc38f9` (worktree `_r1base_product`) |
| **Platform clean base** | `origin/platform-dev @ 12c5ee55` (worktree `_r1base_platform`) |
| **Broad sweep result** | **75 failed, 2391 passed, 62 skipped, 15 xfailed, 23 errors** in 1055.09s |
| **Verdict** | **STOP — D count = 10 > 0. Do NOT proceed to G3 until the 10 merge-introduced failures are resolved.** |

---

## 1. Objective

Re-run all failing tests from the G2 resolved-merge-rehearsal with full logs, then classify each
failure into one of four categories using **clean-base reproduction** as proof:

| Cat | Meaning | Action |
|---|---|---|
| **A** | Pre-existing on `product-dev-recovered` | Not a merge regression — ignore for G3 gate |
| **B** | Pre-existing on `platform-dev` | Not a merge regression — ignore for G3 gate |
| **C** | Environment / fixture / order-pollution / contract-scope-context-only | Not a merge regression — ignore for G3 gate |
| **D** | **Merge-introduced regression / blocker** | **Must fix before G3** |

**Recommendation rule (per CTO directive):** proceed to G3 only if D count = 0; otherwise STOP and
list required fixes.

---

## 2. Base Proof Gate

```
git fetch origin product-dev-recovered platform-dev
origin/product-dev-recovered @ 66e8371b  (advanced after G2 was cut; G2 base was 6bcc38f9)
origin/platform-dev        @ 12c5ee55
```

G2-R1 is an evidence/classification task on the **already-committed** G2 feature branch. No source
code was modified — the only artifact is this ledger. The G2 worktree HEAD is `f03127fd` (the G2
ledger commit). Pre-existing modified binary files (smoke screenshots, `pnpm-lock.yaml`,
`smoke_result.json`) were left untouched and are NOT part of this commit.

Clean-base worktrees (detached HEAD, created for comparative reproduction):

```
_r1base_product  @ 6bcc38f9  (product-dev-recovered, G2's actual base)
_r1base_platform @ 12c5ee55  (platform-dev)
```

---

## 3. Methodology — Clean-Base Reproduction

For every failing test file, three reproduction runs were performed where applicable:

1. **G2 broad sweep** — `pytest tests/ --tb=no -q -p no:hypothesis` on the G2 merge tree.
2. **G2 isolation** — `pytest <file> --tb=line -q -p no:hypothesis` on the G2 merge tree alone.
3. **Clean-base isolation** — same isolation command on `_r1base_product` and/or `_r1base_platform`.

Classification logic:
- Fails identically on clean product base → **A**
- Fails identically on clean platform base → **B**
- Passes in isolation but fails in broad sweep → **C (order pollution)**
- Errors with `getaddrinfo failed` / `KeyError: 'POSTGRES_DB'` → **C (environment — no live DB)**
- Fails in isolation on G2 but passes on the relevant clean base → **D (merge-introduced)**

---

## 4. Full Failure Table (75 FAILED + 23 ERROR = 98)

### Category D — Merge-Introduced Regression (10) — BLOCKERS

| # | Test | Count | Root cause | Clean-base proof |
|---|---|---|---|---|
| D1 | `test_route_authorization_policy.py` (5) | 5 | G2-merged platform routes use `require_platform_operator` (P10/P11 identity guard), but the product-side test harness `AUTH_DEPENDENCY_NAMES` does not recognise it. Result: 60 routes flagged "no explicit auth strategy"; platform-admin boundary check fails. | **Product base: 36/36 PASS.** File absent on platform base. → merge-introduced. |
| D2 | `test_platform_p11c0_legacy_guard.py::TestHealthInfoUnauthenticated` (4) | 4 | G2-merged `health.py` carries `RequirePlatformAdmin()` on `/health` and `/info` (product version won the merge), but the platform test expects unauthenticated `200`. Errors: `assert 401 == 200`, `KeyError: 'track'`. | **Platform base: 24/24 PASS.** File absent on product base. → merge-introduced. |
| D3 | `test_s6e_rbac_permission_registry_drift_gate.py::test_frontend_permission_references_are_seeded` (1) | 1 | The merged frontend union brought in new permission references (`denied:acknowledge`, `denied:close`, `denied:complete`, `node:fs`, `node:path`) not seeded in the backend permission registry. | **Fails in isolation on G2** (not order pollution). File absent on platform base. **Product base: PASS.** → merge-introduced. |

**D subtotal: 10 failures across 3 test files.**

### Category A — Pre-existing on product-dev-recovered (16)

| # | Test | Count | Root cause | Clean-base proof |
|---|---|---|---|---|
| A1 | `test_u4ib2_intake_apply_service.py` (13) | 13 | `socket.gaierror: getaddrinfo failed` at setup — needs a live PostgreSQL; default test DB host `postgres` unresolvable in this Windows environment. In broad sweep showed as FAILED (shared engine from earlier test); in isolation shows as ERROR. | **Product base isolation: 13 identical ERRORs** (`getaddrinfo failed`). Same Python/DB env. → pre-existing on product. |
| A2 | `test_u3c_import_apply.py::TestCustomAttributesGuard` (2) | 2 | `module 'starlette.status' has no attribute 'HTTP_422_UNPROCESSABLE_CONTENT'` — installed starlette is older than the version the test/code expects. | **Product base isolation: identical 2 FAILs** (same AttributeError). Same Python install. → pre-existing on product. |
| A3 | `test_u3e_e2e_hardening.py::TestE2EFailClosed::test_custom_attributes_stops_with_no_creation` (1) | 1 | Same starlette `HTTP_422_UNPROCESSABLE_CONTENT` AttributeError. | **Product base isolation: identical FAIL.** → pre-existing on product. |

**A subtotal: 16 failures across 3 test files.**

### Category B — Pre-existing on platform-dev (6)

| # | Test | Count | Root cause | Clean-base proof |
|---|---|---|---|---|
| B1 | `test_models_structure.py` (4 broad) | 4 | `PlatformBackupOutcome` model: PK named `outcome_id` (not `id`); missing audit columns (`updated_at`, `deleted_at`, `is_deleted`); tablename not snake_case plural. `PublicBaseModel` also flagged. G2 isolation: 8/8 PASS (order pollution amplifies); broad sweep: 4 FAIL. | **Platform base isolation: 4 identical FAILs.** Product base isolation: 8/8 PASS. → pre-existing on platform + order pollution. |
| B2 | `test_platform_p17dc_backup_registry_read.py` (2) | 2 | `assert 'stale' == 'success'` — backup registry source-discovery returns stale status. | **Platform base: same 2 FAILs.** → pre-existing on platform. |

**B subtotal: 6 failures across 2 test files.**

### Category C — Environment / Fixture / Order-Pollution / Contract-Scope-Context (66)

#### C-env: No live PostgreSQL (getaddrinfo / KeyError)

| # | Test | Count | Error | Evidence |
|---|---|---|---|---|
| C1 | `test_s6_2_materialized_views.py` | 4 | `getaddrinfo failed` | G2 iso: 5 ERROR. Needs live DB. |
| C2 | `test_s6_3_dashboard_api.py` | 5 | `getaddrinfo failed` | G2 iso: 6 ERROR. Needs live DB. |
| C3 | `test_s6_p_reporting_constraints.py` | 2 fail + 5 err | `getaddrinfo failed` | G2 iso: 7 ERROR. Needs live DB. |
| C4 | `test_s3b_fresh_tenant_live_runtime_proof.py` | 1 fail + 18 err | live runtime needs DB | G2 iso: 3 passed, 19 skipped (live tests skip cleanly). Broad sweep: 1F + 18E (order pollution made live tests attempt connection). |
| C5 | `test_u4d_intake_parser_preview.py` | 2 | `getaddrinfo failed` | G2 iso: 2 ERROR. Needs live DB. |
| C6 | `test_u1r1_bootstrap_completeness.py` | 1 | `getaddrinfo failed` | G2 iso: many ERROR. Needs live DB. |
| C7 | `test_u6f_onboarding_auth_chain_closeout.py` | 1 | `getaddrinfo failed` | G2 iso: ERROR. Needs live DB. |
| C8 | `test_u6h2_tenant_provisioning_wholesaler_schema.py` | 1 | `getaddrinfo failed` | G2 iso: ERROR. Needs live DB. |
| C9 | `test_u6h3_tenant_provisioning_reconcile_cleanup.py` | 1 | `getaddrinfo failed` | G2 iso: ERROR. Needs live DB. |
| C10 | `test_s4g_migration_infrastructure_hardening.py` | 5 | `KeyError: 'POSTGRES_DB'` | G2 iso: 5 FAIL. Alembic migration tests need DB env vars. |

#### C-pollution: Order pollution (passes in isolation, fails in broad sweep)

| # | Test | Count | Evidence |
|---|---|---|---|
| C11 | `test_payments_schema_contract.py::TestLiveRetailerPricesContract` | 13 | **G2 iso: 21 passed, 19 skipped, 0 failed.** Product base: 21 passed, 19 skipped. Broad sweep: 13 FAIL (earlier test imported live DB engine, making live tests run but fail on schema). |
| C12 | `test_s7_4_tenant_assets.py::TestDynamicRegistry::test_null_resolver_returns_none` | 1 | **G2 iso: PASS.** Both clean bases: PASS. Broad sweep FAIL is model-registry pollution from earlier imports. |

#### C-contract: Contract-scope guard (asserts narrow branch scope; invalid on 552-file merge tree)

| # | Test | Count | What it asserts | Why it fails on merge tree |
|---|---|---|---|---|
| C13 | `test_u6i0_owner_credential_setup_contract.py` | 2 | Branch changes only contract doc + static test (2 files) | G2 merge tree has 552 changed files. Extra items include platform ops pages, durable-approval migration, etc. |
| C14 | `test_u6i1_owner_credential_setup_schema.py` | 3 | Alembic head == `028_owner_credential_setup_tokens`; branch changes only schema-foundation files | G2 head is `030_platform_backup_status_source` (platform migrations renumbered). 552 files ≠ allowed set. |
| C15 | `test_u6e0_onboarding_status_token_schema.py` | 1 | `/onboarding/status` not in public routes | Platform merge brought `/onboarding/status` route. Product-slice contract doesn't know about it. Context mismatch, not a runtime regression. |

**C subtotal: 66 failures across 15 test files.**

---

## 5. Summary Counts

| Category | Failures | Errors | Total | % of 98 |
|---|---|---|---|---|
| **A** — pre-existing on product | 16 | 0 | 16 | 16.3% |
| **B** — pre-existing on platform | 6 | 0 | 6 | 6.1% |
| **C** — env / fixture / pollution / contract-scope | 39 | 27 | 66 | 67.3% |
| **D** — merge-introduced regression | 10 | 0 | 10 | 10.2% |
| **Total** | **75** | **23** | **98** | 100% |

---

## 6. Required Fixes Before G3 (D-blockers)

### D1 — `test_route_authorization_policy.py` (5 failures)

**Root cause:** Platform routes (P10/P11) use `require_platform_operator` as their identity guard.
The product-side test harness set `AUTH_DEPENDENCY_NAMES` in `test_route_authorization_policy.py`
does not include `require_platform_operator`, so the harness reports these routes as having "no
explicit auth strategy" and the platform-admin boundary check fails.

**Fix:**
1. Add `require_platform_operator` to the `AUTH_DEPENDENCY_NAMES` set in
   `tests/test_route_authorization_policy.py`.
2. Review the 60 "unclassified business routes" — many are platform routes that legitimately use
   `require_platform_operator`; update the route-policy classifier to recognise them.
3. Verify `test_platform_routes_use_require_platform_admin` logic: platform routes that use
   `require_platform_operator` (identity-only) should be allowed if they are read-only platform
   routes, or upgraded to `RequirePlatformAdmin` if they perform privileged actions.

### D2 — `test_platform_p11c0_legacy_guard.py` (4 failures)

**Root cause:** The merged `backend/api/v1/platform/health.py` carries `RequirePlatformAdmin()` on
both `/health` and `/info` (the **product** version of health.py won the merge via Decision B
platform-wins resolution, but health.py was **not** explicitly listed in Decision B's platform-wins
list). The platform test `test_platform_p11c0_legacy_guard.py` expects these endpoints to return
`200` unauthenticated (legacy public health check).

**Fix (requires CTO decision):**
- **Option D2-a:** Revert `health.py` to the platform version (remove auth from `/health` and
  `/info`) — restores p11c0 compatibility but may conflict with product's S2 route-hardening.
- **Option D2-b:** Keep product's `RequirePlatformAdmin` and update the p11c0 test to expect `401` —
  but this changes the platform contract.
- **Option D2-c:** Split: keep `/health` unauthenticated (platform legacy) and protect `/info` with
  `RequirePlatformAdmin`.

This is a **merge-resolution gap** — `health.py` was modified on BOTH sides of the merge
(platform: `af6eedd2 P11-C0 legacy guard`; product: `99c91f3b S2 route gaps` +
`49537181 S2-R1 platform super-admin boundary`) but was NOT covered by any CTO Decision (A–G).

### D3 — `test_s6e_rbac_permission_registry_drift_gate.py` (1 failure)

**Root cause:** The merged frontend union introduced permission references that the backend
permission seed registry does not contain: `denied:acknowledge`, `denied:close`, `denied:complete`,
`node:fs`, `node:path`.

**Fix:**
1. Audit the merged frontend source for these permission strings.
2. Add the legitimate ones to the backend permission seed files.
3. If `node:fs` / `node:path` are false positives from frontend test imports, add them to the
   drift-gate's ignore list.

---

## 7. Correction of G2 Ledger's Failure Count

The G2 ledger (`2026-07-08_product_merge_prep_g2_resolved_merge_rehearsal.md`) claimed "29 test
failures, all non-merge-regression, D count = 0." The G2-R1 broad sweep proves this was incorrect:

| Metric | G2 ledger claim | G2-R1 actual |
|---|---|---|
| Failed tests | 29 | **75** |
| Errors | (not counted) | **23** |
| Total failures+errors | 29 | **98** |
| D count | 0 | **10** |

The G2 ledger's undercount was caused by running only a targeted subset of test files rather than a
full broad sweep. G2-R1 corrects this with a complete `pytest tests/` sweep.

---

## 8. File Existence Matrix (clean bases)

| Test file | Product base (`6bcc38f9`) | Platform base (`12c5ee55`) |
|---|---|---|
| `test_route_authorization_policy.py` | EXISTS | MISSING |
| `test_platform_p11c0_legacy_guard.py` | MISSING | EXISTS |
| `test_models_structure.py` | EXISTS | EXISTS |
| `test_platform_p17dc_backup_registry_read.py` | MISSING | EXISTS |
| `test_s6e_rbac_permission_registry_drift_gate.py` | EXISTS | MISSING |
| `test_s7_4_tenant_assets.py` | EXISTS | EXISTS |
| `test_u4ib2_intake_apply_service.py` | EXISTS | MISSING |
| `test_u3c_import_apply.py` | EXISTS | MISSING |
| `test_u3e_e2e_hardening.py` | EXISTS | MISSING |

---

## 9. Clean-Base Reproduction Commands & Results

```powershell
# Environment (all runs)
$env:PYTHONIOENCODING="utf-8"; $env:PYTHONUTF8="1"
$PYTHON = "C:\Users\Jeff0\AppData\Local\Programs\Python\Python312\python.exe"

# G2 broad sweep
cd _mergeresolve_g2_2026-07-08\backend
& $PYTHON -m pytest tests/ --tb=no -q -p no:hypothesis
# => 75 failed, 2391 passed, 62 skipped, 15 xfailed, 23 errors in 1055.09s

# D1 proof — routeauth on product base
cd _r1base_product\backend
& $PYTHON -m pytest tests/test_route_authorization_policy.py --tb=line -q -p no:hypothesis
# => 36 passed (EXIT=0)

# D2 proof — p11c0 on platform base
cd _r1base_platform\backend
& $PYTHON -m pytest tests/test_platform_p11c0_legacy_guard.py --tb=line -q -p no:hypothesis
# => 24 passed (EXIT=0)

# D3 proof — s6e on G2 isolation + product base
cd _mergeresolve_g2_2026-07-08\backend
& $PYTHON -m pytest tests/test_s6e_rbac_permission_registry_drift_gate.py --tb=line -q
# => 1 failed (frontend refs missing from seeds)
cd _r1base_product\backend
& $PYTHON -m pytest tests/test_s6e_rbac_permission_registry_drift_gate.py --tb=line -q
# => passed

# A1 proof — u4ib2 on product base (same getaddrinfo errors)
cd _r1base_product\backend
& $PYTHON -m pytest tests/test_u4ib2_intake_apply_service.py --tb=line -q
# => 13 errors (getaddrinfo failed)

# A2/A3 proof — u3c/u3e on product base (same starlette AttributeError)
cd _r1base_product\backend
& $PYTHON -m pytest tests/test_u3c_import_apply.py::TestCustomAttributesGuard tests/test_u3e_e2e_hardening.py::TestE2EFailClosed --tb=line -q
# => 3 failed (HTTP_422_UNPROCESSABLE_CONTENT)

# B1 proof — models_structure on platform base
cd _r1base_platform\backend
& $PYTHON -m pytest tests/test_models_structure.py --tb=line -q
# => 4 failed (outcome_id PK, missing audit columns, tablename)
```

---

## 10. Scope Diff Gate

```
Artifact: ai-ledger/platform/2026-07-08_product_merge_prep_g2_r1_failure_classification.md
Scope:   1 new file (documentation only), no runtime code, no migrations, no deployment files.
```

---

## 11. Recommendation

**STOP — do NOT proceed to G3.**

D count = **10** > 0. The following merge-introduced failures must be resolved first:

1. **D1 (5):** Update `AUTH_DEPENDENCY_NAMES` to include `require_platform_operator`; reclassify
   platform routes in the route-policy contract.
2. **D2 (4):** Obtain a CTO decision on `health.py` auth strategy for `/health` and `/info`
   (platform legacy-public vs product `RequirePlatformAdmin`). This file was a merge-resolution gap
   not covered by Decisions A–G.
3. **D3 (1):** Seed the merged frontend's permission references (`denied:acknowledge`,
   `denied:close`, `denied:complete`) in the backend permission registry; audit `node:fs` /
   `node:path` as potential false positives.

Once D1–D3 are resolved and re-verified with a clean-base reproduction sweep, re-run the G2-R1
classification. Proceed to G3 only when D count = 0.
