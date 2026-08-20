# DC-12R1-MVP-L1-PW1-R4-C1-R1-V1 - Kilo Final Bounded Source Review

**Review mode:** Adversarial source, test-authenticity and evidence-truth review.
This is NOT the authoritative 162-node browser final, merge approval, deployment
approval or VPS approval. The candidate branch was NOT modified.

| Field | Value |
|---|---|
| Candidate SHA | `f51c10943b5d1a67569d681e66a6d56e728860b4` |
| Candidate branch | `zcode/dc12r1-mvp-l1-pw1-r4-c1-r1-browser-integration-closure-2026-08-20` |
| Direct parent | `df7c8f15435e6821a4f18fbb476b091761933f8d` |
| Product baseline | `9067e38f83edb38fcdb53fb5d5eea7e75e85cf5f` |
| Frozen harness | `db84b1325c51a484af55029ce3485d9995b0669a` |
| Prior Kilo C1 review | `ab58a6d71c1f988025737bce0ab5ce8511b34e3e` |
| Authoritative V2 STOP | `c7d880e3cbfcbab10e3b3fbcc160c9f3c980fc74` |
| Protected `origin/product-dev-recovered` | `9067e38f` (verified equal) |
| `origin/main` | `134ea59e` (verified equal) |
| Review host | Kilo (Windows/PowerShell) - `git 2.50.1`, `node v22.17.1`, `pnpm 9.15.4`, `vitest 1.6.1` (jsdom) |
| Review date | 2026-08-20 |
| **Verdict** | **PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R4_C1_R1_V1_KILO_FINAL_REVIEW** |

---

## Phase 1 - Proof Gate  PASS

Created a detached, clean review worktree at the exact candidate SHA
(`C:\Users\Jeff0\kilo_review_r4c1_review_wt`), `git fetch --all --prune` run first.

| Check | Result |
|---|---|
| Remote tip `origin/zcode/...` == `f51c109` | OK `f51c10943b5d1a67569d681e66a6d56e728860b4` |
| `f51c109^` == `df7c8f15` | OK `df7c8f15435e6821a4f18fbb476b091761933f8d` |
| `9067e38f` is ancestor of candidate | OK `git merge-base --is-ancestor` true |
| Protected `origin/product-dev-recovered` == `9067e38f` | OK match |
| Protected `origin/main` == `134ea59e` | OK match |
| `df7c8f15..f51c109` modified files | OK exactly 5 (see authorized list) |
| `9067e38f..f51c109` cumulative paths | OK exactly the same 5 authorized paths |
| Unauthorized category change (backend/router/auth/config/lockfile/deploy/harness) | OK none (filtered diff returned empty) |
| Commits `df7c8f15..f51c109` | OK 1 (the candidate commit) |
| Commits `9067e38f..f51c109` | OK 4 |

**Authorized five files (both ranges identical):**
1. `frontend/src/components/layout/MainLayout.tsx`
2. `frontend/src/components/layout/Header.tsx`
3. `frontend/src/components/layout/Sidebar.tsx`
4. `frontend/src/tests/Pw1R4C1MainLayoutResponsive.test.tsx`
5. `ai-ledger/product-ai/2026-08-17_dc12r1_mvp_l1_pw1_r4_c1_responsive_main_layout.md`

No STOP triggered - SHA, ancestry, dirty-tree and scope all consistent.

---

## Phase 2 - F1 Visible-First-Landmark Review  PASS (source)

Frozen selector: `page.locator('main, [data-testid="dashboard"], nav, aside').first()`

Source facts (`MainLayout.tsx`):
- The in-flow content column (`<Header>` -> breadcrumb `<nav>` + `<main>`) now
  renders **before** `<Sidebar>` in DOM order (reversed from parent `df7c8f15`,
  which had `<Sidebar>` first).
- DOM order -> first frozen-selector match resolves to the **breadcrumb `<nav>`**
  (always visible, `flex min-w-0 flex-1`, no `display:none`), then `<main>`.
- Desktop `<aside>` is `hidden lg:flex w-64` (off at mobile) **and** appears after
  `nav`/`main` in DOM, so it can never be `.first()`. Verified by T10's
  `compareDocumentPosition` assertions and by **M7 mutation** (see Phase 5).
