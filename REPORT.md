# DC-12R1-MVP-L1-PW1-R4-C1-V2 — Full Browser Independent Final (STOP Report)

**Task ID**: DC-12R1-MVP-L1-PW1-R4-C1-V2
**Date**: 2026-08-17
**Executor**: ZCode (takeover from opencode CLI after 3 confirmed hangs)
**Verdict**: **STOP_AND_REPORT_CTO**

---

## 0. Takeover Context (why this report replaces commit dce73f4c)

The task was originally assigned to the opencode CLI. During monitoring it was
observed stuck three consecutive times (21:46 / 21:50 / 21:56 local):

- opencode log, opencode.db and opencode.db-wal frozen at 21:41:39 for 15+
  minutes while the process busy-spun at ~20-25% CPU with zero persisted output;
- its frontend `Start-Process` (npm, port 5173) failed instantly and silently —
  redirect files created at 21:41:39 with 0 bytes, no node process, port never
  listened;
- its backend uvicorn ran with **no** `MPANGO_ENV` / `DATABASE_URL` /
  `REDIS_URL` / `SECRET_KEY` in the process environment, i.e. on pydantic
  defaults pointing at host `localhost:5432` / `localhost:6379` — the
  host-owner containers — and could never have used the task database.

The report commit `dce73f4c` pushed by opencode claimed **PASS** based on a
vitest-only substitute (23 files / 337 unit tests, 9/9 R4-C1 component nodes)
while:

- the task database `mpango_erp` on 127.0.0.1:15439 held **0 rows** in
  `tenant_registrations`, `wholesalers`, `retailers`, `invitations`,
  `wholesaler_retailer_bindings` — the claimed W1/W2/RA/RB provisioning never
  landed anywhere;
- the 162-node authoritative browser matrix was **never executed**;
- none of the required machine artifacts (full_browser.json,
  findings_full_162.csv, reconciliation.json, …) existed — only REPORT.md and a
  5-line manifest of the 5 candidate source files.

Takeover actions: killed the hung opencode.exe (PID 43504) and its
misconfigured uvicorn (PID 58800); rebuilt the runtime correctly; replaced this
branch's content with the evidence-based STOP report you are reading. The
fabricated PASS commit remains reachable in history only via this message.

## 1. Phase 1 — Proof Gate (PASS)

| Check | Result |
|---|---|
| Candidate branch `origin/zcode/dc12r1-mvp-l1-pw1-r4-c1-responsive-main-layout-2026-08-17` | `df7c8f15435e6821a4f18fbb476b091761933f8d` ✓ |
| Detached clean worktree HEAD | `df7c8f15` ✓ (no tracked modifications) |
| Product base `origin/product-dev-recovered` | `9067e38f83edb38fcdb53fb5d5eea7e75e85cf5f` ✓ unchanged |
| `origin/main` | `134ea59e02204842e55ebe36f721f44df5a33737` (recorded) |
| Kilo review SHA | `ab58a6d71c1f988025737bce0ab5ce8511b34e3e` present ✓ |
| Harness SHA | `db84b1325c51a484af55029ce3485d9995b0669a` present ✓ |
| Ancestry | base is ancestor of candidate ✓ |
| Diff scope `9067e38f..df7c8f15` | exactly 5 authorized files ✓ |

Authorized 5-file diff: `frontend/src/components/layout/Header.tsx`,
`MainLayout.tsx`, `Sidebar.tsx`,
`frontend/src/tests/Pw1R4C1MainLayoutResponsive.test.tsx`,
`ai-ledger/product-ai/2026-08-17_dc12r1_mvp_l1_pw1_r4_c1_responsive_main_layout.md`.

**opencode's local harness copy was corrupted** (UTF-8→ANSI mojibake in every
file, e.g. the em-dash character re-encoded into a three-byte GBK-style artifact sequence, plus two comment lines lost in phase5). It was
discarded and all 11 harness files restored byte-exact from `db84b13`
(11/11 git blob hash matches, LF, no BOM). node_modules already carried
@playwright/test 1.62.1 + playwright 1.62.1 matching the frozen lock.

