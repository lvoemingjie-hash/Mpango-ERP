# DC-12R1-S3-S2B-I2C-I2B — Contract D Printable Relationship Statement

> **⚠️ SUPERSEDED_BY_I2C_I2B_R1**
>
> The `f9456bd` PASS verdict below is **superseded** by the R1 correction
> (Contract Truth Closure) on this same isolated branch. R1 closes **all
> seven** CTO merge blockers; the authoritative verdict is
> **PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I2B_R1_MERGE_REVIEW** (see §R1).
> Prior evidence (§0–§9) is preserved as non-authoritative history.

> Isolated branch:
> `zcode/dc12r1-s3-s2b-i2c-i2b-contract-d-statement-2026-08-10`

## 0 Verdict Summary

| Dimension | Result |
|---|---|
| Base / lineage | ✅ `origin/product-dev-recovered` == expected SHA `d45b5020`; clean isolated worktree |
| Scope discipline | ✅ Exactly 8 new + 10 edited = **18 files** (see §4); zero migration/permission/config/dependency/lockfile/deployment changes |
| Read-only statement | ✅ `GET /api/v1/client/statements/print` + `GET /api/v1/statements/print`; zero DB mutations; no ledger/event/outbox/payment-provider work |
| 14 binding accounting rules | ✅ All incorporated (see §2) — fail-closed 409s, dual-key isolation, independent lists, soft-delete retention, no balance leakage |
| Server-authoritative money | ✅ Decimal strings rendered via string-only grouping (shared `formatKes`); no Number/parseFloat/Intl parse (large >2^53 + high-precision preserved) |
| Static route ownership | ✅ `mode` fixed by static route config; `retailer_id`/`from`/`to` are read-only query inputs, `encodeURIComponent`-encoded |
| Neutral fail-closed UI | ✅ 401/403/404/409/5xx collapse to fixed neutral strings; a 409 (period/ledger-scope/reconciliation) is indistinguishable from not-available |
| Backend gates | ✅ Focused 18/18 natural + 18/18 reverse; regressions green; full `pytest tests/` on two independent fresh PG16+Redis7 stacks: identical totals, 0 failed / 0 errors |
| Frontend gates | ✅ Full `pnpm vitest run` 265/0 (incl. 38 new statement tests + 8-route matrix); `pnpm build` exit 0 |
| Self-review | ✅ `py_compile` clean; `git diff --check` clean; scoped pre-commit passed; detect-secrets 0 new; no mojibake; GitNexus analyze/status up-to-date |
| Verdict | **PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I2B_REVIEW** |

---

## 1 Objective

Contract D — read-only printable **relationship account statement**:

- Retailer: `GET /api/v1/client/statements/print?from=YYYY-MM-DD&to=YYYY-MM-DD`
  (permission `client:finance:read`; the retailer identity is **server-derived**
  from the token tenant — never a request-supplied selector).
- Supplier: `GET /api/v1/statements/print?retailer_id=<uuid>&from=&to=`
  (permission `finance:read`; `retailer_id` is only a target selector — the
  active binding under the token tenant remains the authority).

Explicit exclusions honoured: no I2C-I3 (movements projection service), no
S3-S3, no S4 (recurring/report generation); no financial writes; no events /
outbox / SMS / WhatsApp / provider credentials / PDF / QR / payment-provider
integration; no binding-cache repair; no migration 038.

## 2 Binding corrections (all incorporated)

1. **Opening balance** = receivable ledger sum **strictly before** the EAT
   period (UTC half-open `[start_utc, next_day_utc)` windowing, 365-day cap).
2. **Movements** = receivable ledger entries inside the inclusive `[from, to]`
   EAT period only (rule 3).
3. **Closing balance** = opening + net_movement, **re-derived independently**
   from a DB period sum; any arithmetic mismatch → 409
   `STATEMENT_INTERNAL_INCONSISTENT` (rule 4).
4. **charge / collection / net** derive **only** from the movements list
   (rule 5/6) — never from cached balances.
5. **settled_payments** = canonical **completed** payments only (rule 8);
   pending/rejected declarations and non-completed payments never affect any
   balance.
