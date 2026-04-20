# Phase 5 Slice 1 - Final Closeout Patch

**Date:** 2026-04-14
**Agent:** Product AI (Goose)
**Branch:** product-dev
**Status:** COMPLETED

## CTO Findings Addressed

1. **Request-level API tests missing**: Tests mocked at service/repo level but never called the actual `pay_order` endpoint function.
2. **Frontend mojibake**: OrderListPage.tsx and PaymentRecordModal.tsx contained non-ASCII characters (ellipses, arrows, em-dashes, checkmarks, warning signs).

## Changes Made

### 1. Endpoint-function contract tests (4 new tests)

**File:** `backend/tests/test_phase5_order_payment.py`

Added section 7 with 4 tests that call `api.v1.orders.pay_order()` directly with mocked dependencies (same pattern as `test_payments_api.py` calls `create_payment`):

| Test | What it proves |
|------|---------------|
| `test_api_legacy_pay_empty_body` | Endpoint returns `OrderActionResponse` with `status=paid` on empty body |
| `test_api_structured_full_payment` | Endpoint returns `paid` + `payment_id` + `payment_amount` for full payment |
| `test_api_structured_partial_payment` | Endpoint returns `partially_paid` status for partial payment |
| `test_api_reject_overpayment` | Endpoint raises HTTP 400 with `PAYMENT_EXCEEDS_REMAINING` on overpayment |

NOTE: These are endpoint-function contract tests, NOT full HTTP route-level tests. They prove function-level behavior (response shape, error codes, business logic paths) but do not test URL routing, JSON deserialization, middleware, or dependency injection resolution. See `2026-04-14_phase5_hygiene_closeout.md` for detailed classification.

### 2. Encoding cleanup

| File | Before | After |
|------|--------|-------|
| `frontend/src/pages/orders/OrderListPage.tsx` | 8 non-ASCII (U+2026, U+2192, U+2014) | 0 |
| `frontend/src/components/ui/PaymentRecordModal.tsx` | 5 non-ASCII (U+2026, U+2713, U+26A0) | 0 |

Replacements applied:
- U+2026 (horizontal ellipsis) -> `...`
- U+2192 (rightwards arrow) -> `->`
- U+2014 (em dash) -> `--`
- U+2713 (check mark) -> `[OK]`
- U+26A0 (warning sign) -> `[!]`

### 3. Test coverage summary

| Category | Count | Level |
|----------|-------|-------|
| Schema validation | 3 | Unit |
| State machine | 5 | Unit |
| Outstanding balance | 5 | Logic |
| Repository | 2 | Integration-mock |
| Atomic transaction | 2 | Integration-mock |
| Legacy compat | 1 | Request-level API |
| Amount-to-state | 3 | Logic |
| OrderService | 2 | Integration-mock |
| **Endpoint-function contract (NEW)** | **4** | **Endpoint-function (NOT full route)** |
| **Total** | **26** | |

## Files Changed

| File | Change |
|------|--------|
| `backend/tests/test_phase5_order_payment.py` | +4 endpoint-function contract tests, helper refactors |
| `frontend/src/pages/orders/OrderListPage.tsx` | Encoding cleanup (8 -> 0 non-ASCII) |
| `frontend/src/components/ui/PaymentRecordModal.tsx` | Encoding cleanup (5 -> 0 non-ASCII) |

## Non-negotiables Compliance

- [x] No new features
- [x] No platform work
- [x] No tenancy changes
- [x] No pricing changes
- [x] No broad UX refactor
- [x] No push
- [x] No temp artifacts
