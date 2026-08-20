# DC-12R1-MVP-L1-PW1-R4-C1-R1-V2 — Full Browser Independent Final (PASS_FOR_CTO / Evidence Ready)

**Task ID**: DC-12R1-MVP-L1-PW1-R4-C1-R1-V2
**Date**: 2026-08-20
**Executor**: opencode (browser evidence run)
**Verdict**: **PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R4_C1_R1_V2_BROWSER_EVIDENCE_READY**

---

## 1. Phase 1 — Proof Gate (PASS)

| Check | Result |
|---|---|
| Candidate branch `origin/zcode/dc12r1-mvp-l1-pw1-r4-c1-r1-browser-integration-closure-2026-08-20` | `f51c10943b5d1a67569d681e66a6d56e728860b4` OK |
| Detached clean worktree HEAD | `f51c109` (no tracked modifications) |
| Candidate parent | `df7c8f15…` (prior STOP candidate) |
| Product base `origin/product-dev-recovered` | `9067e38f83edb38fcdb53fb5d5eea7e75e85cf5f` OK |
| `origin/main` | `134ea59e02204842e55ebe36f721f44df5a33737` OK |
| Kilo review SHA | `5cff172a80f530c39036c61325dfa9090428d612` present OK |
| Harness SHA | `db84b1325c51a484af55029ce3485d9995b0669a` present OK |
| Ancestry | base is ancestor of candidate OK |
| Diff scope `9067e38f..f51c109` | exactly 5 authorized R4-C1 files OK |

Authorized 5-file diff: `frontend/src/components/layout/Header.tsx`,
`MainLayout.tsx`, `Sidebar.tsx`,
`frontend/src/tests/Pw1R4C1MainLayoutResponsive.test.tsx`,
`ai-ledger/product-ai/2026-08-20_dc12r1_mvp_l1_pw1_r4_c1_r1_browser_integration_closure.md`.

Harness tree restored byte-exact from `db84b13` (11 frozen files, LF, no BOM,
no `.only`/`.skip`/`.fixme`/`xfail`; `workers=1`, `retries=0`,
`fullyParallel=false`). Chromium `chromium-1217` present.

## 2. Phase 2 — Fresh Runtime (PASS)

| Component | Detail |
|---|---|
| PostgreSQL 16 | container `pw1r4c1r1v2_postgres`, `127.0.0.1:27443`, fresh anonymous volume, migrated base → head `037_payment_declarations_schema`, 0 identity rows before provisioning |
| Redis 7 | container `pw1r4c1r1v2_redis`, `127.0.0.1:27390`, empty keyspace at start |
| Backend | `uvicorn` on `127.0.0.1:8000` (PID 61744), `MPANGO_ENV=staging`, real `JwtAuthStrategy` (verified in structured logs) |
| Frontend | Vite on `127.0.0.1:5173` (PID 13708, `--strictPort`), candidate `f51c109` |
| SECRET_KEY | generated fresh `secrets.token_urlsafe(48)`, shared backend/provisioning, never logged, absent from all artifacts |
| Ports | 8000 / 5173 / 27443 / 27390 loopback task-exclusive |
| Health probes | backend `/health` 200, frontend `/health` 200 |
| Watchdog | armed (10-min no-progress → kills task-owned listeners) |
| Host-owner set | untouched (verified identical before/after: `dc12r1_mvp_l1_r0_*`, `mpango_*`, etc.) |

## 3. Phase 3 — Official Provisioning (PASS)

All four identities created exclusively through the official lifecycle
(signup → verify-email → owner setup-credential → login → select-tenant →
invitation → retailer registration → retailer credential setup), executed via
the task runtime against the candidate backend with the staging dev-sink used
only to capture single-use email tokens (no SMTP in staging; tokens random and
stored hashed). No SQL writes, no hand-written hashes, no copied historical
identities, no historical JWTs.

Canonical retailer names: **PW1R1 Retailer A** (ra), **PW1R1 Retailer B** (rb).

| Check | Result |
|---|---|
| W1/W2 admin login | 200, 1 tenant each |
| RA client login @W1 | 200 (multi-tenant identity, 2 available tenants) |
| RA client login @W2 | 200 |
| RB client login @W1 | 200 (single-tenant) |
| Retailer permissions (RA@W1) | exactly six server-derived `client:*` incl. `client:payments:declare` |
| Tenant schemas | W1 `t_1d832289…`, W2 `t_b107b683…` — 23 tables, roles `admin`+`retailer_operator`, 52 permissions |
| Negative paths | wholesaler wrong password 401 `INVALID_CREDENTIALS`; retailer portal wrong password 401 |

Provisioning steps: 0 failed (see `provision_evidence.json`). Live credentials
live only in task-private `identities.json` (never committed).

## 4. Phase 4 — Pre-Gates (ALL PASS)

| # | Gate | Result |
|---|---|---|
| 1 | Auth matrix 27/27 (9 tests × desktop/tablet/mobile, frozen unmodified) | **27/27** OK |
| 2 | Mobile drawer pre-gate 25/25 (real W1 @390×844) | **25/25** OK |
| 3 | Kilo carry-forward observations (F-OBS-1/2/3) | recorded OK |
| 4 | `phase2-identity.spec.ts:28` desktop stability ×10 | **10/10** OK |
| 5 | `playwright --list` | **162 tests in 7 files** OK |
| 6 | Harness purity (`workers=1`, `retries=0`, `fullyParallel=false`, no grep) | OK |