- Desktop fixed sidebar unchanged at `lg+`: content column keeps `lg:ml-64`,
  desktop `<aside>` keeps `inset-y-0 left-0 z-30 w-64 hidden lg:flex`. Zero visual
  change at `lg+` (fixed elements are position:fixed regardless of DOM order).
- Breadcrumb nav 0-width guard: the header uses **two `flex-1 min-w-0`** siblings
  (breadcrumb nav + tenant/user/logout group) that split free space; each uses
  `truncate`, so neither collapses to 0px nor forces page overflow at 390px. Source
  math: 390 - 32(px-4) - 40(hamburger) - 12(gap) ~= 306px => ~147px per `flex-1`
  group => "Dashboard" renders. (Exact 390px pixel layout is jsdom-host-limited;
  T9 validates the `min-w-0`+`truncate` shrink contract.)
- T10 exercises the **real** `MainLayout` DOM (renders `(MainLayout)` with
  `MemoryRouter`/`Routes`, queries `container.querySelector('main')`,
  `document.querySelector('aside')`, `screen.getByLabelText('Breadcrumb')`,
  `compareDocumentPosition`). It is not a source-string-only assertion.

**M7 reproduction:** reverting to Sidebar-first DOM order made **T10 RED**
(`asideFollowsNav` `expect(true)` failed). Restored byte-identically
(`git diff --quiet` clean).

**Non-blocking observation (F-OBS-1):** the DOM reorder changes desktop keyboard
focus order (main content now precedes the sidebar navigation links). All controls
remain reachable; this is a necessary consequence of the F1 mobile fix and is not
inaccessible. Recommend a skip-link / explicit tab ordering if strict nav-first
keyboard order is required for `lg+`.

---

## Phase 3 - F2 Mobile Logout Review  PASS (source)

Frozen locator: `button:has-text("Logout"), a:has-text("Logout"), [data-testid="logout"], [aria-label="Logout"]`

Source facts (`Header.tsx`):
- Header logout button: native `<button>`, `onClick={logout}` where
  `logout = useAuthStore((s) => s.logout)` - the **same** store action the Sidebar
  uses (no duplicate/auth-split path). `aria-label="Logout"`.
- Visible & actionable at every viewport: icon always shown; text label
  `hidden sm:inline` (icon-only below `sm`) - the button itself is never
  `display:none`, so it is the first DOM match and clickable at mobile.
- Keyboard accessible: native button, no `tabindex=-1`, not `disabled` (asserted in T11).
- Real `WholesalerRoute` reacts: `guards.tsx` - after logout `user==null &&
  accessToken==null` => `<Navigate to="/login" replace />`. T11 asserts
  `page-login` present, `page-home` absent.
- State cleared: `authStore.logout` sets `accessToken/refreshToken/user/tenantCode`
  to `null` (T11 asserts all three null).
- T11 uses the **real** `Header`, `MainLayout`, `useAuthStore`, `WholesalerRoute`.
- **M8 reproduction:** removing the Header logout button made **T11 RED**
  (`headerLogout.closest('header')` null). This proves T11 cannot pass through a
  mocked logout. Restored byte-identically.
- Desktop now has **two** Logout controls (header + shared SidebarBody in the
  desktop aside). Same real action. **Non-blocking observation (F-OBS-2):** mild
  visual redundancy on desktop; no functional/regression defect.
- Header non-overflow at 390px with long tenant/user: `flex min-w-0` + `truncate`
  on breadcrumb nav, tenant badge (`max-w-[6rem] sm:max-w-[10rem] truncate`, full
  value preserved via `title`) and user block (T9). Source-level; jsdom cannot do
  pixel layout (host-limited).

---

## Phase 4 - F3 Real Pointer Geometry Review  PASS (source)

Source facts (`Sidebar.tsx`):
- Mobile backdrop: `fixed inset-x-0 bottom-0 top-16 z-40` (starts **below** the
  64px sticky header, which is `sticky top-0 z-20 h-16`).
- Mobile drawer `<aside>`: `fixed bottom-0 left-0 top-16 z-50` - also starts at
  `top-16`, leaving the header row (and the hamburger) exposed. Parent `df7c8f15`
  used `inset-y-0`/`inset-0` (full height over the header) - confirmed by diff.