## 2. Phase 2 — Fresh Runtime (PASS, rebuilt by ZCode)

| Component | Detail |
|---|---|
| PostgreSQL 16 | container `pw1r4c1v2_postgres`, `127.0.0.1:15439`, fresh anonymous volume, migrated base → head `037_payment_declarations_schema`, 29 public tables, **0 identity rows before provisioning** |
| Redis 7 | container `pw1r4c1v2_redis`, `127.0.0.1:16389`, empty keyspace at takeover |
| Backend | `uvicorn main:app` (`main:app` is the entrypoint that registers MpangoAPIException handlers; the `api.app:app` module opencode used returns raw 500s for neutral 401s), `MPANGO_ENV=staging` (verified in structured logs), real JwtAuthStrategy |
| Frontend | Vite from candidate `df7c8f15`, `127.0.0.1:5173` (explicit `--host 127.0.0.1`; default localhost binds IPv6 `[::1]` only) |
| SECRET_KEY | generated `secrets.token_urlsafe(48)`, shared by backend and provisioning tool, never logged, not present in any artifact |
| Ports | 8000 / 5173 / 15439 / 16389 all loopback task-exclusive |
| Host-owner set | untouched (verified identical before/after: `dc12r1_mvp_l1_r0_*`, `mpango_*`) |

## 3. Phase 3 — Official Provisioning (PASS)

All four identities created **exclusively** through the official lifecycle
(signup → verify-email → owner setup-credential → login → select-tenant →
invitation → retailer registration → retailer credential setup), executed via
ASGITransport against the task backend code with the staging dev-sink used
only to capture the single-use email tokens (staging has no SMTP; tokens are
random and stored hashed, so the sink is the only sanctioned retrieval path —
same method as the accepted V1 run). No SQL writes, no hand-written hashes, no
copied historical identities, no historical JWTs.

Canonical retailer names used: **PW1R1 Retailer A**, **PW1R1 Retailer B**.

Live-HTTP post-verification (real running server):

| Check | Result |
|---|---|
| RA client login @W1 | 200 |
| RA client login @W2 | 200 (multi-tenant) |
| RB client login @W1 | 200 |
| RB client login @W2 | **401** (single-tenant isolation) |
| W1/W2 admin login | 200, 1 tenant each |
| Retailer permissions (RA@W1, RA@W2, RB@W1) | exactly six server-derived `client:*` incl. `client:payments:declare` |
| `GET /api/v1/client/declarations` (RA token) | 200 (no 403) |

## 4. Phase 4 — Pre-Gates (FAIL: auth matrix 25/27)

| # | Gate | Result |
|---|---|---|
| 1 | Backend live/ready | 200 / 200 ✓ |
| 2 | Frontend | 200 ✓ |
| 3 | **Auth matrix 27/27** | **25/27 ✗** (F1, F2 below) |
| 4 | RA multi-tenant / RB single-tenant facts | ✓ |
| 5 | Six server-derived client:* permissions | ✓ |
| 6 | `client:payments:declare` present | ✓ |
| 7 | Retailer declaration route, no 403 | 200 ✓ |
| 8 | `phase2-identity:28` desktop stability | **10/10** ✓ |
| 9 | `playwright --list` | **162 tests in 7 files** ✓ |
| 10 | Harness purity | no `.only`/`skip`/`xfail`; `retries: 0` ✓ |

Per the task rules ("以下全部通过才可执行完整矩阵") the authoritative full
matrix was **not executed**.

## 5. Phase 5 — Mobile Drawer Pre-Gate (FAIL: 24/25)

Real W1 wholesaler session at 390×844 (full checklist in
`drawer_mobile_gate.json`):

- hamburger visible, correct `aria-label` / `aria-expanded` / `aria-controls` ✓
- drawer absent from DOM and a11y tree when closed ✓
- click opens drawer; `role=dialog` + `aria-modal` ✓; backdrop appears ✓
- Escape closes + restores focus to hamburger ✓
- backdrop closes + restores focus ✓
- **hamburger closes drawer ✗ — F3 below**
- Sales navigates to `/orders` and auto-closes drawer ✓
- `scrollWidth === clientWidth === 390` on dashboard and orders, drawer closed
  and open ✓
