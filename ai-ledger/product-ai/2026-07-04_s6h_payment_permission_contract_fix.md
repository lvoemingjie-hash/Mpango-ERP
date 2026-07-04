# S6-H Payment Permission Contract Fix

Date: 2026-07-04
Branch: codex/s6h-payment-permission-contract-fix
Verdict: PASS_FOR_CTO_REVIEW

## Trigger

Independent pre-U5 re-audit found one P1 blocker after S6-G:

- Active docs say canonical payment writes use `payments:create`.
- Runtime route `POST /api/v1/orders/{order_id}/pay` was still guarded by
  `RequirePermission("orders:update")`.

This created an active RBAC/API contract mismatch: finance users with documented
payment-create authority could be blocked from the canonical payment write path.

## Decision

Fix production code to match the business/API contract:

- `POST /api/v1/orders/{order_id}/pay` requires `payments:create`.
- `orders:update` remains for order lifecycle mutations such as confirm, cancel,
  return, and fulfillment.

This is the least surprising MVP permission model because recording a payment is
a finance action, even though the route lives under the order resource.

## Changes

- Updated `backend/api/v1/orders.py` pay route dependency:
  - from `RequirePermission("orders:update")`
  - to `RequirePermission("payments:create")`
- Added route policy harness coverage that asserts the pay route requires
  `payments:create` and not `orders:update`.

## Scope

Changed files:

- `backend/api/v1/orders.py`
- `backend/tests/test_route_authorization_policy.py`
- `ai-ledger/product-ai/2026-07-04_s6h_payment_permission_contract_fix.md`

No payment ledger logic, order state machine logic, migration, frontend, deploy,
or docs change was required.

## Validation

- GitNexus context: `backend/api/v1/orders.py:pay_order` participates in payment
  and order route tests.
- Route/RBAC gate:
  - `poetry run pytest tests/test_route_authorization_policy.py tests/test_u1_bootstrap_permission_completeness.py -q`
  - Result: 40 passed.
- Payment/order regression attempt:
  - `poetry run pytest tests/test_phase5_order_payment.py tests/test_s5d4b_settled_cash_payment.py tests/test_s5d5_payment_ledger_runtime_invariant.py tests/test_s5d6_multi_partial_payment_state_machine.py -q`
  - Result: 63 passed, 1 xfailed, 9 errors.
  - Error cause: local DB fixture could not resolve/connect to the configured PostgreSQL host (`socket.gaierror`).
- Payment/order DB retry with explicit localhost env:
  - `POSTGRES_HOST=127.0.0.1`, `POSTGRES_PORT=5432`, `POSTGRES_USER=mpango`, `POSTGRES_PASSWORD=MpangoTest_2026`, `POSTGRES_DB=mpango_erp`, `REPORTING_USER_PASSWORD=MpangoTest_2026`
  - Result: 10 passed, 9 errors.
  - Error cause: local PostgreSQL rejected the test password (`InvalidPasswordError`).
- `git diff --check`: PASS.
- GitNexus `detect_changes`: pending final staged run before commit.

The failed DB-capable tests are environment authentication/connectivity failures in
test fixture setup, not product assertion failures. Cross-environment/runner DB
validation is still recommended before final product merge if CTO requires live DB
proof for this permission-only change.

## Result

The active payment permission contract is aligned again:

- Docs: `payments:create`
- Runtime route: `payments:create`
- Route policy harness: enforces `payments:create`
