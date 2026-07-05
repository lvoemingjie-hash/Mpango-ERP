# U6-A Tenant Onboarding and Email Auth Contract Gate

Date: 2026-07-05
Branch: `opencode/u6a-tenant-onboarding-email-auth-contract-2026-07-05`
Base: `origin/product-dev-recovered` at `eac7642e merge: S6-I2 full backend pytest green gate`
Verdict: `PASS_FOR_CTO_U6A_REVIEW`

## Scope

U6-A is design and contract only. It defines the MVP self-service tenant onboarding and email-auth contract for U6-B through U6-H.

No production runtime code, backend route, service, model, migration, dependency, frontend implementation, email provider integration, deployment, or environment change is included in U6-A.

## 1. Current State Audit

### Wholesaler Registry-Only Creation

Current public tenant registry CRUD lives in `backend/api/v1/wholesalers.py` and is mounted at `/api/v1/wholesalers` by `backend/api/app.py`.

Observed contract:

- `POST /api/v1/wholesalers` requires `RequirePermission("wholesalers:write")`.
- It creates only a `public.wholesalers` row through `crud_wholesaler`.
- The route message explicitly says tenant schema, login, admin user, RBAC, inventory, orders, and finance workspace are not provisioned.
- `models/wholesaler.py` derives the tenant schema from UUID as `t_<uuid_without_dashes>` and carries platform lifecycle snapshot fields such as `status`, `provisioned_at`, and suspension metadata.

Why it is not self-service onboarding:

- A visitor cannot call it because it is protected by existing RBAC.
- It does not create the schema or first user.
- It does not verify email ownership.
- It creates no login path for the new customer.
- It depends on an already provisioned tenant/admin to grant `wholesalers:write`.

### Seed and Onboard Scripts

Current provisioning history lives mainly in:

- `backend/scripts/onboard_tenant.py`
- `backend/scripts/create_wholesaler.py`
- `backend/scripts/bootstrap_tenant_schema.py`
- `backend/scripts/seed_test_tenant.py`
- `backend/scripts/seed_demo_data.py`

Observed contract:

- `onboard_tenant.py` is an operator/CLI flow that asks for business name, code, admin email, admin password, and optional demo data.
- It attempts to create the public wholesaler, tenant schema, tenant tables, admin role, permissions, and admin user.
- `bootstrap_tenant_schema.py` is the current canonical raw-DDL bootstrap/reconcile path for tenant schemas. It creates tenant tables including users, roles, permissions, SKUs, inventory, orders, payments, ledger, reporting, import runs, and U4 intake tables, then reconciles known drift.
- `seed_test_tenant.py` is test/dev focused and idempotently seeds the gold-standard test tenant plus admin RBAC. It is explicitly guarded for local/test/dev use.
- Some scripts print operational summaries, including admin identity information. Self-service production onboarding must not display or log credentials.

Why it is not self-service onboarding:

- It requires CLI or operator execution.
- It can accept or print admin credentials in a way that is not suitable for customer-facing production onboarding.
- It does not persist a customer-facing registration lifecycle before tenant activation.
- It does not send or verify email before provisioning.
- It does not provide retryable, audited, API-driven provisioning semantics.

### Admin Bootstrap History

Current admin bootstrap is script-centered:

- `onboard_tenant.py` and `seed_test_tenant.py` both define the admin permission set and assign it to an `admin` role.
- S6-E and S6-I2 aligned stale tests to the current permission registry, including intake permissions and SKU import.
- `models/user.py` stores users, roles, and permissions inside tenant schemas, not in a public global user table.

Why it is not self-service onboarding:

- First-admin creation is coupled to scripts, not to an audited registration state machine.
- There is no pending user that becomes active only after email verification.
- There is no protection against provisioning a tenant for an unverified address.
- There is no first-owner contract distinct from platform super-admin.

### Auth Login and Select-Tenant Flow

Current auth flow lives in `backend/api/v1/auth.py`, `backend/schemas/auth.py`, `backend/crud/user.py`, and `backend/core/security.py`.

Observed contract:

- `POST /api/v1/auth/login` accepts email and password only.
- Login scans active tenant schemas via `find_user_across_tenants` and returns an identity JWT plus `available_tenants`.
- `POST /api/v1/auth/select-tenant` upgrades an identity/context token to a contextual JWT after verifying that the user exists and is active in the selected tenant schema.
- Password hashing uses bcrypt via `passlib` and truncates input to 72 bytes for bcrypt compatibility.
- There are no public signup, verify-email, resend-verification, forgot-password, or reset-password endpoints today.

Why it is not self-service onboarding:

- Auth assumes users already exist in tenant schemas.
- New users cannot register a company from the public website.
- Unverified email state does not exist.
- Password reset flow does not exist.
- Tenant activation is not tied to an email-verified registration.

### Platform Boundary

