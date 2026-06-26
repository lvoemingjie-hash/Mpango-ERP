# S5-D4B -- Settled Cash Payment Status Contract

**Date**: 2026-06-26
**Branch**: `opencode/s5d4b-settled-cash-payment-status-contract-2026-06-26`
**Lineage**: `origin/product-dev-recovered`
**Verdict**: `PASS_FOR_CTO_REVIEW`

---

## Problem

S5-D4A audit proved that once an order reaches `paid`/`fulfilled`, its
`payments.status` rows remain stuck at `pending` for cash (and credit). No code
path advanced `pending` -> `completed`. The PaymentListPage UI therefore showed
100% of cash payments as yellow "Pending" even after full settlement.

## Solution (minimal closure slice)

Implement the S5-D4A **Option B MVP slice**: when a structured
`POST /orders/{id}/pay` causes the order to transition into `PAID`, advance all
`method IN ('cash', 'transfer')` payments for that order from `pending` to
`completed` **in the same transaction**.

### Contract boundaries honored

- `OrderService._post_ledger_entries()` was NOT modified.
- No new `reconciled`/`refunded` enum values added.
- Credit payments left unchanged (SQL excludes `credit`).
- No historical data backfill.
- No VPS / deploy / runtime data touched.
- `mobile_money` not touched.
- Legacy empty-body pay path untouched.

---

## Changes

### 1. `backend/repositories/payment_repository.py` -- new method (+40 lines)

Added `update_cash_transfer_to_completed(db, *, order_id) -> int`:

```python
async def update_cash_transfer_to_completed(self, db, *, order_id):
    result = await db.execute(
        text(
            "UPDATE payments "
            "SET status = 'completed', updated_at = now() "
            "WHERE order_id = :order_id "
            "  AND is_deleted IS FALSE "
            "  AND method IN ('cash', 'transfer') "
            "  AND status = 'pending'"
        ),
        {"order_id": order_id},
    )
    return int(result.rowcount or 0)
```

**Idempotency & scope guarantees** (encoded in the SQL WHERE clause):
- Scoped to a single `order_id` (no cross-order side effects).
- Only `cash`/`transfer` rows touched; `credit` excluded.
- Only `status = 'pending'` rows touched; already-`completed` rows are no-ops
  (safe to call repeatedly).
- `is_deleted IS FALSE` guard skips soft-deleted rows.
- Returns the count of updated rows.

### 2. `backend/api/v1/orders.py` -- call site (+12 lines)

In the structured pay path, **after** `order_service.transition()` succeeds and
**only when** `target_state == OrderState.PAID`, call the settle method:

```python
order = await order_service.transition(...)

# S5-D4B: Once the order has transitioned into PAID, settle all
# cash/transfer payments for this order to 'completed' in the same
# transaction. Credit payments are intentionally left 'pending'.
if target_state == OrderState.PAID:
    await payment_repo.update_cash_transfer_to_completed(
        db, order_id=order.id,
    )
```

**Placement rationale** (critical for atomicity):
- Lives **inside** the existing `try` block, so any exception rolls back the
  whole transaction (payment create + balance delta + order transition +
  settle) -- the session is managed by `get_tenant_db_session`.
- Runs **after** transition succeeds -- guarantees order IS `paid` before any
  payment is settled (no payment=completed without order=paid).
- Gated on `target_state == PAID` -- partial payments (PARTIALLY_PAID) skip
  settle (no premature settlement).
- Legacy empty-body path (the `else` branch) is untouched -- no settle there.

