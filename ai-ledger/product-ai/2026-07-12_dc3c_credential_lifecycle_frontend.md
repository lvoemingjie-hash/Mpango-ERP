# 2026-07-12 DC-3C Credential Lifecycle Frontend

## Scope

- Branch: `opencode/dc3c-credential-lifecycle-frontend-2026-07-12`
- Base: `origin/product-dev-recovered` at `b10a43fe993efaeb7372c10f716b8695bf0c3c7f`
- Area: customer-facing credential setup and password recovery UI
- Out of scope: backend changes, migrations, deployment, config, package/lockfile changes, token decoding, analytics

## Implementation

- Added public routes:
  - `/setup-credential`
  - `/forgot-password`
  - `/reset-password`
- Added auth service methods:
  - `setupCredential({ setupToken, password })`
  - `forgotPassword({ email })`
  - `resetPassword({ resetToken, newPassword })`
- Added setup credential page that reads `setupToken` from the URL, keeps it only in component state, clears it from the visible URL with `history.replaceState`, and submits it in JSON body only.
- Added forgot password page that posts `{ email }` and always displays neutral success copy: `If an account exists, reset instructions will be sent.`
- Added reset password page that reads `resetToken` from the URL, keeps it only in component state, clears it from the visible URL with `history.replaceState`, and submits it in JSON body only.
- Added `Forgot password?` link on the login page without changing login submit behavior.

## Security Notes

- Tokens are not logged.
- Tokens are not written to `localStorage` or `sessionStorage`.
- Tokens are not sent in backend query strings.
- Frontend does not decode or inspect JWTs.
- User-facing invalid/expired link messages are neutral and friendly.

## Regression Coverage

- `frontend/src/tests/CredentialLifecyclePages.test.tsx`
- Setup page test verifies `setupToken` is removed from the visible URL, sent to `/auth/onboarding/setup-credential` in JSON body only, not persisted to storage, and success links to `/login`.
- Forgot password test verifies neutral success copy even when the request rejects.
- Reset page test verifies `resetToken` is removed from the visible URL, sent to `/auth/reset-password` in JSON body only, not persisted to storage, and success links to `/login`.
- Login page test verifies the `/forgot-password` link exists.

## GitNexus

- Base index was stale after branch switch; ran `npx gitnexus analyze` before edits.
- Pre-edit impact:
  - `AppRouter`: LOW, impacted count 0.
  - `LoginPage`: LOW, impacted count 0.
  - `authService`: target not found by GitNexus under that symbol name.

## Validation

- `pnpm install --frozen-lockfile` was required because `frontend/node_modules` was absent. It did not change package or lock files.
- `pnpm exec vitest run src/tests/CredentialLifecyclePages.test.tsx`: 4 passed.
- `pnpm build`: passed.
- Build/test warnings observed:
  - Existing duplicate `jsdom` key warning in `frontend/package.json`.
  - Existing Vite chunk-size warning.
  - React Router future-flag warnings in tests.

## Verdict

DC-3C credential lifecycle frontend is implemented locally with body-only backend token submission and no client-side token persistence.
