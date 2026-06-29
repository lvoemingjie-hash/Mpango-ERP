# S5-D4B -- Settled Cash Payment Status Contract

**Date**: 2026-06-26
**R2 evidence correction date**: 2026-06-29
**R1 branch**: `opencode/s5d4b-r1-financial-atomicity-proof-2026-06-26`
**R1 commit**: `1a4f174 fix: tighten paid settlement atomicity guard`
**Lineage**: `e58062c feat(S5-D4B): settle cash/transfer payments to completed on order PAID transition`
**Verdict**: `PASS_FOR_CTO_REVIEW`

---

## R2 Correction Summary

This ledger supersedes stale S5-D4B evidence claims from the original R0 record.
The R1 implementation truth is:

- Settlement is gated on the returned order's actual status: `returned order.status == paid`.
- Settlement is not gated merely on the proposed `target_state == OrderState.PAID`.
- S5-D4B targeted tests are `12 passed`, not `9 passed`.
- The S5-D4B/R1 changed-file count is `6` when including original S5-D4B closure plus R1 evidence/harness correction:
  `backend/repositories/payment_repository.py`, `backend/api/v1/orders.py`, `backend/tests/test_s5d4b_settled_cash_payment.py`, `backend/tests/conftest.py`, `backend/tests/b6_hardening/test_b6_payment_atomicity.py`, and this evidence ledger.

R2 is an evidence-ledger correction only. No production code was changed in R2.

---

## Problem

S5-D4A audit proved that once an order reached `paid`/`fulfilled`, cash payment
rows could remain stuck at `pending`. The PaymentListPage UI therefore showed
cash payments as pending after full settlement.

The original S5-D4B closure added a repository method to complete pending
`cash`/`transfer` rows for an order, but its first evidence record overstated the
guard as `target_state == PAID`. R1 tightened the guard to the actual returned
order status and added real DB/request-lifecycle proof.

---

## Final Contract

When a structured `POST /orders/{id}/pay` records payment and the order service
returns an order whose actual status is `paid`, advance pending `cash` and
`transfer` payments for that order to `completed` in the same request-owned DB
transaction.

Contract boundaries honored:

- `OrderService._post_ledger_entries()` was not modified.
- No new `reconciled`/`refunded` enum values were added.
- `credit` rows remain `pending`; settlement SQL excludes `credit`.
- No historical data backfill.
- No VPS, deploy, or runtime production data touched.
- `mobile_money` not touched.
- Legacy empty-body pay path untouched.

---

## Actual Settlement Gate

R1 production behavior in `backend/api/v1/orders.py`:

```python
order = await order_service.transition(...)

order_status = getattr(order.status, "value", order.status)
if order_status == OrderState.PAID.value:
    await payment_repo.update_cash_transfer_to_completed(
        db, order_id=order.id,
    )
```

This proves settlement is based on the persisted/returned transition result, not
only on the handler's proposed target state.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/repositories/payment_repository.py` | Original S5-D4B repository method: scoped `cash`/`transfer` pending-to-completed update. |
| `backend/api/v1/orders.py` | R1 guard correction: settle only when returned `order.status` is actually `paid`. |
| `backend/tests/test_s5d4b_settled_cash_payment.py` | Expanded to 12 tests including actual-status guard, real DB credit proof, and live request rollback proof. |
| `backend/tests/conftest.py` | Added tenant test `payments` table bootstrap and truncation for real DB payment proofs. |
| `backend/tests/b6_hardening/test_b6_payment_atomicity.py` | Aligned stale nested-transaction assertion with current middleware-owned transaction contract. |
| `ai-ledger/product-ai/2026-06-26_s5d4b_settled_cash_payment_status_contract.md` | R2 evidence correction only. |

---

## Proof Added In R1

### S5-D4B Target Suite

`tests/test_s5d4b_settled_cash_payment.py`: `12 passed`

Key added/updated proofs:

- `test_api_proposed_paid_but_returned_non_paid_does_not_settle`: proposed PAID is insufficient; settlement does not run when returned status is non-PAID.
- `test_settle_update_leaves_credit_rows_pending`: real tenant DB proof that credit rows remain `pending` while cash rows complete.
- `test_route_settlement_failure_rolls_back_payment_order_balance_and_ledger`: real ASGI request/middleware/session lifecycle proof that a forced settlement failure after `transition()` rolls back order status, new payment creation, public outstanding balance, and ledger writes.

