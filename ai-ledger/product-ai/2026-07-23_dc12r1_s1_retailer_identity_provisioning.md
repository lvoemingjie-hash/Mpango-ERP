# DC-12R1-S1 Retailer Identity, Credential and Invitation Foundation

> **R4 REPORT (2026-07-24).** This document is the R4 delivery record for
> the DC-12R1-S1 implementation. It supersedes all prior
> revisions. The initial S1 PASS (`450e372d`) was REVOKED by CTO
> `STOP_BEFORE_MERGE` and corrected through four review rounds (R1→R4).

## Verdict

**PASS_FOR_CTO_DC12R1_S1_R4_MERGE_REVIEW**

Branch: `opencode/dc12r1-s1-retailer-identity-provisioning-2026-07-23`
R4 implementation tip: `00aba91b` (fast-forward from `19351c91` to `197d09ca` to `e6ab4c86` to `450e372d`)
R4 report publication tip: `6a8ddcf348e9b1bdcc902929011e6212cc675cf8`
Base: `78c40563` (descends from `product-dev-recovered` @ `757aef26`)

---

## Revision History

| Rev | Commit | Trigger | Key fixes | Tests |
|---|---|---|---|---|
| S1 | `450e372d` | Initial implementation | Migration 036, atomic invitation lifecycle, retailer-owned credentials, resolve_client_identity, frontend pages | 14 S1 + 183 regression |
| R1 | `e6ab4c86` | CTO `STOP_BEFORE_MERGE` (5 P1 blockers) | Atomic credential update (all-or-nothing), pending placeholder semantics (is_active-aware), invitation expiry/timezone, reissue permission parity, migration fail-closed | +8 R1 (RED→GREEN) |
| R2 | `76b362e4` | Strict mapping + migration contract | Remove silent skips, pre-write existence checks, define `_constraint_exists`, semantic token-table validation, `pytest.raises(Exception)`→exact types, real-PG RBAC catalog | +4 R2 |
| R3 | `197d09ca` | Migration semantic contract | Column types/nullability, contype+pg_get_constraintdef, pg_index/pg_get_indexdef, no continue in hash preflight, two-phase write (validate then update) | +11 R3 |
| R4 | `19351c91`→`00aba91b` | Exact catalog equivalence | ZERO substring matching: conkey UNIQUE, confkey/confrelid/confdeltype FK, strict CHECK semantics, pg_index indisunique/indnkeyatts/pg_get_expr, VARCHAR lengths, both tables, transactional rollback proof, is_active-only hash preflight | +9 R4 |

---

## What S1 Implements

### Migration `036_retailer_mvp_identity` (down_revision `035`)
- `wholesaler_retailer_bindings.tenant_user_id` (nullable UUID, partial unique `(wholesaler_id, tenant_user_id)`)
- `retailers.email_verified_at` (nullable TIMESTAMPTZ)
- `invitations.expires_at` NOT NULL (7-day default + backfill) + `revoked_at`/`revoked_by`
- `public.retailer_credential_setup_tokens` (retailer_id + binding_id, FK CASCADE)
- `public.retailer_password_reset_tokens` (retailer-scoped, FK CASCADE)
- Per live tenant: `retailer_operator` role + 6 `client:*` permissions; `invitations:revoke` + `retailers:reissue_credential` → admin only
- `ux_users_email_active` partial unique index per tenant
- Read-only preflight (duplicate emails, conflicting mappings/hashes, incompatible catalog); forward-only; idempotent; single head

### Migration catalog validation (R4 exact equivalence — zero substring matching)
- **UNIQUE**: `pg_constraint.conkey` — exactly one local column (`token_hash`); composite rejected
- **FK**: `conkey`/`confkey`/`confrelid`/`confdeltype` — exact local col, ref table, ref col, CASCADE ('c')
- **CHECK purpose**: normalized exact equality `purpose = 'literal'` (rejects OR TRUE, wrappers, extras)
- **CHECK used/revoked**: exact `used_at IS NULL OR revoked_at IS NULL` (rejects AND FALSE, negation, extra conditions)
- **Index**: `indisunique=true`, `indnkeyatts=1`, key=`[retailer_id]` (no expression keys), `pg_get_expr(indpred)` exact three AND conditions (no OR, no extra, no missing)
- **VARCHAR lengths**: `character_maximum_length` — token_hash=128, purpose=64
- **Both tables**: setup and reset validated with identical exact catalog logic
- **Transaction rollback proof**: R4 used a helper-level validator proof. R5 supersedes this with an actual Alembic 035-to-036 rollback proof that validates malformed pre-existing token tables before migration mutations.

