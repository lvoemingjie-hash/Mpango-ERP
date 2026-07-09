# G3-R3 Final Pre-G4 Validation After G3-R2 + P25-EG

## Metadata

| Field | Value |
|-------|-------|
| Task ID | G3-R3 |
| Date | 2026-07-09 |
| Branch | `codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08` |
| Worktree | `_mergeresolve_g2_2026-07-08` |
| Tip SHA | `6b1a7616c8d8eb484d0116c6bab23a2fe1573a36` |
| Base | `origin/product-dev-recovered` = `19f6afde` |
| Protected `origin/platform-dev` | `12c5ee55` (unchanged) |
| Protected `origin/product-dev-recovered` | `19f6afde` (unchanged) |
| Prior commits on branch | G3-R2 `040e6e0a`, P25-EG `6b1a7616` |

## Base Proof Gate

- `git rev-parse HEAD` = `6b1a7616` (P25-EG tip) ✓
- `git rev-parse origin/product-dev-recovered` = `19f6afde` ✓
- HEAD != base (expected — rehearsal branch has 2 feature commits)
- `git status --short`: no staged/modified source files; only smoke evidence (screenshots/JSON) and temp output ✓

## 1. Backend Regression (235 passed, 0 failed)

| Suite | Count | Status |
|-------|-------|--------|
| P10 contracts (incl. G3-R2 + P25-EG tests) | 173 | PASS |
| Route auth policy (D-class G2-R2) | 34 | PASS |
| P11c0 legacy guard (D-class G2-R2) | 24 | PASS |
| S6E RBAC drift gate (D-class G2-R2) | 4 | PASS |
| **Total** | **235** | **0 failed** |

Command: `python -m pytest backend/tests/test_platform_p10_contracts.py backend/tests/test_route_auth_policy.py backend/tests/test_p11c0_legacy_guard.py backend/tests/test_s6e_rbac_drift_gate.py -v`

## 2. Alembic / Database

| Check | Result |
|-------|--------|
| `alembic heads` | Single head: `030_platform_backup_status_source` ✓ |
| `alembic current` | `030_platform_backup_status_source (head)` ✓ |
| `alembic upgrade head` | Clean (no errors, already at head) ✓ |

DB: `postgresql://mpango:p25ec_throwaway_pw@localhost:5433/mpango_erp` (port 5433, disposable smoke stack)

## 3. Real-Stack Platform Smoke

### Identity Smoke: 6/6 PASS

| Case | Expected | Actual | Status |
|------|----------|--------|--------|
| operator_admit | 200 | 200 | PASS |
| test_override_reject | 403 | 403 | PASS |
| identity_super_admin_admit | 200 | 200 | PASS |
| no_credentials_deny | 401 | 401 | PASS |
| wrong_operator_deny | 403 | 403 | PASS |
| **tenant_context_admin_deny** | **401/403** | **401** | **PASS (G3-R2 verified)** |

G3-R2 real-stack confirmation: `tenant_context_admin_deny` returns clean 401 with body `{"code":"TENANT_CONTEXT_UNRESOLVABLE","message":"Tenant context referenced by token is not available"}`. No 500. ✓

### Route Smoke: 19/19 HTTP 200

| Metric | Value |
|--------|-------|
| Total routes | 19 |
| HTTP 200 | 19 |
| Redirected | 0 |
| Routes with console errors | 2 (Tenant Health 404s, Registry 500) |
| Routes with 5xx | 1 (Registry) |
| Routes with forbidden controls | 0 |
| Screenshots captured | 19/19 |

**G3-R2 + P25-EG specific checks:**

| Check | Result |
|-------|--------|
| `/platform/tenants` (P10 tenant list) — no 500 on legacy UUID | HTTP 200, 0 errors ✓ (P25-EG verified) |
| `tenant_context_admin_deny` — 401 not 500 | 401 ✓ (G3-R2 verified) |
| `/platform/audit` — stays 200 | HTTP 200, 0 errors ✓ |

### Log Grep

| Metric | Value |
|--------|-------|
| TenantContextMissingError occurrences | 0 ✓ |
| HTTP 500 / ERROR lines | 2 (both P17 registry) |
| Traceback lines | 66 |

500 samples:
```
GET /api/v1/platform/p17/registry?limit=50&offset=0 → 500
```

### Registry 500 Root Cause

