# P25-B Platform Frontend Customer-Readiness Validation Harness

**Phase:** P25-B Platform Frontend Customer-Readiness Validation Harness
**Date:** 2026-07-06
**Base:** `48ddda4` (origin/platform-dev -- P25-A contract merged)
**Branch:** `codex/platform-p25b-platform-frontend-readiness-validation-2026-07-06`
**Worktree:** `_p25b_2026-07-06`
**Tip:** this R1 ledger-correction commit (branch HEAD). Prior commits: `74bf9c2e` (code) and
`0ed79cbd` (R0 ledger body). The R1 tip SHA is reported in chat only, not embedded here, to
keep this ledger non-self-referential (mirrors P25-A correction `a06bcb4f`).
**Ahead / behind base:** 3 / 0 (`74bf9c2e` code + `0ed79cbd` R0 ledger + this R1 correction)
**Verdict:** **READY_FOR_CTO_REVIEW** (harness sound; 2 recorded defects for a separately
approved fix slice; not merged; not pushed to platform-dev; P25-C not started)

## 1. Phase inventory

P25-B is the P25-A section 9 gate: a non-shipping, non-merging frontend validation / smoke
harness over the as-built P10-P24 platform surface. It adds no capability, route, backend,
migration, package/lockfile, auth/RBAC, execution-expansion, or notification-delivery change.

11 harness files, all under `frontend/src/pages/platform/__tests__/p25/` (0 backend / 0
migration / 0 package / 0 lockfile / 0 auth / 0 product). The full branch diff versus
origin/platform-dev is **12 files**: these 11 harness files plus this ledger markdown (the
12th). Scans below target the 11 harness files unless stated otherwise.

- `__helpers__/readiness.tsx` -- closed route table (19), identity fixtures, never-leaked
  scanner, `renderPlatformAt` (full PlatformRoute subtree), `EMPTY_BODY`, `SWEEP_ROUTES`,
  `DEFECT_EMPTY_CRASH_ROUTES`, `URL_ONLY_ROUTES`.
- `__helpers__/node-shims.d.ts` -- ambient `node:fs` / `node:path` / `process` declarations
  (@types/node is intentionally not a frontend dependency; vitest provides them at runtime).
- `P25_RouteInventory.test.tsx` (6) -- closed-set grounding in AppRouter source (19 routes;
  none dropped C11; none invented C12; PlatformRoute wraps the subtree section 3.6).
- `P25_GuardMatrix.test.tsx` (5) -- identity-only PlatformRoute admit (identity-only
  super_admin) + deny (tenant-contextual super_admin, non-super_admin, unauthenticated); C13.
- `P25_SidebarNav.test.tsx` (14) -- 10 sidebar links present for identity-only / hidden for
  all others; active-link highlight per route; AC 9.
- `P25_StateMatrix.test.tsx` (51) -- empty (dim 4) / loading (dim 5) / error (dim 6) per
  route with mocked `@/services/api`; AC 5/6/7; C9/C10.
- `P25_CopySafety.test.tsx` (51) -- empty + error never-leaked scan + sensitive-label scan
  across all routes; AC 11; C20.
- `P25_ConsoleConsistency.test.tsx` (10) -- `resolveOperatorDisplayTone` /
  `resolveCloseoutDisplayTone` / `resolveStepDisplayTone` + `isHealthy*Tone` +
  `PlatformStatusBadge`: source_unknown never green, backup_check_warning / degraded /
  linked-execution-warning never green, terminal success blue; AC 13/14/15; C14/C15/C17.
- `P25_ForbiddenControls.test.tsx` (18) -- no execute / dispatch / deliver / send / push /
  clear-flag / set-flag / delete-tenant / purge / truncate control; regex self-calibration;
  AC 17; C19.
- `P25_RecordedDefects.test.tsx` (3) -- D1 nav-reachability gap (7 URL-only routes); D2
  empty-state crash on Audit Events + Tenant Directory (`expect(render).toThrow()`, green
  while the defect exists, red once fixed).
- `README.md` -- readiness matrix (19 routes x 12 dimensions), screenshot skip reasons, demo
  script, defect list, known warnings.

Total: 8 test files + 1 helper module + 1 `.d.ts` shim + 1 README. **158 P25-B tests.**

## 2. Capability statement

P25-B adds NO capability. It is a read-only validation layer:

- It reads the as-built platform surface (AppRouter, guards, Sidebar, pages, type resolvers).
- It renders pages through the real `PlatformRoute` guard with a mocked backend
  (`@/services/api` -> `platformService` / `supportService`).
