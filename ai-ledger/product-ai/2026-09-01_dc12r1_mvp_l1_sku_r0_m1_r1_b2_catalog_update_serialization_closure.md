# B2 Ledger — Catalog Update Async Serialization Closure (2026-09-01)

- Base `734eaf5c` (B1 tip). Ancestry 24a28d76 -> 8bdb9911 -> 8cef1fff ->
  0376ce93 -> 5c5a9a82 -> 734eaf5c -> B2.
- Root cause corrected vs B1 wording: NOT a lazy relationship load. The
  `sellable_units` collection is eagerly loaded (selectinload); the failure
  class is flush-expired server-onupdate SCALAR state —
  `CatalogProduct.updated_at` / `SKU.updated_at`
  (`AuditMixin.updated_at onupdate=func.now()`) touched by `_to_read()`
  outside an awaited boundary. Evidence recorded in
  `sku-m1-browser/results/b2-t1-instance-state-evidence.json` (T1, real PG16).
- Fix (services/catalog_product_service.py only): `_reload_product_graph`
  awaited boundary (selectinload + populate_existing + per-unit awaited
  refresh of expired scalars) applied to create_product, update_product,
  add_sellable_unit, update_sellable_unit; get_product gains
  populate_existing. `_to_read()` remains pure (zero SQL).
- Regression: T1–T8 on real PG16 (9 passed), incl. zero-implicit-SQL proof
  (instrumented) and historical snapshot integrity. Falsification: 6
  mutations (M01 remove reload, M02 remove populate_existing, M03
  selectinload source guard, M04 expired pre-reload return, M05 omit unit
  updated_at serialization, M06 test-check omission guard) — all RED,
  byte-identical restores.
- Verification: fresh PG16/Redis7; SKU-M1 + business 156 pass; A3 61-node
  bundle 61 pass; full backend authority exactly once via
  AUTHORITY_SKU_M1_BACKEND — AUTHORITY_EXECUTED_GREEN, 3750/48/15, gap=0,
  manifest==child==junit 3813/3813, native transport binding, no fallback,
  no rerun.
- B1 harness diagnostic (AUTHOR_DIAGNOSTIC_ONLY, one run, frozen harness):
  rename/deactivate defect RESOLVED in-browser (order 201, rename 200,
  deactivate 200 on desktop CATALOG-HIST-001). Residual failures classified
  HARNESS (cross-node provisioning isolation; icon-button/mobile-nav
  accessible-name selectors). No 401 reproduced; no CURRENT_PRODUCT_DEFECT.
- sku-m1-browser/** byte-identical to 734eaf5c (git diff empty).
- Scope: only services/catalog_product_service.py (product), one new test
  file + one mutation runner (tests), B2 ledger/report. No migrations, no
  frontend, no H2-C, no pricing/order/reorder, no A3 evidence changes.
