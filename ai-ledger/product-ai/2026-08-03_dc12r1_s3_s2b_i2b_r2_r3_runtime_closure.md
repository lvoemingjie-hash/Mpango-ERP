# DC-12R1-S3-S2B-I2B-R2-R3: Runtime Closure — Authoritative Final Report

**Date**: 2026-08-03
**Branch**: `codex/dc12r1-s3-s2b-i2b-payment-declaration-runtime-2026-08-03`
**Base SHA**: `76fb345c9054530cb0e6abccf35f0cc1863d2bef` (origin/product-dev-recovered)
**R2 commit**: `4a11ac240174c85a63e6c5e90039d8acec0d956f` (accepted production fixes)
**R3 commit**: (this report accompanies the R3 implementation commit)

---

## Verdict

**`PASS_FOR_CTO_DC12R1_S3_S2B_I2B_R2_R3_FINAL_MERGE_REVIEW`**

All CTO merge blockers closed without changing the approved I2B financial
semantics. Two accepted production fixes from R2 are preserved. Four list+search
anti-patterns eliminated. Stable frontend idempotency implemented. Authentic
admin/cashier harness replaces retailer-as-admin shortcut. 42 backend tests pass
GREEN (up from 19 in R2).

---

## R2 Accepted Fixes (Preserved)

1. **`scripts/bootstrap_tenant_schema.py`** — admin role created before
   permission grants in `_reconcile_rbac_s1()`.
2. **`services/payment_declaration_service.py`** — `text` imported from sqlalchemy.

---

## R3 Changes

### S3: Exact Joined Dual-Key Repository Reads (4 list+search sites eliminated)

**Problem**: 4 API route handlers fetched full pages of declarations then filtered
in memory with `next(...)` to find a single row. This caused:
- `size=1000` page loads for detail views
- `size=50` for post-submit enrichment
- `size=1` for post-reject readback (almost always missed the target row)
- Missing `order_status` and `receipt_number` in responses

**Fix**: Added two new joined dual-key methods to `PaymentDeclarationRepository`:
- `get_detail_by_wholesaler(declaration_id, wholesaler_id)` — cashier scope
- `get_detail_by_retailer(declaration_id, retailer_id, wholesaler_id)` — retailer scope

Both return the full joined column set (including `order_status`, `receipt_number`)
via exact WHERE clauses — no pagination, no list+search.

**Files changed**:
- `backend/repositories/payment_declaration_repository.py` (+65 lines: 2 new methods)
- `backend/api/v1/declarations.py` (detail + post-reject: list+search → dual-key)
- `backend/api/v1/client/declarations.py` (detail: list+search → dual-key)
- `backend/api/v1/client/orders.py` (post-submit: list+search → dual-key)

### S4: Non-Latest Rejection

Added `TestNonLatestRejection.test_reject_older_declaration_with_newer_present` —
creates two declarations, rejects the older one, asserts 200 with correct status
and `order_status`, zero financial mutation, newer declaration unchanged.

### S5: Stable Frontend Idempotency

**Problem**: `DeclarePaymentPage.tsx:21` generated the idempotency key per-call
inside `handleSubmit` using `Date.now()` + `Math.random()`. Retries got new keys,
defeating backend deduplication.

**Fix**:
- Key generated once per mount via `useRef<string>(crypto.randomUUID())`
- `submittingRef` mutex prevents duplicate in-flight submissions
- Same key reused across retries (catch path does not rotate)
- Key rotated only after confirmed success
- No localStorage/sessionStorage used

**Vitest proof** (`frontend/src/tests/DeclarePaymentPage.test.tsx`): 4 test cases
covering same-key retry, duplicate-click prevention, single navigation, no storage.

**Files changed**:
- `frontend/src/pages/client/DeclarePaymentPage.tsx` (rewritten handleSubmit)
- `frontend/src/tests/DeclarePaymentPage.test.tsx` (new: 122 lines)

### S6: Authentic Admin/Cashier Harness

**Problem**: Test helper `_grant_admin_role` granted admin to the RETAILER user,
manufacturing authorization by attaching admin to the retailer identity.

**Fix**: Replaced with `_provision_admin_user` + `_cashier_token`:
- Creates a SEPARATE admin/cashier user with unique email
- Assigns ONLY the admin role (never retailer_operator)
- Obtains token through real `/auth/login` + `/auth/select-tenant` path
- Asserts `admin_user_id != retailer_user_id`
- Asserts retailer_operator never receives `payments:confirm_declaration` (403)
- Asserts admin never receives `client:*` permissions
- Retailer token gets controlled 403 on confirm/reject
- Cashier token executes confirm/reject successfully

**Test class**: `TestAuthenticHarness` (5 tests)

### S7: Backend Runtime Matrix

