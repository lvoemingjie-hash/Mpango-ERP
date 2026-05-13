# Phase 6.1 — Credit Ledger Semantics Fix

## Metadata

| Field | Value |
|-------|-------|
| Worktree | `C:\Users\Jeff0\MPANGO ERP\phase6-credit-mvp-2026-05-13` |
| Branch | `codex/phase6-credit-payment-mvp-2026-05-13` |
| Base commit | `555f340 docs(ai): record phase6 credit payment acceptance` |
| Date | 2026-05-13 |

## CTO Instruction Compliance

| Instruction | Status |
|-------------|--------|
| Do not push | COMPLIANT — no push |
| Do not commit unless told by CTO | COMPLIANT — changes left unstaged |
| Do not touch platform, auth, tenancy, billing, UI, credit limits, aging, partial credit, split tender, returns, cancellation | COMPLIANT — only touched `OrderService.transition`, `_post_ledger_entries`, and `pay_order` structured path |
| Do not broad-rewrite order state machine or accounting model | COMPLIANT — single optional parameter, guard clause in `_post_ledger_entries` |
| Preserve default behavior for all existing callers | COMPLIANT — `payment_method: Optional[str] = None` default preserves all existing call sites |
| Run GitNexus impact before editing | COMPLIANT — see results below |

## GitNexus Impact Analysis

### `transition` — HIGH RISK (37 impacted, 23 direct callers)

| Metric | Value |
|--------|-------|
| Risk | HIGH |
| Direct callers (d=1) | 23 (test files + API handlers + seed script) |
| Processes affected | `fulfill_order`, `return_order`, `seed` |
| Modules affected | Tests (36 hits), Scripts (1 hit) |

**HIGH-risk mitigation**: The change is default-preserving. `payment_method: Optional[str] = None` is a new optional parameter with default `None`. All 23 existing callers pass no `payment_method` argument, so they receive `None` and execute the exact same code path as before. Only the `pay_order` structured payment path (a single call site) passes `payment_method=payment_input.method`. No callers are broken by this addition.

### `_post_ledger_entries` — LOW RISK (24 impacted, 1 direct caller)

| Metric | Value |
|--------|-------|
| Risk | LOW |
| Direct caller (d=1) | `transition` (same file) |
| Processes affected | `fulfill_order`, `return_order` |

Only `transition` calls `_post_ledger_entries`. The new `payment_method` parameter is threaded from `transition` and defaults to `None`. The guard clause `if payment_method == "credit"` only fires when explicitly set, preserving all existing behavior.

### `pay_order` — LOW RISK (0 impacted from crud layer)

The GitNexus analysis found `backend/crud/order.py:pay_order` (deprecated) with 0 upstream callers. The real target is `backend/api/v1/orders.py:pay_order` which is the active endpoint.

## Files Changed

| File | Change |
|------|--------|
| `backend/services/order_service.py` | Added `payment_method: Optional[str] = None` to `transition()` and `_post_ledger_entries()`. Credit PAID skips `post_payment_received()`. |
| `backend/api/v1/orders.py` | Structured payment path passes `payment_method=payment_input.method` to `transition()`. Legacy path unchanged. |
| `backend/tests/test_phase5_order_payment.py` | Added 7 tests: 3 verifying `payment_method` passthrough (credit/cash/legacy), 4 mock-based `_post_ledger_entries` tests (credit skips, default calls, cash calls, transfer calls). |
| `backend/tests/test_s5_ledger.py` | Added 3 DB-integration tests for credit PAID ledger behavior (requires DB-capable validation). |
| `ai-ledger/product-ai/2026-05-13_phase6_credit_ledger_semantics_fix.md` | This audit ledger. |

**Tracked code/test diff stats before ledger**: 4 files changed, 451 insertions(+), 16 deletions(-).

## Behavior Before / After

### Before (BUG)

1. `pay_order(method="credit")` → `OrderService.transition(... target_state=PAID)`
2. `_post_ledger_entries()` blindly calls `LedgerService.post_payment_received()` for every PAID transition
3. Ledger shows: CASH +100, RECEIVABLE -100 (settlement) — looks like cash was received
4. Receivable exposure from confirmation is erased from the balance view
5. Finance summary incorrectly shows no outstanding receivable for credit sales

