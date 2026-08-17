# DC-12R1-MVP-L1-PW1-R4-C1 — Responsive MainLayout & Mobile Navigation Closure (Zcode)

- Task: DC-12R1-MVP-L1-PW1-R4-C1
- Owner: Zcode
- Date: 2026-08-17
- Mode: Frontend product implementation
- Frozen base: `origin/product-dev-recovered` @ `9067e38f83edb38fcdb53fb5d5eea7e75e85cf5f` (verified equal before branch creation)
- Accepted diagnostic: R4-C0-R2-E1 @ `1929197d932a15fd98d0b43c906b1e23a34a1ef4`
- Authoritative browser harness: `db84b1325c51a484af55029ce3485d9995b0669a` (pw1r4b)
- Branch: `zcode/dc12r1-mvp-l1-pw1-r4-c1-responsive-main-layout-2026-08-17`
- Isolated worktree: `_zcode_dc12r1_r4c1_worktree_2026-08-17` (created from frozen SHA, clean tree)

## Phase 1 — Proof and Impact Gate

- `git fetch --all --prune` executed; protected ref `origin/product-dev-recovered` == `9067e38f` (no drift).
- GitNexus index built on the isolated worktree at the frozen SHA (15,221 nodes / 45,671 edges).
- Upstream impact (GitNexus): `MainLayout`, `Sidebar`, `Header` → impactedCount 0 (pure JSX wiring), risk **LOW** for all three. Per directive §6 no HIGH/CRITICAL report was required.
- Direct callers (grep): `frontend/src/router/AppRouter.tsx` (2 layout route nodes) and 2 existing test files render MainLayout (`Pw1R2AuthSessionClosure.test.tsx`, `PrintableWorkspace.test.tsx`).
- Affected routes under MainLayout: 38 total (19 wholesaler ERP + 19 platform cockpit).
- No symbols modified before impact analysis completed.

## Product Contract Implementation

Authorized files only:

1. `frontend/src/components/layout/MainLayout.tsx` — owns drawer open/close state; content `lg:ml-64` + `min-w-0` (no `ml-64` on mobile); Escape close with focus restore; route-change auto-close; no overflow masking anywhere.
2. `frontend/src/components/layout/Sidebar.tsx` — desktop `<aside>` unchanged at lg+ (`hidden lg:flex w-64` fixed 256px); mobile off-canvas drawer rendered only while open (closed drawer fully unmounted → links in neither tab order nor accessibility tree); backdrop (`lg:hidden`, z-40) closes drawer.
3. `frontend/src/components/layout/Header.tsx` — accessible hamburger `<lg` (`aria-label`, `aria-expanded`, `aria-controls="mobile-navigation-drawer"`); header keeps `shrink-0`; children use `min-w-0` + `truncate` (breadcrumb nav, tenant badge with `title` preserving full code, user block); right group may shrink (`gap-2 lg:gap-4`, badge `max-w-[6rem] sm:max-w-[10rem] truncate`) so the header never forces overflow at 390px.
4. `frontend/src/tests/Pw1R4C1MainLayoutResponsive.test.tsx` (new) — T1–T9 rendering the real MainLayout + Header + Sidebar with MemoryRouter/Routes.

ClientLayout, auth, permissions, API, backend, payment declaration flow: untouched.

## Required Product Tests — all GREEN

- Natural order: 9/9 passed.
- Fixed-seed shuffled (`--sequence.shuffle --sequence.seed=42424`): 9/9 passed.
- Existing Header / PrintableWorkspace / PW1-R2 auth-session suites: 111/111 passed.
- Full `pnpm vitest run`: **23 files / 337 tests / 0 failed**.
- `pnpm build`: exit 0.
- No skip/xfail/only/conditional passes/retry-greening/assertion weakening.

## Mutation RED Gates — all verified RED then restored GREEN

