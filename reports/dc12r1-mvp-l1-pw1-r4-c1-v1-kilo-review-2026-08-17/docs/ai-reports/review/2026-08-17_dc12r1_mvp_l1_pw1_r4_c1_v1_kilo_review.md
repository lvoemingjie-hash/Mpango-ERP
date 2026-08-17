# DC-12R1-MVP-L1-PW1-R4-C1-V1 — Kilo Final Bounded Source Review

- Mode: Adversarial frontend source / test-authenticity review
- Date: 2026-08-17
- Reviewer: Kilo (bounded host review; OpenCode performs the authoritative fresh-runtime 162-node browser gate afterward)

## Frozen Candidate Under Review
- Branch: `origin/zcode/dc12r1-mvp-l1-pw1-r4-c1-responsive-main-layout-2026-08-17`
- Candidate SHA: `df7c8f15435e6821a4f18fbb476b091761933f8d`
- Product base: `9067e38f83edb38fcdb53fb5d5eea7e75e85cf5f`
- Accepted diagnostic: `1929197d932a15fd98d0b43c906b1e23a34a1ef4`
- Worktree: detached, clean, at exact `df7c8f15` (`kilo_review_r4c1_worktree`)

## CTO Adjudication Scope (honored, not re-litigated)
- Zcode phase6 retailer failures classified `HOST_RUNTIME_FIXTURE_INCOMPLETE`.
- No requirement to authenticate task-private browser logs that were cleaned up.
- The six retailer 401 nodes are NOT treated as candidate defects (no source-level causation established).
- No backend, ClientLayout, provisioning, RBAC seed or harness edits authorized or performed.
- No full 162-node browser matrix executed in this Kilo task.

---

## Phase 1 — Proof Gate
| Check | Result |
|---|---|
| `git fetch --all --prune` executed | PASS |
| Detached clean worktree at exact `df7c8f15` | PASS |
| Source branch tip == candidate SHA | PASS (`df7c8f15`) |
| Base `9067e38f` is ancestor of candidate | PASS |
| `origin/product-dev-recovered` remains `9067e38f` | PASS (no drift) |
| Aggregate delta == exactly five files | PASS |

Delta (verified):
```
ai-ledger/product-ai/2026-08-17_dc12r1_mvp_l1_pw1_r4_c1_responsive_main_layout.md
frontend/src/components/layout/MainLayout.tsx
frontend/src/components/layout/Header.tsx
frontend/src/components/layout/Sidebar.tsx
frontend/src/tests/Pw1R4C1MainLayoutResponsive.test.tsx
```
No ref, ancestry, scope or cleanliness mismatch. Phase 1 STOP condition not triggered.

---

## Phase 2 — Product Contract Review (from actual source)
All items verified against the real `MainLayout.tsx` / `Sidebar.tsx` / `Header.tsx`.

- **MainLayout owns drawer state** — `useState(false)` for `drawerOpen`, `hamburgerRef` and `location`; passes `mobileOpen`/`onClose` to `Sidebar` and `drawerOpen`/`hamburgerRef`/`onToggleDrawer` to `Header`. PASS.
- **Mobile content: no unconditional `ml-64`** — content wrapper is `flex min-w-0 flex-1 flex-col lg:ml-64`. The only `ml-64` is gated behind `lg:`. PASS.
- **Desktop content retains `lg:ml-64`** — present on the same wrapper. PASS.
- **`min-w-0` usage** — `main` has `min-w-0`; content wrapper has `min-w-0`; Header's shrinkable children (breadcrumb `<nav>`, tenant/user group) carry `min-w-0`/`truncate`. NOTE: the `Header` element itself does not carry `min-w-0`, but that is the correct CSS pattern (the flex *children* that must shrink carry it). PASS (intent satisfied).
- **No overflow masking** — no `overflow-x-hidden`, no `overflow-hidden`, no negative margin, no content-removal clip. The `hidden`/`lg:hidden` utilities are responsive visibility toggles for the desktop sidebar / hamburger / drawer, not overflow masks. `git diff` confirms no overflow-masking added. PASS.
- **Desktop Sidebar: fixed, 256px, visible at lg+** — `<aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col ... bg-white lg:flex">`. `w-64` == 256px; `hidden` below `lg`, `lg:flex` at `lg+`. PASS.
- **Mobile drawer: absent when closed, mounted only when open** — `{mobileOpen && (...)}`; entire `role="dialog"` drawer (and backdrop) is unmounted when closed. PASS.
- **Closed drawer links absent from tab order & a11y tree** — unmounted when closed; T2 confirms `getByRole('dialog', {name:'Navigation menu'})` and backdrop are null and only one "Sales" link exists. PASS.
- **Hamburger a11y** — `aria-label="Toggle navigation menu"`, `aria-expanded={drawerOpen}`, `aria-controls="mobile-navigation-drawer"`. PASS.
- **Drawer close via hamburger, backdrop, Escape** — hamburger toggle (`setDrawerOpen(open => !open)`); backdrop `onClick={onClose}`; window `keydown` Escape handler. PASS.
- **Route navigation closes drawer** — `useEffect(() => setDrawerOpen(false), [location])`. PASS.
- **Escape/backdrop close restores focus** — both call `closeDrawer` which `hamburgerRef.current?.focus()`; the Escape handler also focuses the hamburger directly. PASS.
- **Hamburger close does not lose focus** — `closeDrawer` re-focuses the hamburger (same control). PASS.
- **Event listeners cleaned up** — `window.addEventListener('keydown', onKeyDown)` with symmetric `removeEventListener` in the effect cleanup. PASS.
- **Long tenant / username / breadcrumb remain available while truncating** — tenant badge and username use `truncate` + `title={...}` (full value preserved on hover/DOM); breadcrumb crumbs use `truncate` and remain in the DOM (T9 asserts each crumb text present). NOTE: breadcrumb crumbs carry `truncate` without a `title` attribute, but the full text stays in the DOM (not removed), satisfying "available via text". PASS.
- **ClientLayout, auth, permissions, API, backend, payment flow untouched** — the delta is exactly the five authorized files; `ClientLayout.tsx`, `authStore`, `router/guards`, payment/API paths are not in the diff. GitNexus impact (fresh index) reports `MainLayout` and `Sidebar` `impactedCount 0 / LOW`; `Header` `2 / LOW` (see Phase 7 note on a spurious backend `declare_payment` edge — graph noise, not real coupling). PASS.

