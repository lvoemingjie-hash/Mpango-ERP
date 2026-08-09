# DC-12R1-S3-S2B-I2C-I2-R1 Kilo Debug Final Source Review

- **Verdict:** `STOP_AND_REPORT_CTO`
- **Review type:** Independent adversarial source and test-authenticity review
- **Base SHA:** `4d97df5963a391a8d16d19988868234fd0d86648`
- **Candidate SHA:** `e23fc70bf0339b16f1850a9ebe07f3d7b731f357`
- **Report SHA:** `PENDING_FINAL_PUSH_SHA`
- **Candidate ref:** `origin/zcode/dc12r1-s3-s2b-i2c-i2-printable-workspace-2026-08-09`
- **Report branch:** `reports/dc12r1-s3-s2b-i2c-i2-r1-kilo-debug-review-2026-08-09`
- **Runtime execution status:** Not used for source-review conclusions. Local frontend runtime execution was not available in this review worktree because `pnpm vitest run src/tests/PrintableWorkspace.test.tsx` failed with `Command "vitest" not found` before dependency installation.

## 1. Proof gate

### 1.1 Ref and lineage proof
- `git fetch --all --prune` completed.
- `origin/zcode/dc12r1-s3-s2b-i2c-i2-printable-workspace-2026-08-09` resolved exactly to `e23fc70bf0339b16f1850a9ebe07f3d7b731f357`.
- Expected base resolved exactly to `4d97df5963a391a8d16d19988868234fd0d86648`.
- `git merge-base --is-ancestor 4d97df5963a391a8d16d19988868234fd0d86648 e23fc70bf0339b16f1850a9ebe07f3d7b731f357` returned success.
- Candidate parent lineage is exact single-parent lineage: `e23fc70bf0339b16f1850a9ebe07f3d7b731f357 4d97df5963a391a8d16d19988868234fd0d86648`.

### 1.2 Isolated review checkout
- Source review used detached worktree `C:\Users\Jeff0\AppData\Local\Temp\kilo\dc12r1_i2c_i2_review` at `e23fc70bf0339b16f1850a9ebe07f3d7b731f357`.
- Final source-review worktree remained byte-clean: `git status --short` empty at candidate SHA.

### 1.3 Exact delta accounting
Observed delta from base to candidate:
- **18 files changed**
- **9 new**
- **9 edited**
- **1649 insertions / 6 deletions**

#### New (9)
1. `ai-ledger/product-ai/2026-08-09_dc12r1_s3_s2b_i2c_i2_printable_workspace.md`
2. `frontend/src/pages/print/DeclarationPrintPage.tsx`
3. `frontend/src/pages/print/OrderPrintPage.tsx`
4. `frontend/src/pages/print/ReceiptPrintPage.tsx`
5. `frontend/src/styles/print.css`
6. `frontend/src/tests/PrintableWorkspace.test.tsx`
7. `frontend/src/types/print.ts`
8. `frontend/src/utils/printError.ts`
9. `frontend/src/utils/printFormat.ts`

#### Edited (9)
1. `frontend/src/main.tsx`
2. `frontend/src/pages/client/DeclarationHistoryPage.tsx`
3. `frontend/src/pages/client/OrderDetailPage.tsx`
4. `frontend/src/pages/finance/DeclarationQueuePage.tsx`
5. `frontend/src/pages/orders/OrderListPage.tsx`
6. `frontend/src/router/AppRouter.tsx`
7. `frontend/src/services/clientOrderService.ts`
8. `frontend/src/services/declarationService.ts`
9. `frontend/src/services/orderService.ts`

### 1.4 Forbidden-scope proof
No delta entries were found in backend, migrations, permissions, configuration, dependency manifests, lockfiles, deployment files, `PROJECT.md`, `CTO_CURRENT_OPS.md`, `package.json`, `pnpm-lock.yaml`, or `.secrets.baseline`.

### 1.5 Insert/delete detail
| File | + | - |
|---|---:|---:|
| ai-ledger/product-ai/2026-08-09_dc12r1_s3_s2b_i2c_i2_printable_workspace.md | 152 | 0 |
| frontend/src/main.tsx | 2 | 0 |
| frontend/src/pages/client/DeclarationHistoryPage.tsx | 22 | 1 |
| frontend/src/pages/client/OrderDetailPage.tsx | 13 | 2 |
| frontend/src/pages/finance/DeclarationQueuePage.tsx | 36 | 2 |
| frontend/src/pages/orders/OrderListPage.tsx | 11 | 1 |
| frontend/src/pages/print/DeclarationPrintPage.tsx | 190 | 0 |
| frontend/src/pages/print/OrderPrintPage.tsx | 171 | 0 |
| frontend/src/pages/print/ReceiptPrintPage.tsx | 156 | 0 |
| frontend/src/router/AppRouter.tsx | 14 | 0 |
| frontend/src/services/clientOrderService.ts | 8 | 0 |
| frontend/src/services/declarationService.ts | 39 | 0 |
| frontend/src/services/orderService.ts | 8 | 0 |
| frontend/src/styles/print.css | 66 | 0 |
| frontend/src/tests/PrintableWorkspace.test.tsx | 518 | 0 |
| frontend/src/types/print.ts | 112 | 0 |
| frontend/src/utils/printError.ts | 51 | 0 |
| frontend/src/utils/printFormat.ts | 80 | 0 |

