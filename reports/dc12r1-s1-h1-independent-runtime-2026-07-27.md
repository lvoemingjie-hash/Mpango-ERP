# DC-12R1-S1-H1 Independent Verification Report (CORRECTED)
## Verification-Token Terminal-State Runtime Gate

**Date:** 2026-07-27
**Verifier:** `opencode` (subagent/session)
**Target:** `ac625b78850df3e6f078896a318770902b48a9f4`
**Base:** `c78101186f1fb4811a886e3e55f96708ea960c0a`
**Branch:** `opencode/dc12r1-s1-h1-verification-token-terminal-state-2026-07-27`

---

## Gate 1 — HEAD Match

| Check | Result |
|-------|--------|
| `git rev-parse HEAD` | `ac625b78850df3e6f078896a318770902b48a9f4` |
| `git rev-parse origin/opencode/dc12r1-s1-h1-verification-token-terminal-state-2026-07-27` | `ac625b78850df3e6f078896a318770902b48a9f4` |
| `git rev-parse origin/product-dev-recovered` | `c78101186f1fb4811a886e3e55f96708ea960c0a` |
| Working tree | Clean |
| **Verdict** | **PASS** — HEAD matches remote, base is correct, tree clean |

---

## Gate 2 — Change Set Boundaries

Three files differ between HEAD and base (candidate scope):

| File | Change |
|------|--------|
| `backend/services/onboarding_service.py` | +34/-8: `verify_email_token` — added `.where(EmailVerificationToken.is_deleted.is_(False))`, reorganized terminal-state guard ordering |
| `backend/tests/test_dc12r1_s1_h1_verification_token_terminal_state.py` | +350: new H1-dedicated test suite |
| `ai-ledger/product-ai/2026-07-27_dc12r1_s1_h1_verification_token_terminal_state.md` | +554: ai-ledger report documenting the change |

No migration, no model, no schema, no config, no frontend, no lockfile changed.

**Verdict: PASS** — change is isolated to one production function, one test file, and one ai-ledger report.

---

## Gate 3 — Commit Trail (Base to HEAD)

The actual product commit is `9420476bc4d6f8bc0803b339a8c4671d9202d4e2`, NOT the non-existent `9ba53cf`/`1d0e0c8` previously claimed. After the product commit, 5 docs-only commits follow.

| Commit | SHA | Message | Type |
|--------|-----|---------|------|
| **Product** | `9420476` | fix(onboarding): close verification token terminal-state boundary | **PRODUCTION CHANGE** |
| Docs | `a258e97` | add DC-12R1-S1-H1 verification token terminal-state report | ai-ledger |
| Docs | `24fd910` | R1 hygiene correction | ai-ledger |
| Docs | `feb6914` | record R1 push-proof SHAs | ai-ledger |
| Docs | `fa64055` | de-self-reference R1 final tip claim | ai-ledger |
| Docs | `ac625b7` | remove last stale 18c3a2c8 reference | ai-ledger |

**Verdict: CORRECTED** — `9420476` is the sole product commit. 5 docs-only commits follow. No product code committed after `9420476`.

---

## Gates 4–5 — Infrastructure

Run A container pair:
- **PG16:** `dc12r1-s1-h1-v1-runa-pg16` at `172.27.0.2` (db: `test_dc12r1_h1_a`)
- **Redis7:** `dc12r1-s1-h1-v1-runa-redis7` at `172.27.0.3`
- **Alembic head:** `036_retailer_mvp_identity`

Run B container pair:
- **PG16:** `dc12r1-s1-h1-v1-runb-pg16` at `172.28.0.2` (db: `test_dc12r1_h1_b`)
- **Redis7:** `dc12r1-s1-h1-v1-runb-redis7` at `172.28.0.3`
- **Alembic head:** `036_retailer_mvp_identity`

Both runs: reporting role, reporting user, materialized views all created successfully.

**Verdict: PASS** — two independent disposable infra pairs provisioned and migrated.

---

## Gates 6–9 — H1-Specific Tests

All 6 H1-dedicated tests pass on both Run A and Run B:

| Test | Status |
|------|--------|
| `test_soft_deleted_verification_token_is_rejected_neutrally_with_zero_mutation` | PASS |
| `test_terminal_token_skips_dependent_lookup_orchestration_and_writes[used]` | PASS |
| `test_terminal_token_skips_dependent_lookup_orchestration_and_writes[revoked]` | PASS |
| `test_terminal_token_skips_dependent_lookup_orchestration_and_writes[expired]` | PASS |
| `test_terminal_token_skips_dependent_lookup_orchestration_and_writes[soft_deleted]` | PASS |
| `test_valid_non_terminal_token_is_not_rejected_by_the_terminal_boundary` | PASS |