---

## Phase 3 — Accessibility & Regression Review (adversarial)
- **Duplicate desktop/mobile navigation a11y behavior** — when the drawer is open at `<lg`, the desktop `<aside>` is `hidden` (display:none) so it is not in the a11y tree in a real browser; only the drawer's `role="dialog"` nav is exposed. jsdom shows both in the DOM, which the tests explicitly count (T2: 1 link closed, T3: 2 links open). No duplicate-focusable-navigation defect. PASS.
- **`role="dialog"` / `aria-modal` truthfulness** — present and correct on the drawer. OBSERVATION (low severity): `aria-modal="true"` declares the background inert, but the implementation does not enforce an actual focus trap nor set `aria-hidden` on sibling regions. All navigation remains accessible (links focusable, three close paths, focus restored), so this is a semantic-completeness gap, not a blocked navigation path. Not a merge blocker.
- **Backdrop layering & click** — backdrop `z-40`, drawer `z-50`, both `lg:hidden`; backdrop `onClick={onClose}` closes. Click on backdrop closes and restores focus (T5). PASS.
- **Keyboard reachability** — hamburger is a real `<button>` (focusable); drawer links are real `<Link>`s (focusable when mounted). PASS.
- **Focus after every close path** — Escape → hamburger focus (T5); backdrop → hamburger focus (T5); hamburger toggle → focus retained (closeDrawer re-focuses); route navigation → link clicked unmounts, focus returns to `body` (acceptable; contract does not require focus restoration on route change). No navigation path leaves focus stranded in a removed subtree. PASS.
- **Direct Sidebar/Header tests source-compatible** — existing `Header.test.tsx` and `SidebarOps.test.tsx` call `<Header/>` / `<Sidebar/>` with no props; new optional props with defaults keep them compiling and passing (verified in the 111/111 focused run). PASS.
- **Platform navigation & logout unchanged** — `SidebarBody` extracted unchanged: identical `navItems`, identical `showPlatformNav = isIdentityPlatformOperator(user)` platform block, identical `logout` button. No behavior change. PASS.
- **No hidden mobile navigation dead end** — on `<lg` the only nav entry point is the hamburger → drawer, which is fully reachable and closable. PASS.
- **No desktop regression at `lg`** — desktop sidebar `lg:flex` (visible), hamburger `lg:hidden`, drawer `lg:hidden`, content `lg:ml-64`; identical to pre-change desktop layout. T7 confirms. PASS.

No genuine inaccessible navigation path found. Phase 3 raises zero merge blockers.

---

## Phase 4 — Test Authenticity
### T1–T9 use the real layout
The suite imports the real `MainLayout`, `Header`, `Sidebar`, `useAuthStore` and renders them inside `MemoryRouter` + `Routes` with real `Outlet` page stubs. No fake reconstructed layout, no source-text scanning as behavioral proof, no weakened assertions, no `skip`/`xfail`/`only`/`conditional` pass, no hard-coded pass values, and no mutation-specific production branches (the `lg:`/`hidden` classes are production-responsive classes, not test-only branches). PASS.

