# DC-12R1-MVP-L1-PW1-R3-R2-V1 — Kilo Final Bounded Review (2026-08-15)

## Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R3_R2_V1_KILO_FINAL_REVIEW**

This is **source / test-authenticity / committed-evidence approval only**. It is **not** browser acceptance or merge approval.

---

## 1. Proof gate

### 1.1 Exact candidate, remote equality, lineage
- Detached exact-SHA worktree created at `11148b6e064005a7d719562b7d06f833ae4847bf`.
- Remote source branch `origin/zcode/dc12r1-mvp-l1-pw1-r3-rate-limit-context-closure-2026-08-15` resolves to the **same SHA**.
- Direct lineage verified:
  - `11148b6` parent = `1181ffe`
  - `1181ffe` parent = `07013d2`
  - `07013d2` parent = `9f5d677`
- `9f5d677` is an ancestor of `11148b6`.

### 1.2 Exact aggregate scope
`git diff --name-only 9f5d677..11148b6` is **exactly 28 files**:
- **4 product**
  - `backend/api/app.py`
  - `backend/api/middleware/auth.py`
  - `backend/api/middleware/rate_limiting.py`
  - `backend/core/rate_limiter.py`
- **1 test**
  - `backend/tests/test_pw1r3_rate_limit_context.py`
- **2 docs**
  - `ai-ledger/product-ai/2026-08-15_dc12r1_mvp_l1_pw1_r3_rate_limit_context_closure.md`
  - `docs/ai-reports/review/2026-08-15_PW1_R2_R2_V2_INVALID_EVIDENCE_RECONCILIATION.md`
- **21 evidence**
  - all files under `pw1r3-evidence/` in this candidate

No extra files.

### 1.3 Exact R2-only delta
`git diff --name-only 1181ffe..11148b6` is **exactly 2 files**:
- `ai-ledger/product-ai/2026-08-15_dc12r1_mvp_l1_pw1_r3_rate_limit_context_closure.md`
- `pw1r3-evidence/r1_skip_xfail_comparison.txt`

All **4 product blobs + 1 test blob** are byte-identical between `1181ffe` and `11148b6`.

### 1.4 Forbidden categories
No backend-migration drift beyond the 4 intended backend files. Specifically, there are **no** changes to:
- dependencies / lockfiles
- deployment files
- browser harness
- unrelated product areas

Worktree stayed clean throughout.

---

## 2. Source review

### 2.1 Starlette execution order is correct
`backend/api/app.py` documents and implements the required Starlette ordering rule:
- `app.add_middleware(RateLimitingMiddleware)`
- then `app.add_middleware(AuthenticationMiddleware, ...)`

Because Starlette makes the **last-added middleware outermost**, `AuthenticationMiddleware` runs **before** `RateLimitingMiddleware` on request ingress. That is the correct order for rate limiting to observe verified auth context.

The integration canary `test_middleware_order_auth_runs_before_rate_limiting()` asserts:
- `AuthenticationMiddleware` index `<` `RateLimitingMiddleware` in `app.user_middleware`

This matches actual Starlette execution semantics, not just comments.

### 2.2 Context derives only from verified JWT state
`backend/api/middleware/auth.py` sets request-scoped context only after server-side verification:
- `auth_ctx = await self._strategy.authenticate(request)`
- `authenticate()` in `backend/auth/strategies/jwt.py` extracts bearer token and calls `resolve_auth_context(raw_token)`
- `resolve_auth_context()` in `backend/api/context/auth.py` calls `decode_token(raw_token)` and raises 401 on invalid/expired tokens
- `resolve_tenant_context(auth_ctx.token)` then derives tenant scope from the verified token and real tenant-scoped DB lookup

Downstream rate-limit context is attached only from these verified objects:
- `request.state.tenant_id = str(tenant_ctx.tenant_id)`
- `request.state.user_id = str(auth_ctx.token.user_id)`

No client header, self-declared claim, or ad-hoc request field is trusted for contextual keying.

### 2.3 Anonymous / identity-only / rejected-auth all stay on IP bucket
`backend/core/rate_limiter.py::_get_rate_limit_key()` enforces:
- contextual only when **both** `tenant_id` and `user_id` are present
- otherwise fallback to `rate_limit:ip:{client_ip}` with limit `100`

Important closure properties:
- **identity-only JWT** (`tenant_ctx is None`) never sets tenant-scoped state → IP bucket
- **invalid / malformed / expired Authorization** never reaches inner limiter with contextual state; `AuthenticationMiddleware` calls `enforce_rate_limit_on_auth_rejection()` which applies the **same IP bucket**
- defensive partial-context guard: if `tenant_id` exists but `user_id` is absent, code explicitly drops to anonymous bucket rather than trusting partial state

Therefore invalid Authorization does **not** bypass limiting.

### 2.4 Health/metrics exemptions and exact 429 headers remain intact
`backend/api/middleware/rate_limiting.py` defines a single shared exemption source:
- `RATE_LIMIT_EXEMPT_PATHS = {"/health", "/healthz", "/health/live", "/health/ready", "/readyz", "/metrics"}`

That same set is used by:
- outer `RateLimitingMiddleware`
- auth-rejection limiter hook