Terminal-state guard proofs:
- All terminal states (deleted/used/revoked/expired) → **400 INVALID_OR_EXPIRED_VERIFICATION_TOKEN** (neutral, single wording)
- Valid pending token → 200
- Terminal tokens never call `_is_retryable_setup_email_failure` or `complete_email_verified_onboarding`
- Zero mutation on terminal states (status, email_verified_at, tenant_schema, wholesaler_id, provisioning_completed_at, used_at, revoked_at all unchanged)
- Zero owner-setup-token rows created
- Zero owner-setup emails delivered

**Verdict: PASS** — all 6 tests pass, all terminal-state 400 proofs show neutral wording, zero-mutation and zero-orchestration assertions verified, valid-pending 200 path confirmed, retry-anchor passes.

---

## Gate 10 — Cross-File Regression

76 tests across 7 files, all passing on Run A:

| File | Tests | Result |
|------|-------|--------|
| `test_u6d_verify_email_endpoint.py` | 11 | PASS |
| `test_u6f_onboarding_auth_chain_closeout.py` | 7 | PASS |
| `test_u6l_email_verified_onboarding_orchestration.py` | 7 | PASS |
| `test_u6i6_onboarding_e2e_closeout.py` | 11 | PASS |
| `test_dc3b_auth_flow.py` | 11 | PASS |
| `test_auth_regressions.py` | 2 | PASS |
| `test_route_authorization_policy.py` | 27 | PASS |

**Verdict: PASS** — 76/76 cross-file regression tests passing.

---

## Gate 11 — Full Suite Run A

Results from disposable Run A infrastructure:

| Metric | Count |
|--------|-------|
| **Passed** | 2861 |
| **Skipped** | 29 |
| **xfailed (expected)** | 15 |
| **Failed** | 9 |
| **Errors** | 36 |

**45 red nodes — classification below:**

| Test File | Red Count | Root Cause |
|-----------|-----------|------------|
| `test_s4g_migration_infrastructure_hardening.py` | 5 FAIL | Temp-DB creation privileges on Docker IP |
| `test_u6i1_owner_credential_setup_schema.py` | 1 FAIL | **U6I1 CONTRACT GUARD** (see Gate 12) |
| `test_dc11t4c_reporting_bootstrap_contract.py` | 1 FAIL | `MPANGO_TEMP_DB_ALLOWED_PORTS` |
| `test_dc12r1_s1_r5_migration_preflight_exact_catalog.py` | 1 FAIL | Temp-DB host allowance |
| `test_uuid_serialization.py` | 1 FAIL | asyncpg timing sensitivity |
| `test_dc10e_export_worker_tenant_context.py` | 4 ERR | Reporting-role guard on Docker IP |
| `test_dc11t4h_receivable_collection_integrity.py` | 6 ERR | Temp-DB on Docker IP |
| `test_platform_p17dc_backup_migration.py` | 9 ERR | Temp-DB on Docker IP |
| `test_platform_p21_durable_approval_migration.py` | 6 ERR | Temp-DB on Docker IP |
| `test_s6_2_materialized_views.py` | 1 ERR | Reporting-role guard on Docker IP |
| `test_s6_3_dashboard_api.py` | 1 ERR | Reporting-role guard on Docker IP |
| `test_s6_p_reporting_constraints.py` | 7 ERR | Reporting-role guard on Docker IP |
| `test_u1r1_bootstrap_completeness.py` | 2 ERR | Seed data for sidebar routes |

---

## Gate 12 — Base Commit Reproduction (INCOMPLETE — 12/45 verified)

On base commit `c781011`:

| Test File | On HEAD | On BASE | Status |
|-----------|---------|---------|--------|
| `test_dc10e_export_worker_tenant_context.py` | 4 ERR | 4 ERR | ✅ Pre-existing |
| `test_s6_p_reporting_constraints.py` | 7 ERR | 7 ERR | ✅ Pre-existing |
| `test_s6_2_materialized_views.py` | 1 ERR | 1 ERR | ✅ Pre-existing |
| `test_u6i1_owner_credential_setup_schema.py` | 1 FAIL | **0 FAIL** | **STALE_TEST_CONTRACT** |

**Accounting gap: 33 of 45 red nodes were not reproduced on base.**
The following were NOT verified on base:
- `test_s4g_migration_infrastructure_hardening.py` (5 FAIL)
- `test_dc11t4c_reporting_bootstrap_contract.py` (1 FAIL)
- `test_dc12r1_s1_r5_migration_preflight_exact_catalog.py` (1 FAIL)
- `test_uuid_serialization.py` (1 FAIL)
- `test_dc11t4h_receivable_collection_integrity.py` (6 ERR)
- `test_platform_p17dc_backup_migration.py` (9 ERR)
- `test_platform_p21_durable_approval_migration.py` (6 ERR)
- `test_s6_3_dashboard_api.py` (1 ERR)
- `test_u1r1_bootstrap_completeness.py` (2 ERR)

