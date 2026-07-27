# DC-12R1-S1-V2-R1 Permission Drift Gate Restoration Evidence

## Verdict

**PASS_FOR_CTO_DC12R1_S1_V2_R1_MERGE_REVIEW**

## Scope

- Date: Monday, July 27, 2026
- Branch: `reports/dc12r1-s1-v2-test-contract-reconciliation-2026-07-27`
- Branch tip at start of this R1 correction pass: `72374389f7c18856dd5f30f367a35239dfa0e487`
- Disposable worktree: `/home/ivy/MPANGO/dc12r1-s1-v2-r1-disposable`
- Allowed code/report edits used in this pass:
  - `backend/scripts/seed_demo_data.py`
  - `backend/tests/test_s6e_rbac_permission_registry_drift_gate.py`
  - this report

No skip, xfail, deselection, exclusion, assertion weakening, migration edits, or
unrelated product/test edits were introduced. S2 was not started.

## Test-Safe Environment

- PostgreSQL 16 container: `dc12r1-s1-v2-r1-pg16`
- Redis 7 container: `dc12r1-s1-v2-r1-redis7`
- PostgreSQL loopback DSN host/port: `127.0.0.1:56433`
- Redis loopback URL: `redis://127.0.0.1:57380/0`
- Environment:
  - `MPANGO_ENV=test`
  - `MPANGO_ALLOW_TEMP_DB_CREATE=1`
  - `MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1,localhost`
  - `MPANGO_TEMP_DB_ALLOWED_PORTS=56433`
  - `REPORTING_USER_PASSWORD` set to a disposable test value
  - all `TEST_DATABASE_URL` / `DATABASE_URL` values used non-production names,
    loopback hosts, and disposable test credentials only
  - all reporting DSNs used explicit test reporting credentials only

## RED Proof

Current `seed_demo_data.py` permission drift was reproduced before the fix with
an authoritative registry compare.

- Log: `/tmp/dc12r1-s1-v2-r1_seed_demo_red.log`
- Result: exit `1`
- Observed counts:
  - `seed_demo_data permission count: 39`
  - `canonical admin permission count: 45`
- Missing canonical admin permissions:
  - `inventory:write`
  - `invitations:revoke`
  - `orders:cancel`
  - `orders:confirm`
  - `orders:ship`
  - `retailers:reissue_credential`
  - `roles:create`
  - `roles:delete`
  - `roles:update`
- Legacy extras still present:
  - `orders:delete`
  - `orders:write`
  - `users:delete`

This established a real permission-set drift in `backend/scripts/seed_demo_data.py`.

## Corrections Applied

- Restored `seed_demo_data.py` into `PROVISIONING_PERMISSION_SCRIPTS`.
- Removed filename-based `ADMIN_PERMISSION_CODES` short-circuit behavior from
  `test_s6e_rbac_permission_registry_drift_gate.py`.
- Reworked the S6-E gate to prove actual canonical registry consumption through
  runtime extraction helpers that load each provisioning script and execute its
  real permission-seeding path instead of matching source literals.
- Updated `backend/scripts/seed_demo_data.py` to import `ADMIN_PERMISSIONS` from
  `core.permission_registry` and preserve the public consumer name
  `PERMISSION_CODES = ADMIN_PERMISSIONS`.
- Tightened the gate to assert exact permission-set equality, including no
  legacy extras.
- Removed the old report EOF whitespace and corrected the earlier inaccurate
  "no assertion weakening" wording.

## Canonical Registry Consumption Proof

The authoritative S6-E gate now proves:

- `onboard_tenant.py` consumes the canonical admin registry via its runtime
  role-permission create path
- `create_wholesaler.py` consumes the canonical admin registry via its runtime
  role-permission create path
- `seed_test_tenant.py` consumes the canonical admin registry via its runtime
  role-permission create path
- `seed_demo_data.py` consumes the canonical admin registry via
  `PERMISSION_CODES = ADMIN_PERMISSIONS`
- all four provisioning paths resolve to exact canonical admin-permission set
  equality, with neither omissions nor legacy extras

## Focused GREEN Proof

- `tests/test_s6e_rbac_permission_registry_drift_gate.py`
  - PASS: `5 passed`
  - Log context: post-fix targeted rerun
- Targeted regression bundle:
  - `tests/test_s6e_rbac_permission_registry_drift_gate.py`
  - `tests/test_u3b1_contract_foundation.py`
  - `tests/test_u1_bootstrap_permission_completeness.py`
  - `tests/test_u1r1_bootstrap_completeness.py`
  - `tests/test_dc12r1_s1_r5a_permission_registry_parity.py`
  - `tests/test_route_authorization_policy.py`
  - `tests/test_rbac_enforcement.py`
  - PASS: `123 passed, 5 xfailed`
  - Log: `/tmp/dc12r1-s1-v2-r1_targeted.log`

