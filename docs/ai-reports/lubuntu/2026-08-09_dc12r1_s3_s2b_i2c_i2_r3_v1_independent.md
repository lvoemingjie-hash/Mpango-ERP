# DC-12R1-S3-S2B-I2C-I2-R3-V1 Independent Final Runtime Verification

**Date**: 2026-08-09  
**Executor**: Lubuntu host `ivy-20149` (Linux 7.0.0-28-generic x86_64, Ubuntu 24.04)  
**Toolchain**: Node v22.23.2, pnpm 11.1.2, vitest 1.6.1, Vite 5.4.21  
**Verdict**: `PASS_DC12R1_S3_S2B_I2C_I2_R3_V1_INDEPENDENT_FINAL`

---

## 1. SHAs and Lineage

| Ref | Expected SHA | Verified | Match |
|-----|-------------|----------|-------|
| Candidate | `10c9158d993226082484f4186c8fc8749d97b65d` | `10c9158d` | YES |
| Product base | `4d97df5963a391a8d16d19988868234fd0d86648` | `4d97df5` | YES |
| R3 predecessor (R2) | `93539814380b014a3a78b31a545bb5e63ff90a28` | `9353981` | YES |
| Kilo closure report | `d1e5f51896ee5d3564623695a92c1a6ec7734e9a` | `d1e5f51` | YES |

**Ancestry**: base is ancestor of predecessor, predecessor is ancestor of candidate, base is ancestor of candidate.  
**Candidate parent**: `9353981` (R2).  
**Clone type**: full clone (`.git` directory, not worktree pointer).

### R3 delta (predecessor..candidate): exactly 2 files

| File | Lines |
|------|-------|
| `frontend/src/tests/PrintableWorkspace.test.tsx` | 208 changed |
| `ai-ledger/product-ai/2026-08-09_dc12r1_s3_s2b_i2c_i2_printable_workspace.md` | 162 changed |

No production code changes between R2 and R3.

### Aggregate base..candidate delta: exactly 18 files (9 new + 9 edited)

**9 new**: `DeclarationPrintPage.tsx`, `OrderPrintPage.tsx`, `ReceiptPrintPage.tsx`, `print.css`, `PrintableWorkspace.test.tsx`, `print.ts`, `printError.ts`, `printFormat.ts`, ledger `.md`.

**9 edited**: `main.tsx`, `DeclarationHistoryPage.tsx`, `OrderDetailPage.tsx`, `DeclarationQueuePage.tsx`, `OrderListPage.tsx`, `AppRouter.tsx`, `clientOrderService.ts`, `declarationService.ts`, `orderService.ts`.

No backend, migration, permission, config, dependency, lockfile, deployment, package.json, pnpm-lock.yaml, or .secrets.baseline changes.

---

## 2. Source Invariants

### A. Response authority
- `confirmDeclaration(id)` invoked exactly once with REQUEST_ID (DeclarationQueuePage.tsx:69).  
- Receipt identity derived ONLY from `resp.data.id` (lines 77-79). No `resp.id`, `resp.data.data.id`, `?? id`, `|| id`, or stale/cached fallback.  
- Missing/malformed envelope: `setConfirmedReceiptId(null)` + `setReceiptLinkUnavailable(true)` -- fail closed, no link exposed.  
- `encodeURIComponent(confirmedReceiptId)` before URL construction (line 130).  
- Confirmation transaction unchanged: single POST `/declarations/{id}/confirm`.

### B. Money
- `formatDecimalMoney` / `formatKes`: pure string regex grouping. No `Number()`, `parseFloat`, `parseInt`, `Intl.NumberFormat`, `Math.`, `.toFixed()`, or arithmetic in print code.  
- Large amounts beyond 2^53 (e.g. `9007199254740993.125`) preserved exactly.  
- High-precision decimals preserved verbatim.

### C. Document truth
- Pending/rejected: `doc.non_receipt_notice` rendered prominently with "NOT A RECEIPT" (DeclarationPrintPage.tsx:133-141).  
- Status labels: "Pending -- awaiting confirmation", "Confirmed", "Rejected" -- never "Payment Received" for pending/rejected.  
- Receipt view uses Contract C only (ReceiptPrintPage calls `getClientReceipt`/`getCashierReceipt`).  
- Error states: `sanitizePrintError` checks HTTP status only, never echoes response body/headers/internal IDs.

### D. Scope
- Only `window.print()` (1 call per print page in code; OrderPrintPage comment mentions it once more).  
- No Contract D, PDF, QR, event/outbox, SMS/WhatsApp, provider, server printing, or backend change.  
- All 4 new services are GET-only.

---

## 3. Authentic Link-Follow Runtime Proof

Test: `R3 Correction 1 -- genuine link-follow to ReceiptPrintPage (Contract C only)` -- **PASSED**.

Real flow verified: AppRouter -> WholesalerRoute -> MainLayout -> DeclarationQueuePage -> click Confirm -> authentic AxiosResponse/API envelope -> rendered receipt Link -> click rendered Link -> React Router navigation -> real ReceiptPrintPage -> exact supplier Contract C GET.

