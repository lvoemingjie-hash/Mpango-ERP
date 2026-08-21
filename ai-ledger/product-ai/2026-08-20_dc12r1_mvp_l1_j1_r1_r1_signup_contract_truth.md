# DC-12R1-MVP-L1-J1-R1-R1 Signup Contract Truth Closure — Ledger Entry

- Date: 2026-08-20
- Owner: Zcode
- Authority: CTO
- Branch: `zcode/dc12r1-mvp-l1-j1-r1-r1-signup-contract-truth-2026-08-20`
- Base candidate: `b7fbe1cccb5e3b2dc4b9c6011dab17ad5db81fe7`
- Accepted Kilo STOP input: `c63ddf1ff90e0b962252478bca0b5f586a1fac48` (V2 independent review)
- Protected baseline: `fc8abdf327ae386c938541e847dabd786592af23` = `origin/product-dev-recovered`
- Provenance note: commit `a3243779` ("V1 Kilo final review") is Zcode self-review
  historical material only; its PASS is not inherited and it is not a Kilo product.

## Findings addressed (from c63ddf1f)

- **F-A (P0)** First password collected then discarded. Closed:
  - Backend `SignupRequest.password` → optional + deprecated (accepted for
    legacy clients, policy-validated when present, never stored).
  - `create_signup_registration` stores `password_hash=None`; `hash_password`
    removed from the signup path entirely; nullable column + terminal cleanup
    retained for historical rows (no migration).
  - `_request_fingerprint_hash` excludes the deprecated password: fingerprint
    is deterministic for passwordless requests; legacy replays with a
    different (discarded) password replay instead of 409. Exact tests:
    u6c `test_legacy_replay_with_different_password_same_key_is_not_a_conflict`,
    `test_fingerprint_deterministic_for_passwordless_and_legacy_payloads`.
  - Frontend signup page has no password field; accepted copy states the
    customer will SET the password after verification.
  - setup-credential remains the only creator of `users.password_hash`.
- **F-B (P0)** Unreachable zero-tenant "cold start" claim. Closed:
  - LoginPage Condition D is now a fail-closed defensive guard: neutral
    "Invalid credentials", stays on /login, persists nothing, never
    auto-navigates. Test replaced: the mock-only 200+[] "cold-start closure"
    test is deleted; a clearly-labeled defensive fail-closed test replaces
    it, and first-time entry is proven only via the login link + public
    /signup route.
  - `/onboarding/create-tenant` remains nonexistent (source assertion kept
    as supporting evidence).
- **F-C (P0)** Idempotency rotation never observable. Closed:
  - `useRef` key is lazily initialized (generator no longer runs on every
    render).
  - After an accepted success the key rotates and the accepted panel offers
    "Register another account", making rotation behaviorally observable:
    failure retry reuses the same key; post-restart submission uses a new
    key. Mutations M4 (delete rotation) and M5 (rotate on failure) are RED.
- **F-OBS1 (P3)** pathname-only dashboard assertion. Closed: single-tenant
  login test now mocks the four dashboard GETs, asserts the real dashboard
  heading renders, and asserts `console.error` was never called.

## Mutation accounting (all RED, all byte-clean restored, final suites GREEN)

- M1 restore signup password field/payload → RED (`NO password field` test).
- M2 store `password_hash` again on new registrations → RED (u6c
  `legacy_password_is_accepted_but_never_stored`).
- M3 restore zero-tenant auto-jump → RED (`fails closed` test).
- M4 delete accepted-success rotation → RED (`rotates it observably` test).
- M5 rotate on failure → RED (`failure retries reuse the SAME key`).
- M6 render raw backend/axios error → RED (`failure shows neutral copy only`).

## Out-of-scope STOP trigger (see report)

`backend/tests/test_u6i6_onboarding_e2e_closeout.py:343` asserts
`pending["password_hash"] is not None` — the exact pre-F-A behavior the CTO
mandate removes. The file is outside the authorized scope, so per §2 the run
stopped and reported instead of editing it.

## Runtime environment

- Task-exclusive `postgres:16` (16.14) on 127.0.0.1:15433 (stack 1) and a
  second fresh stack for the second full run; `redis:7-alpine` on 6391.
- No J1-R0 retained volumes, protected refs, or OpenCode artifacts touched.

## Final gate results (stacks: postgres:16 @15433/@15434, redis:7-alpine @6391/@6392, task-exclusive)

- U6-C: 14/14 natural order, 14/14 reverse order (also 6/6 on the
  passwordless/fingerprint subset); M2 mutation RED proof included.
- U6-F/L: 14/14. U6-I series: 63/64 — u6i6 fails (STOP trigger).
- Full backend run A (15433): 3198 passed / 82 failed / 426 errors — mass
  failures were missing-alembic-schema environmental errors (fresh DBs must
  be migrated first; REPORTING_USER_PASSWORD required).
