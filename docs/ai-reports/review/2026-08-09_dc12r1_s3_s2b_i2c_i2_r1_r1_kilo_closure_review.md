# DC-12R1-S3-S2B-I2C-I2-R1-R1 Kilo Blocker-Closure Review

- **Verdict:** `STOP_AND_REPORT_CTO`
- **Review type:** Independent adversarial closure review of R1 delta only
- **Product base SHA:** `4d97df5963a391a8d16d19988868234fd0d86648`
- **Predecessor SHA:** `e23fc70bf0339b16f1850a9ebe07f3d7b731f357`
- **Frozen R1 SHA:** `b3a84748ace61696f4429f34537cb36715b64dba`
- **Prior Kilo report SHA:** `2c79cb45e8bbe77179954c4e790011adaab1383c`
- **Report branch:** `reports/dc12r1-s3-s2b-i2c-i2-r1-r1-kilo-closure-review-2026-08-09`
- **Report SHA:** `5018423775ac7a809ae85a2106ddc2716ac7f775`
- **Runtime evidence:** Not used for source-review conclusions. Local Vitest execution remained unavailable because `pnpm vitest run src/tests/PrintableWorkspace.test.tsx` failed with `Command "vitest" not found`.

## 1. Executive summary

R1 does **not** close the prior Kilo blockers.

The critical closure failure is that the real cashier confirmation handler no longer falls back to the request ID, but it also no longer reads the response-authoritative declaration ID from the real service envelope. It reads `resp.id`, while `confirmDeclaration()` returns `ApiResponse<DeclarationConfirmResponse>` and the actual payload ID lives at `resp.data.id`. As shipped, a valid confirmation response will fail closed and expose no receipt link.

The new cashier tests are also false-green because they mock `api.post` with the wrong shape (`{ data: { id: ... } }`) rather than the real service envelope (`{ data: { success, data: { id: ... } } }`). That mock shape makes the broken handler appear correct.

The new route-guard evidence is improved but still incomplete: it renders the real `AppRouter`, yet it does not satisfy the required deny/allow matrix for all six print/receipt routes, and it does not prove static-mode endpoint ownership for declaration/receipt routes.

## 2. Phase 1 — Proof gate

### 2.1 SHA verification
All four required SHAs resolved exactly:
- candidate ref `origin/zcode/dc12r1-s3-s2b-i2c-i2-printable-workspace-2026-08-09` → `b3a84748ace61696f4429f34537cb36715b64dba`
- predecessor → `e23fc70bf0339b16f1850a9ebe07f3d7b731f357`
- base → `4d97df5963a391a8d16d19988868234fd0d86648`
- prior Kilo report → `2c79cb45e8bbe77179954c4e790011adaab1383c`

### 2.2 Lineage proof
- Direct-parent proof: `git rev-list --parents -n 1 b3a84748...` returned `b3a84748... e23fc70b...`
- Base ancestry proof: `git merge-base --is-ancestor 4d97df59... b3a84748...` succeeded.

### 2.3 Isolated detached review worktree
- Detached review worktree: `C:\Users\Jeff0\AppData\Local\Temp\kilo\dc12r1_i2c_i2_r1_review`
- HEAD at review completion: `b3a84748ace61696f4429f34537cb36715b64dba`
- Final `git status --short`: clean

### 2.4 Exact R1 delta proof
R1 delta `e23fc70b..b3a84748` changed **exactly 3 files**:
1. `frontend/src/pages/finance/DeclarationQueuePage.tsx`
2. `frontend/src/tests/PrintableWorkspace.test.tsx`
3. `ai-ledger/product-ai/2026-08-09_dc12r1_s3_s2b_i2c_i2_printable_workspace.md`

R1 shortstat:
- `3 files changed, 613 insertions(+), 14 deletions(-)`

R1 per-file stats:
- `ai-ledger/product-ai/2026-08-09_dc12r1_s3_s2b_i2c_i2_printable_workspace.md` `+125 -1`
- `frontend/src/pages/finance/DeclarationQueuePage.tsx` `+54 -12`
- `frontend/src/tests/PrintableWorkspace.test.tsx` `+434 -1`

### 2.5 Aggregate base..R1 scope proof
Aggregate `base..R1` scope remained the approved **18 files** and matched the previously approved manifest.

Aggregate shortstat:
- `18 files changed, 2248 insertions(+), 6 deletions(-)`

