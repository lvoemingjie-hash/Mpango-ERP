# DC-11T4A-H2-R1B U6 Auth/Onboarding Failure Classification

Date: 2026-07-21
Target SHA: `6daa32bf3fd41b37ac53205b86764df757e2e4c7`
Branch: `reports/dc11t4a-h2-r1b-u6-classification-2026-07-21`

## Verdict

`PASS_DC11T4A_H2_R1B_CLASSIFICATION_COMPLETE`

No `CURRENT_PRODUCT_DEFECT` was reproduced. No CTO stop condition was triggered.

## Environment

- PostgreSQL: `16.14`
- Redis: `7.4.9`
- Python: `3.12.3`
- Poetry: `2.4.1`

## Scope And Target Set

This run classified the exact 14 U6 H2 nodes previously listed as failed in the prior H2 full-backend gate artifact for the same SHA:

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
12. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_production_missing_owner_setup_smtp_config_fails_closed`
13. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_production_owner_setup_smtp_failure_fails_closed_with_retry_anchor`
14. `tests/test_u6l_email_verified_onboarding_orchestration.py::test_real_bootstrap_owner_setup_smtp_failure_persists_anchor_and_retry_reconciles`

## Execution Contract

The run followed the requested rules:

1. Fresh disposable PostgreSQL 16 and Redis 7 containers.
2. Alembic upgrade executed through `034_platform_operators`.
3. No `.env.prod` read and no real SMTP/mailbox usage.
4. SMTP remained mocked/faked exactly by the tests.
5. Each file ran in its own fresh pytest process.
6. Independent pass repeated on a second fresh database.
7. All four files ran grouped in H2 order on another fresh database.
8. All four files ran grouped in reverse order on another fresh database.
9. No product edits, test edits, skips, deselects, xfails, assertion weakening, or code repair.

## Scenario Results

| Scenario | Fresh DB | Pytest processes | Result |
|---|---:|---:|---|
| `individual_a` | 1 | 4 | all files passed |
| `individual_b` | 1 | 4 | all files passed |
| `group_h2` | 1 | 1 | all 23 tests passed |
| `group_reverse` | 1 | 1 | all 23 tests passed |

Independent file outcomes on both fresh databases:

| File | DB A | DB B |
|---|---|---|
| `tests/test_u6i5_owner_credential_setup_endpoint.py` | PASS (`10/10`) | PASS (`10/10`) |
| `tests/test_u6i6_onboarding_e2e_closeout.py` | PASS (`1/1`) | PASS (`1/1`) |
| `tests/test_u6k_production_smtp_email_delivery.py` | PASS (`5/5`) | PASS (`5/5`) |
| `tests/test_u6l_email_verified_onboarding_orchestration.py` | PASS (`7/7`) | PASS (`7/7`) |

Grouped-order observations:

- H2-order grouped run: PASS (`23/23`)
- Reverse-order grouped run: PASS (`23/23`)
- No target-node failure appeared in any grouped run.
- No order sensitivity was observed.
- No target node required an earlier in-scope file to pass or fail.

## Alembic Evidence

Fresh-db Alembic logs were deterministic:

- full upgrade succeeded to `034_platform_operators`
- single-head check resolved to `034_platform_operators (head)`
- public schema migrations completed cleanly on every fresh database

## Explicit Evidence

### Whether each file passes or fails independently

All four files passed independently on both fresh databases.

### Whether failure requires an earlier test file

No. There were no failures in any independent or grouped scenario, so no earlier in-scope file was required to trigger any target node outcome.

### Whether `get_settings` / cache or environment state leaks across tests

No in-scope leak was observed.

Evidence:

- `core.config.get_settings()` is `@lru_cache`, but these U6 production-path tests monkeypatch `onboarding_service.get_settings`, not the core cache.
- `group_h2` and `group_reverse` both passed `23/23`, matching both independent passes exactly.
- The test fixtures explicitly reset:
  - `app.dependency_overrides` via `dependency_overrides.pop(...)`
  - dev email sink via `clear_dev_email_deliveries()`
  - fake SMTP state via `FakeSMTP.reset()`
- No cache-clear workaround was needed to make the files pass.