```
backend/api/v1/platform/p17/services.py:627 → PlatformTenantRegistry(tenant_id=str(w.id))
→ pydantic_core.ValidationError: tenant_id
  Value error, UUID must be version 4 or 7, got: 11111111-1111-1111-1111-111111111111
```

Root cause: `p17/schemas.py:380` — `PlatformTenantRegistry._validate_tenant_id = field_validator("tenant_id")(validate_uuid_v4_v7)` — same strict UUID validator as P25-EG bug class, on a different DTO.

**Pre-existing confirmation:** P25-EE baseline smoke (`verify/p25ee/smoke_result.json`) also had `routes_with_5xx: 1`. G3-R2 and P25-EG did NOT modify `p17/schemas.py` (git diff confirms).

## 4. Frontend

| Check | Result |
|-------|--------|
| Production build (`pnpm build`) | PASS — `✓ built in 8.47s`, 1269 modules transformed |
| Vitest suite (`npx vitest run`) | PASS — 9 files, 81 tests, all passed |

Frontend tests include: permissions (19), SKUListPage (8), MobileScanPreview (10), InventoryAdjustModal (3), TenantListPage (2), SKUImportE2E (7), SKUImportModal (15), S5BRealUserSmoke (1), DataIntakePage (16).

## 5. Product Smoke

| Component | Result |
|-----------|--------|
| InventoryAdjustModal.test.tsx | 3 tests PASS ✓ |
| S5BRealUserSmoke.test.tsx | 1 test PASS ✓ |
| (InventoryPage / OrderListPage) | Covered within S5BRealUserSmoke ✓ |

No product smoke regression. All product-component tests pass.

## 6. Failure Classification (A/B/C/D)

| Class | Count | Details |
|-------|-------|---------|
| **A** (merge-introduced) | **0** | No new issues introduced by G3-R2 or P25-EG |
| **B** (pre-existing) | **1** | P17 Registry 500 — `PlatformTenantRegistry` strict UUID v4/v7 validator on legacy UUID `11111111-1111-1111-1111-111111111111`. Same bug class as P25-EG. Pre-existing in baseline. NOT modified by G3-R2 or P25-EG. |
| **C** (environment/infra) | **0** | — |
| **D** (critical/blocking) | **0** | G3-R2 and P25-EG fixes verified working in real stack. No merge regressions. |

## 7. Scope Diff Gate

```
git diff --name-status origin/product-dev-recovered..HEAD
```

Source code changes (from G3-R2 + P25-EG only):
- `backend/api/context/tenant.py` (G3-R2)
- `backend/api/v1/platform/p10/schemas.py` (P25-EG)
- `backend/tests/test_platform_p10_contracts.py` (both)

No scope-creep: no migration/alembic changes, no backend deployment drift, no lockfile changes, no product business logic changes.

## 8. Verdict

### STOP_AND_REPORT_CTO

**Rationale:** The verdict rule explicitly lists "backend 5xx" as a STOP condition. There is 1 pre-existing backend 5xx on `/api/v1/platform/p17/registry` (Class B). While D=0 and no merge regression occurred, the strict verdict rule is triggered by the backend 5xx condition.

### Key findings supporting GO conditional on CTO override:

1. **G3-R2 verified in real stack**: `tenant_context_admin_deny` → 401 (not 500) ✓
2. **P25-EG verified in real stack**: Tenant Directory `/platform/tenants` → HTTP 200, 0 errors ✓
3. **D=0**: No new critical issues from the merge
4. **No merge regression**: 5xx count unchanged from P25-EE baseline (still 1)
5. **All backend tests pass**: 235/235
6. **Alembic single head**: `030_platform_backup_status_source`
7. **Frontend build + tests pass**: 81/81
8. **Product smoke pass**: InventoryAdjustModal + S5BRealUserSmoke
9. **Protected branches unchanged**

### Recommended follow-up: P25-EH

Apply the same lenient UUID validator (`validate_uuid_any_version`) to `PlatformTenantRegistry._validate_tenant_id` in `p17/schemas.py:380`. This is the same fix pattern as P25-EG, just applied to a different DTO that has the identical bug. Scope: `backend/api/v1/platform/p17/schemas.py` + tests.

## Evidence Files

- Smoke result: `verify/p25ef/smoke_result.json`
- Backend log: `verify/p25ef/backend_stdout.log`
- Screenshots: `verify/p25ef/screenshots/*.png` (19 files)
