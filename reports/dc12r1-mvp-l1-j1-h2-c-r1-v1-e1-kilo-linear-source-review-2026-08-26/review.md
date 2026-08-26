# DC-12R1-MVP-L1-J1-H2-C-R1-V1 Kilo Bounded Final Source and Test-Authenticity Review

**VERIFICATION_TIER:** V1_SOURCE_REVIEW
**CLAIM_CEILING:** BOUNDED_SOURCE_AND_TEST_AUTHENTICITY_APPROVAL_ONLY
**REVIEW_BASE:** b2d28f320c7428e7e81f7cb2033c99b1aa4471dd
**IMPLEMENTATION:** 867810af364b53ba4d73ac57e0c45fe43ffb1a5c
**TEST_FIX:** 446c7210d54379363e8ce8acb663d5caa5ee952e
**CANDIDATE:** 8ad346e52ff812638a6ac35205b3aade68e20005
**PROTECTED_BASELINE:** 2c20d58c88a0a8f5175f4d11041d03b6ca785e06

---

## Phase 1 Proof Gate

| Check | Result |
|---|---|
| `git fetch --all --prune` | PASS |
| Detached worktree at CANDIDATE | PASS (`C:\Users\Jeff0\AppData\Local\Temp\kilo\dc12r1-h2-c-r1-v1-wt`) |
| Remote source tip == CANDIDATE | PASS (`remotes/origin/zcode/dc12r1-mvp-l1-j1-h2-c-r1-retailer-recovery-discovery-2026-08-26` → `8ad346e5`) |
| Chain `b2d28f32 -> 867810af -> 446c7210 -> 8ad346e5` | PASS (all ancestry checks exit 0) |
| Cumulative delta == 12 declaration files | PASS (exactly 12 files) |
| `authService.ts` unchanged | PASS |
| `j1h2b-forgot-reset/**` unchanged | PASS |
| `migration`/`model`/`dependency`/`lockfile`/`deployment` unchanged | PASS |
| Protected baseline is ancestor of CANDIDATE | PASS (`2c20d58c` in history of `8ad346e5`) |
| `origin/main` drift check | NOTE: `origin/main` (`134ea59e`) is a separate CI/docs branch and is neither ancestor nor descendant of the candidate chain. The protected baseline `2c20d58c` is the correct product baseline ancestor. No product-main drift relative to the protected baseline within the candidate ancestry. |

### 12-File Delta (REVIEW_BASE..CANDIDATE)

1. `ai-ledger/product-ai/2026-08-26_dc12r1_mvp_l1_j1_h2_c_r1_retailer_recovery_discovery.md`
2. `backend/services/onboarding_service.py`
3. `backend/services/retailer_provisioning_service.py`
4. `backend/tests/test_dc12r1_j1_h2c_retailer_recovery_discovery.py`
5. `frontend/src/pages/client/ClientLoginPage.tsx`
6. `frontend/src/pages/retailer/RetailerForgotPasswordPage.tsx`
7. `frontend/src/pages/retailer/RetailerResetPasswordPage.tsx`
8. `frontend/src/router/AppRouter.tsx`
9. `frontend/src/tests/Dc12r1S2RetailerPortal.test.tsx`
10. `frontend/src/tests/PublicPasswordRecoveryInterceptor.test.tsx`
11. `frontend/src/tests/RetailerCredentialPages.test.tsx`
12. `frontend/src/tests/RetailerPasswordRecoveryDiscovery.test.tsx`

---

## Phase 2 Mandatory Product Source Review

### 2.1 Route Authorization
**Item 1:** `/retailer/forgot-password` is a public route.
**Evidence:** `AppRouter.tsx:95` — `{ path: '/retailer/forgot-password', element: <RetailerForgotPasswordPage /> }` is nested under `<PublicRoute />` (`AppRouter.tsx:81`). No `ProtectedRoute` or retailer/wholesaler guard wraps it.
**Verdict:** PASS — no auth bypass.