6. **Two independent lists** — movements (receivable ledger) and
   settled payments (payment records) are never cross-associated in the
   document or in tests (rule 7).
7. **Pending/rejected declarations** are non-accounting context; rendered only
   when explicitly requested (`?include_pending=true`); never affect balances
   (rule 7/11).
8. **Soft-deleted orders are retained** — receivable ledger rows whose order
   was soft-deleted still count (rule 10).
9. **Orphan receivable refs** (ledger row without its order) → fail-closed 409
   `STATEMENT_LEDGER_SCOPE_INCOMPLETE` (checked before any balance
   computation).
10. **Credit-only reconciliation** — for a relationship whose full payment
    history is credit-only, the ledger receivable total must equal the cached
    binding `outstanding_balance`; mismatch → 409
    `STATEMENT_RECONCILIATION_FAILED` (rule 11).
11. **Mixed relationships** — the statement prints the ledger-derived balance;
    `binding.outstanding_balance` is **never exposed** or reconciled in the
    public document (rule 12).
12. **Fail-closed completeness** — no partial document is ever returned after a
    fail-closed condition; zero DB mutations on any path (rule 13/14).
13. **Dual-key isolation** — tests prove a tenant-B retailer cannot see
    tenant-A data via the retailer route, and the supplier route resolves the
    binding authority server-side (retailer_id is not an access key).
14. **Deterministic neutral UI** — every failure (401/403/404/409/5xx)
    collapses to fixed neutral copy via `sanitizePrintError`; a 409 is
    deliberately indistinguishable from not-available.

## 3 Truth contract

- Only server-authoritative fields render. The browser never recomputes
  opening/closing/charge/collection/net or cross-associates movements with
  payments. Money stays an exact decimal string (string-only grouping).
- `mode` is fixed by static route config; `retailer_id`/`from`/`to`/
  `include_pending` are read-only GET inputs, never mode switches.
- No tokens/credentials in URLs; the shared axios client injects the bearer
  header. No internal IDs (schema names, ledger row UUIDs) reach the UI.
- The statement is a read-only document; no page or endpoint performs any
  write.

## 4 Exact changed-file scope (scope gate — 8 new + 10 edited = 18)

**New (8):**
- `backend/repositories/statement_repository.py`
- `backend/api/v1/statements.py`
- `backend/tests/test_dc12r1_contract_d_statement_print.py`
- `frontend/src/types/statement.ts`
- `frontend/src/services/statementService.ts`
- `frontend/src/pages/print/StatementPrintPage.tsx`
- `frontend/src/tests/StatementPrintWorkspace.test.tsx`
- `ai-ledger/product-ai/2026-08-10_dc12r1_s3_s2b_i2c_i2b_contract_d_statement.md`

**Edited (10):**
- `backend/schemas/print.py` (StatementPrintView + nested views)
- `backend/services/print_service.py` (additive `build_statement_print`)
- `backend/api/v1/client/statements.py` (additive `GET /print`)
- `backend/api/app.py` (mount supplier statements router)
- `backend/tests/test_dc12r1_s3_s1_catalog_order_hardening.py` (route-permission entry)
- `backend/tests/test_dc12r1_s3_s2_read_only_retailer_finance.py` (read-only route assertions)
- `frontend/src/router/AppRouter.tsx` (2 additive static routes)
- `frontend/src/pages/client/FinanceBalancePage.tsx` (statement entry link)
- `frontend/src/pages/finance/FinancePage.tsx` (per-retailer statement entry link)
- `frontend/src/tests/PrintableWorkspace.test.tsx` (guard matrix 6 → 8 routes)

No migration, permission, config, dependency, lockfile, or deployment changes.
Any 19th file would have triggered `STOP_AND_REPORT_CTO`.

## 5 Backend design (14 binding rules → code)

- `StatementRepository` (schema-qualified raw SQL; no `search_path` reliance):
  `eat_date_range_to_utc_half_open`, `count_orphan_receivable_refs`,
  `sum_receivable_before`, `list_movements`, `sum_receivable_period`,
  `list_settled_payments`, `list_pending_declarations`,
  `relationship_has_non_credit_payment`, `ledger_receivable_total`,
  `cached_binding_balance`.
