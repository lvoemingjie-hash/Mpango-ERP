# DC-12R1-MVP-L1-PW1-R1-V1 — Kilo Auth Defect Final Review (2026-08-14)

## Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R1_V1_KILO_FINAL_REVIEW**

(D1 root cause and runtime evidence are real and reproducible; evidence integrity holds;
accounting gap = 0. This is a *source-review* approval of the evidence branch — not a
product fix, deployment, or merge approval.)

| Verdict input | Result |
|---|---|
| D1 root cause real & reproducible | YES (reproduced live on retained staging runtime) |
| D2 real, correctly scoped P3 | YES |
| Evidence integrity (162 = 7 + 2 + 153, gap 0) | YES |
| 153 blocked from real `playwright --list` | YES (re-enumerated = 153) |
| No secrets in committed artifacts | YES |
| Frozen product tree unmodified | YES (diff = only `A pw1r1/...`) |
| Protected refs unchanged | YES |

---

## 1. Phase 1 — Proof Gate

| Check | Result |
|---|---|
| `git fetch --all --prune` | clean |
| Evidence branch SHA `pw1r1/real-jwt-browser-review-2026-08-14` | `d787c58ca85f05823fd4816e662c3db1f182dc92` == expected ✅ |
| Evidence branch direct parent | `d2e7e44cf23e91cabfab545c494abd342fec3062` (frozen product source) ✅ |
| Product source is ancestor of evidence | YES ✅ |
| `d2e7e44..d787c58` scope | **only `A pw1r1/...`** (versioned harness, provisioned evidence, results, report). Zero `M`/`D` on product paths ✅ |
| Frozen product tree modification | **none** (only additions under `pw1r1/`) ✅ |
| Protected ref `origin/product-dev-recovered` | `d2e7e44cf23e91cabfab545c494abd342fec3062` unchanged ✅ |
| Isolated reading | detached worktree at `d787c58`, removed at end; no product/PW1/harness writes ✅ |

(Protected ref `origin/pw1r1/real-jwt-browser-review-2026-08-14` = `d787c58` = the candidate; not modified by this review.)

---

## 2. Phase 2 — D1 Source Truth (root cause)

### 2.1 Observed code (frozen SHA)

- `frontend/src/pages/auth/LoginPage.tsx:78-105` (Condition C, multi-tenant):
  `updateTokens({access_token, refresh_token})` is called **first** (inside the still-mounted
  `PublicRoute`-wrapped `/login`), setting `accessToken` = **identity token** while `user`
  stays `null`; only then `navigate('/select-workspace', {replace, state:{availableTenants}})`.
- `frontend/src/stores/authStore.ts:76-80` (`updateTokens`): sets **only** `accessToken` /
  `refreshToken`; does **not** set `user` or `tenantCode`. So the store enters an
  **identity-only, user-null** state.
- `frontend/src/router/guards.tsx:31-39` (`PublicRoute`): `if (accessToken) return <Navigate to="/" replace />`.
  It checks **only `accessToken`** — it does **not** require `user` to be set.
- `frontend/src/router/guards.tsx:13-25` (`ProtectedRoute`): same pattern — admits on
  `accessToken` presence alone, never checks `user`.
- `frontend/src/router/AppRouter.tsx:95-98`: `/select-workspace` is a **top-level route with NO
  guard**, so the intended flow relies on the token being present for `WorkspaceSelectorPage`
  to call `selectTenant`.
- `frontend/src/pages/auth/WorkspaceSelectorPage.tsx`: reads tenants from `location.state`;
  the page itself is **healthy** (see §3.3).

### 2.2 Root-cause determination (combination — NOT a one-line reorder)

Per the task's explicit instruction, I do **not** certify the "one-line reorder" as the
complete fix. The defect is a **combination** of three factors:

1. **LoginPage navigation order (proximate trigger):** `updateTokens` (user=null) fires
   *before* `navigate('/select-workspace')`, while the component is still under `PublicRoute`.
2. **PublicRoute treats any `accessToken` as fully authenticated:** `PublicRoute` (and
   `ProtectedRoute`) admit on `accessToken` presence alone and never require `user != null`.
   An identity-only token is therefore treated as a contextual session.
3. **Auth-store lacks an explicit identity-vs-contextual state:** `updateTokens` produces an
   ambiguous `accessToken-set / user-null` state that guards interpret as authenticated.

