# DC-11T2 Test Infrastructure and Contract Repair

Date: 2026-07-17

## Verdict

PASS_FOR_CTO_DC11T2_MERGE_REVIEW

The delivery baseline is no longer blocked by the unstable local full-suite
signal. A fresh PostgreSQL 16 database and a clean Redis 7 state produced a
zero-failure backend run at the final branch tip. Two narrow product defects
were confirmed and fixed; the remaining work in this slice repairs test
isolation, stale contracts, and explicit environment gates.

## Baseline and Branch

- Base: `d0c7c6f1a754d4ea160547e59a6dfec6ce2b451a`
- Branch: `codex/dc11t2-test-infrastructure-contract-repair-2026-07-17`
- Product migrations changed: none
- Frontend source changed: none
- Dependency and lock files changed: none
- Protected branches pushed by this task: none

## Confirmed Product Defects

### 1. Password reset tenant enumeration transaction poisoning

`PasswordResetService` scanned active tenant schemas in one outer database
transaction. If one registered tenant had a missing or damaged `users` table,
PostgreSQL aborted that transaction. Catching the exception did not recover the
transaction, so a healthy tenant later in the scan could not receive a reset
token or email.

Fix:

- Isolate each tenant query in a nested transaction/SAVEPOINT.
- Roll back only the damaged tenant query and continue neutral enumeration.
- Add a regression with one broken tenant anchor followed by a healthy tenant.

Evidence:

- `tests/test_dc3b_credential_recovery_backend.py`: 16 passed.
- The final full suite includes the new broken-anchor regression.

### 2. Redis connection URL disclosure and stale-loop shutdown

Redis initialization logged the complete configured URL. A URL may contain
credentials and must not be emitted. The process-wide Redis client could also
remain assigned when its close operation encountered a client bound to an
already-closed event loop, poisoning later tests or shutdown work.

Fix:

- Remove the Redis URL from the initialization log.
- Clear the process-wide client reference before closing.
- Use `aclose()` and tolerate only the exact already-closed-loop shutdown case.
- Re-raise unrelated runtime errors.
- Add a direct stale-loop regression.

Evidence:

- `tests/test_s3c_cache.py`: 10 passed in focused validation.
- No Redis URL or credential is included in this report.

## Test Infrastructure Repairs

- Added event-loop-preserving helpers for synchronous tests that call async
  code or Alembic.
- Removed the custom session-scoped pytest event loop that conflicted with the
  installed pytest-asyncio lifecycle.
- Replaced throwaway `asyncio.run()` calls that closed shared loops.
- Made disposable database creation use the active test server and refuse
  production-like source database names.
- Derived the reporting connection from the current disposable test database.
- Removed legacy trigger residue before the test fixture owns the ledger
  immutability trigger.
- Isolated business and Finance test data so sequence order does not change
  assertions.
- Made the S3-B prepared-live gate skip when its explicitly prepared schema is
  absent, while `S3B_REQUIRE_LIVE_DB=1` remains fail-closed.

No test was batch skipped or converted to xfail to obtain a green run.

## Stale Contract Repairs

- Updated platform durable-approval and backup tests to migrations 029 and 030.
- Replaced fixed historic backup timestamps with current freshness evidence.
- Aligned U6 onboarding tests with the active post-verification orchestration
  contract.
- Removed feature-branch-only changed-file assertions from merged-baseline
  contracts where those assertions no longer describe the product branch.
- Made ORM structure checks deterministic and limited generic base-model rules
  to models that actually inherit the relevant generic bases.
- Selected setup-token rows by expected hash rather than relying on tied
  `created_at` ordering.

## Product Areas Rechecked

The repaired suite re-exercised:

- signup, verification, onboarding, owner setup, forgot/reset, and auth;
- tenant provisioning and legacy tenant reconciliation;
- inventory reservation and business invariants;
- order, payment, ledger, and Finance receivables;
- reporting materialized views and dashboard API;
- platform backup, durable approval, controlled execution, and operator schema;
- Redis cache behavior and route authorization.

Finance cross-tenant leakage, payment integrity, onboarding orchestration, and
platform durable approval did not reproduce as current product defects after
the test environment and contracts were corrected.

## Validation Evidence

### Final backend gate

Environment:

- Fresh disposable PostgreSQL 16 database.
- Redis 7 state flushed before the run.
- UTF-8 Python execution environment.

Results:

- Alembic upgrade: passed.
- Alembic current/head: `034_platform_operators` (single head).
- Full backend: `2747 passed, 29 skipped, 15 xfailed, 0 failed, 0 errors`.
- Duration: 418.32 seconds.
- Warnings: 2205, primarily existing deprecation warnings.

The 29 skips are explicit prepared-live or external-environment gates and are
not represented as passed coverage. The 15 xfails are existing acknowledged
expectations and were not changed by this slice.

### Determinism evidence

- A clean database plus clean Redis run passed with zero failures before the
  final row-selection correction.
- A later fresh-database run exposed one U6-I6 nondeterministic token-row
  selection based on tied timestamps.
- The test now selects the row by the expected token hash.
- The exact U6-I6 test passed five consecutive executions after correction.
- The final branch-tip full run then passed with zero failures and zero errors.

One intermediate run reused Redis state and produced U6 failures. It was
rejected as invalid fresh-infrastructure evidence rather than being hidden or
classified as a product result.

### Frontend gate

- Vitest: 12 files, 88 tests passed.
- Production build: passed, 1275 modules transformed.
- Existing non-blocking warnings remain: duplicate `jsdom` package key,
  React Router future flags, test `act()` warnings, and bundle chunk size.
- `frontend/package.json` and `frontend/pnpm-lock.yaml` are unchanged.

### Static and hygiene gates

- Python compile for all changed Python files: passed.
- `git diff --check`: passed, with Windows LF/CRLF notices only.
- Added-line ASCII scan: passed.
- Mojibake scan: passed.
- GitNexus pre-commit change analysis: HIGH across 40 tracked files plus three
  new helper/evidence files; affected product flows are limited to forgot/reset
  password. No payment/order/tenant-isolation product flow expansion was found.

## Scope and Risk

The branch changes two product modules and otherwise changes test infrastructure
or test contracts. This is intentionally broader than a one-defect patch
because the delivery decision had been obscured by order-dependent failures
across platform, onboarding, Finance, reporting, and migration suites.

Residual risks:

1. Independent Linux validation is still required after merge because this
   final full run was performed on Windows.
2. Prepared-live and external gates represented by the 29 skips still require
   their own governed environments; they were not silently counted as green.
3. The frontend duplicate `jsdom` key should be removed in a separate narrow
   dependency-hygiene slice.
4. Runtime VPS smoke remains required after promotion; this task does not
   authorize deployment.

## CTO Recommendation

Merge only after an independent reviewer confirms the branch scope and reruns
the backend full suite on clean Linux PostgreSQL/Redis infrastructure. If that
cross-environment run remains zero-failure, promote through the existing
candidate process and then execute a credentialed VPS smoke. Do not start
DC-11P3/P4/P5 as part of this repair branch.
