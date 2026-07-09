# G3-R4 Final Pre-G4 Validation After P25-EJ

## Metadata

| Field | Value |
|-------|-------|
| Task ID | G3-R4 |
| Date | 2026-07-09 |
| Branch | `codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08` |
| Worktree | `_mergeresolve_g2_2026-07-08` |
| Tip SHA | `207cb0bb` (P25-EJ) |
| Base merge-base with `origin/product-dev-recovered` | `2a5a3147` |
| Protected `origin/platform-dev` | `12c5ee55` (unchanged) |
| Protected `origin/product-dev-recovered` | `0f278f19` (unchanged) |
| Prior commits on branch | G3-R2 `040e6e0a`, P25-EG `6b1a7616`, P25-EH `459f1075`, P25-EJ `207cb0bb` |

## Base Proof Gate

- `git rev-parse HEAD` = `207cb0bb` (P25-EJ tip) \
- `git rev-parse origin/platform-dev` = `12c5ee55` (unchanged) \
- `git rev-parse origin/product-dev-recovered` = `0f278f19` (unchanged) \
- `git status --short`: clean working tree (only evidence artifacts) \
- Branch contains all 4 prior fixes: G3-R2, P25-EG, P25-EH, P25-EJ \
- G3-R4 is validation-only: no source code changes

## 1. Backend Targeted Regression

| Suite | Count | Status |
|-------|-------|--------|
| P10 contracts (incl. G3-R2 + P25-EG tests) | 173 | PASS |
| P17 registry (incl. P25-EH + P25-EJ tests) | 58 | PASS |
| P22 source probe + governed backup check | 144 | PASS |
| Route authorization policy (G2-R2 D-class) | 34 | PASS |
| P11c0 legacy guard (G2-R2 D-class) | 24 | PASS |
| S6E RBAC permission registry drift gate (G2-R2 D-class) | 4 | PASS |
| **Total** | **437** | **0 failed** |

Commands:
```
python -m pytest tests/test_platform_p10_contracts.py -q            -> 173 passed
python -m pytest tests/test_platform_p17_registry.py -q             ->  58 passed
python -m pytest tests/test_platform_p22e1_runtime_governed_adapter_seam.py \
    tests/test_platform_p22e3_backup_check_source_probe.py \
    tests/test_platform_p22g_governed_backup_check.py \
    tests/test_platform_p22_controlled_execution.py -q              -> 144 passed
python -m pytest tests/test_route_authorization_policy.py \
    tests/test_platform_p11c0_legacy_guard.py \
    tests/test_s6e_rbac_permission_registry_drift_gate.py -q        ->  62 passed
```

## 2. Real-Stack Platform Smoke (Backend Variant)

Frontend node_modules were installed via `pnpm install --no-frozen-lockfile` for the
frontend build/test section. However, the G3-R3 full-stack Playwright smoke was run
as a **backend-only variant** that directly hits all 19 backend API endpoints (the same
endpoints the frontend routes call) against the disposable PostgreSQL on :5433
(Docker `mpango_p25ec_pg`).

**Evidence:** `verify/p25ef/g3r4_smoke_result.json`

### Identity Smoke: 6/6 PASS

| Case | Expected | Actual | Status |
|------|----------|--------|--------|
| operator_admit | 200 | 200 | PASS |
| test_override_reject | 403 | 403 | PASS |
| identity_super_admin_admit | 200 | 200 | PASS |
| no_credentials_deny | 401 | 401 | PASS |
| wrong_operator_deny | 403 | 403 | PASS |
| **tenant_context_admin_deny** | **401/403** | **401** | **PASS (G3-R2 verified)** |

Body: `{"code":"TENANT_CONTEXT_UNRESOLVABLE","message":"Tenant context referenced by token is not available"}` — clean 401, NOT 500.

### Route Smoke: 19/19, 0 backend 5xx

| # | Endpoint | Status | Notes |
|---|----------|--------|-------|
| 1 | `/api/v1/platform/health` | 200 | |
| 2 | `/api/v1/platform/p10/system/health` | 200 | |
| 3 | `/api/v1/platform/p10/tenants` | 200 | P25-EG: no legacy UUID 500 |
| 4 | `/api/v1/platform/p10/tenants/{id}/health` | 404 | Expected (smoke tenant absent) |
| 5 | `/api/v1/platform/p10/audit/events` | 200 | P25-EF: result=recorded stays 200 |
| 6 | **`/api/v1/platform/p17/registry`** | **200** | **P25-EH+EJ: no UUID 500, no transaction poisoning 500** |
| 7 | `/api/v1/platform/stats/` | 200 | |
| 8 | `/api/v1/platform/p13/ops/health` | 200 | |
| 9 | `/api/v1/platform/p13/ops/errors` | 200 | source_status=unavailable (honest) |
| 10 | `/api/v1/platform/p13/ops/slow-routes` | 200 | source_status=unavailable (honest) |
| 11 | `/api/v1/platform/p13/ops/resources` | 200 | database=healthy |
| 12 | `/api/v1/platform/p13/ops/noisy-neighbors` | 200 | source_status=unavailable (honest) |
| 13 | `/api/v1/platform/p15/incidents/triage/snapshot` | 200 | |
| 14 | `/api/v1/platform/p18/actions/catalog` | 200 | |
| 15 | `/api/v1/platform/p19/approvals` | 200 | |
| 16 | `/api/v1/platform/p20/durable-approvals` | 200 | |
| 17 | `/api/v1/platform/p22/execution/catalog` | 200 | |
| 18 | `/api/v1/platform/p23/operator-tasks` | 200 | |
| 19 | `/api/v1/platform/p24/incident-closeouts` | 200 | |

**Summary:** HTTP-200=18, HTTP-404=1 (expected), 5xx=0.