Consequence on the `/login → /` transition: `updateTokens` re-renders the still-mounted
`PublicRoute`, which immediately returns `<Navigate to="/" replace/>`; the `/select-workspace`
history entry is committed but then **superseded** by `/` before `WorkspaceSelectorPage`
mounts. At `/`, `WholesalerRoute` cannot classify the `user-null` session, so the retailer
operator is admitted into the wholesaler ERP shell, where every dashboard call is rejected
with **403** by the real backend (identity-only JWT, no tenant context).

**Why a one-line reorder is insufficient:** even if `navigate` precedes `updateTokens`,
`ProtectedRoute` still admits any `accessToken`-present, `user-null` session. The same broken
state is reachable by full-page reload (the identity token is `persist`-ed to `mpango-auth`
with `user:null`) or any direct navigation to `/`. A robust fix must make guards require
`user != null` (and tenant context for ERP routes) and/or introduce an explicit
identity/contextual state — not merely reorder two lines. (Product fix is out of review scope.)

---

## 3. Phase 3 — Runtime Authenticity (independently reproduced)

Environment reused as provided: backend staging/JWT `http://127.0.0.1:8000` (200),
frontend `http://127.0.0.1:5173` (200), Playwright workspace
`C:\Users\Jeff0\playwright_pw1_r1_2026-08-14`. Real backend confirmed: `GET /api/v1/auth/me`
(no token) → `401` (not the old mock `USER_NOT_FOUND`); `/auth/login` wrong creds → flat
`{"code":"INVALID_CREDENTIALS","message":"Invalid credentials","request_id":"…"}`.

### 3.1 Uninstrumented minimal repro (`repro-workspace-selector-defect.js`, RA identity)

```
[login-resp] roles=["retailer_operator"] tenants=["TR16BB078F3A444E409D0BA80AE9D3CE","TR683EC9D1C5414CC6AE7F760ADB0406"]
[replaceState] /select-workspace {usr:{availableTenants:[W1,W2]}}
[replaceState] / {usr:null}
[replaceState] / {usr:null}
GET /dashboards/kpi/summary, /orders, /inventory/stocks ...  (ERP shell rendered)
[final] http://127.0.0.1:5173/
```
- `/auth/login` 200, **exactly 2 tenants** ✅
- Final URL = `/` ✅; **`[select-tenant-call]` never logged** (select-tenant NOT called) ✅
- Dashboard API calls fire → ERP shell rendered, `WorkspaceSelectorPage` never mounted ✅
- In this run a **single** `POST /auth/login` occurred and the defect still reproduced →
  the intermittent double-POST the candidate noted is **not** the cause of D1 (Phase 3.6).

### 3.2 Diagnostic instrumentation (`repro-module-instrumentation.js`)

```
[PR] PublicRoute render, accessToken= false   (pre-submit)
[PR] PublicRoute render, accessToken= false
[PR] PublicRoute render, accessToken= true     (after updateTokens, still on /login)
[PR] PublicRoute render, accessToken= true
[WSP]  (NEVER LOGGED — WorkspaceSelectorPage never rendered)
[final] http://127.0.0.1:5173/
```
Proves the mechanism: `updateTokens` re-renders `PublicRoute` with `accessToken=true` while
still on `/login`, and `WorkspaceSelectorPage` never renders. The instrumentation adds
**only** log lines — it does **not** change the final result (still `/`), so D1 is not an
artifact of instrumentation.

### 3.3 Manual state injection (`repro-manual-state-injection.js`) — diagnostic only

Pushing `/select-workspace` with the correct state + `popstate` renders the selector:
```
[url after manual popstate] http://127.0.0.1:5173/select-workspace
[buttons] ["PW1R1 W1 Wholesale Code: TR16BB…","PW1R1 W2 Wholesale Code: TR683…","Sign out …"]
[headings] ["Welcome Back","PW1R1 W1 Wholesale","PW1R1 W2 Wholesale"]
```
The selector logic itself is **healthy**; the defect is purely the navigation handoff.
This is diagnostic evidence that the selector works when reached — it is **not** a product
GREEN (the broken flow prevents reaching it).

---

## 4. Phase 4 — D2 Review

- Backend 401 envelope is the **flat** `{code, message, request_id}` shape (DC-12R1-H2),
  confirmed live: `{"code":"INVALID_CREDENTIALS","message":"Invalid credentials",…}`.
- Owner `LoginPage.tsx:114-120` only understands the legacy `detail.error.message`
  envelope; with the flat envelope `'error' in detail` is false → falls back to
  `axiosErr.message` → displays *"Request failed with status code 401"* (raw axios text).
- Retailer `ClientLoginPage.tsx:106-114`: on 401 → fixed neutral *"Invalid credentials"*,
  handling both envelopes; the retailer negative node is green.
