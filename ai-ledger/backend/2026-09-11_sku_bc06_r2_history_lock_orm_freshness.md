# SKU-BC06-R2 — HISTORY-LOCK EXTENSION + LOCKED-FRESH ORM READS (audit ledger)

- CTO_AUTHORIZATION_ID: CTO-AUTH-DC12R1-MVP-L1-SKU-BC06-R2-HISTORY-LOCK-ORM-FRESHNESS-2026-09-11
- EXECUTOR: ZCode-W
- FROZEN_INPUT_CANDIDATE: f151f53da2374c2b9b23b2899fa1b2b7cef6f48d (R1 tip; verified == origin/zcode/dc-12r1-mvp-l1-sku-bc06-r1-reprice-guard-2026-09-10 after `git fetch --all --prune`)
- BRANCH: zcode/dc-12r1-mvp-l1-sku-bc06-r2-history-lock-2026-09-11
- CLAIM_CEILING: CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY (no merge, no deploy, no browser run)
- NEXT_GATE: Kilo independent source + real-concurrency review

## SCOPE (R2 deltas on top of f151f53)

1. `backend/services/package_identity.py`
   - `has_transaction_history` → `has_identity_use_history`, now fail-closed across four probes:
     order_items INCLUDING soft-deleted rows (no `is_deleted` filter, by sellable_unit_id OR never-reused
     sku_code); ANY retained inventory_movements row; any inventory_stocks row with quantity_on_hand <> 0
     OR quantity_reserved <> 0 (checked regardless of is_deleted); ANY retained inventory_reservations row
     in ANY status — reserved/consumed/released all block; NO consumed/released exception granted
     (directive default: must not default to modifiable). Only the automatic all-zero inventory_stocks
     placeholder row is not history.
   - `lock_sku_row` now returns the LOCKED-FRESH ORM SKU: `select(SKU).where(id=...).with_for_update()`
     with `populate_existing=True` — one statement acquires the shared row lock and overwrites any stale
     pre-lock identity-map instance. Returns None only if the row vanished concurrently (callers raise 404).
2. `backend/services/sku_service.py` — `update_sku` uses the locked-fresh instance for BOTH the change
   decision and the write; concurrent soft-delete between precheck and lock → structured 404.
3. `backend/services/catalog_product_service.py` — `update_sellable_unit` identical wiring.
4. `backend/repositories/pricing_repository.py` — UNCHANGED this round: set_price keeps taking the SAME
   skus row lock (N6 mutation proved the sharing is load-bearing).
5. `backend/tests/test_sku_bc06_reprice_guard.py` — 14 → 23 nodes. New: soft-deleted order_items lock;
   inventory_movements lock; non-zero on-hand lock; non-zero reserved lock; active-reservation lock;
   consumed-reservation lock (no exception); locked-fresh two-connection test for BOTH entries; sibling-sync
   regression (product-level rename propagates name/description/category to all units while each unit keeps
   its own package_quantity).

## FALSIFICATION (each: semantic RED → sha256-verified byte-identical restore → full 23/23 suite GREEN)

- N1 remove inventory_movements probe → movement test RED "DID NOT RAISE". Restored sha 281fe369…
- N2 restore `is_deleted IS NOT TRUE` on order_items → soft-deleted-orders test RED "DID NOT RAISE". Restored.
- N3 remove non-zero stock + reservation probes → 4 tests RED "DID NOT RAISE". Restored.
- N4 remove populate_existing refresh → BOTH locked-fresh tests RED with the exact semantic failure:
  stale 1.000 vs committed 24.000 → wrongful REPRICE_REQUIRED 409. Restored.
- N5 remove shared guard from update_sellable_unit → live-price unit-entry test RED "DID NOT RAISE". Restored.
- N6 remove set_price's shared lock → price-first concurrency test RED at iteration 1
  ("price-first must gate the repackage, got success"). Restored.
- Snapshot hashes: package_identity 281fe369…, sku_service 0012b72f…, catalog_product_service b53da905…,
  pricing_repository 5bd32734….

## GATES

- Pre-edit: `git fetch --all --prune`; GitNexus analyze (37,981 nodes); impact — update_sku /
  update_sellable_unit / set_price LOW; lock_sku_row (6 impacted), ensure_package_quantity_change_allowed (4),
  has_transaction_history (5) reported **HIGH** — recorded honestly per directive.
- detect-changes (staged): 4 files / 10 symbols / 8 affected processes / risk **HIGH** — recorded honestly.
- Real PG16 16.15 (task-private container sku_bc06_r1_pg16, 127.0.0.1:17755, URL-safe task credential):
  focused suite 23/23 GREEN, re-run GREEN after EVERY mutation restore.
- Regression: 128 passed (phase3/phase4 pricing, sku m1 catalog identity + api rbac, sku b2 serialization,
  sku r1 multipackaging closure, order creation/api, u3c import apply, u4ib2 intake apply service).
- Typecheck: mypy/ruff/black declared in pyproject but NOT installed in the shared venv — executed
  `py_compile` on all five touched files as the available static gate: OK. Recorded honestly.
- `git diff --check` clean; staged blobs strict UTF-8 / LF / no BOM / no NUL (byte-verified).
- detect-secrets: repo pre-commit hook PASSED; `.secrets.baseline` sha256 03d01ade… verified IDENTICAL
  before and after the scan (read-only proven this round; R1's baseline-truncation incident not repeated).
- R1 erratum (no history rewritten): the R1 report's stated branch name
  zcode/dc-12r1-mvp-l1-sku-bc06-r1-reprice-guard-2026-09-10 is confirmed correct; both R1 and R2 report
  files live outside the candidate history (AI_REPORT_INBOX), so no candidate file needed changing.

## INCIDENTS

None this round. The secrets scan was executed only via the pre-commit hook form with before/after baseline
hash proof (the R1 working-tree baseline truncation came from a direct `detect-secrets scan --baseline`
invocation, which was not repeated).
