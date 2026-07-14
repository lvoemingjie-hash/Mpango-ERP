# DC-11P2 Platform Operator Credential Lifecycle

Date: 2026-07-14

Branch: `kilo/dc11p2-p5-platform-operator-lifecycle-2026-07-14`

Base: `origin/product-dev-recovered @ d0c7c6f1a754d4ea160547e59a6dfec6ce2b451a`

Scope: DC-11P2 only. DC-11P3 login/JWT/guard, DC-11P4 frontend, and DC-11P5 strict-mode closeout remain on hold.

## Verdict

`PASS_FOR_CTO_DC11P2_VALIDATION_CHECKPOINT`

R1 update verdict: `PASS_FOR_CTO_DC11P2_R1_REVIEW`

## Scope Implemented

- Added platform operator lifecycle service for bootstrap, invite, setup credential, forgot/reset password, disable, enable, revoke, password verification helper, recovery credential storage, and break-glass reset recovery.
- Added public token exchange/reset endpoints under `/api/v1/platform/operators` for setup, forgot password, and reset password.
- Added guarded operator lifecycle management endpoints under `/api/v1/platform/operators` using the existing P10 platform guard without modifying the guard.
- Added non-production email sink support for platform operator setup/reset emails while preserving production fail-closed SMTP behavior.
- Added CLI scripts for first-operator bootstrap and break-glass recovery that do not print raw setup/reset tokens or passwords.
- Added DC-11P2 tests covering hash-only tokens, single-use setup/reset, neutral reset responses, disable/enable/revoke, break-glass password preservation, route policy, schema sufficiency, and P3 file non-mutation.

## R1 Lifecycle Boundary Corrections

- Bootstrap now requires a recovery credential supplied through hidden stdin by the CLI and stores only `credential_hash` in the same transaction as operator/setup-token creation.
- Recovery credentials enforce the documented minimum: at least 24 characters, no whitespace, lowercase, uppercase, digit, symbol, and no common weak substrings.
- Break-glass recovery now consumes the current recovery credential and atomically installs the caller-supplied replacement credential hash; the service never generates or returns replacement credentials.
- Added a service-only recovery credential rotation boundary for future P3 platform-admin wiring.
- Normal `enable_operator` now fails closed when `revoked_at` is set; only validated break-glass can clear `revoked_at`.
- Platform operator setup/reset email links now use `/platform/setup-credential` and `/platform/reset-password` with URL-encoded tokens.
- Public setup/forgot/reset responses now return fixed neutral messages with empty `data` objects and no operator identifiers/status/role/auth_version/email/token/recovery fields.
- Same-email invite uniqueness conflicts are mapped to sanitized `PlatformOperatorExistsError` / HTTP 409 behavior.
- Delivery failures for bootstrap, invite, reset, and break-glass are covered by rollback regressions.

## Files Changed

- `backend/api/app.py`
- `backend/api/v1/platform/operators.py`
- `backend/schemas/platform_operator.py`
- `backend/scripts/bootstrap_platform_operator.py`
- `backend/scripts/break_glass_platform_operator.py`
- `backend/services/email_delivery.py`
- `backend/services/platform_operator_service.py`
- `backend/tests/test_dc11p2_platform_operator_lifecycle.py`
- `backend/tests/test_route_authorization_policy.py`
- `ai-ledger/product-ai/2026-07-14_dc11p2_platform_operator_lifecycle.md`

## Schema Sufficiency

The four existing DC-11P1 tables are sufficient for DC-11P2:

- `public.platform_operators`
- `public.platform_operator_setup_tokens`
- `public.platform_operator_reset_tokens`
- `public.platform_operator_recovery_credentials`

No migration `035` was created. Migration `034_platform_operators.py` was not modified. No `<=034` migration was modified.

## GitNexus Impact

Pre-edit impact analysis was run for existing symbols touched or depended on:

- `configure_app`: MEDIUM risk, router/app wiring and tests only.
- `record_password_reset_email`: LOW risk.
- `append_audit_entry`: CRITICAL risk because many platform routes depend on audit append semantics; implementation was not modified, only called from the new P2 service.
- `PlatformOperator`: LOW risk.
- `PlatformOperatorSetupToken`: LOW risk.
- `PlatformOperatorResetToken`: LOW risk.
- `PlatformOperatorRecoveryCredential`: LOW risk.
- `get_platform_db`: LOW risk.
- `PUBLIC_ALLOWLIST`: LOW risk.
- `PLATFORM_PUBLIC_ALLOWLIST`: LOW risk.
- `classify_route`: LOW risk.
- `clear_dev_email_deliveries`: MEDIUM risk, direct test helpers only.