## 2. GitNexus review

### 2.1 Index status
- `npx gitnexus analyze` completed successfully in the isolated review worktree.
- `npx gitnexus status` reported repo `dc12r1_i2c_i2_review` as up-to-date at candidate commit `e23fc70`.

### 2.2 detect_changes limitation
- This CLI build exposes `analyze/index/serve/mcp/list/status/clean/wiki/augment/query/context/impact/cypher`.
- `detect_changes` is not available in the installed CLI surface, so exact `git diff` plus GitNexus `query/context/impact` was used as the review fallback.

### 2.3 GitNexus impacts and flows reviewed
- `sanitizePrintError` upstream impact: **LOW**, 4 direct dependants, all inside the new print surface plus `PrintableWorkspace.test.tsx`.
- `formatKes` upstream impact: **LOW**, 4 direct dependants, all inside the new print surface plus `PrintableWorkspace.test.tsx`.
- `normalizeApiError` upstream impact: **HIGH**, 17 impacted nodes / 10 direct callers across Client, Skus, and Tenants. It was **reused without any edit**, satisfying the reuse constraint.
- `confirmDeclaration` context: caller `frontend/src/pages/finance/DeclarationQueuePage.tsx:handleConfirm`; process `DeclarationQueuePage → ConfirmDeclaration`.
- Query evidence linked the candidate UI to existing backend print flows for client declaration printing and receipt models.

### 2.4 Effective review radius
Reviewed within HIGH effective radius:
- all six print service functions
- `OrderPrintPage`
- `DeclarationPrintPage`
- `ReceiptPrintPage`
- `sanitizePrintError`
- `printFormat` money/date handling
- cashier confirmation receipt-link flow
- `AppRouter` print-route ownership
- d=1 callers outside the print pages where relevant (`confirmDeclaration`, `normalizeApiError`)

## 3. Correctness matrix

| Area | Result | Notes |
|---|---|---|
| A. API and route ownership | **Source pass; test gap** | All six print services are GET-only and path IDs are encoded. Static `mode` routes exist under `RetailerRoute`/`ClientLayout` and `WholesalerRoute`/`MainLayout`. New tests do **not** verify guard ownership. |
| B. Financial display integrity | **Pass** | New print path keeps monetary values as strings and uses `formatKes`/`formatDecimalMoney`; no print-path numeric recomputation found. |
| C. Declaration vs receipt truth | **Pass** | Pending/rejected declaration view renders `non_receipt_notice` verbatim and does not title itself as a receipt. Receipt page uses Contract C only. |
| D. Cashier flow | **Fail** | Receipt link source uses `resp?.data?.id ?? id`, which falls back to request-supplied ID instead of requiring response-authoritative ID. |
| E. Error boundary | **Pass** | `sanitizePrintError` maps only on HTTP status and never reads response body fields. |
| F. Print behavior and UX | **Pass** | Each print page calls `window.print()` once, does not mutate state on print, and uses safe back links and print CSS. |
| G. Scope exclusions | **Pass** | No Contract D / mutation / migration / backend-write additions in the diff. |

## 4. Findings

### P1 — Cashier receipt link is not strictly response-authoritative
- **File:** `frontend/src/pages/finance/DeclarationQueuePage.tsx:55-62`
- **Evidence:** `setConfirmedReceiptId(resp?.data?.id ?? id);`
- **Why it matters:** Directive D requires the receipt link to use the declaration ID returned by the single existing confirmation response, with **no** fixed, stale, request-supplied, or pre-confirmation fallback. This code explicitly falls back to the request parameter `id`.
- **Impact:** If the response shape drifts, is partially malformed, or is adapted through an intermediate layer, UI can still surface a receipt link built from a request-supplied identifier rather than fail closed.
- **Classification:** `P1`

### P1 — Required cashier receipt-link authenticity proof is missing
- **Files:**
  - `frontend/src/tests/PrintableWorkspace.test.tsx:18-37`
  - `frontend/src/tests/PrintableWorkspace.test.tsx:65-77`