### 2.2 Forgot Password Entry Guard
**Item 2:** Forgot password entry renders only for valid `portalCode`, carrying normalized `w`.
**Evidence:** `ClientLoginPage.tsx` normalizes `w` via `trim().toUpperCase()` and `^[A-Z0-9]+$` regex; the forgot-password link href is built only when `isValidPortal` is true. `RetailerForgotPasswordPage.tsx:31-33` repeats the same normalization.
**Verdict:** PASS.

### 2.3 Invalid Portal Zero-Call
**Item 3:** Missing or malformed `w` shows neutral invalid-portal state and zero recovery API calls.
**Evidence:** `RetailerForgotPasswordPage.tsx:70-89` — early return with "Invalid Portal" UI before any API call. `RetailerPasswordRecoveryDiscovery.test.tsx:110-119` asserts `mockPost` not called for missing and `w=BAD%21`.
**Verdict:** PASS.

### 2.4 Single API Call / No Raw Error
**Item 4:** Forgot password page calls only `authService.retailerForgotPassword`; never displays raw error.
**Evidence:** `RetailerForgotPasswordPage.tsx:56-59` calls only `retailerForgotPassword`. Catch block at line 64 sets fixed neutral string. `RetailerPasswordRecoveryDiscovery.test.tsx:186-203` (M3) verifies raw error is never surfaced.
**Verdict:** PASS.

### 2.5 submitInFlight Synchronous Guard
**Item 5:** `submitInFlight` ref must be synchronous before `await`/React re-render.
**Evidence:** `RetailerForgotPasswordPage.tsx:52-53` sets `submitInFlight.current = true` before `await`. The double-click test (`RetailerPasswordRecoveryDiscovery.test.tsx:137-159`) uses `act(() => { button.click(); button.click(); })` to dispatch both clicks synchronously; only the ref guard suppresses the second submit.
**Verdict:** PASS.

### 2.6 Canonical `w.code` from DB Row
**Item 6:** `_find_verified_retailer_for_wholesaler` returns database matched row's canonical `w.code`.
**Evidence:** `retailer_provisioning_service.py:1004-1043` — SQL query selects `w.code` from the matched wholesaler row. The match predicate is `lower(w.code) = lower(:code)` but the returned `row[1]` is the canonical DB value. `request_password_reset` at line 918 unpacks `retailer, canonical_wholesaler_code = match` and passes `canonical_wholesaler_code` to `build_retailer_reset_link`.
**Verdict:** PASS.

### 2.7 Legacy Link Byte Shape Preservation
**Item 7:** `build_retailer_reset_link` without `w` preserves historical link byte shape.
**Evidence:** `onboarding_service.py:489-515` — when `wholesaler_code` is `None`, `fragment = f"resetToken={encoded}"` and `path = f"/retailer/reset-password#{fragment}"`. Backend test `test_reset_link_legacy_shape_unchanged_without_code` asserts exact legacy string `/retailer/reset-password#resetToken=raw-reset-token-1`.
**Verdict:** PASS.

### 2.8 Fragment-Only Email Link with `w`
**Item 8:** Email link with `w` is fragment-only: `#resetToken=<SECRET>&w=<CANONICAL_CODE>`.
**Evidence:** `onboarding_service.py:506-515` — when `wholesaler_code` is provided, fragment becomes `resetToken=<SECRET>&w=<CANONICAL_CODE>` and path is `/retailer/reset-password#{fragment}`. No query string is ever produced.
**Verdict:** PASS.

### 2.9 Reset Page Reads `w` Before Scrub
**Item 9:** Reset page reads `w` before URL scrub; token and `w` must not enter storage/log.
**Evidence:** `RetailerResetPasswordPage.tsx:44-54` — `useEffect` parses `w` from `location.hash` via `URLSearchParams` BEFORE calling `readFragmentToken` (which scrubs the URL as a side effect). The POST body at line 74 contains only `reset_token` and `new_password`.
**Verdict:** PASS.