Conclusion:

- within the scoped four-file slice, no settings cache, environment variable, dependency override, module monkeypatch, or process-state leak changed outcomes.
- if the earlier full-suite gate failure was real, it depended on out-of-scope suite contamination rather than these four files themselves.

### Whether production SMTP tests attempt any real network access

No real SMTP network access was attempted.

Evidence:

- `tests/test_u6k_production_smtp_email_delivery.py` monkeypatches `email_delivery.smtplib.SMTP` to `FakeSMTP` for SMTP-delivery scenarios.
- `tests/test_u6l_email_verified_onboarding_orchestration.py` does the same for SMTP-delivery scenarios.
- The missing-config production tests patch production settings with `SMTP_HOST=None`, and `onboarding_service.complete_email_verified_onboarding(...)` / `create_signup_registration(...)` fail closed on `is_verification_email_delivery_configured(...)` before SMTP send.
- SMTP success/failure assertions were satisfied entirely via `FakeSMTP.sent_messages`, `FakeSMTP.login_calls`, and `FakeSMTP.starttls_calls`.
- No DNS/socket/network exception was needed or observed for any passing node.

### Whether database rows remain from preceding files

Public onboarding rows did not remain after any traced file.

On a follow-up traced shared-database pass run in H2 file order, after each file:

- `public.tenant_registrations = 0`
- `public.wholesalers = 0`
- `public.email_verification_tokens = 0`
- `public.onboarding_status_tokens = 0`
- `public.owner_credential_setup_tokens = 0`

Tenant schema residue nuance:

- `tests/test_u6i5_owner_credential_setup_endpoint.py` creates ad-hoc tenant schemas named `t_u6i5_*` and does not drop them.
- Those schemas remained after the file completed.
- This residue did not affect later files:
  - `group_h2` still passed `23/23`
  - `group_reverse` still passed `23/23`
  - both independent passes still passed fully

Conclusion:

- public onboarding rows/tokens do not leak across files.
- `u6i5` does leave tenant schemas behind, but that residue is non-causative for the 14-node H2 target set under this run.

## Classification Summary

| Class | Count |
|---|---:|
| `TEST_INFRASTRUCTURE` | 14 |
| `STALE_TEST_CONTRACT` | 0 |
| `CURRENT_PRODUCT_DEFECT` | 0 |
| `ENVIRONMENT_GATED` | 0 |

Accounting: `14 / 14`, gap=`0`

## Exact Classification Table

Because none of the 14 target nodes failed in any fresh-db reproduction, no runtime exception was reproduced for any node. For classification purposes, each node is assigned `TEST_INFRASTRUCTURE`: the previously reported H2 full-suite failure is non-reproducible on a clean exact-SHA rerun and therefore attributable to suite/harness contamination outside the scoped four-file slice rather than a current product defect.

