# U6-I6 Onboarding End-to-End Closeout Gate

## Scope

- Added a backend-only end-to-end closeout gate for the owner onboarding chain.
- Covered public signup, email verification, onboarding status, tenant provisioning, owner setup token issue, credential setup endpoint, and tenant admin/RBAC proof.
- No production code was changed.
- No frontend, migration, deploy, VPS, `.env`, or `product-dev-recovered` push was performed.

## Proof Points

- Public signup creates one pending registration and hash-only email verification/status tokens.
- Verify-email moves the registration to `email_verified`.
- Onboarding status returns `email_verified` after verification.
- Tenant provisioning service claims the registration, provisions wholesaler/schema, clears registration password hash, and returns `existing` on a second provisioning call.
- Owner setup token issue returns the raw token once, persists only `token_hash`, and returns `existing` with no raw token on duplicate issue.
- `POST /api/v1/auth/onboarding/setup-credential` creates the tenant owner user, admin role, canonical permissions, user role mapping, and admin role permission mappings.
- The owner/admin is found in the tenant schema, is active, has an admin role, and the supplied password verifies against the stored hash.
- Replaying the consumed setup token returns neutral 401 and does not change `password_hash`.
- GET and POST query-string setup token paths do not work; POST query-string rejection leaves a fresh setup token unused.
- Public responses are checked for absence of raw tokens, token hashes, password hashes, tenant schema, user ID, role ID, and permission IDs.

## Validation Results

- `poetry run pytest tests/test_u6i6_onboarding_e2e_closeout.py -q`: `1 passed` using disposable Postgres `opencode_u6i6_pg` on `127.0.0.1:55437`.
- `poetry run pytest tests/test_u6i5_owner_credential_setup_endpoint.py tests/test_u6f_onboarding_auth_chain_closeout.py tests/test_route_authorization_policy.py -q`: blocked by existing U6F assertion in `tests/test_u6f_onboarding_auth_chain_closeout.py::test_migration_schema_sanity_for_u6f_closeout_gate`.
- Observed failure: `ScriptDirectory.from_config(alembic_cfg).get_current_head()` returned `028_owner_credential_setup_tokens`; existing U6F test still expects `027_onboarding_status_tokens`.
- U6F file is outside the U6-I6 allowed edit list, so it was not changed.
- `git diff --check`: passed.
- ASCII/mojibake scans: passed.
- Secret-term scan: reviewed; findings are expected test token/password/hash terminology and allowlisted test credentials only.
- `pre-commit run --files backend/tests/test_u6i6_onboarding_e2e_closeout.py ai-ledger/product-ai/2026-07-09_u6i6_onboarding_e2e_closeout.md`: passed.
- Implementation/evidence commit: `aa566b1d test(U6-I6): add onboarding e2e closeout gate`.
- `npx gitnexus analyze`: repository indexed successfully, `7,066 nodes | 20,207 edges | 470 clusters | 239 flows`.
- `npx gitnexus status`: indexed commit `aa566b1`, current commit `aa566b1`, status up to date.
- Verdict condition: `STOP_AND_REPORT_CTO` unless CTO authorizes updating the U6F closeout migration-head expectation or expands U6-I6 allowed files.

## R1 Closeout Regression Head Alignment

- CTO authorized editing `backend/tests/test_u6f_onboarding_auth_chain_closeout.py` because the U6F closeout gate carried stale Alembic head contract text from before U6-I1/U6-I2.
- Root cause: `TEST_CONTRACT_DRIFT`, not a product defect.
- Updated the U6F migration sanity assertion from `027_onboarding_status_tokens` to the current canonical onboarding/auth head `028_owner_credential_setup_tokens`.
- The test was not weakened: it now asserts `script.get_heads() == ["028_owner_credential_setup_tokens"]` and `script.get_current_head() == "028_owner_credential_setup_tokens"`.
- `poetry run pytest tests/test_u6i6_onboarding_e2e_closeout.py -q`: `1 passed` using disposable Postgres `opencode_u6i6_r1_pg` on `127.0.0.1:55438`.
- `poetry run pytest tests/test_u6i5_owner_credential_setup_endpoint.py tests/test_u6f_onboarding_auth_chain_closeout.py tests/test_route_authorization_policy.py -q`: `51 passed`.
- `git diff --check`: passed.
- ASCII/mojibake scans: passed.
- Secret-term scan: reviewed; findings are expected test token/password/hash terminology and existing allowlisted test credentials only.
- `pre-commit run --files backend/tests/test_u6f_onboarding_auth_chain_closeout.py ai-ledger/product-ai/2026-07-09_u6i6_onboarding_e2e_closeout.md`: passed.
- R1 implementation/evidence commit: `6623d561 test(U6-I6): align U6F closeout alembic head`.
- `npx gitnexus analyze`: repository indexed successfully, `7,073 nodes | 20,208 edges | 476 clusters | 239 flows`.
- `npx gitnexus status`: indexed commit `6623d56`, current commit `6623d56`, status up to date.