- **Security properties of D2: none violated** — the message is a generic string, no raw
  body / credential / token leaked. Therefore **D2 stays P3 (cosmetic/UX) and must NOT be
  escalated to a P1 that blocks D1.**

---

## 5. Phase 5 — Evidence Integrity

### 5.1 Identity provenance
`provision_identities.py` drives the product's **formal lifecycle**: signup → email-verify →
HTTP `/auth/onboarding/setup-credential`; retailer register → reissue → HTTP
`/retailers/setup-credential`; RA multi-tenant via **two** invitations (W1 + W2) then a real
`/auth/login` asserting `available_tenants == 2`. Passwords are hashed by the product's own
`OwnerCredentialSetupService` / `RetailerProvisioningService`. **No direct `INSERT`, no
hand-written hashes.** `provision_evidence.json` (committed) contains only step assertions
(no JWT/password/`DATABASE_URL` values).

### 5.2 Secret hygiene (committed artifacts)
Scan of the committed `pw1r1/` tree for `eyJ…` / `DATABASE_URL` / `postgres://` /
`password` / `INSERT` / `bcrypt` matched only: variable-name `password=` references in the
provisioning **script** (no literal values), a redacted `[REDACTED]` example in the report,
branch names containing `bcrypt`, and a **forged** test JWT (`eyJ…forged.payload`) inside a
negative test. **No real secrets committed.** `identities.json` (passwords) is **not** in the
branch.

### 5.3 Node accounting (gap = 0)
Re-parse of `PW1_R1_RESULTS.json` + `PW1_R1_JUNIT.xml` + `PW1_R1_FINDINGS.csv`:

| Collected | Count |
|---|---|
| Executed (stage1 desktop) | 9 |
| — PASSED | 7 |
| — FAILED | 2 (D1 timeout-wait, D2 element-not-visible) |
| BLOCKED (stages 2-3, `--list` enumerated) | 153 |
| SKIPPED (genuine `test.skip`) | 0 |
| **Total** | **162** |

`reconciliation.json`: `executed 9 + blocked 153 = junit_tests 162 = csv_rows 162`;
`junit_failures 2 = json_fail 2`; **gap = 0**. CSV proper parse: `PASSED=7, FAILED=2,
BLOCKED=153`. The 2 failures map to **2 distinct root causes** (D1, D2); the 153 blocked
share the single upstream root cause D1 and are not independent defects.

### 5.4 153 blocked are real `playwright --list` nodes (re-enumerated)
Replicated the runner's exact `--list` enumeration
(`npx playwright test <stage args> --project … --list` → JSON → flatten):
- stage2-phases-desktop = **45** nodes
- stage3-matrix-tablet-mobile = **108** nodes
- **TOTAL = 153** ✅ (matches the report; not hardcoded)

### 5.5 Blocked explicitly marked not-executed
In `PW1_R1_JUNIT.xml` each blocked node is emitted as
`<testcase …><skipped message="BLOCKED: auth matrix gate failed (not a product FAIL)"/></testcase>`
inside `<testsuites … skipped="153">`. They are **not** in `failures` (failures=2), so they
are excluded from product failures. (Note for the CTO: the JUnit artifact uses the standard
`<skipped>` element for these gate-blocked nodes; the runner's own accounting labels them
`blocked`=153 / `skipped`=0 to distinguish "gate-prevented" from "voluntarily skipped". No
node is reported as passed that did not run.)

### 5.6 Runner has no skip / xfail / retry / conditional-pass / hardcoded stats
- `grep` of `pw1r1/tests/**` and `playwright.config.js`: **no** `test.skip` / `test.fixme` /
  `test.only` / `retries` / conditional logic. `playwright.config.js:14` = `retries: 0`
  (no retry masking).
- `run-tests.js` computes all counts from execution + `--list`; the only xfail-adjacent
  branch (`failed-expected`) is mapped to **failure**, never to pass. No hardcoded
  `162`/`153`/`7`/`2` statistics.

---

## 6. Deliverables of this review
- `docs/ai-reports/review/2026-08-14_dc12r1_mvp_l1_pw1_r1_v1_kilo_review.md` (this file)
- `docs/ai-reports/review/2026-08-14_dc12r1_mvp_l1_pw1_r1_v1_kilo_findings.csv`

Branch `reports/dc12r1-mvp-l1-pw1-r1-v1-kilo-review-2026-08-14` is built **from frozen
`d2e7e44`** and contains **only these two files** (product source unchanged). No product
source, PW1 harness, candidate branch, or protected ref was modified. STOP.