| H2 Node | Exception class observed in this run | Sanitized root cause | Classification |
|---|---|---|---|
| `tests/test_u6i5_owner_credential_setup_endpoint.py::test_no_query_string_token_support` | `NONE_OBSERVED` | passed independently twice and grouped twice; prior H2 failure non-reproducible under clean exact-SHA rerun | `TEST_INFRASTRUCTURE` |
| `tests/test_u6i6_onboarding_e2e_closeout.py::test_full_owner_onboarding_backend_chain_proves_hash_only_tokens_and_admin_rbac` | `NONE_OBSERVED` | passed independently twice and grouped twice; prior H2 failure non-reproducible under clean exact-SHA rerun | `TEST_INFRASTRUCTURE` |
| `tests/test_u6k_production_smtp_email_delivery.py::test_production_missing_smtp_config_returns_503_and_writes_no_rows` | `NONE_OBSERVED` | passed independently twice and grouped twice; prior H2 failure non-reproducible under clean exact-SHA rerun | `TEST_INFRASTRUCTURE` |
| `tests/test_u6k_production_smtp_email_delivery.py::test_production_smtp_success_creates_hash_only_registration_and_token` | `NONE_OBSERVED` | passed independently twice and grouped twice; prior H2 failure non-reproducible under clean exact-SHA rerun | `TEST_INFRASTRUCTURE` |
| `tests/test_u6k_production_smtp_email_delivery.py::test_production_smtp_send_failure_rolls_back_registration_and_token` | `NONE_OBSERVED` | passed independently twice and grouped twice; prior H2 failure non-reproducible under clean exact-SHA rerun | `TEST_INFRASTRUCTURE` |
| `tests/test_u6k_production_smtp_email_delivery.py::test_test_environment_still_uses_dev_sink_without_smtp` | `NONE_OBSERVED` | passed independently twice and grouped twice; prior H2 failure non-reproducible under clean exact-SHA rerun | `TEST_INFRASTRUCTURE` |
| `tests/test_u6k_production_smtp_email_delivery.py::test_duplicate_live_email_in_production_is_neutral_and_sends_no_extra_smtp` | `NONE_OBSERVED` | passed independently twice and grouped twice; prior H2 failure non-reproducible under clean exact-SHA rerun | `TEST_INFRASTRUCTURE` |
| `tests/test_u6l_email_verified_onboarding_orchestration.py::test_verify_email_provisions_tenant_issues_setup_token_and_sends_owner_email` | `NONE_OBSERVED` | passed independently twice and grouped twice; prior H2 failure non-reproducible under clean exact-SHA rerun | `TEST_INFRASTRUCTURE` |
| `tests/test_u6l_email_verified_onboarding_orchestration.py::test_emailed_setup_token_can_create_first_admin_rbac_and_status_is_public_active` | `NONE_OBSERVED` | passed independently twice and grouped twice; prior H2 failure non-reproducible under clean exact-SHA rerun | `TEST_INFRASTRUCTURE` |
| `tests/test_u6l_email_verified_onboarding_orchestration.py::test_repeated_internal_orchestration_does_not_duplicate_tenant_token_or_admin_rows` | `NONE_OBSERVED` | passed independently twice and grouped twice; prior H2 failure non-reproducible under clean exact-SHA rerun | `TEST_INFRASTRUCTURE` |
| `tests/test_u6l_email_verified_onboarding_orchestration.py::test_reused_verification_token_remains_neutral_and_does_not_duplicate_orchestration` | `NONE_OBSERVED` | passed independently twice and grouped twice; prior H2 failure non-reproducible under clean exact-SHA rerun | `TEST_INFRASTRUCTURE` |
| `tests/test_u6l_email_verified_onboarding_orchestration.py::test_production_missing_owner_setup_smtp_config_fails_closed` | `NONE_OBSERVED` | passed independently twice and grouped twice; prior H2 failure non-reproducible under clean exact-SHA rerun | `TEST_INFRASTRUCTURE` |
| `tests/test_u6l_email_verified_onboarding_orchestration.py::test_production_owner_setup_smtp_failure_fails_closed_with_retry_anchor` | `NONE_OBSERVED` | passed independently twice and grouped twice; prior H2 failure non-reproducible under clean exact-SHA rerun | `TEST_INFRASTRUCTURE` |
| `tests/test_u6l_email_verified_onboarding_orchestration.py::test_real_bootstrap_owner_setup_smtp_failure_persists_anchor_and_retry_reconciles` | `NONE_OBSERVED` | passed independently twice and grouped twice; prior H2 failure non-reproducible under clean exact-SHA rerun | `TEST_INFRASTRUCTURE` |

## Why `TEST_INFRASTRUCTURE` And Not Another Class

Not `CURRENT_PRODUCT_DEFECT`:

- zero of 14 target nodes failed on the exact target SHA in any scenario
- both grouped orders matched both independent passes

Not `STALE_TEST_CONTRACT`:

- the tests themselves are currently satisfiable by the product at this SHA
- no assertion needed weakening or reinterpretation

Not `ENVIRONMENT_GATED`:

- the requested fresh PostgreSQL 16 / Redis 7 environment was sufficient
- no real SMTP server, mailbox, or `.env.prod` dependency was required
- mocked/fake SMTP paths passed exactly as authored

Therefore:

- the previously reported H2 U6 failure set is best classified as `TEST_INFRASTRUCTURE`, meaning non-reproducible suite/harness contamination outside this scoped slice.
