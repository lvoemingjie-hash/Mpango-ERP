# DC-10L Order Status Enum Reconciliation

Date: 2026-07-14

## Verdict

PASS_FOR_CTO_DC10L_REVIEW

## Baseline

- Branch base: `origin/product-dev-recovered`
- Base commit: `280c5629ee46efbcb9b890c105320bfdac8bc694`
- Implementation branch:
  `codex/dc10l-order-status-enum-reconciliation-2026-07-14`
- OPS evidence:
  `ai-ledger/ops/2026-07-13_dc10k_r3_post_rotation_credential_lifecycle_smoke.md`

## Production Symptom

DC-10K-R3 confirmed that the post-rotation credential lifecycle worked, but
`GET /api/v1/finance/receivables/orders?page=1&size=20` returned HTTP 500.
The sanitized runtime classification was a database programming / enum
coercion failure.

## Root Cause

The Python `OrderStatus` contract and fresh tenant bootstrap support these
canonical values:

- `draft`
- `confirmed`
- `partially_paid`
- `paid`
- `fulfilled`
- `cancelled`
- `voided`
- `returned`

Some legacy tenant schemas were created before the full state machine existed.
Their schema-local PostgreSQL `order_status` enum can contain
`partially_paid` while still missing `paid`, `fulfilled`, and `voided`.

The Finance receivable-orders query binds `confirmed`, `partially_paid`, and
`paid` as enum parameters. PostgreSQL rejects `paid` before evaluating rows
when the tenant enum lacks that value. A real PostgreSQL 15 reproduction
produced:

`invalid input value for enum order_status: "paid"`

This explains why the Finance summary could return 200 while the order list
returned 500: the two queries bind different status sets.

## Implementation

### Forward Migration 033

Added:

`backend/alembic/versions/033_order_status_enum_reconciliation.py`

The migration:

- is self-contained and imports no runtime models;
- uses `032_payment_method_integrity` as its `down_revision`;
- enumerates only live tenants from
  `public.tenant_registrations JOIN public.wholesalers`;
- validates tenant schema names and wholesaler-derived schema identity;
- requires each live tenant to have an `orders` table;
- requires `orders.status` to use the schema-local `order_status` enum;
- normalizes PostgreSQL catalog values returned as `str`, `bytes`, or
  `memoryview`;
- rejects live rows with NULL or non-canonical order status values;
- preflights every target tenant before applying any enum mutation;
- adds only missing canonical values with `ADD VALUE IF NOT EXISTS`;
- ignores unregistered and inactive tenant schemas;
- is idempotent.

Unused extra legacy enum labels are not removed. PostgreSQL enum value removal
requires a type rebuild and is outside this narrow runtime closure. The
application can write only canonical `OrderStatus` values, and the migration
fails closed if any live row currently uses a non-canonical label.

### Bootstrap Reconciliation

Updated:

`backend/scripts/bootstrap_tenant_schema.py`

Fresh schemas still create the complete canonical enum. Existing schemas now:

1. validate that `orders.status` uses the schema-local enum;
2. reject NULL or non-canonical live rows;
3. add any missing canonical enum values.

Validation occurs before enum mutation. A wrong column type cannot be silently
accepted or partially repaired.

## GitNexus Impact

Pre-edit impact for `bootstrap_tenant_schema.bootstrap` was HIGH:

- 20 direct callers;
- 33 total impacted symbols;
- affected paths were bootstrap, provisioning, scripts, and their tests.

The risk was reported before editing. The implementation did not modify API,
Finance, order, payment, or ledger service behavior. It added one forward
migration and a narrow bootstrap reconciliation step.

## DB-Backed Proof

`tests/test_dc10l_order_status_enum_reconciliation.py` provides eight tests:

1. migration self-containment and catalog byte normalization;
2. exact Finance enum-coercion reproduction and post-migration recovery;
3. second-run idempotency;
4. all-tenant preflight prevents partial mutation;
5. unregistered and inactive schemas remain unchanged;
6. wrong status column type fails closed;
7. fresh bootstrap has the complete canonical enum;
8. legacy bootstrap reconciliation and wrong-type rollback behavior.

Target result:

- `8 passed`

The key regression first reproduced the asyncpg/PostgreSQL failure, then ran
migration 033 and invoked the same `ReceivablesService.list_receivable_orders`
path successfully.

## Regression Results

- Finance runtime/API/service: `40 passed`
- Order/payment/ledger: `72 passed, 1 xfailed`
- DC-2M2, DC-10F-R1, and U1 bootstrap: `41 passed`
- Migration infrastructure: `5 passed`
- Alembic heads: `033_order_status_enum_reconciliation (head)`
- Alembic upgrade/current: passed at the same single head
- Python compile: passed

The migration-infrastructure suite initially lacked its explicit
`POSTGRES_DB`, `POSTGRES_HOST`, and related test environment variables. It
passed after those variables were supplied from the same disposable PostgreSQL
container without printing credentials.

## Scope

Changed files are limited to:

- `backend/alembic/versions/033_order_status_enum_reconciliation.py`
- `backend/scripts/bootstrap_tenant_schema.py`
- `backend/tests/test_dc10l_order_status_enum_reconciliation.py`
- `ai-ledger/product-ai/2026-07-14_dc10l_order_status_enum_reconciliation.md`

No historical migration was edited. No Finance query, order/payment behavior,
frontend, configuration, dependency, lockfile, deployment file, or protected
branch was changed.

## Rollback

PostgreSQL enum values cannot be removed safely in place. Migration 033 is
forward-only. Operational rollback requires application rollback plus restore
from the verified pre-deploy database backup. No deploy is authorized by this
implementation branch.

## Next Gate

Independent cross-environment review should verify the four-file scope, run
the DB-backed DC-10L suite, confirm one Alembic head at 033, and re-run the
Finance receivable-orders path before CTO merge approval.
