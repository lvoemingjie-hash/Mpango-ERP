# DC-12R1-H3: Payment UI Permission Contract Repair

**Date:** 2026-07-31
**Branch:** `zcode/dc12r1-h3-payment-ui-permission-contract-2026-07-31`
**Product baseline:** `origin/product-dev-recovered` @ `0aec0f0b`

---

## 1. Defect Summary

The frontend "Record Payment" button in `OrderListPage.tsx` gated payment actions on `orders:update`, while the backend `POST /api/v1/orders/{order_id}/pay` requires `payments:create`. This caused:
- Users with `orders:update` but not `payments:create` to see the button, open the modal, submit, and receive a 403.
- Users with `payments:create` but not `orders:update` to be unable to see the button at all.

## 2. Root Cause

`OrderListPage.tsx:70` used a single `hasUpdatePermission` variable (checking `orders:update`) to gate both order-edit actions AND payment actions. The backend pay route (`orders.py:561`) requires `payments:create` — a different permission.

## 3. Changes Made

### 3.1 `frontend/src/pages/orders/OrderListPage.tsx`

| Line | Before | After |
|---|---|---|
| 70-71 | `hasUpdatePermission` = `orders:update` OR `roles.includes('admin')` | Split into `hasUpdatePermission` (orders:update) + `hasPayPermission` (payments:create) |
| 70-73 | Role-name shortcut `|| user?.roles.includes('admin')` | **Removed.** Permission set is sole source of truth. |
| 262, 268, 281, 287 | Collect deep-link used `hasUpdatePermission` | Changed to `hasPayPermission` |
| 300 | useEffect dep `hasUpdatePermission` | Changed to `hasPayPermission` |
| 440-441 | Record Payment button `disabled={!hasUpdatePermission}` | Changed to `disabled={!hasPayPermission}` |

**Genuine order-edit actions** (Confirm, Fulfill, Cancel, Return) remain gated by `hasUpdatePermission` (`orders:update`).

### 3.2 `frontend/src/tests/H3PaymentPermissionContract.test.tsx` (NEW)

6 test scenarios:
1. `payments:create` without `orders:update` CAN record payment (GREEN)
2. `orders:update` without `payments:create` CANNOT open/submit payment (RED)
3. Collect deep-link denied for user without `payments:create`
4. Collect deep-link opens modal for user with `payments:create`
5. Admin with `payments:create` in permission set can record payment
6. Admin role WITHOUT `payments:create` cannot record payment (proves no role-name shortcut)

## 4. Backend — No Changes

`POST /api/v1/orders/{order_id}/pay` remains protected by `payments:create` (`orders.py:561`). No weakening. Verified by `test_route_authorization_policy.py:904` (`TestOrderPaymentRoutePolicy`).

## 5. Validation Results

| Gate | Result |
|---|---|
| H3 focused tests | **6 passed** |
| Full vitest | **17 files, 154 passed** |
| TypeScript (`tsc --noEmit`) | **Clean** |
| `pnpm build` (`vite build`) | **Success** |
| Backend route-authorization + payment regressions | **39 passed** |
| `git diff --check` | **Clean** |
| Pre-commit (trim/EOF/YAML/large-files/detect-secrets) | **All pass** |
| GitNexus analyze | 14,043 nodes, 43,345 edges |

## 6. GitNexus Impact

| Symbol | Change | Risk |
|---|---|---|
| `OrderListPage` | Payment permission gate changed from `orders:update` to `payments:create` | LOW — more correct, aligns with backend |
| `hasPayPermission` (new) | New permission check variable | LOW — additive |
| No backend changes | Backend untouched | NONE |

## 7. Scope Compliance

- Frontend permission contract, tests, and report only
- No migration, financial write change, S2B implementation
- No deployment or protected-branch push
- No backend code changes

## 8. Self-Review

| # | Check | Result |
|---|---|---|
| 1 | Payment visibility uses `payments:create` (not `orders:update`) | PASS |
| 2 | `orders:update` kept for genuine order-edit actions only | PASS |
| 3 | Collect deep links use `payments:create` | PASS |
| 4 | No role-name shortcuts as authorization truth | PASS |
| 5 | Backend not weakened | PASS |
| 6 | Tests prove all 5 required scenarios | PASS (6 tests) |
| 7 | Denied paths make zero payment API calls | PASS (scenario 2, 6) |
| 8 | Full vitest green | PASS (154/154) |
| 9 | Build succeeds | PASS |
| 10 | Backend regressions green | PASS (39/39) |
| 11 | `git diff --check` clean | PASS |
| 12 | detect-secrets clean | PASS |
| 13 | No protected ref pushed | PASS |

## 9. Verdict

```
PASS_FOR_CTO_DC12R1_H3_MERGE_REVIEW
```
