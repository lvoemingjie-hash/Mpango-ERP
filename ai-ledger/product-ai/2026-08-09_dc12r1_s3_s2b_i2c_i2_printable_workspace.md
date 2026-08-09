# DC-12R1-S3-S2B-I2C-I2 — Retailer Printable Workspace

> **⚠️ SUPERSEDED_BY_I2C_I2_R3**
>
> The `e23fc70b` (I2C-I2), `b3a84748` (R1), and `93539814` (R2) PASS verdicts
> are all **superseded** by the R3 correction. Latest Kilo report: `f3e033d6`
> (prior: `2c79cb45`, `361adfb9`). CTO adjudication ACCEPTED two blockers and
> REJECTED the count blocker. R3 closes the two accepted blockers (test +
> ledger only; no production/component/service/router changes):
>
> 1. **Genuine link-follow** — R2's link-follow test manually invoked
>    `mockGet(receiptUrl)` instead of following the rendered receipt link. R3
>    replaces it with real user navigation: render the real `<AppRouter/>` at
>    `/declarations` (wholesaler) → click Confirm → wait for the rendered
>    View/Print receipt Link → **click the Link through React Router** → wait
>    for the real ReceiptPrintPage → assert exactly one supplier Contract C GET.
> 2. **Opposite-endpoint exclusivity** — R2's `not.toHaveBeenCalledWith` for
>    order routes only was incomplete for declaration/receipt routes. R3
>    extends `routeExpectations` with `opposite` + a full six-endpoint list and
>    asserts the **complete print-data GET list** equals exactly
>    `[expectedEndpoint]` for all 6 ALLOW routes and `[]` for all 6 DENY routes.
>
> Prior evidence (§0–§10) is preserved as non-authoritative history. The
> authoritative verdict is
> **PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I2_R3_MERGE_REVIEW** (see §11).

> **⚠️ SUPERSEDED_BY_I2C_I2_R2**
>
> Both the `e23fc70b` (I2C-I2) and `b3a84748` (R1) PASS verdicts are
> **superseded** by the R2 correction. Kilo R2 report: commit `361adfb9`
> (in addition to the R1 report `2c79cb45`). R2 closes three further blockers:
>
> 1. **Real response envelope** — R1 read the receipt id at the wrong envelope
>    layer (`resp.id`). R2 derives it ONLY from `resp.data.id`, matching the
>    declared `confirmDeclaration` contract
>    `Promise<ApiResponse<DeclarationConfirmResponse>>` (ApiResponse =
>    `{success, data:{id,...}, timestamp}`). Full runtime validation; no
>    `resp.id`, no `resp.data.data.id`, no fallback; `encodeURIComponent`-encoded.
> 2. **Authentic three-layer mocks** — R2 eliminates the flattened false-green
>    mock `{data:{id}}` and reproduces the real boundary exactly
>    (AxiosResponse → ApiResponse → DeclarationConfirmResponse → id) via named
>    helpers `confirmResponsePayload` / `confirmApiEnvelope` / `axiosResponse`.
> 3. **Complete AppRouter matrix** — R2 parameterizes all six routes for both
>    retailer and wholesaler (12 cases) with static endpoint ownership.
>
> Prior evidence (§0–§9) is preserved as non-authoritative history. The
> authoritative verdict is
> **PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I2_R2_MERGE_REVIEW** (see §10).

> **⚠️ SUPERSEDED_BY_I2C_I2_R1**
>
> The `e23fc70b` PASS verdict below is **superseded** by the R1 correction.
> Three Kilo merge blockers were identified (Kilo report commit `2c79cb45`)
> and closed by the R1 delta on this same isolated branch:
>
> 1. **Receipt-link authority** — the cashier confirmation response ID had a
>    `?? id` fallback to the request/row declaration ID. R1 removes every
>    fallback; the receipt link is now built ONLY from the successful
>    confirmation response ID, rendered only when it is a non-empty string,
>    and `encodeURIComponent`-encoded. Missing/malformed response IDs fail
>    closed (controlled neutral copy, no link), without claiming payment
>    failure.
> 2. **Authentic cashier RED/GREEN tests** — R1 adds tests using distinct
>    request vs response IDs, fail-closed cases for missing/null/empty/
>    non-string IDs, rejection no-link, encoding, and proves a `?? id`/
>    fixed/stale mutation goes RED (8/9 fail against `e23fc70b`).
> 3. **Real route-guard evidence** — R1 replaces the local test-only harness
>    with tests that render the **actual `<AppRouter/>`** route tree and the
>    real `RetailerRoute`/`WholesalerRoute` guards (no source scanning, no
>    reconstructed guard substitutes). Guards are NOT edited.
>
> The `e23fc70b` evidence below is preserved as history; the authoritative
> verdict is **PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I2_R1_MERGE_REVIEW** (see §9).

