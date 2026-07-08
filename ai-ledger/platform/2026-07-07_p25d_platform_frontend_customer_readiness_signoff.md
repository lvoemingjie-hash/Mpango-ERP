# P25-D Platform Frontend Customer-Readiness Signoff

**Phase:** P25-D Platform Frontend Customer-Readiness Signoff Gate
**Date:** 2026-07-07
**Base:** `b78244ef` (origin/platform-dev -- P25-C customer-readiness defect fix merged)
**Branch:** `codex/platform-p25d-platform-frontend-customer-signoff-2026-07-07`
**Worktree:** `_p25d_2026-07-07`
**Tip:** this ledger commit (branch HEAD). The exact tip SHA is reported in chat only, not
embedded here, to keep this ledger non-self-referential (mirrors P25-C R1 / P25-B `a7fce2ee`).
**Ahead / behind base:** 1 / 0 (this ledger commit only; 0 runtime/frontend/test code changed)
**Verdict:** **P25_PLATFORM_FRONTEND_CUSTOMER_READY** (evidence/signoff closeout over the
as-built P10-P25 platform frontend surface; no new defect found; not merged; not pushed to
platform-dev; `origin/platform-dev` left unchanged at `b78244ef`)

## 1. Phase inventory

P25-D is the final customer/operator readiness signoff over the as-built P10-P25 platform
frontend surface. It is **evidence/signoff only**: it adds NO capability, NO route, NO backend,
NO migration, NO package/lockfile change, NO auth/RBAC/session rewrite, NO product-dev-recovered
path, and NO new execution/delivery/approval control. It re-runs the P25-B readiness harness
(plus the P25-C defect guards) over the post-P25-C code at `b78244ef`, confirms every platform
route is READY, and records the verdict.

This single ledger markdown is the only changed file vs `origin/platform-dev`. 0 backend /
migration / alembic / package.json / lockfile / auth / product / .sql / .ts / .tsx paths.

The closeout covers the full merge chain it stands on (each merge to `platform-dev`):

- P25-A `48ddda43` -- readiness contract (19-route inventory, 12-dimension matrix, P25-B gate).
- P25-B `5687e7d4` -- non-shipping readiness validation harness (8 files, 158 tests; recorded
  defects D1/D2, deliberately not fixed).
- P25-C `b78244ef` -- frontend-only defect fix slice (resolved D1 + D2, tightened the harness
  to GUARD the fix; 158 -> 173 P25 / 580 -> 595 full).

P25-D does not alter any of that code; it signs it off as customer-ready.

## 2. Scope statement (evidence/signoff only)

P25-D is a VALIDATION layer, not a capability layer (same framing as P25-A section 1.3). Its
sole artifact is this ledger. It performs no merge into `platform-dev` or `product-dev-recovered`,
pushes nothing, and changes no shipped source. All non-goals from the P25-A contract (1.3.2)
are honored by construction (there is no code change to violate them):

- No new capability; no migration; no product branch merge; no product business mutation.
- No auth/RBAC rewrite (the P10/P11 `PlatformRoute` identity-only global super_admin guard is
  reused unchanged).
- No P22 execution expansion; no notification delivery; no tenant-data leak.
- No `source_unknown` shown healthy; no `backup_check_warning` shown as success.
- No audit-history deletion; no AI agent execution / auto-approval / auto-close.
- No screenshot / transcript secret leak (screenshots remain skip-with-reason; section 6).

## 3. As-built surface under signoff (the closed 19-route set)

The readiness harness grounds its route table in the shipped source
(`frontend/src/router/AppRouter.tsx` + `frontend/src/components/layout/Sidebar.tsx`), not in an
invented list. The closed set is 19 routes across 8 capability families, all behind the
identity-only `PlatformRoute` guard:

