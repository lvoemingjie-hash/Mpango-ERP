# DC-12R1-MVP-L1-J1-R1-V2 Kilo Actual Independent Final Source Review

- **Mode:** Adversarial source review + test-authenticity review
- **Authority:** CTO
- **Date:** 2026-08-20
- **Reviewer:** Kilo (independent — NOT inheriting any Zcode self-review PASS)
- **Verdict:** `STOP_AND_REPORT_CTO_DC12R1_MVP_L1_J1_R1_V2_KILO_INDEPENDENT_REVIEW`

---

## 0. Frozen Inputs (verified, not assumed)

| Item | Value | Verification |
|------|-------|--------------|
| Candidate SHA | `b7fbe1cccb5e3b2dc4b9c6011dab17ad5db81fe7` | `git cat-file -t` = commit ✅ |
| Source branch | `origin/zcode/dc12r1-mvp-l1-j1-r1-wholesaler-signup-closure-2026-08-20` | tip == candidate ✅ |
| Expected parent | `fc8abdf327ae386c938541e847dabd786592af23` | `candidate^` == parent ✅ |
| Protected baseline | `origin/product-dev-recovered` | == `fc8abdf3` ✅ |
| Candidate delta scope | 6 frontend files (exact) | `git diff --name-only` matches exactly ✅ |
| No backend/migration/dependency/lockfile/pricing/barcode/deploy change | — | diff name-only shows only 6 frontend files ✅ |

Local/remote equality for source branch: `zcode/...` (local) == `origin/zcode/...` == `b7fbe1cc` ✅.

The Zcode self-review report (`a3243779…`, branch `reports/dc12r1-mvp-l1-j1-r1-v1-kilo-final-review-2026-08-20`) is treated **only as material under challenge**. Its internal `Reviewer: Kilo` self-label is recorded as an evidence-provenance defect (see Finding F-PROV). Its PASS is **not inherited**.

---

## 1. Proof Gates

- `source branch == candidate`: ✅ (both `b7fbe1cccb5e3b2dc4b9c6011dab17ad5db81fe7`)
- `candidate^ == fc8abdf3`: ✅
- `origin/product-dev-recovered == fc8abdf3`: ✅
- `fc8abdf3` is the direct parent of candidate: ✅
- Candidate delta is **exactly** the 6 files:
  1. `frontend/src/pages/auth/LoginPage.tsx`
  2. `frontend/src/pages/auth/SignupPage.tsx`
  3. `frontend/src/router/AppRouter.tsx`
  4. `frontend/src/services/authService.ts`
  5. `frontend/src/tests/SignupClosure.test.tsx`
  6. `frontend/src/types/auth.ts`

No backend, migration, dependency, lockfile, pricing, barcode, or deploy changes present.

---

## 2. Three Mandated Adversarial Points

### A. First password is an invalid secret (collected then discarded) — STOP

**Trace (signup password → final usable credential):**

1. `SignupPage.tsx:89-96` builds payload including `password` and sends it via `authService.signup(payload, key)` → `POST /auth/signup`.
2. `backend/services/onboarding_service.py:298` validates the password (`validate_signup_password`), and **line 325** stores it: `TenantRegistration(password_hash=hash_password(request.password))`. The first password is hashed and persisted.
3. After email verification, `complete_email_verified_onboarding` → `provision_wholesaler_and_schema` → `_complete_after_bootstrap` calls `_clear_registration_credential` (`backend/services/tenant_provisioning_service.py:362-367`):
   ```python
   setattr(registration, "password_" "hash", None)
   setattr(registration, "password_" "hash_cleared_at", completed_at)
   setattr(registration, "password_" "hash_cleanup_reason", "provisioned")
   ```
   → the first password is **nulled at provisioning completion**.
4. The owner/administrator user is created later in `OwnerCredentialSetupService.consume_setup_token` (`owner_credential_service.py:142-175`): it computes `password_hash = hash_password(password)` where `password` is the **second** password typed into the email setup-credential form.
5. `_ensure_owner_user` (`owner_credential_service.py:250-292`) sets the owner user's `password_hash` from that **second** password only. The first password hash is never assigned to any `users` row.

**Facts established by source:**
- The registration password is cleared when provisioning completes ✅ (and never used for any user row).
- The tenant admin's final `password_hash` comes **solely** from the second (email-setup) password ✅.
- The user's **first** typed password cannot log in anywhere — `find_user_across_tenants` checks the user row's `password_hash` (second password); the first password hash is nulled and orphaned ✅.
- The signup page asks the user to **create a password** (`SignupPage.tsx:237-257`) and the accepted-state copy tells them to **"set up your password"** via the emailed link (`SignupPage.tsx:134`). This is a misleading "set a password now, then set another password by email" experience ✅.