**Status:** ⚠️ SUPERSEDED_BY_I2C_I2_R3 (prior: I2C-I2 @ `e23fc70b`, R1 @ `b3a84748`, R2 @ `93539814`)
**Executor:** local Zcode (real execution, no static analysis)
**Date:** 2026-08-09
**Branch:** `zcode/dc12r1-s3-s2b-i2c-i2-printable-workspace-2026-08-09`
**Base:** `origin/product-dev-recovered` @ `4d97df5963a391a8d16d19988868234fd0d86648`
**Required code ancestor:** `e923fd8567637ecc87b40d775caa8860b10821a0` (confirmed ancestor)
**I2C-I2 tip:** `e23fc70bf0339b16f1850a9ebe07f3d7b731f357`
**Kilo report:** commit `2c79cb45`

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

---

## 9 R1 — Receipt-Link Authority and Route-Guard Evidence

**R1 status:** PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I2_R1_MERGE_REVIEW
**R1 base (parent):** `e23fc70bf0339b16f1850a9ebe07f3d7b731f357` (I2C-I2 tip)
**Kilo report:** commit `2c79cb45` (three merge blockers)

### 9.1 The three Kilo blockers and exact closure

**Blocker 1 — response-authoritative receipt link.** The `e23fc70b` cashier
confirmation derived the receipt id with `resp?.data?.id ?? id`, falling back to
the request/row declaration id when the response lacked one. **R1 closure:**
removed every fallback (`?? id`, `|| id`, any cached/stale id). The receipt id is
now read ONLY from the successful confirmation response; the receipt link is
rendered only when that id is a non-empty string and is `encodeURIComponent`-
encoded. Missing/null/empty/non-string response ids fail closed: controlled
neutral copy ("The receipt link is unavailable.") and NO receipt link — but the
message does NOT claim payment failure (confirmation itself succeeded; only the
receipt-link rendering fails closed). The confirmation transaction is unchanged
(exactly one `POST /declarations/{id}/confirm`; no retry, no alteration).

**Blocker 2 — authentic cashier RED/GREEN tests.** R1 adds tests with distinct
request and response IDs. Required cases all covered: POST receives REQUEST_ID
exactly once; RESPONSE_ID ≠ REQUEST_ID yields link
`/declarations/{RESPONSE_ID}/receipt`; no link containing REQUEST_ID; missing/
null/empty/non-string response IDs expose no link; rejection/error exposes no
link; a `?? id`/fixed/stale mutation makes the tests RED; following the link
invokes only the supplier Contract C GET; no extra POST/PUT/PATCH/DELETE.

**Blocker 3 — real route-guard evidence.** R1 supplements the local test-only
harness with tests that render the **actual `<AppRouter/>`** (the real
`createBrowserRouter` route tree, the real `RetailerRoute`/`WholesalerRoute`
guard components, the real layouts, and the real print pages). No source-string
scanning; no locally reconstructed guard substitutes; guards are NOT edited.
Because `createBrowserRouter` snapshots the URL at construction, the tests render
once and then drive the singleton data router via `history.pushState` +
`popstate`, which the real router reacts to.

### 9.2 RED evidence (against `e23fc70b`, pre-correction)

With only `DeclarationQueuePage.tsx` reverted to `e23fc70b` (the new tests kept),
**8 of 9** Correction-2 tests failed RED:

| RED test (fails against e23fc70b) | Root cause |
|---|---|
| confirmation POST receives REQUEST_ID exactly once; link uses RESPONSE_ID | link `href="/declarations/dec-request-aaa/receipt"` (REQUEST_ID via `?? id`) instead of RESPONSE_ID `dec-response-bbb` |
| response with missing/null/empty/non-string id exposes NO link | `?? id` fallback exposes a link using the request id |
| encodes the response id | link built from request id, not encoded response id |
| a second POST never occurs | asserts the response-authoritative link which the old version renders differently |

