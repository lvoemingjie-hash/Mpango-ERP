# DC-12R1-S3-S2B-I2C-I2 — Retailer Printable Workspace

**Status:** PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I2_REVIEW (pending independent Lubuntu validation before merge)
**Executor:** local Zcode (real execution, no static analysis)
**Date:** 2026-08-09
**Branch:** `zcode/dc12r1-s3-s2b-i2c-i2-printable-workspace-2026-08-09`
**Base:** `origin/product-dev-recovered` @ `4d97df5963a391a8d16d19988868234fd0d86648`
**Required code ancestor:** `e923fd8567637ecc87b40d775caa8860b10821a0` (confirmed ancestor)

---

## 0 Verdict Summary

| Dimension | Result |
|---|---|
| Base / lineage | ✅ `origin/product-dev-recovered` == expected SHA; `e923fd85` is an ancestor; clean isolated worktree |
| Scope discipline | ✅ Only `frontend/**` + this ledger; zero backend/migration/permission/config/dependency/lockfile/status-doc changes |
| Browser-print only | ✅ `window.print()` + focused print CSS; no PDF lib, upload, server-side print mutation, or new dependency |
| Server-authoritative money | ✅ Decimal strings rendered via string-only grouping; no Number/parseFloat/Intl parse (large >2^53 + high-precision preserved) |
| Pending/rejected ≠ receipt | ✅ Server `non_receipt_notice` rendered verbatim ("NOT A RECEIPT"); never a formal receipt, receipt number, or "Payment Received" |
| Receipt = Contract C only | ✅ Receipt view uses only `/receipt` endpoints; cashier confirmed-receipt link navigates to Contract C without altering the confirm transaction |
| Static route ownership | ✅ `mode` fixed by static route config; dynamic segments `encodeURIComponent`-encoded; no query-param mode |
| Sanitized errors | ✅ `/receipt` 404 → neutral copy only; no eligibility/payment/binding/supplier/internal-id/schema/raw-text disclosure |
| Frontend gates | ✅ full `pnpm vitest run` 196/0; new file 36/0; `pnpm build` exit 0 |
| Self-review | ✅ `git diff --check` clean; detect-secrets 0 new; no mojibake; GitNexus status up-to-date |

---

## 1 Objective

Implement browser-printable frontend views for the existing read-only I2C-I1
Contracts A–C only:
- **A.** Order print — `GET /client/orders/{id}/print`, `GET /orders/{id}/print`
- **B.** Payment declaration print — `GET /client/declarations/{id}/print`, `GET /declarations/{id}/print`
- **C.** Eligible confirmed receipt print — `GET /client/declarations/{id}/receipt`, `GET /declarations/{id}/receipt`

Explicit exclusions honoured: no Contract D relationship statements; no
events/outbox/SMS/WhatsApp/provider credentials/QR/payment-provider work; no
retailer payment submission, cashier confirm/reject mutation, ledger,
receivable, settlement, receipt allocation, or any financial mutation; no
migrations or deployment.

## 2 Binding corrections (all incorporated)

1. **Money exactness** — `utils/printFormat.ts` groups thousands by pure string
   manipulation; never Number/parseFloat/Intl. Tests assert `9007199254740993.125`
   (>2^53) and `0.000001` render verbatim.
2. **NOT-A-RECEIPT semantics** — pending/rejected render the server
   `non_receipt_notice` (verbatim, incl. "NOT A RECEIPT"). Tests assert: not a
   formal receipt, no receipt number, no "Payment Received" — not a mechanical
   ban on the word `receipt`.
3. **Cashier confirmed-receipt entry** — after `confirmDeclaration` returns the
   confirmed declaration id, a "View / Print receipt" link navigates to
   Contract C only. The confirm transaction itself is unchanged (single
   `POST /declarations/{id}/confirm`); only the response id is read.
4. **Static route mode** — `mode="client"|"cashier"` is set on the `<Route>`
   element; never derived from a query param. Dynamic segments are
   `encodeURIComponent`-wrapped in the services (test verifies `a/b c` →
   `a%2Fb%20c`).
5. **Exact file-list scope gate** — scope is the enumerated file list, not a
   count (see §4).
6. **`/receipt` 404 neutral** — `sanitizePrintError` returns only fixed
   status-derived strings; the body is never inspected or echoed. Test feeds a
   rich `RECEIPT_NOT_AVAILABLE` body (eligibility/payment_id/binding/supplier)
   and asserts none of it reaches the UI.

## 3 Truth contract

- Only server-authoritative API fields are rendered. The browser never
  recomputes totals, balances, prices, payment state, or receipt eligibility.