- `build_statement_print` order: period validation → active-binding check
  (neutral 404) → orphan precheck (409) → opening sum → movements + DB period
  sum cross-check (409) → derived totals → settled payments → credit-only
  reconciliation (409) → optional pending list → assemble view.
- Routes map `StatementResult` to 404/409 with flattened
  `{code, message, request_id}` bodies; no partial documents.

## 6 Backend verification (real execution)

- Focused Contract D suite: **18/18** natural order + **18/18** reverse order
  (custom `-p _reverse_plugin`).
- Regressions: I2C-I1 36/36, I2B 42/42, I2A+finance+payments+orders 55/55,
  inventory (incl. 2 updated expected-dict tests) 50/50.
- Full suite `poetry run pytest tests/ -q` on **two independent fresh
  PG16+Redis7 stacks** (contractd_pg16 :5433 / contractd_redis7 :6380 and
  contractd_pg16_run2 :5434 / contractd_redis7_run2 :6381; both migrated to
  alembic 037; `REPORTING_USER_PASSWORD` set; real-Alembic tests authorized via
  `MPANGO_ENV=test`, `MPANGO_ALLOW_TEMP_DB_CREATE=1`,
  `TEST_DATABASE_URL=postgresql://mpango_test:***@localhost:<port>/test_mpango`,
  `MPANGO_TEMP_DB_ALLOWED_PORTS`):

| Run | Stack | Totals |
|---|---|---|
| #1 | :5433 / :6380 | **3234 passed, 48 skipped, 15 xfailed — 0 failed, 0 errors** (exit 0) |
| #2 | :5434 / :6381 | **3234 passed, 48 skipped, 15 xfailed — 0 failed, 0 errors** (exit 0) |

Both runs are identical with `0 failed / 0 errors` (warnings differ only by a
few non-deterministic DeprecationWarning counts: 2725 vs 2728).

> ⚠️ Environment note (honest reporting): two earlier full-run attempts on the
> :5433 stack were **invalid and discarded** because the harness environment
> was mis-configured, not the code:
> 1. First attempt omitted the real-Alembic prerequisites
>    (`MPANGO_ALLOW_TEMP_DB_CREATE=1`, `TEST_DATABASE_URL`) — 29 setup errors +
>    18 fails from `test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py`, whose
>    `_require_test_env` is intentionally fail-closed.
> 2. Second attempt used a non-superuser `mpango_test` role, which PG denies on
>    tables owned by the superuser that ran the migrations
>    (`permission denied for table tenant_registrations`,
>    `relation "ledger_entries" does not exist` for the reporting_user path).
> After rebuilding the stack (superuser test role; `reporting_user` created
> fresh; `test_mpango` migrated from zero), both runs above are green and
> identical. The focused Contract D suite and all regressions were green before
> and after; no production code changed between attempts.

## 7 Frontend verification (real execution)

- `frontend/src/tests/StatementPrintWorkspace.test.tsx` — 38 tests: endpoint
  ownership + encoding; deterministic rendering; independent movements /
  settled-payments sections; pending only when requested; `window.print()` once;
  cashier missing-`retailer_id` fail-closed with zero GETs; 401/403/404/409/5xx
  neutral copy (no body echo); zero mutation + **mutation RED** (write mocks
  throw); real-AppRouter guard matrix across **all 8 print routes**
  (retailer/wholesaler × ALLOW/DENY with exact endpoint exclusivity); genuine
  entry links from the real finance pages.
- `frontend/src/tests/PrintableWorkspace.test.tsx` — guard matrix extended
  6 → 8 routes (Contracts A–D).
- Full `pnpm vitest run`: **265 passed / 0 failed** (20 files).
- `pnpm build`: exit 0.

## 8 Self-review

- `python -m py_compile` on all 8 changed backend files: clean.
- `git diff --check`: clean (trailing-blank-line fix applied to
  `backend/schemas/print.py`).
