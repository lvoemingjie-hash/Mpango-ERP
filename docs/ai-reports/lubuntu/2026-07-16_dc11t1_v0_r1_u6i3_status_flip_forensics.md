# DC-11T1-V0-R1 U6-I3 Status-Flip Forensics

**Date:** 2026-07-16  
**Branch:** `reports/dc11t1-v0-r1-u6i3-forensics-2026-07-16`  
**Source branch:** `reports/dc11t1-v0-stable-failure-inventory-2026-07-15`  
**Source commit:** `67d2696b1b89cbf1ed6cda686797d395b8ef7801`  
**Known node:** `tests/test_u6i3_owner_credential_setup_consume.py::test_invalid_or_missing_raw_token_fails_neutrally[   ]`  
**Verdict:** `PASS_DC11T1_V0_R1_STATUS_FLIP_EXPLAINED`

## Scope

Focused forensic only. I did not rerun the full suite and did not change product,
test, config, migration, or dependency files. The only tracked change is this
report.

## Environment Proof

- Remote source proof before worktree creation:
  - `67d2696b1b89cbf1ed6cda686797d395b8ef7801 refs/heads/reports/dc11t1-v0-stable-failure-inventory-2026-07-15`
- Clean disposable worktree was created from that exact commit.
- Backend Poetry probes:
  - `poetry env info --path`: `/home/ivy/Desktop/dc11t1-v0-r1-u6i3-forensics-wt/backend/.venv`
  - `poetry run python --version`: `Python 3.12.3`
  - `poetry run pytest --version`: `pytest 8.4.2`
- The Poetry environment was initially absent. `poetry env use python3.12` and
  `poetry install --no-interaction` were run.
- `backend/pyproject.toml` and `backend/poetry.lock` remained unchanged.
- Disposable infrastructure:
  - PostgreSQL image: `postgres:16`
  - Redis image: `redis:7`
  - Direct `docker run --rm` containers, random localhost ports, no named
    volumes.

## Collected Node ID

`pytest --collect-only -q tests/test_u6i3_owner_credential_setup_consume.py`
collected the exact whitespace parameter as:

`tests/test_u6i3_owner_credential_setup_consume.py::test_invalid_or_missing_raw_token_fails_neutrally[   ]`

Direct node selection was accepted by pytest.

## Required Runs

Each run used a separate pytest process and a fresh per-run database inside the
disposable PostgreSQL container. "DB setup completed" means the U6-I3 autouse
fixture completed enough setup for all three expected public tables to exist:
`wholesalers`, `tenant_registrations`, and `owner_credential_setup_tokens`.

| Run | Selection | Outcome | Phase | Exception class | Root-cause fingerprint | DB setup completed |
|---|---|---:|---|---|---|---:|
| file_run_1 | full file | PASSED | n/a | n/a | n/a | yes |
| file_run_2 | full file | PASSED | n/a | n/a | n/a | yes |
| file_run_3 | full file | PASSED | n/a | n/a | n/a | yes |
| node_ws_run_1 | exact whitespace node | PASSED | n/a | n/a | n/a | yes |
| node_ws_run_2 | exact whitespace node | PASSED | n/a | n/a | n/a | yes |
| node_ws_run_3 | exact whitespace node | PASSED | n/a | n/a | n/a | yes |

Additional focused diagnostics:

| Run | Precondition | Outcome | Phase | Exception class | Root-cause fingerprint | DB setup completed |
|---|---|---:|---|---|---|---:|
| diag_alembic_node_ws | Alembic attempted without reporting password | PASSED | n/a | n/a | Alembic precondition failed separately: `RuntimeError: REPORTING_USER_PASSWORD environment variable must be set before running this migration` | yes |
| diag_alembic_ok_node_ws | Alembic reached head with reporting password supplied | PASSED | n/a | n/a | n/a | yes |

The missing reporting password diagnostic is not a U6-I3 node failure: Alembic
failed before the test precondition, but the direct whitespace node still
passed afterward. With the reporting prerequisite supplied, migration reached
head and the exact node still passed.

## Evidence Comparison

Available V0 evidence in
`docs/ai-reports/lubuntu/2026-07-15_dc11t1_v0_stable_failure_inventory.csv`
records this node as `failed`.

The V0 markdown report records a suite-level status swap, but also states that
the original baseline per-node ledger was unavailable. It does not provide the
underlying exception, pytest phase, or traceback for this specific node.

Available local DC-11T0-R2 artifacts are not T0-R4 proof for this node:

- `full-run-1/normalized_node_ledger.csv`: `notrun`
- `full-run-1-valid/normalized_node_ledger.csv`: `passed`
- `full-run-2-valid/normalized_node_ledger.csv`: `passed`

The task-supplied observation says T0-R4 `ERROR` became V0 `FAILED`, but the
available repository/local evidence does not include the T0-R4 per-node
exception or phase. Therefore I do not classify this as a pytest boundary issue.
The phase/exception evidence required to make that claim is absent.

The current focused reproduction is stronger for this node than the checked-in
inventory label: six required focused pytest processes passed, the exact
whitespace parameter passed three times, database setup completed every time,
and the node also passed after a successfully migrated database.

## Classification

**Classification:** `TEST_INFRASTRUCTURE`

Rationale:

- No focused run reproduced a product failure, stale assertion, or test-contract
  mismatch.
- The node's service path for whitespace input raises the neutral
  `OwnerCredentialSetupTokenInvalidError` before token lookup.
- The observed V0 `failed` label is inventory/harness evidence without
  node-specific phase and exception support.
- The exact node is not environment-gated under the required disposable
  PostgreSQL 16 and Redis 7 setup, and it also passes after successful Alembic
  migration.
- The only environment-gated finding was an unrelated Alembic prerequisite when
  `REPORTING_USER_PASSWORD` was absent.

Rejected classifications:

- `CURRENT_PRODUCT_DEFECT`: rejected because all focused runs passed.
- `STALE_TEST_CONTRACT`: rejected because the test contract matches the service
  behavior for whitespace input.
- `ENVIRONMENT_GATED`: rejected for the node because the standard disposable
  infrastructure and migrated-database diagnostic both pass.

## Cleanup Proof

- Containers stopped after testing.
- `docker ps -a --filter name=dc11t1-v0-r1-u6i3 --format ...` returned no
  matching containers.
- `docker volume ls --format ... | grep dc11t1-v0-r1-u6i3` returned no matching
  named volumes.
- The disposable worktree is removed after the report branch is committed and
  pushed; final command proof is reported outside this file because this file
  must exist inside the worktree until commit.