| group | route | name | sidebar? |
| --- | --- | --- | --- |
| overview | `/platform` | Platform Overview | yes |
| health | `/platform/system/health` | System Health | hub (Overview) |
| registry | `/platform/tenants` | Tenant Directory | hub (Overview) |
| health | `/platform/tenants/:tenantId/health` | Tenant Health | link (Tenant Card) |
| overview | `/platform/audit` | Audit Events | hub (Overview) |
| registry | `/platform/registry` | Registry | hub (Overview) |
| support | `/platform/support` | Support Console | yes |
| ops | `/platform/ops/health` | Ops Cockpit | yes |
| ops | `/platform/ops/errors` | Ops Errors | hub (Ops Cockpit) |
| ops | `/platform/ops/slow-routes` | Ops Slow Routes | hub (Ops Cockpit) |
| ops | `/platform/ops/resources` | Ops Resources | hub (Ops Cockpit) |
| ops | `/platform/ops/noisy-neighbors` | Ops Noisy Neighbors | hub (Ops Cockpit) |
| ops | `/platform/ops/incidents/triage` | Incident Triage | yes |
| actions | `/platform/controlled-actions` | Controlled Actions | yes |
| approvals | `/platform/approvals` | Approvals | yes |
| approvals | `/platform/durable-approvals` | Durable Approvals | yes |
| execution | `/platform/controlled-execution` | Controlled Execution | yes |
| tasks | `/platform/operator-tasks` | Operator Tasks | yes |
| closeouts | `/platform/incident-closeouts` | Incident Closeouts | yes |

10 routes are direct Sidebar links; 9 are reached via a parent page hub link added by P25-C
(Platform Overview "Platform Pages" and Ops Cockpit "Operations Views") or a tenant-card link.
The helper's source reachability scan computes `URL_ONLY_ROUTES` and it is EMPTY -- every route
is navigable without a typed URL. P25-C resolved defect D1 (the prior 7 URL-only routes) and D2
(the EmptyState icon crash); both are now guarded by `P25_RecordedDefects` (4 tests, GREEN while
the fix holds, RED on regression).

## 4. Verification

Exact commands (run from the worktree; `node_modules` symlinked from the sibling main checkout;
vitest 1.6.1, jsdom; tsc 5.x):

```
node_modules/.bin/vitest run src/pages/platform/__tests__/p25   # 8 files, 173 tests PASS
node_modules/.bin/vitest run                                   # 48 files, 595 tests PASS
node_modules/.bin/tsc --noEmit                                  # 39 errors (base 39; P25-D +0 new)
git diff --check origin/platform-dev                            # clean
```

- **P25 readiness harness:** 173 passed / 0 failed (8 files). Dimension coverage: smoke/route
  inventory (6), guard admit/deny (5), sidebar nav (14), empty/loading/error state (57),
  copy/never-leaked (57), console tone (10), forbidden control (20), resolved-defect guards (4).
  Every one of the 19 routes reports READY across the asserted dimensions.
- **Full frontend suite:** 595 passed / 0 failed / 0 regressions (48 files). Matches the P25-C
  recorded count exactly (580 P25-B base + 15 from the P25-C fix = 595).
- **tsc --noEmit:** 39 errors total, identical to the post-P25-C baseline. P25-D ships 0 `.ts` /
  `.tsx` files (the working tree is byte-identical to `b78244ef` for all source), so the count is
  the baseline by construction: **+0 new**. Breakdown (all pre-existing, all in untouched test or
  page files): 13x TS2339, 7x TS6196, 5x TS2353, 4x TS6133, 4x TS2345, 3x TS2740, 1x TS2739,
  1x TS2459, 1x TS2322. (Typical shapes: `res.data?.data` unwrap on typed service responses, and
  unused-import lint in `src/types/__tests__/*`.) vitest uses esbuild transpilation, so these
  type-only diagnostics do not block the 595/595 runtime suite.
- **git diff --check:** clean (LF->CRLF warnings are core.autocrlf=true, benign, prior-phase
  convention; git stores LF).

Known warnings (honest, not hidden):

- React Router v7 future-flag warnings (`v7_startTransition`, `v7_relativeSplatPath`) are emitted
  to stderr by several tests. These are benign opt-in notices from react-router 6.x, pre-existing,
  and asserted-against indirectly by the passing nav tests.

## 5. Customer / operator path verification

Each customer/operator path below is asserted by a harness dimension AND grounded in the shipped
source; the suite is GREEN, so each path is verified, not just described.

- **Login / guard admit-deny (dim 2; AC 13):** `PlatformRoute` admits ONLY an identity-only
  global super_admin -- `user.roles` includes `super_admin` AND `user.tenant_id == null` AND
  `user.tenant_schema == null` (`frontend/src/router/guards.tsx`). A tenant-contextual super_admin
  (`tenant_id != null`) is explicitly DENIED and redirected to `/`; a regular user is DENIED
  likewise; an unauthenticated request is redirected to `/login` by `ProtectedRoute`.
  `P25_GuardMatrix` (5 tests) asserts each branch.
