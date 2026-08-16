# DC-12R1-MVP-L1-PW1-R4-B4-V1 — Kilo Final Bounded Source Review

## Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R4_B4_V1_KILO_FINAL_REVIEW**

This is a bounded source/evidence review only. It is not a 162-node browser rerun, not an R4-C execution, and not a merge approval.

---

## 1. Proof gate

Reviewed in an isolated detached worktree at the exact candidate SHA.

Verified:
- baseline/product: `888683ba23c14b48a102289a29f9b7adf674fdaf`
- candidate: `9f24d969e30a2c8ed3ae9e0eddebae170089292a`
- branch `origin/zcode/dc12r1-mvp-l1-pw1-r4-b4-retailer-permission-context-2026-08-16` resolves to the same full SHA
- direct parent of the candidate is exactly the baseline SHA `888683ba...`
- candidate worktree stayed clean throughout review

### Exact delta scope
`git diff --name-status 888683ba..9f24d96` contains exactly **7 files**:
1. `ai-ledger/product-ai/2026-08-16_dc12r1_mvp_l1_pw1_r4_b4_retailer_permission_context.md`
2. `backend/api/v1/client/auth.py`
3. `backend/schemas/retailer_credentials.py`
4. `backend/tests/test_pw1r4b4_retailer_permission_context.py`
5. `frontend/src/pages/client/ClientLoginPage.tsx`
6. `frontend/src/tests/Pw1R4B4RetailerPermissionContext.test.tsx`
7. `frontend/src/types/auth.ts`

I found **no** changes under:
- migrations / alembic
- JWT issuance files
- backend `RequirePermission` implementation
- dependencies / lockfiles
- deployment files
- the B3 browser harness (`pw1r4b/`)

---

## 2. Backend permission authenticity

### 2.1 Retailer login permissions come only from the current tenant schema
The new permission query is in `backend/api/v1/client/auth.py` step **9b** and is tenant-local:

```sql
SELECT DISTINCT p.code
FROM "{tenant_schema}".permissions p
JOIN "{tenant_schema}".role_permissions rp ON rp.permission_id = p.id
JOIN "{tenant_schema}".roles r ON r.id = rp.role_id
JOIN "{tenant_schema}".user_roles ur ON ur.role_id = r.id
WHERE ur.user_id = :user_id
  AND p.is_deleted IS FALSE
  AND r.is_deleted IS FALSE
ORDER BY p.code
```

This proves:
- only the current `tenant_schema` is consulted
- only permissions for the already-authenticated **tenant-local** `user_id` are considered
- no cross-tenant permission source is available to the query at all

### 2.2 User identity is already verified before the permission query runs
Before step 9b, `retailer_login()` already verifies:
1. active tenant registration + derived schema contract
2. tenant-local `users` row (`is_deleted IS FALSE`, `is_active = true`)
3. password correctness
4. active binding in `public.wholesaler_retailer_bindings`
5. presence of the `retailer_operator` role membership
6. non-deleted retailer row

So the permission list is derived only after the request has already been narrowed to a verified tenant-local principal.

### 2.3 JOIN scope and soft-delete filters match the real model structure
I verified the actual RBAC models:
- `User`, `Role`, `Permission` inherit `BaseModel`, which includes `is_deleted`
- `user_roles` and `role_permissions` are plain association tables without `is_deleted`

Therefore the query’s filters are structurally correct:
- `p.is_deleted IS FALSE` is real and necessary
- `r.is_deleted IS FALSE` is real and necessary
- no `is_deleted` filter is missing on the join tables, because they do not have such a column

### 2.4 DISTINCT + ORDER BY provide genuine deduplication and stable order
The query uses:
- `SELECT DISTINCT p.code`
- `ORDER BY p.code`

This is a real dedup + deterministic-order guarantee. It is not merely cosmetic.

### 2.5 No foreign or deleted permissions can leak
The query cannot mix in:
- other tenants (fixed `tenant_schema`)
- other users (`ur.user_id = :user_id`)
- soft-deleted permissions (`p.is_deleted IS FALSE`)
- soft-deleted roles (`r.is_deleted IS FALSE`)

The backend test suite also explicitly covers:
- foreign admin-only permission codes do not appear
- soft-deleted permissions disappear after deletion

### 2.6 Empty-permission user succeeds at login but fails closed later
`test_empty_permission_user_login_ok_but_route_denied()` proves:
- a user who still holds the `retailer_operator` role but whose role grants are removed logs in successfully
- the response contains `permissions: []`
- the same contextual JWT then gets a **403** on a permission-gated route

This is the required fail-closed behavior.

### 2.7 `RetailerLoginUser.permissions` is required in the response schema
`backend/schemas/retailer_credentials.py` now defines:

```py
class RetailerLoginUser(BaseModel):
    ...
    permissions: list[str]
```

No default, no optional field. It is a required response field.

### 2.8 JWT issuance and backend `RequirePermission` semantics remain unchanged
No changes were made to:
- `backend/core/security.py`
- backend `RequirePermission` implementation (`backend/api/middleware/rbac.py`)

The candidate scope excludes both.

So B4 changes the **login response permission hydration**, not JWT claims or backend guard semantics.

---

## 3. Front-end context authenticity

### 3.1 `ClientLoginPage` uses only `data.user.permissions`
In `frontend/src/pages/client/ClientLoginPage.tsx`, the new session user object is built with:

```ts
permissions: data.user.permissions,
```

I found **no** retained fallback such as:
- `permissions: []` hardcoding
- role-name inference
- static six-permission defaults

### 3.2 Auth store persistence / refresh behavior is correct
`frontend/src/stores/authStore.ts` was **not** changed in this candidate, but its existing behavior remains crucial and correct:
- `persist` stores the full `user` object, which includes `permissions`
- `updateTokens(...)` only updates `accessToken` and `refreshToken`
- it does **not** rewrite `user`