Current platform routes are mounted under `/api/v1/platform/*` and protected by `RequirePlatformAdmin`.

Observed contract:

- `RequirePlatformAdmin` accepts only strict identity-only JWTs with `super_admin` role.
- Contextual tenant admins are explicitly rejected from platform endpoints.
- `public.platform_tenants` tracks operational provisioning status, but today it is an operational journal for platform actions, not a self-service registration table.
- `public.platform_audit_logs` is append-only and queryable only by platform admins.

U6 must preserve this boundary: tenant owners/admins are not platform super-admins and must not access `/api/v1/platform/*`.

## 2. Target User Journey

Customer-facing MVP flow:

1. Visitor opens `/signup`.
2. Visitor enters company name, country, email, password, optional phone, and optional business type.
3. Backend validates the request at the public boundary and creates a pending tenant registration in `pending_email_verification` status.
4. Backend creates a single-use email verification token, stores only a hash of the token, and sends a verification link.
5. UI shows a neutral success page: "Check your email to verify your account." It does not reveal whether an email was already registered beyond acceptable signup UX.
6. User opens the verification link and lands on `/verify-email`.
7. Frontend submits the opaque token to `POST /api/v1/auth/verify-email`.
8. Backend atomically marks the token used and moves the registration to `email_verified`.
9. Backend starts tenant provisioning and transitions status to `provisioning`.
10. Provisioning creates the public tenant registry record, tenant schema, current tenant tables, first owner/admin user, RBAC baseline, and required empty setup workspace/state.
11. On success, backend marks registration and tenant lifecycle `active`.
12. User logs in through existing `POST /api/v1/auth/login`, selects the tenant if needed, receives contextual JWT, and lands in `/setup`.
13. `/setup` shows a guided checklist for company profile, products, customers, pricing, inventory, and first order. No demo business data appears unless explicitly requested in a later product flow.

User-visible recovery paths:

- If verification email is missed, `/signup` success and `/verify-email` expired/invalid states offer resend.
- If the verification token expired, resend creates a new token and invalidates previous unused tokens.
- If provisioning fails, login remains blocked and status shows a friendly "We are finishing setup" or support state while audit logs retain internal error details.
- If the registration is cancelled or expired, the user can restart signup.

## 3. Domain Model Proposal

### `public.tenant_registrations`

Purpose: durable customer-facing registration state before and during tenant provisioning.

Proposed fields:

| Field | Type | Required | Contract |
| --- | --- | --- | --- |
| `id` | UUID | yes | Primary key. |
| `company_name` | varchar(255) | yes | Customer-entered company display name. |
| `tenant_code` | varchar(32) | no until provisioning | Generated from company name or user-proposed, normalized, unique once reserved. |
| `country` | varchar(2) or varchar(64) | yes | MVP can store ISO country code; frontend displays country names. |
| `business_type` | varchar(64) | no | Optional customer segment, e.g. wholesale, distribution, retail-wholesale. |
| `phone` | varchar(32) | no | Optional contact phone. |
| `owner_email` | varchar(255) | yes | Normalized lowercase email for first owner/admin. |
| `owner_full_name` | text | no | Optional; can default to company owner/admin label if absent. |
| `password_hash` | varchar(255) | yes | Hashed at signup. Never store plaintext. |
| `status` | varchar(40) | yes | State machine below. |
| `email_verified_at` | timestamptz | no | Set once after verification. |
| `provisioning_started_at` | timestamptz | no | Set when provisioning begins. |
| `provisioning_completed_at` | timestamptz | no | Set when activation succeeds. |
| `failed_at` | timestamptz | no | Set when provisioning fails. |
| `failure_code` | varchar(64) | no | Machine-readable internal failure category. |
| `failure_message` | text | no | Internal sanitized diagnostic; not returned publicly in full. |
| `wholesaler_id` | UUID | no | Linked after public registry row creation. |
| `tenant_schema` | varchar(64) | no | Linked after tenant id exists; derived from wholesaler UUID. |
| `idempotency_key_hash` | varchar(128) | no | Hash of signup idempotency key if provided. |
| `request_fingerprint_hash` | varchar(128) | no | Hash of normalized signup payload for safe replay detection. |
| `expires_at` | timestamptz | yes | Pending registrations expire if unverified. |
| `created_at` | timestamptz | yes | Server-side timestamp. |
| `updated_at` | timestamptz | yes | Server-side timestamp. |

Suggested uniqueness:

- Unique active/pending `owner_email` for statuses not in `cancelled`, `expired`, or terminal stale states.
- Unique `tenant_code` once reserved.
- Unique `wholesaler_id` when not null.
- Unique `idempotency_key_hash` when not null.

### `public.email_verification_tokens`

Purpose: single-use email verification for tenant registrations.

Proposed fields:

