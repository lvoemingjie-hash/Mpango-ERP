# DC-12R1-MVP-L1-SKU-R0-M1-R1-R1 Product-Level Multipackaging Contract Closure

Date: 2026-09-01

Owner line: ZCODE / Windows product repair line

Base: `a45fe99eaab73f4949cf4c3e4797626ec5f571cd`
(parent of the candidate; reference-only independent B4-V1 report branch
`reports/dc12r1-mvp-l1-sku-r0-m1-r1-b4-v1-lubuntu-independent-browser-authority-2026-09-01`
tip `8bc543c8` was NOT modified and NOT used as authority)

Product-byte candidate SHA (this branch, product+test commit):
`c2c3bff38514901d7d3f7d71bb49af6d6eb4226b`

Branch: `zcode/dc12r1-mvp-l1-sku-r0-m1-r1-r1-multipackaging-closure-2026-09-01`

Ancestry: `a45fe99e (base) -> c2c3bff3 (product candidate) -> <report commit>`

## Defects Closed

1. **CTO blocker
   `STOP_AND_REPORT_CTO__SKU_M1_PRODUCT_LEVEL_MULTIPACKAGING_CONTRACT_NOT_CLOSED`**
   — the retailer catalog listed ONE ITEM PER SKU (per sellable unit), and
   `GET /client/products/{id}` actually matched `skus.id`, so "product_id" was
   ambiguous with SKU.id. There was no packaging selector anywhere; a
   two-packaging product was presented as two independent product cards.
2. **Concurrent duplicate SKU-code 500 defect** — every SKU insertion path
   relied on a check-then-insert precheck; a concurrent duplicate insert hit
   the unique constraint at flush and surfaced as an unhandled
   IntegrityError → HTTP 500.

## Exact Changed-Path Inventory (a45fe99e..c2c3bff3)

```text
M    backend/api/v1/client/products.py               (product-level rewrite)
M    backend/schemas/client.py                       (product/unit view models)
M    backend/services/catalog_product_service.py     (flush guard, 2 paths)
M    backend/services/import_service.py              (flush guard, bulk path)
M    backend/services/sku_service.py                 (flush guard, legacy path)
A    backend/services/sku_integrity.py               (named-constraint guard)
A    backend/tests/test_sku_r1_multipackaging_closure.py
A    backend/tests/test_sku_r1_client_catalog_contract.py
M    frontend/src/types/client.ts                    (product/unit types)
M    frontend/src/pages/client/ProductListPage.tsx   (one card per product)
M    frontend/src/pages/client/ProductDetailPage.tsx (packaging selector)
M    frontend/src/pages/client/CreateOrderPage.tsx   (per-unit picker)
A    frontend/src/tests/ClientMultipackaging.test.tsx
M    sku-m1-browser/tests/catalog-id-001.spec.ts     (strengthened oracle)
M    sku-m1-browser/tests/catalog-hist-001.spec.ts   (container-based interlude)
M    sku-m1-browser/validator/static_validator.py    (R1 anchors + forbidden per-SKU locator)
M    sku-m1-browser/validator/mutations.py           (M37-M42)
M    sku-m1-browser/README.md                        (mutation count 36 -> 42)
A    docs/ai-reports/windows/2026-09-01_dc12r1_mvp_l1_sku_r0_m1_r1_r1_multipackaging_closure.md
```

No migration was created and NO schema change was needed (stop condition not
triggered). No pricing, order-price, reorder or H2-C code was touched.

## API Old/New Contract Table (customer/retailer catalog)

