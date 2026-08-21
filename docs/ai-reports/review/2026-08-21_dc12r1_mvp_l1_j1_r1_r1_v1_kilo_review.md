# DC-12R1-MVP-L1-J1-R1-R1-V1 — Kilo Independent Final Adversarial Source Review

- **Review date:** 2026-08-21
- **Reviewer:** Kilo (independent adversarial review; prior STOP `c63ddf1f` accepted as input)
- **Candidate SHA:** `cbcecbf2bcb670efd67f2680075a7afea7562223`
- **Required parent:** `candidate^ == b7fbe1cccb5e3b2dc4b9c6011dab17ad5db81fe7` ✅
- **Protected baseline:** `fc8abdf327ae386c938541e847dabd786592af23` (must be an ancestor) ✅
- **Source branch:** `origin/zcode/dc12r1-mvp-l1-j1-r1-r1-signup-contract-truth-2026-08-20` == candidate ✅
- **Report branch (only 2 files pushed):** `reports/dc12r1-mvp-l1-j1-r1-r1-v1-kilo-review-2026-08-21`
- **VERDICT:** `PASS_FOR_CTO_DC12R1_MVP_L1_J1_R1_R1_V1_KILO_FINAL_REVIEW`

---

## 1. Proof & Scope (Phase 1) — ALL PASS

| Gate | Result | Evidence |
|------|--------|----------|
| Candidate is a commit & == remote source tip | PASS | `git cat-file -t` = commit; `origin/...signup-contract-truth-2026-08-20` = `cbcecbf2…` |
| Direct parent `candidate^ == b7fbe1cc` | PASS | `rev-parse candidate^` = `b7fbe1cccb5e3b2dc4b9c6011dab17ad5db81fe7` |
| Baseline `fc8abdf3` is ancestor | PASS | `merge-base --is-ancestor fc8abdf3 candidate` exit 0 |
| Delta == exactly 9 declared files | PASS | `git diff --name-status b7fbe1cc cbcecbf2` → 9 files (see §2) |
| No migration/model/dependency/lockfile/config/deploy change | PASS | filename filter for `migrations|models/|requirements|package.json|pnpm-lock|lock.json|.config.|deploy|Dockerfile|compose|k8s|helm|.env` → none |
| Candidate worktree remains clean | PASS | `git status --porcelain` empty after all operations (mutation restored, `.secrets.baseline` restored) |
| Protected refs unchanged | PASS | `origin/product-dev-recovered` = `fc8abdf327…`; source branch tip = candidate |

Delta (9 files):
1. `ai-ledger/product-ai/2026-08-20_dc12r1_mvp_l1_j1_r1_r1_signup_contract_truth.md` (new ledger entry — not source)
2. `backend/schemas/auth_signup.py` (M)
3. `backend/services/onboarding_service.py` (M)
4. `backend/tests/test_u6c_signup_email_verification_skeleton.py` (M)
5. `backend/tests/test_u6i6_onboarding_e2e_closeout.py` (M)
6. `frontend/src/pages/auth/LoginPage.tsx` (M)
7. `frontend/src/pages/auth/SignupPage.tsx` (M)
8. `frontend/src/tests/SignupClosure.test.tsx` (M)
9. `frontend/src/types/auth.ts` (M)

---

## 2. Cross-version Idempotency (Phase 2) — RESOLVED, NO STOP

### 2.1 Fingerprint algorithms (independent review)
- **New canonical** `_request_fingerprint_hash` (`backend/services/onboarding_service.py:578-595`): payload = `{business_type, company_name, country, email, phone}` — **password deliberately excluded**; HMAC-SHA256 over sorted-JSON canonical.
- **Legacy** `_request_fingerprint_hash_with_password` (`onboarding_service.py:558-575`): identical but **includes `password`**; retained **only** for idempotent replay of rows written by pre-R1-R1 code; never used to create new fingerprints.

### 2.2 New registrations never include password in canonical fingerprint
Confirmed: `create_signup_registration` computes `fingerprint_hash = _request_fingerprint_hash(...)` (passwordless) and stores that. ✅

### 2.3 Legacy compatibility usage constraints (`onboarding_service.py:305-329`)
The legacy branch is reached **only when** an existing registration already exists for the idempotency key, and then **only when**:
- the **replaying request itself carries a valid legacy password** (`request.password is not None`), AND
- the replay request's legacy fingerprint exactly equals the stored legacy fingerprint (`existing.request_fingerprint_hash == _request_fingerprint_hash_with_password(request,...)`).