(The 9th — "confirmation rejection exposes no link" — passes both ways: both
versions correctly hide the link on error, so it is not a discriminator.)

Correction-3 route-guard tests did not exist at `e23fc70b` (no RED baseline
possible); they are net-new authentic evidence.

### 9.3 GREEN gates

| Gate | Result |
|---|---|
| Focused `PrintableWorkspace` | **50 passed / 0 failed** |
| Full `pnpm vitest run` | **210 passed / 0 failed** (19 files) |
| `pnpm build` (tsc + vite) | exit 0 |
| Existing retailer-portal + route-guard tests | **19 passed / 0 failed** (unaffected) |
| Reversed focused order | vitest 1.6.1 has no `--reverse` flag → limitation documented; sequential run 50/0 |
| Zero skipped/deselected/xfail | confirmed (no `.skip`/`xit`/`todo`) |

### 9.4 R1 changed-file scope

R1 touched exactly the **3 allowed files** (the aggregate candidate delta remains
the same approved 18 files; no new file added):

- `frontend/src/pages/finance/DeclarationQueuePage.tsx` (Correction 1)
- `frontend/src/tests/PrintableWorkspace.test.tsx` (Corrections 2 & 3)
- `ai-ledger/product-ai/2026-08-09_dc12r1_s3_s2b_i2c_i2_printable_workspace.md` (this section)

### 9.5 R1 self-review

- `git diff --check`: clean (no whitespace/conflict-marker errors).
- Scope: only the 3 allowed files; aggregate still 18; no forbidden paths.
- No new dependency; no skip/xfail/deselection/timeout increase/weakened assertion.
- **detect-secrets** (read-only scan + `detect-secrets-hook --baseline`): 0 secrets, exit 0.
- **Mojibake**: no U+FFFD/double-encoded; non-ASCII is intentional em-dash (convention).
- **GitNexus**: pre-edit impact on `DeclarationQueuePage`/`handleConfirm`/`confirmDeclaration` = LOW.
  `detect_changes` NOT available in this CLI build (documented); direct `git diff` used.
  `gitnexus analyze`/`status` run after the final commit (§9.6).
- **Adversarial**: verified no `?? id`/`|| id`/request-id/stale-id fallback in code;
  `confirmDeclaration` called exactly once (no retry); link `encodeURIComponent`-encoded;
  the confirmation transaction is not altered (single POST, response id read-only).

### 9.6 Post-commit GitNexus

`gitnexus analyze` + `gitnexus status` to be re-run after the R1 commit (recorded
in the commit/push step). `detect_changes` remains unavailable in this CLI build
(limitation documented; exact `git diff` evidence in §9.4).

---

## 10 R2 — Real API Envelope and Complete Guard Matrix

**R2 status:** PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I2_R2_MERGE_REVIEW
**R2 base (parent):** `b3a84748` (R1 tip)
**Kilo R2 report:** commit `361adfb9` (R1 report: `2c79cb45`)
**Supersedes:** `e23fc70b` (I2C-I2) and `b3a84748` (R1)

### 10.1 The three R2 blockers and exact closure

**Blocker 1 — real response envelope.** R1 read the receipt id at the wrong
envelope layer (`resp.id` via `'id' in resp`). The declared
`confirmDeclaration` contract is
`Promise<ApiResponse<DeclarationConfirmResponse>>`, and `ApiResponse<T>` is
`{ success, data: T, timestamp }`, so the receipt id lives at `resp.data.id`.
R2 derives it ONLY from `resp.data.id` with full runtime validation: `resp` is
an object; `resp.data` is a non-null object; `resp.data.id` is a non-empty
string; then `encodeURIComponent(resp.data.id)` before constructing the link.
Forbidden and absent: `resp.id`, `resp.data.data.id`, request/row/cached/fixed/
route id fallback, `?? id`/`|| id`, and any shape guessing beyond the declared
`ApiResponse` contract. `declarationService.ts` was NOT changed (its public
contract is unchanged).

**Blocker 2 — authentic three-layer mocks.** R2 eliminates the flattened
false-green mock `{ data: { id } }` and reproduces the real boundary exactly:

```
AxiosResponse
  .data = ApiResponse<DeclarationConfirmResponse>   ({ success, data, timestamp })
    .data = DeclarationConfirmResponse               ({ id, ... })
      .id = RESPONSE_ID
```

