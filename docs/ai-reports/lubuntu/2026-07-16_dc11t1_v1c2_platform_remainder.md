# DC-11T1-V1C2 Platform Remainder Classification

## Verdict

`PASS_DC11T1_V1C2_CLASSIFICATION_COMPLETE`

All 11 remaining V0 platform-domain nodes are classified as `TEST_INFRASTRUCTURE`. No current product defect, stale test contract, or environment-gated behavior was found in this slice.

## Scope

- Code baseline: `7a972d1dca944db3476c405b807ddb5313f5ef95`
- V0 inventory: `67d2696b1b89cbf1ed6cda686797d395b8ef7801`
- Inventory nodes: 11
- Scoped files: 7
- Product code changes: none
- Test changes: none
- Migration changes: none
- Configuration and lockfile changes: none

Scoped files:

- `backend/tests/test_s4_jobs_persistence.py` (5 inventory nodes)
- `backend/tests/test_request_validation.py` (1)
- `backend/tests/test_s3c_cache.py` (1)
- `backend/tests/test_s3c_self_contained_fresh_tenant_live_proof.py` (1)
- `backend/tests/test_s5a_fresh_tenant_real_user_journey_gate.py` (1)
- `backend/tests/test_search_path.py` (1)
- `backend/tests/test_tenant_isolation.py` (1)

The V0 inventory commit differs from the code baseline only by the V0 report and CSV. No product or test source drift exists between them.

## Environment and Gate

- Host: Windows local workstation
- Python: 3.12.10
- Poetry-managed in-project environment: `backend/.venv`
- pytest: 8.4.2
- PostgreSQL: fresh `postgres:16-alpine` per gate
- Redis: fresh `redis:7-alpine` per gate
- Database migrations: complete Alembic upgrade to current head per gate
- Test schemas: fresh `t_test` and `t_dev` bootstrap per gate

The repository-provided deterministic gate created and removed independent infrastructure for every isolated file and for each grouped-order run. Database URLs and generated credentials were redacted from artifacts and are not recorded here.

## R4 Evidence Stability

The two preserved R4 full-suite artifacts contain exactly the same 11 node/status pairs:

| R4 run | Failed | Errors | Total | Node/status diff |
| --- | ---: | ---: | ---: | ---: |
| full run 1 | 5 | 6 | 11 | 0 |
| full run 2 | 5 | 6 | 11 | 0 |

The failures are therefore reproducible at the full-suite harness level. Their exception classes, however, are infrastructure state failures rather than failed business assertions.

## Independent File Runs

Every affected file was rerun in its own disposable PostgreSQL/Redis environment and pytest process.

| File gate | Collected | Passed | Failed | Errors | XFailed |
| --- | ---: | ---: | ---: | ---: | ---: |
| S4 jobs persistence | 5 | 5 | 0 | 0 | 0 |
| request validation | 9 | 3 | 0 | 0 | 6 |
| S3C cache | 9 | 9 | 0 | 0 | 0 |
| S3C fresh tenant | 17 | 17 | 0 | 0 | 0 |
| S5A real journey | 3 | 3 | 0 | 0 | 0 |
| search path | 1 | 1 | 0 | 0 | 0 |
| tenant isolation | 4 | 4 | 0 | 0 | 0 |

The six request-validation xfails are pre-existing explicit xfails outside this 11-node inventory. The inventory target `test_login_rejects_missing_email` passed.

## Grouped Order Matrix

All seven files were then run together in two fresh environments and opposite target orders.

| Grouped gate | Collected | Passed | Failed | Errors | XFailed |
| --- | ---: | ---: | ---: | ---: | ---: |
| forward order | 48 | 42 | 0 | 0 | 6 |
| reverse order | 48 | 42 | 0 | 0 | 6 |

Both runs produced the same normalized all-status ledger hash and the same empty failed/error ledger hash. The seven files do not contaminate one another. Their R4 outcomes require broader full-suite state that is absent from this controlled slice.

## Root-Cause Evidence

### Request validation

Inventory node:

- `backend/tests/test_request_validation.py:28`

