# S5-D6 Multi-Partial Payment State Machine Fix

**Date**: 2026-06-30
**Branch**: `opencode/s5d6-multi-partial-payment-state-machine-fix-2026-06-30`
**Executor**: OPS / opencode
**Verdict**: `PASS_FOR_CTO_REVIEW`

## Summary

S5-D6 fixes the structured payment route so an order can receive multiple partial cash or transfer payments before the final settlement payment.

The defect was confirmed before the fix:

```text
confirmed -> partially_paid: first partial payment succeeds
partially_paid -> partially_paid: second partial payment fails with INVALID_STATE_TRANSITION
```

The minimal fix keeps the global state matrix strict and adds a contextual exception inside `OrderService.transition()` only when the same-state transition is driven by structured cash or transfer payment context.

## Audit Finding

The global matrix in `backend/core/domain/order_state.py` intentionally does not include `PARTIALLY_PAID -> PARTIALLY_PAID`.

The structured payment route in `backend/api/v1/orders.py` already applies the correct payment guards:

- Draft, paid, cancelled, fulfilled, returned, and other non-payable states are rejected before transition.
- Overpayment is rejected against remaining balance.
- Duplicate credit is rejected.
- Credit remains full-credit only and does not create misleading cash settlement ledger entries.
- Final partial payment targets `PAID` and triggers settlement.

The bug was that the route correctly computed the second non-final partial as target `PARTIALLY_PAID`, but `OrderService.transition()` rejected the same-state transition before payment-context semantics could be applied.

## Implementation

Changed `backend/services/order_service.py`:

```text
PARTIALLY_PAID -> PARTIALLY_PAID is accepted only when payment_method is cash or transfer.
```

Changed tests:

- `backend/tests/test_s5_order_state_machine.py`
- `backend/tests/test_s5d6_multi_partial_payment_state_machine.py`

The global helper `is_valid_transition(PARTIALLY_PAID, PARTIALLY_PAID)` still returns false. This avoids making non-payment no-op transitions globally legal.

## Ledger Behavior

Intermediate partial payments remain target `PARTIALLY_PAID`, so `_post_ledger_entries()` does not create cash or receivable settlement entries.

Final partial payment targets `PAID`, so the existing ledger path posts a single balanced order-level settlement:

```text
cash debit == total completed cash/transfer payments
receivable credit == total completed cash/transfer payments
settlement sum == 0.0000
settlement entry count == 2
```

Existing S5-D4B settlement then marks pending cash/transfer payments completed only after the returned order status is actually `paid`.

## Contextual Transition Risk

Architecture supports contextual transition through the existing `payment_method` argument on `OrderService.transition()`.

Risk is contained because the global matrix remains unchanged and a new state-machine test proves non-payment `PARTIALLY_PAID -> PARTIALLY_PAID` still raises `InvalidStateTransitionError`.

## Validation

Focused reproduction before fix:

```text
3 failed
Failures reproduced INVALID_STATE_TRANSITION for partially_paid -> partially_paid.
```

Focused validation after fix:

```text
poetry run pytest tests/test_s5d6_multi_partial_payment_state_machine.py tests/test_s5_order_state_machine.py::test_partially_paid_self_transition_is_not_globally_valid tests/test_s5_order_state_machine.py::test_partially_paid_self_transition_allowed_only_for_payment_context -q -rxX --tb=short
4 passed
```

Required regression gate:

```text
poetry run pytest tests/test_s5d6_multi_partial_payment_state_machine.py tests/test_s5d5_payment_ledger_runtime_invariant.py tests/test_s5d4b_settled_cash_payment.py tests/test_phase5_order_payment.py tests/test_payment_atomicity.py tests/b6_hardening/test_b6_payment_atomicity.py tests/test_s5_order_state_machine.py tests/test_s5_ledger.py tests/test_s5_5_ledger_hardening.py tests/business/test_s4f_business_invariant_closeout.py -q -rxX --tb=short
124 passed, 1 xfailed
```

Hygiene:

```text
git diff --check: PASS
tracked changed-line ASCII scan: PASS
new test ASCII scan: PASS
changed-files sensitive scan: PASS
pre-commit on changed files: PASS
```

## Scope Discipline

- Frontend changed: no.
- Migration added: no.
- Deployment performed: no.
- `product-dev-recovered` pushed: no.
- Secrets printed: no.
- Tests weakened or skipped: no.