| Mutation | Expected RED | Result |
|---|---|---|
| M1 unconditional `ml-64` | T8 | RED confirmed, reverted |
| M2 remove header children `min-w-0` | T9 | RED confirmed, reverted |
| M3 hide Sidebar + remove hamburger/drawer | T1/T3 (and T7 for sidebar-hiding half) | RED confirmed, reverted |
| M4 remove Escape close / remove backdrop close | T4 | RED confirmed (both halves), reverted |
| M5 remove route-change close | T6 | RED confirmed, reverted |
| M6 remove focus restore | T5 | RED confirmed, reverted |

No mutation residue: worktree clean after each revert; final state re-verified GREEN.

## Targeted Browser Gate (harness worktree @ db84b132)

Runtime: candidate frontend dev server (this branch) on 127.0.0.1:5173; existing staging backend on 127.0.0.1:8000 (pw1r4c0 postgres/redis containers restarted for the run); harness identities copied from the pw1r4b4v3 provision.

`phase6-responsive.spec.ts` full run (workers=1, retries=0):

- Final run: **15 passed / 6 failed**.
- ALL wholesaler-side nodes PASS at desktop/tablet/mobile — including the two originally-red mobile nodes:
  - `wholesaler dashboard` (mobile): scrollWidth === clientWidth === 390, zero offenders.
  - `wholesaler orders` (mobile): scrollWidth === clientWidth === 390, zero offenders.
  (Pre-fix these measured +19px overflow from the header user-info group; root cause fixed via shrink/truncate contract, not masking.)
- 6 failing nodes are the **retailer catalog/orders nodes at all 3 viewports**, failing at HTTP 401 during `/client/auth/login` — before any page renders, on ClientLayout journeys untouched by this task. Root cause is the runtime, not the frontend: the pw1r4c0 staging DB contains **no retailers** (`public.retailers` empty), **zero seeded permissions** in the tenant schema (RBAC tables empty → `invitations:create` and every permission-gated provisioning endpoint 403), and the pw1r4b4v3 retailer identity `rb` does not exist in this DB. Provisioning a retailer through the supported lifecycle was attempted and blocked at step 2 (403 PERMISSION_DENIED). Repairing this requires backend/runtime provisioning work outside the 4 authorized files.

Mobile hamburger/drawer actual-click verification (390px, real login, `drawer_click_gate.cjs`): **18/18 PASS** — hamburger visible with full aria contract; drawer default-closed and absent from DOM; click opens drawer + backdrop; Escape/backdrop/hamburger close; focus returns to hamburger; drawer link click navigates to /orders and auto-closes; overflow == 0 at every step; final dashboard dims `{"sw":390,"cw":390}`.

## Quality and Scope

- `git diff --check`: clean.
- Scoped pre-commit (trailing whitespace, end-of-files, large files) and detect-secrets: passed on every commit.
- Strict UTF-8, no BOM, no mojibake in all 4 code files (verified byte-level).
- Branch increment vs frozen base: exactly the 4 authorized code/test files plus this evidence file (5 files).
- GitNexus: index built at frozen SHA; post-change impact/context re-run (risk LOW); `detect_changes` subcommand not present in the installed CLI version — scope verified via git status/diff instead (no unauthorized file touched).
- Protected refs unchanged; local SHA == remote SHA after push (see below).

## Verdict

Frontend product contract, mutation gates, unit/build gates: **PASS**.
Browser gate: wholesaler-side (this task's scope) fully green including both originally-red mobile nodes and real click verification; the 6 retailer nodes are blocked by missing runtime provisioning (empty RBAC/retailer tables in the pw1r4c0 staging DB), which cannot be repaired within the authorized file scope.

**STOP_AND_REPORT_CTO** — retailer-node environment repair (permission seeding + retailer lifecycle provisioning) requires CTO authorization. Not starting Kilo; not running the full 162 browser matrix; not merging, deploying, or starting follow-on work.

## Runtime Cleanup

- Candidate frontend dev server stopped after evidence capture.
- Harness worktree artifacts (diag scripts, run logs, copied identities) are task-private and removed with the worktree.
- pw1r4c0 postgres/redis containers stopped after the run (they were stopped when the task started).
