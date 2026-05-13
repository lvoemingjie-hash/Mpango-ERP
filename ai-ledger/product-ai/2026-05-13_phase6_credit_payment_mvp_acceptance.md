# Phase 6 — Credit Payment MVP Acceptance Ledger

**Date:** 2026-05-13
**Author:** Claude Code (Codex execution agent)
**Worktree:** `C:\Users\Jeff0\MPANGO ERP\phase6-credit-mvp-2026-05-13`
**Branch:** `codex/phase6-credit-payment-mvp-2026-05-13`
**Base commit:** `af80149 docs(ai): align handoff baseline before phase6 work`
**Verdict:** READY_FOR_CTO_REVIEW

---

## CTO Instruction Compliance Check

| # | CTO Constraint | Compliant | Evidence |
|---|----------------|-----------|----------|
| 1 | Do not push | YES | No push executed. `git status --short` shows only this new ledger file. |
| 2 | Do not commit unless told by CTO | YES | No commits made. All changes (if any) remain unstaged. |
| 3 | Do not touch platform, auth, tenancy, billing, accounting redesign | YES | No edits to any file outside the Phase 6 scope. |
| 4 | Do not implement partial credit, split tender, credit limits, aging, returns, cancellation, UI | YES | No new code written. Existing implementation already rejects all of these. |
| 5 | If Phase 6 MVP is already correct, validate and write ledger only | YES | This is a validation-only mission. |
| 6 | Run GitNexus impact before editing any symbol | N/A | No code edited. |
| 7 | Keep claims evidence-based | YES | All claims below include exact commands and results. |

---

## Files Changed

**Validation-only.** No source files were modified.

Created:

- `ai-ledger/product-ai/2026-05-13_phase6_credit_payment_mvp_acceptance.md`

The Phase 6 credit payment MVP was implemented at commit history prior to this branch's base (`af80149`), documented in `ai-ledger/product-ai/2026-05-06_phase6_credit_payment_mvp_implementation.md`.

---

## Approved Model vs Code Validation

Each requirement from the approved Phase 6 MVP model was verified against the current source code:

| # | Approved Requirement | Satisfied | Code Evidence |
|---|---------------------|-----------|---------------|
| 1 | Full-credit sale only | YES | `orders.py:492` — `pay_amount != order_total` → 400 `CREDIT_AMOUNT_MISMATCH` |
| 2 | Credit allowed only on clean order (prior_paid == 0) | YES | `orders.py:478` — `prior_paid > 0` → 400 `CREDIT_SPLIT_TENDER_UNSUPPORTED` |
| 3 | Credit amount must equal full order total | YES | `orders.py:492` — same guard as #1 |
| 4 | Credit increases outstanding_balance by +amount | YES | `orders.py:554-558` — `balance_delta = pay_amount` for credit; `payment_service.py:167-173` applies `+amount` |
| 5 | Credit payment status is pending | YES | `orders.py:540` — `"completed" if transfer else "pending"` |
| 6 | Credit does not count into cash paid_total | YES | `payment_repository.py:138-153` — `AND method IN ('cash', 'transfer')` filter |
| 7 | Full credit closes order lifecycle as PAID | YES | `orders.py:506-511` — cumulative = prior_paid + pay_amount >= order_total → PAID |
| 8 | Duplicate credit on same order is rejected | YES | `orders.py:462-475` — `count_order_payments(method='credit') > 0` → 409 `DUPLICATE_CREDIT_PAYMENT` |
| 9 | Partial credit and split tender are rejected | YES | Guards #1 and #2 cover both cases |

---

## Tests Run and Exact Results

**Command 1 — Claude Code initial run without local reporting password:**
```
cd "C:\Users\Jeff0\MPANGO ERP\phase6-credit-mvp-2026-05-13\backend"
poetry run pytest tests/test_phase5_order_payment.py -q --tb=short
```

**Result:**
```
collected 47 items
43 passed, 3 failed, 1 xfailed, 11 warnings
```

**Command 2 — CTO rerun with required local environment variable:**
```
cd "C:\Users\Jeff0\MPANGO ERP\phase6-credit-mvp-2026-05-13\backend"
$env:REPORTING_USER_PASSWORD='test_reporting_password'
$env:PYTHONIOENCODING='utf-8'
poetry run pytest tests/test_phase5_order_payment.py -q --tb=short
```

**Result:**
```
collected 47 items
46 passed, 1 xfailed, 44 warnings
```

### Breakdown

#### Final accepted result: 46 PASSED, 1 XFAILED, 0 FAILED

The 3 initial failures were eliminated by setting the documented local prerequisite `REPORTING_USER_PASSWORD`.
No source code or test strategy was changed.