### Live DB Rollback Proof

The rollback test seeds:

- confirmed order
- existing pending cash payment
- public `wholesaler_retailer_bindings.outstanding_balance`
- existing ledger rows

It then executes `POST /api/v1/orders/{id}/pay` through real FastAPI routing,
`AuthenticationMiddleware`, tenant context creation, and middleware-owned session
finalization. The only injected failure is
`PaymentRepository.update_cash_transfer_to_completed()` after order transition.

Assertions prove rollback:

- order remains `confirmed`
- no new payment persists
- existing pending payment remains `pending`
- outstanding balance is unchanged
- ledger count and ledger sum are unchanged

### Credit-Row Real DB Proof

The credit proof inserts real tenant-local `payments` rows:

- pending `cash`
- pending `credit`

After `update_cash_transfer_to_completed()`, assertions prove:

- cash row becomes `completed`
- credit row remains `pending`
- update count is exactly `1`

---

## Test Results

### R2 Evidence-Correction Rerun

```text
poetry run pytest tests/test_s5d4b_settled_cash_payment.py tests/test_phase5_order_payment.py tests/test_payment_atomicity.py tests/b6_hardening/test_b6_payment_atomicity.py -q -rxX --tb=short
68 passed, 1 xfailed, 53 warnings
```

This R2 rerun used local Docker-backed PostgreSQL settings (`POSTGRES_HOST=127.0.0.1`, `POSTGRES_PORT=5432`) with connection values loaded into process environment from running containers and not printed.

### R1 Verified Results

```text
poetry run pytest tests/test_s5d4b_settled_cash_payment.py -q -rxX --tb=short
12 passed, 9 warnings
```

```text
poetry run pytest tests/test_phase5_order_payment.py -q -rxX --tb=short
53 passed, 1 xfailed, 45 warnings
```

```text
poetry run pytest tests/test_payment_atomicity.py tests/b6_hardening/test_b6_payment_atomicity.py -q -rxX --tb=short
3 passed
```

```text
poetry run pytest tests/business/test_s4f_business_invariant_closeout.py -q -rxX --tb=short
8 passed, 18 warnings
```

```text
poetry run pytest tests/test_s5_order_state_machine.py tests/test_s5_ledger.py tests/test_s5_5_ledger_hardening.py -q -rxX --tb=short
39 passed
```

Notes:

- A combined S4-F/S5 run once hit an `asyncpg` stale enum cache error; the isolated failing test passed immediately.
- A parallel S4-F/S5 rerun hit expected shared `t_test` DB deadlocks; serial reruns passed.
- Final accepted evidence uses serial live-DB runs.

---

## Quality Gates

| Check | Status |
|-------|--------|
| Isolated branch, no `product-dev-recovered` push | PASS |
| `git diff --check` | PASS |
| ASCII scan | PASS |
| Sensitive-material scan | PASS |
| pre-commit hooks | PASS |
| GitNexus analyze/status | PASS, indexed at `1a4f174` |
| No `OrderService._post_ledger_entries()` modified | PASS |
| No `mobile_money` change | PASS |
| No migration/backfill/deploy/VPS action | PASS |

GitNexus note: this OpenCode session exposed the GitNexus CLI (`analyze`,
`status`) but not an MCP `detect_changes` command. The worktree was indexed and
reported up to date at `1a4f174`.

---

## Explicitly Removed Stale Claims

The following R0 claims are no longer accurate and are superseded by this R2
ledger correction:

- Settlement gate is `target_state == OrderState.PAID`.
- S5-D4B target suite has 9 tests.
- Only 3 files changed.
- Credit safety is proven only by mock-level/tautological assertions.
- Rollback safety is mock-only.

---

## Explicit Non-Actions

- Did not modify production code in R2.
- Did not modify `OrderService._post_ledger_entries()`.
- Did not add payment status enum values.
- Did not change `credit` settlement behavior.
- Did not backfill historical data.
- Did not touch `mobile_money`.
- Did not deploy or touch VPS/runtime data.
- Did not push to `product-dev-recovered`.
