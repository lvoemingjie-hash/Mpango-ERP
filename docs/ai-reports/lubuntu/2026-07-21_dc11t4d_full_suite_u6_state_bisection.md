# DC-11T4D Full-Suite State Pollution Root-Cause Bisection

Date: Tuesday, July 21, 2026
Base: `origin/product-dev-recovered`
Exact SHA: `6daa32bf3fd41b37ac53205b86764df757e2e4c7`
Report Branch: `reports/dc11t4d-full-suite-u6-state-bisection-2026-07-21`

## Scope

Investigate the prior claim that the following 14 U6 nodes fail only in the full backend suite, while passing independently and in either four-file grouped order:

1. `tests/test_u6i5_owner_credential_setup_endpoint.py::test_no_query_string_token_support`
2. `tests/test_u6i6_onboarding_e2e_closeout.py::test_full_owner_onboarding_backend_chain_proves_hash_only_tokens_and_admin_rbac`
3. `tests/test_u6k_production_smtp_email_delivery.py::test_production_missing_smtp_config_returns_503_and_writes_no_rows`
4. `tests/test_u6k_production_smtp_email_delivery.py::test_production_smtp_success_creates_hash_only_registration_and_token`
5. `tests/test_u6k_production_smtp_email_delivery.py::test_production_smtp_send_failure_rolls_back_registration_and_token`
6. `tests/test_u6k_production_smtp_email_delivery.py::test_test_environment_still_uses_dev_sink_without_smtp`
7. `tests/test_u6k_production_smtp_email_delivery.py::test_duplicate_live_email_in_production_is_neutral_and_sends_no_extra_smtp`
8. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_verify_email_provisions_tenant_issues_setup_token_and_sends_owner_email`
9. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_emailed_setup_token_can_create_first_admin_rbac_and_status_is_public_active`
10. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_repeated_internal_orchestration_does_not_duplicate_tenant_token_or_admin_rows`
11. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_reused_verification_token_remains_neutral_and_does_not_duplicate_orchestration`
12. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_production_smtp_failure_prevents_public_status_completion`
13. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_retry_after_smtp_failure_reuses_existing_tenant_and_completes_owner_setup`
14. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_complete_onboarding_rejects_unverified_email`

## Environment

- Fresh PostgreSQL 16 container: `dc11t4d_fullsuite_pg`
- Fresh Redis 7 container: `dc11t4d_fullsuite_redis`
- Fresh database/user pair created for this run: database `dc11t4d_suite`, user `tester`
- `MPANGO_ENV=test`
- `REDIS_URL=redis://127.0.0.1:56385/0`
- Alembic applied through head on the exact target SHA before pytest assertions
- No manual DDL, `create_all`, bootstrap repair, or schema reconciliation was run before assertions
- No `.env.prod`, real SMTP credentials, or real mailboxes were used

Artifacts:

- `/tmp/dc11t4d_fullsuite_artifacts/fullsuite.collect.log`
- `/tmp/dc11t4d_fullsuite_artifacts/fullsuite.alembic.log`
- `/tmp/dc11t4d_fullsuite_artifacts/fullsuite.pytest.log`
- `/tmp/dc11t4d_fullsuite_artifacts/fullsuite.junit.xml`

## Method

1. Created a fresh worktree from the exact requested SHA.
2. Installed backend dependencies with Poetry in that worktree.
3. Started fresh PostgreSQL 16 and Redis 7 containers.
4. Applied Alembic to head.
5. Ran one full backend suite in a fresh pytest process:
   `poetry run pytest -vv --tb=long --junitxml=/tmp/dc11t4d_fullsuite_artifacts/fullsuite.junit.xml tests`
6. Inspected only leakable cross-test state after the run:
   - cached settings access
   - dependency overrides
   - monkeypatch-driven SMTP fakes
   - dev email sink state
   - public onboarding rows
   - tenant schemas

## Full-Suite Reproduction Result

The prior 14 U6 failures did **not** reproduce on Tuesday, July 21, 2026.

Observed suite summary from `/tmp/dc11t4d_fullsuite_artifacts/fullsuite.pytest.log`:

- `12 failed, 2711 passed, 63 skipped, 15 xfailed, 2490 warnings in 622.72s (0:10:22)`

The only reproduced failures were the already-known reporting failures:

- `tests/test_s6_2_materialized_views.py` (4)
- `tests/test_s6_3_dashboard_api.py` (5)
- `tests/test_s6_p_reporting_constraints.py` (3)

No U6 target node failed in the clean full-suite run.

## Exact Status Of The 14 Target U6 Nodes In The Full-Suite Process