| Field | Type | Required | Contract |
| --- | --- | --- | --- |
| `id` | UUID | yes | Primary key. |
| `registration_id` | UUID | yes | FK to `tenant_registrations.id`. |
| `token_hash` | varchar(128) | yes | HMAC-SHA256 or SHA-256 over high-entropy token plus server-side pepper. |
| `purpose` | varchar(32) | yes | `signup_email_verification`; future compatible with reset flows if separate table is not used. |
| `expires_at` | timestamptz | yes | MVP default: 24 hours for signup verification. |
| `used_at` | timestamptz | no | Set exactly once. |
| `revoked_at` | timestamptz | no | Set when resend invalidates older unused tokens. |
| `sent_to_email` | varchar(255) | yes | Normalized email at send time for audit. |
| `send_count` | integer | yes | Tracks resend pressure per registration. |
| `last_sent_at` | timestamptz | yes | Rate limit support. |
| `created_at` | timestamptz | yes | Server-side timestamp. |

### Password Reset Tokens

Password reset may use a separate `public.password_reset_tokens` table for clarity, or a generic auth token table with `purpose = password_reset`.

MVP recommendation: separate table in U6-C/U6-B planning if it keeps constraints clearer.

Required fields mirror verification tokens:

- `id`
- `user_email_hash` or registration/user locator
- `tenant_id` when known
- `token_hash`
- `expires_at`
- `used_at`
- `revoked_at`
- `created_at`

Password reset must not require selecting a tenant before email delivery. If the same email exists in multiple active tenants, reset email should lead to a tenant selection step or reset all tenant copies only after explicit safe design. MVP recommendation: tenant selection after token validation, before password update, unless the user has exactly one tenant.

### Optional Invitation Table

Current `public.invitations` is retailer-focused. U6-F should introduce an employee invitation contract instead of overloading retailer invitations.

Proposed `public.tenant_user_invitations` fields:

- `id`
- `tenant_id` / `wholesaler_id`
- `tenant_schema`
- `email`
- `role_id` or role code requested by inviter
- `token_hash`
- `status`: `pending`, `accepted`, `expired`, `revoked`
- `invited_by_user_id`
- `expires_at`
- `accepted_at`
- `created_at`
- `updated_at`

Employee invitations are out of U6-A implementation and should be U6-F.

### Owner/Admin User Creation Contract

Provisioning creates the first tenant user from `tenant_registrations.owner_email` and `password_hash`.

Contract:

- The first user is active only after email verification and successful provisioning.
- The first user is not created in a tenant schema before email verification.
- The first user receives tenant role `owner` or `admin` per RBAC decision below.
- The first user is not granted platform `super_admin`.
- The first user cannot access platform routes.
- No default weak password is generated or displayed.

### Provisioning Status State Machine

Required states:

- `pending_email_verification`: registration accepted, token issued, no tenant schema created.
- `email_verified`: valid token consumed, ready to provision.
- `provisioning`: backend is creating registry, schema, tables, user, RBAC, and setup baseline.
- `active`: provisioning completed and login is allowed.
- `failed`: provisioning failed; login blocked; retry may be allowed by internal job/service.
- `cancelled`: customer or support cancelled before activation.
- `expired`: email was not verified before `expires_at`.

Allowed transitions:

- `pending_email_verification` to `email_verified`
- `pending_email_verification` to `expired`
- `pending_email_verification` to `cancelled`
- `email_verified` to `provisioning`
- `provisioning` to `active`
- `provisioning` to `failed`
- `failed` to `provisioning` only through an idempotent retry path
- `failed` to `cancelled`

Forbidden transitions:

- Any terminal stale state directly to `active`.
- `pending_email_verification` directly to `active`.
- Any state to `provisioning` without verified email.

### Idempotency and Retry Behavior

Signup:

- Accept optional `Idempotency-Key` header.
- Store only a hash of the key.
- Same key plus same normalized payload returns the same registration status.
- Same key plus different payload returns `409 IDEMPOTENCY_CONFLICT`.
- Without an idempotency key, duplicate pending signup for the same normalized email returns a neutral response that instructs the user to check email or resend, without leaking account status unnecessarily.

Verification:

- Verification is idempotent for an already-used valid token if the registration reached `active`; return success/status without re-running provisioning.
- Reuse of a token after it was used for a different state should not reactivate anything; return a generic invalid/expired response.

Provisioning retry:

- Provisioning steps must be idempotent and checkpointed.
- Retry from `failed` must reuse the same `registration_id`, `wholesaler_id` if already created, and tenant schema if already derived.
- Retry must not create duplicate users, roles, permissions, or registry records.
- Retry must fail closed if it detects inconsistent partial state that cannot be reconciled safely.

## 4. Security Contract

### Email Verification Token Handling

