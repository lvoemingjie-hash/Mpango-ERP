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

## R2: Strict CHECK Semantic Equivalence Gate

Commit base: b7a717f256566604eac8e9f338adf5a70fbdcbb8

R2 changes:

- Migration 032 now reads CHECK expressions from pg_constraint/pg_get_expr plus constrained column names from conkey.
- Equivalent payment method constraints must be validated CHECK constraints, depend only on payments.method, use positive membership semantics, and contain exactly cash, transfer, and credit.
- NOT IN, negation, inequality, OR, AND/extra conditions, extra columns, and same literals on non-method columns fail closed.
- Canonical plus duplicate equivalent constraints fail closed.
- More than one equivalent legacy candidate fails closed instead of choosing by sorted name.
- A same-name canonical constraint with incompatible semantics still fails closed.
- Exactly one equivalent legacy constraint is still safely renamed to ck_payments_method_canonical.
- Future tenant bootstrap reconciliation mirrors the same strict semantic gate and duplicate policy.

R2 DB-backed test coverage added:

- method NOT IN ('cash', 'transfer', 'credit') fails closed.
- method IN (...) OR method = 'banana' fails closed.
- status IN ('cash', 'transfer', 'credit') fails closed.
- COALESCE(method IN ('cash', 'transfer', 'credit'), false) wrapper fails closed.
- canonical plus equivalent legacy duplicate fails closed.
- multiple equivalent legacy constraints fail closed.
- same canonical name with incompatible NOT IN semantics fails closed in bootstrap reconciliation.
- existing canonical constraint is a no-op.
- one equivalent legacy constraint is renamed.
- repeated migration run remains idempotent.
- canonical inserts succeed and banana insert is rejected by ck_payments_method_canonical.
- fresh bootstrap still creates the canonical constraint.

R2 validation environment:

- Disposable/local Postgres: mpango_dc10g_test_pg on 127.0.0.1:5435.
- TEST_DATABASE_URL/DATABASE_URL: postgresql://mpango_test:***@127.0.0.1:5435/mpango_erp_test.
- REDIS_URL: redis://127.0.0.1:6379/0.
- Initial un-overridden test run failed before assertions because the default test DB host postgres is not resolvable from this Windows shell; rerun used TEST_DATABASE_URL against the local mapped port.

R2 validation evidence:

```text
poetry run python -m py_compile alembic/versions/032_payment_method_integrity.py scripts/bootstrap_tenant_schema.py tests/test_dc10f_r1_payment_method_migration.py
PASS
```

```text
poetry run pytest tests/test_dc10f_r1_payment_method_migration.py -q
18 passed
```

```text
poetry run pytest tests/test_dc10f_payment_method_integrity.py -q
4 passed, 29 warnings
```

```text
poetry run pytest tests/test_phase5_order_payment.py tests/test_s5d4b_settled_cash_payment.py tests/test_s5d5_payment_ledger_runtime_invariant.py tests/test_s5d6_multi_partial_payment_state_machine.py -q
72 passed, 1 xfailed, 137 warnings
```

```text
poetry run pytest tests/test_s4g_migration_infrastructure_hardening.py -q
5 passed
```

```text
poetry run alembic upgrade head
Running upgrade 031_legacy_tenant_reconciliation -> 032_payment_method_integrity
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

```text
git diff --check
PASS; only CRLF conversion warnings
```

```text
pre-commit run --files backend/alembic/versions/032_payment_method_integrity.py backend/scripts/bootstrap_tenant_schema.py backend/tests/test_dc10f_r1_payment_method_migration.py
trim trailing whitespace: Passed
fix end of files: Passed
check yaml: Skipped (no files)
check for added large files: Passed
Detect secrets: Passed
```

```text
npx gitnexus analyze
Already up to date
```

```text
npx gitnexus status
Indexed commit: b7a717f
Current commit: b7a717f
Status: up-to-date
```

R2 verdict:

```text
PASS_FOR_CTO_DC10F_MERGE_REVIEW
```

## R3: Exact Membership Member Gate

Commit base: b7a717f256566604eac8e9f338adf5a70fbdcbb8 plus uncommitted R2 worktree.

R3 changes:

- Replaced wildcard IN/ANY matching with exact member parsing for migration 032 and bootstrap_tenant_schema.py.
- Accepted member shapes are limited to direct SQL string literals with optional PostgreSQL-generated casts.
- IN/ANY member lists must contain exactly three members and the unique member set must be exactly cash, transfer, credit.
- Explicitly fail closed for NULL members, current_user/current_role, function/expression members, ARRAY concatenation, duplicate canonical literals, fourth members, subqueries, and any nonliteral member.
- Preserved R2 duplicate policy: exactly one equivalent legacy constraint can be renamed; multiple equivalents and canonical-plus-equivalent duplicates fail closed.

R3 DB-backed test coverage added:

- CHECK (method IN ('cash', 'transfer', 'credit', NULL)) allows banana under PostgreSQL CHECK semantics, then migration rejects it as incompatible and does not rename/accept it.
- CHECK (method = ANY (ARRAY['cash', 'transfer', 'credit', NULL])) allows banana under PostgreSQL CHECK semantics, then migration rejects it as incompatible and does not rename/accept it.
- The same two NULL-member cases are proven against bootstrap reconciliation: banana is allowed before reconciliation, then bootstrap rejects the malformed constraint and leaves it unaccepted.
- CHECK (method IN ('cash', 'transfer', 'credit', current_user::text)) fails closed.
- CHECK (method = ANY (ARRAY['cash', 'transfer', 'credit'] || ARRAY[current_user::text])) fails closed.

R3 validation evidence:

```text
poetry run python -m py_compile alembic/versions/032_payment_method_integrity.py scripts/bootstrap_tenant_schema.py tests/test_dc10f_r1_payment_method_migration.py
PASS
```

```text
poetry run pytest tests/test_dc10f_r1_payment_method_migration.py -q
24 passed
```

```text
poetry run pytest tests/test_dc10f_payment_method_integrity.py -q
4 passed, 29 warnings
```

```text
poetry run pytest tests/test_phase5_order_payment.py tests/test_s5d4b_settled_cash_payment.py tests/test_s5d5_payment_ledger_runtime_invariant.py tests/test_s5d6_multi_partial_payment_state_machine.py -q
72 passed, 1 xfailed, 137 warnings
```

```text
poetry run pytest tests/test_s4g_migration_infrastructure_hardening.py -q
5 passed
```

```text
poetry run alembic upgrade head
PASS
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

```text
git diff --check
PASS; only CRLF conversion warnings
```

```text
pre-commit run --files backend/alembic/versions/032_payment_method_integrity.py backend/scripts/bootstrap_tenant_schema.py backend/tests/test_dc10f_r1_payment_method_migration.py ai-ledger/product-ai/2026-07-13_dc10f_payment_method_financial_integrity.md
trim trailing whitespace: Passed
fix end of files: Passed
check yaml: Skipped (no files)
check for added large files: Passed
Detect secrets: Passed
```

```text
npx gitnexus_detect_changes compare --staged
FAILED: npm 404 Not Found for gitnexus_detect_changes@*; requested package is unavailable in this environment.
```

R3 verdict:

```text
PASS_FOR_CTO_DC10F_MERGE_REVIEW
```