| aspect | OLD (per-SKU) | NEW (product-level) |
| --- | --- | --- |
| list item granularity | one item per `skus` row | one item per `catalog_products` row |
| item `id` | SKU.id (ambiguous) | **CatalogProduct.id** (no `sellable_unit_id` at product level) |
| list pagination `total` | count of SKUs | count of PRODUCTS (units never counted) |
| packaging visibility | each SKU was its own "product" card | `units[]` nested inside the product object |
| unit fields | flat on the item | per unit: `sellable_unit_id`, `sku_code`, `unit`, `package_quantity`, `price`, `in_stock`, `stock_level`, `can_order` |
| detail path id | matched `skus.id` (ambiguity) | matches **`catalog_products.id` only**; a unit UUID is `404 PRODUCT_NOT_FOUND`; malformed id is a clean 404 without SQL |
| detail inactive product | `404 PRODUCT_INACTIVE` | preserved |
| price/stock | per SKU row | per unit; product-level `in_stock`/`stock_level`/`can_order` aggregate best unit |
| isolation | retailer_id-scoped prices, tenant search_path | unchanged (dual-key client identity, retailer-specific `retailer_prices` join) |
| ordering | stock DESC, name, sku_code | products `(name ASC, id ASC)`; units `(package_quantity ASC, sku_code ASC, sellable_unit_id ASC)` — deterministic |
| queries | count + paged join (per-SKU rows) | 3 awaited queries (count, page ids, unit rows for page) + detail 2 — zero N+1 |

Response envelope (`{items, pagination}` inside `DataResponse`) is unchanged;
permission (`client:catalog:read`) unchanged; only active units of active
products are ever visible (same visibility semantics as the old inner join).

## Product Grouping And Pagination Evidence

HTTP-level (real app + JWT retailer, real PG16 —
`tests/test_sku_r1_client_catalog_contract.py`, 8 nodes GREEN):

```text
R1-LIST-1  1 product (2 units)  -> items == 1; id == catalog_product_id;
           unit_count == 2; both codes nested in (qty, code) order
R1-LIST-2  3 products x 1 unit, size=2 -> page1 items=2, page2 items=1,
           pagination.total == 3 (products, NOT units), deterministic order
R1-LIST-3  search by unit sku_code -> exactly the parent product container
R1-DETAIL  detail by product id -> 200 + 2 units; detail by UNIT uuid -> 404
           PRODUCT_NOT_FOUND; detail /not-a-uuid -> 404 (no SQL)
R1-VIS     inactive unit hidden from units[]; all-inactive product absent from
           list; inactive product detail -> 404 PRODUCT_INACTIVE
R1-ISO     unpriced unit price==null & can_order==false; stock 0 ->
           OUT_OF_STOCK; retailer-specific price honored
```

Browser-level containment proof (both viewports, from
`results/reconciliation-in.jsonl` of the fresh-stack run):

```text
retailer_sees_product_in_catalog            <- exactly ONE product container
                                               (toHaveCount(1))
product_level_packaging_selection_visible   <- bottle AND case INSIDE that
                                               same container
packaging_selection_changes_sellable_unit_id<- data-selected-sellable-unit-id
                                               bottleUuid -> caseUuid -> bottleUuid
stock_updates_for_selected_unit             <- "Low Stock" (case, 5 on hand)
                                               vs "Limited Stock" (bottle, 50)
order_request_carried_selected_sellable_unit_uuid <- captured POST payload
submitted_identity_equals_chosen_unit       <- GET order items[0]
                                               .sellable_unit_id == chosen uuid
```

Screenshot/artifact references: the run captures no images by contract; the
authoritative visual-state evidence is the harness artifact set under
`sku-m1-browser/results/` — `playwright-report.json` (per-execution DOM
outcomes, both viewports), `reconciliation.json` (node x viewport accounting,
gap=0), `reconciliation-in.jsonl` (assertion lists above), `authority-report.json`,
`invocation-ledger.jsonl`, `live-execution-contract.json`, `preflight-verdict.json`
(embedded verbatim below). Selector truth is static-enforced (anchors +
forbidden per-SKU-link locator pattern).

## Submitted sellable_unit_id Evidence

- Frontend unit test F3 captures the real axios POST body:
  `items[0].sellable_unit_id === <case unit UUID>` exactly when the case
  packaging radio is selected (`frontend/src/tests/ClientMultipackaging.test.tsx`).
- Browser oracle: `observedOrderCreations` (passive request listener, no
  interception) captured `POST /api/v1/client/orders` with
  `payloadUnitIds` containing the selected `bottleUuid` after
  case->bottle re-selection, and the returned order detail
  (`GET /client/orders/{id}`, retailer bearer) returned
  `items[0].sellable_unit_id == bottleUuid` — both asserted per viewport and
  recorded as `order_request_carried_selected_sellable_unit_uuid` +
  `submitted_identity_equals_chosen_unit`.

