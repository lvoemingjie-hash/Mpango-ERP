# P25-C Platform Frontend Customer-Readiness Defect Fix

**Phase:** P25-C Platform Frontend Customer-Readiness Defect Fix Slice
**Date:** 2026-07-06
**Base:** `5687e7d4` (origin/platform-dev -- P25-B validation harness merged)
**Branch:** `codex/platform-p25c-customer-readiness-defect-fix-2026-07-06`
**Worktree:** `_p25c_2026-07-06`
**Tip:** reported in chat only (this ledger stays non-self-referential, mirroring P25-A/B/C/D
ledger convention). Code commit + ledger commit are reported in chat.
**Verdict:** **READY_FOR_CTO_REVIEW** (frontend-only fix slice; both recorded defects
resolved; not merged; not pushed to platform-dev; P25-D / customer signoff not started)

## 1. Phase inventory

P25-C is the separately approved fix slice for the two customer-readiness defects that P25-B
*recorded* and deliberately did not fix (contract section 6.8 / section 9). It is frontend-only:
no backend, no migration, no package/lockfile, no auth/RBAC/session rewrite, no
product-dev-recovered, no product business path. It adds NO platform capability -- only
render-safety (an icon prop) and navigation (restrained in-app hub links).

7 changed files, all under `frontend/src/`:

- `pages/platform/PlatformAuditEventsPage.tsx` -- import `ClipboardDocumentListIcon`; pass the
  required `icon` prop to `<EmptyState>` (D2).
- `pages/platform/PlatformTenantDirectoryPage.tsx` -- import `BuildingOfficeIcon`; pass the
  required `icon` prop to `<EmptyState>` (D2).
- `pages/platform/PlatformOverviewPage.tsx` -- add a "Platform Pages" hub section with
  `<Link>`s to System Health, Tenant Directory, Audit Events, Registry (D1, the 4 non-ops
  URL-only routes).
- `pages/platform/ops/OpsHealthPage.tsx` -- add an "Operations Views" hub section with
  `<Link>`s to Ops Errors, Slow Routes, Resources, Noisy Neighbors (D1, the 4 ops URL-only
  routes).
- `pages/platform/__tests__/p25/__helpers__/readiness.tsx` -- `SWEEP_ROUTES` is now all 19
  (D2 resolved); `URL_ONLY_ROUTES` is computed by a source reachability scan (empty when every
  route is Sidebar-linked or in-app `<Link>`-linked); the unused `DEFECT_EMPTY_CRASH_ROUTES` /
  `DEFECT_D2_PATHS` were removed; `routeIsReachable` is exported for the D1 guard test.
- `pages/platform/__tests__/p25/P25_RecordedDefects.test.tsx` -- reshaped from 3
  "expect-throw" / "expect-7-URL-only" defect assertions into 4 resolution GUARDS: D2-a/D2-b
  assert the empty branch renders the empty copy (no throw); D1-a/D1-b assert no route is
  URL-only and every route is reachable. GREEN while the fix holds; RED the moment a defect
  regresses.
- `pages/platform/__tests__/p25/README.md` -- matrix table flipped (D1/D2 cells -> PASS; all
  19 routes READY); "Recorded defects" section -> "Resolved defects (P25-C)"; counts updated
  (158 -> 173 P25, 580 -> 595 full); demo script + warnings updated.

0 backend / migration / alembic / package.json / lockfile / auth / product / .sql paths.

## 2. Capability statement

P25-C adds NO capability. It is render-safety + navigation over the as-built P10-P24 surface:

- D2: two pages already used `<EmptyState>`; they now pass its (already-required) `icon` prop.
  No new component, no `EmptyState` API change (the `icon` prop was already non-optional), no
  new state, no new read, no new write.
- D1: two existing hub pages (Platform Overview, Ops Cockpit) gain navigation `<Link>` grids to
  existing as-built routes. No new route, task type, closeout state, action, governed slice,
  migration, channel, auth/RBAC change, execution expansion, or notification delivery.
- It reuses the P10/P11 `PlatformRoute` identity-only global super_admin guard unchanged. It
  reuses the existing heroicons dependency unchanged.

## 3. Safety statement

All-P25 non-goals (contract 1.3.2) honored:

- No new capability; no migration; no product branch merge; no product business mutation.
- No auth/RBAC rewrite (reuses `PlatformRoute` + `isIdentityPlatformOperator` unchanged).
- No P22 execution expansion; no notification delivery; no tenant-data leak (the never-leaked
  sweep now covers Audit Events + Tenant Directory too).