Historical reds on prior candidate `df7c8f15` (auth 25/27: F1 aside-before-main,
F2 hidden-aside logout; drawer 24/25: F3 drawer overlay blocking hamburger) are
all resolved by candidate `f51c109`:

- **F1** — content column now renders before the fixed aside; the frozen
  `auth-matrix.spec.ts:18` locator resolves to a visible element at mobile.
- **F2** — header-anchored Logout (`aria-label="Logout"`) is visible at mobile;
  `auth-matrix.spec.ts:118` clicks it and lands on `/login`.
- **F3** — drawer/backdrop geometry is `top-16` (starts below the sticky header),
  so the hamburger stays clickable while the drawer is open; the real-pointer
  hit-test in the drawer pre-gate passes.

## 5. Phase 5 — Authoritative Full Matrix (PASS)

| Metric | Value |
|---|---|
| Command | `npx playwright test` (all 3 projects, 1 worker, 0 retries, no grep, single run) |
| Nodes | 162 |
| Result | **162 passed (3.6m)** |
| JSON stats | `expected: 162, skipped: 0, unexpected: 0, flaky: 0` |
| JUnit (independent count) | 162 testcases, 0 failures, 0 errors, 0 skipped |

## 6. Phase 6 — Machine Evidence (PASS)

All required artifacts generated with strict UTF-8 (no BOM) and verified
independently from three sources (JSON, JUnit, CSV):

- `findings_full_162.csv` — exactly 162 data rows + header (independent row count
  from JSON spec enumeration and JUnit testcase count both agree).
- `reconciliation.json` — accounting gap `0`; all three counts equal 162.
- `failure_set.json` — empty (0 failures).
- `required_greens.json` — auth 27/27, drawer 25/25, stability 10/10, list
  162/7, full matrix 162 — all green.
- `verdict.json` — `PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R4_C1_R1_V2_BROWSER_EVIDENCE_READY`.

Kilo carry-forward observations recorded in `drawer_mobile_gate.json`:

- **F-OBS-1** desktop keyboard focus order (12 Tabs): header Logout → Home →
  Sales → Products → Stock → Finance → Payments → Customers → Pricing → sidebar
  Logout. Content-column navigation precedes the sidebar in DOM order; the
  first focused element is the header Logout.
- **F-OBS-2** two desktop Logout controls (header `aria-label="Logout"` + sidebar
  text button); both invoke the same real `useAuthStore.logout` action; both
  clear the persisted session and land on `/login` (verified by real click
  through both controls).
- **F-OBS-3** `aria-modal="true"` dialog with the outside header hamburger
  remaining interactive while the drawer is open (recorded, non-blocking).

## 7. Evidence Index (this commit)

`auth_matrix.json` · `full_browser.json` · `full_browser_junit.xml` ·
`findings_full_162.csv` (162 rows) · `reconciliation.json` ·
`failure_set.json` (empty) · `required_greens.json` · `test_list_162.txt` ·
`stability_gate.json` (10/10) · `drawer_mobile_gate.json` (25/25 + Kilo
observations) · `provisioning_steps_status.md` · `provision_evidence.json`
(no credentials) · `runtime_preflight.json` · `cleanup_closure.md` ·
`verdict.json` · `sha256_manifest.txt` (git-blob SHA-256 of every artifact,
manifest excluded).

Not committed (per task rules): `identities.json`, `.env`, SECRET_KEY, JWTs,
Authorization headers, provisioning/drawer/evidence-generation scripts.

## 8. Phase 8 — Cleanup (PASS, done before this commit)

- Task backend + frontend + watchdog stopped; ports 8000 / 5173 / 27443 / 27390
  released (0 listeners).
- `pw1r4c1r1v2_postgres` / `pw1r4c1r1v2_redis` removed **with their volumes**;
  network removed; 0 task containers/volumes/networks remaining.
- Task worktrees (`pw1r4c1r1v2_candidate`, `pw1r4c1r1v2_harness`) deregistered
  and directories removed; `git worktree prune` run.
- Host-owner container set identical before/after (name-set comparison).
- Protected refs unchanged at final check: candidate `f51c109`,
  `product-dev-recovered` `9067e38f`, `main` `134ea59e` (local == remote).
- Candidate untouched: no merge, no deploy, no product/harness source changes
  on this branch.

## 9. Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R4_C1_R1_V2_BROWSER_EVIDENCE_READY**

The authoritative 162-node browser matrix passed 162/162 on a fresh runtime with
formally provisioned identities and real JWT auth; all pre-gates green (auth
27/27, drawer 25/25, stability 10/10, list 162/7); the three historical mobile
defects (F1/F2/F3) from prior candidate `df7c8f15` are fixed; Kilo observations
carried forward without regression. Evidence is committed with this report and
the manifest is verified from committed git blobs. Per task rules this is an
evidence-ready PASS for CTO review — no merge, no deploy performed.