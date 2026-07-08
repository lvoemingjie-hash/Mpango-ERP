# U6-K Production SMTP Email Delivery

## Scope

- Implement production-safe SMTP email delivery for onboarding verification email.
- Preserve dev/test in-memory sink outside production.
- Keep production fail-closed when SMTP config is missing or send fails.
- No frontend, migration, deploy, VPS, or `product-dev-recovered` push.

## Implementation Notes

- Added email delivery settings for `EMAIL_PROVIDER`, `EMAIL_DELIVERY_MODE`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, `SMTP_STARTTLS`, and `SMTP_USE_TLS`.
- Production delivery requires `EMAIL_PROVIDER=smtp`, `EMAIL_DELIVERY_MODE=smtp`, and complete SMTP host/user/password/from config.
- SMTP send failures raise `EMAIL_DELIVERY_NOT_CONFIGURED` and signup rolls back flushed registration/token rows.
- Non-production runtimes continue using the dev/test sink and do not require SMTP config.
- The email body may contain the verification link because email is the delivery channel; raw tokens are not persisted in DB or returned by API.

## Validation Results

- `poetry run pytest tests/test_u6k_production_smtp_email_delivery.py -q`: `5 passed` using disposable Postgres `opencode_u6k_pg` on `127.0.0.1:55439`.
- `poetry run pytest tests/test_u6c_signup_email_verification_skeleton.py tests/test_u6d_verify_email_endpoint.py tests/test_u6e_onboarding_status_endpoint.py tests/test_u6f_onboarding_auth_chain_closeout.py -q`: `38 passed`.
- `poetry run pytest tests/test_route_authorization_policy.py tests/test_auth_regressions.py -q`: `36 passed`.
- `poetry run alembic heads`: `028_owner_credential_setup_tokens (head)`.
- `git diff --check`: passed.
- ASCII/mojibake scans: passed on added diff and new U6-K files.
- Secret-term scan: reviewed; findings are expected config/test token/password/SMTP terminology and placeholders only.
- `pre-commit run --files .env.example backend/.env.example backend/core/config.py backend/services/email_delivery.py backend/services/onboarding_service.py backend/tests/test_u6k_production_smtp_email_delivery.py ai-ledger/product-ai/2026-07-09_u6k_production_smtp_email_delivery.md`: passed.
- Implementation/evidence commit: `6987eff7 feat(U6-K): add production SMTP email delivery`.
- `npx gitnexus analyze`: repository indexed successfully, `7,119 nodes | 20,340 edges | 477 clusters | 239 flows`.
- `npx gitnexus status`: indexed commit `6987eff`, current commit `6987eff`, status up to date.