### 2.6 Forbidden-scope proof
No backend, migration, permission, dependency, lockfile, configuration, deployment, status-document, `package.json`, `pnpm-lock.yaml`, or `.secrets.baseline` changes were present in `base..R1`.

## 3. Phase 2 — Blocker 1: response-authoritative receipt link

### 3.1 What source now does
`frontend/src/pages/finance/DeclarationQueuePage.tsx:61-89`
- calls `confirmDeclaration(id)` exactly once
- clears prior UI state before each confirmation
- reads `resp` after confirmation
- sets `confirmedReceiptId` only when `typeof responseId === 'string' && responseId.length > 0`
- encodes `confirmedReceiptId` in the link URL with `encodeURIComponent`
- shows neutral no-link copy when the derived ID is missing/malformed
- exposes no link on confirmation failure
- introduces no retry or extra mutation request

### 3.2 Closure failure
`frontend/src/services/declarationService.ts:66-70` returns `resp.data` and is typed as `Promise<ApiResponse<DeclarationConfirmResponse>>`.

`frontend/src/types/api.ts:6-10` defines the real envelope:
- `ApiResponse<T> { success: boolean; data: T; timestamp: string; }`

Therefore the real confirmation payload ID is at **`resp.data.id`**, not `resp.id`.

But `frontend/src/pages/finance/DeclarationQueuePage.tsx:73-76` does:
```ts
const responseId =
  resp && typeof resp === 'object' && 'id' in resp
    ? (resp as { id?: unknown }).id
    : undefined;
```

This means Blocker 1 is **not closed**:
- receipt-link identity does **not** come from the real successful response payload
- a valid response envelope will be treated as malformed
- the UI will incorrectly suppress a legitimate receipt link
- the code is fail-closed, but it is not response-authoritative in the required way

### 3.3 Sub-matrix assessment
| Requirement | Result | Evidence |
|---|---|---|
| confirmDeclaration receives requested declaration ID exactly once | PASS | `DeclarationQueuePage.tsx:69`; `declarationService.ts:66-70` |
| Receipt-link identity comes only from successful response payload | **FAIL** | handler reads `resp.id`, not `resp.data.id` |
| No `?? id`, `|| id`, fixed/request/cached fallback | PASS | no such fallback in `DeclarationQueuePage.tsx:73-83` |
| Response ID must be non-empty string | PASS | `DeclarationQueuePage.tsx:77-83` |
| Encoded before entering receipt URL | PASS | `DeclarationQueuePage.tsx:127` |
| Missing/null/empty/non-string response IDs expose no link | PASS in source path | `DeclarationQueuePage.tsx:79-83,141-147` |
| Confirmation failures expose no receipt link | PASS in source path | `DeclarationQueuePage.tsx:85-87` |
| No retry or financial transaction change | PASS | single `confirmDeclaration(id)` call only |
| UI does not claim payment failed when response contract malformed | PASS | neutral copy `Declaration confirmed. The receipt link is unavailable.` |

### 3.4 Blocker 1 verdict
**STOP condition met for non-closure.**
Not because a request-ID fallback remains, but because the handler does not consume the real response envelope and therefore does not implement the required authoritative mapping.

## 4. Phase 3 — Blocker 2: cashier test authenticity

### 4.1 Real service contract
- `confirmDeclaration()` returns `resp.data` from axios, typed `ApiResponse<DeclarationConfirmResponse>`.
- Real payload shape is `{ success, data: { id, ... }, timestamp }`.

### 4.2 Test mock contract is wrong
`frontend/src/tests/PrintableWorkspace.test.tsx:630-631, 666, 686, 724`
uses:
```ts
vi.mocked(api.post).mockResolvedValueOnce(data(confirmResponseEnvelope(RESPONSE_ID)) as never)
```
where `data(x)` returns `{ data: x }`.

That means the mocked axios response shape is:
```ts
{ data: { id: RESPONSE_ID, ... } }
```
not the real shape:
```ts
{ data: { success: true, data: { id: RESPONSE_ID, ... }, timestamp: ... } }
```

Because `confirmDeclaration()` returns `resp.data`, the test passes `handleConfirm()` a flattened object with direct `.id`. That perfectly matches the broken production handler and hides the real contract bug.