- Open drawer no longer covers the hamburger hit target: hamburger lives in the
  header band (0..64px); drawer begins at 64px, so the hamburger remains
  pointer-clickable. (Real hit-testing needs a browser - **host-limited**, see F-LIM-1.)
- Escape/backdrop/route-change close + focus restoration: unchanged
  (`MainLayout.tsx` `useEffect` on `location`, `keydown` Escape -> `hamburgerRef.focus()`,
  `closeDrawer` -> `hamburgerRef.focus()`). Verified by T4/T5/T6 in jsdom.
- Dashboard & orders exactly 390px wide without masking: no `overflow-x-hidden`,
  `overflow-hidden`, `overflow-clip`, or negative margin anywhere (scanned; T8
  asserts `container.innerHTML` excludes `overflow-x-hidden`/`overflow-hidden`).
- Drawer absent from DOM/a11y tree while closed: `{mobileOpen && (...)}` only;
  T2 asserts no `dialog`/`aside` and exactly one "Sales" link when closed.
- **aria-modal="true" with an interactive outside hamburger:** **Non-blocking
  observation (F-OBS-3).** The mobile drawer is `role="dialog" aria-modal="true"`
  yet the header hamburger (outside the dialog) remains interactive as an alternate
  close affordance. This is a minor ARIA-correctness nuance (aria-modal implies
  outside content is inert for AT), but it is **not** a genuinely inaccessible or
  misleading modal contract: Escape, backdrop and route-change also close the
  drawer, the hamburger has a real accessible name and is keyboard reachable, and
  closing restores focus to it. Classified non-blocking.

**M9 reproduction:** restoring full-height (`inset-y-0`) drawer coverage would
cause genuine pointer interception of the hamburger. This requires a real browser
hit-test (jsdom performs no layout); **not executable on the Kilo jsdom host**
(F-LIM-1). The source fix (`top-16` vs parent `inset-y-0`) is verified by diff.

---

## Phase 5 - Test Authenticity  PASS

- `git diff df7c8f15..f51c109 -- Pw1R4C1MainLayoutResponsive.test.tsx`: T1-T9 body
  **unchanged verbatim**; only the `describe()` label and header comment changed,
  and **T10 + T11** were added.
- T10/T11 are the **only** new unit nodes (11 `it()` blocks total; prior 9).
- No `.skip` / `.only` / `.todo` / `xfail` / retry-until-green / conditional pass /
  weakened assertion (scanned the file).
- No test branches on mutation flags.
- Natural vs shuffled independence: suite passes **11/11** in both natural and
  `--sequence.shuffle --sequence.seed=20260820` order (Phase 6).
- Full-suite growth reconciles exactly: **337 -> 339 = +2 (T10 + T11)** (Phase 6).
- Mutation restoration byte-equality: M7 (Sidebar-first -> T10 RED) and M8
  (remove Header logout -> T11 RED) each reverted; `git diff --quiet` confirms the
  candidate tree is byte-identical to `f51c109` after restore.

---

## Phase 6 - Runtime Gates On Kilo Host  PASS

Run from `frontend/` (deps installed via `pnpm install`; `vitest 1.6.1`, jsdom).

| Command | Expected | Obtained |
|---|---|---|
| `pnpm vitest run src/tests/Pw1R4C1MainLayoutResponsive.test.tsx` | 11/11 | **11/11** OK |
| `... --sequence.shuffle --sequence.seed=20260820` | 11/11 | **11/11** OK |
| `pnpm vitest run src/tests/Header.test.tsx src/tests/PrintableWorkspace.test.tsx src/tests/Pw1R2AuthSessionClosure.test.tsx` | 111/111 | **111/111** OK |
| `pnpm vitest run` | 23 files / 339 passed / 0 failed | **23 files / 339 passed / 0 failed** OK |
| `pnpm build` | exit 0 | **exit 0** OK |

The `337 -> 339` growth reconciles exactly with T10+T11. The focused
real-browser reproduction (11/11) and the authoritative 162-node matrix are
**out of Kilo scope** and were **not** run or claimed (F-LIM-4).

---