No impact analysis expanded into payments, orders, tenant provisioning, or other product business domains.

R1 pre-edit impact highlights:

- `PlatformOperatorService`: HIGH, confined to platform lifecycle routes/scripts/tests.
- `bootstrap_first_operator`: LOW.
- `invite_operator`: LOW.
- `enable_operator`: LOW.
- `break_glass_recover`: LOW.
- `store_recovery_credential`: LOW.
- `record_platform_operator_setup_email`: LOW.
- `record_platform_operator_reset_email`: LOW.
- `setup_platform_operator_credential`: LOW.
- `reset_platform_operator_password`: LOW.
- `PlatformOperatorActionResponseData`: MEDIUM, confined to platform lifecycle routes/tests.

R1 GitNexus compare result against `d0c7c6f1`: HIGH, 123 changed symbols, 9 affected flows.

## Validation

Disposable validation database:

- Container: `dc10a_pg_547b0b29`
- Database: `dc11p2_test`
- URL used by tests: disposable local Postgres on `localhost:55432/dc11p2_test`
- Redis used by ASGI tests: `redis://localhost:56379/0`

Commands and results:

- `pytest tests/test_dc11p2_platform_operator_lifecycle.py -q`: `7 passed`
- `pytest tests/test_route_authorization_policy.py -q`: `37 passed`
- `pytest tests/test_dc11p1_platform_operator_schema.py -q`: `36 passed`
- `python -m py_compile services/platform_operator_service.py schemas/platform_operator.py api/v1/platform/operators.py scripts/bootstrap_platform_operator.py scripts/break_glass_platform_operator.py`: passed

R1 RED/GREEN evidence:

- RED after adding R1 regressions before implementation: `pytest tests/test_dc11p2_platform_operator_lifecycle.py -q` -> `11 failed, 6 passed`.
- GREEN after R1 fixes: `pytest tests/test_dc11p2_platform_operator_lifecycle.py -q` -> `17 passed`.
- DC-11P0 contract after R1 boundary update: `pytest tests/test_dc11p0_platform_operator_identity_contract.py -q` -> `16 passed`.
- DC-11P1 schema after R1: `pytest tests/test_dc11p1_platform_operator_schema.py -q` -> `36 passed`.
- Route authorization policy after R1: `pytest tests/test_route_authorization_policy.py -q` -> `37 passed`.
- R1 `py_compile`: passed for service, schemas, routes, scripts, and updated tests.
- R1 `git diff --check`: passed.
- R1 ASCII/mojibake scan on changed files: passed.
- R1 pre-commit on changed files: passed.
- R1 `detect-secrets-hook --baseline .secrets.baseline` on changed files: passed.

Initial focused test attempt without explicit local DB/Redis env failed because the default `postgres`/`redis` hostnames do not resolve from this Windows shell. Validation was rerun successfully against the disposable local test container endpoints above.

## DC-11P2 Boundaries Preserved

- No `backend/api/v1/auth.py` changes.
- No `backend/core/security.py` changes.
- No `backend/api/v1/platform/p10/guard.py` changes.
- No frontend changes.
- No strict-mode closeout changes.
- No production config changes.
- No protected branch push.
- No production data, production credentials, real JWTs, or customer emails used.

## Anticipated DC-11P3 Work

Expected files for P3 dedicated platform identity enforcement:

- `backend/api/v1/auth.py`: add dedicated platform operator login/token exchange surface or branch from existing login while preserving tenant login behavior.
- `backend/core/security.py`: add platform operator JWT claims such as `platform_operator_id`, `platform_role`, and `auth_version`, with strict separation from tenant `user_id`/`tenant_id` context.
- `backend/api/v1/platform/p10/guard.py`: require dedicated platform operator identity in strict mode, verify operator status/auth_version, and retire identity-only `super_admin` platform access once P3 strict path is enabled.

P3 acceptance notes only, not implemented in R1:

- Management routes must become `platform_admin`-only.
- P3 must pass authenticated platform operator `actor_id` into audit records and `invited_by`.
- Tenant legacy `super_admin` must never become the dedicated platform operator actor identity.