### 2.10 Reset POST Body Scope
**Item 10:** Reset POST body contains only `reset_token` and `new_password`.
**Evidence:** `RetailerResetPasswordPage.tsx:74` — `authService.retailerResetPassword({ resetToken: state.token, newPassword })`. Backend schema `RetailerResetPasswordRequest` defines only `reset_token` and `new_password`. Frontend test `RetailerPasswordRecoveryDiscovery.test.tsx:220-229` and `RetailerCredentialPages.test.tsx:79-84` assert body shape.
**Verdict:** PASS.

### 2.11 Success CTA Routing
**Item 11:** Success CTA only enters `/retail/login?w=<CODE>`, never wholesaler `/login`.
**Evidence:** `RetailerResetPasswordPage.tsx:99-105` — when `portalCode` is truthy, CTA href is `/retail/login?w=${portalCode}`. Legacy branch at lines 107-116 shows neutral text with no `/login` link. `RetailerPasswordRecoveryDiscovery.test.tsx:238-249` asserts no `/login` link.
**Verdict:** PASS.

### 2.12 Legacy Token Reset Path
**Item 12:** Legacy valid token must still reset, showing only supplier portal return guidance.
**Evidence:** `RetailerResetPasswordPage.tsx:107-116` — legacy branch renders neutral guidance "Return to the portal link your supplier provided to sign in." No `/login` CTA, no portal guessing. Backend `consume_password_reset` does not require `w`.
**Verdict:** PASS.

### 2.13 401 Stay-on-Page Neutrality
**Item 13:** Forged/expired token 401 stays on page with neutral error; no refresh/logout/navigation.
**Evidence:** Backend `retailer_reset_password` returns neutral 401 (`RESET_TOKEN_INVALID` + `NEUTRAL_RETAILER_CREDENTIAL_MESSAGE`). Frontend catches and displays fixed neutral copy. `api.ts:119-121` — `skipAuthInterceptors: true` causes immediate rejection with no toast, no refresh, no logout, no navigation. `PublicPasswordRecoveryInterceptor.test.tsx:T1/T3` verifies zero refresh/logout/toast/navigation under stale session.
**Verdict:** PASS.

### 2.14 Public `w` Not a Binding Credential
**Item 14:** Public `w` must not be treated as binding credential; tampered `w` cannot change account or tenant binding.
**Evidence:** `_find_verified_retailer_for_wholesaler` uses `w` only for lookup. `consume_password_reset` derives `retailer_id` exclusively from `token_row.retailer_id` (the reset token binding). `_write_hash_to_mapped_copies` updates users keyed by `tenant_user_id` from the binding, not by `w`. Tampering `w` only affects the email-lookup step; it cannot alter account or tenant binding.
**Verdict:** PASS.

---

## Phase 3 Test Authenticity Review

### 3.1 Five Test Files — Real Product Code Hit Assessment

| File | Authenticity Assessment |
|---|---|
| `backend/tests/test_dc12r1_j1_h2c_retailer_recovery_discovery.py` | **REAL DB + REAL SMTP sink.** Provisions tenant via `_make_tenant` → invitation → `register_with_invitation` → `consume_setup_token` → real `request_password_reset` → captures email via `get_dev_retailer_email_deliveries`. Not mock-only. |
| `frontend/src/tests/RetailerPasswordRecoveryDiscovery.test.tsx` | **REAL rendered components.** Uses `render` + `userEvent` + `act` against actual `RetailerForgotPasswordPage` / `RetailerResetPasswordPage` / `ClientLoginPage`. API layer is mocked, but component behavior, ref guards, URL scrub, and storage spy assertions are real. |
| `frontend/src/tests/PublicPasswordRecoveryInterceptor.test.tsx` | **REAL interceptors.** Installs a recording Axios adapter on the shared `api` instance. The request interceptor (token injection), response interceptor (refresh/queue/logout), and `skipAuthInterceptors` opt-out all execute for real. `authService` is NOT mocked. T1–T6 are truth-level interceptor tests. |
| `frontend/src/tests/RetailerCredentialPages.test.tsx` | **REAL rendered components.** Tests `RetailerSetupCredentialPage` and `RetailerResetPasswordPage` with real mounting, URL scrub observation (`window.location.hash`), and `Storage.prototype.setItem` spy. |
| `frontend/src/tests/Dc12r1S2RetailerPortal.test.tsx` | **REAL rendered components + guards.** Tests `ClientLoginPage`, `RetailerRoute`, `WholesalerRoute`, and `ClientLoginAliasRedirect` with real `MemoryRouter`/`Routes` mounting. Auth store is seeded; API is mocked for call-isolation assertions only. |

