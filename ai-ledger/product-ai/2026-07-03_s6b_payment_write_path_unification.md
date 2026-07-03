# S6-B Payment Write Path Unification

**Date**: 2026-07-03
**Branch**: `opencode/s6b-payment-write-path-unification-2026-07-03`
**Executor**: OPS / opencode
**Verdict**: `PASS_WITH_LOCAL_ENVIRONMENT_BLOCKERS`

## Summary

S6-B disables the legacy `POST /api/v1/payments` write path so MVP payment creation must go through `POST /api/v1/orders/{order_id}/pay`.

The legacy route created payment rows directly through `PaymentService.create_payment()` and could bypass the order state machine and order-level settlement ledger protections. The canonical order payment route remains the single payment write path for order status, partial-payment, and ledger consistency.

## Impact Audit

Required GitNexus impact/context checks were run before editing:

```text
create_payment: resolved to backend/services/payment_service.py:create_payment, LOW risk
PaymentService.create_payment: target name not found directly; context found via backend/services/payment_service.py:create_payment
/orders/{id}/pay: context found via backend/api/v1/orders.py:pay_order
OrderService.transition: resolved to backend/services/order_service.py:transition, HIGH risk, 90 impacted symbols
```

The HIGH impact on `OrderService.transition` was expected for the financial state-machine path and was not modified.

## Implementation

Changed `backend/api/v1/payments.py`:

```text
POST /api/v1/payments now returns 409 PAYMENT_WRITE_PATH_DISABLED before calling PaymentService.create_payment().
```

Error contract:

```json
{
  "code": "PAYMENT_WRITE_PATH_DISABLED",
  "message": "Use POST /api/v1/orders/{order_id}/pay so order status and ledger stay consistent."
}
```

Unchanged behavior:

```text
GET /api/v1/payments remains enabled.
GET /api/v1/payments/{payment_id} remains enabled.
PaymentService.create_payment service-level idempotency behavior remains tested and unchanged.
OrderService.transition remains unchanged.
Ledger posting rules remain unchanged.
```

## Tests

Added `backend/tests/test_s6b_payment_write_path_unification.py`:

```text
Proves legacy POST /payments returns 409 and performs no DB execute, flush, commit, or rollback side effects.
```

Updated route-level payment API tests:

```text
backend/tests/test_payments_api.py
backend/tests/b6_hardening/test_b6_payments_api.py
```

The obsolete route-level transfer idempotency-key assertions were replaced with disabled-route assertions. Service-level idempotency tests remain intact.

## Validation

Targeted S6-B validation passed:

```text
poetry run pytest tests/test_s6b_payment_write_path_unification.py tests/test_payments_api.py tests/b6_hardening/test_b6_payments_api.py -q
9 passed in 1.21s
```

Required S5-D5 financial invariant suite was attempted but blocked by local DB DNS setup before tests executed:

```text
poetry run pytest tests/test_s5d5_payment_ledger_runtime_invariant.py -q
5 errors during fixture setup
socket.gaierror: [Errno 11001] getaddrinfo failed
```

Required S5-D6 plus Phase5 suite was attempted. Most DB-independent tests passed, but DB-backed setup and route import tests were blocked by local environment requirements:

```text
poetry run pytest tests/test_s5d6_multi_partial_payment_state_machine.py tests/test_phase5_order_payment.py -q
50 passed, 1 xfailed, 3 failed, 2 errors
```

Environment blockers from that run:

```text
tests/test_s5d6_multi_partial_payment_state_machine.py: async DB fixture failed with socket.gaierror [Errno 11001] getaddrinfo failed.
tests/test_phase5_order_payment.py route-level app import tests failed because REPORTING_USER_PASSWORD environment variable was not set.
```

No secret values, JWTs, or passwords were read or printed.

Hygiene:

```text
git diff --check: PASS
changed-file ASCII scan: PASS
changed-file mojibake scan: PASS
changed-file sensitive-keyword scan: PASS, matched only ledger references to REPORTING_USER_PASSWORD and no-secrets notes
pre-commit on changed files: PASS
GitNexus analyze: PASS, already up to date for indexed commit 61a6a53
GitNexus status: up-to-date
```

## Frontend Audit

Frontend payment service audit found no legacy write caller:

```text
frontend/src/services/paymentService.ts exposes read methods only: getAll, getById, getByOrder.
```

No frontend changes were made.

## Scope Discipline

- Frontend changed: no.
- Migration added: no.
- Ledger rules changed: no.
- Order state machine changed: no.
- Deployment performed: no.
- `product-dev-recovered` pushed: no.
- Secrets printed: no.
- Tests weakened or skipped: no.
