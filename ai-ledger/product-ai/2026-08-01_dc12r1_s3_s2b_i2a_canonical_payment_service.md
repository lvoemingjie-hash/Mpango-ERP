# DC-12R1-S3-S2B-I2A Canonical Payment Transaction Service Extraction

## Verdict

`PASS_FOR_CTO_DC12R1_S3_S2B_I2A_REVIEW`

## Baseline And Branch

- Baseline ref: `origin/product-dev-recovered`
- Expected baseline SHA: `9528cb6de5f668ed09feb7a1eaa9aafaa537987d`
- Verified baseline SHA before editing: `9528cb6de5f668ed09feb7a1eaa9aafaa537987d`
- Worktree: `C:\Users\Jeff0\MPANGO ERP\_codex_dc12r1_s3_s2b_i2a_2026-08-01`
- Branch: `codex/dc12r1-s3-s2b-i2a-canonical-payment-service-2026-08-01`
- Docs checkpoint commit: `1183611b`

## Scope

This slice is backend-only. No frontend, migration, permission, config, lockfile, deployment, or protected-ref changes were made.

Changed files in this slice:

- `docs/ai/CTO_CURRENT_OPS.md`
- `docs/ai/PROJECT.md`
- `backend/services/canonical_payment_service.py`
- `backend/api/v1/orders.py`
- `backend/tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py`
- `backend/tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py`
- `ai-ledger/product-ai/2026-08-01_dc12r1_s3_s2b_i2a_canonical_payment_service.md`

## Docs Checkpoint

Before product edits, a docs-only commit updated:

- `docs/ai/PROJECT.md`
- `docs/ai/CTO_CURRENT_OPS.md`

Recorded in that checkpoint:

- I1 merged at `9528cb6d`
- migration `037_payment_declarations_schema` is the sole head
- I2A is active
- design gate and schema foundation are no longer `next` or `held`
- I2B/I2C/frontend/runtime remain pending

## GitNexus Impact Before Editing

GitNexus index refreshed for this exact worktree before editing.

- `pay_order`: graph ambiguity resolved to a legacy symbol path, so it was treated as non-authoritative; effective risk forced to HIGH by task rule.
- `PaymentService`: MEDIUM in graph; treated as HIGH by task rule.
- `PaymentRepository`: LOW in graph; treated as HIGH by task rule.
- `LedgerService`: HIGH in graph.
- `OrderService.transition`: HIGH in graph.
- `_apply_outstanding_balance_delta`: LOW in graph; treated as HIGH by task rule.

Rationale: this slice touches the direct financial mutation path and therefore the effective financial blast radius is HIGH regardless of graph score.

## RED Evidence

New boundary test suite added first:

- `backend/tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py`

Initial RED proof before implementation:

- `poetry run pytest tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py -q --tb=short`
- failed with `ModuleNotFoundError: No module named 'services.canonical_payment_service'`

This proved the new service boundary did not yet exist while preserving all existing product behavior tests untouched.

## Implementation Summary

- Added `backend/services/canonical_payment_service.py`
- Implemented `CanonicalPaymentService.confirm_payment(...)`
- Added typed result `CanonicalPaymentResult`
- Added `CanonicalPaymentMutationHttpError` so the route can roll back only post-mutation `HTTPException`s and preserve pre-mutation fail-closed semantics
- Refactored `POST /api/v1/orders/{order_id}/pay` to:
  - keep request parsing, auth, permission, idempotency-key validation, prechecks, and HTTP serialization in the route
  - call the extracted service for the mutation core only
  - retain route-owned rollback/transaction handling
- `force_completed=True` is supported in the service for later declaration-confirmation use, but direct `pay_order` always calls it with `force_completed=False`
- No route-to-route calls were added
- No declaration HTTP route or declaration mutation was added in I2A

## Financial Behavior Proof

- Direct `pay_order` still performs its original prevalidation before mutation:
  - body required
  - method required/validated
  - idempotency replay/conflict
  - order lookup and lock
  - remaining balance / credit-collection checks
  - duplicate transfer reference checks