- No `source_unknown` shown healthy; no `backup_check_warning` shown as success (unchanged tone
  resolvers).
- No audit-history deletion; no AI agent execution / auto-approval / auto-close.
- No screenshot / transcript secret leak (screenshots remain skip-with-reason; the never-leaked
  scan covers the two formerly-D2 routes).

## 4. Verification

Exact commands (run from the worktree; `node_modules` junction'd from the sibling main
checkout; vitest 1.x, jsdom):

```
node_modules/.bin/vitest run src/pages/platform/__tests__/p25   # 8 files, 173 tests PASS
node_modules/.bin/vitest run                                   # 48 files, 595 tests PASS
node_modules/.bin/tsc --noEmit                                  # 39 errors (base 41; P25-C +0 new)
git diff --check origin/platform-dev                            # clean
python -m detect_secrets.pre_commit_hook --baseline .secrets.baseline <7 files>  # exit 0
```

- **P25 harness:** 173 passed / 0 failed (8 files). Was 158 in P25-B; +15 = the 2 D2 routes
  rejoining the state/copy/forbidden sweeps (+6 state, +6 copy, +2 forbidden) and the
  recorded-defect file reshaping 3 -> 4 (+1 net).
- **Full frontend suite:** 595 passed / 0 failed / 0 regressions (48 files). Prior P25-B base
  580 + 15 = 595.
- **tsc --noEmit:** 39 errors total. Normalized diff versus base (`5687e7d4`): **+0 new**, and
  the 2 errors that disappeared are *exactly* the D2 defects themselves
  (`error TS2741: Property 'icon' is missing ... but required in type 'EmptyStateProps'` on
  PlatformAuditEventsPage and PlatformTenantDirectoryPage) -- fixed by passing the icon prop.
  All 39 remaining errors are pre-existing in untouched files (the `res.data?.data` unwrap on
  typed service responses, plus unused-import lint in `src/types/__tests__/*`).
- **git diff --check:** clean (the LF->CRLF warnings are core.autocrlf=true, benign, prior-
  phase convention; git stores LF).
- **ASCII:** the 4 NEW/rewritten harness files (readiness.tsx, RecordedDefects.test.tsx,
  README.md, OpsHealthPage.tsx) are pure ASCII. The 3 modified page files
  (PlatformAuditEventsPage / PlatformTenantDirectoryPage / PlatformOverviewPage) retain
  pre-existing em-dashes in their *untouched* JSDoc headers; their non-ASCII byte counts are
  identical branch-vs-base (12=12, 3=3, 5=5), so P25-C adds **0 new non-ASCII bytes**.
- **detect-secrets 1.5.0 (configured baseline):** exit 0, 0 findings on the 7 changed files;
  `.secrets.baseline` UNCHANGED (`git diff origin/platform-dev -- .secrets.baseline` empty).
- **Forbidden-path audit:** all 7 changed files are under `frontend/src/` (4 page/source +
  helper + test + README); 0 backend / migration / alembic / package.json / lockfile / auth /
  product / .sql paths.

Known warnings (honest, not hidden):

- Screenshots + dim-10 (no clipped/overlapping) remain **skip-with-reason**: Playwright is not
  installed (forbidden package change) and no runnable stack is available; component-level
  tests substitute (P25-A section 9). NOT a silent pass (C21).
- Loading affordance (dim 5) for store-backed pages: the in-effect loading-flag transition is a
  jsdom/act artifact; the dim-5 check is "read issued / no error flash / no crash on mount"
  (unchanged from P25-B).

## 5. GitNexus summary

`npx gitnexus analyze` + `npx gitnexus status` run at the code commit (`5f4918b`):

```
9,453 nodes | 28,839 edges | 592 clusters | 300 flows
Indexed commit: 5f4918b   Current commit: 5f4918b   Status: up-to-date
```

(A pre-commit analyze of the working tree read 9,441 / 28,826 / 593; the small wobble is the
test/doc-symbol contribution between reads. Both land in the band and flows are unchanged.)
Counts sit within the documented P24-P25 band (~9,393-9,466 nodes / ~28,767-28,846 edges /
584-598 clusters). **Flows STABLE at 300** -- the change is frontend-only (markup, an icon
prop, navigation `<Link>`s, and test/doc files), so it adds test/doc/nav symbols but touches 0
backend / product code; the 300 runtime flows are unchanged. The ledger commit is docs-only
(markdown, not a symbol), so the code graph at the final tip == the graph at `5f4918b`.