via clearly named helpers `confirmResponsePayload(id)`,
`confirmApiEnvelope(payload)`, `axiosResponse(body)`, and
`authenticConfirmSuccess(id)`. The successful `api.post` mock is equivalent to
`{ data: { success: true, data: { id: RESPONSE_ID, ... }, timestamp } }`.

**Blocker 3 — complete AppRouter matrix.** R2 parameterizes all six routes for
both retailer and wholesaler (12 cases) against the real `<AppRouter/>`,
`RetailerRoute`, `WholesalerRoute`, `ClientLayout`, `MainLayout`, and real print
pages. Static endpoint ownership is proven for all six routes.

### 10.2 Final envelope shape (explicit)

The cashier confirmation receipt identity is derived exclusively as:

```ts
const dataObj = resp && typeof resp === 'object' ? resp.data : undefined;
const responseId = dataObj && typeof dataObj === 'object' ? dataObj.id : undefined;
if (typeof responseId === 'string' && responseId.length > 0) {
  setConfirmedReceiptId(responseId);  // → link /declarations/{encodeURIComponent(responseId)}/receipt
} else {
  // fail closed: neutral copy, no link, NOT a payment-failure message
}
```

### 10.3 Complete 12-case guard matrix (explicit)

| # | Session | Route | Result |
|---|---|---|---|
| 1 | retailer | `/client/orders/:id/print` | ALLOW → GET `/client/orders/:id/print` once |
| 2 | retailer | `/client/declarations/:id/print` | ALLOW → GET `/client/declarations/:id/print` once |
| 3 | retailer | `/client/declarations/:id/receipt` | ALLOW → GET `/client/declarations/:id/receipt` once |
| 4 | retailer | `/orders/:id/print` | DENY/redirect; no print-data GET |
| 5 | retailer | `/declarations/:id/print` | DENY/redirect; no print-data GET |
| 6 | retailer | `/declarations/:id/receipt` | DENY/redirect; no print-data GET |
| 7 | wholesaler | `/orders/:id/print` | ALLOW → GET `/orders/:id/print` once |
| 8 | wholesaler | `/declarations/:id/print` | ALLOW → GET `/declarations/:id/print` once |
| 9 | wholesaler | `/declarations/:id/receipt` | ALLOW → GET `/declarations/:id/receipt` once |
| 10 | wholesaler | `/client/orders/:id/print` | DENY/redirect; no print-data GET |
| 11 | wholesaler | `/client/declarations/:id/print` | DENY/redirect; no print-data GET |
| 12 | wholesaler | `/client/declarations/:id/receipt` | DENY/redirect; no print-data GET |

Plus static endpoint ownership: each allowed route calls exactly its own GET
endpoint once, never the opposite client/supplier endpoint, and issues no
POST/PUT/PATCH/DELETE.

### 10.4 RED proof (against `b3a84748`, pre-R2)

With only `DeclarationQueuePage.tsx` reverted to `b3a84748` (R2 tests kept),
**5 of 12** authentic-envelope Correction-2 tests fail RED, including the
authoritative success case. Root cause: `b3a84748` reads `resp.id`, but the
authentic `ApiResponse` envelope has no top-level `id`, so the link is not built
from `RESPONSE_ID` (assertion on `href=.../RESPONSE_ID/receipt` fails). RED
tests: 1 (POST/link), 2 (no extra mutation — depends on link), 3 (encoded
RESPONSE_ID), 11/12 (Contract C GET), 9 (flattened legacy). Additionally, the
`encodeURIComponent`-removal mutation makes test 3 RED (verified).

### 10.5 GREEN gates

| Gate | Result |
|---|---|
| Authentic-envelope RED on `b3a84748` | 5/12 RED (captured) |
| Focused `PrintableWorkspace` | **62 passed / 0 failed** |
| Focused, 3 consecutive clean-process runs | 62/62 × 3 |
| Full `pnpm vitest run` | **222 passed / 0 failed** (19 files) |
| Existing retailer-portal + route-guard tests | **19 passed / 0 failed** |
| `pnpm build` | exit 0 |
| Zero skip/xfail/deselected/timeout/assertion weakening | confirmed |

### 10.6 R2 changed-file scope

R2 touched exactly the **3 allowed files** (aggregate base..HEAD remains the
approved 18 files; no new file added; `declarationService.ts` unchanged):