## Concurrent Duplicate SKU-Code Race — Timeline And Exact Outcomes

Guard (`backend/services/sku_integrity.py`): catches IntegrityError at flush,
rolls back the failed transaction, and maps ONLY a violation of the exact
SKU-code unique constraint names — `skus_sku_code_key` (runtime tenant schema,
canonical bootstrap) or `ux_skus_sku_code` (legacy alembic public table) — to
`409 SKU_EXISTS`. Unrelated IntegrityErrors (check/FK/other uniques) propagate
UNCHANGED, never a 409. Wired into all four SKU insertion paths:
`create_product` (initial units), `add_sellable_unit`, `SKUService.create_sku`,
and bulk import apply. Friendly prechecks retained for UX; correctness no
longer depends on them.

Measured two-session race (real PG16, one tenant schema, same normalized code,
both sessions past the friendly precheck before either flush):

```text
t0 +0.0ms    two sessions/connections open, race code armed
t1 +50.3ms   gate released; BOTH requests passed the check-then-insert
             precheck concurrently
t2 +288.5ms  both settled: winner INSERT committed;
             loser flush raised 23505 on the SKU-code unique constraint
             -> named-constraint guard -> session rollback -> SKU_EXISTS

OUTCOME A: HTTP 201-equivalent success (product created)
OUTCOME B: HTTP 409 SKU_EXISTS
persisted sku rows for the raced code = 1   (loser's parent product row was
                                             rolled back with the transaction)
```

Automated suite (`tests/test_sku_r1_multipackaging_closure.py`, 5 nodes GREEN):

- `test_concurrent_duplicate_sku_code_races_deterministically` — 6 iterations,
  both session orders: ALWAYS exactly one success + one `409 SKU_EXISTS`,
  zero IntegrityError leaks, exactly one persisted SKU row AND one parent
  product per race.
- `test_race_loser_session_is_immediately_usable_and_parent_row_rolled_back`
  — the 409'd session immediately creates another product successfully.
- `test_concurrent_add_sellable_unit_race_maps_to_409` — the add-unit path:
  one success + one 409.
- `test_unrelated_integrity_violation_is_not_mapped_to_409` — a
  `ck_skus_package_quantity_positive` check violation through the SAME guarded
  flush propagates as the raw IntegrityError (never HTTPException/409), and
  the classifier is False for it while True for a real unique-code violation.
- `test_product_listing_groups_units_and_orders_deterministically` — route
  grouping/ordering/aggregation.

Zero 500s were observed in any race iteration, in the browser run backend
log, or in any suite run.

## Test Accounting

Focused backend (natural + reverse on SEPARATE fresh databases `r1_focus_a` /
`r1_focus_b`, each migrated 000→038 by the real chain):

```text
81 passed / 0 failed in BOTH orders:
  test_sku_r1_multipackaging_closure.py        5   (NEW)
  test_sku_r1_client_catalog_contract.py       8   (NEW)
  test_sku_m1_catalog_identity.py             16   (UUID identity, backfill
                                                     rules, snapshots — preserved)
  test_sku_b2_catalog_serialization.py         9   (B2 rename/deactivate — preserved)
  test_dc12r1_s3_s1_catalog_order_hardening.py 43  (RBAC isolation, dual-key
                                                     scoping — preserved)
```

Full backend suite (single author-diagnostic run, fresh DB `test_r1_backend`
migrated 000→038):

```text
3693 passed | 69 skipped | 15 xfailed | 0 product failures
50 nodes (15 FAILED + 35 ERROR) — ALL environment-gated, zero product
  defects: the three infra modules
  (test_dc11t2_async_test_utils, test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade,
  test_sku_m1_migration_pg16) fail closed without their documented opt-ins
  (KeyError TEST_DATABASE_URL; MPANGO_ALLOW_TEMP_DB_CREATE=1 gate;
  MPANGO_TEMP_DB_ALLOWED_PORTS). Immediately re-run with the documented env:
  62/62 PASSED.
Effective total: 3755 passed / 0 failed / 69 skipped / 15 xfailed.
```