### 4.3 Required-proof assessment
| Required proof | Result | Evidence |
|---|---|---|
| REQUEST_ID and RESPONSE_ID are distinct | PASS | `PrintableWorkspace.test.tsx:625-626` |
| Confirmation POST asserted with REQUEST_ID | PASS | `:647-649` |
| Receipt link asserted with RESPONSE_ID only | PASS in mocked world | `:651-654` |
| REQUEST_ID absent from receipt-link URL | PASS in mocked world | `:654` |
| Returned ID encoding asserted | PASS in mocked world | `:720-733` |
| Missing/null/empty/malformed/non-string response IDs expose no link | PASS in mocked world | `:677-701` |
| Confirmation rejection/error exposes no link | PASS | `:703-718` |
| Following the link invokes only supplier Contract C GET | **FAIL / MISSING** | no click-follow test exists |
| No extra POST/PUT/PATCH/DELETE occurs | PASS (partial) | `:656-659`, `:662-675` |
| Tests fail if `responseId ?? requestId` is restored | Unverified locally; source likely RED | runtime unavailable |
| Tests fail if fixed/stale ID replaces response ID | Unverified locally; source likely RED | runtime unavailable |
| Tests reflect real confirmation service contract | **FAIL** | wrong mock shape at `:630-631,666,686,724` |

### 4.4 Blocker 2 verdict
**Not closed.**
The new cashier tests are false-green against the real service contract because they flatten the confirmation envelope and thereby validate `resp.id` instead of the real `resp.data.id` path.

## 5. Phase 4 — Blocker 3: real route-guard evidence

### 5.1 What improved
R1 does render the real route tree:
- imports `AppRouter` at `PrintableWorkspace.test.tsx:34`
- renders `<AppRouter />` at `PrintableWorkspace.test.tsx:836`
- `AppRouter` owns the real guarded routes at `frontend/src/router/AppRouter.tsx:103-156`
- those routes sit under the real `WholesalerRoute` and `RetailerRoute`
- the real guard implementations are in `frontend/src/router/guards.tsx:75-124`
- the real layouts remain `MainLayout` and `ClientLayout`

So there is real route execution, not just source-string scanning.

### 5.2 Remaining matrix gaps
The required ownership matrix is still incomplete.

Covered:
- retailer can enter all three client print/receipt routes (`PrintableWorkspace.test.tsx:862-886`)
- wholesaler can enter all three supplier print/receipt routes (`:897-919`)
- retailer cannot enter supplier **order** print route only (`:888-895`)
- wholesaler cannot enter client **order** print route only (`:921-929`)
- static mode endpoint ownership is checked for **order print only** (`:931-950`)

Missing:
- retailer cannot enter supplier declaration print route
- retailer cannot enter supplier receipt route
- wholesaler cannot enter client declaration print route
- wholesaler cannot enter client receipt route
- static client mode invokes only client GET endpoint for declaration print and receipt routes
- static cashier mode invokes only supplier GET endpoint for declaration print and receipt routes

### 5.3 Blocker 3 verdict
**Partially improved but not fully closed.**
The tests now use the real `AppRouter`, but they still do not satisfy the full required route-ownership proof matrix.

## 6. Phase 5 — Regression and scope review

| Invariant | Result | Notes |
|---|---|---|
| String-only money rendering in print path remains intact | PASS | unchanged print pages/types/formatters |
| Pending/rejected declarations remain NOT A RECEIPT | PASS | unchanged print pages/tests for declaration semantics |
| Receipt page remains Contract C only | PASS | unchanged services/pages |
| Error responses remain neutral and body-blind | PASS | unchanged `sanitizePrintError` path |
| Print remains `window.print` only | PASS | unchanged print pages |
| No backend / Contract D / provider / PDF / QR / event / migration / dependency / deployment expansion | PASS | proof-gate scope clean |

## 7. Phase 6 — GitNexus and quality

### 7.1 GitNexus
- `npx gitnexus analyze` completed successfully.
- `npx gitnexus status` reported the review repo up-to-date at `b3a8474`.
- `detect_changes` is unavailable in this CLI build; exact `git diff` was used instead.
- `gitnexus context` for `handleConfirm` showed:
  - incoming caller: `DeclarationQueuePage`
  - outgoing call: `confirmDeclaration`
  - process: `DeclarationQueuePage → ConfirmDeclaration`
- `gitnexus impact` for `confirmDeclaration` showed LOW risk with d=1 caller `handleConfirm` and d=2 caller `DeclarationQueuePage`.