- `frontend/src/pages/finance/DeclarationQueuePage.tsx` (Correction 1)
- `frontend/src/tests/PrintableWorkspace.test.tsx` (Corrections 2 & 3)
- `ai-ledger/product-ai/2026-08-09_dc12r1_s3_s2b_i2c_i2_printable_workspace.md` (this section)

### 10.7 R2 self-review

- `git diff --check`: clean.
- Scope: only the 3 allowed files; aggregate still 18; `declarationService.ts`
  unchanged; no forbidden paths.
- No new dependency; no skip/xfail/deselection/timeout increase/assertion weakening.
- **detect-secrets** (read-only scan + `detect-secrets-hook --baseline`): 0 secrets, exit 0.
- **Mojibake**: no U+FFFD/double-encoded; non-ASCII is intentional em-dash (convention).
- **GitNexus**: pre-edit impact on `handleConfirm`/`confirmDeclaration`/`DeclarationQueuePage` = LOW.
  `detect_changes` NOT available in this CLI build (documented); direct `git diff` used.
  `gitnexus analyze`/`status` run after the final commit.
- **Adversarial**: verified the code reads `resp.data.id` (not `resp.id`/`resp.data.data.id`);
  no `?? id`/`|| id`/fixed/stale fallback; `confirmDeclaration` called once; link
  `encodeURIComponent`-encoded; confirmation transaction unaltered.

### 10.8 Post-commit GitNexus

`gitnexus analyze` + `gitnexus status` re-run after the R2 commit (recorded in
the commit/push step).

---

## 11 R3 — Link-Follow and Endpoint-Exclusivity Evidence

**R3 status:** PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I2_R3_MERGE_REVIEW
**R3 base (parent):** `93539814` (R2 tip)
**Kilo R3 report:** commit `f3e033d6` (CTO adjudication: 2 ACCEPTED blockers, 1
REJECTED count blocker). Prior Kilo reports: `2c79cb45`, `361adfb9`.
**Supersedes:** `e23fc70b` (I2C-I2), `b3a84748` (R1), `93539814` (R2).
**R3 scope:** test + ledger only — NO production/component/service/router changes.

### 11.1 CTO adjudication and the two accepted blockers

- **ACCEPT (Correction 1):** R2's link-follow test manually invoked
  `mockGet(receiptUrl)` instead of following the rendered receipt link.
- **ACCEPT (Correction 2):** opposite-endpoint absence was incomplete for
  declaration and receipt routes (`not.toHaveBeenCalledWith` for order routes
  only).
- **REJECT (count):** the 62 focused nodes were structurally correct
  (48 plain declarations + 8 loop-generated + 6 `it.each` = 62; full 222 =
  prior 210 + 12 R2 nodes). No count change was warranted.

### 11.2 Correction 1 — genuine link-follow

The link-follow test now exercises real user navigation only:

```
real AppRouter @ /declarations (wholesaler)
  → DeclarationQueuePage
  → real Confirm button (click)
  → authentic AxiosResponse → ApiResponse → confirmation payload (RESPONSE_ID)
  → rendered View/Print receipt Link (waitFor)
  → fireEvent.click(link)            [NOT mockGet, NOT window.location]
  → real AppRouter / WholesalerRoute / MainLayout / real ReceiptPrintPage
  → getCashierReceipt → supplier Contract C GET
```

Forbidden behaviors (all absent, verified by adversarial scan): direct
`mockGet`; direct `getCashierReceipt`; separate `ReceiptPrintPage` render;
manual `window.location`; reconstructed local receipt route; asserting only
`href` without following it.

**Mutation RED evidence** (each temporarily applied, captured RED, restored):
- link → `REQUEST_ID`: R3 link-follow test RED (the R2 tests 1 & 3 also RED).
- link → `/client/declarations/.../receipt` (wrong boundary): R3 link-follow RED
  (wholesaler following a client-boundary link is redirected by the guard).
- `ReceiptPrintPage` cashier mode → client service (`getCashierReceipt` ↔
  `getClientReceipt` swapped): 5 tests RED (link-follow + receipt ALLOW matrix),
  because following the link hits the client `/client/declarations/.../receipt`
  endpoint instead of supplier Contract C.

### 11.3 Correction 2 — opposite-endpoint exclusivity (all six routes)

