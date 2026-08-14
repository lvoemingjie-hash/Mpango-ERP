# DC-12R1-MVP-L1-PW1-R2 — Auth Session State Closure (2026-08-14)

> ## VERDICT CORRECTION (PW1-R2-R1, 2026-08-14)
>
> The original PW1-R2 PASS verdict is **SUPERSEDED_BY_PW1_R2_R1_AUTHORIZATION_PRECEDENCE_CLOSURE**.
>
> Reason: PW1-R2 claimed the workspace completion used the contextual token
> explicitly (`authService.me(ctxTokens.access_token)`), but the shared axios
> request interceptor UNCONDITIONALLY overwrote every Authorization header with
> the store token — so `/auth/me` during selection actually flew with the
> identity token, and the committed user could be built from the identity-level
> `/auth/me` payload (tenant-less, permission-less). The "atomic contextual
> session" claim was therefore NOT closed at the HTTP layer.
>
> PW1-R2-R1 (same branch, later commit) closes this: the interceptor now
> preserves caller-provided Authorization and only injects the store token when
> the header is absent. See the PW1-R2-R1 section at the end of this ledger.

## Baseline & Branch

- Baseline: `d2e7e44cf23e91cabfab545c494abd342fec3062` (verified: worktree HEAD, 0 tracked mods pre-edit)
- Accepted evidence: PW1-R1 `d787c58ca85f05823fd4816e662c3db1f182dc92`; Kilo V1 `99a7c6fc4af0a058dcd1caa29f93c481bce0ef9d`
- Branch: `zcode/dc12r1-mvp-l1-pw1-r2-auth-session-closure-2026-08-14`
- Worktree: `C:\Users\Jeff0\pw1_r2_worktree` (isolated; frozen checkout untouched)

## Closed defects

- **D1 (PW1-R1, P1/stop-condition)**: a multi-tenant identity token written by the
  login page was mistaken by token-only route guards for a full authenticated
  session; the workspace selector never rendered and the pending session entered
  the wholesaler shell with 403s.
- **D2 (PW1-R1, P3)**: the owner login page displayed raw axios fallback text
  (`Request failed with status code 401`) instead of neutral copy for the flat
  structured error envelope.

## Exact file list (scope)

| File | Change |
|---|---|
| `frontend/src/stores/authStore.ts` | binding session contract: derived `sessionKind()` (contextual / pending-identity / anonymous — no stored booleans); new `beginWorkspaceSelection(identityTokens)` writing a pending session (user=null, tenantCode=null, portal context cleared); `updateTokens` documented as refresh-only |
| `frontend/src/router/guards.tsx` | `PublicRoute` redirects `/` only for contextual sessions (pending passes to complete the handoff); `ProtectedRoute` admits only contextual sessions (pending fails closed to `/login`); `WholesalerRoute` additionally fails closed on its own authority for `!user \|\| !accessToken` |
| `frontend/src/pages/auth/LoginPage.tsx` | multi-tenant branch calls `beginWorkspaceSelection` before navigating with `availableTenants` in router state; catch block shows fixed neutral copy (`Invalid credentials` for 401, fixed fallback otherwise) — no axios/backend message, request_id, body or code leakage |
| `frontend/src/pages/auth/WorkspaceSelectorPage.tsx` | atomic completion: select-tenant with explicit identity token → `me(ctxTokens.access_token)` → single `login(...)` commit; the pre-fix mid-flight `updateTokens` write is removed; failure keeps the pending session and stays retry-safe; neutral error copy |
| `frontend/src/tests/Pw1R2AuthSessionClosure.test.tsx` | NEW mandatory test suite (23 tests; real `<App />` + recording axios adapter + minimal guard harnesses) |
| `frontend/src/tests/SKUListPage.test.tsx` | 2-line type alignment only: the store mock objects gain `beginWorkspaceSelection: vi.fn()` required by the new `AuthActions` member. No semantic change; required for the mandatory `pnpm build` gate after the interface evolution. |

No other product file was touched (`git status` above is the complete change set).

## Phase 1 — Proof & impact

