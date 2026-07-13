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
