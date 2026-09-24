# SKU delivery R2: fixture isolation repair

TASK_ID: DC-12R1-MVP-L1-SKU-DELIVERY-R2
EXECUTOR_AND_SOURCE_REVIEWER: Codex-L
VERIFICATION_EXECUTOR: ZCode (subordinate author verification, not independent acceptance)
BASE: 8e9aeb4847d392c6556c22e289f5652cb14b39bf
VERIFICATION_TIER: V3_MERGE_CRITICAL
CLAIM_CEILING: AUTHOR_FIXTURE_REPAIR_PENDING_REAL_PG_VERIFICATION

Scope: backend/tests/test_sku_bc06_reprice_guard.py; harness-governance/inventory/protocol-deltas.json; this ledger. No product/shared-bootstrap/authority/schema changes. Scope follows the founder's bounded disposition and request for Codex-L to own the repair while ZCode handles verification.

## Cause and decision

The external diagnostic full suite recorded 30 BC-06 setup errors because blanket pg_terminate_backend targeted other roles' sessions. Single-module PASS does not close this test defect. Do not grant pg_signal_backend or kill all same-role sessions. Preserve prior failed run and its environment diagnosis. Its direct pytest driver is not authority and its final rc cannot establish suite success.

## Repair

Exclusive CREATE SCHEMA with a random per-test identifier establishes ownership. Bootstrap is unchanged. Teardown drops only a successfully created schema with bounded database lock/statement and asyncio timeouts; cleanup errors surface. Engine teardown closes registered owned sessions even when a test assertion interrupts normal caller cleanup, then disposes its pool. No process termination query remains.

CHANGED_OR_ADDED_TESTS_COVERING_NEW_PATHS: one existing BC-06 module; all 22 original business test function bodies retained byte-identically. Six new test functions (seven parameterized nodes) exercise same-role/reporting-role bystanders, overlapping schema isolation, body failure with owned lock cleanup, failure after bootstrap, cleanup lock timeout propagation, and collision refusal without deleting pre-existing data.

CODE_PATH_TO_TEST_MATRIX: _bc06_schema -> all seven new nodes; _bc06_engine/_session_maker -> bystanders and body failure; _drop_bc06_schema -> timeout/collision/overlap; shared bootstrap remains an unmodified dependency.

NEGATIVE_AND_FAILURE_PATHS: no signaling privilege, no foreign session termination, duplicate schema rejected, test/setup error propagated, blocked drop raises SQLSTATE 55P03 and preserves the bystander connection.

FALSIFICATION_RESULT: pending delegated disposable-copy mutations; no current GREEN claim.
UNCOVERED_NEW_PATHS: real PG execution, reverse-order execution and full authority are pending at draft time. Abrupt OS kill is not guaranteed to clean a schema; it must be handled by task-runtime destruction and never by killing unrelated sessions.
PRODUCT_RUNTIME_RESULT: NOT_RUN_THIS_REPAIR_DRAFT

GitNexus D1 exact-node context/cypher identified pytest injection as unmodeled and bootstrap as having 50 callers. No LOW rating is invented; only fixture-local changes are made. Runtime verification and final detect_changes are required before committing this repair.