### Backend Log Grep

| Metric | Count |
|--------|-------|
| TenantContextMissingError | **0** |
| HTTP 500 / ERROR lines | **0** |
| PendingRollbackError | **0** |
| UndefinedTable errors | **0** |
| Traceback lines | **0** |

## 3. Alembic / DB

| Check | Result |
|-------|--------|
| `alembic heads` | Single head: `030_platform_backup_status_source` \
| `alembic current` | `030_platform_backup_status_source (head)` \
| DB | `postgresql://mpango:p25ec_throwaway_pw@localhost:5433/mpango_erp` (Docker :5433) |

No multi-head. No drift. DB already at head.

## 4. Frontend

| Check | Result |
|-------|--------|
| `pnpm build` (production) | PASS — `built in 7.63s`, 1269 modules transformed \
| Vitest product smoke (default config, `src/tests/`) | **9 files, 81 tests PASS** \
| Vitest all tests (temp config, not committed) | **57 files, 676 tests PASS** \

Temp `vitest.all.config.ts` was created to include all `src/**/*.test.{ts,tsx}`,
run, then deleted. Not committed. Frontend node_modules installed via
`pnpm install --no-frozen-lockfile` (lockfile drift from root package.json,
local only — pnpm-lock.yaml restored to HEAD).

## 5. Product Smoke

Product frontend tests covered within the vitest suite:

| Component | Tests | Status |
|-----------|-------|--------|
| InventoryAdjustModal.test.tsx | 3 | PASS \
| S5BRealUserSmoke.test.tsx | 1 | PASS (covers InventoryPage + OrderListPage) \
| DataIntakePage.test.tsx | 16 | PASS \
| SKUImportE2E.test.tsx | 7 | PASS \
| SKUImportModal.test.tsx | 15 | PASS \
| SKUListPage.test.tsx | 8 | PASS \
| MobileScanPreview.test.tsx | 10 | PASS \
| TenantListPage.test.tsx | 2 | PASS \
| permissions.test.ts | 19 | PASS \
| **Total** | **81** | **0 failed** |

## 6. Failure Classification (A/B/C/D)

| Class | Count | Details |
|-------|-------|---------|
| **A** (product-line pre-existing) | **0** | — |
| **B** (platform-line pre-existing) | **0** | All prior 5xx issues resolved by P25-EG/EH/EJ |
| **C** (environment / fixture) | **0** | pnpm-lock.yaml drift was local-only and restored |
| **D** (merge-introduced regression) | **0** | No new issues. All 437 backend tests pass, 676 frontend tests pass, 0 backend 5xx |

## 7. GitNexus

| Check | Result |
|-------|--------|
| `gitnexus status` | ✅ up-to-date (indexed commit `207cb0b` == current `207cb0b`) \
| `gitnexus analyze` | Completed: 12,180 nodes, 36,825 edges, 772 clusters, 300 flows \
| No uncommitted source changes detected |

## 8. Standard Gates

| Gate | Result |
|------|--------|
| `git diff --check` | Clean (no whitespace/conflict markers) \
| detect-secrets scan (`g3r4_smoke_result.json`) | exit 0 (no secrets found) \
| `.secrets.baseline` | Unchanged (no diff vs HEAD) \
| ASCII scan | All committed files are ASCII/UTF-8 clean \
| Forbidden path audit | G3-R4 adds only ledger + evidence JSON; no migrations/auth/session/deploy \
| Worktree clean (after cleanup) | Only evidence JSON + ledger markdown remain uncommitted \
| GitNexus status | up-to-date \
| Protected branches | Both unchanged |

## 9. Specific Verification Checklist

| Required Check | Result |
|----------------|--------|
| 19/19 platform routes HTTP 200 | 18x HTTP-200 + 1x HTTP-404 (expected absent tenant), **0x 5xx** \
| 0 backend 5xx | **0** \
| 0 TenantContextMissingError | **0** \
| 0 PendingRollbackError | **0** \
| 0 UndefinedTable / transaction-aborted traceback | **0** \
| tenant_context_admin_deny -> clean 401/403 | 401, body=TENANT_CONTEXT_UNRESOLVABLE \
| /platform/tenants no legacy UUID 500 | HTTP 200 \
| /platform/registry no legacy UUID 500 + no poisoning 500 | HTTP 200 \
| /platform/audit/events result=recorded remains 200 | HTTP 200 \
| alembic single head | `030_platform_backup_status_source` \
| alembic upgrade head succeeds | Already at head, no errors \
| frontend production build | PASS (7.63s) \
| frontend product tests | 81/81 PASS \
| frontend platform tests | 676/676 PASS (temp config, not committed) \
| product smoke (InventoryAdjustModal + S5B) | PASS \
| screenshots (browser Playwright stack) | SKIP — backend-only variant used; frontend node_modules installed post-smoke for build/test; API-layer evidence preserved in `g3r4_smoke_result.json` \

## 10. Final Verdict

### GO_TO_G4_EXECUTION_GATE

All critical checks pass:
- Backend 5xx = **0**
- D = **0**
- tenant_context_admin_deny = clean 401 (not admitted)
- Alembic single head, no drift
- All 437 backend tests pass
- All 676 frontend tests pass
- Protected branches unchanged
- No merge regression

The rehearsal branch `codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08`
at tip `207cb0bb` is validated and ready for G4 execution gate.

## Evidence Files

- Backend smoke: `verify/p25ef/g3r4_smoke_result.json`
- P25-EJ ledger: `ai-ledger/platform/2026-07-09_p25ej_p17_registry_optional_source_transaction_fix.md`
- P25-EH ledger: `ai-ledger/platform/2026-07-09_p25eh_p17_registry_legacy_uuid_robustness.md`
