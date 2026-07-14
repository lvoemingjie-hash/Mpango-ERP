# DC-11C Final Adversarial Delivery Review

Target SHA: `cb1b1fffc63ed19e320701043eed38b8f2bea0c7`
Report branch: `reports/dc11c-final-red-team-2026-07-14`
Review date: 2026-07-14
Verdict: `STOP_BEFORE_DELIVERY`

## Scope And Method

I reviewed the exact target source and ran sanitized no-mutation runtime probes against the deployed HTTP origin. Runtime probes used only unauthenticated, invalid-bearer, wrong-platform-secret, malformed-ID, query-string-token, and stale-browser-auth cases. I did not create tenants, orders, payments, exports, setup/reset tokens, or permanent records.

Direct host log access was not available: SSH returned `Permission denied (publickey,password)`. Log review is therefore limited to public-response scanning and source review of logging paths, not a completed production log scan.

## P0 Findings

None found in the completed source review and public no-mutation runtime probes.

## P1 Findings

### P1-1: Partial Payment Replay Creates Duplicate Financial Side Effects

Endpoint: `POST /api/v1/orders/{order_id}/pay`

Evidence:

- `backend/api/v1/orders.py:388` defines the canonical structured order payment endpoint.
- `backend/api/v1/orders.py:451-458` computes remaining balance from prior cash/transfer payments.
- `backend/api/v1/orders.py:460-471` rejects only payments greater than the current remaining balance.
- `backend/api/v1/orders.py:561-568` creates a new payment row and passes `idempotency_key=None`.
- `backend/api/v1/orders.py:584-599` applies the outstanding-balance delta for each accepted request.
- `backend/repositories/payment_repository.py:195-257` unconditionally inserts the payment row passed by the caller.
- `backend/services/payment_service.py:84-107` has idempotency checks, but this canonical order-payment path does not call that service method.
- `frontend/src/services/orderService.ts:40-45` posts payment data without an idempotency header.
- `frontend/src/components/ui/PaymentRecordModal.tsx:68-74` submits method, amount, transaction reference, and notes without replay protection.

Reproduction without production mutation:

1. Use a disposable confirmed or partially paid order with remaining balance greater than the replay amount, for example remaining `100.00`.
2. Send `POST /api/v1/orders/{order_id}/pay` with body `{"method":"cash","amount":"25.00"}`.
3. Replay the exact same request while remaining balance is still at least `25.00`.
4. The second request is not deduplicated. The code computes a new remaining balance, inserts another payment row with `idempotency_key=None`, and applies another outstanding-balance delta.

Impact:

A client retry, double click, proxy replay, or network ambiguity can double-record partial cash/transfer payments and double-apply balance changes while the request is semantically the same payment attempt. This can understate receivables, create duplicate payment rows, and move an order toward `paid` earlier than the real settlement. Transfer `transaction_id` is also not used as an idempotency key in this path.

Release impact: P1. Blocks delivery.

## P2 Findings

None found.

## P3 Findings

### P3-1: Stale Browser Auth State Produces Console Errors

Routes: `/`, `/orders`, `/orders/new`, `/finance`, `/payments`, `/client`, `/platform`, `/platform/tenants`, `/platform/ops/health`, `/platform/controlled-execution`

Runtime evidence:

- Unauthenticated sweep covered all 45 routes declared in `frontend/src/router/AppRouter.tsx`; all loaded or redirected without console/page errors.
- Stale persisted auth using the documented `mpango-auth` key produced console errors on all 11 stale-auth routes tested.
- Focused stale dashboard rerun: `status=200`, `final=/`, `page_errors=0`, `body_len=132`, `console_errors=7`; console errors were 401 failed-resource messages.

Source evidence:

- `frontend/src/stores/authStore.ts:51-58` persists access token, refresh token, user, and tenant code under `mpango-auth`.
- `frontend/src/services/api.ts:28-33` attaches the persisted bearer token to every API request.
- `frontend/src/services/api.ts:110-171` attempts refresh on 401, logs out on refresh failure, and redirects to `/login`.

Impact:

No SPA crash was reproduced in the focused rerun, but the explicit “no console error” criterion is not met under stale persisted auth. This is a frontend hardening/quality issue, not a data isolation or financial-integrity defect.

### P3-2: Platform Guard Uses Non-Strict Identity Semantics

Endpoints: `/api/v1/platform/**` routes wired through `require_platform_operator`

Evidence:

- `backend/core/security.py:65-69` defines `TokenPayload.is_identity_only` as `tenant_id is None or tenant_schema is None`.
- `backend/api/v1/platform/p10/guard.py:61-82` accepts `token.is_super_admin and token.is_identity_only`.
- `backend/api/middleware/rbac.py:78-137` contains a stricter `RequirePlatformAdmin` helper that explicitly documents why OR semantics are unsafe for platform boundaries, but the P10 platform guard does not use it.
- `backend/auth/strategies/jwt.py:27-35` also skips tenant-context resolution when `is_identity_only` is true.

Reproduction:

