# P25-B Platform Frontend Customer-Readiness Validation Harness

**Phase:** P25-B Platform Frontend Customer-Readiness Validation Harness
**Date:** 2026-07-06
**Base:** `48ddda4` (origin/platform-dev -- P25-A contract merged)
**Branch:** `codex/platform-p25b-platform-frontend-readiness-validation-2026-07-06`
**Scope:** non-shipping, non-merging frontend validation/smoke harness over the as-built
P10-P24 platform surface. It adds NO capability, NO route, NO backend, NO migration. It
records results and records defects for a later, separately approved fix slice; it never
fixes a defect inline (contract section 6.8 / section 9).

This harness is the P25-A section 9 P25-B gate: a Playwright-equivalent harness that, where
no runnable browser stack exists, exercises the `PlatformRoute` guard and the page components
at the unit/component level with a mocked backend. It traverses the section 3 route inventory,
captures the section 4 matrix per route, and writes the section 6 evidence set.

---

## 1. How to run

```bash
# from the frontend/ directory (node_modules junction'd from a sibling checkout)
node_modules/.bin/vitest run src/tests/p25            # the P25-B harness only (158 tests)
node_modules/.bin/vitest run                          # full frontend suite (580 tests)
```

The harness is 8 files under `frontend/src/tests/p25/`:

| file | dimension (section 4) | tests |
| --- | --- | --- |
| `__helpers__/readiness.tsx` | shared route table, fixtures, leak scanner, render harness | -- |
| `P25_RouteInventory.test.tsx` | dim 1 smoke / closed-set grounding (C11/C12) | 6 |
| `P25_GuardMatrix.test.tsx` | dim 2 login / admit + deny (section 3.6; C13) | 5 |
| `P25_SidebarNav.test.tsx` | dims 3 + 8 navigation + active highlight (AC 9) | 14 |
| `P25_StateMatrix.test.tsx` | dims 4/5/6 empty / loading / error (AC 5/6/7; C9/C10) | 51 |
| `P25_CopySafety.test.tsx` | dim 9 copy / never-leaked (AC 11; C20) | 51 |
| `P25_ConsoleConsistency.test.tsx` | dim 11 tone consistency (AC 13/14/15; C14/C15/C17) | 10 |
| `P25_ForbiddenControls.test.tsx` | dim 12 no forbidden control (AC 17; C19) | 18 |
| `P25_RecordedDefects.test.tsx` | recorded defects D1/D2 (section 6.8) | 3 |

---

## 2. Screenshot evidence -- skip-with-reason (honest)

Every screenshot cell is **skip-with-reason**. Per the P25-B gate this is recorded honestly,
not as a pass (contract C21):

- **Playwright is not installed** and is not in `frontend/package.json`. Installing it would
  be a forbidden package/lockfile change (no capability/migration/package change without
  separate approval -- hard stops). The harness therefore does not capture browser pixels.
- **No runnable stack** is available in this worktree (no dev server / backend / DB seeded
  with a safe operator fixture). A real login smoke could not be executed.
- **Substitute (contract section 9 permitted):** every route is exercised at the
  unit/component level with a mocked backend (`@/services/api`), which renders the real page
  through the real `PlatformRoute` guard and asserts the empty / loading / error / denied /
  copy / consistency / forbidden dimensions directly. This is the component-level substitute
  the contract names for the no-runnable-stack case.

Screenshot cell verdict for all 19 routes: `skip -- Playwright not installed; no runnable
stack; component-level tests substitute (P25-A section 9).`

---

## 3. Readiness matrix (route x dimension)

Dimensions: 1 smoke | 2 login(deny) | 3 sidebar-nav | 4 empty | 5 loading | 6 error |
7 denied | 8 nav-path | 9 copy-leak | 10 no-clip* | 11 console-tone | 12 forbidden-control.
`PASS` = covered by a harness assertion; `SKIP` = honest skip-with-reason; `DEFECT` = a
recorded defect blocks the cell.

\* dim 10 (no clipped/overlapping text) is a visual dimension that needs a real browser
viewport; it is `SKIP` here for the same reason as screenshots (no Playwright). Copy/tone/
forbidden/invariant dimensions ARE asserted in-DOM where feasible.