- Generate at least 128 bits of entropy, preferably 256 bits.
- Store only `token_hash`, never the raw token.
- Hash with HMAC-SHA256 using a server-side pepper or equivalent keyed construction; plain SHA-256 is acceptable only if the token entropy is high and pepper strategy is documented in U6-B.
- Token TTL: 24 hours for signup verification unless CTO sets a different product rule.
- Token is single-use; `used_at` is set atomically in the same transaction that validates status and expiry.
- Resend invalidates older unused tokens for the same registration.
- Token values must never be logged, returned after creation, or stored in audit metadata.
- Verification endpoint must accept the token only in request body, not in path logs. Frontend may receive it from query string and immediately submit it to the API.

### Password Hashing Rules

- Continue using the current bcrypt/passlib policy unless CTO approves a hash migration.
- Enforce minimum length 8 at API boundary; recommended product minimum is 10 or 12 for U6-B discussion.
- Preserve bcrypt 72-byte compatibility handling consistently with `core/security.py`.
- Never store plaintext passwords.
- Never print, log, email, or display passwords.
- Do not create default passwords.

### Rate Limiting

Required rate limits:

- Signup by IP and normalized email.
- Resend verification by IP and registration/email.
- Verify-email by IP and token hash prefix or request fingerprint.
- Forgot-password by IP and normalized email.
- Reset-password by IP and token hash prefix or request fingerprint.

MVP recommended limits:

- Signup: 5 attempts per IP per 15 minutes and 3 attempts per email per hour.
- Resend verification: 3 sends per registration per hour, 6 per day.
- Verify-email: 10 attempts per IP per 15 minutes.
- Forgot-password: 5 attempts per email per hour, neutral response always.
- Reset-password: 10 attempts per IP per 15 minutes.

Exact numbers may be tuned in U6-C, but tests must prove limits exist.

### Tenant Creation Timing

Default rule: no tenant schema creation before email verification.

Justification:

- Prevents unauthenticated attackers from creating schemas and consuming DB resources.
- Prevents unverified identities from claiming tenant namespaces.
- Keeps stale registrations cheap to expire.

Exception requires CTO approval and explicit abuse controls. No exception is approved in U6-A.

### Login and Account Activation

- Pending registrations cannot log in.
- `POST /api/v1/auth/login` must continue to find only active tenant users.
- No tenant user row is created before email verification.
- If a user row exists from a partially failed provisioning attempt, it must remain inactive or inaccessible until registration reaches `active`.
- `select-tenant` must reject users whose tenant provisioning is not active.

### No Privilege Escalation

- Public signup creates only a tenant-scoped owner/admin role in the newly created tenant.
- Public signup never creates `super_admin` and never writes platform admin privileges.
- Public signup must not accept requested permissions or requested role names from the client.
- First-admin RBAC is server-defined from the current permission registry.
- Signup cannot create or modify existing tenants.

### Enumeration and Error Disclosure

- Signup may say "If this email can be used, we will send verification instructions" when duplicate/ambiguous cases occur.
- Login keeps current generic `INVALID_CREDENTIALS` semantics.
- Forgot-password always returns a neutral success response, whether or not the email exists.
- Resend verification can return a neutral success for both known pending registrations and non-actionable states.
- Verification may show user-friendly invalid/expired states because the user already holds a token, but internal reasons must remain coarse.
- API error bodies use machine-readable codes and safe messages only.

### Fail-Closed Partial Provisioning

- Any unreconciled partial provisioning moves registration to `failed` and blocks login.
- Failed provisioning does not expose contextual tokens.
- If public registry row exists but schema creation failed, platform status must not be `active`.
- If schema exists but RBAC/user creation failed, platform status must not be `active`.
- If owner user exists but role assignment failed, owner login must be blocked or tenant selection must fail.
- Retry must validate every prerequisite before advancing state.

### Required Audit Events

Audit events must avoid raw tokens and credentials.

Required events:

- `tenant_registration.created`
- `tenant_registration.email_verification_sent`
- `tenant_registration.email_verified`
- `tenant_registration.verification_resend_requested`
- `tenant_registration.expired`
- `tenant_registration.cancelled`
- `tenant_provisioning.started`
- `tenant_provisioning.registry_created`
- `tenant_provisioning.schema_created`
- `tenant_provisioning.bootstrap_completed`
- `tenant_provisioning.owner_created`
- `tenant_provisioning.rbac_seeded`
- `tenant_provisioning.activated`
- `tenant_provisioning.failed`
- `tenant_provisioning.retry_started`
- `password_reset.requested`
- `password_reset.completed`

Destination:

- Customer-facing registration/provisioning events should be persisted in the new registration/provisioning model and, where platform-wide audit is needed, mirrored to `public.platform_audit_logs` through internal appender service semantics.

## 5. RBAC Contract

### First User Role

Decision for U6-A contract: first user is the tenant owner/admin.

MVP role name recommendation: `admin` for compatibility with current bootstrap scripts and tests.

