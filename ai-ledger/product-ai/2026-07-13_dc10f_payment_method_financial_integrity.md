# DC-10F Payment Method Financial Integrity

Date: 2026-07-13
Branch: opencode/dc10f-payment-method-financial-integrity-2026-07-13
Base: 547b0b294aa387d6179f53eca3ec162532a1e29e

## Scope

Fix the order payment write path so only canonical payment methods can affect payment rows, receivable balances, order state transitions, and ledger behavior.

Canonical methods:

- cash
- transfer
- credit

## GitNexus Impact

Repository index: dc10f-payment-method-financial-integrity

- PayOrderRequest: LOW, 2 direct upstream references, 0 affected processes.
- pay_order: LOW, 0 upstream references, 0 affected processes.
- PaymentMethod: LOW, 1 direct upstream reference, 0 affected processes.
- PaymentRecordModal: LOW, 0 upstream references, 0 affected processes.

## RED Proof

Command:

```text
poetry run pytest tests/test_dc10f_payment_method_integrity.py -q
```

Result before fix:

```text
2 failed, 1 passed
```

Failures proved:

- PayOrderRequest accepted method="banana".
- pay_order did not reject method="banana" before financial side effects.

## Fix

- Reused backend schemas.payment.PaymentMethod enum in PayOrderRequest.
- Added a defensive pay_order method allowlist before paid-total lookup, payment insert, receivable delta, order transition, or ledger behavior.
- Normalized enum values to strings before repository/service calls.
- Added migration 032_payment_method_integrity with tenant payments.method CHECK constraint.
- Updated PaymentRecordModal so Mobile Money submits canonical method="transfer" with label "Bank Transfer / Mobile Money".
- Tightened frontend PayOrderData.method to 'cash' | 'transfer' | 'credit'.

## Migration Validation

Disposable Postgres: dc10f_pg_547b0b29 on 127.0.0.1:55434

Public migration to head:

```text
poetry run alembic upgrade head
```

Result:

```text
Running upgrade 031_legacy_tenant_reconciliation -> 032_payment_method_integrity
```

Tenant constraint check after staging a tenant payments table at version 031:

```text
ck_payments_method_canonical | CHECK (((method)::text = ANY ((ARRAY['cash'::character varying, 'transfer'::character varying, 'credit'::character varying])::text[])))
```

Invalid insert verification:

```text
ERROR: new row for relation "payments" violates check constraint "ck_payments_method_canonical"
DETAIL: Failing row contains (..., banana).
```

Preflight behavior with existing invalid data was also verified with --raiseerr: migration raises a RuntimeError before adding the constraint when non-canonical method rows exist.

## Validation

Backend:

```text
poetry run pytest tests/test_dc10f_payment_method_integrity.py tests/test_phase5_order_payment.py tests/test_s6b_payment_write_path_unification.py -q
57 passed, 1 xfailed, 58 warnings
```

Python compile:

```text
poetry run python -m py_compile schemas/order.py api/v1/orders.py alembic/versions/032_payment_method_integrity.py tests/test_dc10f_payment_method_integrity.py
PASS
```

Frontend:

```text
pnpm install --frozen-lockfile
pnpm build
PASS
```

Frontend build warnings were pre-existing/non-blocking categories: duplicate jsdom key in package.json and chunk size warning.

## Notes

- Migration 005 was not edited.
- No protected branch was pushed.
- No deployment or VPS changes were made.

## R1: Migration + Future Tenant Closure

Commit base: 5cad2e7051ebdf2a0885f093d9ec7d40f1f86482

R1 changes:

- backend/scripts/bootstrap_tenant_schema.py now creates fresh tenant payments with ck_payments_method_canonical and reconciles older bootstrapped payments tables to the same contract.
- Migration 032 no longer scans broad t_% schemas. It uses public.tenant_registrations JOIN public.wholesalers as the authoritative live registry source, mirroring migration 031 validation.
- Migration 032 validates tenant schema format, duplicate registry rows, wholesaler-derived schema match, schema existence, payments table existence, noncanonical/NULL method rows, and check-constraint compatibility before mutation.
- Unregistered rogue t_% schemas are not mutated.
- Invalid tenant_schema x-arguments fail with sanitized preflight errors.
- Equivalent legacy method checks are renamed to the canonical constraint name; incompatible same-name constraints fail closed; repeated runs are idempotent.
- Added HTTP regression proving POST /orders/{id}/pay with method="banana" returns controlled 4xx and does not enter payment, order-state, outstanding-balance, or ledger side-effect paths.
- Added frontend regression proving "Bank Transfer / Mobile Money" submits method="transfer" and no mobile_money option value remains in the payment request path.

Domain risk note:

- Payment/order/ledger integrity is treated as CRITICAL domain risk even when GitNexus file/symbol mapping reports LOW.

R1 validation evidence:

```text
poetry run python -m py_compile alembic/versions/032_payment_method_integrity.py scripts/bootstrap_tenant_schema.py tests/test_dc10f_payment_method_integrity.py tests/test_dc10f_r1_payment_method_migration.py
PASS
```

```text
poetry run pytest tests/test_dc10f_payment_method_integrity.py -q
4 passed, 30 warnings
```

```text
poetry run pytest tests/test_dc10f_r1_payment_method_migration.py -q
10 passed
```

```text
poetry run alembic upgrade head
PASS; reached 032_payment_method_integrity
```

```text
poetry run pytest tests/test_dc10f_payment_method_integrity.py tests/test_dc10f_r1_payment_method_migration.py tests/test_phase5_order_payment.py tests/test_s5d4b_settled_cash_payment.py tests/test_s5d5_payment_ledger_runtime_invariant.py tests/test_s5d6_multi_partial_payment_state_machine.py -q
86 passed, 1 xfailed, 168 warnings
```

```text
poetry run pytest tests/test_s4g_migration_infrastructure_hardening.py -q
5 passed
```

```text
poetry run alembic current
032_payment_method_integrity (head)
```

```text
poetry run alembic heads
032_payment_method_integrity (head)
```

```text
pnpm vitest run src/tests/PaymentRecordModal.test.tsx
1 passed
```

```text
pnpm build
PASS
```

Frontend build warnings remain pre-existing/non-blocking categories: duplicate jsdom key in package.json and chunk size warning.

GitNexus note:

- npx gitnexus_detect_changes compare --base origin/product-dev-recovered failed because gitnexus_detect_changes is not available as an npm package in this environment.
- npx gitnexus analyze before the R1 commit reported already up to date at 5cad2e7; final branch-tip analyze/status evidence is captured after commit in the R1 handoff.