No source or runtime evidence was found that the first password has a real, necessary, customer-understandable purpose. Per the verdict rule, "首次密码被收集但最终丢弃" is an explicit STOP trigger and may not be downgraded as "inherited from an old contract."

**Severity:** P0 · **Blocking:** YES · **Finding:** F-A

---

### B. Zero-tenant login branch is unreachable against the real backend — mock-only impossible-state false-green — STOP

**Real backend `/auth/login` (`backend/api/v1/auth.py:232-311`):**
```python
verified_user_id, matches = await find_user_across_tenants(db, normalized_email, request.password)
if verified_user_id is None or len(matches) == 0:
    raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS", ...})
...
available_tenants = [TenantInfo(...) for m in matches]
return IdentityLoginResponse(data=IdentityTokenData(available_tenants=available_tenants))
```
The only place in this file that returns `available_tenants: []` is the **`/auth/refresh`** endpoint (`auth.py:487`), a different route requiring a refresh token. `/auth/login` returns HTTP **401** whenever there are zero verified tenant matches and **never** returns HTTP 200 with an empty tenant list.

**Frontend `LoginPage.tsx:109-113` (Condition D):** when `identityData.available_tenants.length === 0`, it `navigate('/signup')`. This branch is only reachable if `/auth/login` returns HTTP 200 with `available_tenants: []` — which the real backend never produces. A zero-tenant identity therefore receives **401 → "Invalid credentials"** (LoginPage.tsx:122-123) and never reaches `/signup` via this path.

**Test `cold-start branch never references /onboarding/create-tenant` (`SignupClosure.test.tsx:89-115`):** mocks `mockPost` to resolve with `{ data: { success: true, data: { ..., available_tenants: [] } } }` — i.e. it fabricates an **HTTP 200 + `available_tenants: []`** response that the real backend cannot emit. The test then asserts the redirect to `/signup`. This is a **mock-only impossible-state false-green**: it proves nothing about real backend behavior and the "cold-start → signup" routing is dead code relative to the actual backend.

**What J1-R1 actually closes:** the `/signup` public entry itself is real and correctly public (see §3). But the *claimed* closure of a "cold-start branch" is a branch the real backend does not support; the test that "proves" it is a false-green.

Per the verdict rule, "zero-tenant 测试依赖正式 backend 不可能返回的响应" is an explicit STOP trigger.

**Severity:** P0 · **Blocking:** YES · **Finding:** F-B

---

### C. Idempotency-rotation test does not observe the post-success key — false-green / misnamed — STOP

**Test under review:** `rotates the idempotency key only after an accepted success` (`SignupClosure.test.tsx:222-253`).

What it actually asserts:
- A first rejected call uses key `failedKey`.
- After the failure the form stays; a second submit reuses the **same** key (lines 247-249) — correct.
- After a later accepted success, "Check your email" is shown (line 252).

What it does **NOT** assert: that after the accepted success a **new/different** key is in `idempotencyKeyRef` for future submissions. The name claims rotation is observed after success; no assertion ever compares the post-success key to `failedKey` or checks a third submission uses a different key.

**Mandated mutation executed (independent, reproducible):**
- In the candidate worktree I removed the post-success rotation line `idempotencyKeyRef.current = newIdempotencyKey();` from `SignupPage.tsx:103` (transient edit, then restored; candidate commit `b7fbe1cc…` left byte-identical — see §6).
- Ran: `pnpm vitest run src/tests/SignupClosure.test.tsx -t "rotates the idempotency key only after an accepted success"`.
- **Result: still PASSED** (`Test Files 1 passed (1)`, `Tests 1 passed | 14 skipped`). The mutation did **not** turn the test RED.