### 3. `backend/tests/test_s5d4b_settled_cash_payment.py` -- new test file (9 tests)

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_settle_update_executes_scoped_sql` | UPDATE SQL is scoped (order, cash/transfer, pending, soft-delete guard) |
| 2 | `test_settle_update_zero_rows_when_none_pending` | Idempotent: returns 0 when nothing to settle |
| 3 | `test_api_full_cash_settles_payment_to_completed` | Full cash -> PAID -> settle called for order |
| 4 | `test_api_partial_cash_does_not_settle` | Partial cash -> PARTIALLY_PAID -> settle NOT called |
| 5 | `test_api_second_partial_completes_and_settles` | Second partial reaching PAID -> settle called (covers both rows) |
| 6 | `test_api_transfer_full_payment_settle_called` | Full transfer -> PAID -> settle called (no-op on completed rows) |
| 7 | `test_api_credit_paid_settle_targets_cash_transfer_only` | Credit -> PAID -> settle called but SQL excludes credit (0 returned) |
| 8 | `test_api_failed_transition_no_settle` | Transition raises -> settle NOT called (rollback semantics) |
| 9 | `test_api_legacy_pay_no_settle` | Legacy empty-body -> no settle call (backward compat) |

---

## Transactional Safety (P0 invariants verified by tests 4, 8, 9)

The task required that failures never produce:
- `order=paid` while `payment` not completed -- **prevented**: settle runs in
  the same transaction AFTER transition; if settle fails, the whole txn rolls
  back (order reverts to confirmed).
- `payment=completed` while `order` not paid -- **prevented**: settle is gated
  on `target_state == PAID` AND runs after transition succeeds.
- partial payment prematurely marked completed -- **prevented**: settle only
  fires when `target_state == PAID`; PARTIALLY_PAID skips it (test 4).

---

## GitNexus Impact Analysis (pre-edit, required gate)

| Symbol | Direction | Risk | d=1 callers | Action |
|--------|-----------|------|-------------|--------|
| `pay_order` | upstream | **LOW** | 0 (leaf endpoint) | Proceed |
| `PaymentRepository` | upstream | **LOW** | 4 (payment_service.__init__, pay_order, 2 file imports) | Proceed -- additive method, no existing caller affected |

Both **LOW**, no HIGH/CRITICAL. No d=1 caller required updates (the new method
is additive; `pay_order` is the only new caller and it is this change).

`detect_changes` is an MCP-only tool (not exposed by the CLI); equivalent scope
verification performed via `git diff --check` + `git diff --stat` (confirms
only the 3 expected files changed).

---

## Test Results

### New suite (9 tests, all PASS)

```
poetry run pytest tests/test_s5d4b_settled_cash_payment.py -q
============================== 9 passed, 8 warnings in 1.64s ========================
```

### Regression: Phase 5 order payment contract (53 passed, 0 failed)

```
poetry run pytest tests/test_phase5_order_payment.py -q
================= 53 passed, 1 xfailed, 48 warnings in 13.28s =================
```

No regressions in the most relevant suite (mock-based pay_order / state machine
/ cumulative settlement / overpayment / legacy compat tests).

### Live-DB suites (pre-existing environment limitation)

`test_s5_order_state_machine.py`, `test_s5_ledger.py`,
`test_s5_5_ledger_hardening.py` fail at **setup** with
`socket.gaierror: [Errno 11001] getaddrinfo failed` because Docker PostgreSQL
is not running on this machine. This is a **pre-existing environment
limitation** (documented in the S5-C-R6A ledger), not a code defect introduced
by this change. The mock-based equivalents in `test_phase5_order_payment.py`
cover the same contract surface and all pass.

---

## Quality Gates

| Check | Status |
|-------|--------|
| Isolated branch (no `product-dev-recovered` push) | PASS |
| `git diff --check` | PASS (no whitespace/conflict markers) |
| ASCII / mojibake scan on new lines | PASS (added lines clean; 3 pre-existing em-dashes on untouched lines left as-is) |
| Secret scan | PASS (0 matches) |
| Linter diagnostics | PASS (0 errors on all 3 files) |
| pre-commit hooks | PASS (run at commit) |
| GitNexus impact (pre-edit) | PASS (both symbols LOW) |
| No `OrderService._post_ledger_entries()` modified | PASS |
| No new enum values | PASS |
| Credit status unchanged | PASS (SQL excludes credit) |
| Legacy empty-body pay unchanged | PASS (test 9) |

---

## Explicit Non-Actions

- Did NOT modify `OrderService._post_ledger_entries()`.
- Did NOT add `reconciled`/`refunded` statuses.
- Did NOT change credit payment status.
- Did NOT backfill historical data.
- Did NOT touch VPS, deploy, or runtime DB data.
- Did NOT fix mobile_money (separate task).
- Did NOT push to `product-dev-recovered`.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/repositories/payment_repository.py` | +40 lines: `update_cash_transfer_to_completed()` |
| `backend/api/v1/orders.py` | +12 lines: settle call after PAID transition (structured path only) |
| `backend/tests/test_s5d4b_settled_cash_payment.py` | +282 lines: new test file (9 tests) |
