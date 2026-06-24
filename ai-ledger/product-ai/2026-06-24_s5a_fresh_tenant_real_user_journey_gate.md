# S5-A: Fresh Tenant Real User Journey Gate

| Field | Value |
|-------|-------|
| Date | 2026-06-24 |
| Branch | `opencode/s5a-fresh-tenant-real-user-journey-gate-2026-06-24` |
| Base | `origin/product-dev-recovered` @ `5ea95fd` (`merge: S4-G migration infrastructure hardening`) |
| Verdict | NEEDS_PRODUCT_FIX |

---

## Scope

S5-A was requested as a real fresh-tenant, real-DB user journey gate covering login, admin page permissions, SKU CSV import, stock initialization, order create/confirm/pay/fulfill/return, rollback safety, and tenant isolation.

Per instruction, production code was not changed. The implementation stopped after finding a concrete product blocker that prevents the requested passing journey from being true for newly bootstrapped tenants.

---

## Product Defect

Fresh tenant bootstrap creates the tenant-local `order_status` enum without `returned`:

```text
draft, confirmed, partially_paid, paid, fulfilled, cancelled, voided
```

The real return endpoint transitions fulfilled orders to `OrderState.RETURNED` / `OrderStatus.RETURNED`. A newly bootstrapped tenant therefore cannot persist the return step required by S5-A.

Strict audit added:

- `backend/tests/test_s5a_fresh_tenant_real_user_journey_gate.py::test_fresh_tenant_bootstrap_supports_returned_order_status_for_real_return_journey`
- Uses real PostgreSQL through `scripts.bootstrap_tenant_schema.bootstrap()` and `AsyncSessionLocal`.
- Does not mock DB behavior.
- Does not skip or xfail.
- Drops the temporary tenant schema in `finally`.

Expected current result: FAIL with `STOP_AND_REPORT_CTO` until bootstrap/migration reconciliation includes `returned` for fresh tenants.

---

## Coverage Status

Requested S5-A coverage is blocked before PASS promotion:

- Fresh tenant bootstrap: audited and fails the required return-status prerequisite.
- Admin login and page permissions: not promoted because the return prerequisite is already false for fresh tenants.
- CSV import preview/validate/apply: not promoted in this branch because the run must stop on product defect.
- Stock/order/confirm/reservation/pay/fulfill/return: not promoted because the real return step cannot persist on fresh bootstrap.
- Failure rollback and tenant isolation: not promoted because the journey gate cannot pass until the fresh tenant status contract is fixed.

---

## Required Product Fix

Bring fresh tenant bootstrap and migration reconciliation into alignment with the order state machine by ensuring tenant-local `order_status` includes `returned` for both new and existing tenant schemas.

After the product fix, S5-A should continue with the full real-user journey gate rather than leaving only this strict blocker audit.

---

## Validation

Strict S5-A blocker audit:

```text
poetry run pytest tests/test_s5a_fresh_tenant_real_user_journey_gate.py -q -rxX --tb=short
1 failed

AssertionError: STOP_AND_REPORT_CTO: fresh tenant bootstrap creates order_status without 'returned'. labels=['draft', 'confirmed', 'partially_paid', 'paid', 'fulfilled', 'cancelled', 'voided']. The real return journey cannot persist OrderStatus.RETURNED until bootstrap or migration reconciliation is fixed.
```

Hygiene:

```text
git diff --check
PASS
```

```text
Changed-line ASCII/mojibake scan
PASS
```

GitNexus analyze:

```text
npx gitnexus analyze
Repository indexed successfully (16.1s)
5,676 nodes | 16,489 edges | 369 clusters | 222 flows
```

GitNexus detect_changes:

```text
scope: staged
risk_level: low
changed_files: 2
changed_count: 9
affected_count: 0
affected_processes: []
```