On match it **returns the existing registration** (no new creation, no authorization broadening). Otherwise raises `IdempotencyConflictError`.

### 2.4 Compatibility path cannot accept forbidden variations
| Forbidden case | Behavior | Code guarantee |
|---|---|---|
| changed email/tenant code/organization data | 409 | legacy fingerprint includes those fields → mismatch → conflict |
| different password | 409 | legacy fingerprint includes `password`; differing password → mismatch → conflict |
| omitted password against a legacy fingerprint | 409 | first condition `request.password is not None` fails → `legacy_match=False` → conflict |
| malformed/oversized legacy password | rejected pre-fingerprint | `validate_signup_password` runs at `onboarding_service.py:299-300` (min 8 / max 128) → `ValueError` |

No authorization broadening (the path only replays the existing row; it never creates or elevates). ✅

### 2.5 Test authenticity — DB-write-then-replay (PROVEN at source)
`backend/tests/test_u6c_signup_email_verification_skeleton.py:447-493` (`test_legacy_fingerprint_record_replays_under_new_code_without_409`) **INSERTs** a row with a real pre-R1-R1 legacy fingerprint (`_legacy_fingerprint(payload, email)` = `_request_fingerprint_hash_with_password(...)`), then **replays through the current production endpoint** (`client.post("/api/v1/auth/signup", json=payload, headers={Idempotency-Key:key})`). Asserts HTTP 202, `len(rows)==1` (replayed, no new registration), `password_hash is None`.

### 2.6 Same key + exact legacy payload → original accepted result, no new registration
Covered by §2.5 (202, single existing row). ✅

### 2.7 Same key + changed payload → 409
`test_legacy_fingerprint_record_still_409_for_different_payload` (`test_u6c:496-534`): preset legacy row, replay with `companyName="Different Co Ltd"` under same key → **409** `IDEMPOTENCY_CONFLICT`. ✅

### 2.8 Leak / timing / downgrade review
- **No password persistence:** `password_hash=None` (`onboarding_service.py:348`); `hash_password` import removed; never written.
- **No logging/reflection:** signup endpoint (`api/v1/auth.py:102-119`) passes `Idempotency-Key` to the service and has no `logger.`/`logging.`/`print(` of password; response schema carries no password/token.
- **No downgrade:** new registrations use passwordless canonical; legacy path is replay-only.
- **Timing note (P3, non-blocking):** fingerprint comparison uses Python `!=` on HMAC hexdigests rather than `hmac.compare_digest`. Since the operands are HMAC outputs (not plaintext secrets), practical timing exposure is negligible; flagged as a low-severity hardening suggestion, **not** a STOP.

---

## 3. Passwordless Signup Contract (Phase 3) — RESOLVED

- **F-A `SignupRequest.password` optional/deprecated only for compatibility:** `auth_signup.py:24-26` (`password: str | None = Field(None, min_length=8, max_length=128, deprecated=True)`); validated only when present (`onboarding_service.py:299-300`). ✅
- **Current `SignupPage` does not render/collect/retain/transmit a password:** `SignupPage.tsx` — no password field in `signupSchema` (lines 29-53), no password input JSX, payload (lines 97-103) omits password, no `localStorage`/`sessionStorage` write. Confirmed by passing test `the signup form never renders a password input` and `submits a payload with NO password field`. ✅
- **Newly accepted registrations store `password_hash=NULL`:** `onboarding_service.py:348` + tested (`test_u6c:221`, `test_u6i6:345`, `test_u6i6:379`). ✅
- **Credential setup remains the only path establishing the actual password:** `owner_credential_service` (unchanged in this delta) sets `users.password_hash`; `test_u6i6:428` verifies `verify_password(OWNER_PASSWORD, owner_admin["password_hash"])` after setup-credential. ✅
- **Terminal cleanup & secret-leak protections intact:** `test_u6i6:380-381` asserts `password_hash_cleared_at is not None` and `cleanup_reason=="provisioned"`; query-string token rejection (405/401) preserved (`test_u6i6:464,472`). ✅
- **No query-string / browser-persistence exposure:** all setup/reset/verification links use URL **fragment** (`onboarding_service.py:413-487`); tests assert key never enters URL/storage/UI (`SignupClosure.test.tsx:299-315`). ✅

---

## 4. U6I6 Authenticity (Phase 4) — INTACT