- **Sidebar + hub navigation (dims 3 + 8; AC 9):** the Sidebar platform section shows 10 direct
  links to an identity-only super_admin and hides them for everyone else
  (`P25_SidebarNav`, 14 tests). The 9 non-sidebar routes are reached via the P25-C hub links on
  Platform Overview and Ops Cockpit plus the tenant-card link; the reachability scan
  (`URL_ONLY_ROUTES`) is EMPTY, and `P25_RouteInventory` (6 tests) + `P25_RecordedDefects` D1-a/D1-b
  assert every route is reachable. No route is URL-only/unreachable.
- **Empty / loading / error states (dims 4/5/6; AC 5/6/7):** `P25_StateMatrix` (57 tests) renders
  each route through the real `PlatformRoute` with a mocked backend and asserts the empty, loading,
  and error branches render the right affordance with no crash. Defect D2 (EmptyState missing its
  required `icon` prop on Audit Events + Tenant Directory) is resolved and guarded, so the empty
  branch renders safely on all 19 routes.
- **No secret / copy leak (dim 9; AC 11):** `P25_CopySafety` (57 tests) scans every route's
  rendered text against 15 leak patterns (postgres/mysql/redis/mongodb DSN, aws endpoint, bearer
  token, basic-auth header, api-key, AWS access key, JWT, set-cookie, private key, password
  assignment, shell injection, raw SQL DML). Zero hits. No customer secret, DSN, token, or tenant
  business payload reaches the DOM.
- **No forbidden execute/send/approve/deliver control (dim 12; AC 17):** `P25_ForbiddenControls`
  (20 tests) scans every route's button labels against a calibrated regex:
  `\b(execute|dispatch|deliver|send|push)\b | \bclear\s+flag\b | \bset\s+flag\b | \bdelete\s+tenant\b | \bpurge\b | \btruncate\b`.
  Dry-run / Record / Acknowledge / Self-assign / Complete / Materialize / Approve / Retry are
  PERMITTED (record/transition, not execution); bare Execute / dispatch / deliver / send / push /
  flag mutation / delete-tenant / purge / truncate are FORBIDDEN. An adversarial calibration test
  pins the boundary. The platform cockpit surfaces no execution, delivery, approval-decision, or
  flag-mutation control -- consistent with the P22-P24 invariants (closeout = view, step = pointer,
  follow-up = record, notification = record not delivery).
- **Console tone consistency (dim 11; AC 13/14/15):** `P25_ConsoleConsistency` (10 tests) asserts
  `source_unknown` is never shown healthy and `backup_check_warning` is never shown as success,
  including on completed states.

No stop condition is triggered by any path (no crash, no URL-only route, no forbidden control).

## 6. Screenshot evidence -- skip-with-reason (honest)

Every screenshot cell is **skip-with-reason**, recorded honestly, not as a pass (P25-A contract
C21). This is unchanged from P25-B/P25-C and is re-confirmed here:

- **Playwright is not installed** and is not in `frontend/package.json` or
  `frontend/node_modules`. Installing it would be a forbidden package/lockfile change (no
  capability/migration/package change without separate approval -- a P25-A hard stop). The harness
  therefore captures no browser pixels.
- **No runnable stack** is available in this worktree for a reproducible operator-login smoke: a
  real pass needs a running backend + DB seeded with a safe operator fixture + `vite dev` + a
  browser driver. The repo ships a `docker-compose.yml` for deploy infra (postgres/backend), but
  standing it up, seeding a safe operator, and browser-driving it is backend/DB/auth/fixture work
  outside this signoff gate's scope, and a browser driver is still absent without a package change.
- **Substitute (P25-A section 9 permitted):** every route is exercised at the unit/component level
  with a mocked backend, rendered through the real `PlatformRoute` guard, and asserted on the
  empty / loading / error / denied / copy / tone / forbidden dimensions directly (173 tests).

