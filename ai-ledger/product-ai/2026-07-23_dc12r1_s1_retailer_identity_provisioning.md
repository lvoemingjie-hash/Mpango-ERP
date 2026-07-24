# DC-12R1-S1 Retailer Identity, Credential and Invitation Foundation

## Verdict

**PASS_FOR_CTO_DC12R1_S1_REVIEW**

S1 implements the authoritative retailer-user mapping, migration 036, the atomic
invitation lifecycle (CTO order B), retailer-owned setup/reset credentials, and
backend identity resolution — all CTO corrections A–G and the 7 final constraints
honored. 14 new S1 backend tests + 9 frontend Vitest pass; 183 regression tests
green; single Alembic head `036_retailer_mvp_identity`.

## Base / Branch

- Base: `origin/opencode/dc12r1-retailer-mvp-identity-invitation-design-2026-07-23 @ 78c40563`
- Baseline checks (correction A): `merge-base --is-ancestor origin/product-dev-recovered 78c40563` exit 0; post-worktree `merge-base --is-ancestor 78c40563 HEAD` exit 0.
- Branch: `opencode/dc12r1-s1-retailer-identity-provisioning-2026-07-23`
- No merge to product-dev-recovered, no deploy, no S2/S3/S4 started.

## GitNexus Impact (correction #1)

- `register_with_invitation` — LOW (1 direct dependent: `register_retailer_with_invitation` API).
- `resolve_client_identity` — LOW (FastAPI `Depends`, not in static call graph; covered by route tests).
- `mark_used` — LOW (0 dependents; replaced by conditional-update in the new transaction).
- `hash_token` — **CRITICAL (7 direct dependents: password_reset_service, owner_credential_service, onboarding_service + auth endpoints).** Decision: **REUSE, not modify** — so the blast radius is unchanged; the owner-auth/dc3b regressions (run green below) prove no break.

## CTO Corrections A–G — evidence

- **A Baseline** — both `merge-base` checks exit 0 (above).
- **B Invitation transaction order** — `RetailerProvisioningService.register_with_invitation` follows exactly: SELECT FOR UPDATE → validate → retailer → binding+user+mapping+role → setup token → SMTP before commit → mark used with `used_retailer_id` (only after `retailer_id` exists) → commit. Any failure rolls back the invitation state too (`services/retailer_provisioning_service.py`).
- **C Retailer permission namespace** — only `client:catalog:read`, `client:orders:read`, `client:orders:create`, `client:payments:read`, `client:payments:create`, `client:finance:read` granted to `retailer_operator`; `invitations:revoke` granted to admin only (migration 036 + bootstrap parity + create_wholesaler). Route-policy test proves retailer token is denied generic `/orders`, `/payments`, `/finance`, invitation-management and platform routes.
- **D Pending credential user** — `users.password_hash` stays **NOT NULL** (no ORM/DDL/bootstrap change). First setup creates `is_active=false` with an unrecoverable random-secret hash; setup consumption activates + writes the real hash; copy-existing-hash creates an active user. Test `test_pending_user_cannot_authenticate` proves no recoverable/default password exists.
- **E PUBLIC_FRONTEND_URL** — already present on the base branch (`config.py:152-156`); not re-added. Only `build_retailer_setup_link`/`build_retailer_reset_link` + fragment pages added.
- **F Invitation lookup** — `POST /invitations/lookup` (JSON body) added; legacy `GET /invitations/{code}` retained and marked `deprecated=True` (one live consumer: `InvitePage.tsx`); no new frontend/email uses the GET path.
- **G** — all other S1 requirements implemented.

## 7 Final Constraints — evidence

1. **GitNexus MCP** — impact run for all targets (above); HIGH/CRITICAL (`hash_token`) recorded + decided REUSE.
2. **Reissue/revoke tenant-scoped** — `reissue_setup_token` verifies the caller's `wholesaler_id` owns a binding for the retailer (`_verify_tenant_owns_retailer`); dedicated `retailers:reissue_credential` permission (admin only); cross-tenant → neutral 404 (`test_cross_tenant_reissue_is_neutral_404`). Invitation revoke checks `invitation.wholesaler_id == token.tenant_id`.
3. **Forgot-password true-neutral** — no-account/unverified/wrong-code/SMTP-failure all return identical neutral response; SMTP failure rolls back token + sanitized log (no email/token/link) (`test_forgot_password_neutral_for_unknown_account`).
4. **Identity collision fail-closed** — existing retailer matched by phone: submitted email must match the canonical (verified) email, else `RETAILER_IDENTITY_CONFLICT` rollback; unverified legacy email is never silently overwritten.
5. **SMTP timeout** — `_send_smtp_email` uses `timeout=15`; no broad `except Exception` masking DB errors as email errors (DB errors propagate; only `EmailDeliveryNotConfiguredError` is mapped to rollback).
6. **Permission/route gates** — retailer_operator gets only `client:*`; route-policy test asserts denial of all non-`/client/*` tenant business routes + `/platform/*`. S1 uses synthetic signed contextual tokens in tests (real client login is S2).
7. **Migration/compat** — `users.password_hash` nullability untouched; only design-required indexes added; legacy GET retained/deprecated; `downgrade()` is fail-closed (raises, no destructive DDL).

