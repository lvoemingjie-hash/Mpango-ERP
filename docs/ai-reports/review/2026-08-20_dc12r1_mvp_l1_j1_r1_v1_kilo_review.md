# DC-12R1-MVP-L1-J1-R1-V1 Kilo Final Bounded Source Review

- **Reviewer:** Kilo (adversarial source/test-authenticity review)
- **Authority:** CTO
- **Date:** 2026-08-20
- **Candidate:** `b7fbe1cccb5e3b2dc4b9c6011dab17ad5db81fe7`
- **Source branch:** `zcode/dc12r1-mvp-l1-j1-r1-wholesaler-signup-closure-2026-08-20`
- **Frozen parent / protected baseline:** `fc8abdf327ae386c938541e847dabd786592af23`

## Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_J1_R1_V1_KILO_FINAL_REVIEW**

Counts: **P0=0, P1=0, P2=1, P3=3, INFO=3 — accounting gap = 0** (7 findings,
all classified in the CSV; no unclassified observation remains open).

---

## Phase 1 — Proof Gate (all PASS)

| Check | Result |
|---|---|
| `git fetch --all --prune` | OK |
| Detached review worktree at exact candidate SHA | OK (`_kilo_j1r1_v1_review_2026-08-20`) |
| Remote source branch == candidate | PASS — `origin/zcode/...2026-08-20` resolves to `b7fbe1cc` |
| `candidate^` == `fc8abdf3` | PASS (verified via `git cat-file -p`) |
| `fc8abdf3` == current `origin/product-dev-recovered` | PASS |
| Delta is exactly the six expected files | PASS — `git diff --name-only` returns exactly the six files, +838/−2 |
| Backend/migration/dependency/lockfile/config/deploy/pricing/barcode/retained-J1-runtime changes | NONE present |

## Phase 2 — Backend Contract Truth (independently verified against source, not comments)

Verified against `backend/schemas/auth_signup.py`, `backend/api/v1/auth.py`,
`backend/services/onboarding_service.py`, `backend/services/email_delivery.py`:

- **Field names/aliases:** `companyName` (alias, 2–255), `country` (exactly 2,
  normalized upper), `email` (EmailStr, lower), `password` (8–128),
  `phone` (optional ≤32), `businessType` (alias, optional ≤64).
  `ConfigDict(populate_by_name=True)` genuinely accepts camelCase — the
  frontend payload is accepted as-is (also proven live by Zcode's 202/lifecycle
  run and my regression run below). MATCH.
- **Status/envelope:** 202, `registrationId: null`, `status:
  "pending_email_verification"`, neutral `NEUTRAL_SIGNUP_MESSAGE`. MATCH.
- **Idempotency-Key semantics:** header-based; same key + same fingerprint →
  replay of existing registration; same key + different payload → 409
  `IDEMPOTENCY_CONFLICT`; key absent → normal flow. Frontend behavior (stable
  on failure, rotate after accepted success) is replay-safe under exactly
  these semantics. MATCH.
- **Anti-enumeration:** an existing live registration for the same email
  returns the identical neutral 202 with `registrationId: None` — no duplicate
  registration, no existence disclosure. MATCH.
- **Lifecycle:** verify-email (fragment token) → provisioning + owner
  setup-credential email (fragment token) → setup-credential → login →
  select-tenant → contextual /auth/me. The candidate's accepted-state copy and
  non-navigation match this lifecycle. MATCH.

## Phase 3 — Journey Semantics

1. Anonymous discovery of `/signup`: PASS (public route under `PublicRoute`;
   real-router test + login entry link + behavioral test).
2. No guard interception/redirect loop: PASS — `PublicRoute` only redirects a
   *contextual* session; anonymous and pending-identity sessions pass through.
3. Contextual sessions fail closed on public routes: PASS (test
   `anonymous visitor can reach /signup but a contextual session is
   redirected` + existing guard suite).
4. Login no longer reaches `/onboarding/create-tenant`: PASS (behavioral
   cold-start test + raw-source assertion as supporting evidence only).
5. **Zero-tenant redirect semantics** — adversarial analysis (see P3-01):
   - Re-registering the same email is SAFE against enumeration (neutral 202)
     and creates no duplicate while a live registration exists.
   - For an *established* zero-tenant identity (edge state; provisioning
     normally always yields a tenant), a fresh signup would create a new
     registration whose verify path provisions/reconciles — no crash, no
     idempotency burn, no account takeover. The redirect is defensible but is
     a judgment call; a dedicated "no workspace yet" state would be cleaner
     long-term. **Not blocking** — the dead route removal was mandated and
     `/signup` is the only live self-service entry.
6. **Signup password vs setup-credential password** (P2-01): the backend
   contract itself stores a password hash at signup AND issues a
   setup-credential (second password) later. The candidate is mandated to
   reuse the contract *exactly* and does; the duplication is
   contract-inherited, not introduced. Disclosed to CTO as the single P2.
7. Single-tenant and multi-tenant login paths: PASS — diff shows Condition D
   and the entry link only; single-tenant auto-select regression test GREEN;
   existing auth/session bundle (60 tests) GREEN.

## Phase 4 — Secret and Error Boundary (all PASS)

- No access/refresh/setup/verification token enters storage, URL, logs or UI
  (the 202 carries none; page writes nothing — proven by storage spy test and
  mutation M6).
- Password never logged or reflected (masked input; no echo anywhere).
- Raw axios/backend message, code, request_id, body never render (fixed
  neutral copy; proven by leak test + mutation M5).
- Accepted response is neutral, does not disclose account existence.
- Idempotency-Key carries no user data (UUID only).
- Fallback key generation (`Date.now()-random` only when
  `crypto.randomUUID` unavailable): no user data; collision probability
  negligible for its purpose; backend treats it as opaque (P3-03, non-blocking).