- Full backend run B (15434, alembic-migrated 37/37): 3587 passed /
  12 failed / 182 errors. Failures: u6i6 (contract STOP trigger), u6i2
  (order-dependent flake — passes 14/14 in isolation), s4g migration-catalog
  (environmental), sporadic host-load singles. 182 errors concentrated in
  suites requiring explicit temporary-database opt-in env (statement print /
  declarations / real-alembic) — environmental on this host.
- Frontend: SignupClosure 16/16 natural + 16/16 shuffled seed 20260820;
  full vitest 355/355; tsc+vite build PASS.
- Real-server lifecycle (uvicorn + real SMTP sink + real provisioning):
  passwordless signup 202 -> password_hash IS NULL -> verify 200 ->
  provisioned active -> setup-credential 200 (replay 401) -> login 200 with
  THE password -> select-tenant 200 -> contextual /auth/me 200.
- Quality: py_compile, git diff --check, scoped pre-commit, detect-secrets
  (0 findings), strict UTF-8/no-BOM across all eight files.

## Verdict

STOP_AND_REPORT_CTO_DC12R1_MVP_L1_J1_R1_R1 — sole blocker is the
out-of-scope u6i6 assertion (file not in the authorized list). All F-A/F-B/
F-C/F-OBS1 work is complete, mutation-proven, and lifecycle-proven; the
branch is NOT pushed pending CTO scope decision on u6i6.

## Correction round (CTO STOP_AND_REQUIRE_J1_R1_R1_CORRECTION, 2026-08-21)

Scope extended by CTO: backend/tests/test_u6i6_onboarding_e2e_closeout.py added.

1. P1 cross-version idempotency: replay path now also accepts the
   pre-R1-R1 fingerprint format (password included) when the replaying
   request itself carries a legacy password
   (`_request_fingerprint_hash_with_password` retained solely for this
   compat check). Real cross-version tests added to u6c: DB rows are
   PRE-SEEDED with the legacy-format fingerprint via SQL, then replayed by
   the new code -> 202 replay / single row; a different payload under the
   same key still 409s.
2. u6i6 updated per authorization: signup payload no longer sends a
   password; pending registration asserts password_hash IS None; the
   setup-credential password-setting, terminal cleanup assertions, and all
   secret-leak assertions are preserved verbatim.
3. SignupClosure act() cleanup: router popstate dispatch wrapped in act(),
   store mutations act-wrapped, settle() flush at test ends; the dashboard
   no-render-error assertion now runs in the fully settled final state.
   File emits ZERO "not wrapped in act" warnings (verified by stderr grep).
4. Full-suite environment truth (why previous runs were red):
   - fresh stacks must be alembic-migrated (37 migrations) BEFORE tests,
     with REPORTING_USER_PASSWORD set;
   - temp-DB suites require MPANGO_ENV=test, MPANGO_ALLOW_TEMP_DB_CREATE=1,
     MPANGO_TEMP_DB_ALLOWED_PORTS=<port>, a `test_*`-named database and a
     non-mpango DB user (role `tester`, superuser for migration 011);
   - REDIS_URL must point at the task redis; pw1r3 additionally needs
     PW1R3_TEST_REDIS_URL.
   Full run A (stack 1) with the corrected env: 3650 passed / 48 skipped /
   15 xfailed / 0 errors; the single failure (pw1r3) was the missing
   PW1R3_TEST_REDIS_URL and passes 7/7 with it set; run A re-executed and
   run B (stack 2) recorded below.
5. Pre-existing, out-of-scope observation: S5BRealUserSmoke.test.tsx still
   emits 11 act warnings in the FULL frontend run (not from this delta's
   files; SignupClosure is warning-free).

## Final authoritative gate results (identical fresh-DB lifecycle per stack)

Both stacks: drop/create `test_r1r1_*` (owner `tester`), alembic 37/37,
redis flushed, identical env. Results:

- Stack 1 (PG16.14@15433 + redis7@6391): 3651 passed / 0 failed /
  0 errors / 48 skipped / 15 xfailed.
- Stack 2 (PG16.14@15434 + redis7@6392): 3651 passed / 0 failed /
  0 errors / 48 skipped / 15 xfailed.
- Skip reason sets compared with `diff`: IDENTICAL (48 = 48).
- Note: an earlier rerun on a REUSED stack-1 database showed 29 skips and
  one pre-existing flake (s5a journey gate) — both explained by DB-lifecycle
  state and host load, not by this delta; the authoritative runs above use
  the identical fresh lifecycle and are 0/0.

Frontend final: SignupClosure 16/16 natural + 16/16 shuffled seed 20260821,
ZERO act warnings in the file; full vitest 355/355; build PASS.
(11 act warnings in the full run originate from pre-existing
S5BRealUserSmoke.test.tsx, out of scope, unchanged.)