- Extracted service owns only the canonical mutation sequence:
  - create payment row
  - apply outstanding-balance delta when required
  - post cash/receivable ledger entries for credit collection
  - transition order state
  - settle pending cash/transfer rows to `completed` only when appropriate
- Service never commits, rolls back, closes, or replaces the caller session
- No float arithmetic was introduced; all money arithmetic remains `Decimal`
- No request-supplied wholesaler or retailer authority exists in the service

## GREEN Evidence

Focused new I2A suite on fresh PostgreSQL 16 / Redis 7:

- `11 passed`

Focused targeted regression bundle on fresh PostgreSQL 16 / Redis 7:

- `272 passed`, `1 xfailed`, zero failed, zero errors

Bundle included:

- new I2A suite
- payment atomicity / replay / idempotency / concurrency suites
- route payment API suites
- order state-machine suites
- ledger and receivable invariant suites
- DC-11T4H finance integrity
- S2B-I1 migration suites

## Full Backend Validation

Fresh Run A:

- PostgreSQL 16: `dc12r1_i2a_pg_a`
- Redis 7: `dc12r1_i2a_redis_a`
- Alembic current/head: sole `037_payment_declarations_schema (head)`
- Command: `poetry run pytest tests/ -q --tb=short`
- Result: `3120 passed, 48 skipped, 15 xfailed`, zero failed, zero errors

Fresh Run B:

- PostgreSQL 16: `dc12r1_i2a_pg_b`
- Redis 7: `dc12r1_i2a_redis_b`
- Alembic current/head: sole `037_payment_declarations_schema (head)`
- Command: `poetry run pytest tests/ -q --tb=short`
- Result: `3120 passed, 48 skipped, 15 xfailed`, zero failed, zero errors

Equality check:

- Run A totals exactly match Run B totals

## Additional Compatibility Repair

`backend/tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py` was updated so the legacy exact-catalog rollback/no-op proof remains pinned to `035 -> 036`, rather than implicitly following the repository `head` now that head is `037`.

This is not a migration change and does not weaken `037` coverage; `037` is already covered by the dedicated S2B-I1 suites run in this slice.

## GitNexus Detect Changes

Attempted CLI command:

- `npx gitnexus detect_changes --scope all --repo "_codex_dc12r1_s3_s2b_i2a_2026-08-01"`

Result:

- installed CLI returned `unknown command 'detect_changes'`

Fallback evidence used:

- pre-edit `gitnexus impact`
- post-edit `gitnexus analyze`
- direct changed-file scope review via git diff

## Self-Review Before Commit

1. No financial behavior drift:
   direct route prechecks were restored to their original position; service executes the same mutation sequence and parity tests compare route and service outcomes.
2. No route-to-route call:
   `pay_order` invokes `CanonicalPaymentService`, not another route handler.
3. No service-owned commit/rollback:
   explicit unit test proves the service does not call `commit()` or `rollback()`.
4. No float arithmetic:
   all payment math remains `Decimal`.
5. No declaration API accidentally added:
   I2A adds no declaration route or declaration mutation path.
6. No migration/permission/frontend/config changes:
   verified by changed-file scope.
7. Docs accurately identify I1 completed and I2A active:
   recorded in the docs-only checkpoint commit.
8. Changed-file scope is exact:
   only docs, service extraction, route refactor, focused tests, and one stale legacy migration test adjustment changed.
9. Every HIGH-risk caller has regression evidence:
   route, repository, order transition, ledger, receivable, replay, atomicity, and migration bundles all ran green.

## Hygiene

- `python -m py_compile` for changed Python: passed
- `git diff --check`: passed, with working-copy LF to CRLF warnings only
- scoped `pre-commit`: passed
- scoped `detect-secrets`: passed with empty results

## Cleanup Proof

Removed disposable validation containers:

- `dc12r1_i2a_pg_target`
- `dc12r1_i2a_redis_target`
- `dc12r1_i2a_pg_a`
- `dc12r1_i2a_redis_a`
- `dc12r1_i2a_pg_b`
- `dc12r1_i2a_redis_b`
