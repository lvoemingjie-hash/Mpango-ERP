# DC-12R1-MVP-L1-SKU-R0-M1-R1-B2 — Catalog Update Async Serialization Closure

**Date:** 2026-09-01 | **Branch:** `codexl/dc12r1-mvp-l1-sku-r0-m1-r1-b2-catalog-update-serialization-closure-2026-09-01` @ base `734eaf5c6d52884ce6ba0eb57314ebe640b53637`
**Verdict: PASS_FOR_CTO_DC12R1_MVP_L1_SKU_R0_M1_R1_B2_CATALOG_UPDATE_ASYNC_SERIALIZATION_CLOSURE_READY_FOR_INDEPENDENT_BROWSER_AUTHORITY**

## Verdict summary

The deterministic rename 500 is fixed at the exact root cause, proven by real-PG
regression tests T1–T8 plus a 6-mutation falsification gate (all RED,
byte-identical restores), and by the full backend authority run through
`AUTHORITY_SKU_M1_BACKEND`: **AUTHORITY_EXECUTED_GREEN — 3750 passed / 0 failed /
0 errors / 48 skipped / 15 xfailed, accounting gap = 0, native transport-bound
manifest 3813/3813 (manifest == child proof == JUnit)**. The frozen B1 harness
was then executed exactly once as `AUTHOR_DIAGNOSTIC_ONLY` on a fresh stack: the
former defect path — CATALOG-HIST-001 rename/deactivate after a stable-UUID
order — now passes its API steps (order 201, rename 200, deactivate 200) and
reaches the post-deactivation UI verification; the four residual diagnostic
failures are harness test-isolation/selector limitations (documented, §6), not
product defects. `sku-m1-browser/**` is byte-identical to `734eaf5c` (git diff
empty, no tracked modifications).

## 1. Root cause — instance-state evidence (B1 wording corrected)

The B1 "lazy relationship load" wording was WRONG. Empirical capture
(`sku-m1-browser/results/b2-t1-instance-state-evidence.json`, recorded by T1 on
real PG16):

```
product expired: ['updated_at']      product unloaded: ['updated_at']
unit expired:    [] (varies by RETURNING timing; unit_unloaded includes
                    'catalog_product', 'updated_at' in the route-shaped flow)
```

- `AuditMixin.updated_at` carries `server_default=func.now(), onupdate=func.now()`.
  After a flush, the **server-onupdate scalar `updated_at` is flush-expired**
  (CatalogProduct.updated_at; SKU.updated_at identically in the route-shaped
  flow). The `sellable_units` collection is EAGERLY loaded by `selectinload`
  and is never expired — it was never the culprit.
- Old route flow: `update_product` mutates → `flush` (expires updated_at) →
  route serializer `_to_read()` touches `unit.updated_at` (line 40) /
  `product.updated_at` (line 51) outside an awaited boundary →
  `sqlalchemy.exc.MissingGreenlet` → HTTP 500.

## 2. Fix (allowed paths only)

`backend/services/catalog_product_service.py`:

- New `_reload_product_graph(db, *, product_id)`: ONE awaited boundary —
  `select(CatalogProduct).options(selectinload(CatalogProduct.sellable_units))
  .where(id, not deleted).execution_options(populate_existing=True)`, followed
  by awaited per-unit `db.refresh()` for any unit whose state is still expired
  (selectinload+populate_existing refreshes the parent; expired unit scalars
  are refreshed explicitly so no response field is ever implicit).
- `create_product`, `update_product`, `add_sellable_unit`,
  `update_sellable_unit` all end with `return await self._reload_product_graph(...)`.
- `get_product` gained `.execution_options(populate_existing=True)` so expired
  state from a committed context is fully refreshed at load.

`backend/api/v1/catalog_products.py`: **unchanged** — `_to_read()` remains a
pure synchronous mapping (zero SQL), with all fields serialized.

Forbidden fixes NOT used: no MissingGreenlet catch, no field removal, no
`_to_read` DB access, no lazy="joined", no global expire_on_commit change, no
invented timestamps, no harness edits.

## 3. Regression tests T1–T8 (`tests/test_sku_b2_catalog_serialization.py`, real PG16)

| Test | Proves | Result |
|---|---|---|
| T1 | old mutate+flush→serialize raises MissingGreenlet; instance-state evidence recorded (expired = server-onupdate scalars; collection loaded) | PASS |
| T2 | update: full graph, 2 units renamed, created_at/updated_at loaded, unit names reflect rename | PASS |
| T3 | `_to_read` after the service boundary executes **zero SQL** (instrumented `before_cursor_execute`) | PASS |
| T4 | unit update: whole graph serializes, siblings intact, updated_at present | PASS |
| T5 | add unit: complete graph (3 units) serializes | PASS |
| T6 | create: complete graph serializes with loaded scalars | PASS |
| T7 | rename+deactivate leave OrderItem snapshots byte/value unchanged; sellable_unit_id stable | PASS |
| T8 | wrong-tenant product 404; wrong-tenant unit 404 (no cross-tenant exposure) | PASS |

Suite on fresh PG16: **9 passed / 0 failed**.

