# DC-11T1-V2A Auth Entry Classification

Date: 2026-07-17

## Verdict

`PASS_DC11T1_V2A_CLASSIFICATION_COMPLETE`

The 37 V0 auth-entry FAILED/ERROR nodes are fully classified with an accounting gap of zero:

| Classification | Count |
| --- | ---: |
| TEST_INFRASTRUCTURE | 34 |
| STALE_TEST_CONTRACT | 3 |
| CURRENT_PRODUCT_DEFECT | 0 |
| ENVIRONMENT_GATED | 0 |
| Total | 37 |

This report is a classification artifact, not permission to ignore the test-harness defect. The event-loop/Alembic interaction must still be corrected through the dedicated test-infrastructure branch before a deterministic full-suite gate can pass.

## Scope

- Product baseline: `7a972d1dca944db3476c405b807ddb5313f5ef95`
- V0 inventory source: `67d2696b1b89cbf1ed6cda686797d395b8ef7801`
- V0 domain: `AUTH_ONBOARDING`
- V2A files:
  - `tests/test_u6c_signup_email_verification_skeleton.py`
  - `tests/test_u6d_verify_email_endpoint.py`
  - `tests/test_u6e0_onboarding_status_token_schema.py`
  - `tests/test_u6e_onboarding_status_endpoint.py`
  - `tests/test_u6f_onboarding_auth_chain_closeout.py`
- V0 observed outcome: 28 failed, 9 errors, 37 total.
- No product code, tests, migrations, frontend, configuration, dependency, or lockfile was changed.

## Infrastructure

Every new reproduction used the repository deterministic gate with fresh disposable infrastructure:

- PostgreSQL `16-alpine`
- Redis `7-alpine`
- Alembic current/head `034_platform_operators`
- Bootstrapped tenant schemas `t_test` and `t_dev`
- Per-run container, network, and volume cleanup verified complete

No database, container, or event-loop state was reused between independent file runs.

## Independent File Results

| Test file | V0 nodes | Fresh isolated result | Classification |
| --- | ---: | --- | --- |
| `test_u6c_signup_email_verification_skeleton.py` | 10 | 10 passed | 10 TEST_INFRASTRUCTURE |
| `test_u6d_verify_email_endpoint.py` | 7 | 8 passed, including all 7 V0 nodes | 7 TEST_INFRASTRUCTURE |
| `test_u6e0_onboarding_status_token_schema.py` | 1 | 7 passed, 1 stable contract failure | 1 STALE_TEST_CONTRACT |
| `test_u6e_onboarding_status_endpoint.py` | 12 | 13 passed, including all 12 V0 nodes | 12 TEST_INFRASTRUCTURE |
| `test_u6f_onboarding_auth_chain_closeout.py` | 7 | 5 passed, 2 stable contract failures | 5 TEST_INFRASTRUCTURE, 2 STALE_TEST_CONTRACT |

The five-file grouped run collected 46 nodes and produced `43 passed, 3 failed, 0 errors`. The three failures were exactly the three stale contracts listed below. All 34 nodes classified as TEST_INFRASTRUCTURE passed in the grouped process.

## Causal Order Matrix

The R4 raw log first fails an async database fixture with:

`Future attached to a different loop`

Later fixtures, including U6C, fail with:

`cannot use Connection.transaction() in a manually started transaction`

The following fresh-infrastructure order matrix reproduced the mechanism without changing source code.

### Control: migration tests before async pool initialization

Order:

1. `test_platform_p21_durable_approval_migration.py`
2. the five V2A files

Result: 52 collected, 43 passed, 9 failed, 0 errors. Six failures were known stale P21 migration assertions and three were the V2A stale contracts. No V2A infrastructure-classified node failed.

### Reproduction: async pool, direct Alembic, then V2A

Order:

1. `test_s4_jobs_persistence.py::test_job_persistence_happy_path` initializes the async DB pool.
2. `test_platform_p21_durable_approval_migration.py` invokes `command.upgrade(...)` directly at lines 216, 220, 257, 282, 295, and 318.
3. the five V2A files run in the same pytest process.

Result: 53 collected, 8 passed, 45 failed, 0 errors. Every U6C/D/E/F test that needed the pytest event loop failed with:

`RuntimeError: There is no current event loop in thread 'MainThread'.`

The direct Alembic calls therefore close or replace the loop after the async engine has bound pooled connections to it. The next async test either sees no current loop or attempts to reuse a connection bound to the prior loop. This is the same mechanism recorded in the R4 raw run.

The difference between pytest reporting these outcomes as FAILED versus ERROR is phase placement, not a product behavior difference.

## Stale Contract Evidence

### STALE-ROUTE-001

Node:

`tests/test_u6e0_onboarding_status_token_schema.py::test_no_onboarding_status_endpoint_or_runtime_route_added`

The test at lines 155-159 asserts that `/onboarding/status` does not exist. The current product intentionally implements that route in `api/v1/auth.py` at lines 187-191. Current route authorization tests also list it as a public token-exchange route. The assertion describes the pre-U6E0 boundary and is stale.

### STALE-ALLOWLIST-001

Node:

`tests/test_u6f_onboarding_auth_chain_closeout.py::test_route_policy_keeps_only_expected_onboarding_auth_routes_public`

The hard-coded `EXPECTED_PUBLIC_ALLOWLIST` at lines 38-44 predates the implemented forgot-password and reset-password routes. Current route-policy evidence lists both routes at lines 146-160 of `test_route_authorization_policy.py`. The product behavior is intentional and independently covered; the U6F exact-set assertion is stale.

### STALE-HEAD-001

Node:

`tests/test_u6f_onboarding_auth_chain_closeout.py::test_migration_schema_sanity_for_u6f_closeout_gate`

The test at lines 550-551 pins Alembic head `028_owner_credential_setup_tokens`. The exact baseline has the single current head `034_platform_operators`. Historical migration 028 remains in the chain; the exact-head assertion is stale.

## Accounting

| File | TEST_INFRASTRUCTURE | STALE_TEST_CONTRACT | Total |
| --- | ---: | ---: | ---: |
| U6C | 10 | 0 | 10 |
| U6D | 7 | 0 | 7 |
| U6E0 | 0 | 1 | 1 |
| U6E | 12 | 0 | 12 |
| U6F | 5 | 2 | 7 |
| Total | 34 | 3 | 37 |

`34 + 3 + 0 + 0 = 37`; accounting gap = 0.

The companion CSV contains all 37 exact V0 node IDs with no normalization, truncation, batch skip, xfail, or assertion weakening.

## CTO Decision

1. No CURRENT_PRODUCT_DEFECT is confirmed in this V2A slice.
2. The three stale tests should be updated narrowly after the classification program is complete; they must not be converted to blanket skips or xfails.
3. The direct Alembic/event-loop contamination is a real test-harness defect. The dedicated DC-11T0 infrastructure work should preserve the pytest event loop around migration calls and remain separate from product code.
4. Proceed to the next AUTH_ONBOARDING batch only; do not infer that all 135 AUTH_ONBOARDING nodes are closed from this 37-node result.

## Compliance

- No credentials, JWTs, raw tokens, email addresses, SMTP values, or database URLs are recorded.
- No protected branch was pushed.
- No release tag was created or moved.
- Disposable infrastructure cleanup completed for every run.
