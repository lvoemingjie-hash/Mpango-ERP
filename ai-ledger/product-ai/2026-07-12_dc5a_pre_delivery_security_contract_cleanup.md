# 2026-07-12 DC-5A Pre-Delivery Security/Contract Cleanup

## Scope

- Branch: `opencode/dc5a-pre-delivery-security-contract-cleanup-2026-07-12`
- Base: `origin/product-dev-recovered` at `bf0649c0c0e09d2b902a49b2bf366c1323f4b0f5`
- Areas: export route authorization, login email normalization, RBAC contract vocabulary, MVP auth-storage risk note
- Out of scope: migrations, deployment, backend credential lifecycle behavior, package/lockfile changes, broad auth storage redesign

## GitNexus Impact Checks Before Edits

- `create_export`: LOW, impacted count 0.
- `get_export_status`: LOW, impacted count 0.
- `download_export`: LOW, impacted count 0.
- `LoginPage`: LOW, impacted count 0.
- Generic `login` resolved to a test helper, so `find_user_across_tenants` was checked: LOW, impacted count 4, including `backend/api/v1/auth.py:login` and frontend login submit paths.
- No HIGH or CRITICAL impact was reported.

## Export Authorization Fix

- `GET /api/v1/exports/{job_id}` now uses `RequirePermission("exports:create")`.
- `GET /api/v1/exports/{job_id}/download` now uses `RequirePermission("exports:create")`.
- Tenant ownership checks remain unchanged and still run inside the handlers.
- Route policy tests now prove:
  - POST `/exports` requires `exports:create`.
  - GET `/exports/{job_id}` requires `exports:create`.
  - GET `/exports/{job_id}/download` requires `exports:create`.
  - No export route is plain authenticated-only.

## Login Email Normalization

- Backend login normalizes the email with `strip().lower()` before cross-tenant user lookup.
- Frontend login submit also trims/lowercases email before posting to `/auth/login` for immediate UX consistency.
- Signup normalization was not changed.

## RBAC Contract Correction

- Replaced stale `products:*` vocabulary with `skus:*`.
- Documented current MVP permission vocabulary from route guards and tenant bootstrap/admin setup code.
- Clarified that `admin` is the seeded MVP role with all current permissions.
- Clarified that sales, warehouse, and finance mappings are examples only until explicitly seeded and tested.
- Documented `exports:create` as the current MVP permission for export create/status/download.

## Raw JWT Persistence Decision

MVP temporarily persists access/refresh JWTs in browser storage; accepted for delivery with immediate post-MVP hardening task to move refresh token to HttpOnly SameSite cookie or memory-only strategy.

No broad auth storage redesign was attempted in this slice.

## Regression Evidence

- Added backend login normalization test that directly calls the login handler and verifies mixed-case, padded email is normalized before lookup.
- Added frontend login test that verifies `/auth/login` receives lowercase trimmed email.
- Tightened route authorization policy tests for export GET routes.

## Validation

- Red check before export fix: `poetry run pytest tests/test_route_authorization_policy.py -q` failed on export status/download being plain `authenticated`.
- Red check before login fixes: backend login normalization test and frontend login submit test failed with mixed-case email passed through.
- Post-fix focused checks passed:
  - `poetry run pytest tests/test_route_authorization_policy.py -q`: 35 passed.
  - `poetry run pytest tests/test_s6_4_async_exports.py -q`: 33 passed.
  - `poetry run pytest tests/test_dc5a_login_email_normalization.py -q`: 1 passed.
  - `pnpm exec vitest run src/tests/CredentialLifecyclePages.test.tsx`: 5 passed.
  - `poetry run python -m py_compile api/v1/exports.py api/v1/auth.py`: passed.
  - `pnpm build`: passed.
  - `git diff --check`: clean except LF-to-CRLF warnings.
  - ASCII/mojibake scans on changed files: clean.
  - `pre-commit` on changed files: passed, including detect-secrets.
  - `npx gitnexus analyze`: completed.
  - `npx gitnexus status`: up to date at `bf0649c`.

## Notes

- Existing warnings observed during tests/build are unrelated to DC-5A:
  - SQLAlchemy `declarative_base` deprecation warning.
  - `datetime.utcnow()` deprecation warning in existing auth response timestamp code.
  - Duplicate `jsdom` key warning in `frontend/package.json`.
  - React Router future-flag warnings in frontend tests.
- No backend credential behavior, migration, deployment, package, or lockfile changes were made.

## Verdict

DC-5A closes the selected pre-delivery P1/P2 items that are safe for MVP delivery and leaves raw browser JWT persistence as an explicit accepted post-MVP hardening item.