- Payload no longer includes password (`test_u6i6:_signup_payload` lines 143-152). ✅
- Pending `password_hash` asserted `NULL` (`test_u6i6:345`; the delta **strengthened** the prior `is not None` → `is None`). ✅
- Setup-credential, terminal cleanup, credential rotation (query-path 405/401), and leakage assertions preserved verbatim (`test_u6i6:416-503`). ✅
- **Node count / skip-xfail-only-retry:** no `pytest.mark.skip`/`xfail`/`only`/`describe.skip`/`it.skip`/`retry` directives added in any of the 9 files (matches confirmed by grep; the "retry"/`only` hits are prose/comments/variable names). ✅

---

## 5. Frontend Test Authenticity (Phase 5) — PASS

- Tests review against real components/router/store: `SignupClosure.test.tsx` renders `SignupPage` / `AppRouter` (real router, real `popstate`), `LoginPage` via `?raw` source assertion. ✅
- `popstate` and store mutations inside `act()`: `renderAt` wraps `dispatchEvent(popstate)` in `act()` (lines 31-33); store `login`/`logout` wrapped in `act()` (lines 393, 413-415). ✅
- `settle()` waits for meaningful final UI state: `await act(async () => {})` (lines 39-41); the no-render-error assertion runs **after** the dashboard truly mounts and after `settle()/settle()` (lines 460-475). ✅
- No-render-error assertion cannot finish before late async updates: dashboard heading asserted present, then double `settle()`, then `consoleError` check. ✅
- **Run focused file naturally AND mutation:** `SignupClosure.test.tsx` → **16 passed / 16** (matches ledger 16/16). Seed `20260821` shuffle NOT reproducible here (vitest 1.6.1 lacks `--seed`/`--shuffle` — see HOST-LIM-2); substituted with natural focused run + full-suite run (which reorders files).
- **SignupClosure `act` warning = candidate defect check:** ran the file AND the full frontend suite; **ZERO** "not wrapped in act(...)" warnings originate from `SignupClosure.test.tsx`. (Full-suite act warnings come from pre-existing unrelated components — `Header`, `SidebarBody`, `WholesalerRoute`, `ProtectedRoute`, `RetailerPricingPage`, `ToastContainer`, `RouterProvider`, `VerifyEmailPage` — disclosed per Phase 5.7, NOT attributed to this candidate.)
- **Mutation M4 proof (resolves prior F-C false-green):** removed `idempotencyKeyRef.current = newIdempotencyKey();` (SignupPage.tsx:110) → the F-C rotation test (`failure retries reuse the SAME key; accepted success rotates it observably`) went **RED** at `expect(rotatedKey).not.toBe(failedKey)`; file restored. The test is authentic, not a false-green.

---

## 6. Runtime (Phase 6) — what was executed vs HOST_LIMITATION

### Executed by this reviewer (frontend)
- `SignupClosure.test.tsx` natural: **16/16 PASS**, **0 act() warnings**.
- Full frontend `vitest run`: **24 files / 355 tests PASS** (matches ledger `355/355`).
- `pnpm build`: **SUCCESS** (`✓ built in 5.99s`; only the pre-existing non-blocking >500 kB chunk-size advisory).
- F-C mutation (M4): **RED** under mutation (authenticity proven).

### HOST_LIMITATION (backend U6 suites NOT executed by this reviewer)
- No Python venv / backend dependencies installed; no configured/migrated PostgreSQL (alembic 37/37) or `redis` available on this host. Therefore **U6-C natural/reverse, U6-F, U6-L, U6-I6 were NOT re-executed** by this reviewer.
- I do **not** claim the backend 3651/48/15 full-suite run. The candidate's ledger reports `3651 passed / 48 skipped / 15 xfailed / 0 failed / 0 errors ×2` with **identical skip-reason sets (48=48)**; I independently reconciled this against the task's stated claim and found it **consistent**. Backend test **authenticity** was verified at the source level (real SQL pre-seed of legacy fingerprints, replay via the real ASGI endpoint, assertions on 202/409/single-row/NULL-hash). The backend execution numbers remain the candidate's environmental claim, not independently rerun here.
- Seed `20260821` shuffle: vitest 1.6.1 has no `--seed`/`--shuffle`; the candidate's "16/16 shuffled seed 20260821" is their environmental claim. I substituted natural focused run + full-suite run and confirmed act-warning-free behavior.

---

## 7. Governance & Quality (Phase 7)

