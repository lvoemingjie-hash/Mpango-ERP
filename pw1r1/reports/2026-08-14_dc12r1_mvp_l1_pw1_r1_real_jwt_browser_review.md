# DC-12R1-MVP-L1-PW1-R1 — Real-JWT Browser Evidence Review (2026-08-14)

## Verdict

**STOP_AND_REPORT_CTO_WITH_REPRODUCIBLE_PRODUCT_DEFECT**

Stop condition #3 triggered: *a successful login response (HTTP 200) after which the
frontend does not enter the correct workspace* — the multi-tenant workspace selector
(`/select-workspace`) is unreachable through the real owner login flow. The session
instead lands on the wholesaler dashboard with a null user and an identity-only JWT,
producing a wall of 403s. See defect **PW1R1-D1** below for the full, reproducible chain.

No product code was modified by this task. The frozen source remains at
`d2e7e44cf23e91cabfab545c494abd342fec3062` with zero tracked-file modifications.

---

## 1. Environment & Proof Chain

| Item | Value | Evidence |
|---|---|---|
| Frozen source SHA | `d2e7e44cf23e91cabfab545c494abd342fec3062` | `git rev-parse HEAD` before and after run; tracked-mod count = 0 |
| Refs before/after | 449 refs, byte-identical | `snapshots/refs_before.txt` vs `refs_after.txt`, diff = 0 lines |
| Backend | `MPANGO_ENV=staging` (PID 26408, `uvicorn main:app --host 127.0.0.1 --port 8000`) | task launcher `run_backend_pw1r1.ps1`; log line `"env": "staging"` |
| JwtAuthStrategy proof | `GET /api/v1/auth/me` without token → `401 {"code":"UNAUTHENTICATED"}` (pre-restart Mock mode returned `401 USER_NOT_FOUND` with an injected mock identity) | probe + backend logs |
| Frontend | Vite dev server, frozen source (PID 46940, `127.0.0.1:5173`) | process command line points at the deployment tree |
| Endpoints | `/health/live` 200, `/health/ready` 200, frontend `/` 200 | curl probes |
| Datastores | PG `127.0.0.1:15432`, Redis `127.0.0.1:16379` (compose project `dc12r1_mvp_l1_r0_743684555`) | `docker ps`, both healthy |
| Old PW1 | superseded (CSV 53 nodes 21P/32F vs MD claiming 57P/60F; Mock auth; masked failures; hardcoded console-error zeros) | `playwright_test_1972351466/test-reports/SUPERSEDED_BY_PW1_R1.md` |

The old backend (PID 38792, started by `run_backend.ps1` with `MPANGO_ENV=test`) was
stopped; it was the task's own deployment process. No other process, container, or
volume was touched.

## 2. Canonical Identity Provisioning (Phase 3)

All four identities were created through the product's formal lifecycle at frozen SHA
— **no direct INSERTs, no hand-written password hashes**:

| Identity | Formal lifecycle used | Verified state |
|---|---|---|
| W1 (single-tenant wholesaler admin) | signup → email verify → `OwnerCredentialSetupService` setup token → HTTP `/auth/onboarding/setup-credential` | user active, role `admin`, 1 tenant, auto-select login 200 |
| W2 (second wholesaler admin) | same | user active, role `admin`, independent tenant |
| RA (multi-tenant retailer) | W1 invitation (HTTP) → retailer register (HTTP) → reissued setup token → HTTP `/retailers/setup-credential`; then **second binding** to W2 via a second invitation | login returns `available_tenants = [W1, W2]`, role `retailer_operator`, both bindings active |
| RB (retailer B) | W1 invitation → register → setup | user active, role `retailer_operator`, 1 tenant |

Design note: the signup lifecycle blocks a second live registration for the same
owner email (`LIVE_REGISTRATION_STATUSES` includes `active`), so a same-email
multi-tenant *owner* cannot be produced formally. The product's formal multi-tenant
path is retailer double-binding, which is how RA was provisioned.

Provisioning evidence: 27 asserted steps, all green (`provision/provision_evidence.json`),
including negative proofs (wrong password → 401 on both login surfaces).
Passwords live only in `provision/identities.json` (task-private, never committed,
never in reports).

## 3. Product Defect PW1R1-D1 (P1 — stop condition #3)

**Multi-tenant login never reaches the workspace selector; the session lands on the
wholesaler dashboard with a null user and an identity-only token.**

### Reproduction (real staging backend, real JWT, formally provisioned RA)

Minimal repro: `evidence/repro-workspace-selector-defect.js` (Playwright, ~40 lines).

