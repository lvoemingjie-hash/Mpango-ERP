# S5-D5 Payment Ledger Runtime Invariant Gate

**Date**: 2026-06-29
**Branch**: `opencode/s5d5-payment-ledger-runtime-invariant-2026-06-29`
**Executor**: OPS / opencode
**Mode**: audit first, minimal backend fix, then runtime smoke

## Verdict

**PASS_WITH_RUNTIME_DEPLOYED_SMOKE**

- Product defect confirmed: partial structured `transfer` payments were marked `completed` before the order reached `paid`, while settlement ledger entries are only written on final `paid` transition.
- Minimal backend fix deployed to the running prod-like Docker stack: structured `transfer` payments are only created as `completed` when the same request transitions the order to `paid`; otherwise they remain `pending` until final settlement.
- Local live DB/regression gate passed.
- Runtime HTTP smoke passed after backend redeploy and DB backup.
- No frontend changes, no migration, no secrets printed.

## Audit Summary

Structured `POST /api/v1/orders/{id}/pay` creates a payment row, applies retailer balance delta, transitions order state through `OrderService.transition()`, and then completes pending cash/transfer payments only when the returned order status is actually `paid`.

Ledger entries are posted by `OrderService._post_ledger_entries()` through `LedgerService.post_payment_received()` on `paid` transition. Entries are order-level (`reference_type='order'`, `reference_id=order_id`) and post cash debit plus receivable credit.

The defect was isolated to structured transfer payment creation status: every transfer row was created as `completed` immediately, even for partial payments. That made a completed payment exist before ledger coverage existed.

## Minimal Fix

Changed `backend/api/v1/orders.py` so structured transfer payment creation uses `completed` only when `target_state == OrderState.PAID`; otherwise the row remains `pending` and is completed by the final paid settlement path.

No migration was required.

## Local Validation

Command:

```text
poetry run pytest tests/test_s5d5_payment_ledger_runtime_invariant.py tests/test_s5d4b_settled_cash_payment.py tests/test_phase5_order_payment.py tests/test_payment_atomicity.py tests/b6_hardening/test_b6_payment_atomicity.py tests/test_s5_ledger.py tests/test_s5_5_ledger_hardening.py -q -rxX --tb=short
```

Result:

```text
99 passed, 1 xfailed
```

Hygiene:

```text
git diff --check HEAD~1..HEAD: PASS
pre-commit hooks during commit: PASS
GitNexus analyze: PASS, indexed commit b42cbc9
GitNexus status: up-to-date
GitNexus impact: available, but pay_order symbol resolution matched legacy backend/crud/order.py rather than the changed API route; treated as non-authoritative for this route-level change.
```

Secret scan note: broad keyword scan matched only test helper names such as `_Token` and `token=` variable usage. No secret values, JWTs, passwords, or credentials were printed or committed.

## Runtime Deployment And Smoke

DB backup was created before redeploy:

```text
backup_created=s5d5_mpango_prod_backup_20260629_194206.sql size_bytes=101692
```

Backend redeploy:

```text
docker compose -p mpango_staging_rehearsal -f docker-compose.prod.yml up -d --no-deps --build backend
mpango_prod_backend: healthy
```

Deployed code verification:

```text
/app/api/v1/orders.py contains transfer completed guard:
payment_input.method == "transfer" and target_state == OrderState.PAID
```

Runtime smoke used a unique bootstrapped tenant schema, minted a contextual super-admin test JWT inside the backend container without printing it, called the real HTTP endpoint, and verified DB rows directly.

Runtime result:

```text
S5D5_RUNTIME_SMOKE_PASS
tenant_schema=t_5add36875058477390fb985219baf070
full_cash: order_status=paid completed_count=1 completed_total=100.00 cash_debit=100.0000 receivable_credit=100.0000 settlement_sum=0.0000 settlement_entries=2
partial_cash_final: order_status=paid completed_count=2 completed_total=100.00 cash_debit=100.0000 receivable_credit=100.0000 settlement_sum=0.0000 settlement_entries=2
full_transfer: order_status=paid completed_count=1 completed_total=100.00 cash_debit=100.0000 receivable_credit=100.0000 settlement_sum=0.0000 settlement_entries=2
partial_transfer_final: order_status=paid completed_count=2 completed_total=100.00 cash_debit=100.0000 receivable_credit=100.0000 settlement_sum=0.0000 settlement_entries=2
credit_excluded: order_status=paid completed_count=0 completed_total=0 cash_debit=0 receivable_credit=0 settlement_sum=0 settlement_entries=0
```

Repeat/retry behavior:

```text
Repeated full cash payment returned an expected client error and the before/after payment plus ledger snapshot was unchanged.
```

## Notes

An initial runtime smoke attempt failed before any payment API calls because the direct seed helper used an unqualified tenant table after transaction commit reset the session search path. The rerun used schema-qualified tenant table writes and reads and passed. No secret material was printed in either attempt.

## Scope Discipline

- Frontend changed: no.
- Migration added: no.
- Product branch pushed: no.
- Secrets printed: no.
- Tests weakened or skipped: no.