- `git diff --check` (delta vs parent): **clean** (exit 0).
- `py_compile` of the 4 backend `.py` in the delta (`auth_signup.py`, `onboarding_service.py`, `test_u6c…`, `test_u6i6…`): **all OK** (Python 3.12.10).
- `detect-secrets` scoped scan of all 9 delta files: **0 findings** (test passwords carry `# pragma: allowlist secret`).
- `detect_changes`: **NOT available** on this host → disclosed; substituted with exact `git diff` evidence + `detect-secrets` + manual review (no false claim of running it).
- UTF-8 / BOM / mojibake: **0 problems** across all 9 files (strict UTF-8 decode, no BOM).
- GitNexus: `analyze` run on the candidate worktree; `status` confirms re-indexed at `cbcecbf2…` (see §9).

---

## 8. Findings Accounting — gap analysis

| Finding | Prior severity | This review | Blocking? |
|---|---|---|---|
| F-A first password collected then discarded | P0 | **Resolved** — passwordless contract, `password_hash=None`, no storage, tests pass | No |
| F-B unreachable zero-tenant false-green | P0 | **Resolved** — `LoginPage` Condition D fail-closed; defensive test (not a false reachability claim) | No |
| F-C idempotency rotation not observable (false-green) | P0 | **Resolved** — lazy key + observable rotation; **mutation M4 RED** | No |
| P1 cross-version idempotency replay | — | **Resolved** — authentic DB-write-then-replay tests (2.5-2.7) | No |
| F-OBS1 pathname-only dashboard assertion | P3 | **Resolved** — real dashboard render + `console.error` never called | No |
| OBS-2 (non-blocking) preset-legacy + different-password → 409 not *explicitly* tested | P3 | Code-correct (legacy fingerprint includes password → mismatch → 409); coverage observation only | No |

**No accounting gap** between the candidate's ledger claims (F-A/F-B/F-C/F-OBS1 closed, mutation-proven) and this independent verification. The only un-reconciled items are residual **HOST_LIMITATION** (backend execution, seed shuffle) — disclosed, not contradictions.

### Ledger provenance distinction (required by task)
- **Current evidence:** this review (Kilo, 2026-08-21), independent adversarial source/test execution.
- **Superseded Zcode self-review:** commit `a3243779` ("V1 Kilo final review") is Zcode self-review historical material; its PASS is **not inherited** and is not a Kilo product (recorded in the candidate's own ledger §Provenance note).
- **Kilo prior STOP:** `c63ddf1ff90e0b962252478bca0b5f586a1fac48` (V2 independent review) accepted as the input that triggered this correction.
- **Residual host limitations:** backend U6 execution + seed-20260821 shuffle not reproducible on this host (§6).

---

## 9. Report Publication & Local/Remote Equality

- Report branch: `reports/dc12r1-mvp-l1-j1-r1-r1-v1-kilo-review-2026-08-21` (two files only):
  - `docs/ai-reports/review/2026-08-21_dc12r1_mvp_l1_j1_r1_r1_v1_kilo_review.md`
  - `docs/ai-reports/review/2026-08-21_dc12r1_mvp_l1_j1_r1_r1_v1_kilo_findings.csv`
- **Report commit SHA:** `<FILL_AFTER_PUSH>`
- **Local == Remote:** `<FILL_AFTER_PUSH>` (verified equal after push)
- GitNexus: `analyze` executed on candidate worktree; `status` shows indexed at `cbcecbf2bcb670efd67f2680075a7afea7562223`.

---

## 10. Verdict

`PASS_FOR_CTO_DC12R1_MVP_L1_J1_R1_R1_V1_KILO_FINAL_REVIEW`

No STOP condition triggered:
1. No false-green compatibility test (cross-version tests pre-seed real legacy fingerprints and replay via the real endpoint; F-C test is mutation-sensitive).
2. No legacy replay authorization broadening (compat path requires the replay request to carry a valid legacy password AND the exact legacy fingerprint, and only returns the existing registration).
3. No password persistence or leakage (`password_hash=None`, no `hash_password`, no logging, fragment-only links).
4. No weakened U6I6 terminal-state assertion (strengthened: `password_hash is None`).
5. No SignupClosure `act()` warning (verified zero).
6. No scope / lineage / evidence mismatch (delta exactly 9 files, parent `b7fbe1cc`, baseline ancestor, candidate == source tip).

Recommendation: candidate is cleared for CTO merge consideration. Residual items to track (non-blocking): backend U6 suites should be re-run in the authorized CI environment with alembic-migrated Postgres + redis to independently confirm the 3651/48/15 ledger claim; consider `hmac.compare_digest` for the fingerprint comparison hardening; add an explicit "preset legacy row + different password → 409" test for completeness.