Future optional refinement: introduce `owner` as a distinct role after a registry migration and permission review. If `owner` is added later, it should receive admin-level permissions plus ownership-only controls such as billing or tenant deletion, if those exist.

### Permissions Granted

The first `admin` role receives the current U1/S6-E permission registry used by `onboard_tenant.py`, `seed_test_tenant.py`, and S6-I2 tests:

- `users:read`
- `users:create`
- `users:update`
- `users:deactivate`
- `wholesalers:read`
- `wholesalers:write`
- `roles:read`
- `roles:create`
- `roles:update`
- `roles:delete`
- `roles:assign`
- `orders:read`
- `orders:create`
- `orders:update`
- `orders:confirm`
- `orders:ship`
- `orders:cancel`
- `skus:read`
- `skus:create`
- `skus:update`
- `skus:import`
- `intake:read`
- `intake:create`
- `intake:update`
- `intake:approve`
- `intake:export`
- `intake:import_to_erp`
- `inventory:read`
- `inventory:write`
- `inventory:update`
- `payments:read`
- `payments:create`
- `retailers:read`
- `invitations:create`
- `pricing:read`
- `pricing:write`
- `finance:read`
- `dashboards:read`
- `reports:read`
- `reports:analyze`
- `exports:create`
- `system:admin`
- `metrics:admin`

Alignment requirements:

- U6-B/U6-D must source this list from one canonical permission registry or test-gated equivalent.
- S6-E drift tests must remain green after any new permission or role changes.
- Signup must not accept arbitrary client-requested permissions.

### Platform Super-Admin Separation

- Platform `super_admin` remains separate from tenant owner/admin.
- Public signup must never assign `super_admin`.
- Tenant `admin` may receive tenant permission `system:admin`, but that does not satisfy `RequirePlatformAdmin`.
- `/api/v1/platform/*` remains protected by strict identity-only `super_admin`; tenant contextual tokens must be rejected.
- Tests must prove a newly onboarded tenant admin receives 403 from `/api/v1/platform/*`.

## 6. Provisioning Contract

Activation must create exactly the following, idempotently:

1. `public.wholesalers` tenant registry row.
2. `public.platform_tenants` lifecycle row or equivalent provisioning journal row, linked to the wholesaler.
3. Tenant schema named by `Wholesaler.get_tenant_schema()`.
4. All current tenant tables and reconciliation artifacts at the current Alembic/bootstrap contract, using `bootstrap_tenant_schema.bootstrap()` or a CTO-approved replacement.
5. Tenant-scoped `users` row for first owner/admin, using the verified email and stored password hash.
6. Tenant-scoped `roles` row for `admin`.
7. Tenant-scoped `permissions` rows for the current U1/S6-E registry.
8. Tenant-scoped `role_permissions` rows assigning all baseline permissions to `admin`.
9. Tenant-scoped `user_roles` row assigning the first owner/admin to `admin`.
10. Empty setup checklist/workspace state for `/setup`, if U6-B/U6-D introduces a table for it.
11. Audit/provisioning events for every state transition.

Activation must not create:

- Demo retailers, SKUs, inventory, orders, payments, or ledger data unless the customer explicitly requests demo data in a later product flow.
- Default or weak passwords.
- OPS-visible or UI-visible password output.
- Platform `super_admin` users.
- Cross-tenant bindings unrelated to the new tenant.

Activation success criteria:

- `tenant_registrations.status = active`.
- `public.wholesalers.status = active` and `provisioned_at` is set.
- `public.platform_tenants.provisioning_status` reflects active/complete semantics or a new U6 status map approved by CTO.
- Owner/admin can log in through existing auth and enter the tenant.
- Owner/admin has expected tenant permissions.
- Owner/admin cannot access platform routes.

## 7. Email Provider Strategy

U6-A does not integrate a provider. U6-C should add an email sender interface and choose one runtime provider plus a dev sink.

### SMTP

Pros:

- Standard protocol and widely available.
- Works with many local/dev tools.
- Avoids provider-specific API dependency.

Cons:

- Deliverability and bounce handling vary by host.
- Credential and TLS configuration is easy to misconfigure.
- Provider-specific throttling and diagnostics are weaker through generic SMTP.

Fit: acceptable fallback, not the best MVP production choice unless an existing managed mailbox is already approved.

### Resend

Pros:

- Developer-friendly API.
- Simple transactional-email integration.
- Good fit for product-led SaaS verification/reset emails.

Cons:

- Adds a new vendor dependency.
- Region/compliance and deliverability must be checked for Mpango deployment markets.

Fit: recommended MVP provider if vendor/account approval is straightforward.

### SendGrid

Pros:

- Mature transactional email platform.
- Good dashboards, templates, and deliverability tooling.
- Broad ecosystem support.

Cons:

- Setup and account verification can be heavier.
- Some accounts require additional deliverability/domain configuration before reliable sending.

Fit: solid production option, especially if already approved by operations.