Screenshot cell verdict for all 19 routes: `skip -- Playwright not installed; no runnable stack;
component-level tests substitute (P25-A section 9).` This does NOT contradict the test matrix -- it
is the matrix's own recorded verdict for the visual dimensions (screenshots + dim-10 no-clip), and
the non-visual dimensions are all PASS.

## 7. GitNexus summary

`gitnexus analyze` was run on the `_p25d_2026-07-07` worktree; `gitnexus status` is up-to-date at
the branch tip (indexed commit == current commit == branch tip). The exact tip SHA is reported in
chat only, not embedded here, to keep this ledger non-self-referential.

Observed analyze counts sit within the documented P24-P25 band (~9,393-9,466 nodes /
~28,767-28,846 edges / 584-598 clusters / 300 flows). **Flows STABLE at 300.** P25-D is docs-only
(this ledger markdown); markdown is not a code symbol, so the code graph at the P25-D tip == the
graph at `b78244ef` == the graph at the P25-C code commit. The 300 runtime flows are unchanged.

`detect_changes` (MCP) is flaky in this environment (per prior phases); the reliable corroborator
is the change scope itself: `git diff origin/platform-dev` is **1 file** -- this ledger markdown
under `ai-ledger/platform/`. 0 backend / migration / product / frontend symbols -> 0 affected
runtime flows -> stop gate NOT triggered.

## 8. Stop-conditions check + forbidden-path audit

Stop conditions (task spec) -- none triggered:

- Any route still crashes -- NO (`P25_StateMatrix` 57 green; D2 resolved; no render throws).
- Any route is URL-only/unreachable -- NO (`URL_ONLY_ROUTES` empty; D1 resolved; reachability
  scan green).
- Any forbidden execution/delivery/approval control appears -- NO (`P25_ForbiddenControls` 20
  green; regex calibrated; no bare execute/dispatch/deliver/send/push/flag-mutation control).
- Any backend/product/auth/migration/package scope change is needed -- NO (docs-only signoff; 0
  such files changed).
- Any screenshot/demo evidence contradicts the test matrix -- NO (screenshots are skip-with-reason,
  the matrix's own recorded verdict for visual dims; non-visual dims all PASS; no contradiction).

Forbidden-path audit: the single changed file is `ai-ledger/platform/2026-07-07_p25d_...md` --
allow-listed. 0 backend / migration / alembic / package.json / lockfile / auth / product / .sql /
.ts / .tsx paths. ASCII clean (new markdown, pure ASCII). detect-secrets 1.5.0 (configured
baseline) exit 0, 0 findings; `.secrets.baseline` UNCHANGED at `34ad65f4...`
(`git diff origin/platform-dev -- .secrets.baseline` empty).

## 9. Final verdict + next-gate statement

**P25_PLATFORM_FRONTEND_CUSTOMER_READY.**

The as-built P10-P25 platform frontend surface is customer/operator-ready as an identity-only,
non-executing, non-sending console: all 19 routes render through the real `PlatformRoute` guard
with correct admit/deny; every route is reachable; empty/loading/error states render safely; no
secret/copy leaks; no forbidden execution/delivery/approval/flag-mutation control; tone invariants
hold (source_unknown never healthy, backup_check_warning never success). Evidence: 173 P25 harness
+ 595 full frontend suite green; tsc +0 new (39 pre-existing baseline); git diff --check clean; 0
new non-ASCII; detect-secrets clean (baseline unchanged); forbidden-path clean; GitNexus flows
STABLE 300. Screenshots are honestly skip-with-reason with the contract-permitted component-level
substitute; that is consistent with, not contradictory to, the matrix.

Blockers: none. Risk: LOW (docs-only signoff; 0 code change; 0 backend flows; 0 product paths).

Non-goals: no merge into `platform-dev` or `product-dev-recovered`; no push to platform-dev
(branch push-ready with an explicit `X:X` refspec on request; `origin/platform-dev` left unchanged
at `b78244ef`); no new capability; no Playwright/screenshots (still a forbidden package change
without separate approval).

Next gate: P25-D closes the P25 readiness track. Any further capability work (P26+) requires a new
contract and must stay behind the identity-only platform-operator guard, the never-leaked list, and
the forbidden-control boundary. A real Playwright pass on a runnable stack with a seeded safe
operator fixture remains a separately approved gate if executable browser-pixel evidence is later
required; until then the component-level harness is the evidence of record.