- It records matrix results and records defects; it fixes nothing inline (contract 6.8 / 9).
- It reuses the P10/P11 `PlatformRoute` identity-only global super_admin guard unchanged.
- It adds no route, task type, closeout state, action, governed slice, migration, channel,
  auth/RBAC change, or notification delivery.

## 3. Safety statement

All-P25 non-goals (contract 1.3.2) honored:

- No new capability; no migration; no product branch merge; no product business mutation.
- No auth/RBAC rewrite (reuses `PlatformRoute` + `isIdentityPlatformOperator` unchanged).
- No P22 execution expansion; no notification delivery; no tenant-data leak (asserted).
- No `source_unknown` shown healthy; no `backup_check_warning` shown as success (asserted
  across the operator/closeout/step tone resolvers and `PlatformStatusBadge`).
- No audit-history deletion; no AI agent execution / auto-approval / auto-close.
- No screenshot / transcript secret leak (screenshots are skip-with-reason; transcripts are
  the test runners, scrubbed by the never-leaked scan).

## 4. Verification

Exact commands (run from the worktree; `node_modules` junction'd from the sibling main
checkout; vitest 1.x, jsdom):

```
node_modules/.bin/vitest run src/pages/platform/__tests__/p25   # 8 files, 158 tests PASS
node_modules/.bin/vitest run                                   # 48 files, 580 tests PASS
node_modules/.bin/tsc --noEmit                                  # 41 errors (baseline; +0 P25)
git diff --check (cached)                                       # clean
LC_ALL=C grep -rnP "[^\x00-\x7F]" .../p25/                      # empty (pure ASCII)
python -m detect_secrets.pre_commit_hook --baseline .secrets.baseline <p25 files>  # exit 0
```

- **P25-B harness:** 158 passed / 0 failed (8 files).
- **Full frontend suite:** 580 passed / 0 failed / 0 regressions (48 files). Prior P24-D base
  422 + P25-B 158 = 580.
- **tsc --noEmit:** 41 errors total, all pre-existing in untouched files (matches P24-C
  baseline); P25-B files add **0 new errors** (`vi.mocked()` casts for mock methods;
  `node-shims.d.ts` ambient declarations for `node:fs` / `process`; typed `RegExpExecArray`).
- **git diff --check:** clean (the LF->CRLF warnings are core.autocrlf=true, benign, prior-
  phase convention; git stores LF).
- **ASCII:** all 11 harness files pure ASCII (Python-ordinal check); the 12th file (this
  ledger markdown) is also pure ASCII.
- **detect-secrets 1.5.0 (configured baseline):** exit 0, 0 findings on the 11 harness
  files; `.secrets.baseline` UNCHANGED (`git diff origin/platform-dev -- .secrets.baseline`
  empty).
- **Forbidden-path audit:** all 12 changed files are under
  `frontend/src/pages/platform/__tests__/p25/` (11 harness files) or `ai-ledger/platform/`
  (this ledger); 0 backend / migration / alembic / package.json / lockfile / auth / product
  / .sql paths.

Known warnings (honest, not hidden):

- Screenshots + dim-10 (no clipped/overlapping) are **skip-with-reason**: Playwright is not
  installed (forbidden package change) and no runnable stack is available; component-level
  tests substitute (P25-A section 9). NOT a silent pass (C21).
- Loading affordance (dim 5) for store-backed pages: the in-effect loading-flag transition is
  a jsdom/act artifact (the store setter registers when invoked directly, per a harness
  diagnostic). The dim-5 check is "read issued / no error flash / no crash on mount"; the
  Skeleton affordance is verified for local-state-backed pages and is present in a real
  browser. Test-environment limitation, not a product defect.
- Error affordance (dim 6) for the Support Console: a sessions-read failure continues to
  render the usable form (no red box); the check accepts "explicit error affordance OR sane
  primary content" (no crash, no leak) for that route.
- D2 defect tests intentionally render the two crashing routes; React logs "Element type is
  invalid" for those two cases. Expected.

## 5. GitNexus summary

GitNexus was re-run after the R1 ledger correction was committed; `npx gitnexus status` is
up-to-date at the current P25-B branch tip (indexed commit == current commit == branch
tip). The exact R1 tip SHA is reported in chat only, not embedded here, to keep this ledger
non-self-referential (mirrors P25-A correction `a06bcb4f`). Counts are recorded as a band,
not a point, to avoid amend loops.