Sanitized request/response (password/token values redacted):

```
POST /api/v1/auth/login            -> 200
{"email":"pw1r1.ra.r1@pw1r1.dev","password":"[REDACTED]"}
<- {"data":{"token_type":"bearer",
           "roles":["retailer_operator"],
           "available_tenants":[{"code":"TR16BB..."},{"code":"TR683..."}],
           "access_token":"[REDACTED]","refresh_token":"[REDACTED]"}}
```

Observed navigation (browser history trace, `framenavigated` + `history.replaceState` hook):

```
[replaceState] /select-workspace  state={"usr":{"availableTenants":[W1,W2]},"key":"z30olbry","idx":0}
[replaceState] /                  state={"usr":null,"key":"9vym1zu3","idx":0}
[replaceState] /                  state={"usr":null,"key":"ycfbndej","idx":0}
final URL: /     (wholesaler dashboard; every dashboard API call -> 403 Forbidden)
```

Root-cause instrumentation (`evidence/repro-module-instrumentation.js`, module patch
applied only inside the diagnostic browser session) shows the decisive facts:

```
[PR] PublicRoute render, accessToken= false    <- /login, pre-submit
[PR] PublicRoute render, accessToken= true     <- updateTokens() fired while still on /login
[WSP] (WorkspaceSelectorPage render)           <- NEVER LOGGED
```

### Mechanism (exact source locations, frozen SHA)

1. `frontend/src/pages/auth/LoginPage.tsx:96-104` — Condition C (multi-tenant) first
   calls `useAuthStore.getState().updateTokens({...})` (synchronous zustand write) and
   only then `navigate('/select-workspace', { replace: true, state: { availableTenants } })`.
2. The token write re-renders the still-mounted `PublicRoute`
   (`frontend/src/router/guards.tsx:29-37`), which now sees `accessToken` and renders
   `<Navigate to="/" replace />` (guards.tsx:35) — a competing navigation that wins the
   race; the `/select-workspace` history entry is committed but superseded before
   `WorkspaceSelectorPage` ever renders (its render hook never fires).
3. At `/`, `WholesalerRoute` (`guards.tsx:136-157`) cannot classify the session because
   `user` is still `null` (Condition C stores tokens only), so the retailer_operator is
   admitted to the wholesaler ERP shell; the dashboard's API calls run with the
   identity-only JWT and are rejected with 403 by the real backend.
4. The selector page itself is healthy: injecting the same state via `popstate`
   (`evidence/repro-manual-state-injection.js`) renders both tenant buttons and the
   selection flow completes with a real `/auth/select-tenant` 200. The defect is purely
   the navigation handoff in step 1-2.

Secondary observation (not load-bearing): the login form intermittently issues two
sequential `POST /auth/login` calls from one submit; aborting the second request does
not change the outcome, so D1 is not caused by the double submit.

### Affected red node

`[desktop] auth-matrix.spec.ts:36 — RA multi-tenant login: response carries 2 availableTenants into workspace selector`

### Suggested product fix direction (NOT applied — out of task scope)

In Condition C, navigate to `/select-workspace` *before* (or without) the intermediate
`updateTokens` write, or store the pending tenants outside the auth store so the
public-route guard cannot observe a half-established session. One-line ordering change
candidate: `LoginPage.tsx:96-104`.

## 4. Product Defect PW1R1-D2 (P3 — cosmetic/UX)

**Owner login page renders the raw axios fallback message instead of the backend's
neutral error text.**

- Node: `[desktop] auth-matrix.spec.ts:78 — wrong password on wholesaler login`
- The API correctly returns `401 {"code":"INVALID_CREDENTIALS","message":"Invalid credentials"}`.
- `frontend/src/pages/auth/LoginPage.tsx:110-124` only understands the legacy envelope
  (`detail.error.message`); with the flat structured envelope (DC-12R1-H2) it falls
  back to `axiosErr.message` and displays *"Request failed with status code 401"*.
- Contrast: `frontend/src/pages/client/ClientLoginPage.tsx:101-114` (DC-12R1-S2-R2)
  handles both envelopes and shows the neutral message — the retailer-portal negative
  node is green.
- Security properties verified green on the same node: 401 status asserted, no token
  persisted, user remains on `/login`, neutral portal behavior for the retailer surface.

## 5. Green Evidence (real JWT, staging)

All of the following passed with HTTP-level assertions on the real login APIs:

- W1 and W2 single-tenant owner logins: `/auth/login` 200 → auto `/auth/select-tenant`
  200 → `/` dashboard, `mpango-auth` persisted (`state.accessToken`, `user.roles`,
  `tenantCode`).
