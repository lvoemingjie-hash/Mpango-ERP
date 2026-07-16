# DC-11T1-V2B Provisioning Classification

Date: 2026-07-17

## Verdict

`PASS_DC11T1_V2B_CLASSIFICATION_COMPLETE`

The 29 V0 U6H1/H2/H3 provisioning failures are fully classified:

| Classification | Count |
| --- | ---: |
| TEST_INFRASTRUCTURE | 26 |
| STALE_TEST_CONTRACT | 3 |
| CURRENT_PRODUCT_DEFECT | 0 |
| ENVIRONMENT_GATED | 0 |
| Total | 29 |

Accounting gap: zero.

## Scope

- Product baseline: `7a972d1dca944db3476c405b807ddb5313f5ef95`
- V0 inventory source: `67d2696b1b89cbf1ed6cda686797d395b8ef7801`
- V0 observed result: 29 failed, 0 errors.
- Test files:
  - `tests/test_u6h1_tenant_provisioning_service_skeleton.py`
  - `tests/test_u6h2_tenant_provisioning_wholesaler_schema.py`
  - `tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py`
- No production code, test, migration, frontend, configuration, dependency, or lockfile was changed.

## Fresh Infrastructure

Every reproduction used a new disposable environment:

- PostgreSQL `16-alpine`
- Redis `7-alpine`
- Alembic current/head `034_platform_operators`
- Fresh `t_test` and `t_dev` tenant schemas
- Per-run container, volume, and network cleanup verified complete

## Independent Results

| File | V0 nodes | Isolated result | V0 classification |
| --- | ---: | --- | --- |
| U6H1 | 9 | 9 passed, 1 stale failure | 8 TEST_INFRASTRUCTURE, 1 STALE_TEST_CONTRACT |
| U6H2 | 13 | 13 passed, 1 stale failure | 12 TEST_INFRASTRUCTURE, 1 STALE_TEST_CONTRACT |
| U6H3 | 7 | 7 passed, 1 stale failure | 6 TEST_INFRASTRUCTURE, 1 STALE_TEST_CONTRACT |

The three-file grouped run collected 32 tests and produced `29 passed, 3 failed, 0 errors`. Every provisioning behavior test passed together. The only failures were the three static source assertions described below.

The passing coverage includes:

- registration claim and blocked-status behavior
- wholesaler and tenant-schema creation
- duplicate retry and idempotency
- partial-schema retry anchor preservation
- reconcile to active without duplicate wholesaler
- bootstrap failure cleanup and sanitized failure messages
- missing-schema fail-closed behavior
- no user, role, RBAC, or admin seeding in these slices

## Full-Suite Failure Mechanism

The R4 full-run traceback for the first failing node in each file ends with the same infrastructure exception:

`Future attached to a different loop`

This occurs before provisioning assertions execute, while the test attempts its first async SQL operation.

A fresh causal-order run used:

1. `test_s4_jobs_persistence.py::test_job_persistence_happy_path` to bind the async pool to the pytest event loop.
2. `test_platform_p21_durable_approval_migration.py`, which invokes `command.upgrade(...)` directly.
3. all three U6H files in the same pytest process.

Result: 39 collected, 1 passed, 38 failed. All six P21 migration tests and all 32 U6H tests failed after the event loop was removed. The U6H failures report:

`RuntimeError: There is no current event loop in thread 'MainThread'.`

Without this order pollution, the U6H grouped run passes every current behavior test. The 26 V0 behavior nodes are therefore TEST_INFRASTRUCTURE, not product defects.

## Stale Contract Evidence

The three stale nodes are:

- `tests/test_u6h1_tenant_provisioning_service_skeleton.py::test_public_auth_routes_do_not_call_tenant_provisioning`
- `tests/test_u6h2_tenant_provisioning_wholesaler_schema.py::test_public_auth_routes_still_do_not_call_tenant_provisioning_service`
- `tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py::test_public_auth_routes_do_not_call_tenant_provisioning_service`

Each test reads `api/v1/auth.py` and `services/onboarding_service.py` as text and asserts that no `TenantProvisioningService` reference exists. The assertions were valid before U6-L.

Current intended behavior is different:

- `api/v1/auth.py` lines 147-154 routes verify-email into `verify_email_token` and describes full backend onboarding orchestration.
- `services/onboarding_service.py` imports `TenantProvisioningService` at line 37 and invokes it from the verified-email flow around line 188.
- `test_u6l_email_verified_onboarding_orchestration.py` begins its direct runtime proof at line 330 and expects the registration to become active.

The current architecture intentionally provisions after successful email verification. These three source-absence assertions are historical boundary gates, not evidence of a current security or product regression.

## Accounting

| File | TEST_INFRASTRUCTURE | STALE_TEST_CONTRACT | Total |
| --- | ---: | ---: | ---: |
| U6H1 | 8 | 1 | 9 |
| U6H2 | 12 | 1 | 13 |
| U6H3 | 6 | 1 | 7 |
| Total | 26 | 3 | 29 |

`26 + 3 + 0 + 0 = 29`; gap = 0.

The companion CSV preserves every exact V0 node ID. No node was normalized, hidden, skipped, or converted to xfail.

## CTO Decision

1. No CURRENT_PRODUCT_DEFECT is confirmed in the U6H provisioning slice.
2. The three obsolete source-absence tests should be updated narrowly to the U6-L orchestration contract after the classification program; do not batch skip or xfail them.
3. The Alembic/event-loop harness defect remains real and must be corrected in the dedicated DC-11T0 infrastructure branch.
4. Proceed to the credential-setup U6I0-I6 batch. Do not generalize this result to the remaining AUTH_ONBOARDING inventory.

## Compliance

- No credentials, JWTs, raw tokens, emails, SMTP values, or database URLs are recorded.
- No protected branch was pushed.
- No release tag was created or moved.
- Disposable Docker resources were removed after every run.