- `git fetch --all --prune` OK; isolated worktree at the exact baseline.
- GitNexus: repo indexed at baseline (15,118 nodes / 45,321 edges / 300 flows).
  Upstream `impact` saved per symbol (`pw1_r2_evidence/impact_*.json`). The
  graph models TS/TSX only at file level (JSX composition is not a call edge),
  so a grep-based direct-caller census was recorded as the authoritative caller
  inventory (`caller_census.md`): `useAuthStore` 187 refs/43 files;
  `updateTokens` production callers = api.ts refresh interceptor (preserved),
  LoginPage/WorkspaceSelectorPage (both replaced here).
- Pre-edit regression checklist saved (`regression_checklist.md`): 13 items
  covering auth routes, refresh, logout, retailer portal, D1/D2 closure criteria.
- Auth surface treated as CRITICAL regardless of graph counts.

## Guard semantics (binding contract, derived facts only)

```
contextual session:       accessToken != null AND user != null
pending identity session: accessToken != null AND user == null
anonymous:                accessToken == null (user-less token-less state)
```

## Mandatory tests (13/13)

Suite: `frontend/src/tests/Pw1R2AuthSessionClosure.test.tsx` — 23 tests, all
against the REAL `<App />` router tree with a recording axios adapter, plus
minimal MemoryRouter harnesses for the guard components themselves (fast RED
evidence without App-level redirect loops).

| # | Requirement | Result |
|---|---|---|
| M1 | multi-tenant login 200 → selector renders (real AppRouter) | PASS |
| M2 | zero dashboard API requests before selector render | PASS (log-asserted) |
| M3 | select-tenant 200 → me 200 (ordered) → workspace entry | PASS (log-ordered) |
| M4 | retailer_operator → `/client`; owner → `/` | PASS (both variants) |
| M5 | single-tenant owner + super_admin unregressed (retailer portal covered by existing `Dc12r1S2RetailerPortal` suite, green in full run) | PASS |
| M6 | pending session on protected routes fails closed, no shell, no business API | PASS |
| M7 | pending session NOT bounced off `/login` by PublicRoute | PASS |
| M8 | selector state lost on refresh → `/login`, never the shell | PASS |
| M9 | select-tenant/me failure → no contextual session, no business API, retry-safe | PASS (both failure points) |
| M10 | flat 401 / legacy envelope / malicious message → fixed neutral copy only | PASS |
| M11 | exactly ONE `POST /auth/login` per submit | PASS |
| M12 | mutation RED: token-only PublicRoute/ProtectedRoute restored → suite fails | RED captured (2 failures; full-App run additionally hangs in a `/`↔`/login` redirect ping-pong, itself proof the token-only judgment is unsafe) |
| M13 | mutation RED: mid-flight `updateTokens` restored → atomic-session test fails | RED captured (1 failure: contextual token committed before `me`) |

Evidence: `pw1_r2_evidence/mutations/M12_token_only_guards_RED.txt`,
`M13_midflight_updateTokens_RED.txt`; GREEN re-verified after each restore.

## Gates

1. Focused Vitest: **23/23 passed**.
2. Existing auth/route/retailer-portal suites green (included in full run).
3. Full `pnpm vitest run`: **21 files / 314 tests / 0 failed** (`full_vitest_run.txt`).
4. `pnpm build`: **exit 0** (after removing an unused test binding and the 2-line
   SKUListPage mock type alignment noted above).
5. PW1-R1 auth matrix on the real staging/JWT stack, aimed at this worktree's
   frontend (Vite :5174; deployment stack :5173/:8000 untouched): **9/9 passed**
   — including the former D1 red node (RA multi-tenant selector) and the former
   D2 red node (neutral `Invalid credentials` on owner 401). Only the auth
   matrix was run; the full 162-node PW1 was NOT claimed.
6. Scope: `git diff --check` clean; change set exactly as listed above.
7. Hygiene: detect-secrets 1.5.0 scan over all six changed files → **0 findings**
   (one initial false positive — a literal dummy test password — was renamed);
   mojibake scan → 0 replacement chars; all files strict UTF-8.
8. GitNexus pre-commit: CLI has no `detect_changes` command and the graph models
   these TS components at file level only, so the equivalent evidence is the
   baseline `impact` set + caller census + the behavioral gates above; recorded
   in `detect_changes_precommit.txt` (context query results: no process edges —
   documented limitation, not a silent pass).
9. Post-commit: `gitnexus analyze` re-run on the committed tree (see below).

## Stated deviations (for review honesty)

- `frontend/src/tests/SKUListPage.test.tsx`: 2-line mock type alignment (required
  by the new store action for the build gate; no behavioral change).