### After (FIX)

1. `pay_order(method="credit")` → `OrderService.transition(..., payment_method="credit")`
2. `_post_ledger_entries(payment_method="credit")` skips `post_payment_received()` for credit PAID
3. Ledger shows: RECEIVABLE +100 (from confirmation only) — no cash settlement
4. Receivable exposure remains visible on the ledger
5. Finance summary correctly shows outstanding receivable for credit sales
6. All existing callers (cash, transfer, legacy) still get `post_payment_received()` as before

### Default Behavior Preserved

| Caller | `payment_method` value | Ledger behavior |
|--------|----------------------|-----------------|
| Legacy empty-body pay | `None` (default) | `post_payment_received()` called — same as before |
| Cash structured pay | `"cash"` | `post_payment_received()` called — same as before |
| Transfer structured pay | `"transfer"` | `post_payment_received()` called — same as before |
| Credit structured pay | `"credit"` | `post_payment_received()` SKIPPED — fix applied |
| `fulfill_order` transition | `None` (default) | Unaffected — CONFIRMED→PAID not used |
| `return_order` transition | `None` (default) | Unaffected — RETURNED path unchanged |
| `seed_demo_data` | `None` (default) | Unaffected |

## Tests Run — Exact Results

### `test_phase5_order_payment.py` (mock-based, no DB required)

```
$ REPORTING_USER_PASSWORD=test_reporting_password PYTHONIOENCODING=utf-8 \
  poetry run pytest tests/test_phase5_order_payment.py -q --tb=short

53 passed, 1 xfailed, 48 warnings in 13.18s
```

**New tests (all passing):**
- `test_credit_payment_passes_method_to_transition` — credit pay passes `payment_method="credit"` to `OrderService.transition`
- `test_cash_payment_passes_method_to_transition` — cash pay passes `payment_method="cash"` to `OrderService.transition`
- `test_legacy_pay_passes_no_payment_method_to_transition` — legacy pay omits `payment_method` (default `None`)
- `test_post_ledger_entries_credit_paid_skips_payment_received` — credit PAID does NOT call `LedgerService.post_payment_received`
- `test_post_ledger_entries_default_paid_calls_payment_received` — default PAID still calls `post_payment_received`
- `test_post_ledger_entries_cash_paid_calls_payment_received` — cash PAID calls `post_payment_received`
- `test_post_ledger_entries_transfer_paid_calls_payment_received` — transfer PAID calls `post_payment_received`

**Pre-existing xfail:** `test_route_overpayment_rejected_with_400` — known mock complexity issue, unrelated.

### `test_s5_ledger.py` (DB integration, requires PostgreSQL)

```
collected 15 items — ALL ERRORED

ERROR: socket.gaierror: [Errno 11001] getaddrinfo failed
```

All 15 tests (12 pre-existing + 3 new) fail at fixture setup due to PostgreSQL not being reachable from this environment. This run does not prove the DB integration tests pass. The mock-based tests in `test_phase5_order_payment.py` provide local behavioral coverage; DB-capable validation remains required before final promotion.

## Git Status

```
 M backend/api/v1/orders.py
 M backend/services/order_service.py
 M backend/tests/test_phase5_order_payment.py
 M backend/tests/test_s5_ledger.py
?? ai-ledger/product-ai/2026-05-13_phase6_credit_ledger_semantics_fix.md
```

All changes unstaged at Claude handoff. No commit made by Claude.

## Commit / Push Status

- **Commit**: NOT DONE (awaiting CTO instruction)
- **Push**: NOT DONE (governance: do not push)

## Verdict

**READY_FOR_CTO_REVIEW**

The fix is minimal (4 tracked code/test files plus this ledger, 1 optional parameter, 1 guard clause), default-preserving (all 23 existing `transition` callers unaffected), and locally validated with 7 new mock-based tests (all passing). The credit ledger gap is closed at the unit/seam level: credit PAID transitions no longer create spurious cash-settlement entries, keeping receivable exposure visible on the ledger. DB-capable validation is still required for the new integration tests.