**Verdict:** All five files contain genuine product-code truth tests. None are mock-only false greens.

### 3.2 M1–M9 Mutation Point Verification

| Mutation | Description | RED Node | Restored Blob Consistency | Evidence Source |
|---|---|---|---|---|
| M1 | Remove valid-portal forgot-password entry | HC01/HC02 fail (entry missing) | PASS — byte-identical restore | `RetailerPasswordRecoveryDiscovery.test.tsx:62-83` + `Dc12r1S2RetailerPortal.test.tsx:210-221` |
| M2 | Invalid portal still shows entry | HC02 fails (entry present on invalid portal) | PASS — byte-identical restore | `RetailerPasswordRecoveryDiscovery.test.tsx:79-89` |
| M3 | Forgot page leaks raw error | M3 test fails (raw error surfaced) | PASS — byte-identical restore | `RetailerPasswordRecoveryDiscovery.test.tsx:186-203` |
| M4 | Reset email drops `w` | HC11/HC17 assertions fail (`&w=` missing) | PASS — byte-identical restore | `test_dc12r1_j1_h2c_retailer_recovery_discovery.py:94-121` |
| M5 | Email echoes caller's lowercase code | HC17 assertion fails (lowercase present) | PASS — byte-identical restore | `test_dc12r1_j1_h2c_retailer_recovery_discovery.py:94-121` |
| M6 | Scrub then read `w` from live `window.location.hash` | HC13 fails (portalCode lost after scrub, success CTA missing `w`) | PASS — byte-identical restore | `RetailerPasswordRecoveryDiscovery.test.tsx:208-234` + `RetailerPasswordRecoveryDiscovery.test.tsx:238-249` |
| M7 | Success CTA restored to `/login` | HC13 fails (CTA points to `/login`) | PASS — byte-identical restore | `RetailerPasswordRecoveryDiscovery.test.tsx:238-249` |
| M8 | Legacy link treated as invalid | HC14 fails (InvalidLink shown instead of reset success) | PASS — byte-identical restore | `RetailerPasswordRecoveryDiscovery.test.tsx:253-268` |
| M9 | Remove single-submit protection | HC06 fails (2 POSTs on double-click) | PASS — byte-identical restore | `RetailerPasswordRecoveryDiscovery.test.tsx:137-159` |

### 3.3 M6 Real Defect Form Verification
**Requirement:** Verify M6 uses scrub then read live `window.location.hash` real defect form.
**Evidence:** `RetailerResetPasswordPage.tsx:44-54` reads `w` from `location.hash` BEFORE calling `readFragmentToken` (which scrubs). If mutated to read after scrub, `location.hash` would be empty, `portalCode` would be `null`, and the success CTA would fall through to the legacy branch — causing HC13 to fail. The test `HC13` (line 238) asserts `/retail/login?w=VALID`, which would break under the mutation.
**Verdict:** M6 defect form is correctly identified and test-gated. `CANDIDATE_PROVIDED_EVIDENCE` — Kilo did not re-execute the scripted mutation; the candidate's mutation ledger documents the RED outcome and byte-identical restore.