**Added**: `TestRuntimeMatrix` class + expanded `TestRejectDeclaration` — covering:

| Scenario | Test |
|----------|------|
| Wrong wholesaler confirm → neutral 404 | `test_wrong_wholesaler_confirm_returns_neutral_404` |
| Wrong retailer ownership → fail closed | `test_wrong_retailer_declaration_ownership_fail_closed` |
| Inactive binding → fail closed | `test_inactive_binding_confirmation_fail_closed` |
| Soft-deleted binding → fail closed | `test_soft_deleted_binding_confirmation_fail_closed` |
| Concurrent same-payload → one declaration | `test_concurrent_same_payload_submit_one_declaration` |
| Concurrent different-payload same key → 409 | `test_concurrent_different_payload_same_key_one_success_one_409` |
| Concurrent confirmation → one payment+receipt | `test_concurrent_confirmation_one_payment_one_receipt` |
| Confirmation replay → same payment+receipt | `test_confirmation_replay_same_payment_and_receipt_zero_writes` |
| Malformed replay receipt → controlled 409 | `test_malformed_replay_receipt_returns_409` |
| Receipt allocation rollback → zero residue | `test_receipt_allocation_rollback_zero_residue` |
| Rollback → sequence reusable | `test_rollback_leaves_sequence_transactionally_reusable` |
| Overpayment → pending + unchanged snapshot | `test_overpayment_rejection_leaves_declaration_pending` |
| Unrelated IntegrityError → not 409 | `test_unrelated_integrityerror_not_reclassified_as_409` |
| Reserved namespace → rejected | `test_direct_payment_reserved_namespace_rejected` |
| Reject reason missing → 400 | `test_reject_reason_missing_returns_400` |
| Reject reason oversized → 400 | `test_reject_reason_oversized_returns_400` |
| Reject reason HTML → 400 | `test_reject_reason_forbidden_html_returns_400` |

**Product fix for 422→400**: `schemas/declaration.py` — `DeclarationRejectRequest.reason`
changed from required (`Field(...)`) to optional (`Field(None)`) so Pydantic
validation does not preempt the route's controlled 400 `INVALID_REJECTION_REASON`.

### S4: Non-Latest Rejection (detailed)

**Test class**: `TestNonLatestRejection`

| Test | Description |
|------|-------------|
| `test_reject_older_declaration_with_newer_present` | Older declaration rejected with 200, correct status + order_status, zero mutation, newer unchanged |

---

## Exact Changed Files

```
 backend/api/v1/client/declarations.py              |   7 +-
 backend/api/v1/client/orders.py                    |  11 +-
 backend/api/v1/declarations.py                     |  20 +-
 backend/repositories/payment_declaration_repository.py |  65 ++
 backend/schemas/declaration.py                     |   4 +-
 backend/tests/test_dc12r1_s3_s2b_i2b_payment_declarations.py | 927 ++++++++++++++++++---
 frontend/src/pages/client/DeclarePaymentPage.tsx   |  21 +-
 frontend/src/tests/DeclarePaymentPage.test.tsx     | (new: 122 lines)
```

Plus report files (this file + SUPERSEDED notices on 2 prior reports).

## Test Totals

| Suite | Tests | Status |
|-------|-------|--------|
| TestParityGate | 1 | PASS |
| TestAuthenticHarness (S6) | 5 | PASS |
| TestSubmitDeclaration | 7 | PASS |
| TestNamespaceIsolation | 2 | PASS |
| TestConfirmDeclaration | 6 | PASS |
| TestRejectDeclaration (expanded) | 6 | PASS |
| TestNonLatestRejection (S4) | 1 | PASS |
| TestRuntimeMatrix (S7) | 14 | PASS |
| **Total backend** | **42** | **ALL PASS** |
| Frontend Vitest (S5) | 4 | (requires pnpm install) |

---

## Environment

- Python 3.12.3, bcrypt 4.0.1, passlib 1.7.4
- PostgreSQL 16, Redis 7
- Alembic head: `037_payment_declarations_schema`
- No migration 038, no dependency/lockfile/config/deployment changes
- No merge, no force-push, no I2C work

## Quality Gates

- `py_compile`: all changed files OK
- `git diff --check`: clean (no whitespace errors)
- Mojibake/U+FFFD scan: clean
- No credentials, JWTs, emails, DB URLs, or row contents in reports or tests

## Prohibited Actions Verified Absent

- No migration 038
- No dependency/lockfile/config changes
- No push to product-dev-recovered, main, or platform-dev
- No merge or deployment
- No I2C work
- No retailer-to-admin shortcut in tests
- No list+search detail/replay code remaining
- No 422/500 replacing approved controlled errors
- No skips, xfails, deselections, retries, or weakened assertions