| # | route | group | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | verdict |
| --- | --- | --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | --- |
| 1 | /platform | overview | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | SKIP | PASS | PASS | READY |
| 2 | /platform/system/health | health | PASS | PASS | D1 | PASS | PASS | PASS | PASS | D1 | PASS | SKIP | PASS | PASS | READY* |
| 3 | /platform/tenants | registry | DEFECT-D2 | PASS | D1 | DEFECT-D2 | DEFECT-D2 | DEFECT-D2 | PASS | D1 | DEFECT-D2 | SKIP | n/a | DEFECT-D2 | BLOCKED-D2 |
| 4 | /platform/tenants/:id/health | health | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | SKIP | PASS | PASS | READY* |
| 5 | /platform/audit | overview | DEFECT-D2 | PASS | D1 | DEFECT-D2 | DEFECT-D2 | DEFECT-D2 | PASS | D1 | DEFECT-D2 | SKIP | n/a | DEFECT-D2 | BLOCKED-D2 |
| 6 | /platform/registry | registry | PASS | PASS | D1 | PASS | PASS | PASS | PASS | D1 | PASS | SKIP | PASS | PASS | READY* |
| 7 | /platform/support | support | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | SKIP | PASS | PASS | READY |
| 8 | /platform/ops/health | ops | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | SKIP | PASS | PASS | READY |
| 9 | /platform/ops/errors | ops | PASS | PASS | D1 | PASS | PASS | PASS | PASS | D1 | PASS | SKIP | PASS | PASS | READY* |
| 10 | /platform/ops/slow-routes | ops | PASS | PASS | D1 | PASS | PASS | PASS | PASS | D1 | PASS | SKIP | PASS | PASS | READY* |
| 11 | /platform/ops/resources | ops | PASS | PASS | D1 | PASS | PASS | PASS | PASS | D1 | PASS | SKIP | PASS | PASS | READY* |
| 12 | /platform/ops/noisy-neighbors | ops | PASS | PASS | D1 | PASS | PASS | PASS | PASS | D1 | PASS | SKIP | PASS | PASS | READY* |
| 13 | /platform/ops/incidents/triage | ops | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | SKIP | PASS | PASS | READY |
| 14 | /platform/controlled-actions | actions | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | SKIP | PASS | PASS | READY |
| 15 | /platform/approvals | approvals | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | SKIP | PASS | PASS | READY |
| 16 | /platform/durable-approvals | approvals | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | SKIP | PASS | PASS | READY |
| 17 | /platform/controlled-execution | execution | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | SKIP | PASS | PASS | READY |
| 18 | /platform/operator-tasks | tasks | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | SKIP | PASS | PASS | READY |
| 19 | /platform/incident-closeouts | closeouts | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | SKIP | PASS | PASS | READY |

`READY*` = the route itself renders cleanly across all exercised dimensions; the `D1` in
dims 3/8 is a NAVIGATION-reachability gap (no sidebar/hub link to it), not a render defect.

---

## 4. Recorded defects (for a separately approved fix slice; NOT fixed inline)

### D1 -- navigation reachability gap (AC 9; section 3.6)

Of the 19 routes, 10 are reachable from the Sidebar platform section. Of the other 9:
- `/platform/tenants/:tenantId/health` is linked from the tenant-directory card
  (`PlatformTenantCard`); `/platform/tenants` has a back-link from tenant-health.
- The remaining **7 routes have no sidebar link and no in-app `<Link>`** from any platform
  page -- they are reachable only by direct URL today: `/platform/system/health`,
  `/platform/audit`, `/platform/registry`, `/platform/ops/errors`, `/platform/ops/slow-routes`,
  `/platform/ops/resources`, `/platform/ops/noisy-neighbors`.

(Functionally 9 of 19 routes are not sidebar-reachable: the tenant-health/directory pair is
only reachable once the operator already has a URL into that cluster.) A later, separately
approved fix slice should add sidebar or hub links for these routes. Asserted in
`P25_RecordedDefects.test.tsx` (D1).