### 3.4 M9 Double-Click in Single `act`
**Requirement:** Verify M9 same-`act` double-click triggers second submit before React disables button.
**Evidence:** `RetailerPasswordRecoveryDiscovery.test.tsx:146-149`:
```tsx
act(() => {
  button.click();
  button.click();
});
```
Both clicks are dispatched synchronously inside one `act` batch. React cannot re-render and set `isSubmitting` between them. The `submitInFlight.current = true` guard at `RetailerForgotPasswordPage.tsx:53` is synchronous, so the second click is suppressed. Without the guard, both clicks would enter `onSubmit` and `mockPost` would be called twice.
**Verdict:** M9 is correctly gated. `CANDIDATE_PROVIDED_EVIDENCE` — Kilo did not re-execute the scripted mutation removal; the candidate's ledger records 1 failure on M9 removal and byte-identical restore.

### 3.5 HC01–HC17 Inventory Cross-Check
**Source:** `docs/test-plans/2026-08-26_dc12r1_mvp_l1_j1_h2_c_node_inventory.csv` (18 nodes, HC01–HC17).
**Cross-check:** Node IDs, order, and oracle meanings match the candidate's test suite:
- HC01–HC06: discovery, invalid-portal zero-call, form validation, double-click — covered by `RetailerPasswordRecoveryDiscovery.test.tsx`
- HC07–HC10: four-case canonical neutrality — **frontend mock coverage only** (see 3.6)
- HC11: fragment-only link shape — covered by backend `test_dc12r1_j1_h2c_retailer_recovery_discovery.py`
- HC12: URL scrub + leakage scan — covered by `RetailerPasswordRecoveryDiscovery.test.tsx`
- HC13: success CTA to portal — covered by `RetailerPasswordRecoveryDiscovery.test.tsx`
- HC14: legacy link validity — covered by `RetailerPasswordRecoveryDiscovery.test.tsx`
- HC15: forged/expired token — covered by `RetailerPasswordRecoveryDiscovery.test.tsx` and `PublicPasswordRecoveryInterceptor.test.tsx`
- HC16: 390px responsive reset page — jsdom structural coverage in `RetailerPasswordRecoveryDiscovery.test.tsx`
- HC17: DB-canonical `w` code — covered by backend `test_dc12r1_j1_h2c_retailer_recovery_discovery.py`

**Verdict:** IDs, order, and oracle meanings align. No inventory drift detected.

### 3.6 HC07–HC10 Canonical Neutrality Evidence Boundary
**Requirement:** If real HTTP four-case canonical equality proof exists, name the node and assertion. If only frontend mock or source derivation, mark `NOT_YET_RUNTIME_PROVEN`. Do not advance browser-gate responsibility.
**Finding:** The frontend test `RetailerPasswordRecoveryDiscovery.test.tsx:164-182` mocks `mockPost.mockResolvedValue(NEUTRAL_OK)` for all four email cases and asserts identical rendered neutral copy. This is **frontend mock only** — it does not exercise the real backend HTTP responses.
The backend `request_password_reset` (`retailer_provisioning_service.py:900-960`) is always-neutral by design (returns `False` for no-match, catches `EmailDeliveryNotConfiguredError`, rolls back), but the H2-C candidate test suite does **not** contain a real HTTP integration test that POSTs all four email cases to `/client/auth/forgot-password` and compares canonical response equality.
**Boundary:** HC07–HC10 canonical neutrality is `NOT_YET_RUNTIME_PROVEN` at the HTTP level. The candidate provides source-code proof of neutrality design and frontend mock proof of UI uniformity. Authoritative runtime proof is deferred to the subsequent browser/backend gate.
**Verdict:** NOT_YET_RUNTIME_PROVEN — frontend mock + source derivation only.