Frontend:

```text
tsc -p tsconfig.app.json --noEmit      CLEAN (the repo-wide tsconfig.json run
                                       reports 27 PRE-EXISTING test-only type
                                       errors in untouched platform/ops test
                                       files — verified identical on pristine
                                       base a45fe99e via git stash; out of scope)
vitest run                             30 files / 403 tests PASSED
                                       (incl. NEW ClientMultipackaging.test.tsx:
                                       F1 single-container rendering, F2 selector
                                       switches unit/price/stock, F3 submission
                                       carries exactly the selected UUID)
pnpm build                             production build OK (VITE_API_URL bound
                                       at build time for the runtime stack)
```

Browser harness gates (all GREEN before the run):

```text
harness tsc --noEmit                        CLEAN
playwright --list                           exactly 4 executions; results tree
                                            byte-identical (no evidence written)
static_validator --allow-missing-reconciliation  GREEN (with new R1 anchors)
reconciliation_truth_tests.py               PASS (T01..T21b)
mutations.py                                ALL 42 mutations RED with
                                            byte-identical restore (36 prior +
                                            NEW M37-M42)
secret/artifact scan                        GREEN
git diff --check                            clean
```

## Stale-Test-Contract Changes (complete enumeration)

Backend: NONE — every pre-existing backend test passes unchanged (all
existing `/client/products` usages assert status codes/envelopes only).

Browser harness (oracle repair, per task item 3):

1. `tests/catalog-id-001.spec.ts` — steps 7–10 replaced: per-SKU link
   locators (`linkForSku`) removed; proof is now containment
   (`toHaveCount(1)`), in-container packaging, selector-driven
   `data-selected-sellable-unit-id` switching, selected-unit stock text, and
   the returned order identity. Steps 11–13 (mismatch/cross-tenant/identity)
   and all B1 anchors unchanged.
2. `tests/catalog-hist-001.spec.ts` — products-page interlude only: the
   active case unit must be visible INSIDE the product container and the
   deactivated unit absent from the same container
   (`await expect(unavailableUnitLink).toHaveCount(0);` anchor preserved
   verbatim). Journey bodies (order create, rename, deactivate, snapshot
   immutability) unchanged.
3. `validator/static_validator.py` — added 6 required R1 anchors; added
   forbidden pattern `selector:per_sku_link_locator` so two-SKU-link proofs
   can never be reintroduced.
4. `validator/mutations.py` — added M37–M42 (each RED, byte-identical
   restore); README mutation count updated.

No test was weakened, skipped, deselected or xfailed anywhere.

## Fresh-Stack AUTHOR_DIAGNOSTIC Browser Execution

Fresh task-private stack (nothing reused; loopback only):

```text
PostgreSQL 16 dc12r1_r1_pg16  127.0.0.1:18061  fresh db r1_browser, alembic
                              chain applied from empty through head 038
Redis 7    dc12r1_r1_redis7   127.0.0.1:18062  DB15 dbsize 0 before run;
                              sentinel 127.0.0.1:26379 unreachable
SMTP       local fake sink    127.0.0.1:18063  (Maildir in task results)
Backend    fresh uvicorn      127.0.0.1:18064  MPANGO_ENV=production, real SMTP
                              into the local sink; .env.prod never read
Frontend   production build   https://127.0.0.1:18065  (VITE_API_URL bound at
                              build time to http://127.0.0.1:18064/api/v1)
Browser    real Chromium /usr/bin/chromium-browser, fresh profile
```

Exactly ONE invocation (no rerun, no replay):

```text
B3_AUTHOR_DIAGNOSTIC=1  B4_INDEPENDENT_AUTHORITY unset
B1_CANDIDATE_SHA=c2c3bff38514901d7d3f7d71bb49af6d6eb4226b
workers=1 retries=0  (no grep/shard/repeat-each/only/skip/xfail/deselection)

  ✓  1 [desktop]    › catalog-hist-001.spec.ts:28:5 › CATALOG-HIST-001 (6.9s)
  ✓  2 [desktop]    › catalog-id-001.spec.ts:31:5  › CATALOG-ID-001   (8.7s)
  ✓  3 [mobile-390] › catalog-hist-001.spec.ts:28:5 › CATALOG-HIST-001 (6.8s)
  ✓  4 [mobile-390] › catalog-id-001.spec.ts:31:5  › CATALOG-ID-001   (8.1s)
  4 passed (49.0s)   exit 0
```