- Scoped pre-commit (`pre-commit run --files` on the 18 changed files): all
  hooks passed (trim trailing whitespace, end-of-file-fixer, yaml, large files,
  detect-secrets).
- Mojibake scan: clean.
- GitNexus: `detect_changes` recorded pre-commit; `analyze` + `status` run
  post-commit; knowledge graph reflects the isolated branch state.
- Adversarial self-review: rule-by-rule pass over the 14 binding corrections
  against the implementation and tests (see §2 mapping).

## 9 Next steps (out of scope, explicitly not started)

I2C-I3 (movements projection service), S3-S3, S4 (recurring report
generation), PDF/QR generation, payment-provider integration, migration 038.

---

## §R1 Contract Truth Closure (SUPERSEDES the verdict above)

Starting SHA `f9456bd463f65091d11a851d60758985831987ac` (verified); protected
baseline `origin/product-dev-recovered` = `d45b5020` (unchanged). Scope:
statement repository/schema/service/routes, Contract D backend/frontend tests,
StatementPrintPage, statement types/service, the two finance entry pages, the
shared print date utility (`printFormat.ts`), and this ledger. **13 files
edited** (all within the existing Contract D file set; no new files, no
migrations, no permissions/config/dependencies, no financial writes).

### R1.1 Financial ownership (blocker 1)

- `list_settled_payments` and `relationship_has_non_credit_payment` now pin
  ownership fully: `p.retailer_id = :rid AND o.retailer_id = :rid AND
  o.wholesaler_id = :wid`.
- New same-schema precheck `count_completed_payment_ownership_mismatch`
  (completed, non-deleted payments whose retailer differs from their order's
  retailer) runs before any balance computation → 409
  `STATEMENT_INTERNAL_INCONSISTENT`, zero partial document.
- **RED/GREEN (real PG):** `TestPaymentOwnershipIntegrity` seeds a corrupt
  completed payment (`retailer_id != order.retailer_id`) and asserts 409 +
  no `data` + no corrupt id in the response, on BOTH routes. On the pre-R1
  implementation this returned 200 (RED); R1 returns 409 (GREEN).

### R1.2 Response truth (blocker 2)

- `settled_total` added, computed ONLY from `settled_payments[].amount`
  (service; tested: equals the sum of the settled list, 325.00 for two
  payments, never a movement/pending figure).
- `movement.kind` (`charge`|`collection`) + `display_amount=abs(signed_amount)`
  added; zero-valued movement fails closed as
  `STATEMENT_INTERNAL_INCONSISTENT` (test: seeded 0.00 charge → 409, no data).
- `movement_id` / `payment_id` REMOVED from response schemas and frontend
  types; serialized-response tests assert the keys are absent (`r.text`
  contains neither).
- Printable DOM never shows a full UUID (`shortRef` → first 8 chars);
  frontend tests assert `FULL_UUID_RE` does not match the document text.
- Independent movements/settled-payments lists preserved (existing tests kept).

### R1.3 Date error contract (blocker 3)

- Shared strict parser `parse_statement_date_range` used by BOTH routes:
  missing / blank / malformed / reversed / >365-day ranges → controlled
  **400 `INVALID_DATE_RANGE`** (never framework 422, never neutral 404).
- Public message is neutral; tests assert no raw parser details
  (`strptime`/`ValueError`/raw input) and parity across retailer + supplier.

### R1.4 Reconciliation tolerance (blocker 4)

- Credit-only reconciliation fails only when
  `abs(ledger_total - cached) > Decimal("0.01")`.
- Tests (real PG, credit-only setup): 0.001 difference → 200; 0.01 → 200;
  0.0101 → 409 `STATEMENT_RECONCILIATION_FAILED` with no `data`. The delta is
  introduced via a high-precision receivable LEDGER row because the cached
  binding column is `numeric(12,2)` (0.0101 would round to 0.01); the cached
  balance is pinned to exactly 0.

### R1.5 Bounded high-volume behavior (blocker 5)