- **Evidence:** Test file imports only service helpers and print pages; it never imports/renders `DeclarationQueuePage` and never exercises `confirmDeclaration` or the post-confirmation receipt-link behavior.
- **Why it matters:** Directive Phase 4 requires proof that a fixed confirmation ID causes a cashier receipt-link test to fail. No such test exists, so the claimed invariant is false-green.
- **Classification:** `P1`

### P1 — Route ownership authenticity proof is missing for the new print routes
- **File:** `frontend/src/tests/PrintableWorkspace.test.tsx:65-77`
- **Evidence:** Tests mount ad-hoc `<Routes>` directly to print-page components instead of exercising `AppRouter`, `RetailerRoute`, or `WholesalerRoute` ownership for the new print routes.
- **Why it matters:** Directive Phase 4 requires route tests that genuinely exercise existing guard ownership rather than only checking source strings. Current tests cannot fail if a print route is moved outside the intended guards while the page components themselves remain unchanged.
- **Classification:** `P1`

### INFO — Local runtime evidence was unavailable in this review worktree
- **Evidence:** `pnpm vitest run src/tests/PrintableWorkspace.test.tsx` failed with `Command "vitest" not found` before dependency installation.
- **Classification:** `INFO`

## 5. Test-authenticity matrix

| Required proof | Status | Evidence |
|---|---|---|
| Six services distinguishable; endpoint swap fails | **PASS (source/test inspection)** | Service endpoint assertions exist at `PrintableWorkspace.test.tsx:174-215`. |
| Duplicate loading causes request-count failure | **PASS (source/test inspection)** | Request-count assertions exist at `:178`, `:185`, `:192`, `:199`, `:206`, `:213`, `:240`, `:383`. |
| POST/PUT/PATCH/DELETE introduction fails | **PASS (source/test inspection)** | Explicit no-write assertions at `:242-245`, `:358`, `:385-388`. |
| Number conversion breaks high-precision tests | **PASS (source/test inspection)** | High-precision expectations at `:265-272`, `:449-474`. |
| Raw backend-message rendering breaks sanitizer tests | **PASS (source/test inspection)** | Neutral-copy and non-leak assertions at `:274-307`, `:407-442`, `:481-518`. |
| Fixed confirmation ID breaks cashier receipt-link test | **FAIL / MISSING** | No `DeclarationQueuePage` confirm-to-receipt-link test exists anywhere in `frontend/src/tests`. |
| Removing `encodeURIComponent` breaks path test | **PASS (source/test inspection)** | Dynamic path encoding assertion at `:217-221`. |
| Calling `window.print` twice breaks print-count test | **PASS (source/test inspection)** | Single-call assertions at `:255-262`, `:361-367`, `:398-404`. |
| Pending/rejected positive receipt presentation fails | **PASS (source/test inspection)** | Pending/rejected declaration assertions at `:314-369`. |
| Route tests exercise real guard ownership | **FAIL / MISSING** | `PrintableWorkspace.test.tsx:65-77` mounts local routes only; no print-route guard test uses `AppRouter`/guards. |

## 6. Quality checks

- `git diff --check` on base..candidate: clean.
- Replacement-character mojibake scan (`rg "�"`) on changed files: no hits.
- Scoped `detect-secrets-hook --baseline .secrets.baseline` over changed files: clean.
- GitNexus analyze/status: completed and up-to-date.
- Final candidate review worktree: clean at exact candidate SHA.

## 7. Accounting totals and gap

### Expected vs observed
| Metric | Expected | Observed | Gap |
|---|---:|---:|---:|
| Total changed files | 18 | 18 | 0 |
| New files | 9 | 9 | 0 |
| Edited files | 9 | 9 | 0 |
| Forbidden-scope files | 0 | 0 | 0 |

### Review outcome gap
- **Scope/accounting gap:** `0`
- **Correctness/authenticity gap:** non-zero, due to the two P1 authenticity failures and one P1 source-level cashier-flow violation above.

## 8. Local/remote report-branch equality

- **Local report branch head:** `PENDING_FINAL_PUSH_SHA`
- **Remote report branch head:** `PENDING_FINAL_PUSH_SHA`
- **Equality:** Pending final push verification.

## 9. Cleanup proof

- Detached candidate review worktree remained at `e23fc70bf0339b16f1850a9ebe07f3d7b731f357` with empty `git status --short`.
- No candidate branch commits, rebases, merges, or pushes were performed.
- No temporary mutation RED proof was executed because local runtime dependencies were unavailable; therefore no candidate-file mutation/restore cycle was needed.

## 10. Final verdict

`STOP_AND_REPORT_CTO`