### AWS SES

Pros:

- Cost-effective and reliable at scale.
- Strong IAM integration for AWS-hosted stacks.
- Good production deliverability when domains are configured.

Cons:

- More setup friction, sandbox exit, DKIM/SPF/domain verification.
- Less ergonomic for early MVP than Resend/SendGrid.

Fit: good long-term production option if AWS is already part of infrastructure.

### Tencent Cloud Email

Pros:

- Regional fit if production stays on Tencent/China infrastructure.
- Potentially better operational alignment with existing Tencent VPS constraints.

Cons:

- Team familiarity and API ergonomics need validation.
- Deliverability for non-China recipients needs testing.

Fit: evaluate for deployment-region alignment before final provider selection.

### Console/Dev Email Sink

Pros:

- No external calls in local tests.
- Prevents accidental real emails from CI/dev.
- Easy to assert token links in tests without exposing raw token in logs.

Cons:

- Does not test provider deliverability.

Fit: required fallback for local tests and CI.

MVP recommendation:

- Define an `EmailSender` interface in U6-C with provider-neutral payloads.
- Use console/dev sink in local and test environments.
- Use Resend for MVP production if approved; otherwise SendGrid or AWS SES depending on existing operations preference.
- Keep SMTP as fallback adapter, not the first-choice production integration.

## 8. Frontend Contract

No frontend implementation in U6-A. U6-E should implement the following pages and states.

### `/signup`

Fields:

- Company name
- Country
- Email
- Password
- Optional phone
- Optional business type

States:

- Empty form
- Inline validation errors
- Submitting
- Success: check email
- Rate-limited: wait and retry
- Recoverable duplicate/neutral response: check email or resend
- Unexpected error: friendly support copy

Copy requirements:

- Clear English.
- Browser-translation friendly.
- Avoid idioms and slang.
- Example: "Create your company account" and "We sent a verification link to your email address."

### `/verify-email`

Inputs:

- Token from URL query handled by frontend and submitted to API.

States:

- Verifying
- Verified: continue to login or setup
- Expired: request a new verification email
- Invalid: request a new verification email or contact support
- Provisioning: account is being prepared
- Provisioning failed: friendly support state, no internal details

### `/login`

Requirements:

- Keep existing email and password login.
- If identity login returns one tenant, frontend may auto-select only if product approves; otherwise show tenant picker.
- If login fails, show generic invalid credentials.
- If account is not active, show email verification/setup status without leaking sensitive internals.

### `/forgot-password`

Fields:

- Email

States:

- Empty form
- Submitting
- Neutral success: if an account can be reset, instructions were sent
- Rate-limited

### `/reset-password`

Fields:

- New password
- Confirm new password

States:

- Token validating
- Valid token
- Expired token
- Invalid token
- Password validation errors
- Success path to login

### `/setup`

Guided checklist for first-run activation:

- Confirm company profile
- Add or import products
- Add customers/retailers
- Configure prices
- Set opening inventory
- Create first order

No demo data should appear by default. Setup may include optional "Load sample data" only in a future explicit flow.

## 9. API Contract

All proposed endpoints are contracts only in U6-A. Do not implement until U6-C/U6-D.

Common response envelope:

- Success: `success`, `data`, `message`, `timestamp`.
- Error: structured machine-readable code under the existing error response style.
- Timestamps are ISO 8601.
- Response fields use camelCase in external API where existing frontend expects it, or match current schema conventions if backend consistency requires snake_case. U6-C must choose one and test it.

### `POST /api/v1/auth/signup`

Purpose: create pending tenant registration and send verification email.

Auth: public, rate-limited.

Headers:

| Header | Required | Contract |
| --- | --- | --- |
| `Idempotency-Key` | no | Recommended for client retries. Store only hash. |

Request fields:

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `companyName` | string | yes | 2-255 chars, trimmed. |
| `country` | string | yes | ISO country code preferred. |
| `email` | email string | yes | Normalize lowercase. |
| `password` | string | yes | Minimum 8, product may raise to 10/12. |
| `phone` | string | no | Max 32, normalized if possible. |
| `businessType` | string | no | Enum or safe string max 64. |

Success response: `202 Accepted`.

Data fields:

| Field | Type | Contract |
| --- | --- | --- |
| `registrationId` | UUID or null | May be null in neutral duplicate responses. |
| `status` | string | Usually `pending_email_verification`. |
| `emailVerificationRequired` | boolean | Always true for new signup. |
| `resendAvailableAt` | datetime or null | Set when rate limiting resend. |

Error codes:

- `VALIDATION_ERROR` with 422.
- `SIGNUP_RATE_LIMITED` with 429.
- `IDEMPOTENCY_CONFLICT` with 409.
- `SIGNUP_UNAVAILABLE` with 503 if signup is disabled.