- The M12 mutation full-App run hangs in a redirect loop rather than failing
  cleanly; the minimal guard-harness subset provides the clean RED verdict.
- PW1-R1 evidence workspace gained one runner-variant config
  (`pw1r2-authmatrix.config.js`, baseURL → :5174) to aim the unchanged PW1-R1
  auth matrix at this worktree; no PW1-R1 test or original config was modified.

## Reproduction

- Real stack: staging backend (`MPANGO_ENV=staging`, JwtAuthStrategy) + this
  worktree's frontend on :5174; PW1-R1 identities (suffix `r1`) unchanged.
- `cd frontend && pnpm vitest run src/tests/Pw1R2AuthSessionClosure.test.tsx`

---

# PW1-R2-R1 — Explicit Authorization Precedence Closure (same branch)

## Scope (authorization-extended)

| File | Change |
|---|---|
| `frontend/src/services/api.ts` | request interceptor: caller-provided Authorization ALWAYS wins; store access token injected only when the header is absent. Refresh retry path unaffected (explicit refreshed header + store already updated). Dev logs still `[REDACTED]`. |
| `frontend/src/tests/Pw1R2AuthSessionClosure.test.tsx` | new "explicit Authorization precedence" suite (3 tests) + adapters now token-gated; also gates the raw global axios used by the api.ts refresh bypass |
| ledger (this file) | R2 verdict superseded (above) |
| `pw1r2-evidence/` | replacement evidence (impact, mutations, gates) |

## Fix contract verification

1. Interceptor impact: GitNexus has no symbol for the anonymous interceptor
   closure (documented in `pw1r2-evidence/impact_api_interceptor.md` with the
   full grep census: every shared-instance consumer).
2-3. Explicit Authorization preserved; store token injected only when absent —
   proven by token-gated adapters (below) and mutation RED.
4. No URL/query/log/global-variable token transport; dev log remains `[REDACTED]`.
5. Verified in run output.
6. Refresh retry uses the refreshed token (dedicated test; stale->401, refresh,
   retry->200 only with `Bearer refreshed-token`).
7. R2 session-state contract unchanged (R2 suite still green, 26/26 incl. R2 tests).

## Authenticity tests (three distinct in-memory tokens)

`identity-token` / `contextual-token` / `refreshed-token`:

- `/auth/select-tenant` adapter asserts `Authorization == Bearer identity-token` (else 401)
- `/auth/me` adapter asserts `Authorization == Bearer contextual-token` (else 401)
- post-completion business requests assert `Bearer contextual-token`
- token-gated adapters return real 401s on any wrong token (path alone cannot green)
- `/auth/me` body contract: `tenant_id` == selected tenant, `tenant_schema`
  non-empty, `permissions` == the selected tenant's exact permission list
- committed `mpango-auth.user`: tenant_id/tenant_schema/permissions asserted (not just role/URL)
- refresh test: no explicit header -> store token; retry -> refreshed token

## Mutation RED (both restored and re-verified GREEN afterwards)

- **R1-MUT-A** (unconditional overwrite restored): contextual `/auth/me` test
  fails — me flies with the store identity token, gating 401s, flow never completes.
- **R1-MUT-B** (explicit contextual token removed from the selector's me call):
  same test fails — store identity token reaches me, 401, no completion.
- Evidence: `pw1r2-evidence/mutations/R1_MUT_{A,B}_*_RED.txt`

## Gates

1. Focused Vitest: **26/26** (R2 23 + R1 3).
2. Full `pnpm vitest run`: **21 files / 317 tests / 0 failed**.
3. `pnpm build`: exit 0.
4. Real staging/JWT PW1-R1 auth matrix (worktree frontend :5174, unchanged
   PW1-R1 tests/config): **9/9**.
5. Browser in-memory comparison (real run, staging): select-tenant response
   token vs `/auth/me` Authorization → **MATCH** (result file records MATCH
   only; no token values anywhere).
6. Final `mpango-auth.user`: `tenant_id` == selected tenant, `tenant_schema`
   non-empty, `permissions` count 6 (formally provisioned retailer_operator),
   `tenantCode` == selected code → PASS.
7. `git diff --check` clean; detect-secrets 0 findings; mojibake 0.
8. Interceptor impact analysis recorded (GitNexus limitation + grep census).
9. Full 162-node PW1 NOT run (awaiting Kilo).