- A pending/rejected declaration is a declaration document, never a receipt.
  Receipt content is only ever fetched from the Contract C endpoint.
- No tokens/credentials in URL query strings, browser storage, or print output.
  The shared axios client injects the bearer header from the Zustand store.
- No internal IDs (payment row UUID, cashier user id, `tenant_user_id`) are
  exposed by the I2C-I1 views and none are added by the frontend.

## 4 Exact changed-file scope (scope gate)

**New (9):**
- `frontend/src/types/print.ts`
- `frontend/src/utils/printError.ts`
- `frontend/src/utils/printFormat.ts`
- `frontend/src/pages/print/OrderPrintPage.tsx`
- `frontend/src/pages/print/DeclarationPrintPage.tsx`
- `frontend/src/pages/print/ReceiptPrintPage.tsx`
- `frontend/src/styles/print.css`
- `frontend/src/tests/PrintableWorkspace.test.tsx`
- `ai-ledger/product-ai/2026-08-09_dc12r1_s3_s2b_i2c_i2_printable_workspace.md`

**Edited (9):**
- `frontend/src/services/clientOrderService.ts` (additive `getPrint`)
- `frontend/src/services/orderService.ts` (additive `getPrint`)
- `frontend/src/services/declarationService.ts` (additive 4 read funcs; existing funcs untouched)
- `frontend/src/router/AppRouter.tsx` (6 additive routes + imports)
- `frontend/src/main.tsx` (1 import line)
- `frontend/src/pages/client/OrderDetailPage.tsx` (Print link)
- `frontend/src/pages/client/DeclarationHistoryPage.tsx` (Print link; Receipt link when confirmed)
- `frontend/src/pages/orders/OrderListPage.tsx` (Print link)
- `frontend/src/pages/finance/DeclarationQueuePage.tsx` (Print link + post-confirm Contract-C receipt link)

No backend, migration, permission, config, dependency, lockfile, or
project-status document changes. (`.secrets.baseline` was momentarily touched
by a detect-secrets scan invocation and restored to its committed state; final
`git diff` confirms it is untouched.)

## 5 Routes (static mode)

Retailer (under existing `RetailerRoute` → `ClientLayout`):
- `/client/orders/:orderId/print`
- `/client/declarations/:declarationId/print`
- `/client/declarations/:declarationId/receipt`

Cashier (under existing `WholesalerRoute` → `MainLayout`):
- `/orders/:orderId/print`
- `/declarations/:declarationId/print`
- `/declarations/:declarationId/receipt`

## 6 Verification (real execution)

- **`pnpm vitest run` (full):** 19 test files, **196 passed / 0 failed**.
- **New file `src/tests/PrintableWorkspace.test.tsx`:** **36 passed / 0 failed**.
  Covers: correct GET endpoint + exactly one request per view; no
  POST/PUT/PATCH/DELETE; deterministic server-fixture rendering; `window.print()`
  invoked; pending/rejected NOT-A-RECEIPT semantics; large/high-precision money
  exactness; sanitized 401/403/404/5xx; `/receipt` 404 disclosure containment.
- **`pnpm build`** (`tsc -p tsconfig.app.json && vite build`): exit 0; `dist/`
  produced. (A pre-existing duplicate `jsdom` key warning in `package.json` and
  a chunk-size advisory are unchanged/environmental — `package.json` is not in
  this branch's diff.)

## 7 Self-review

- `git diff --check`: clean (no whitespace/conflict-marker errors).
- Changed-file scope: matches §4 exactly; no forbidden paths.
- No new dependency; no skip/xfail/deselection/timeout increase/weakened
  assertion (all new assertions are additive and deterministic).
- **detect-secrets**: read-only scan of all 17 changed/new files → 0 secrets.
  `detect-secrets-hook --baseline .secrets.baseline` → exit 0.
- **Mojibake**: no U+FFFD / double-encoded sequences; non-ASCII usage is
  intentional em/en-dash + smart apostrophe, matching the existing convention
  (e.g. `frontend/src/services/api.ts`).
- **GitNexus**: `detect-changes` subcommand is NOT available in this CLI build
  (limitation recorded). Direct `git diff` proof used instead (§4). `gitnexus
  analyze` → "Already up to date"; `gitnexus status` → ✅ up-to-date at
  `4d97df5`. Pre-edit impact on touched symbols was LOW (0 dependants) except
  `normalizeApiError` (HIGH, 15 dependants) which was reused unedited.

## 8 Next steps

Push only the isolated Zcode branch. Do not merge, deploy, or start I2C-I3.
Independent Lubuntu frontend/runtime validation precedes any controlled merge.