Both R4 outputs report `There is no current event loop` followed by a middleware task using a Future attached to a different loop. The request contract assertion did not fail. The node passed independently and in both grouped orders.

Classification: `TEST_INFRASTRUCTURE`.

### Redis lifecycle

Inventory node:

- `backend/tests/test_s3c_cache.py:214`

R4 fails while the Redis client attempts loop-bound cleanup after the loop is already closed. The nine-test cache file and both grouped orders pass with fresh Redis and a clean loop.

Classification: `TEST_INFRASTRUCTURE`.

### Self-contained fresh tenant dashboard

Inventory node:

- `backend/tests/test_s3c_self_contained_fresh_tenant_live_proof.py:654`

R4 raises `Future attached to a different loop` during the dashboard request. The 17-test fresh-tenant file passes in independent infrastructure, including the same endpoint assertion.

Classification: `TEST_INFRASTRUCTURE`.

### S4 job persistence

Inventory nodes:

- `backend/tests/test_s4_jobs_persistence.py:61`
- `backend/tests/test_s4_jobs_persistence.py:111`
- `backend/tests/test_s4_jobs_persistence.py:161`
- `backend/tests/test_s4_jobs_persistence.py:207`
- `backend/tests/test_s4_jobs_persistence.py:275`

The R4 ledger promotes these nodes to ERROR because async-session setup or teardown also fails. Raw output includes cross-loop Futures on the retry and multiple-job calls. All five job persistence tests pass together on a clean migrated database, and remain green in both seven-file grouped orders.

Classification: five `TEST_INFRASTRUCTURE` nodes.

### S5A returned-order bootstrap proof

Inventory node:

- `backend/tests/test_s5a_fresh_tenant_real_user_journey_gate.py:272`

R4 reaches the database through a pooled connection that still has a manually started transaction and raises `cannot use Connection.transaction() in a manually started transaction`. The returned-status assertion is not the failing condition. The full S5A file passes independently and in both grouped orders.

Classification: `TEST_INFRASTRUCTURE`.

### Search path

Inventory node:

- `backend/tests/test_search_path.py:7`

R4 raises a cross-loop Future and records an additional fixture teardown error. The node passes in independent infrastructure and in both grouped orders.

Classification: `TEST_INFRASTRUCTURE`.

### Tenant isolation

Inventory node:

- `backend/tests/test_tenant_isolation.py:40`

R4 reports `hypothesis.errors.FlakyFailure`: the first generated example sees a connection with a manually started transaction, while Hypothesis cannot reproduce that state on replay. The four-test isolation file and both grouped orders pass cleanly.

Classification: `TEST_INFRASTRUCTURE`.

## Accounting

| Classification | Count |
| --- | ---: |
| `TEST_INFRASTRUCTURE` | 11 |
| `STALE_TEST_CONTRACT` | 0 |
| `CURRENT_PRODUCT_DEFECT` | 0 |
| `ENVIRONMENT_GATED` | 0 |
| Total | 11 |

Accounting: `11 + 0 + 0 + 0 = 11`, gap `0`.

The complete node ledger is `docs/ai-reports/lubuntu/2026-07-16_dc11t1_v1c2_platform_remainder.csv`.

## Interpretation and Follow-Up

These results close the remaining V0 platform-domain inventory without changing product behavior. They do not justify skips, xfails, or weakened assertions.

The later test-infrastructure correction should focus on the full-suite process boundary:

1. Ensure direct Alembic and synchronous helper calls cannot replace or close the session event loop.
2. Dispose loop-bound async engines, Redis clients, and pools before a fixture changes loop ownership.
3. Roll back manually started transactions before returning pooled connections.
4. Keep Hypothesis database tests isolated from shared transaction state.

The exact upstream contaminating file is outside this seven-file slice. Forward and reverse grouped runs prove none of these seven files creates the R4 failure state for another scoped file.

## Cleanup and Safety

- All gate containers, networks, and volumes were removed by the deterministic gate.
- No product database or VPS was accessed.
- No raw credentials, tokens, database URLs, passwords, or email addresses were recorded.
- No protected branch was pushed.
