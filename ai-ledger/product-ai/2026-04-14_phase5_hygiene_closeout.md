# Phase 5 Slice 1 - Hygiene and Truthfulness Closeout

**Date:** 2026-04-14
**Agent:** Product AI (Goose)
**Branch:** product-dev
**Status:** COMPLETED

## CTO Findings Addressed

1. **Worktree dirty**: unstaged encoding cleanup in `backend/schemas/order.py`, stray repo-root file `127]`.
2. **Test coverage claims overstated**: tests call `pay_order()` directly but are described as "request-level API tests" -- must be honest about what they actually are.

## Changes Made

### 1. Branch cleanliness

| Action | File |
|--------|------|
| Staged (legitimate encoding cleanup) | `backend/schemas/order.py` -- 3 em-dashes replaced with `--` |
| Staged (encoding cleanup carried over) | `frontend/src/pages/orders/OrderListPage.tsx` -- 8 non-ASCII cleaned |
| Staged (encoding cleanup carried over) | `frontend/src/components/ui/PaymentRecordModal.tsx` -- 5 non-ASCII cleaned |
| Deleted (stray artifact) | `127]` at repo root |

### 2. Test coverage classification (Path A chosen)

**Path A selected**: Keep current tests, describe them honestly.

The 4 tests in section 7 of `test_phase5_order_payment.py` call `api.v1.orders.pay_order()` directly. They mock the DB session, repositories, and services. They prove:

- The endpoint function signature accepts `payment_input: Optional[PayOrderRequest]`
- The endpoint returns `OrderActionResponse` with correct shape on success
- The endpoint raises `HTTPException` with correct status code and error codes on failure
- Business logic paths (legacy, full, partial, overpayment) are exercised through the real function

**What they are NOT**: They are NOT full HTTP route-level tests using `httpx.AsyncClient` / `TestClient` against the FastAPI app. They do not test:
- URL routing
- Request deserialization from JSON body
- Response serialization to JSON
- Middleware execution (RBAC, auth)
- Dependency injection resolution

This is the same pattern used by the existing `test_payments_api.py` which also calls `create_payment()` directly.

**Honest classification**:

| Category | Count | Level |
|----------|-------|-------|
| Schema validation | 3 | Unit |
| State machine | 5 | Unit |
| Outstanding balance | 5 | Logic |
| Repository | 2 | Integration-mock |
| Atomic transaction | 2 | Integration-mock |
| Amount-to-state | 3 | Logic |
| OrderService | 2 | Integration-mock |
| **Endpoint-function contract** | **4** | **Endpoint-function (NOT full route)** |
| **Total** | **26** | |

### 3. Ledger accuracy fix

Previous ledgers described section 7 tests as "request-level API tests". Updated to "endpoint-function contract tests" throughout. No test code was changed.

## Files Changed

| File | Change |
|------|--------|
| `backend/schemas/order.py` | Encoding cleanup (3 em-dashes to `--`) |
| `frontend/src/pages/orders/OrderListPage.tsx` | Encoding cleanup (8 non-ASCII to ASCII) |
| `frontend/src/components/ui/PaymentRecordModal.tsx` | Encoding cleanup (5 non-ASCII to ASCII) |

## Non-negotiables Compliance

- [x] No new features
- [x] No platform work
- [x] No tenancy changes
- [x] No pricing changes
- [x] No broad UX refactor
- [x] No push
- [x] No temp artifacts
- [x] No misleading validation claims
