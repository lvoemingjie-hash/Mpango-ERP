# U6-H4 Tenant Provisioning First Admin + RBAC Slice

Date: 2026-07-08
Branch: `opencode/u6h4-tenant-provisioning-first-admin-rbac-2026-07-08`
Base: `origin/product-dev-recovered` at `5beccba9eedcbf658c55f8b1beae5d067acaaba2`
Verdict: `STOP_AND_REPORT_CTO`

## Pre-Edit GitNexus Impact

GitNexus index was refreshed on the clean U6-H4 base before impact checks.

- `TenantProvisioningService`: `HIGH`, `22` impacted; affected module was `Tests`. This does not require edits outside `TenantProvisioningService`, tests, or docs.
- `User`: `HIGH`, `43` impacted; affected processes include `bootstrap_tenant`, `create_user_endpoint`, and `onboard_tenant`. U6-H4 does not edit `User` or those flows.
- `Role`: `MEDIUM`, `41` impacted; affected processes include tenant bootstrap scripts.
- `Permission`: `MEDIUM`, `41` impacted; affected processes include tenant bootstrap scripts.
- `bootstrap_tenant_schema.bootstrap`: exact target not found.
- Fallback `bootstrap`: `HIGH`, `27` impacted; affected files include canonical bootstrap and seed scripts. U6-H4 does not edit bootstrap.

No code edits were made before this STOP decision.

## Findings

The task requires `provision_first_admin_rbac(registration_id)` to create the first tenant admin user for an already active/provisioned tenant.

The current provisioning cleanup contract clears `TenantRegistration.password_hash` when tenant provisioning completes. In `TenantProvisioningService._complete_after_bootstrap`, successful activation calls `_clear_registration_credential`, which sets:

- `password_hash = None`
- `password_hash_cleared_at = completed_at`
- credential cleanup reason is recorded as `"provisioned"`

Therefore, for the required precondition `registration.status == active`, the original credential hash is intentionally unavailable.

The tenant `users` table requires `password_hash VARCHAR(255) NOT NULL`, and `models.user.User.password_hash` is non-nullable. Creating an admin user for the owner email without a valid credential hash would require either inventing a credential, storing an unusable placeholder hash, or changing the credential lifecycle. All options are security-sensitive and outside the requested safe slice.

The task explicitly states: if `registration.password_hash` is unavailable, `STOP_AND_REPORT_CTO` and propose a credential setup flow. That condition is met.

## Canonical Permission Source

Canonical MVP/admin permission seed list exists in current code/docs:

- `backend/scripts/create_wholesaler.py` has `permissions_data` documented as the complete permission list covering API-enforced `RequirePermission` checks.
- `backend/scripts/onboard_tenant.py` mirrors the same admin permission list.
- `docs/API_CONTRACT_v0.1.7.md` states active permission codes are seeded from `create_wholesaler.py` and the `admin` role receives all permissions during tenant bootstrap.

No STOP was raised for missing canonical permissions.

## Proposed CTO Decision

Choose one credential setup boundary before U6-H4 implementation continues:

1. Preferred: split first-admin RBAC from password delivery. U6-H4 creates/reconciles the tenant admin user only after a separate one-time credential setup/reset token flow exists. The tenant user can be created when the owner completes that flow, not from the cleaned registration hash.
2. Alternative: move first-admin creation into the same transaction boundary before `_clear_registration_credential` runs, then clear the registration credential only after the tenant user has been created with the existing hash. This changes the U6-H task ordering and should be approved explicitly.
3. Do not create a placeholder or random password. That would violate the no credential delivery/no secret logging constraints and could create an unreachable or insecure admin account.

## Validation Performed

- `git fetch origin`: completed.
- Branch created from `origin/product-dev-recovered` at `5beccba9`.
- `npx gitnexus analyze`: repository indexed successfully on the clean base.
- `npx gitnexus status`: indexed commit `5beccba`, current commit `5beccba`, status up-to-date.
- Pre-edit GitNexus impact checks completed for required targets as recorded above.

No production code or tests were edited because the explicit credential availability STOP condition was reached.
