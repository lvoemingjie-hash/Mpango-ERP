# B1 Ledger — SKU Browser Harness Authoring (2026-08-31)

- Base candidate `5c5a9a82a3a2f7f0d5471c38b204e76bac91745e`; ancestry
  24a28d76 -> 8bdb9911 -> 8cef1fff -> 0376ce93 -> 5c5a9a82 verified.
- Delivered the isolated frozen browser harness `sku-m1-browser/` for the two
  registered authoritative nodes CATALOG-ID-001 / CATALOG-HIST-001 (desktop +
  mobile-390 Chromium; real PG16/Redis7/backend/production frontend/system
  Chromium; public-API provisioning only; local Maildir SMTP; no mocks; no
  direct DB seeding; supported-navigation guard).
- Author gates GREEN: frozen install, playwright list (exactly 4 executions),
  static fail-closed validator, strict TS compile, 10/10 mutations RED with
  byte-identical restore, reconciliation contract (4 combinations, gap=0).
- AUTHOR_DIAGNOSTIC_ONLY runs found a deterministic CURRENT_PRODUCT_DEFECT:
  PUT /api/v1/catalog-products/{id} (rename) -> HTTP 500 via
  sqlalchemy.exc.MissingGreenlet raised in
  backend/api/v1/catalog_products.py::_to_read during update response
  serialization (relationship lazy-load outside the async greenlet).
  CATALOG-HIST-001 requires this rename; B1 stopped per failure discipline
  without repairing product code. Full detail in the B1 report.
- Secondary unclassified observation: sporadic in-run 401 UNAUTHENTICATED on
  isolated GETs during browser bursts (succeeds on replay; ~25 min token TTL
  remaining). Left for classification with the harness's embedded status/body
  diagnostics during the independent run.
- Scope: only `sku-m1-browser/**`, the two B1 docs, and no backend/frontend
  product files, no migrations, no existing unit tests, no H2-C paths, no
  pricing/order/reorder implementation, no dependency changes outside the
  isolated harness, no modification of A3 authority evidence.