Conclusion: the test is a **false-green / misnamed** test — it does not verify the rotation it is named for. Per the verdict rule, "成功后 idempotency rotation 测试 mutation 不会 RED" is an explicit STOP trigger. (Note: the actual rotation code at `SignupPage.tsx:103` is correct and present; the defect is the test's lack of an assertion, which leaves the guarantee unverified by the suite.)

**Severity:** P0 · **Blocking:** YES · **Finding:** F-C

---

## 3. Remaining Contract Checks (§五) — SATISFIED

| Check | Result | Evidence |
|-------|--------|----------|
| `/signup` is a real public route, no guard loop | ✅ | `AppRouter.tsx:73` `PublicRoute`, line `80` `{ path: '/signup', element: <SignupPage /> }`; test "guards remain correct" confirms anonymous reach + contextual redirect |
| Discoverable signup link on login page | ✅ | `LoginPage.tsx:216-221` "Create wholesaler account" → `/signup` |
| Payload fields / camelCase aliases match backend Pydantic | ✅ | Frontend `SignupRequest` (`types/auth.ts:43-50`) = `companyName,country,email,password,phone?,businessType?`; backend `SignupRequest` (`schemas/auth_signup.py:11-19`) aliases `companyName`,`businessType`, identical lengths (password 8–128, country 2, phone 32, business_type 64) |
| 202 success copy stays anti-enumeration | ✅ | `SignupPage.tsx:131-134` "If this email can be used…"; backend `NEUTRAL_SIGNUP_MESSAGE` |
| axios/backend message, code, request_id, token never enter UI/URL/storage/log | ✅ | `SignupPage.tsx` failure path neutral only; `storageSetItem` spy never called (test line 178); `LoginPage.tsx:115-130` neutral only |
| Failure keeps same Idempotency-Key | ✅ | test line 185-219 |
| single/multi-tenant & contextual-session behavior not regressed | ✅ | single-tenant test passes; no guard changes beyond J1-R1 scope |
| No skip / xfail / only / conditional pass / retry-green / weakened assertion | ✅ | grep of all 6 changed files: 0 hits for `.skip/.only/xfail/fit/fdescribe` |

---

## 4. Run Gates (executed)

| Gate | Result |
|------|--------|
| SignupClosure focused suite — natural order | ✅ 15/15 PASS (`pnpm vitest run src/tests/SignupClosure.test.tsx`) |
| SignupClosure focused suite — reverse / fixed-seed shuffled | ⚠️ vitest **1.6.1 (pinned)** has no `--shuffle`; substituted by the full-suite run below, which reorders SignupClosure among other suites and exposes cross-suite state. (See F-Q.) |
| Frontend auth/session/router focused regression | ✅ covered by full suite (includes `guards.test.tsx`, `Pw1R2AuthSessionClosure.test.tsx`, `VerifyEmailPage.test.tsx`, `CredentialLifecyclePages.test.tsx`, `SignupClosure.test.tsx`) |
| `pnpm vitest run` (full configured suite) | ✅ **24 files / 354 tests PASS** |
| `pnpm build` | ✅ SUCCESS (pre-existing non-blocking warnings: JS chunk > 500 kB; duplicate `jsdom` dep key) |
| Backend U6 signup/onboarding/owner-credential tests | ❌ **HOST_LIMITATION** — see §6 |

> The full suite is GREEN *including* the false-green tests F-B and F-C. GREEN here does **not** certify the three STOP conditions; it masks them. This is itself the test-authenticity failure the task requires to be surfaced.

---

## 5. Quality Gates

| Gate | Result |
|------|--------|
| `git diff --check` (candidate delta) | ✅ clean (exit 0) |
| Scoped `detect-secrets` (6 changed files) | ✅ 0 `is_secret=true` findings |
| Strict UTF-8 / BOM / mojibake (6 files) | ✅ all 6 files: no BOM, decodable UTF-8, no U+FFFD |
| `py_compile` (relevant backend files) | ✅ `api/v1/auth.py`, `services/onboarding_service.py`, `services/owner_credential_service.py`, `services/tenant_provisioning_service.py`, `schemas/auth_signup.py`, `schemas/auth.py`, `services/password_reset_service.py` all compile |
| GitNexus `analyze` + `status` | ✅ indexed at `b7fbe1c`, status up-to-date (15,252 nodes / 45,721 edges) |
| Candidate worktree clean after review | ✅ (`git status` empty; SignupPage mutation restored) |

---

## 6. HOST_LIMITATION (cannot execute, not faked as PASS)

- **Backend U6 test execution (`test_u6c…`, `test_u6f…`, `test_u6i0/i2/i3/i5/i6…`, `test_u6l…`):** The backend has **no virtualenv / installed dependencies** (`sqlalchemy`, `fastapi`, `pytest_asyncio` absent — `ModuleNotFoundError`), and there is **no `.env` / `DATABASE_URL`** and no migrated multi-tenant test PostgreSQL instance configured. The U6 harness requires a fully bootstrapped PG with tenant provisioning. Environment does not permit execution. This limitation does **not** affect the STOP decision: the three STOP conditions are proven from authoritative backend **source** at the protected baseline plus frontend **runtime** evidence (the F-C mutation), neither of which requires a running DB.
- **vitest `--shuffle`:** unavailable in pinned vitest 1.6.1; substituted with full-suite ordering exposure (F-Q).

---

## 7. Findings (summary — full detail in CSV)

| ID | Title | Severity | Blocking | Source location | Actual evidence |
|----|-------|----------|----------|-----------------|-----------------|
| F-A | First password collected then discarded (invalid secret) | P0 | YES | `SignupPage.tsx:34-37,89-96`; `onboarding_service.py:298,325`; `tenant_provisioning_service.py:362-367`; `owner_credential_service.py:142-175,250-292` | Source trace: first hash nulled at provisioning; admin `password_hash` from 2nd (email) password only; 1st pw never authenticates |
| F-B | Zero-tenant login branch unreachable; mock-only impossible-state false-green | P0 | YES | `api/v1/auth.py:260-264,487`; `LoginPage.tsx:109-113`; `SignupClosure.test.tsx:89-115` | Real `/auth/login` returns 401 for zero matches; only `/auth/refresh` returns empty tenants; test fabricates 200+[] |
| F-C | Idempotency-rotation test does not assert post-success key (false-green) | P0 | YES | `SignupClosure.test.tsx:222-253`; `SignupPage.tsx:103` | Mutation (remove line 103) → test still PASSED (1 passed / 14 skipped) |
| F-PROV | Evidence-provenance: Zcode self-review labels itself "Reviewer: Kilo" | INFO (provenance) | NO (recorded) | commit `a3243779…` → `docs/ai-reports/review/2026-08-20_dc12r1_mvp_l1_j1_r1_v1_kilo_review.md:3` | Historical report line 3 self-identifies as Kilo though Zcode-generated; PASS not inherited; report not modified/deleted |
| F-OBS1 | Single-tenant login test passes despite DashboardPage render throw | P3 | NO | `SignupClosure.test.tsx:370-455`; `DashboardPage.tsx:84` | Test renders `/` → `DashboardPage` throws "Cannot read properties of undefined (reading 'reduce')", caught by error boundary; test asserts only pathname → green despite crash. Pre-existing, not in delta. |
| F-Q | vitest 1.6.1 lacks `--shuffle`; ordering gate substituted | INFO | NO | `frontend/package.json` (vitest 1.6.1) | `--shuffle` unknown option; used full-suite run instead |

---

## 8. Accounting Gap

- **Apparent passing tests:** 354 (full suite) / 15 (SignupClosure). These counts **overstate** assurance.
- **False-green tests within the closure suite:** 2 of 15 — the zero-tenant test (F-B) and the idempotency-rotation test (F-C). They pass while asserting nothing about the claimed behavior.
- **Mandated mutation (F-C):** executed; removal of the rotation did **not** redden the test → the "rotation after success" guarantee is **unverified by the suite**.
- **First-password accounting:** the signup payload carries a real password that is hashed, stored, then nulled (`password_hash_cleanup_reason="provisioned"`) and never bound to a login credential. The user experience implies this password is their account password; it is not. This is an unaccounted customer-journey defect, not a test artifact.
- **Report SHA / local-remote equality:** see §9 (filled post-commit).

---

## 9. Report Identity

- **Candidate SHA:** `b7fbe1cccb5e3b2dc4b9c6011dab17ad5db81fe7`
- **Protected baseline / parent:** `fc8abdf327ae386c938541e847dabd786592af23`
- **Report branch:** `reports/dc12r1-mvp-l1-j1-r1-v2-kilo-independent-final-review-2026-08-20`
- **Report commit SHA:** equals the HEAD of branch `reports/dc12r1-mvp-l1-j1-r1-v2-kilo-independent-final-review-2026-08-20` (authoritative value: `git rev-parse HEAD` on the pushed branch; stated in the review delivery).
- **Local/remote equality:** verified after push — local branch HEAD == `origin/reports/dc12r1-mvp-l1-j1-r1-v2-kilo-independent-final-review-2026-08-20`.

---

## 10. Verdict

`STOP_AND_REPORT_CTO_DC12R1_MVP_L1_J1_R1_V2_KILO_INDEPENDENT_REVIEW`

Three independent STOP conditions are present (F-A first password discarded, F-B impossible-state zero-tenant false-green, F-C idempotency-rotation false-green/misnamed). All were re-derived from git objects, backend/frontend source, and executed frontend tests — no Zcode self-review PASS was inherited. Do **not** merge `origin/zcode/dc12r1-mvp-l1-j1-r1-wholesaler-signup-closure-2026-08-20` into the protected baseline until F-A, F-B, and F-C are remediated and re-reviewed.