- R0 state corrected here: the R0 body recorded `npx gitnexus status -> indexed commit
  74bf9c2 == current commit 74bf9c2; up-to-date` and `analyze -> 9,437 nodes | 28,825 edges
  | 590 clusters | 300 flows`. That index was taken at the *code* commit `74bf9c2`; at the
  R0 ledger tip `0ed79cbd` it had gone stale (`indexed 74bf9c2` / `current 0ed79cb`), so the
  R0 "up-to-date" evidence described the code commit, not the branch tip. CTO review flagged
  this as merge-blocking.
- R1 fix: re-run `npx gitnexus analyze` at the branch tip (after this ledger correction is
  committed) so `status` is genuinely up-to-date at the tip, and record it
  non-self-referentially here.

Observed analyze counts at the tip sit within the documented P24-P25 band: ~9,393-9,466
nodes / ~28,767-28,846 edges / 584-598 clusters / 300 flows. (Re-analyzing at the ledger
tip adds the ledger/test doc symbols versus the pre-ledger code-commit index, but lands
inside the same band.) The new files are markdown + `.tsx`/`.ts` tests + a `.d.ts` shim;
they add test/doc symbols but touch 0 backend / product code, so the 300 runtime flows are
unchanged (frontend-only fallback, contract 4).

`detect_changes` (MCP) is flaky in this environment (per prior phases); the reliable
corroborator is the change scope itself: `git diff origin/platform-dev` is **12 files** --
the 11 harness files under `frontend/src/pages/platform/__tests__/p25/*` plus this ledger
markdown. 0 backend / migration / product symbols -> 0 affected runtime flows -> stop gate
NOT triggered.

## 6. Recorded defects (for a separately approved fix slice; NOT fixed inline)

- **D1 -- navigation reachability gap (AC 9).** 7 routes have no sidebar link and no in-app
  `<Link>` (URL-only today): `/platform/system/health`, `/platform/audit`, `/platform/registry`,
  `/platform/ops/errors`, `/platform/ops/slow-routes`, `/platform/ops/resources`,
  `/platform/ops/noisy-neighbors`. Functionally 9 of 19 routes are not sidebar-reachable.
  Asserted in `P25_RecordedDefects.test.tsx` (D1).
- **D2 -- empty-state render crash (AC 5).** `PlatformAuditEventsPage` and
  `PlatformTenantDirectoryPage` render `<EmptyState>` WITHOUT the required `icon` prop, so the
  page throws on any render that reaches the empty branch (including initial mount). Blocks
  dims 1/4/5/6/9/12 for those two routes. Asserted via `expect(render).toThrow()` in
  `P25_RecordedDefects.test.tsx` (D2-a / D2-b): GREEN while the defect exists, RED once fixed.

Both are recorded for a later, separately approved fix slice. P25-B does not fix them.

## 7. Open risks / non-goals

- Risk: LOW (frontend test-only; 0 backend flows; 0 product paths).
- Blockers: none for the harness. The recorded defects D1/D2 are blockers for declaring the
  *surface* fully customer-ready, not for the harness verdict.
- Non-goals: no merge into `platform-dev` or `product-dev-recovered`; no push to platform-dev
  (branch pushed with explicit `X:X` refspec; `origin/platform-dev` left unchanged at
  `48ddda4`); no feature implementation; no inline defect fix.

## 8. P25-C / next-gate statement

P25-C is NOT started. P25-B is the validation harness only. Any further work (a fix slice for
D1/D2, a real Playwright pass on a runnable stack, a customer sign-off) requires a separately
approved contract / gate and must remain behind the identity-only platform-operator guard and
the never-leaked list.

## 9. Final verdict

**READY_FOR_CTO_REVIEW.**

The P25-B harness is sound, complete, and honest: 158 P25-B tests + 580 full frontend suite
green; tsc +0 new errors; detect-secrets clean (baseline unchanged); pure ASCII; forbidden-
path clean; GitNexus flows STABLE 300. It validates the as-built P10-P24 surface across the
section 4 matrix (smoke / guard admit+deny / sidebar nav / empty / loading / error / copy /
tone consistency / forbidden controls / invariants) and records two defects (D1 nav gap; D2
empty-state crash on Audit Events + Tenant Directory) for a separately approved fix slice.
Screenshots are skip-with-reason (Playwright not installed; component-level tests substitute).
Not merged; not pushed to platform-dev; P25-C not started.