### Mutation RED-gate authentication (each mutation applied to a throwaway copy of the worktree files, suite run, then reverted via `git checkout`)
| Mutation | Target | Result | Genuinely RED? |
|---|---|---|---|
| M1 unconditional `ml-64` | T8 | 1 failed / 8 passed | YES |
| M2 remove header children `min-w-0` | T9 | 1 failed / 8 passed | YES |
| M3 remove hamburger + mobile drawer | T1/T3 | 6 failed / 3 passed | YES |
| M4a remove Escape close | T4 | 2 failed / 7 passed | YES |
| M4b remove backdrop close | T4 | 2 failed / 7 passed | YES |
| M5 remove route-change close | T6 | 1 failed / 8 passed | YES |
| M6 remove focus restore | T5 | 1 failed / 8 passed | YES |

Each mutation targets the claimed contract and makes the corresponding test(s) RED. Worktree reverted clean after each. PASS.

---

## Phase 5 — Runtime Gates (executed on Kilo host)
Dependencies were not pre-installed in the candidate worktree; `node_modules` was provided via a junction to a sibling worktree with a byte-identical `package.json` + `pnpm-lock.yaml` (verified by hash), then removed before finalization so the candidate worktree stayed clean.

| Gate | Command | Result |
|---|---|---|
| R4-C1 natural order | `vitest run ...Pw1R4C1MainLayoutResponsive.test.tsx` | **9/9 PASSED** |
| R4-C1 fixed-seed shuffle | `--sequence.shuffle --sequence.seed=42424` | **9/9 PASSED** |
| Existing focused regressions | Header + Sidebar + PrintableWorkspace + PW1-R2 | **111/111 PASSED** |
| Full frontend | `vitest run` | **23 files / 337 tests / 337 PASSED** |
| Production build | `tsc -p tsconfig.app.json && vite build` | **tsc exit 0; vite "built in 5.67s"; exit 0** |

Expected counts reproduced exactly. (No backend suite and no 162-node browser matrix were required for this Kilo task; those remain with OpenCode per the CTO adjudication.)

---

## Phase 6 — Evidence Truth (ledger audit)
`ai-ledger/product-ai/2026-08-17_dc12r1_mvp_l1_pw1_r4_c1_responsive_main_layout.md`:
- Retains `STOP_AND_REPORT_CTO` for the Zcode browser gate. PASS.
- Does **not** claim retailer runtime success; explicitly states the 6 retailer nodes failed at HTTP 401 on `ClientLayout` journeys untouched by this task. PASS.
- Accurately labels the six failures as runtime-fixture blocked (empty `retailers` / RBAC tables in the pw1r4c0 staging DB). PASS.
- Records wholesaler mobile 390px zero-overflow evidence (dashboard + orders `scrollWidth === clientWidth === 390`, zero offenders) **without** expanding it into a full-browser PASS. PASS.
- Distinguishes the GitNexus graph `LOW` from the residual rollout exposure across the 38 routes under `MainLayout` (6 retailer nodes runtime-blocked). RECOMMENDATION (non-blocking): add an explicit sentence stating "CTO overall rollout risk MEDIUM across 38 routes (6 retailer nodes runtime-blocked)" so the ledger mirrors the adjudication wording verbatim. The current wording is truthful and not misleading, so this is an enhancement, not a blocker.

No misleading PASS or risk wording. Phase 6 no blocker.

---

## Phase 7 — Quality
- `git diff --check` on the five files vs base: clean (no whitespace errors). PASS.
- Scoped `detect-secrets`: tool not installed in this environment; a scoped manual secret scan of the five files (password / secret / api-key / private-key / AWS key / `token =` patterns) returned **no matches**. The only credential-like strings are clearly-labeled `redacted-test-*` placeholders in the test file. PASS (caveat: detect-secrets binary unavailable; manual scan substituted and disclosed).
- Strict UTF-8 / no BOM / no mojibake: all five files confirmed UTF-8 **without** BOM. PASS.
- GitNexus `analyze` + `status` + `impact`: index built on the frozen SHA (15,235 nodes / 45,701 edges, matching the ledger's ~15.2k/45.7k). Fresh `impact` on `MainLayout`/`Sidebar` = `0/LOW`; `Header` = `2/LOW` with one spurious backend `declare_payment` edge (graph noise; backend untouched per 5-file scope). PASS.
- Candidate worktree clean / no source modification: `git status --porcelain` empty after reverting all mutations and removing the temporary `node_modules` junction + `dist/`. PASS.

---

## Verdict
Source, accessibility, test authenticity, evidence truth and quality gates all close. No inaccessible navigation path, no misleading evidence wording, no scope drift, and the R4-C1 (and full frontend) runtime gates were independently reproduced on the Kilo host.

**PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R4_C1_V1_KILO_FINAL_REVIEW**

Follow-on: OpenCode performs the authoritative fresh-runtime 162-node browser gate; the six retailer nodes remain `HOST_RUNTIME_FIXTURE_INCOMPLETE` and require CTO-authorized runtime provisioning (RBAC seed + retailer lifecycle), outside this candidate's four authorized files.