## Independent S4 Failure Review

The first post-fix full backend attempt on Monday, July 27, 2026 produced one
non-acceptance failure:

- Full-run failure node:
  - `tests/test_s4_jobs_persistence.py::test_job_persistence_happy_path`
- Failure detail:
  - phase: call
  - exception: `AssertionError`
  - observed mismatch: `job.status` was `'running'`, expected `'completed'`
- Gate1 log: `/tmp/dc12r1-s1-v2-r1_backend_gate1.log`
- Gate1 JUnit: `/tmp/dc12r1-s1-v2-r1_backend_gate1.xml`
- Gate1 summary:
  - `1 failed, 2870 passed, 48 skipped, 15 xfailed`

That node was then rechecked independently on fresh PostgreSQL 16 databases in
fresh pytest processes:

- `tests/test_s4_jobs_persistence.py`
  - PASS: `5 passed`
  - Log: `/tmp/dc12r1-s1-v2-r1_s4_alone2.log`
- `tests/test_s4_jobs_local.py tests/test_s4_jobs_persistence.py`
  - PASS: `16 passed`
  - Log: `/tmp/dc12r1-s1-v2-r1_s4_orig2.log`
- `tests/test_s4_jobs_persistence.py tests/test_s4_jobs_local.py`
  - PASS: `16 passed`
  - Log: `/tmp/dc12r1-s1-v2-r1_s4_rev2.log`

Because the node did not reproduce independently, in original order, or in
reverse order, it was not used as acceptance evidence and was not attributed to
infrastructure by assumption.

## Full Backend Gate

Accepted full backend evidence used two fresh Alembic-`head` PostgreSQL 16
databases and zero exclusions.

- Gate 2
  - Database: `test_backend_v2_r1_gate2`
  - Log: `/tmp/dc12r1-s1-v2-r1_backend_gate2.log`
  - JUnit: `/tmp/dc12r1-s1-v2-r1_backend_gate2.xml`
  - Result: `2871 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors in 675.46s`
- Gate 3
  - Database: `test_backend_v2_r1_gate3`
  - Log: `/tmp/dc12r1-s1-v2-r1_backend_gate3.log`
  - JUnit: `/tmp/dc12r1-s1-v2-r1_backend_gate3.xml`
  - Result: `2871 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors in 683.73s`

This satisfied the required consecutive two-run backend zero-failure,
zero-error gate.

## Frontend Gate

- `pnpm vitest run`
  - PASS: `14 passed` test files, `123 passed` tests
  - Log: `/tmp/dc12r1-s1-v2-r1_frontend_vitest.log`
- `pnpm build`
  - PASS
  - Log: `/tmp/dc12r1-s1-v2-r1_frontend_build.log`

Observed warnings only:

- duplicate `jsdom` key warning in `frontend/package.json`
- React Router future-flag warnings in existing tests
- existing React `act(...)` warnings in frontend tests
- Vite chunk-size warning for `dist/assets/index-DvBLCYaG.js`

## Repo Hygiene And Tooling

- `git diff --check`
  - PASS
- `pre-commit run --files ...`
  - PASS
  - Log: `/tmp/dc12r1-s1-v2-r1_precommit.log`
- standalone `detect-secrets` CLI was not installed in this environment
- equivalent explicit repo-configured secrets scan:
  - `pre-commit run detect-secrets --files ...`
  - PASS
- `GitNexus`
  - initial parallel `npx` attempts were discarded due npm cache contention
    (`ENOTEMPTY`) and a skipped native install
  - repaired by following the tool's own native-binary install guidance for
    `@ladybugdb/core`
  - `npm_config_ignore_scripts=true npx --yes gitnexus analyze .`
    - PASS
    - `30,361 nodes | 50,577 edges | 735 clusters | 300 flows`
    - Log: `/tmp/dc12r1-s1-v2-r1_gitnexus_analyze.log`
  - `npm_config_ignore_scripts=true npx --yes gitnexus status`
    - PASS
    - indexed commit `7237438`
    - current commit `7237438`
    - status `up-to-date`
    - Log: `/tmp/dc12r1-s1-v2-r1_gitnexus_status.log`

## Final Statement

The required V2-R1 permission-drift restoration is complete. `seed_demo_data.py`
now sources its admin permission set from the canonical registry, the S6-E gate
proves real canonical registry consumption instead of filename shortcuts or
source-literal parsing, focused regressions are green, frontend gates are green,
and the backend full suite passed twice consecutively on separate fresh
PostgreSQL 16 / Redis 7 test environments with zero failures and zero errors.
