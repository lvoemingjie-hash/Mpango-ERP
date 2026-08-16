# DC-12R1-MVP-L1-PW1-R4-B — Browser Harness Truth Closure (Full Machine Evidence)

- **Verdict: `STOP_AND_REPORT_CTO`** (remaining red set = 8 nodes ≠ expected exactly 2; delta = 6 nodes, all one newly-unmasked **canonical-harness defect F6**, not a product regression at the merge base)
- Date: 2026-08-16 · Operator: opencode · Task: DC-12R1-MVP-L1-PW1-R4-B
- Merge base (product under test): `888683ba23c14b48a102289a29f9b7adf674fdaf` (origin/product-dev-recovered; includes R4-A fix `f348f4a`)
- Canonical harness source: `d787c58` (harness lived at `pw1r1/`; removed at `888683ba`; extracted verbatim)
- Accepted failing baseline (R3-V2): branch `ad5de63`, report `2026-08-15_dc12r1_mvp_l1_pw1_r3_v2_full_browser_machine_evidence_final.md` (133P/29F)

## 1. Protocol compliance

- Fresh task-owned runtime: PG `127.0.0.1:25432` (compose project `pw1r4b_runtime_122117`), Redis `26379`, new random `SECRET_KEY` (task-private `.env`, never committed/printed), `MPANGO_ENV=staging`, real `JwtAuthStrategy`, `EMAIL_PROVIDER=dev_sink`.
- Schema: alembic head `037_payment_declarations_schema` + `bootstrap_tenant_schema.py t_dev` at `888683ba`.
- Identity provisioning: supported product lifecycles only (signup→verify→setup-credential, invitations, retailer register→setup-credential; no SQL inserts, no hand-written hashes). Canonical PW1R1 identities: `pw1r3.{w1,w2,ra,rb}.r1@pw1r3.dev` — W1/W2 admin (1 tenant each), RA multi-tenant (W1+W2), RB single-tenant (W1). Client logins + wrong-password 401 negative proofs: all asserted 200/201/401 as expected.
- Harness corrections: **F1/F3/F4 only**, applied before the single invocation (diff artifact: `..._evidence/pw1r4b_harness_corrections.diff`; exactly 4 files differ from canonical — `tests/helpers.ts`, `tests/phase1-routes.spec.ts`, `tests/phase4-retailer.spec.ts`, `tests/phase5-isolation.spec.ts`; `playwright.config.js` and `package.json` are byte-identical: baseURL 5173, workers 1, **retries 0**, projects desktop/tablet/mobile, chromium-1217).
- Inventory preserved: `npx playwright test --list` = **162 tests / 7 files** (auth-matrix 27, phase1 24, phase2 15, phase3 33, phase4 21, phase5 21, phase6 21). List artifacts committed.
- Gates before the run: backend `/health/ready` 200 (DB+Redis healthy); frontend `http://127.0.0.1:5173/` serves the SPA shell (`<div id="root">`); **auth matrix gate 9/9 passed (13.1 s)**.
- **Exactly ONE full invocation** of all 162 nodes (256,887 ms ≈ 4.3 m, 1 worker, 0 retries, no skips, no Redis mutation, no XFF spoofing). No harness file was modified after the run.

## 2. Result of the single full run

**154 passed / 8 failed / 0 skipped** (machine JSON + JUnit + full console committed; SHA-256 in manifest §6).