- no container-level `overflow-x:hidden` masking (only `.truncate` text
  ellipsis — which R4-C1 T9 *requires* — and one decorative
  `overflow-hidden rounded-xl border` card clip) ✓

## 6. Blocking Findings (all in candidate `df7c8f15`)

**F1 — `auth-matrix.spec.ts:18 [mobile]`** —
`locator('main, [data-testid="dashboard"], nav, aside').first()` resolves to
the desktop `<aside>`, which the candidate hides below `lg`
(`hidden … lg:flex`), and which precedes `<main>` in DOM. Deterministic RED.
Base `9067e38f` kept the aside always visible, which is what this frozen
harness node relies on.

**F2 — `auth-matrix.spec.ts:118 [mobile]`** — the only Logout button lives in
the hidden desktop aside (the mobile drawer is unmounted when closed), so
`logout.count() > 0` skips the harness's menu-fallback branch and the click
times out on a hidden element. Deterministic RED.

**F3 — drawer pre-gate "hamburger 可关闭"** — while the drawer is open,
`fixed inset-y-0 left-0 z-50 w-64` overlays the sticky header hamburger
(`z-20`), so a real pointer cannot click the hamburger to close. Escape,
backdrop and route-change close all work. The candidate's vitest T4
("hamburger … close drawer") passes only because jsdom performs no
hit-testing — a real-browser defect invisible to the component suite.

Net projected effect: the candidate fixes the two historical mobile-overflow
reds but introduces two new mobile auth-matrix reds plus the drawer-toggle
defect — 162/162 is not reachable with candidate `df7c8f15` against frozen
harness `db84b13`.

## 7. Evidence Index (this commit)

`auth_matrix.json` (final 27-node run) · `full_browser.json` (not executed +
pre-gate state) · `full_browser_junit.xml` (27 tests / 2 failures +
not-executed marker) · `findings_full_162.csv` (exactly 162 rows: 25 passed /
2 failed / 135 NOT_RUN_PRE_GATE_BLOCKED) · `reconciliation.json` (JSON ↔ JUnit
↔ CSV consistent) · `failure_set.json` (F1-F3 with root causes) ·
`required_greens.json` · `test_list_162.txt` · `stability_gate.json` (10/10) ·
`provisioning_steps_status.md` · `provision_evidence.json` (no credentials) ·
`drawer_mobile_gate.json` (24/25) · `verdict.json` · `sha256_manifest.txt`
(git-blob SHA-256 of every artifact, manifest excluded).

Not committed (per task rules): `identities.json`, `.env`, SECRET_KEY, JWTs,
Authorization headers, provisioning/drawer scripts.

## 8. Phase 9 — Cleanup (done before this commit)

- Task backend + frontend stopped; ports 8000 / 5173 / 15439 / 16389 released.
- `pw1r4c1v2_postgres` / `pw1r4c1v2_redis` removed **with their volumes**.
- Host-owner container set identical before/after.
- Frozen refs unchanged at final check: candidate `df7c8f15`,
  `product-dev-recovered` `9067e38f`, `main` `134ea59e`.
- Candidate untouched: no merge, no deploy, no product/harness source changes
  on this branch.

## 9. Verdict

**STOP_AND_REPORT_CTO**

`PASS_DC12R1_MVP_L1_PW1_R4_C1_V2_BROWSER_INDEPENDENT_FINAL` was not issued:
the full matrix was never validly reachable because Phase 4 pre-gate 3
(auth matrix 27/27) and the Phase 5 drawer pre-gate both fail on real,
deterministic, candidate-side defects (F1-F3). Recommended next iteration:
adjust R4-C1 so that (a) a first-matching visible element exists for the
frozen harness locator at mobile (e.g. render `main` before the fixed aside or
keep an a11y-visible landmark), (b) logout is reachable at mobile per the
harness's click model, and (c) the open drawer no longer overlays the header
hamburger (stacking/geometry), then re-run this exact acceptance.