### Atomic invitation lifecycle (CTO order B)
SELECT FOR UPDATE → validate → retailer → binding + tenant user + tenant_user_id mapping + retailer_operator grant → optional setup token → SMTP before commit → mark used → commit. Any failure rolls back everything.

### Unified credentials (all-or-nothing, two-phase)
Phase 1: resolve + validate EVERY mapped copy (zero writes). Phase 2: update ALL copies only after Phase 1 passes. Any failure → outer transaction rollback; token NOT consumed; `email_verified_at` NOT updated; same token retryable after repair.

### Retailer-owned credential APIs
- `POST /retailers/setup-credential` (body-only token, marks email verified, activates user)
- `POST /retailers/{id}/reissue-setup` (tenant-scoped, `retailers:reissue_credential` perm, only while no established password, neutral 404 cross-tenant)
- `POST /client/auth/forgot-password` (truly neutral, SMTP-timeout, sanitized logs)
- `POST /client/auth/reset-password` (body-only, updates all mapped copies)
- `POST /invitations/lookup` (JSON body); legacy GET deprecated
- `POST /invitations/{id}/revoke` (tenant-scoped `invitations:revoke`)
- NO wholesaler password-reset or verified-email-change endpoint

### Authoritative client resolution
`token.user_id → binding.tenant_user_id → retailer_id` (no email); requires `retailer_operator` role + active binding + tenant match.

### Frontend
`/retailer/setup-credential` + `/retailer/reset-password` fragment-only pages (query-reject-first, scrub URL, JSON body), `urlToken` util, `authService` methods.

---

## Hash preflight (is_active-only)
`_check_conflicting_active_hashes` compares only `is_active = true AND is_deleted = false` copies. Inactive placeholder hashes are existence evidence only — never compared, never cause false conflicts. Missing registry/schema/table/user is fail-closed (no continue paths).

---

## Test Results (final, disposable PG16+Redis7, Poetry env Python 3.12 + bcrypt 4.0.1)

| Suite | Count | Status |
|---|---|---|
| `test_dc12r1_s1_r4_exact_catalog.py` | 9 | ✅ (composite UNIQUE, OR TRUE, AND FALSE, extra predicate, wrong varchar, wrong FK, reset compatible, reset wrong varchar, transactional rollback) |
| `test_dc12r1_s1_r3_migration_contract.py` | 11 | ✅ (1 compatible + 10 malformed variants) |
| `test_dc12r1_s1_r2_strict_mapping.py` | 4 | ✅ |
| `test_dc12r1_s1_r1_corrections.py` | 8 | ✅ (RED→GREEN) |
| `test_dc12r1_s1_retailer_identity.py` | 14 | ✅ |
| `test_dc1g` + `test_dc3b` + auth + route-policy + orders + payments + finance | 76 | ✅ |
| **Backend total** | **122** | **all pass** |
| Frontend Vitest | 9 | ✅ |
| Frontend `pnpm build` | — | ✅ |
| `alembic heads`/`current` | — | single `036`; second upgrade no-op |

## Quality Gates
- `git diff --check`: clean
- ASCII/mojibake scan: CLEAN (all touched files)
- `detect-secrets`: CLEAN
- `pre-commit`: all Passed
- GitNexus `analyze`/`status`: `✅ up-to-date`

## Changed Files (cumulative S1→R4)

**Backend**: `models/{retailer_credentials(new),binding,retailer,invitation,__init__}.py`, `alembic/versions/036_retailer_mvp_identity.py(new)`, `scripts/{bootstrap_tenant_schema,create_wholesaler}.py`, `services/{email_delivery,onboarding_service,retailer_provisioning_service(new),retailer_service,invitation_service}.py`, `repositories/{invitation,binding}_repository.py`, `api/v1/client/{auth(new),dependencies}.py`, `api/v1/{retailers,invitations}.py`, `api/app.py`, `schemas/retailer_credentials.py(new)`, `tests/{test_dc12r1_s1_retailer_identity,test_dc12r1_s1_r1_corrections,test_dc12r1_s1_r2_strict_mapping,test_dc12r1_s1_r3_migration_contract,test_dc12r1_s1_r4_exact_catalog,new}.py`, `tests/{test_dc1g,test_route_authorization_policy}.py`

**Frontend**: `src/pages/retailer/{RetailerSetupCredentialPage,RetailerResetPasswordPage}.tsx(new)`, `src/utils/urlToken.ts(new)`, `src/services/authService.ts`, `src/router/AppRouter.tsx`, `src/tests/RetailerCredentialPages.test.tsx(new)`

**Ledger**: this file.