| # | Node | Viewport | Failure | Category |
|---|------|----------|---------|----------|
| 103 | phase4-retailer.spec.ts:70 `financial idempotency: repeated declaration … ZERO extra writes` | desktop | first declare → 400 `DECLARATION_METHOD_INVALID` (request_id `bb9b3142-cbd7-46ed-9d2f-a8518a7b9f4a`) | **F6** |
| 104 | phase4-retailer.spec.ts:118 `UI double-click on declare submit creates exactly one declaration` | desktop | order ok, declare never created → `afterCount − beforeCount = 0 ≠ 1` (spec:149) | **F6** |
| 110 | phase4-retailer.spec.ts:70 | tablet | 400 `DECLARATION_METHOD_INVALID` (request_id `50fa410f-abc6-40e7-9104-11bcc77a6eed`) | **F6** |
| 111 | phase4-retailer.spec.ts:118 | tablet | same downstream zero-write | **F6** |
| 117 | phase4-retailer.spec.ts:70 | mobile | 400 `DECLARATION_METHOD_INVALID` (request_id `157b0dfa-f919b-47b8-9f1c-3d2d901ae7e7`) | **F6** |
| 118 | phase4-retailer.spec.ts:118 | mobile | same downstream zero-write | **F6** |
| 156 | phase6-responsive.spec.ts:17 `wholesaler dashboard: no horizontal overflow…` | mobile | overflow `scrollWidth−clientWidth = 375` (R3-V2: 374) | **F5** (expected) |
| 157 | phase6-responsive.spec.ts:25 `wholesaler orders page: no horizontal overflow` | mobile | overflow = `347` (R3-V2: 346) | **F5** (expected) |

## 3. Reconciliation vs accepted R3-V2 baseline (29F → 8F)

| R3-V2 category | R3-V2 | R4-B | Disposition |
|---|---|---|---|
| F1 `ORDER_VALIDATION_FAILED` (order-create 400 "Some items cannot be ordered": phase4 ×12 nodes, phase5 ×6 nodes) | 18 | **0** | **Harness correction F1 confirmed effective.** Orders now created through supported lifecycles: `POST /api/v1/inventory/adjust` (perm `inventory:update`) + `PUT /api/v1/pricing/prices` (perm `pricing:write`) + `GET /api/v1/retailers` lookup; RB qty 1000 @ 42.50, RA qty 100 @ 10.00. 12 of 18 nodes now fully green. |
| F2 `InvalidCachedStatementError` → 500 (phase5 cross-tenant ×3) | 3 | **0** | **R4-A product fix (`f348f4a`, `prepared_statement_cache_size: 0`) independently confirmed by browser-harness evidence.** |
| F3 missing-header vs malformed-token taxonomy (×3) | 3 | **0** | Harness correction F3 confirmed (distinct `UNAUTHENTICATED` / `INVALID_TOKEN` assertions at phase5). |
| F4 locator strict-mode violation (phase1 public auth pages ×3) | 3 | **0** | Harness correction F4 confirmed (unique semantic locator `form button[type="submit"]`). |
| F5 mobile horizontal overflow (phase6:17/:25) | 2 | **2** | Product defect unchanged (375/347 px vs 374/346 in R3-V2; +1 px drift, same defect). |
| **F6 (new)** declaration method invalid (phase4:70/:118 ×3 viewports) | 0* | **6** | *Masked in R3-V2: those 6 nodes were part of F1×18 — they failed earlier at the order-create precondition (R3-V2 harness lines 66/113, 400 `ORDER_VALIDATION_FAILED`, e.g. request_id `521f713f-…`). The F1 fix unmasked them. See §4. |

Gate arithmetic: expected remaining red = F5×2 = **2**; actual = **8**; delta 6 = F6. Per task rules → **STOP_AND_REPORT_CTO**. No post-hoc harness edit, no rerun.

## 4. F6 root cause (canonical harness defect, present since d787c58 — not a merge-base regression)

- Canonical payload (d787c58 `pw1r1/tests/phase4-retailer.spec.ts:71`, byte-identical semantics in R4-B at `:79` — untouched by F1/F3/F4 corrections):
  `{ declared_amount: '150.00', method: 'mobile_money', transfer_reference: 'PW1R1-IDEM-001' }`
- Product enum, `backend/services/payment_declaration_service.py:45` — identical at **d787c58, 2b7b959 (R3-V2 candidate) and 888683ba**:
  `ALLOWED_DECLARATION_METHODS = {"cash", "transfer"}`