### 7.2 Quality checks
- `git diff --check e23fc70b..b3a84748`: clean
- mojibake scan on R1 delta (`rg "�"`): clean
- scoped `detect-secrets-hook --baseline .secrets.baseline` on R1 delta: clean
- final detached candidate worktree: clean at `b3a84748ace61696f4429f34537cb36715b64dba`

### 7.3 Runtime limitation
Attempted focused runtime:
- `pnpm vitest run src/tests/PrintableWorkspace.test.tsx`
- result: `Command "vitest" not found`

No runtime RED proof was claimed. No temporary mutation was applied.

## 8. Findings

### P1 — Real confirmation handler reads the wrong response path
- **File:** `frontend/src/pages/finance/DeclarationQueuePage.tsx:73-76`
- **Evidence:** handler inspects `resp.id`, but `confirmDeclaration()` returns `ApiResponse<DeclarationConfirmResponse>` and the real ID is under `resp.data.id`.
- **Impact:** a valid confirmation response exposes no receipt link; Blocker 1 is not closed.

### P1 — Cashier tests are false-green against the real service contract
- **File:** `frontend/src/tests/PrintableWorkspace.test.tsx:630-631,666,686,724`
- **Evidence:** tests mock `api.post` with `{ data: { id: ... } }` rather than the real envelope `{ data: { success, data: { id: ... }, timestamp } }`.
- **Impact:** tests validate the broken `resp.id` implementation and do not prove closure.

### P1 — Route-guard proof matrix remains incomplete
- **File:** `frontend/src/tests/PrintableWorkspace.test.tsx:888-950`
- **Evidence:** cross-boundary deny tests cover only order-print routes; static endpoint ownership proof covers only order-print routes.
- **Impact:** Blocker 3 is only partially closed; declaration/receipt guard ownership can regress undetected.

### P2 — Required supplier Contract C link-follow proof is missing
- **File:** `frontend/src/tests/PrintableWorkspace.test.tsx`
- **Evidence:** no test clicks the cashier receipt link and proves the follow-up request is only supplier `GET /declarations/:id/receipt` with no extra mutations.
- **Impact:** authenticity matrix incomplete.

### INFO — Local runtime evidence unavailable
- **Evidence:** focused Vitest invocation failed because `vitest` was unavailable in the environment.

## 9. Finding counts, mappings, and accounting gap

### 9.1 Finding counts
- P1: 3
- P2: 1
- P3: 0
- INFO: 1
- **Total findings:** 5

### 9.2 Valid mappings
1. R1 removed request-ID fallback syntax and added explicit fail-closed link gating in `DeclarationQueuePage.tsx`.
2. R1 now renders the real `AppRouter`, real guards, and real layouts in route-ownership tests.
3. R1 kept the original I2C-I2 scope boundaries and non-print regressions intact.

**Valid mappings count:** 3

### 9.3 Invalid mappings
1. Real confirmation-response ID mapping is wrong (`resp.id` vs `resp.data.id`).
2. Cashier authenticity tests mock the wrong confirmation envelope and therefore are false-green.
3. Route-guard proof matrix is incomplete for declaration/receipt cross-boundary denies and static endpoint ownership.
4. Required supplier Contract C link-follow proof is missing.

**Invalid mappings count:** 4

### 9.4 Accounting gap
| Metric | Expected | Observed | Gap |
|---|---:|---:|---:|
| R1 delta files | 3 | 3 | 0 |
| Aggregate base..R1 files | 18 | 18 | 0 |
| Forbidden files changed | 0 | 0 | 0 |
| Prior blockers fully closed | 3 | 0 | 3 |

**Accounting gap:** 3 blocker closures missing

## 10. Local/remote report-branch equality

- **Local report SHA:** `5018423775ac7a809ae85a2106ddc2716ac7f775`
- **Remote report SHA:** `5018423775ac7a809ae85a2106ddc2716ac7f775`
- **Equality:** equal

## 11. Cleanup proof

- Candidate branch was not modified, rebased, merged, or pushed.
- Review used detached worktree `C:\Users\Jeff0\AppData\Local\Temp\kilo\dc12r1_i2c_i2_r1_review`.
- Final detached worktree stayed clean at `b3a84748ace61696f4429f34537cb36715b64dba`.
- No temporary mutation was applied because runtime execution was unavailable.

## 12. Final verdict

`STOP_AND_REPORT_CTO`
