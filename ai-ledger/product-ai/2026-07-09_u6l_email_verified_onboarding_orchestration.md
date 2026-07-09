# U6-L Email-Verified Onboarding Orchestration

## Scope

- Trigger backend onboarding orchestration after successful email verification.
- Flow: verify email, provision/reconcile tenant, issue owner setup credential token, send owner setup email.
- Keep public API responses neutral and do not return status/setup tokens.
- Preserve setup credential endpoint behavior.
- No frontend, migration, deploy, VPS, or `product-dev-recovered` push.

## Implementation Notes

- `verify_email_token` now calls `complete_email_verified_onboarding` after marking the registration email verified; the verification token is marked used only after owner setup email delivery succeeds.
- The orchestration helper provisions the tenant, issues an owner credential setup token, and sends the owner setup email only when a new setup token is issued.
- Owner setup email uses the same production SMTP/dev sink boundary as verification email.
- Raw setup token appears only in the delivered email body/link and is not returned by public API responses.
- Production owner setup email missing configuration fails before provisioning; SMTP send failure after provisioning returns neutral `503` but leaves the durable public wholesaler/schema anchor for retry.

## R1 Finding/Fix

- Finding: real tenant bootstrap commits schema DDL independently, while owner setup SMTP failure happened after provisioning but before the public request transaction committed. This could leave a tenant schema without a durable public registration/wholesaler anchor; previous tests used `FakeProvisioningService` and did not prove real-bootstrap retry/reconcile behavior.
- Fix: preflight owner setup email configuration before provisioning, persist the public provisioning anchor after real bootstrap succeeds and before setup token issuance/email delivery, and keep the verification token unused until setup email delivery succeeds.
- Retry behavior: an unused verification token may retry only for an `active` provisioned registration with `wholesaler_id`, `tenant_schema`, `provisioning_completed_at`, and no active owner setup token. Retry reconciles the same assignment, issues exactly one setup token, and sends exactly one setup email.

## Validation Results

- Implementation commit: `6ab2a436` (`feat(U6-L): orchestrate onboarding after email verification`).
- `poetry run pytest tests/test_u6f_onboarding_auth_chain_closeout.py -q` -> 7 passed.
- `poetry run pytest tests/test_u6d_verify_email_endpoint.py tests/test_u6e_onboarding_status_endpoint.py tests/test_u6i5_owner_credential_setup_endpoint.py -q` -> 31 passed.
- `poetry run pytest tests/test_u6l_email_verified_onboarding_orchestration.py -q` -> 6 passed.
- `poetry run pytest tests/test_route_authorization_policy.py tests/test_auth_regressions.py -q` -> 36 passed.
- `poetry run alembic heads` -> `028_owner_credential_setup_tokens (head)`.
- `git diff --check` -> passed; Git emitted LF/CRLF warnings only.
- Mojibake scan for U6-L Python files -> no matches.
- `pre-commit run --files <U6-L files>` -> passed, including `detect-secrets`.
- Repo-wide `pre-commit run --all-files` is blocked by pre-existing unrelated YAML parse errors and a Windows GBK UnicodeEncodeError while printing non-ASCII filenames; hook-created unrelated edits were restored.
- `gitleaks` binary unavailable on PATH; no Gitleaks result recorded.
- Post-commit `npx gitnexus analyze` -> indexed successfully; 7,183 nodes, 20,532 edges, 483 clusters, 243 flows.
- Post-commit `npx gitnexus status` -> up-to-date at current commit `6ab2a43`.

## R1 Validation Results

- `poetry run pytest tests/test_u6l_email_verified_onboarding_orchestration.py::test_real_bootstrap_owner_setup_smtp_failure_persists_anchor_and_retry_reconciles -q` initially failed on `pending_email_verification` after real bootstrap SMTP failure, proving the missing public anchor.
- `poetry run pytest tests/test_u6l_email_verified_onboarding_orchestration.py -q` -> 7 passed.
- `poetry run pytest tests/test_u6d_verify_email_endpoint.py tests/test_u6e_onboarding_status_endpoint.py tests/test_u6i5_owner_credential_setup_endpoint.py -q` -> 31 passed.
- `git diff --check` -> passed; Git emitted LF/CRLF warnings only.
- Mojibake scan for backend Python files -> no matches.
- `pre-commit run --files backend/services/onboarding_service.py backend/tests/test_u6l_email_verified_onboarding_orchestration.py` -> passed, including `detect-secrets`.
- Pre-commit caveat from initial U6-L remains: repo-wide `pre-commit run --all-files` is blocked by unrelated legacy YAML parse errors and Windows GBK filename printing.
- Pre-commit secret gate passed for changed R1 files; `gitleaks` binary remains unavailable on PATH.
- Pre-commit `npx gitnexus analyze` -> already up to date at committed head `4808ae5`; final post-commit GitNexus evidence will be recorded in the session summary.