Post-run strict gates:

```text
static_validator.py                                    GREEN (gap=0)
static_validator.py --require-mode AUTHOR_DIAGNOSTIC   GREEN
static_validator.py --require-mode INDEPENDENT_AUTHORITY  RED
  (required_mode_not_met on all five sources — this author evidence can
   never be presented as independent)
tools/scan_artifacts.py                                GREEN (9 files, 0 findings)
```

Evidence binding (all five sources record execution_mode=AUTHOR_DIAGNOSTIC,
candidate_sha=c2c3bff38514901d7d3f7d71bb49af6d6eb4226b, workers=1, retries=0):

```text
invocation-ledger.jsonl: exactly one start + one end, zero refused,
  observed_node_count=4
live-execution-contract.json: {"execution_mode":"AUTHOR_DIAGNOSTIC",
  "candidate_sha":"c2c3bff38514901d7d3f7d71bb49af6d6eb4226b","workers":1,
  "retries":0,"expected_execution_count":4,"frozen_at_invocation_start":true}
playwright-report.json stats: {"expected":4,"unexpected":0,"flaky":0,
  "skipped":0,"duration":48973.721}
authority-report.json: status "passed", observed 4/4, all NO_FAILURE
reconciliation.json accounting: {"pass":4,"fail":0,"skipped":0,"not_run":0,
  "duplicates":0,"gap":0,"mode_mismatches":0,"candidate_sha_mismatches":0,
  "report_disagreements":0,...}, errors=[]
preflight-verdict.json: {"outcome":{"kind":"OK"},"sharedIdentitiesOnly":true}
```

Runtime observations: zero HTTP 401; only expected negative paths
(4×400 mismatched/cross-tenant selectors, 2×409 retired-code reuse); all 5
local sink emails delivered and consumed (real production-mode SMTP into the
fake sink only).

## Regression Preservation Evidence

- Stable UUID identity + no-guess backfill: `test_sku_m1_catalog_identity.py`
  16/16 GREEN in both orders.
- B2 rename/deactivate serialization: `test_sku_b2_catalog_serialization.py`
  9/9 GREEN in both orders; CATALOG-HIST-001 snapshot immutability passed on
  both viewports.
- Stock constraints and order snapshots: S5/S6 suites inside the full run
  GREEN (no stock/order code touched).
- Tenant/RBAC isolation: `test_dc12r1_s3_s1_catalog_order_hardening.py`
  43/43 GREEN in both orders; retailer-specific pricing isolation proven
  again in the new HTTP contract module.

## Cleanup Evidence

After PASS, all task-private infrastructure was removed: docker containers
`dc12r1_r1_pg16`/`dc12r1_r1_redis7`, network `dc12r1-r1-net`, SMTP sink /
backend uvicorn / HTTPS frontend processes, fresh venv, node_modules and
frontend dist, task worktree, Maildir, harness results and temporary files;
loopback ports 18061–18065 released. Evidence survives verbatim in this
report.

## Required Statements

```text
H2-C_NOT_EVALUATED
PRICING_NOT_STARTED
ORDER_PRICE_NOT_STARTED
REORDER_NOT_STARTED
B4_AUTHORITY_INVALIDATED_FOR_NEW_PRODUCT_BYTES
AUTHOR_DIAGNOSTIC_NOT_INDEPENDENT_AUTHORITY
REQUIRES_FRESH_KILO_AND_LUBUNTU_AUTHORITIES
```

## Verdict

```text
PASS_FOR_CTO_DC12R1_MVP_L1_SKU_R0_M1_R1_R1_AUTHOR_CANDIDATE_READY_FOR_KILO_AND_INDEPENDENT_AUTHORITIES
```
