# DC-12R1-MVP-L1-PW1-R4-B2 — Declaration Harness Payload Correction (Full Machine Evidence)

- **Verdict: `STOP_AND_REPORT_CTO`** — run result **157 passed / 5 failed** ≠ expected 160/2. The authorized one-line fix cleared F6a completely (phase4:70 ×3 → green); the 3-node delta is **F6b, a second latent canonical-harness defect** (UI double-click test never fills the required Amount field), predicted and documented BEFORE the run, not authorized for correction in B2.
- Date: 2026-08-16 · Operator: opencode · Task: DC-12R1-MVP-L1-PW1-R4-B2
- Product under test: `888683ba23c14b48a102289a29f9b7adf674fdaf` (verified: `git diff 888683ba HEAD -- backend/ frontend/` empty; worktree clean on tracked paths)
- Baseline: R4-B evidence `4f34c17fcf3e09d0f12595fe1d5c2f15b5447711` (154P/8F); branch cut from `4f34c17` as required.

## 1. Authorized change — proof of scope (step 2 of protocol)

`git diff` (entire worktree, vs `4f34c17`) is EXACTLY one line:

```diff
-    const payload = { declared_amount: '150.00', method: 'mobile_money', transfer_reference: 'PW1R1-IDEM-001' };
+    const payload = { declared_amount: '150.00', method: 'transfer', transfer_reference: 'PW1R1-IDEM-001' };
```

- `transfer_reference` value and all assertions preserved (same payload key, same `PW1R1-IDEM-001`, same idempotency-key logic).
- `git grep mobile_money -- pw1r4b/` → no residual occurrences.
- `git diff --check` → clean (no whitespace damage). No backend/frontend product file touched.

## 2. Protocol compliance

- Fresh task-owned runtime: compose project `pw1r4b2_runtime_233517` (PG 25432 / Redis 26379, both `healthy` before use), **new random SECRET_KEY** (rotated; `.env` task-private, never printed/committed), `MPANGO_ENV=staging`, real `JwtAuthStrategy`, `dev_sink` email.
- Schema: alembic head + `scripts/bootstrap_tenant_schema.py t_dev` (19 tables) at 888683ba, exit 0.
- Backend `http://127.0.0.1:8000/health/ready` → 200 (DB+Redis healthy); frontend launched with the corrected invocation `node node_modules/vite/bin/vite.js --port 5173 --host 127.0.0.1 --strictPort` → 200, SPA shell `<div id="root">` present.
- Canonical provisioning via supported lifecycles (no SQL inserts): W1/W2 admin, RA multi-tenant (2 tenants), RB single-tenant; negative 401 proofs asserted. All steps asserted 200/201/401.
- **Auth matrix gate: 9/9 passed (12.5 s).**
- **Inventory: `--list` = 162 nodes / 7 files** (junit artifact committed).
- **Exactly ONE authoritative full run**: 162 nodes, 1 worker, retries=0, 256 s ≈ 4.2 m. No skips, no reruns, no harness edits after start.

## 3. Result of the single full run — accounting gap = 0

Machine-derived: **total 162 = 157 passed + 5 failed + 0 skipped** (gap 0). Findings CSV committed (162 rows).

| Node | Viewport | Result | Category |
|---|---|---|---|
| phase4-retailer.spec.ts:70 `financial idempotency…` | desktop/tablet/mobile | **PASS ×3** | **F6a FIXED by authorized line** (was 400 `DECLARATION_METHOD_INVALID` in R4-B) |
| phase4-retailer.spec.ts:118 `UI double-click…exactly one declaration` | desktop/tablet/mobile | **FAIL ×3** — `Expected: 1, Received: 0` (net new declarations) | **F6b** (see §4) |
| phase6-responsive.spec.ts:17 dashboard overflow | mobile | FAIL — overflow 381 px (R4-B 375, R3-V2 374) | **F5** (known, unchanged) |
| phase6-responsive.spec.ts:25 orders overflow | mobile | FAIL — overflow 353 px (R4-B 347, R3-V2 346) | **F5** (known, unchanged) |

F5 assertions were NOT modified, skipped, or relaxed (diff proof §1 — the only changed line is the payload).

## 4. F6b root cause (canonical harness defect since d787c58 — NOT a product defect, NOT authorized in B2)

- The double-click test (canonical d787c58 `pw1r1/tests/phase4-retailer.spec.ts:110`, byte-identical in R4-B/B2 at `:118`) clicks `button[type="submit"]` **without filling the required Amount input**.
- Product guard: `frontend/src/pages/client/DeclarePaymentPage.tsx:49` — `if (!orderId || !amount) return;` with `<input id="amount" … required>` (line 86). Empty amount → `handleSubmit` returns before any POST → zero declare requests → `afterCount − beforeCount = 0 ≠ 1`.
- History: the node has **never passed against any product commit** — canonical R1 run aborted in stage 1 (7P/2F, 153 nodes blocked; `PW1_R1_RESULTS.json`), and in R3-V2/R4-B the same nodes failed earlier at the order-create precondition (F1), masking F6b. The B2 payload fix removed F6a at `:70` but `:118` drives the UI form (default `method='cash'`, valid) — its failure is purely the missing Amount fill.
- Correction requires CTO authorization (out of B2 scope): one line before the clicks, e.g. `await page.fill('#amount', '150.00');` — semantic: user fills the form, then double-clicks submit.

## 5. Recommended CTO decision

- **Option A (recommended): authorize R4-B3** — single-line addition `await page.fill('#amount', '150.00');` before the first submit click in `:118`; ONE fresh full rerun under the same protocol. Expected terminal: **160 passed / 2 failed (F5 only)** → `PASS_FOR_CTO_DC12R1_MVP_L1_PW1_R4_B2_R4_C_PLANNING_REVIEW` semantics, unblocking R4-C planning (F5 product fix).
- **Option B (not recommended): accept 157/5** with F6b documented; leaves 3 red nodes unowned and the canonical double-click idempotency proof unexecuted forever.

## 6. Evidence manifest (this branch)

| File | Content |
|---|---|
| `..._evidence/pw1r4b2_full_browser.json` / `_junit.xml` / `_console.txt` | Machine JSON / JUnit / full console of the single run |
| `..._evidence/pw1r4b2_test_list_162.json` / `_junit.xml` | Pre-run inventory (162 nodes) |
| `..._evidence/provision_evidence_r4b2.json` | Provisioning steps (asserted statuses; no secrets) |
| `..._findings.csv` | 162-row findings (5 red: 3×F6b, 2×F5; 0 unclassified) |
| `pw1r4b/tests/phase4-retailer.spec.ts` | Corrected harness incl. the authorized one-line change |

Excluded: `pw1r4b/provision/identities.json` (passwords/tokens — never committed), runtime `.env`.

## 7. Integrity checks (step 8 of protocol)

- Secrets: staged-content scan for `SECRET_KEY=`/JWT `eyJ`/`mpango123`/password prefixes — only pre-existing base-commit hits plus the canonical forged-token literal in `phase2-identity.spec.ts:32` (test fixture, not a secret). No runtime values committed.
- UTF-8/mojibake: report/CSV authored UTF-8; console log retains GBK-console artifacts of the run environment (verbatim evidence, unmodified).
- `git diff --check`: clean.
- Resource teardown: backend :8000 and vite :5173 stopped; compose project `pw1r4b2_runtime_233517` removed with volumes; ports 8000/5173/25432/26379 verified free. (Transcript appended post-teardown.)

— END OF REPORT (R4-B2 stops here per protocol; Kilo reviews R4-B/B2 harness truth before any R4-C product work.) —