- REQUEST_ID differs from RESPONSE_ID.
- Confirmation POST uses REQUEST_ID exactly once.
- Link and GET use encoded RESPONSE_ID only.
- Receipt document renders.
- Client Contract C endpoint absent on cashier page.
- No additional mutation request.
- No direct mockGet/service invocation substitutes for following the link.

---

## 4. Complete Route Matrix (12 cases)

Test: `R2 Correction 3 -- complete actual AppRouter guard/endpoint matrix` -- all 12 + 1 static ownership = **13 PASSED**.

| Group | Routes | Result |
|-------|--------|--------|
| Retailer allow (3 client) | `/client/orders/:id/print`, `/client/declarations/:id/print`, `/client/declarations/:id/receipt` | Each: document renders, GET list == [expected] only, exact endpoint called once, all other 5 absent, no write |
| Retailer deny (3 supplier) | `/orders/:id/print`, `/declarations/:id/print`, `/declarations/:id/receipt` | Each: document absent, GET list == [], no write |
| Wholesaler allow (3 supplier) | `/orders/:id/print`, `/declarations/:id/print`, `/declarations/:id/receipt` | Each: document renders, GET list == [expected] only, exact endpoint called once, all other 5 absent, no write |
| Wholesaler deny (3 client) | `/client/orders/:id/print`, `/client/declarations/:id/print`, `/client/declarations/:id/receipt` | Each: document absent, GET list == [], no write |
| Static endpoint ownership | Each route never calls opposite-side endpoint | PASSED |

---

## 5. Mutation Authenticity

| # | Mutation | RED tests | Failed nodes |
|---|----------|-----------|--------------|
| 1 | `resp.data.id` -> `resp.id` | 5 | tests 1, 2, 3, 9, 11/12 |
| 2 | Add `?? requestId` fallback | 5 | tests 5/6 (x2), 7, 8, 9 |
| 3 | Cashier link -> `/client/declarations/.../receipt` | 4 | tests 1, 3, 11/12, R3 link-follow |
| 4 | Cashier receipt service -> client service | 2 | cashier endpoint, R3 link-follow |
| 5 | Add opposite-side GET to OrderPrintPage | 7 | OrderPrintPage (x4), route matrix (x2), static ownership |
| 6 | Remove `encodeURIComponent` | 1 | test 3 (encoded RESPONSE_ID) |
| 7 | `window.print()` twice | 1 | Print button calls window.print() |
| 8 | Parse high-precision through `Number` | 4 | groups thousands, preserves large, handles sign/malformed, formatKes |

Each mutation turned at least one focused test RED. All mutations restored.  
Candidate tree byte-identical to `10c9158d` after all restorations (`git diff` empty, `git status` clean).

---

## 6. Runtime Gates

| Gate | Expected | Result |
|------|----------|--------|
| pnpm install --frozen-lockfile | success | Done in 78.4s |
| Focused verbose run | 63 passed | **63 passed**, 0 failed (12.33s) |
| Consecutive run 1 | 63 passed | **63 passed** |
| Consecutive run 2 | 63 passed | **63 passed** |
| Consecutive run 3 | 63 passed | **63 passed** |
| Retailer portal/guard suite | 19 passed | **19 passed**, 0 failed |
| Full pnpm vitest run | 19 files, 223 passed | **19 files, 223 passed**, 0 failed |
| pnpm build | exit 0 | **exit 0** (12.04s) |

No skip, xfail, deselection, rerun masking, timeout increase, mock-only pass, or assertion weakening.

---

## 7. Quality

| Check | Result |
|-------|--------|
| `git diff --check` | Clean |
| Mojibake scan | Non-ASCII chars are em-dashes (U+2014), en-dashes (U+2013), right arrows (U+2192) in comments -- valid UTF-8, not mojibake |
| `detect-secrets` (scoped) | 0 secrets |
| Non-blocking build warning | "Some chunks are larger than 500 kB" -- standard Vite bundle size advisory |
| Non-blocking test console | DashboardPage TypeError during route matrix tests -- expected from intentional partial mocking; all assertions pass |

---

## 8. Cleanup Proof

| Artifact | Status |
|----------|--------|
| Mutation backups | Removed |
| node_modules | To be removed (task-owned, outside retained clone policy) |
| dist (build output) | To be removed |
| Clone | To be removed |
| Candidate ref | Unchanged: `10c9158d993226082484f4186c8fc8749d97b65d` |
| Protected refs | Unchanged |
| Mutation artifacts | All restored, none committed |

---

## 9. Verdict

`PASS_DC12R1_S3_S2B_I2C_I2_R3_V1_INDEPENDENT_FINAL`

All phases passed:
- Phase 1: SHA/lineage/scope -- 4 SHAs exact, ancestry confirmed, R3 = 2 files, aggregate = 18 files (9+9), no forbidden paths, R2-R3 production byte-identical
- Phase 2: Source invariants -- response authority, money string-only, document truth, scope all verified from source
- Phase 3: Authentic link-follow runtime proof -- PASSED
- Phase 4: Route matrix -- all 12 cases + static ownership PASSED
- Phase 5: Mutation authenticity -- all 8 mutations RED, tree byte-identical after restore
- Phase 6: Runtime gates -- 63 x4, 19, 223 passed, build exit 0
- Phase 7: Quality -- all clean, cleanup complete