## Phase 7 - Evidence Truth  PASS

Ledger `ai-ledger/product-ai/2026-08-17_..._responsive_main_layout.md` (R1 addendum)
accurately records:
- Original Kilo C1 source review `ab58a6d71...` (PASS_FOR_CTO). OK
- Invalid OpenCode vitest-only PASS explicitly recorded as **historical invalid
  evidence** (`dce73f4c`, since replaced). OK
- Authoritative V2 STOP at `c7d880e3cbfcbab10e3b3fbcc160c9f3c980fc74` with F1/F2/F3
  blockers. OK (commit exists; message confirms it replaces the fabricated PASS.)
- F1/F2/F3 closure. OK
- Exact commands and counts (11/11, 111/111, 339, build exit 0). OK
- Exact five-file scope. OK
- Full **162/162 explicitly unclaimed** by this task. OK
- Next sequence documented: Zcode R1 -> Kilo bounded source review -> OpenCode
  pre-gates -> one authoritative 162-node run -> CTO decision. OK

No prose overstates native browser completion, merge readiness or deployment
readiness. The R1 verdict is explicitly `..._SOURCE_REVIEW`.

---

## Phase 8 - Quality  PASS

- `git diff --check df7c8f15..f51c109`: **clean** (no whitespace/trailing errors).
- `py_compile`: not applicable (authorized scope contains no Python).
- Scoped detect-secrets: `gitleaks` not installed on host (F-LIM-3); a scoped
  regex scan of the 5 files found **no real secret** (only ledger prose about
  removed identity artifacts); test credentials are explicitly
  `redacted-test-access-token` / `redacted-test-refresh-token`.
- Strict UTF-8 / no BOM / no mojibake: all 5 files `BOM=False`, `UTF8=OK`,
  no replacement char. OK
- `npx gitnexus analyze`: **success** (15,250 nodes / 45,702 edges).
- `npx gitnexus status`: indexed commit `f51c109` == current commit,
  **up-to-date**. `detect-changes` subcommand absent in installed CLI
  (per ledger) -> exact `git diff` proof used instead (5 authorized files only).
- Candidate detached worktree remains **clean** and byte-identical to `f51c109`
  (`git diff --quiet` true after M7/M8 restore).

---

## Findings

| ID | Category | Severity | Title | Status |
|---|---|---|---|---|
| F-OBS-1 | non_blocking_observation | low | Desktop keyboard focus order changed (content before sidebar nav) due to F1 DOM reorder | recorded |
| F-OBS-2 | non_blocking_observation | low | Two Logout controls on desktop (header + sidebar); redundant, same real action | recorded |
| F-OBS-3 | non_blocking_observation | low | `aria-modal="true"` while header hamburger (outside dialog) remains interactive | recorded (non-blocking) |
| F-LIM-1 | kilo_host_limitation | n/a | jsdom cannot hit-test -> M9 real-pointer F3 reproduction not executable; source fix (`top-16` vs parent `inset-y-0`) verified | recorded |
| F-LIM-2 | kilo_host_limitation | n/a | Exact 390px pixel layout not verifiable in jsdom; source math + T9 truncate contract support | recorded |
| F-LIM-3 | kilo_host_limitation | n/a | `gitleaks` not installed; scoped regex + redacted test creds used instead | recorded |
| F-LIM-4 | kilo_host_limitation | n/a | Focused real-browser repro (11/11) and authoritative 162-node matrix not run/claimed (per task scope) | recorded |

**No candidate source defect. No test false-green. No evidence inconsistency.**

---

## Accounting

| Bucket | Count |
|---|---|
| Candidate source defects | 0 |
| Test false-greens | 0 |
| Evidence inconsistencies | 0 |
| Kilo host limitations | 4 (F-LIM-1..4) |
| Non-blocking observations | 3 (F-OBS-1..3) |

**Accounting gap = 0.**

---

## Required Verdict

> **PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R4_C1_R1_V1_KILO_FINAL_REVIEW**

This is **source-review approval only**. The authoritative 162-node browser
matrix remains explicitly unclaimed and belongs to the agreed next sequence
(Kilo bounded source review -> OpenCode fresh-runtime pre-gates -> one
authoritative 162-node run -> CTO merge decision).
