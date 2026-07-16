# DC-11T1-V1A-R1 Platform Durable Approval Forensics

## Verdict

`PASS_DC11T1_V1A_R1_CLASSIFICATION_COMPLETE`

The 53-node durable approval inventory is fully classified with gap zero:

| Classification | Nodes |
| --- | ---: |
| `TEST_INFRASTRUCTURE` | 46 |
| `STALE_TEST_CONTRACT` | 7 |
| `CURRENT_PRODUCT_DEFECT` | 0 |
| `ENVIRONMENT_GATED` | 0 |
| total | 53 |

R1 replaces the original weak statement that 44 nodes merely depended on an
unknown external suite state. A controlled primer/order matrix now reproduces
the exact failure mechanism and its negative control.

## Scope

- Code baseline: `7a972d1dca944db3476c405b807ddb5313f5ef95`
- Inventory evidence: `67d2696b1b89cbf1ed6cda686797d395b8ef7801`
- Original V1A report commit: `7c0aa934baa9bf5fde05cd9104dbe8166358c0ca`
- R1 branch: `codex/dc11t1-v1a-r1-durable-approval-forensics-2026-07-16`
- Product code, migrations, tests, configuration, and lockfiles changed by R1: none

The 53 inventory nodes are:

| File | Nodes |
| --- | ---: |
| `tests/test_platform_p21_durable_approval_adapter_implementation.py` | 19 |
| `tests/test_platform_p21dd_runtime_storage_cutover_gate.py` | 25 |
| `tests/test_platform_p21_durable_approval_migration.py` | 6 |
| `tests/test_platform_p21e_durable_approval_runtime_closeout.py` | 2 |
| `tests/test_platform_p21_durable_approval_adapter_skeleton.py` | 1 |

## Environment

- Windows 11 disposable Git worktree
- Python 3.12.10
- pytest 8.4.2
- fresh PostgreSQL 16 and Redis 7 per gate run
- single Alembic head `034_platform_operators`
- canonical `t_test` and `t_dev` bootstrapped before pytest
- repository gate: `backend/scripts/dc11t0_deterministic_gate.py`
- every run removed its containers, volumes, and network

The R4 full-run artifacts remained intact under the local temporary artifact
directory. They were used only to identify the exact traceback and test order;
no raw full-suite artifact was committed.

## Source Facts

The current durable approval migration is:

- `backend/alembic/versions/029_durable_approval_store.py`
- revision `029_durable_approval_store`
- down revision `028_owner_credential_setup_tokens`

The stale migration test instead pins:

- head `020_durable_approval_store`
- base `019_platform_audit_logs`

The test calls Alembic directly. Alembic's environment uses `asyncio.run()`,
which creates and closes an event loop. If pytest-asyncio has already installed
its session loop, the direct call clears the current loop for later async
tests. The repository already provides `tests.conftest.run_alembic_upgrade()`
to preserve the loop, but the stale migration tests bypass that wrapper.

## Independent Baselines

Each file was run in a separate process with fresh infrastructure:

| File | Result |
| --- | ---: |
| adapter implementation | 23 passed |
| runtime storage cutover | 36 passed |
| migration | 6 failed |
| runtime closeout | 8 passed |
| adapter skeleton | 31 passed, 1 failed |

The 46 async runtime nodes pass when the event loop is healthy. The seven
remaining failures reproduce without relying on product runtime behavior.

## R4 Raw Evidence

Both deterministic R4 full runs classified the same 53 inventory nodes as
failed. The raw traceback for all 46 runtime nodes failed inside
`pytest_asyncio` before the test body:

`RuntimeError: There is no current event loop in thread 'MainThread'.`

The first durable adapter surface-only test is synchronous and passed. The
next 19 adapter runtime nodes, 25 storage cutover runtime nodes, and first two
P21E restart-safety nodes are async and failed at loop acquisition. This
status shape is consistent with a harness failure, not a durable approval
assertion failure.

## Causal Order Matrix

### Primer Definition

The primer was one known-good async registry node:

`tests/test_platform_p17dc_backup_registry_read.py::TestLoadBackupStatusMap::test_empty_tenant_ids`

Its only purpose was to make pytest-asyncio establish the session loop before
the direct Alembic calls, matching the state of the full suite at the P17/P21
migration boundary.