| # | Node | Full-Suite Status |
| --- | --- | --- |
| 1 | `tests/test_u6i5_owner_credential_setup_endpoint.py::test_no_query_string_token_support` | PASSED |
| 2 | `tests/test_u6i6_onboarding_e2e_closeout.py::test_full_owner_onboarding_backend_chain_proves_hash_only_tokens_and_admin_rbac` | PASSED |
| 3 | `tests/test_u6k_production_smtp_email_delivery.py::test_production_missing_smtp_config_returns_503_and_writes_no_rows` | PASSED |
| 4 | `tests/test_u6k_production_smtp_email_delivery.py::test_production_smtp_success_creates_hash_only_registration_and_token` | PASSED |
| 5 | `tests/test_u6k_production_smtp_email_delivery.py::test_production_smtp_send_failure_rolls_back_registration_and_token` | PASSED |
| 6 | `tests/test_u6k_production_smtp_email_delivery.py::test_test_environment_still_uses_dev_sink_without_smtp` | PASSED |
| 7 | `tests/test_u6k_production_smtp_email_delivery.py::test_duplicate_live_email_in_production_is_neutral_and_sends_no_extra_smtp` | PASSED |
| 8 | `tests/test_u6l_email_verified_onboarding_orchestration.py::test_verify_email_provisions_tenant_issues_setup_token_and_sends_owner_email` | PASSED |
| 9 | `tests/test_u6l_email_verified_onboarding_orchestration.py::test_emailed_setup_token_can_create_first_admin_rbac_and_status_is_public_active` | PASSED |
| 10 | `tests/test_u6l_email_verified_onboarding_orchestration.py::test_repeated_internal_orchestration_does_not_duplicate_tenant_token_or_admin_rows` | PASSED |
| 11 | `tests/test_u6l_email_verified_onboarding_orchestration.py::test_reused_verification_token_remains_neutral_and_does_not_duplicate_orchestration` | PASSED |
| 12 | `tests/test_u6l_email_verified_onboarding_orchestration.py::test_production_smtp_failure_prevents_public_status_completion` | PASSED |
| 13 | `tests/test_u6l_email_verified_onboarding_orchestration.py::test_retry_after_smtp_failure_reuses_existing_tenant_and_completes_owner_setup` | PASSED |
| 14 | `tests/test_u6l_email_verified_onboarding_orchestration.py::test_complete_onboarding_rejects_unverified_email` | PASSED |

Evidence from `fullsuite.pytest.log` includes:

- line 2821: `tests/test_u6i5_owner_credential_setup_endpoint.py::test_no_query_string_token_support PASSED`
- line 2822: `tests/test_u6i6_onboarding_e2e_closeout.py::test_full_owner_onboarding_backend_chain_proves_hash_only_tokens_and_admin_rbac PASSED`
- lines 2823-2827: all five `u6k` nodes PASSED
- lines 2828-2834: all seven `u6l` nodes PASSED

Natural suite ordering from `fullsuite.collect.log` places these files consecutively:

- `test_u6i5_owner_credential_setup_endpoint.py`
- `test_u6i6_onboarding_e2e_closeout.py`
- `test_u6k_production_smtp_email_delivery.py`
- `test_u6l_email_verified_onboarding_orchestration.py`

Because all 14 target nodes passed in that same natural-order suite process, no prefix bisection entry condition was met.

## Leak-Surface Inspection

### 1. Settings Cache

`backend/core/config.py` defines `get_settings()` under `@lru_cache` at lines 252-253.

Result:

- This is a legitimate global leak surface.
- I found no reproduced U6 failure tied to cached settings on July 21, 2026.
- The U6 SMTP tests monkeypatch the imported `onboarding_service.get_settings` symbol rather than mutating environment variables globally, so the monkeypatch should restore automatically at test teardown.

### 2. Dependency Overrides

All four U6 files explicitly remove the DB override in teardown:

- `backend/tests/test_u6i5_owner_credential_setup_endpoint.py:42`
- `backend/tests/test_u6i6_onboarding_e2e_closeout.py:64`
- `backend/tests/test_u6k_production_smtp_email_delivery.py:39`
- `backend/tests/test_u6l_email_verified_onboarding_orchestration.py:54`

Result:

- No lingering `app.dependency_overrides` contamination was reproduced in the clean full-suite run.

### 3. Fake SMTP / Network Access

Observed implementation and tests:

- `backend/services/email_delivery.py:225-257` performs real SMTP only through `_send_smtp_email()`.
- `backend/tests/test_u6k_production_smtp_email_delivery.py:243`, `:269`, `:282`, and `:295` monkeypatch `email_delivery.smtplib.SMTP` to `FakeSMTP`.
- `backend/tests/test_u6k_production_smtp_email_delivery.py:34-42` clears the dev sink and resets `FakeSMTP` before and after each test file use.
- `backend/tests/test_u6l_email_verified_onboarding_orchestration.py:49-57` does the same for the orchestration file.