### 3.7 Candidate-Provided Evidence Disclosure
The following items were **not independently executed by Kilo** and are recorded as `CANDIDATE_PROVIDED_EVIDENCE`:
- M1–M9 scripted mutation RED runs and byte-identical restores.
- Backend real-DB neutrality integration tests for HC07–HC10 four-case canonical equality.
- Authoritative Playwright browser execution for HC01–HC17 (390px, fragment scrub, live navigation).
- Windows 8F/35E parent-differential zero-new-red evidence (candidate's own host-run).

---

## Phase 4 Bounded Runtime

### 4.1 Frontend Focused Tests
- **Natural order:** 4 files / 59 tests — PASS
  `RetailerPasswordRecoveryDiscovery.test.tsx` (20) + `PublicPasswordRecoveryInterceptor.test.tsx` (7) + `RetailerCredentialPages.test.tsx` (11) + `Dc12r1S2RetailerPortal.test.tsx` (21)
- **Reverse order:** 4 files / 59 tests — PASS
  Same files in reverse execution order; identical pass set.

### 4.2 Full Frontend Vitest
- **Result:** 28 files / 416 tests — PASS
- **Duration:** 23.20s

### 4.3 Frontend Build
- **Command:** `pnpm build` (`tsc -p tsconfig.app.json && vite build`)
- **Result:** PASS — `dist/index.html` + `assets/index-*.js` + `assets/index-*.css` produced in 5.56s.

### 4.4 Backend Focused Tests
- **HOST_LIMITATION disclosed:** This Windows host does not have `psql` (PostgreSQL 16 client) or `redis-cli` (Redis 7) available, and no Python virtual environment is present in the worktree. The candidate's own fresh-stack backend focused run (H2-C 4/4 + S1 credential 3 + H2-B runtime closure = 42/42) and full suite (3651 passed / 8 failed / 69 skipped / 15 xfailed / 35 errors, gap=0 vs parent) are recorded as `CANDIDATE_PROVIDED_EVIDENCE`.
- **Kilo did execute:** `py_compile` on `backend/services/onboarding_service.py`, `backend/services/retailer_provisioning_service.py`, and `backend/tests/test_dc12r1_j1_h2c_retailer_recovery_discovery.py` — PASS.

---

## Phase 5 Quality

| Check | Result |
|---|---|
| `git diff --check` (REVIEW_BASE..CANDIDATE) | PASS — no whitespace errors |
| `py_compile` (3 changed backend files) | PASS |
| `tsc -p tsconfig.app.json --noEmit` | PASS — zero type errors |
| `detect-secrets scan --baseline .secrets.baseline` | PASS — no new secrets |
| UTF-8 / no-BOM (all 12 changed files) | PASS |
| GitNexus analyze | PASS — 28,898 nodes / 60,313 edges / 842 clusters / 300 flows |
| Detached worktree clean | PASS (`git status` clean after restoring `.secrets.baseline`) |

---

## STOP Condition Checks

| STOP Trigger | Status |
|---|---|
| 谱系、远端 tip 或 12 文件范围不一致 | NOT TRIGGERED |
| canonical w 来自调用方输入而非数据库行 | NOT TRIGGERED |
| token 进入 query/storage/log | NOT TRIGGERED |
| legacy 链接失效或跳向 /login | NOT TRIGGERED |
| 401 再次触发全局 refresh/logout/navigation | NOT TRIGGERED |
| 双击测试、M6/M9 或 canonical-neutrality 证据属于 false-green | NOT TRIGGERED (M6/M9 verified as real defect forms; HC07–HC10 correctly marked NOT_YET_RUNTIME_PROVEN) |
| 报告把 candidate evidence 写成 Kilo 独立运行证明 | NOT TRIGGERED (all candidate-only evidence explicitly labeled) |

---

## Final Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_R1_V1_KILO_BOUNDED_FINAL_SOURCE_REVIEW**

This bounded review approves the candidate source and test-authenticity within the declared ceiling. It does **not** claim:
- Independent backend full-suite zero-red
- HC01–HC17 authoritative browser PASS
- Merge-ready or deployment-ready

Next step is the subsequent browser/backend gate for HC07–HC10 runtime canonical neutrality and authoritative Playwright execution.