- Therefore `method: 'mobile_money'` was **never valid at any inspected commit**: the canonical PW1-R1 harness could not have passed these 6 nodes against its own contemporary product. The defect was invisible in R3-V2 only because F1 (missing stock/price provisioning) failed the tests one step earlier.
- Post-F1 execution path: order create now 201 → `POST /client/orders/{id}/declare` with `X-Declaration-Idempotency-Key` → 400 `DECLARATION_METHOD_INVALID` ("Declaration method must be one of: cash, transfer") → idempotency test dies at first declare (spec:92); double-click test survives (UI flow) but produces zero declarations → count assertion fails (spec:149).
- Not corrected in R4-B: the task authorized corrections F1/F3/F4 only; a payload change is a new correction (F6) requiring CTO sign-off, and the one-shot protocol forbids fix-and-rerun within this task.

## 5. Recommended CTO decision

- **Option A (recommended): authorize R4-B2** — single-line F6 correction `method: 'mobile_money'` → `'transfer'` (faithful: keeps `transfer_reference` required-and-meaningful; note `'cash'` would silently NULL the reference, service lines 99–118), then ONE fresh full 162-node rerun under the same protocol. Expected terminal state: 160P/2F (F5 only) → `PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R4_B_R4_C_PLANNING`, unblocking R4-C planning.
- **Option B (not recommended): accept F6 as documented harness-defect red** and proceed to R4-C with 154/8 + this report. Leaves 6 red nodes unowned by the product and keeps the canonical harness unrunnable at its own commit.

## 6. Evidence manifest (all on this branch)

| File | Content |
|---|---|
| `..._evidence/pw1r4b_full_browser.json` | Playwright machine JSON of the single full run (154P/8F) |
| `..._evidence/pw1r4b_full_browser_junit.xml` | JUnit for the same run |
| `..._evidence/pw1r4b_full_browser_console.txt` | Full console transcript (list reporter) |
| `..._evidence/pw1r4b_test_list_162.json` / `..._junit.xml` | Pre-run inventory: 162 tests / 7 files |
| `..._evidence/pw1r4b_harness_corrections.diff` | Canonical d787c58 → R4-B corrected harness (4 files; config/package identical) |
| `..._evidence/provision_evidence_r4b.json` | Provisioning steps (statuses asserted; no secrets) |
| `..._findings.csv` | Full 162-node inventory with status + failure category (6×F6, 2×F5, 0 unclassified) |
| `harness/pw1r4b/` | Corrected harness as run (tests + config + package files). **`provision/identities.json` (passwords/JWTs) intentionally excluded and never committed.** |

Integrity: single invocation; no skips/retries/conditional passes; runtime fresh and task-owned; secrets scan performed over the committed tree (`.env` values, identity passwords, tokens — none present).

## 7. Ops notes (for future task runners)

- **Vite launch trap (root cause of recurring false "frontend down"):** `npm run dev` binds `localhost` → `::1` (IPv6 only) while health checks probe `127.0.0.1`. Always launch with `node node_modules/vite/bin/vite.js --port N --host 127.0.0.1 --strictPort` (log via redirect). This session's 5173 listener was verified by parent cmdline + served-HTML match against `pw1r4b_worktree/frontend`.
- Zombie vite instances from earlier tasks (ports 5174/5175, incl. `candidate_worktree_pw1r2`) were found and killed before the run; port map verified clean (5173 only).
- Playwright project name is `desktop` (not `desktop-chrome`); machine reporters via env `PLAYWRIGHT_JSON_OUTPUT_NAME` / `PLAYWRIGHT_JUNIT_OUTPUT_NAME`; PowerShell 5.1 lacks `-SkipHttpErrorCheck` (use `--src-prefix/--dst-prefix` with `git diff --no-index` for clean diffs); GBK console → `PYTHONIOENCODING=utf-8`.

— END OF REPORT (R4-B stops here per protocol; Kilo/CTO review precedes any R4-C planning.) —