While these are likely pre-existing infrastructure limitations, the report
cannot claim "ALL 45 red nodes reproduced on base" without executing them.

### U6I1 Contract-Guard Finding

`test_u6i1_owner_credential_setup_schema.py::test_no_route_service_frontend_or_user_rbac_behavior_changed`
passes on the base commit (0 failures) and fails on the candidate (1 failure).

This test asserts that `FORBIDDEN_RUNTIME_PATHS` — including
`backend/services/onboarding_service.py` — have not changed. The H1 change
intentionally modifies `onboarding_service.py`, so the test fails.

**This is a STALE_TEST_CONTRACT:** the test contract was written before the
H1 change and has not been updated to reflect the approved modification. The
test's FORBIDDEN_RUNTIME_PATHS set should be narrowed, or the test should be
aware that this specific change is pre-approved by DC-12R1-S1-H1.

This is NOT a product defect (the change is intentional) and NOT pre-existing
infrastructure (the test passes on base). It is a stale test contract that
needs correction.

**Verdict: STALE_TEST_CONTRACT — test contract must be updated to account
for the approved H1 change to onboarding_service.py.**

---

## Gate 13–14 — Run B (INCOMPLETE — subset only, not full suite)

Run B executed a selected subset of test files (457 test nodes), NOT the full
backend suite. Original Run A had 2861 passed + 29 skipped + 15 xfailed + 45 red
= ~2950 total nodes. Run B covered only 457 of these (~15%).

Results from Run B subset:

| Metric | Count |
|--------|-------|
| **Passed** | 445 |
| **Skipped** | 3 |
| **xfailed (expected)** | 5 |
| **Failed** | 2 |
| **Errors** | 2 |

**Verdict: INSUFFICIENT** — Run B subset (457 nodes, ~15% of full suite) cannot
substitute for a complete second run. The original report's claim of "Full Suite
Run B" was incorrect.

---

## Summary of Report Errors Corrected

| Original Claim | Correction |
|---------------|------------|
| **Verdict: PASS** | **Verdict: STOP_AND_REPORT_CTO** |
| Product commits are `9ba53cf`/`1d0e0c8` | Product commit is `9420476`; `9ba53cf`/`1d0e0c8` do not exist |
| Candidate scope is 2 files | Candidate scope is **3 files** (onboarding_service.py, tests, ai-ledger report) |
| Terminal states return distinct error codes | All terminal states return neutral `INVALID_OR_EXPIRED_VERIFICATION_TOKEN` |
| U6I1 failure = pre-existing infra | U6I1 failure = **STALE_TEST_CONTRACT** (passes base, fails candidate) |
| Base reproduction: "ALL 45 red nodes reproduced" | Base reproduction: **12/45 verified; 33 not reproduced** |
| Run B was full suite | Run B was **~15% subset (457 nodes)** |

---

## Final Verdict: STOP_AND_REPORT_CTO

| Criterion | Result |
|-----------|--------|
| HEAD matches remote | ✅ PASS |
| Working tree clean | ✅ PASS |
| Base confirmed | ✅ PASS |
| Candidate scope = 3 files | ✅ PASS |
| No migration/schema/config/frontend changes | ✅ PASS |
| H1-specific tests (6/6) | ✅ PASS |
| Terminal-state neutral 400 proofs (5/5) | ✅ PASS |
| Valid pending 200 path | ✅ PASS |
| Retry-anchor regression | ✅ PASS |
| Cross-file regression (76/76) | ✅ PASS |
| Full suite Run A (2861 pass, 45 red) | ✅ COMPLETED |
| Base reproduction (12/45 red) | ⚠️ INCOMPLETE (gap = 33) |
| Run B full-suite repeat | ❌ FAILED (subset only) |
| U6I1 contract guard | ❌ STALE_TEST_CONTRACT |
| **CURRENT_PRODUCT_DEFECT** | **NONE DETECTED** (no product code defect; these are process/reporting defects) |

### Required CTO Actions

1. **STALE_TEST_CONTRACT:** Update `test_u6i1_owner_credential_setup_schema.py` test contract — either narrow `FORBIDDEN_RUNTIME_PATHS` or add H1-awareness so the approved `onboarding_service.py` change does not break the guard.
2. **FULL SUITE RUN B:** Execute a complete second full-suite run on fresh infrastructure to close the Run B gap.
3. **BASE REPRODUCTION:** Verify the remaining 33 red nodes on the base commit to definitively rule out H1 causation.
4. **REPORT CORRECTION:** Document that all terminal states return the neutral `INVALID_OR_EXPIRED_VERIFICATION_TOKEN` (not distinct error codes per state) and that the candidate scope is 3 files including the ai-ledger report.
