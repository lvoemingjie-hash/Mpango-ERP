# DC-12R1-MVP-L1-PW1-R4-B4 — Retailer Permission Context Hydration Closure (2026-08-16)

## Base & Branch

- Base: `888683ba23c14b48a102289a29f9b7adf674fdaf` (`origin/product-dev-recovered`)
- Branch: `zcode/dc12r1-mvp-l1-pw1-r4-b4-retailer-permission-context-2026-08-16`
- Risk class: auth/RBAC boundary — HIGH. GitNexus impact/context executed
  BEFORE editing on all four named symbols (retailer_login,
  ClientLoginPage, RetailerLoginUser, RetailerLoginResponse):
  - `RetailerLoginUser` / `RetailerLoginResponse`: 4 direct dependents
    each, 1 process, 1 module affected (schema consumers).
  - `retailer_login` / `ClientLoginPage`: 0 upstream dependents in the
    graph (route/page entry points), grep census confirmed the only
    production consumers are the client auth router and the retail login
    route registration.

## Product contract implemented

1. `POST /api/v1/client/auth/login` now returns the server-derived CURRENT
   effective permission context of the verified tenant-local user
   (`RetailerLoginUser.permissions`).
2. Permissions come ONLY from the user's live roles joined to non-deleted
   permissions rows (single tenant-local query; no other users/roles).
3. `SELECT DISTINCT p.code ... ORDER BY p.code` — deduplicated and stably
   sorted.
4. The frontend no longer hardcodes `permissions: []`;
   `ClientLoginPage` consumes `data.user.permissions` verbatim (with the
   retail-portal type `RetailerLoginUser.permissions: string[]`).
5. JWT issuance and backend `RequirePermission` semantics are unchanged
   (zero edits to token creation or permission dependencies).
6. Missing permissions still fail closed: an empty-permission user can
   log in (role membership is the login gate) and is then denied 403 by
   permission-gated routes; the frontend `RetailerPermissionRoute`
   redirect for permission-empty users is verified unchanged.

## Files (exact scope)

| File | Change |
|---|---|
| `backend/api/v1/client/auth.py` | step 9b: effective-permission query + `RetailerLoginUser(permissions=...)` |
| `backend/schemas/retailer_credentials.py` | `RetailerLoginUser.permissions: list[str]` (required, documented) |
| `backend/tests/test_pw1r4b4_retailer_permission_context.py` | NEW suite (5 tests, real stack) |
| `frontend/src/types/auth.ts` | `RetailerLoginUser.permissions: string[]` |
| `frontend/src/pages/client/ClientLoginPage.tsx` | `permissions: data.user.permissions` (hardcode removed) |
| `frontend/src/tests/Pw1R4B4RetailerPermissionContext.test.tsx` | NEW suite (5 tests, real App router) |
| `ai-ledger/product-ai/2026-08-16_dc12r1_mvp_l1_pw1_r4_b4_retailer_permission_context.md` | this ledger |

## Backend suite (5 tests, real PG16 + real JwtAuthStrategy app)

- formal bootstrap tenant (S1 RBAC reconcile seeds retailer_operator with
  exactly the six client:* permissions) + synthetic public registry rows
  (wholesalers / tenant_registrations / retailers / bindings, documented
  as synthetic; schema derived as `t_<wholesaler id hex>` per login step 6)
1. exact six permissions, sorted, in the login 200 body
2. no foreign leak: admin-role codes (e.g. payments:confirm_declaration)
   and any non-client: code never appear
3. soft-deleted permission granted to the live role is excluded
   (precondition first proves the live grant IS returned)
4. empty-permission user: login 200 with `permissions: []`, then the same
   contextual JWT gets 403 on `GET /api/v1/client/orders` (fail closed)
5. neutral 401 body carries no permission data

## Frontend suite (5 tests, real AppRouter + real guards)

- T1 real-shaped RetailerLoginResponse writes the exact six permissions
  into the auth store
- T2 no permission data in URL; no console error carries permission strings
- T3 real AppRouter admits a permission-holding user into
  `/client/orders/:id/declare` and `/client/orders/:id/print`
- T4 permission-EMPTY user is redirected off both routes (fail closed,
  no auto-fill)
- T5 `updateTokens` (the refresh-path store action) preserves the user
  permission context

## Mutations (all RED, restored GREEN)

- MUT-B1 backend: effective_permissions emptied -> 3 backend tests RED
  (six-permission, leak, soft-deleted)
- MUT-F1 frontend: `permissions` removed from the response fixture -> T1 RED
- MUT-F2 frontend: `permissions: []` hardcode restored in
  ClientLoginPage -> T1 RED

## Gates

- Backend focused: natural 5/5; reversed node order 5/5.
- Frontend focused: natural 5/5; fixed-seed shuffle 5/5.
- `pnpm vitest run` (full): **328 passed / 0 failed**.
- `pnpm build`: success (pre-existing chunk-size warning only).
- Two independent fresh PG16+Redis7 full backend suites: see below.
- Hygiene: py_compile, git diff --check, scoped pre-commit (incl.
  detect-secrets with baseline; test-password literals carry
  `# pragma: allowlist secret` per repo idiom), strict UTF-8 — clean.
- GitNexus re-analyze + status up-to-date after the change.

## Full-suite gate results

- Gate A (fresh PG16@25440 + Redis7@26387): **3645 passed / 48 skipped /
  15 xfailed / 0 failed / 0 errors**.
- Gate B (fresh PG16@25441 + Redis7@26388): **3645 passed / 48 skipped /
  15 xfailed / 0 failed / 0 errors**.
- Reconciliation: skip-location sets identical (48=48), xfail node-ID sets
  identical (15=15); 3645 = 3640 (R4-A-R2/R3 baseline on this lineage) +
  5 new B4 nodes.