This was not reproduced against production because the normal token issuers create either identity tokens with neither tenant claim or contextual tokens with both tenant claims (`backend/core/security.py:76-159`). However, any signed super-admin token with only one tenant claim missing would be treated as identity-only by the P10 guard.

Impact:

A malformed signed partial-context super-admin token could cross the intended platform-only boundary. Current issuers reduce exploitability, so this is classified as hardening rather than a P1 auth bypass.

### P3-3: Validation Error Serialization Can Reflect Submitted Input

Endpoints observed: `POST /api/v1/auth/login`, `POST /api/v1/auth/forgot-password`

Runtime evidence:

The sanitized HTTP probe saw controlled `422 VALIDATION_ERROR` responses for malformed email input, with an email-pattern flag in the public response body. No account-existence signal or internal identifier was observed.

Source evidence:

- `backend/core/error_codes.py:214-231` serializes `exc.errors()` into response details.
- `backend/core/error_codes.py:218-223` logs the encoded validation errors.

Impact:

Submitted PII can be reflected in public validation responses and logs when validation fails before neutral auth lifecycle handlers run. This is not an account-enumeration finding, but it is a privacy/log hygiene issue.

### P3-4: Export Error Logging Includes Raw Exception Text

Endpoints: `GET /api/v1/exports/{job_id}`, `GET /api/v1/exports/{job_id}/download`

Evidence:

- `backend/api/v1/exports.py:73-88` parses malformed export IDs before DB lookup and returns controlled `INVALID_EXPORT_ID`.
- `backend/api/v1/exports.py:261-268` returns 404 for wrong-tenant status checks.
- `backend/api/v1/exports.py:354-360` returns 404 for wrong-tenant downloads.
- `backend/api/v1/exports.py:295-306` logs `str(e)` on status failures while returning a generic public error.
- `backend/api/v1/exports.py:399-410` logs `str(e)` on download failures while returning a generic public error.

Runtime evidence:

Malformed, encoded, missing, unauthenticated, and invalid-bearer export status/download probes returned controlled 401/400-style responses with no public traceback, DB URL, JWT, or driver-error flags.

Impact:

Public responses are sanitized, but logs may capture raw exception strings if unexpected export errors occur. Since direct production log access was unavailable, this remains source-level log hygiene risk.

## Attack Area Results

Payment integrity: Release-blocking replay defect found in the canonical order payment path. Source also shows direct `POST /api/v1/payments` is disabled at `backend/api/v1/payments.py:83-97`, but the replacement path lacks idempotency. Unauthenticated invalid-method/invalid-amount runtime probes returned 401 and caused no mutation.

Export isolation: Source validates malformed IDs before DB lookup and checks job tenant ownership before status/download responses. Runtime probes for malformed, encoded, missing, unauthenticated, and invalid-bearer export requests produced controlled responses with no public internal exception leak.

Platform UUID/auth: Public platform health/info remained unauthenticated by design. Protected tenant platform routes returned 401 without credentials and 403 with wrong platform secret. The partial-context platform guard issue is P3.

Credential lifecycle: Source review found neutral duplicate/live signup behavior, body-only setup/reset token consumption, query-string setup/reset rejection, invalid/replayed token neutrality, and mixed-case login normalization at `backend/api/v1/auth.py:255`. Runtime query-string setup/reset probes returned controlled 401. Signup was not runtime-mutated.

Tenant isolation: Source review confirms tenant schema/session comes from JWT-derived request state (`backend/api/dependencies.py:33-45`) and tenant ORM filtering requires context (`backend/db/tenant_filter.py:128-199`). No authenticated cross-tenant runtime probes were run because no disposable production credential was provided; this is not classified as PASS.

Finance receivables: Source review found tenant scoping through `wholesaler_id=token.tenant_id` at `backend/api/v1/finance.py:374-408`, order filters on `Order.wholesaler_id` at `backend/services/receivables_service.py:253-258`, malformed retailer/status filters returning empty results at `backend/services/receivables_service.py:260-272`, and public binding lookup scoped by wholesaler at `backend/services/receivables_service.py:358-378`. Unauthenticated malformed enum runtime probes returned controlled 401.

Frontend: All 45 unauthenticated routes in `AppRouter` loaded or redirected without console/page errors. Stale persisted auth produced P3 console errors. Mobile Money submits the canonical transfer value in source: `frontend/src/components/ui/PaymentRecordModal.tsx:16-20` labels transfer as “Bank Transfer / Mobile Money”, and `frontend/src/components/ui/PaymentRecordModal.tsx:68-74` submits that `method` value.

Logs/security: Public HTTP response scan covered 40 malformed/unauthenticated cases and found no 500s, tracebacks, DB URLs, JWTs, UUID driver errors, `TenantContextMissing`, `UndefinedTable`, or serialization errors. Direct production log scan was not completed due SSH denial.

## Final Verdict

`STOP_BEFORE_DELIVERY`

Do not create or move a release tag for this SHA. The P1 payment replay/idempotency defect must be fixed and re-reviewed before delivery.