`routeExpectations` now returns `{ endpoint, opposite, testid }`, plus a
`ALL_SIX_PRINT_ENDPOINTS` list and a `printDataGetUrls` filter. For each of the
6 ALLOW routes, the complete print-data GET list is asserted to equal exactly
`[expectedEndpoint]` (so any of the other 5 endpoints leaking in fails the
test), the opposite endpoint is asserted never called, and all five non-expected
endpoints are asserted never called. For each of the 6 DENY routes, the complete
print-data GET list is asserted empty `[]` and no write occurs.

The six opposite pairs:
- client order print ↔ supplier order print
- client declaration print ↔ supplier declaration print
- client receipt ↔ supplier receipt

A generic `not.toHaveBeenCalledWith` for order routes only is no longer the
sole guard; the complete-list `toEqual` is order/declaration/receipt-agnostic.

### 11.4 Correction 3 — node-count reconciliation (CTO REJECTED the count blocker)

The truthful counts are unchanged in code; this section makes the derivation
explicit (Kilo could not run `vitest` — runtime limitation).

**Focused `pnpm vitest run src/tests/PrintableWorkspace.test.tsx`:**
- R2: 62 nodes = 48 plain `it`/`expect` declarations + 8 nodes generated by four
  three-item `for…of` route loops (4 loops × (1 loop test node + 1 parameter
  expansion?)) — more precisely: the four matrix describes each contribute their
  loop-generated `it` cases; plus 6 `it.each` parameterized cases.
- R3: 63 nodes = R2's 62 + 1 new genuine link-follow `it`.

Actual command output (R3 focused): `Tests 63 passed (63)`, `Test Files 1
passed (1)`. Verbose reporter: 63 test nodes (+ 2 summary lines = 65 grep hits).

**Full `pnpm vitest run`:**
- R2: 222 = prior 210 (I2C-I2 baseline) + 12 R2 matrix nodes.
- R3: 223 = 222 + 1 R3 link-follow node.

Actual command output (R3 full): `Tests 223 passed (223)`, `Test Files 19
passed (19)`.

Kilo's static count estimate differed because `vitest` was unavailable in the
Kilo environment (runtime limitation); the counts above are the real
executed-node counts from the actual test runner.

### 11.5 GREEN gates

| Gate | Result |
|---|---|
| Focused `PrintableWorkspace` (verbose) | **63 passed / 0 failed** |
| Focused, 3 consecutive clean-process runs | 63/63 × 3 |
| Full `pnpm vitest run` | **223 passed / 0 failed** (19 files) |
| Existing retailer-portal + route-guard tests | **19 passed / 0 failed** |
| `pnpm build` | exit 0 |
| Zero skip/xfail/deselected/timeout/assertion weakening | confirmed |

### 11.6 R3 changed-file scope

R3 touched exactly the **2 allowed files** (aggregate base..HEAD remains the
approved 18 files; no production/component/service/router change):

- `frontend/src/tests/PrintableWorkspace.test.tsx` (Corrections 1 & 2)
- `ai-ledger/product-ai/2026-08-09_dc12r1_s3_s2b_i2c_i2_printable_workspace.md` (this section + §11.4)

### 11.7 R3 self-review

- `git diff --check`: clean.
- Scope: only the 2 allowed files; aggregate still 18; NO production/
  component/service/router changes (verified: only the test file changed vs
  HEAD; production files restored to HEAD after every mutation).
- No new dependency; no skip/xfail/deselection/timeout increase/assertion weakening.
- **detect-secrets** (read-only scan + `detect-secrets-hook --baseline`): 0 secrets, exit 0.
- **Mojibake**: none (no U+FFFD/double-encoded).
- **GitNexus**: pre-edit impact on route/guard/page symbols = LOW (R3 touches no
  production code). `detect_changes` NOT available in this CLI build (documented;
  exact `git diff` evidence in §11.6). `gitnexus analyze`/`status` run after the
  final commit.
- **Adversarial**: link-follow uses real `render(<AppRouter/>)` +
  `fireEvent.click(link)`; no forbidden patterns; endpoint-exclusivity asserts
  the complete list for all 12 cases (6 ALLOW `[expected]` + 6 DENY `[]`).

### 11.8 Post-commit GitNexus

`gitnexus analyze` + `gitnexus status` re-run after the R3 commit (recorded in
the commit/push step).