- Exact aggregate line cap **1000**; movements, settled payments and optional
  declarations all query with `LIMIT cap+1`; combined line count > 1000 →
  controlled **400 `STATEMENT_RANGE_TOO_LARGE`**, zero partial document.
- Tests: 1001 pending declarations → 400 (message contains no internal
  counts); exactly-at-cap (998 pending + 1 settled + 1 movement = 1000) → 200.
- Frontend: a 400 shows the fixed neutral **“Choose a shorter date range.”**
  (status-only; no body echo). No silent truncation, no client pagination.

### R1.6 Fixed EAT frontend dates (blocker 6)

- `printFormat.ts` gains `eatDateFromUtc` / `eatToday` / `eatDefaultRange` /
  `eatMonthRange` (Intl.DateTimeFormat, `Africa/Nairobi`); the print page
  default range and BOTH finance entry links use EAT calendar dates — never
  browser-local dates. Money stays string-only (no Number/parseFloat/Intl
  arithmetic).
- Frozen-time boundary tests: at `2026-08-10T22:30:00Z` the UTC calendar date
  is 2026-08-10 while EAT is 2026-08-11; `eatToday()` returns 2026-08-11,
  `eatMonthRange()` returns 2026-08-01→2026-08-11, and the rendered
  retailer entry link carries exactly those EAT anchors.

### R1.7 Evidence repair (blocker 7)

- “No internal ID” tests now assert the serialized response contains no
  `movement_id`/`payment_id` and the printed DOM contains no full UUID.
- Soft-delete test repaired: snapshot taken BEFORE mutation; restore in
  `finally` via a FRESH session; `UPDATE rowcount == 1` asserted; exact
  reread equality asserted. New test proves an active and a soft-deleted
  order produce IDENTICAL accounting totals (opening/closing/charge/
  collection/net/settled_total).
- RED/GREEN coverage: settled_total absence, ownership mismatch, line
  overflow, date 400 contract, tolerance boundary, redaction and EAT
  defaults are all asserted by new tests (each RED on the pre-R1 code,
  GREEN now). No skip/xfail/deselection/mocks/timeout/weakened assertions.

### R1.8 Gates (exact commands + counts)

| Gate | Result |
|---|---|
| Focused Contract D natural | `pytest tests/test_dc12r1_contract_d_statement_print.py -q` → **32 passed** |
| Focused reverse | `-p _reverse_plugin_r1` → **32 passed** |
| Regressions (I2C-I1, I2B, I2A, route-inventory, read-only retailer finance, financial schema, orders) | **192 passed** |
| Full backend run #1 (independent fresh PG16 :5433 + Redis7 :6380) | **3267 passed, 29 skipped, 15 xfailed — 0 failed, 0 errors** (exit 0) |
| Full backend run #2 (independent fresh PG16 :5434 + Redis7 :6381) | **3267 passed, 29 skipped, 15 xfailed — 0 failed, 0 errors** (exit 0) |
| Frontend full vitest | `pnpm vitest run` → **270 passed / 0 failed** (20 files) |
| Frontend build | `pnpm build` exit 0 |
| Self-review | `py_compile` clean; `git diff --check` clean; scoped pre-commit all hooks passed; detect-secrets 0 new; UTF-8/mojibake scan clean; GitNexus `analyze` + `status` up-to-date post-commit |

One pytest process per run; no exclusions/reruns/deselection. The two full
runs are identical (warnings 2901 vs 2900 — non-deterministic
DeprecationWarning counts only).

### R1.9 Adversarial self-review

Each of the seven blockers was re-read against the implementation and its
tests before committing: ownership pins are present in both queries AND the
schema-level precheck; redaction verified at both the serialized-response and
DOM layers; the 400 date contract is enforced by ONE shared parser used by
both routes; tolerance is strictly `> 0.01`; the cap uses `LIMIT cap+1` so
overflow is detectable rather than truncated; EAT helpers are pure and
frozen-time tested; soft-delete evidence follows snapshot→mutate→fresh-session
restore→rowcount→reread. No migration, permission, config, dependency,
lockfile, deployment, payment/ledger mutation, or protected-branch push.