## What was implemented

- **Migration `036_retailer_mvp_identity`** (down_revision `035`): `bindings.tenant_user_id` + partial unique; `retailers.email_verified_at`; invitation `revoked_at`/`revoked_by` + NOT NULL `expires_at` (7-day default/backfill); `retailer_credential_setup_tokens` (retailer_id+binding_id) + `retailer_password_reset_tokens` (retailer-scoped); per-live-tenant `retailer_operator` role + 6 `client:*` perms + `invitations:revoke`→admin + `ux_users_email_active`. Read-only preflight (duplicate emails, conflicting mappings, orphan bindings). Forward-only; idempotent second run; single head.
- **Bootstrap parity** (`bootstrap_tenant_schema.py`): `_reconcile_rbac_s1` seeds retailer_operator + client perms + email index for fresh tenants (password_hash stays NOT NULL).
- **Atomic provisioning** (`services/retailer_provisioning_service.py`): full CTO-order-B transaction; unified credentials (copy-on-identical / setup-token-on-none / fail-closed-on-conflict); retailer-scoped reset; restricted reissue; truly-neutral forgot.
- **APIs**: `POST /retailers/setup-credential`, `POST /retailers/{id}/reissue-setup` (tenant-scoped), `POST /client/auth/forgot-password`, `POST /client/auth/reset-password`, `POST /invitations/lookup`, `POST /invitations/{id}/revoke` (tenant-scoped). Legacy GET deprecated.
- **resolve_client_identity**: `token.user_id → binding.tenant_user_id → retailer_id` (no email); requires `retailer_operator` role + active binding + tenant match.
- **Frontend**: `/retailer/setup-credential` + `/retailer/reset-password` fragment-only pages, `urlToken` util (query-reject-first), `authService` methods, AppRouter routes.

## Test Results (worktree-local Poetry env, Python 3.12, bcrypt 4.0.1 / passlib 1.7.4; disposable PG16 + Redis7)

| Suite | Result |
|---|---|
| `test_dc12r1_s1_retailer_identity.py` (new) | 14 passed |
| `test_dc1g_retailer_registration_binding_balance.py` | pass (updated for new finite-expiry + tenant-user contract) |
| `test_dc3b_credential_recovery_backend.py` | 16 passed |
| `test_auth_regressions.py` + `test_auth_bypass.py` | 7 passed |
| `test_route_authorization_policy.py` | pass (4 new public routes added, CTO-approved) |
| `test_orders_api.py` + `test_payments_api.py` | pass |
| `test_dc10k_finance_receivables_runtime.py` + `test_finance_receivables_api.py` | pass |
| `test_tenant_isolation.py` + `test_global_tenant_filter.py` | pass |
| `test_phase4_pricing_safe_orders.py` | pass |
| `test_dc11d_payment_replay_concurrency_integrity.py` | pass |
| `test_s6_4_async_exports.py` + `test_dc10e_export_worker_tenant_context.py` | pass |
| Frontend `RetailerCredentialPages.test.tsx` (Vitest) | 9 passed |
| Frontend `pnpm build` (tsc + vite) | success |
| `alembic heads` / `current` | `036_retailer_mvp_identity` (single head); second upgrade no-op |

## Changed-file proof

Backend: `models/retailer_credentials.py` (new), `models/{binding,retailer,invitation,__init__}.py`, `alembic/versions/036_retailer_mvp_identity.py` (new), `scripts/{bootstrap_tenant_schema,create_wholesaler}.py`, `services/{email_delivery,onboarding_service,retailer_provisioning_service(new),retailer_service}.py`, `repositories/{invitation,binding}_repository.py`, `api/v1/client/{auth(new),dependencies}.py`, `api/v1/{retailers,invitations}.py`, `api/app.py`, `schemas/retailer_credentials.py` (new), `tests/{test_dc12r1_s1_retailer_identity(new),test_dc1g...,test_route_authorization_policy}.py`.
Frontend: `src/pages/retailer/{RetailerSetupCredentialPage,RetailerResetPasswordPage}.tsx` (new), `src/utils/urlToken.ts` (new), `src/services/authService.ts`, `src/router/AppRouter.tsx`, `src/tests/RetailerCredentialPages.test.tsx` (new).
