# 2026-07-12 DC-3E Frontend SPA Runtime Crash Fix

## Scope

- Branch: `opencode/dc3e-frontend-spa-runtime-crash-fix-2026-07-12`
- Base: `origin/product-dev-recovered` at `51cfd227094235028f6a09fd173576e1ddb8caf5`
- Area: frontend production SPA runtime crash triage and fix
- Out of scope: backend credential behavior, migrations, deployment, API changes, token handling changes

## Reproduction

- Built the frontend production bundle with `pnpm build`.
- Served `frontend/dist` with `pnpm preview --host 127.0.0.1 --port 4173`.
- Seeded sanitized persisted auth state using fake redacted tokens and a user object without `roles`, matching a stale/incomplete persisted auth shape.
- Navigated to `/` in the production bundle.

## Browser Evidence

Sanitized production console stack:

```text
TypeError: Cannot read properties of undefined (reading '0')
    at I2 (http://127.0.0.1:4173/assets/index-DLGu9MHb.js:84:44665)
    at Cf (http://127.0.0.1:4173/assets/index-DLGu9MHb.js:38:17018)
    at _y (http://127.0.0.1:4173/assets/index-DLGu9MHb.js:40:44058)
    at wy (http://127.0.0.1:4173/assets/index-DLGu9MHb.js:40:39790)
React Router caught the following error during render TypeError: Cannot read properties of undefined (reading '0')
```

Source localization:

- `frontend/src/components/layout/Header.tsx` read `user.roles[0]` during protected route shell rendering.
- With an access token present, `/login`, `/setup-credential`, `/forgot-password`, and `/reset-password` are public routes and redirect to `/`; the crash in the protected app shell could therefore block browser validation of all these routes when stale auth state exists.

## Root Cause

- Category: frontend source code bug.
- Not dependency/lockfile drift: the same locked production build reproduced the issue only when runtime persisted state had missing `roles`.
- Not build config: `pnpm build` completed successfully before and after the fix.
- Not deployment/gateway: reproduced locally with `vite preview` serving the production bundle.

## Fix

- Changed `Header` to derive the role label with `Array.isArray(user?.roles) ? user.roles[0] : undefined`.
- The UI now falls back to `User` when persisted user data lacks a roles array.
- No auth routing behavior, credential token scrubbing, or body-only token submission behavior was changed.

## Regression Proof

- Added `frontend/src/tests/Header.test.tsx`.
- The test renders `Header` with sanitized persisted-auth-shaped user data that intentionally omits `roles` and verifies the header renders `User` instead of throwing.

## Production Route Smoke

After the fix and production rebuild:

- `/` -> `/login`, heading `Mpango ERP`, console error count 0.
- `/login` -> `/login`, heading `Mpango ERP`, console error count 0.
- `/setup-credential?setupToken=redacted-test-token` -> `/setup-credential`, heading `Set your password`, console error count 0.
- `/forgot-password` -> `/forgot-password`, heading `Reset your password`, console error count 0.
- `/reset-password?resetToken=redacted-test-token` -> `/reset-password`, heading `Choose a new password`, console error count 0.

Setup/reset visible query token scrubbing was confirmed by the final browser URLs above.

## Validation

- `pnpm exec vitest run src/tests/Header.test.tsx src/tests/CredentialLifecyclePages.test.tsx`: 5 passed.
- `pnpm exec vitest run src/tests/CredentialLifecyclePages.test.tsx`: required focused test retained.
- `pnpm build`: passed.
- Production-bundle browser smoke: passed for listed routes.

## Notes

- Existing warnings remain unrelated to DC-3E:
  - Duplicate `jsdom` key in `frontend/package.json`.
  - Vite chunk-size warning.
  - React Router future-flag warnings in tests.
- No backend, migration, API, package, lockfile, deploy, or protected branch changes were made.

## Verdict

DC-3E fixes the production SPA runtime crash caused by unsafe header role rendering against stale/incomplete persisted auth state. DC-3D browser validation can be rerun after this branch is merged or checked out.