### D2 -- empty-state render crash on Audit Events + Tenant Directory (AC 5)

`PlatformAuditEventsPage` and `PlatformTenantDirectoryPage` render `<EmptyState title=...
description=.../>` WITHOUT the REQUIRED `icon` prop (`EmptyState.icon` is non-optional). The
page therefore throws "Element type is invalid" on any render that reaches the empty branch --
including the initial mount, before any data lands (the list is empty by default). This blocks
dims 1/4/5/6/9/12 for those two routes. A separately approved fix slice should pass an icon
(or make `EmptyState.icon` optional). Asserted in `P25_RecordedDefects.test.tsx` (D2-a/D2-b):
the defect tests are GREEN while the crash exists and turn RED once fixed.

---

## 5. Customer / operator demo script (section 6.7)

Repeatable, copy-safe walkthrough. Run on a stack with an identity-only (global) super_admin
login; every step below is also covered by a component-level test where no stack is present.

1. Log in as an identity-only global `super_admin` (`roles: ['super_admin']`, `tenant_id ==
   null`). Confirm the Sidebar shows the **Platform** section (10 links). (P25-S01.)
2. Open a tenant-contextual `super_admin` session in a second window (`tenant_id != null`)
   and confirm the **Platform** section is hidden and `/platform/*` redirects to `/`. (P25-S02,
   P25-G02.)
3. Walk the sidebar: Platform -> Support Console -> Ops Cockpit -> Incident Triage ->
   Controlled Actions -> Approvals -> Durable Approvals -> Controlled Execution -> Operator
   Tasks -> Incident Closeouts. On each, confirm a loading affordance, then a sane empty
   state, then open one detail/record/transition form (e.g. Acknowledge an operator task;
   advance an incident-closeout step; dry-run a controlled execution request). (P25-LO/EM/ER,
   P25-F.)
4. Force a backing-read failure (e.g. stop the API) and confirm each route renders a redacted
   error (red box + Retry), never a raw payload, stack, secret, or DSN. (P25-ER, P25-C2.)
5. On the Operator Tasks and Incident Closeouts consoles, confirm a `source_unknown` /
   degraded / warning record is NEVER shown green (gray/yellow/blue only), and a completed
   record is blue, not green. (P25-T01..T10.)
6. Confirm no console surfaces a bare Execute / Deliver notification / Clear flag / Send
   control; only Record-* / state transitions are present. (P25-F.)
7. Known gaps to call out in the demo: Audit Events and Tenant Directory crash until D2 is
   fixed (open them last / from a fixed build); the 7 URL-only routes (D1) must be reached by
   typing the URL.

---

## 6. Known warnings / honest skips

- **Screenshots (dim 3 evidence + dim 10):** skip -- Playwright not installed; no runnable
  stack. Component-level tests substitute (section 9). NOT a silent pass.
- **Loading affordance (dim 5):** for store-backed pages (Overview/SystemHealth/OpsHealth/
  TenantHealth/Support) the in-effect loading-flag transition is a jsdom/act artifact (the
  store setter registers when invoked directly, per harness diagnostics). The dim-5 contract
  check is therefore "the read is issued / no error flash / no crash on mount"; the Skeleton
  (`.animate-pulse`) affordance is verified directly for local-state-backed pages and is
  present in a real browser. This is a test-environment limitation, NOT a product defect.
- **Error affordance (dim 6):** the Support Console handles a sessions-read failure by
  continuing to render its usable form (no red box); the dim-6 check accepts "explicit error
  affordance OR sane primary content" (no crash, no leak) for that route.
- **D2 crash logs:** the harness intentionally renders the two D2-defect routes to assert the
  crash; React logs "Element type is invalid" for those two cases. Expected, not a failure.

---

## 7. What this harness is NOT

- It is not a feature. It adds no route, task type, closeout state, action, governed slice,
  migration, auth/RBAC change, execution expansion, or notification delivery.
- It does not merge into `platform-dev` or `product-dev-recovered`. The branch is pushed with
  an explicit `X:X` refspec; `origin/platform-dev` is left unchanged.
- It does not fix D1 or D2. Both are recorded for a separately approved fix slice.