Therefore a refresh preserves the existing server-derived `user.permissions`.

The real front-end test T5 explicitly asserts this behavior.

### 3.3 Real AppRouter / RetailerPermissionRoute execution is used
The front-end suite is not a source-grep or custom-guard fake. It uses:
- the real `<App />`
- the real `AppRouter`
- the real `RetailerPermissionRoute`
- the real `can(user, permission)` helper from `frontend/src/utils/permissions.ts`

So route admission is exercised through the actual shipping route tree.

### 3.4 Declaration route mounts only with the server-derived permission
T3 proves a permission-holding user can really mount:
- `/client/orders/:id/declare`
- `/client/orders/:id/print`

T4 proves an empty-permission user is redirected to `/client` and the child route does not mount.

Print-route routing also remains tied to the real permission mapping configured in `AppRouter.tsx`:
- order print → `CLIENT_PERMISSIONS.ORDERS_READ`
- declaration print / receipt → `CLIENT_PERMISSIONS.PAYMENTS_READ`
- statement print → `CLIENT_PERMISSIONS.FINANCE_READ`

This is real-route execution, not a local refactor or grep-only claim.

---

## 4. Causality and counterexamples

### 4.1 Clearing server permissions would RED the real contract
By source inspection, emptying `effective_permissions` on the backend would break:
- backend six-permission test
- backend no-foreign-leak / exact permission contract checks
- frontend T1 exact-store hydration check

This is consistent with the ledger’s stated backend mutation `MUT-B1` → RED.

### 4.2 Deleting the `permissions` response field fails closed
Because `RetailerLoginUser.permissions` is required in the backend schema and the front-end consumes `data.user.permissions` verbatim, removing the field would not silently green:
- backend response validation would fail or
- frontend T1 would fail

This is consistent with the ledger’s stated frontend mutation `MUT-F1` → T1 RED.

### 4.3 Restoring front-end `permissions: []` must RED
If `ClientLoginPage` were changed back to `permissions: []`, T1 would fail immediately because the stored user would not match the six server-derived codes.

This is consistent with the ledger’s stated frontend mutation `MUT-F2` → T1 RED.

### 4.4 No mock-only pass / weak assertion / fixed result pattern found
I specifically checked for:
- `test.skip` / `.only`
- xfail-style masking
- retries > 0
- weak or vacuous assertions

Findings:
- no `skip` / `.only` / xfail-style source usage in the candidate scope
- `playwright.config.js` from the earlier browser harness is irrelevant here and unchanged
- front-end B4 tests use concrete route/path assertions and store equality assertions
- backend B4 tests use real HTTP responses through `httpx.ASGITransport` and a real app stack

I did not find a fixed-result or conditional-pass pattern in the B4 source delta.

---

## 5. Evidence accounting

### What I independently executed locally
In the detached candidate worktree, after a clean `pnpm install --frozen-lockfile` in `frontend/`, I independently ran:
- focused front-end natural order → **5/5 passed**
- focused front-end fixed-seed shuffle → **5/5 passed**
- full front-end `vitest` → **328/328 passed**
- front-end `build` → **exit 0**

These are real local passes on the candidate source.

### What I could not execute locally
The candidate worktree does **not** contain a ready backend pytest environment:
- global Python in this host lacks `pytest`
- no local backend virtualenv was present in the candidate worktree

Therefore I did **not** claim local PASS for:
- backend focused 5/5 natural
- backend focused 5/5 reversed
- backend A/B full-suite `3645 passed / 48 skipped / 15 xfailed`

I explicitly disclose those as **not locally executed**.

### What I could still verify from committed source/ledger
From the candidate source and ledger:
- backend focused suite contains exactly **5** test nodes (`test_pw1r4b4_retailer_permission_context.py`)
- the ledger consistently states:
  - backend focused: natural 5/5; reversed 5/5
  - frontend focused: natural 5/5; fixed-seed shuffle 5/5
  - frontend full: 328/328
  - build: success
  - backend Gate A/B: each 3645 passed / 48 skipped / 15 xfailed
  - skip/xfail sets identical

I found **no contradiction** in the committed source/ledger regarding those counts, but only the front-end gates above were independently re-executed on this host.

### Accounting gap
Review findings accounting gap = **0**.

---

## 6. Quality gates

Independently run locally in the detached candidate worktree:
- `python -m py_compile` on changed backend Python files → **clean**
- `git diff --check 888683ba..9f24d96` → **clean**
- scoped `detect-secrets` on the changed files → **clean**
- UTF-8 / mojibake scan on changed files → **0** replacement-character hits
- `npx gitnexus analyze` + `npx gitnexus status` → indexed commit `9f24d96`, current commit `9f24d96`, **up-to-date**

---

## Final conclusion

This bounded source review closes the required contract:
- SHA / branch / parent integrity verified
- delta is exactly the approved 7 files
- retailer login permissions are sourced only from the verified tenant-local user in the current tenant schema
- soft-delete / role / dedup / stable-order semantics are correct against the real model structure
- `RetailerLoginUser.permissions` is required
- JWT issuance and backend `RequirePermission` behavior are unchanged
- front-end consumes only `data.user.permissions`, persists it, preserves it across refresh, and exercises the real AppRouter / RetailerPermissionRoute
- the failure counterexamples are real and would RED under the described mutations
- no source-level skip/xfail/retry greenwash found
- front-end focused/full/build gates passed locally; backend runtime gates were **not** locally runnable and are explicitly disclosed as such

**Final verdict: `PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R4_B4_V1_KILO_FINAL_REVIEW`**
