# S5-A: Fresh Tenant Real User Journey Gate

| Field | Value |
|-------|-------|
| Date | 2026-06-24 |
| Branch | `opencode/s5a-r1-fresh-tenant-returned-bootstrap-fix-2026-06-24` |
| Base | `origin/product-dev-recovered` @ `5ea95fd` (`merge: S4-G migration infrastructure hardening`) |
| Verdict | PASS_FOR_CTO_REVIEW |

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

---

## S5-A-R1 Fix

S5-A-R1 fixed the concrete product defect found by the S5-A blocker audit:

- `backend/scripts/bootstrap_tenant_schema.py` now creates fresh tenant-local `order_status` with `returned`.
- `backend/scripts/bootstrap_tenant_schema.py` now reconciles existing tenant-local enums with `ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'returned'`.
- `backend/scripts/seed_demo_data.py` now uses the same fresh/reconcile behavior, preventing demo bootstrap drift.
- `backend/tests/conftest.py` now uses the same enum value and reconciliation so test schema bootstrap no longer manufactures false returned failures.
- `backend/tests/test_s5a_fresh_tenant_real_user_journey_gate.py` now restores the full real-DB S5-A journey gate.

No `OrderService.transition()`, inventory service, ledger service, or Alembic migration logic was changed. Migration 016 already adds `returned`; the defect was bootstrap drift, not migration drift.

The existing `backend/tests/setup_test_schema.py` also contains an older hand-written `order_status` list, but it is outside the allowed S5-A-R1 edit scope. No validation run in this task required modifying it.

---

## S5-A-R1 GitNexus Impact

Pre-edit upstream impact:

```text
bootstrap() in backend/scripts/bootstrap_tenant_schema.py
risk: HIGH
direct: 8
processes_affected: 1
modules_affected: 3

_bootstrap_tenant_schema() in backend/scripts/seed_demo_data.py
risk: LOW
direct: 1
processes_affected: 1

_bootstrap_tenant_test_schema() in backend/tests/conftest.py
risk: LOW
direct: 1
processes_affected: 1
```

Reason for continuing despite HIGH impact: `bootstrap()` is the shared fresh-tenant entry point and the change is a minimal additive enum reconciliation required to align fresh bootstrap with existing `OrderStatus.RETURNED` and Alembic migration 016. The change does not remove or rename any status and should be backward compatible for existing tenants.

Pre-commit `gitnexus_detect_changes(scope="unstaged")` after final ledger update:

```text
risk_level: high
changed_files: 5
changed_count: 37
affected_count: 10
affected_processes:
- Main -> _column_exists
- Main -> _table_exists
- Main -> _column_is_nullable
- Main -> _index_definition
- Main -> _normalize_sql
- Main -> Get
- Main -> Soft_delete
- Main -> _bootstrap_tenant_test_schema
- Main -> _set_search_path
- Seed -> Derive_schema_from_id
```

---

## S5-A-R1 Exact Test Results

S5-A fresh tenant real user journey gate:

```text
poetry run pytest tests/test_s5a_fresh_tenant_real_user_journey_gate.py -q -rxX --tb=short
3 passed, 15 warnings
```

S4-F closeout regression:

```text
poetry run pytest tests/business/test_s4f_business_invariant_closeout.py -q -rxX --tb=short
8 passed, 18 warnings
```

S4 jobs selector:

```text
poetry run pytest tests -q -k "s4_jobs or jobs" -rxX --tb=short
16 passed, 1236 deselected, 525 warnings
```

S5/Phase5 regression:

```text
poetry run pytest tests/test_s5_order_state_machine.py tests/test_phase5_order_payment.py -q -rxX --tb=short
66 passed, 1 xfailed, 45 warnings
```

U1/S3 fresh tenant bootstrap consumers:

```text
S3C_REQUIRE_LIVE_DB=1 poetry run pytest tests/test_u1r1_bootstrap_completeness.py tests/test_s3c_self_contained_fresh_tenant_live_proof.py -q -rxX --tb=short
27 passed, 6 xfailed, 93 warnings
```

Hygiene:

```text
git diff --check
PASS

Changed-line ASCII/mojibake scan
PASS
```

Pre-commit hooks: pending final commit execution.