### Full V1A Matrix

Forward order:

1. async primer
2. stale P17 migration file with direct Alembic calls
3. adapter implementation
4. runtime storage cutover
5. P21E runtime closeout

Result:

- 77 collected
- 22 passed
- 55 failed
- 9 failures were the stale P17 migration file
- exactly 46 failures were the V1A runtime nodes: 19 + 25 + 2
- all 46 carried the no-current-event-loop mechanism

Reverse control:

1. async primer
2. adapter implementation
3. runtime storage cutover
4. P21E runtime closeout
5. stale P17 migration file

Result:

- 77 collected
- 68 passed
- 9 failed
- all 46 V1A runtime nodes passed
- only the stale P17 migration failures remained
- no no-current-event-loop traceback occurred before V1A completed

This directionality is the missing causal proof. Moving the same direct
Alembic file across the unchanged V1A nodes changes all 46 V1A outcomes while
leaving the migration failures stable.

### P21E-Specific Matrix

Forward order `primer -> P21 migration -> P21E`:

- 15 collected
- 7 passed
- 8 failed
- 6 migration contract failures
- exactly 2 P21E no-loop failures

Reverse order `primer -> P21E -> P21 migration`:

- 15 collected
- 9 passed
- 6 failed
- both P21E nodes passed
- only the six migration contract failures remained

The two P21E nodes therefore have the same concrete infrastructure mechanism,
triggered directly by their adjacent stale P21 migration tests.

## Classification Findings

### 46 TEST_INFRASTRUCTURE

The 19 adapter, 25 cutover, and 2 closeout nodes are classified
`TEST_INFRASTRUCTURE` because all of the following are proven:

1. Their R4 failure occurs in pytest-asyncio before test-body execution.
2. Every node passes independently on fresh PostgreSQL 16 and Redis 7.
3. A primer followed by direct Alembic migration calls reproduces all 46
   failures without changing product code, schema source, or assertions.
4. Reversing only the order makes all 46 pass.
5. The failure text is the exact missing-current-loop error documented by the
   repository's event-loop preservation helper.

This does not weaken, skip, or xfail any durable approval assertion.

### 6 STALE_TEST_CONTRACT

All six nodes in
`tests/test_platform_p21_durable_approval_migration.py` are stale because they
request revision `020_durable_approval_store` and downgrade target
`019_platform_audit_logs`. Those are not the current durable approval chain.
Alembic rejects the requested historical path before the intended schema
assertions run.

### 1 STALE_TEST_CONTRACT

The skeleton node asserts that
`backend/alembic/versions/020_durable_approval_store.py` exists. The actual
migration is `029_durable_approval_store.py`; the file assertion is obsolete.

## Independent Review Correction

The independent review correctly rejected the original V1A rationale for the
44 adapter/cutover nodes because isolated PASS alone did not identify a
pollution source. R1 accepts that correction. The primer/order matrix above is
new evidence and closes that exact gap.

The independent review also corrected the migration facts to revision 029
over 028. R1 uses those exact facts and does not rely on stale `migration 020`
comments in model documentation.

## Accounting

| File | Infrastructure | Stale | Product defect | Env gated | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| adapter implementation | 19 | 0 | 0 | 0 | 19 |
| runtime storage cutover | 25 | 0 | 0 | 0 | 25 |
| migration | 0 | 6 | 0 | 0 | 6 |
| runtime closeout | 2 | 0 | 0 | 0 | 2 |
| adapter skeleton | 0 | 1 | 0 | 0 | 1 |
| total | 46 | 7 | 0 | 0 | 53 |

Accounting: `46 + 7 + 0 + 0 = 53`, gap `0`.

## Boundaries

- No product code was edited.
- No migration was edited.
- No test was edited, skipped, xfailed, or weakened.
- No protected branch was pushed.
- No raw credentials, tokens, database URLs, or customer data were recorded.
- Disposable infrastructure cleanup completed after every run.

## Final Decision

`PASS_DC11T1_V1A_R1_CLASSIFICATION_COMPLETE`

No current durable approval product defect was reproduced. This closes only
the 53-node V1A classification and does not claim that the whole repository or
delivery candidate is fully green.