The 46 passed tests include all 16 Phase 6 credit-specific tests:

| Test | Validates |
|------|-----------|
| `test_credit_payment_applies_positive_balance_delta` | Credit → delta = +amount |
| `test_cash_payment_applies_negative_balance_delta` | Cash → delta = -amount |
| `test_transfer_payment_applies_negative_balance_delta` | Transfer → delta = -amount |
| `test_get_order_paid_total_sql_excludes_credit` | SQL filter excludes credit |
| `test_get_order_paid_total_only_counts_cash_and_transfer` | Credit excluded from sum |
| `test_credit_payment_status_is_pending` | Credit payment status = pending |
| `test_credit_full_amount_advances_order_to_paid` | Full credit → PAID |
| `test_credit_partial_amount_rejected` | Partial credit → 400 |
| `test_credit_rejected_when_prior_cash_exists` | Prior cash + credit → 400 |
| `test_credit_rejected_when_amount_exceeds_remaining` | Credit > remaining → 400 |
| `test_payment_service_credit_applies_positive_delta` | PaymentService credit → +delta |
| `test_payment_service_cash_applies_negative_delta` | PaymentService cash → -delta |
| `test_pay_order_request_accepts_credit_method` | Schema accepts credit |
| `test_pay_order_request_accepts_transfer_method` | Schema accepts transfer |
| `test_duplicate_credit_payment_rejected` | Second credit → 409 |
| `test_first_credit_payment_allowed` | First credit passes through to PAID |

#### Initial 3 failures — environment-only, NOT code defects:

All 3 failures are in `TestRouteLevelOrderPaymentMonkeypatch` class, caused by:
```
RuntimeError: REPORTING_USER_PASSWORD environment variable must be set
```
This is a known environment prerequisite documented in `docs/ai/PROJECT.md`. These tests require importing `main.py` which triggers `database/reporting_session.py` → requires `REPORTING_USER_PASSWORD`. The tests that fail are route-level (TestClient-based), not logic tests.

Affected tests:
1. `test_route_legacy_pay_empty_body_returns_200`
2. `test_route_structured_full_payment_returns_200`
3. `test_route_partial_payment_returns_partially_paid`

#### 1 XFAILED — known and documented:

`test_route_overpayment_rejected_with_400` — marked `@pytest.mark.xfail` with documented reason about mock complexity. Overpayment logic is verified by unit test `test_api_reject_overpayment` which PASSES.

---

## GitNexus Impact Results

No code was edited, so no GitNexus impact analysis was required per CLAUDE.md governance.

---

## Validation-Only Assessment

Phase 6 credit payment MVP is **already correctly implemented** on the base commit `af80149`. The implementation:

1. Satisfies all 9 approved model requirements (verified by reading source code)
2. Has 16 dedicated Phase 6 credit tests — all pass
3. Has comprehensive Phase 5 payment tests — all pass (43/43 non-env-dependent)
4. Was previously documented in `2026-05-06_phase6_credit_payment_mvp_implementation.md` with CTO corrections applied

No code changes, no rewrites, no fixes needed.

---

## Remaining Risks / Blockers

| Risk | Severity | Notes |
|------|----------|-------|
| Route-level tests require `REPORTING_USER_PASSWORD` env var | LOW | Known prerequisite. Tests pass when env is configured. |
| Known xfail for overpayment route test | LOW | Logic covered by passing unit test. Route seam complexity documented. |
| No live-DB integration test for credit on this branch | MEDIUM | Unit tests with mocks are comprehensive. Live-DB test recommended before `main` promotion. |
| `payment_service.py` has duplicate credit balance logic | LOW | `create_payment()` applies credit delta (+amount) independently, but `pay_order()` endpoint also applies it. The endpoint path via `pay_order()` is the authoritative flow; `create_payment()` is the standalone payments API path. No double-counting risk because `pay_order()` does NOT call `create_payment()` — it calls `repo.create()` directly. |

---

## Git Status

```
$ git status --short
?? ai-ledger/product-ai/2026-05-13_phase6_credit_payment_mvp_acceptance.md

$ git branch --show-current
codex/phase6-credit-payment-mvp-2026-05-13

$ git log -1 --oneline
af80149 docs(ai): align handoff baseline before phase6 work
```

---

## Commit / Push Status

- **Commits made:** 0 (validation-only)
- **Pushes made:** 0
- **Unstaged changes:** 1 (this ledger file)

---

## CTO Decision Needed

None required. Phase 6 credit payment MVP is implemented correctly and passes all applicable tests. The only decision is whether to proceed with promotion to `main` or continue with Phase 6.1+ scope, which requires separate CTO instruction.