Result:

- No target U6 test attempted real SMTP network access in this clean suite run.
- The missing-SMTP test returns through the fail-closed path before any socket creation.
- The SMTP-path tests use `FakeSMTP`, not a real provider.

### 4. Database Rows

Post-suite residue query on the full-suite database returned:

- `public.tenant_registrations`: `0`
- `public.email_verification_tokens`: `0`
- `public.onboarding_status_tokens`: `0`
- `public.owner_credential_setup_tokens`: `0`
- `public.wholesalers`: `3`

Interpretation:

- No residual public U6 onboarding rows remained after the full suite.
- The remaining `public.wholesalers` rows were not accompanied by U6 registration/token residue and did not cause a reproduced U6 failure in this run.

### 5. Tenant Schemas

This was the only concrete residue observed.

Post-suite schema query returned nine orphaned `t_u6i5_*` schemas:

- `t_u6i5_3f004d19775d4842a0bb`
- `t_u6i5_7b396dfde49f4554b581`
- `t_u6i5_8241af92bef345dfa9cd`
- `t_u6i5_8ce3a250ddb54e61baa1`
- `t_u6i5_93dca02c06644746b37b`
- `t_u6i5_ea93df62c53e4167a231`
- `t_u6i5_f09ad35d37d14b29b1c3`
- `t_u6i5_f2ff1f98583b4b20af17`
- `t_u6i5_ff158ee29abc4cfeaca0`

Each contained five relations after the suite.

Root cause of that residue is visible in test teardown code:

- `backend/tests/test_u6i5_owner_credential_setup_endpoint.py:54-74` deletes matching public rows, but does not drop the created tenant schemas from `_setup_provisioned_tenant()`.
- `backend/tests/test_u6i5_owner_credential_setup_endpoint.py:97-110` explicitly creates a new `t_u6i5_*` schema per setup.
- In contrast, `backend/tests/test_u6i6_onboarding_e2e_closeout.py:87-110` and `backend/tests/test_u6l_email_verified_onboarding_orchestration.py:78-100` both drop matching tenant schemas during cleanup.

Result:

- The only demonstrated suite-state contamination on July 21, 2026 was orphaned tenant schema residue from `test_u6i5_owner_credential_setup_endpoint.py`.
- That residue did **not** reproduce the claimed 14 U6 failures in the clean full-suite process.

## Bisection Outcome

No bisection was performed.

Reason:

- The task required same-process natural-order prefix bisection only if the target U6 failures reproduced in the clean full-suite process.
- On Tuesday, July 21, 2026, they did not reproduce.
- Therefore there was no failing target node for which a minimal preceding prefix could be computed.

## Classification

### Reproduced current-product defect?

No.

No target U6 node failed without preceding suite state, so the STOP condition for `CURRENT_PRODUCT_DEFECT` was not reached.

### Exact contamination source of the previously claimed 14 U6 failures?

Not reproducible on July 21, 2026.

What can be stated exactly from direct evidence:

- The prior July 20, 2026 claim that the 14 U6 nodes fail in the full suite is not reproducible on a fresh July 21, 2026 rerun at the exact requested SHA.
- The only verified leak residue in the U6 area is orphaned `t_u6i5_*` tenant schemas created by `tests/test_u6i5_owner_credential_setup_endpoint.py`.
- No evidence was found that cached settings, dependency overrides, fake SMTP state, or public onboarding rows contaminated the reproduced clean full-suite run.

## Minimal Test-Only Fix

The minimal test-only hardening change supported by direct evidence is:

1. Extend `tests/test_u6i5_owner_credential_setup_endpoint.py` teardown so `_clear_u6i5_rows()` also drops any `tenant_schema` values linked to its `u6i5_%@example.com` registrations before deleting the rows, matching the cleanup pattern already used in `u6i6` and `u6l`.

Rationale:

- This is the only leak surface with concrete post-suite residue.
- It is test-only.
- It reduces cross-suite schema buildup even though it did not reproduce the 14 target failures in this clean rerun.

## Final Conclusion

On Tuesday, July 21, 2026, a clean full backend suite run on `6daa32bf3fd41b37ac53205b86764df757e2e4c7` did **not** reproduce the previously reported 14 U6 failures.

Accordingly:

- no CURRENT_PRODUCT_DEFECT was reproduced,
- no smallest preceding prefix could be identified,
- no exact July 20 contamination chain could be proven from a fresh rerun,
- the only demonstrated leak residue was orphaned `t_u6i5_*` tenant schemas left by `tests/test_u6i5_owner_credential_setup_endpoint.py`.