## Phase 5 — Test Authenticity

- **Real wiring where claimed:** `SignupClosure.test.tsx` mounts the REAL
  `AppRouter` (real `createBrowserRouter`) for route/guard/cold-start/login
  tests; the axios singleton layer is mocked (unavoidable in jsdom) but the
  asserted wire format (path, camelCase payload, header) is exact.
- **No mock-only substitute for routing:** routing is behavioral (click → URL
  → rendered page), including the cold-start zero-tenant navigation.
- **No skip/xfail/only/conditional/retry markers:** grep-clean.
- **No weakened existing assertion:** candidate touches no existing test;
  existing suites re-run GREEN unchanged.
- **Singleton router state:** `createBrowserRouter` is module-singleton; the
  suite resets history and dispatches popstate per test. Order independence
  demonstrated by fixed-seed shuffle GREEN (two different seeds: 20260820 by
  Zcode, 777 by Kilo).
- **Raw-source assertion** is supporting evidence only; behavioral cold-start
  test is the primary proof.
- **Mutation matrix — all 8 required mutations executed by Kilo in the
  detached review worktree, each RED on the intended test, each restored
  byte-clean (`git status` empty afterwards), final suite GREEN 15/15:**

  | # | Mutation | Intended test | Result |
  |---|---|---|---|
  | M1 | Remove `/signup` route | mounts /signup without 404 | RED ✔ |
  | M2 | Restore dead onboarding route | cold-start branch | RED ✔ |
  | M3 | Remove login signup link | signup entry link | RED ✔ |
  | M4 | Rotate idempotency key on failure | failure keeps key stable | RED ✔ |
  | M5 | Render raw backend error | failure keeps key stable / leak assertions | RED ✔ |
  | M6 | Persist signup token-like data | persists nothing | RED ✔ |
  | M7 | Alter required payload field | payload + Idempotency-Key contract | RED ✔ |
  | M8 | Break zero-tenant routing | cold-start branch | RED ✔ |

## Phase 6 — Runtime Gates (Kilo host)

| Gate | Result |
|---|---|
| Focused suite, natural order | 15/15 PASS |
| Focused suite, shuffled seed 777 | 15/15 PASS |
| Existing auth/session/router regression bundle | 60/60 PASS |
| Full `pnpm vitest run` | 354/354 PASS (24 files) |
| `pnpm build` (tsc + vite) | PASS |
| `git diff --check` | clean |
| Scoped pre-commit | all hooks PASS |
| detect-secrets (scoped to six files) | 0 findings |
| Strict UTF-8 / no BOM / no mojibake | PASS (byte-level decode, BOM check) |
| GitNexus analyze/status | indexed at `b7fbe1c`, up-to-date, exact 6-file scope confirmed |

**Host limitation disclosure (not a candidate defect):** this reviewer host's
in-app browser backend cannot dispatch form-submit events (button/Enter do
nothing, including on the pre-existing LoginPage), so no browser-driven
form-submission claim is made here. Zcode disclosed the same limitation and
substituted: real-browser render + link-navigation evidence plus an
API-complete lifecycle through the identical vite proxy. Consistent and
honestly reported; no manufactured PASS detected.

## Phase 7 — Evidence Truth reconciliation

- **Genuine source closure (verified in source, not comments):** public
  `/signup` route, login entry link, dead-route removal, idempotency
  semantics, neutral error/success copy, no token persistence, no backend
  changes.
- **Test-only assertion vs behavior:** all critical claims have behavioral
  tests; the raw-source check is explicitly supporting-only.
- **Reviewer-host limitation:** browser form submission (above); disclosed,
  substituted, non-blocking.
- **Zcode claim reconciliation:** Zcode's commit-message gate claims
  (15/15 ×2, 354/354, build, 51/51 backend regression, detect-secrets,
  pre-commit, UTF-8) were independently re-executed on this host and
  reproduced, except backend contract regression which Kilo verified through
  direct source reading + Zcode's live-run logs rather than a full DB-backed
  re-run (DB harness available on this host was not re-provisioned to avoid
  touching shared state). The contract reading is unambiguous and the live
  evidence was internally consistent. Classified as evidence-truth note, not
  a gap: the single P2 and the P3/INFO items below carry all residual risk.
- **Merge blockers:** none (P0=0, P1=0).

## Findings summary

- **P2-01** Duplicate password UX: signup password + later setup-credential
  password. Contract-inherited (backend U6-C design); candidate mandated to
  reuse the contract exactly. Recommend CTO schedule a contract-level
  decision (out of J1-R1 scope).
- **P3-01** Zero-tenant identity → `/signup` redirect is semantically safe
  (no enumeration, no duplicate registration, no idempotency burn) but
  architecturally blunt; a dedicated no-workspace state would be cleaner.
- **P3-02** Frontend validation is intentionally stricter than backend
  (country letters-only, frontend trims); fail-closed, benign.
- **P3-03** Fallback idempotency key generator has lower entropy than UUIDv4
  but only activates when `crypto.randomUUID` is unavailable; no user data;
  opaque to backend.
- **INFO-01** Axios-layer mock in tests is a jsdom necessity; mitigated by
  exact wire-format assertions + real AppRouter mounting + backend source
  truth.
- **INFO-02** Test asserts UUID shape for Idempotency-Key; backend accepts
  any opaque string, so the assertion is tighter than the contract (safe).
- **INFO-03** Browser form-submission could not be driven on either host;
  substituted evidence accepted as disclosed.

**Accounting: P0=0, P1=0, P2=1, P3=3, INFO=3. Total 7. Gap = 0.**