Enumeration rule: duplicate or existing-account cases should prefer neutral `202` unless a product-approved UX requires explicit conflict.

### `POST /api/v1/auth/verify-email`

Purpose: consume verification token and start or report provisioning.

Auth: public, rate-limited.

Request fields:

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `token` | string | yes | Opaque token from email link. |

Success response: `200 OK`.

Data fields:

| Field | Type | Contract |
| --- | --- | --- |
| `registrationId` | UUID | Registration id. |
| `status` | string | `email_verified`, `provisioning`, or `active`. |
| `loginAvailable` | boolean | True only when active. |
| `nextPath` | string | `/login`, `/setup`, or verification recovery path. |

Error codes:

- `VERIFICATION_TOKEN_INVALID` with 400.
- `VERIFICATION_TOKEN_EXPIRED` with 410.
- `VERIFICATION_TOKEN_USED` with 409 only if not safely idempotent.
- `PROVISIONING_FAILED` with 409 or 202 status payload, depending on async design.
- `VERIFY_RATE_LIMITED` with 429.

### `POST /api/v1/auth/resend-verification`

Purpose: send a fresh verification email for a pending registration.

Auth: public, rate-limited.

Request fields:

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `email` | email string | yes | Normalize lowercase. |

Success response: `202 Accepted` with neutral message.

Data fields:

- `resendAvailableAt`
- `status` as neutral public status, e.g. `email_if_pending`

Error codes:

- `VALIDATION_ERROR` with 422.
- `RESEND_RATE_LIMITED` with 429.

Enumeration rule: do not reveal whether the email belongs to an active account, pending registration, expired registration, or no account.

### `POST /api/v1/auth/forgot-password`

Purpose: initiate password reset.

Auth: public, rate-limited.

Request fields:

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `email` | email string | yes | Normalize lowercase. |

Success response: `202 Accepted` with neutral message.

Data fields:

- `resetEmailSentIfEligible`: boolean, always true from UX perspective.

Error codes:

- `VALIDATION_ERROR` with 422.
- `PASSWORD_RESET_RATE_LIMITED` with 429.

### `POST /api/v1/auth/reset-password`

Purpose: consume reset token and update password.

Auth: public token, rate-limited.

Request fields:

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `token` | string | yes | Opaque reset token. |
| `newPassword` | string | yes | Same password policy as signup. |

Success response: `200 OK`.

Data fields:

- `passwordReset`: true
- `nextPath`: `/login`

Error codes:

- `RESET_TOKEN_INVALID` with 400.
- `RESET_TOKEN_EXPIRED` with 410.
- `RESET_TOKEN_USED` with 409 only if not idempotent.
- `PASSWORD_POLICY_VIOLATION` with 422.
- `PASSWORD_RESET_RATE_LIMITED` with 429.

### `GET /api/v1/onboarding/status`

Purpose: report onboarding/provisioning status for a pending registration or active contextual tenant.

Auth options for U6-C decision:

- Public with signed one-time status token linked to registration.
- Identity JWT after login.
- Contextual JWT after activation.

MVP recommendation:

- Accept `registrationId` plus short-lived status token for pre-login states.
- Accept contextual JWT for active tenant setup checklist states.

Query fields:

| Field | Type | Required | Contract |
| --- | --- | --- | --- |
| `registrationId` | UUID | pre-login only | Registration to check. |
| `statusToken` | string | pre-login only | Short-lived status token. |

Success response: `200 OK`.

Data fields:

| Field | Type | Contract |
| --- | --- | --- |
| `status` | string | Registration/provisioning status. |
| `emailVerified` | boolean | True after verification. |
| `loginAvailable` | boolean | True only when active. |
| `setupChecklist` | array | Empty or checklist summary after activation. |
| `supportReference` | string or null | Present for failed state. |

Error codes:

- `ONBOARDING_STATUS_INVALID` with 400/404 neutralized as needed.
- `ONBOARDING_STATUS_EXPIRED` with 410.
- `ONBOARDING_STATUS_FORBIDDEN` with 403.

## 10. Test and Harness Plan

### Unit Tests

- Signup request validation.
- Email normalization.
- Tenant code generation and collision handling.
- Registration state transitions.
- Token hashing and verification helpers.
- Password policy validation.
- Error code mapping.

### DB Migration Tests

- New public registration/token tables exist with expected columns, indexes, constraints, and FK behavior.
- No tenant tables are created by registration migration.
- Token hash uniqueness and partial indexes behave as intended.
- State enum/check constraints allow only approved states.
- Alembic upgrade head succeeds on a fresh DB.
- Alembic downgrade policy is explicit if supported.

### Bootstrap and Provisioning Tests

- Verified registration provisions `public.wholesalers` row.
- Tenant schema name matches `Wholesaler.get_tenant_schema()`.
- `bootstrap_tenant_schema.bootstrap()` creates all current tenant tables.
- Admin role and permissions match U1/S6-E registry exactly.
- First user is active only after activation.
- Empty setup state exists if introduced.
- No demo data is created by default.