`detect_changes` (MCP) is flaky in this environment (per prior phases); the reliable
corroborator is the change scope itself: `git diff origin/platform-dev` is **7 files**, all
under `frontend/src/`. 0 backend / migration / product symbols -> 0 affected runtime flows ->
stop gate NOT triggered.

## 6. Defect resolution (the P25-B recorded defects, now fixed)

### D2 -- empty-state render crash (AC 5) -- RESOLVED

P25-B recorded that `PlatformAuditEventsPage` and `PlatformTenantDirectoryPage` rendered
`<EmptyState title=... description=.../>` WITHOUT the REQUIRED `icon` prop
(`EmptyState.icon` is non-optional), so the page threw "Element type is invalid" on any render
that reached the empty branch -- including the initial mount. (This was also a tsc error,
TS2741, on both files.)

P25-C fix: import a heroicon and pass `icon` -- `ClipboardDocumentListIcon` on Audit Events,
`BuildingOfficeIcon` on Tenant Directory. The two routes rejoin `SWEEP_ROUTES` (now all 19),
so the state/copy/forbidden sweeps cover them, and `P25_RecordedDefects` D2-a/D2-b assert the
empty copy renders (`waitFor` for the read to settle onto the empty branch, then expect "No
audit events" / "No tenants found"). They turn RED if the icon prop regresses.

### D1 -- navigation reachability gap (AC 9; section 3.6) -- RESOLVED

P25-B recorded 7 routes with no Sidebar link and no in-app `<Link>` (URL-only): System Health,
Audit Events, Registry, Ops Errors, Ops Slow Routes, Ops Resources, Ops Noisy Neighbors.

P25-C fix: restrained, operator-focused hub links (no Sidebar bloat; the Sidebar stays at 10
platform links; `P25_RouteInventory` INV05 "10 sidebar / 9 not" and `P25_SidebarNav`
`SIDEBAR_ROUTES.length === 10` both still hold):

- Platform Overview "Platform Pages" -> System Health, Tenant Directory, Audit Events, Registry.
- Ops Cockpit "Operations Views" -> Ops Errors, Slow Routes, Resources, Noisy Neighbors.

Combined with the existing tenant-directory-card -> tenant-health link and the tenant-health ->
tenant-directory back-link, every platform route is now reachable by a Sidebar link or an
in-app `<Link>`. The helper scans the shipped platform source for a link-target literal
(`to[:=] '<path>'`, matching both the JSX attribute `to="..."` and the link-array `to: '...'`
idiom, but NOT AppRouter `path:` declarations; the parameterized tenant-health route is matched
by its template-literal prefix) to compute `URL_ONLY_ROUTES`, which is EMPTY.
`P25_RecordedDefects` D1-a asserts `URL_ONLY_ROUTES.length === 0` and D1-b asserts every route
passes `routeIsReachable`; both turn RED if a hub link is removed.

## 7. Open risks / non-goals

- Risk: LOW (frontend render-safety + navigation only; 0 backend flows; 0 product paths).
- Blockers: none.
- Non-goals: no merge into `platform-dev` or `product-dev-recovered`; no push to platform-dev
  (branch push-ready with an explicit `X:X` refspec on request; `origin/platform-dev` left
  unchanged at `5687e7d4`); no new capability; no Playwright/screenshots (still forbidden
  package change); no auth/RBAC rewrite.

## 8. P25-D / next-gate statement

P25-D / customer signoff is NOT started. P25-C resolved the two defects the P25-B harness
recorded; a real Playwright pass on a runnable stack and a customer/operator signoff remain
separately approved gates. Any further capability work (P26+) requires a new contract and must
stay behind the identity-only platform-operator guard and the never-leaked list.

## 9. Final verdict

**READY_FOR_CTO_REVIEW.**

P25-C is a sound, minimal, frontend-only fix slice: D2 (empty-state icon) and D1 (hub
navigation) are both resolved and guarded by regression tests; 173 P25 + 595 full frontend
suite green; tsc +0 new (and -2, the D2 defects); git diff --check clean; 0 new non-ASCII;
detect-secrets clean (baseline unchanged); forbidden-path clean; GitNexus flows STABLE 300.
Not merged; not pushed to platform-dev; P25-D / customer signoff not started.
