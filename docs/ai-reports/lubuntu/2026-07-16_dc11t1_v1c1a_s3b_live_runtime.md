# DC-11T1-V1C1-A S3B Prepared Live Runtime Classification

## Verdict

`PASS_DC11T1_V1C1A_CLASSIFICATION_COMPLETE`

All 19 V0 inventory nodes in the S3B prepared live runtime file are classified as `TEST_INFRASTRUCTURE`. No current product defect, stale contract, or environment-gated node was found in this slice.

## Scope

- Code baseline: `7a972d1dca944db3476c405b807ddb5313f5ef95`
- V0 inventory: `67d2696b1b89cbf1ed6cda686797d395b8ef7801`
- Scoped file: `backend/tests/test_s3b_fresh_tenant_live_runtime_proof.py`
- V0 nodes: 19
- Product code changes: none
- Test changes: none
- Migration changes: none
- Configuration or lockfile changes: none

The V0 inventory commit differs from the code baseline only by report artifacts. No source drift exists between the tested baseline and inventory evidence.

## Local Environment

- Host: Windows local workstation
- Python: 3.12.10
- Poetry-managed in-project environment: `backend/.venv`
- pytest: 8.4.2
- PostgreSQL: disposable PostgreSQL 16 container
- Redis: disposable Redis 7 container
- Alembic current: `034_platform_operators (head)`
- Database credentials and ports: generated for the disposable run and not recorded

The repository remained clean before report creation. The in-project virtual environment is ignored and did not alter `pyproject.toml` or `poetry.lock`.

## Existing R4 Evidence

The two preserved DC-11T0-R4 full-suite artifacts show the same S3B result:

| Evidence run | S3B failed | S3B errors | Total inventory nodes |
| --- | ---: | ---: | ---: |
| R4 full run 1 | 1 | 18 | 19 |
| R4 full run 2 | 1 | 18 | 19 |

Both outputs contain the same two infrastructure signatures:

1. The only failed node, `test_all_required_tables_present`, raises `Future attached to a different loop` while using the async SQLAlchemy engine.
2. The shared prepared-admin fixture raises `relation "users" does not exist`, causing the remaining 18 nodes to error before their assertions execute.

Both full-suite logs show the U1R1 tenant bootstrap completion later in the run than the S3B nodes. The S3B source itself states that it is a prepared, previously bootstrapped proof and is not a complete fresh-bootstrap proof:

- `backend/tests/test_s3b_fresh_tenant_live_runtime_proof.py:5`
- `backend/tests/test_s3b_fresh_tenant_live_runtime_proof.py:8`
- `backend/tests/test_s3b_fresh_tenant_live_runtime_proof.py:116`
- `backend/tests/test_s3b_fresh_tenant_live_runtime_proof.py:178`

The external fixture that creates the expected tenant schema and seeds the prepared administrator is defined in a different file:

- `backend/tests/test_u1r1_bootstrap_completeness.py:117-139`

S3B does not depend on that fixture. Full-suite collection order can therefore execute S3B before the required external preparation. This is a test-harness dependency and ordering defect, not a failure of a product request path.

## Independent Reproduction

A new disposable database and cache were created. The validation sequence was:

1. Apply the complete Alembic migration chain to head.
2. Run the U1R1 bootstrap fixture in its own pytest process to create and seed the prepared tenant.
3. Run the entire S3B file in three separate pytest processes against the same correctly prepared disposable database.

| Run | Tests | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| S3B run 1 | 22 | 22 | 0 | 0 | 0 |
| S3B run 2 | 22 | 22 | 0 | 0 | 0 |
| S3B run 3 | 22 | 22 | 0 | 0 | 0 |

The three configuration-only nodes that were already passing in V0 also passed. More importantly, all 19 V0 failed/error nodes passed in every independent prepared run.

## Root-Cause Classification

### One failed node

`TestLiveTenantSchemaBootstrapped::test_all_required_tables_present` is `TEST_INFRASTRUCTURE`.

- R4 run 1 and run 2 both raised the same cross-event-loop `Future` error.
- The product schema assertion did not produce a current schema defect.
- The node passed three times when its async engine was created and consumed in a clean pytest process.

### Eighteen error nodes

The other 18 nodes are `TEST_INFRASTRUCTURE`.

- They share the prepared-admin fixture.
- In both R4 full runs that fixture reached the tenant query before the separate U1R1 bootstrap had prepared the schema.
- The resulting missing `users` relation prevented every downstream RBAC, token, endpoint, and business-empty-state assertion from running.
- All 18 passed in each of the three correctly prepared runs.

These nodes do not demonstrate current product defects. They demonstrate that a prepared-runtime test file has an undeclared external preparation dependency and is unsafe in arbitrary full-suite order.

## Classification Accounting

| Classification | Count |
| --- | ---: |
| `TEST_INFRASTRUCTURE` | 19 |
| `STALE_TEST_CONTRACT` | 0 |
| `CURRENT_PRODUCT_DEFECT` | 0 |
| `ENVIRONMENT_GATED` | 0 |
| Total | 19 |

Accounting: `19 + 0 + 0 + 0 = 19`, gap `0`.

The complete node-level ledger is in `docs/ai-reports/lubuntu/2026-07-16_dc11t1_v1c1a_s3b_live_runtime.csv`.

## Recommended Follow-Up

Do not skip, xfail, or weaken these tests. In a later test-infrastructure slice, make S3B self-contained by explicitly invoking a reusable prepared-tenant bootstrap fixture, or define a deterministic prerequisite fixture shared with U1R1. That change is outside this classification-only task.

## Cleanup

- Disposable PostgreSQL and Redis containers removed.
- Matching disposable volumes absent.
- No product database or VPS accessed.
- No credentials, database URLs, tokens, passwords, or full email addresses recorded.
- No protected branch pushed.