Exact 429 headers are preserved by `_apply_rate_limit_headers()`:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`
- `Retry-After` (429 only)
- `X-Request-ID` preserved when available

---

## 3. Integration-test authenticity

`backend/tests/test_pw1r3_rate_limit_context.py` is a real middleware-stack integration test, not a synthetic state injection.

### 3.1 What it genuinely exercises
- real `FastAPI()` app + real `configure_app(...)`
- production `JwtAuthStrategy`
- real `httpx.ASGITransport`
- real Redis-backed `RateLimiter`
- real PostgreSQL tenant lookup for contextual tokens

### 3.2 No false-green patterns found
Verified absent:
- **no X-Forwarded-For / X-Real-IP spoofing** for test logic
  - anonymous bucket uses fresh ASGI transport peer IPs, not forged proxy headers
- **no conditional status softening**
  - assertions use exact status / exact headers / exact boundaries
- **no `sleep()` / window-alignment timing tricks**
- **no `FLUSHDB`**
- **no wildcard `SCAN/delete` cleanup**
- **no retry-until-green loops**
- **no injected `request.state` fake contextual session**

The only `mock.patch` is for `auth.factory.get_auth_strategy` to force the real JWT strategy into the app wiring; it does not mock the middleware under test.

### 3.3 The seven tests are substantive
The file contains 7 real integration assertions:
1. middleware order canary
2. anonymous request uses IP bucket limit 100
3. contextual JWT uses tenant/user bucket limit 1000
4. contextual burst stays admitted past IP limit
5. identity-only JWT stays on IP limit 100
6. 101st anonymous hits 429 while contextual request remains admitted
7. health endpoint exemption

---

## 4. Mutation authenticity

### 4.1 R1 mutation RED
Committed RED evidence is genuine:
- `R1_MUT_A_wrong_order_RED.txt` → **4 failed / 3 passed**
  - wrong middleware order breaks contextual bucket behavior
- `R1_MUT_B_no_user_id_RED.txt` → **3 failed / 4 passed**
  - dropping verified `user_id` collapses contextual traffic back to IP bucket

### 4.2 R3 mutation RED
Committed RED evidence is genuine:
- `R3_MUT_A_wrong_order_RED.txt` → **6 failed / 1 passed**
- `R3_MUT_B_no_user_id_RED.txt` → **5 failed / 2 passed**

These failures directly match the claimed safety properties, so the suite is not source-grep-only green.

---

## 5. V2 correction review

The superseded V2 branch’s own `results.json` / `reconciliation.json` still claim the invalid story (`162 / 80 / 82`, all 82 due to 429).

I parsed the **raw committed V2 `junit.xml` directly** from the superseded branch:
- **162 collected**
- **104 passed**
- **58 failed**
- among failures:
  - **47** mention `429`
  - **11** do **not** mention `429`

This exactly matches the correction document:
`docs/ai-reports/review/2026-08-15_PW1_R2_R2_V2_INVALID_EVIDENCE_RECONCILIATION.md`

That correction is accurate, and the old V2 report is indeed invalid evidence.

---

## 6. Round C / D verification

From the committed backend logs:
- `r1_gateC_full_backend.txt` tail: `3630 passed / 48 skipped / 15 xfailed / 0 failed / 0 errors`
- `r1_gateD_full_backend.txt` tail: `3630 passed / 48 skipped / 15 xfailed / 0 failed / 0 errors`

From the committed canonical comparison file:
- `r1_skip_xfail_comparison.txt`
  - round C xfail node IDs = **15**
  - round D xfail node IDs = **15**
  - **exact set difference empty**
  - skip entries are described only as **canonical skip locations** (`file:line`), not asserted as JUnit node IDs

This closes the C/D evidence consistency requirement.

---

## 7. Runtime / quality checks

### 7.1 Focused natural/reverse rerun
I probed host support:
- PostgreSQL reachable on `127.0.0.1:5432`
- Redis reachable on `127.0.0.1:6379`
- but no clean local backend pytest environment was present in the candidate worktree, and the live backend listener at `127.0.0.1:8000` was not stably reusable at review time

Therefore I **did not claim a local rerun PASS** for the focused natural/reverse backend tests.

Committed focused evidence present:
- `r1_natural_order.txt`
- `r1_natural_order_second.txt`
- `r1_reverse_order.txt`

I relied on those committed artifacts only.

### 7.2 diff-check
- `git diff --check 9f5d677..11148b6 -- <product+test subset>` = **clean**
- whole-span `git diff --check` flags only copied evidence-output whitespace in `pw1r3-evidence/*.txt` plus one blank EOF line in `frontend_full_vitest.txt`
- no product/test code whitespace defects

### 7.3 detect-secrets
Scoped `detect-secrets` scan on the changed files was **clean**.

### 7.4 UTF-8 / mojibake
Changed-file scan found **0** replacement-character (`U+FFFD`) hits.

### 7.5 GitNexus
- `npx gitnexus analyze` completed successfully
- `npx gitnexus status` reports:
  - indexed commit = `11148b6`
  - current commit = `11148b6`
  - status = **up-to-date**

---

## 8. Conclusion

This bounded review closes:
- exact candidate identity and lineage
- exact 28-file aggregate scope
- exact 2-file R2 delta with product/test byte-identity to R1
- correct Starlette auth-before-rate-limit execution order
- verified-JWT-only contextual key derivation
- no invalid-auth bypass of rate limiting
- preserved exemptions and exact 429 headers
- authentic seven-test integration harness
- correct V2 evidence correction (`162 / 104 / 58`, `47/11`)
- closed Round C/D xfail/skip evidence
- clean scoped secret scan, UTF-8, and GitNexus status

**Final verdict: `PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R3_R2_V1_KILO_FINAL_REVIEW`**
