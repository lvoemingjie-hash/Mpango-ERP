# U6-L Email-Verified Onboarding Orchestration

## Scope

- Trigger backend onboarding orchestration after successful email verification.
- Flow: verify email, provision/reconcile tenant, issue owner setup credential token, send owner setup email.
- Keep public API responses neutral and do not return status/setup tokens.
- Preserve setup credential endpoint behavior.
- No frontend, migration, deploy, VPS, or `product-dev-recovered` push.

## Implementation Notes

- `verify_email_token` now calls `complete_email_verified_onboarding` after marking the verification token used and registration email verified.
- The orchestration helper provisions the tenant, issues an owner credential setup token, and sends the owner setup email only when a new setup token is issued.
- Owner setup email uses the same production SMTP/dev sink boundary as verification email.
- Raw setup token appears only in the delivered email body/link and is not returned by public API responses.
- Production owner setup email configuration or SMTP send failure returns neutral `503` and rolls back the public DB transaction.

## Validation Results

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
- `npx gitnexus analyze` -> indexed successfully; 7,174 nodes, 20,532 edges, 474 clusters, 243 flows.
- `npx gitnexus status` -> up-to-date at current commit `19f6afd`.