### Idempotency Tests

- Signup same idempotency key and same payload returns same registration.
- Signup same idempotency key and different payload returns conflict.
- Verify-email duplicate safe call does not duplicate provisioning.
- Provisioning retry after partial failure does not duplicate wholesaler, schema, user, role, or permissions.
- Resend invalidates previous unused token.

### Email Token Tests

- Raw token is never stored.
- Token hash validates only correct token.
- Expired token is rejected.
- Used token is rejected or safely idempotent depending on final design.
- Revoked token is rejected.
- Token does not appear in logs or audit metadata.

### RBAC Tests

- First owner/admin has all expected tenant permissions.
- First owner/admin can access normal tenant setup endpoints.
- First owner/admin cannot access `/api/v1/platform/*`.
- Public signup cannot request role or permissions.
- S6-E permission drift gate remains green.

### API Tests

- `POST /api/v1/auth/signup` success, validation, rate limit, idempotency, neutral duplicate behavior.
- `POST /api/v1/auth/verify-email` success, invalid, expired, used, provisioning-failed behavior.
- `POST /api/v1/auth/resend-verification` neutral success and rate limit.
- `POST /api/v1/auth/forgot-password` neutral success and rate limit.
- `POST /api/v1/auth/reset-password` success and token failure cases.
- `GET /api/v1/onboarding/status` pre-login and active-user states.
- Existing `login` and `select-tenant` still pass after activation.

### Browser Smoke

- Signup happy path with dev email sink.
- Verify email link happy path.
- Expired token recovery path.
- Login and select tenant after activation.
- Setup checklist renders on desktop and mobile.
- Friendly errors are visible and translatable.

### Runtime VPS Smoke

- Signup route reachable over HTTPS.
- Email sender health/config check passes without printing credentials.
- Dev/staging sink or approved provider sends verification email.
- Verified customer can log in to newly provisioned tenant.
- Tenant admin receives 403 for platform routes.
- No manual DB intervention required.

### No-Secret Tests

- Logs do not include raw verification/reset tokens.
- Logs do not include passwords.
- API responses do not include password hashes.
- Audit metadata excludes token values and credentials.
- Pre-commit secret detection remains green.

## 11. Sprint Breakdown

### U6-B Schema/Migration Only

- Add public registration and token tables.
- Add indexes, constraints, and state checks.
- Add migration tests only.
- No route implementation.
- CTO approval required before migration starts.

### U6-C Backend Signup and Token Service

- Add signup, verify-email, resend-verification, forgot-password, and reset-password route skeletons.
- Add token generation/hash/consume service.
- Add email sender interface and dev sink.
- Add rate limiting.
- No real provider integration unless explicitly approved.

### U6-D Tenant Provisioning Service

- Implement idempotent provisioning service from verified registration to active tenant.
- Reuse or wrap `bootstrap_tenant_schema.bootstrap()`.
- Create owner/admin and RBAC from canonical registry.
- Add provisioning retries and fail-closed partial-state handling.

### U6-E Frontend Signup/Verify/Reset Pages

- Implement `/signup`, `/verify-email`, `/forgot-password`, `/reset-password`, and `/setup` states.
- Wire to backend contracts.
- Add browser smoke tests.

### U6-F Invite Employee Flow

- Add tenant employee invitation model and API.
- Invite existing or new employees into active tenant.
- Ensure inviter permissions and audit events.

### U6-G Runtime Deploy Smoke

- Deploy U6 stack to staging/runtime target.
- Verify email provider/dev sink behavior.
- Run VPS smoke without manual DB intervention.

### U6-H Customer Onboarding Closeout

- End-to-end customer onboarding acceptance.
- Documentation update.
- CTO signoff on production provider and rollout controls.

## CTO Review Questions

- Should the first tenant role remain `admin` for MVP compatibility, or should U6-B introduce a distinct `owner` role?
- Should MVP password minimum remain 8 for compatibility or increase to 10/12 for public signup?
- Which email provider should be approved for first production integration?
- Should password reset update all tenant copies for the same identity or require tenant selection after token validation?
- Should `public.platform_tenants.provisioning_status` be extended to U6 states or should `tenant_registrations.status` be the source of truth with platform status derived?

## U6-A Validation Results

Completed validation for this docs-only change:

- `git diff --check`: passed.
- ASCII scan on changed file: passed.
- Mojibake scan on changed file: passed.
- Added-line secret-pattern scan on changed file: passed.
- Pre-commit on changed file: passed.
- `npx gitnexus analyze`: repository indexed successfully.
- `npx gitnexus status`: up to date at `eac7642`.

## U6-A Result

`PASS_FOR_CTO_U6A_REVIEW`

This contract is ready for CTO review before any U6-B schema or migration work begins.