- Retailer portal logins (RB at W1 portal; RA at W1 portal): `/client/auth/login` 200
  → lands on `/client`, portal code preserved in `mpango-auth`.
- Negative auth: wrong password on both surfaces → 401, stays on the login page, no
  token persisted, no "logged in" claims.
- `/select-workspace` direct access without navigation state → redirected to `/login`.
- Logout clears the session and returns to `/login`.

## 6. Node Accounting (gap = 0)

Execution order followed Phase 5: desktop auth matrix first; phases 1-6 and the
tablet/mobile matrix were **BLOCKED** by the auth gate and are explicitly *not* counted
as product failures (Phase 5.4 rule).

| Collected | Count |
|---|---|
| Executed nodes (stage 1, desktop) | 9 |
| — PASSED | 7 |
| — FAILED (product root causes D1, D2) | 2 |
| BLOCKED (planned nodes of stages 2-3, `--list` enumerated) | 153 |
| SKIPPED | 0 |
| **Collected total** | **162** |

Reconciliation (post-generation re-parse of the emitted files):
`executed 9 + blocked 153 = junit_tests 162 = csv_rows 162`; `junit_failures 2 =
json_fail 2`; **accounting gap = 0** (`reports/reconciliation.json`).

Red-node root-cause dedup: 2 red nodes → 2 distinct root causes
(P1 navigation race `D1`; P3 error-message rendering `D2`). The 153 blocked nodes share
the single upstream root cause D1 and are not independent defects.

Note on scope: because the auth gate failed, the financial idempotency fingerprint
journeys and the cross-tenant/cross-retailer browser isolation journeys are among the
blocked nodes. API-level isolation evidence from provisioning (W2 retailer list excludes
RB; RA cross-tenant contexts resolve independently) is green in
`provision/provision_evidence.json`, but the full PW1 isolation matrix remains to be
executed after D1 is fixed.

## 7. Before/After Reconciliation

| Check | Before | After |
|---|---|---|
| git refs | 449 | 449 (diff = 0) |
| HEAD | `d2e7e44c...` detached | identical |
| Tracked modifications | 0 | 0 |
| Containers | compose PG+Redis healthy; unrelated projects untouched | unchanged |
| Ports | 8000→PID 38792 (old, test mode); 5173→46940; 15432/16379→docker | 8000→PID 26408 (staging); 5173→46940 unchanged; datastores unchanged |
| DB residue | old TEST001-3 direct-insert data (pre-existing, untouched); no PW1R1 rows | + 2 PW1R1 tenant schemas, 2 registrations (active), 4 provisioned users, 2 retailers, 3 bindings (active), 3 used invitations, 2 consumed owner setup tokens, 2 consumed + 2 revoked retailer setup tokens, 2 consumed verification tokens. No harness-created SKUs/orders/declarations (phase 4 blocked). |

## 8. Deliverables

| Deliverable | Path |
|---|---|
| Versioned harness | this workspace (`tests/`, `run-tests.js`, `playwright.config.js`, `provision/provision_identities.py`, `evidence/`) — pushed to isolated branch `pw1r1/real-jwt-browser-review-2026-08-14` |
| Results JSON | `reports/PW1_R1_RESULTS.json` |
| JUnit XML | `reports/PW1_R1_JUNIT.xml` |
| Findings CSV | `reports/PW1_R1_FINDINGS.csv` |
| This report | `reports/2026-08-14_dc12r1_mvp_l1_pw1_r1_real_jwt_browser_review.md` |
| Reconciliation | `snapshots/` (refs/containers/ports/db before+after), `reports/reconciliation.json` |
| Supersede marker | `playwright_test_1972351466/test-reports/SUPERSEDED_BY_PW1_R1.md` |

Credential hygiene: `provision/identities.json` (passwords), backend `.env`, JWTs and
`DATABASE_URL` values are excluded from the branch; an automated scan for
`eyJ…` JWT prefixes and connection-string/secret patterns across all committed
artifacts returned clean.

## 9. Re-run instructions (after D1 is fixed)

```
# backend already running with MPANGO_ENV=staging (run_backend_pw1r1.ps1)
cd C:\Users\Jeff0\playwright_pw1_r1_2026-08-14
node run-tests.js     # stage1 gate -> stage2 phases -> stage3 matrix, reconciliation built-in
```

The runner re-provisions nothing; identities are stable (fixed suffix `r1`) and
`provision_identities.py` is rerun-safe.