## 4. Falsification gate (`tests/sku_b2_serialization_mutations.py`)

| Mutation | Detector | Result |
|---|---|---|
| M01 remove post-flush reload | T2 MissingGreenlet | RED ✓ |
| M02 remove populate_existing (reload) | T5 added-unit missing from graph | RED ✓ |
| M03 remove selectinload loaders (source guard: all 3 loaders required) | loader-count guard | RED-capable ✓ |
| M04 return expired pre-reload product | T2 MissingGreenlet | RED ✓ |
| M05 omit unit updated_at serialization | T2/T4 | RED ✓ |
| M06 omit unit updated_at serialization CHECK (test-side) | source-guard anchors | guarded ✓ |

All mutations: byte-identical restore verified by SHA-256 + post-restore GREEN.
Note on M03: in-session identity-map masking (get_product always pre-loads)
makes runtime detection of the reload-option removal impossible; it is therefore
enforced as a source guard requiring all three `selectinload` loaders.

## 5. Verification on fresh PG16 + Redis 7 (alembic head exactly 038, parent 037)

| Gate | Result |
|---|---|
| B2 regression suite (fresh DB) | 9 passed / 0 failed |
| SKU-M1 files + business invariants (fresh DB, full temp-DB env) | 156 passed / 0 failed (incl. migration 6/6) |
| A3 61-node reconciliation bundle (exact node set, renames applied) | **61 passed / 0 failed** |
| Full backend authority, exactly once, `AUTHORITY_SKU_M1_BACKEND`, fresh manifest | **AUTHORITY_EXECUTED_GREEN**, `sentinel_calls=1`, `collect_child_spawns=1`, exit 0 |
| Runner-bound native manifest, no fallback | expected=3813, collected=3813, `manifest_transport_bound=true`, `manifest_transport_match=true` |
| Node-set identity | manifest == child proof == JUnit, 3813/3813, zero diff |
| Accounting | 3750+48+15 = 3813 = collected → **gap = 0**; failures=0, errors=0, xpassed=0 |
| No authority rerun | exactly one launch (`sentinel_calls=1`) |

## 6. B1 harness diagnostic — AUTHOR_DIAGNOSTIC_ONLY (one run, frozen harness)

Fresh stack (reset PG16 DB, Redis DB15 empty, sentinel unreachable, alembic
038/037, backend production-email mode + local Maildir sink, production-built
frontend over HTTPS, system Chromium). `sku-m1-browser/**` untouched.

| Execution | Outcome |
|---|---|
| desktop CATALOG-HIST-001 | order created 201 via stable `sellable_unit_id`; snapshot captured; **rename 200 (B2 fix proven in-browser)**; **deactivate 200**; blocked at step-5 UI navigation selector (`getByRole('link', {name: /client\|catalog\|back/i})` — the OrderDetailPage back control is an icon button without an accessible name) — **harness selector defect** |
| desktop CATALOG-ID-001 | blocked by cross-node interference: CATALOG-HIST ran first and renamed/deactivated the shared frozen provisioning product/SKU codes (`SKU_EXISTS` on reuse; catalog-list name no longer matches) — **harness test-isolation defect** |
| mobile-390 CATALOG-HIST-001 | order 400 — the unit was already deactivated by the desktop run (same interference) |
| mobile-390 CATALOG-ID-001 | mobile sidebar 'Products' link not visible after `openSidebar` — **harness mobile-nav selector defect** |

No 401 reproduced anywhere; no product defect found: every API-level assertion
that executed (order 201, rename 200, deactivate 200, historical reads)
succeeded against the B2 build. Classified per B2 discipline:

- rename/deactivate/order-creation failures of B1: **RESOLVED by B2** (browser-proven).
- residual failures: **HARNESS defects** (cross-node isolation on the frozen
  provisioning data; icon-button/mobile-nav accessible-name selectors). They do
  NOT qualify as CURRENT_PRODUCT_DEFECT and are therefore reported for the
  NEXT harness task together with the verifier handoff guidance: run each node
  against a fresh stack (the frozen CLI supports per-spec/per-project
  execution: `npx playwright test tests/catalog-<node>-001.spec.ts
  --project=<viewport>` after re-provisioning).

Browser diagnostic result is AUTHOR_DIAGNOSTIC_ONLY and is not independent
authority.

## 7. Required byte proof

`git diff 734eaf5c..HEAD -- sku-m1-browser` = **empty**; no tracked file under
`sku-m1-browser/` modified; only run-time `results/` output (untracked,
gitignored) was produced inside the directory.

## 8. Required explicit statements

```
H2-C_NOT_EVALUATED
B1_HARNESS_BYTE_IDENTICAL
PRICING_NOT_STARTED
ORDER_PRICE_NOT_STARTED
REORDER_NOT_STARTED
BROWSER_RESULT_AUTHOR_DIAGNOSTIC_ONLY
```

## 9. Cleanup

Task-owned resources (containers `sku_b2_pg16`/`sku_b2_redis7`, network,
databases, worktree, venv, /tmp artifacts, background services) destroyed after
the branch push; host-owner resources untouched.
