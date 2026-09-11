# SKU BC-06 R2-R1 — LOCK LIVENESS (soft-delete excluded) + set_price LOCK-RESULT CHECK (audit ledger)

- CTO_AUTHORIZATION_ID: SKU BC-06 R2-R1 (repair on CTO-AUTH-DC12R1-MVP-L1-SKU-BC06-R2-HISTORY-LOCK-ORM-FRESHNESS-2026-09-11 candidate)
- EXECUTOR: ZCode-W
- BASE CANDIDATE: 3e831384ffd067633b9324deec728b7b1370d739 (R2 tip; verified == origin/zcode/dc-12r1-mvp-l1-sku-bc06-r2-history-lock-2026-09-11 at start; parent f151f53da2374c2b9b23b2899fa1b2b7cef6f48d)
- BRANCH: zcode/dc-12r1-mvp-l1-sku-bc06-r2r1-lock-liveness-404-2026-09-11 (new branch; no amend/rebase/force; R2 history untouched)
- CLAIM CEILING: CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW; no merge/deploy claims
- NEXT_GATE: Kilo 独立源码与真实生命周期审查

## FIXES

1. `package_identity.lock_sku_row`: FOR UPDATE query now excludes `is_deleted=true`
   (`.where(SKU.id == sku_id, SKU.is_deleted.is_(False))`), `populate_existing=True` retained; the
   post-lock re-read LIVE row is the only object callers write through. `None` now means
   "missing OR soft-deleted as of lock acquisition".
2. `set_price` (pricing_repository) now CHECKS the lock result: `None` → structured 409-family sibling
   `404 {"code": "SKU_NOT_FOUND", "message": f"SKU '{sku_id}' not found"}` with ZERO price writes —
   the backstop holds even when callers skip their own prechecks. `update_sku` / `update_sellable_unit`
   already failed closed on `None` with their existing structured Not Found semantics (R2), which now
   also covers concurrent soft-deletion because of fix 1.

## TEST DELTAS (focused suite 23 → 30 nodes)

- `test_reservation_status_locks_repackage[reserved|consumed|released]` — replaces the two R2
  reservation tests; unified parametrization proves the R2-confirmed "any retained reservation row
  blocks" across every live status, so a per-status exception cannot slip back in.
- `test_concurrent_soft_delete_wins_updater_returns_structured_404[sku|unit|set_price]` — two REAL
  connections, event barriers: updater FIRST reads the ACTIVE row (b_precheck), A holds the shared skus
  row lock and commits the soft-delete, the updater's lock acquisition then resolves to None →
  structured 404 (SKU_NOT_FOUND / SELLABLE_UNIT_NOT_FOUND) with ZERO business writes (name,
  package_quantity, price rows all untouched; deleter's soft-delete is the surviving state).
- `test_reverse_linearization_update_wins_then_soft_delete[sku|unit]` — the REVERSE order explicitly
  verified: the updater commits first (event-sequenced: b_committed set only after the commit returned),
  then the soft-delete retires the row; final state proves both writes in exactly that order
  (package_quantity 24.000 AND is_deleted true). No arbitrary-outcome greenwashing.
- `test_set_price_fail_closed_on_missing_or_soft_deleted_sku` — soft-deleted AND never-existing SKU →
  404 SKU_NOT_FOUND, zero price rows.

## FALSIFICATION (each: semantic RED → sha256-verified byte-identical restore → full 30/30 suite GREEN)

- M-A remove the soft-delete filter from the lock query → ALL THREE
  `test_concurrent_soft_delete_wins_updater_returns_structured_404` variants RED
  ("the updater must fail closed on the concurrently soft-deleted SKU, not write against a dead row").
- M-B make set_price ignore the lock result → `test_set_price_fail_closed_on_missing_or_soft_deleted_sku`
  RED ("DID NOT RAISE" — a price row would have been written for the dead SKU).
- M-C exclude `released` from the reservation probe → `test_reservation_status_locks_repackage[released]`
  RED ("DID NOT RAISE") while reserved/consumed stay green — proving the parametrization pins every status.
- Snapshot SHA-256: package_identity f294fff2…, pricing_repository 09ac19d5….

## GATES

- Pre-edit GitNexus impact: lock_sku_row **HIGH** (6 impacted) — disclosed, not downgraded; set_price
  LOW(1); update_sku LOW(1) [qualified UID]; update_sellable_unit LOW(1) [qualified UID].
- detect-changes on the FINAL candidate staged diff vs parent 3e831384 (recomputed, not reused from
  any prior report): **4 files / 4 symbols / 5 affected flows / risk MEDIUM** (the fourth file is this
  ledger; code symbols: set_price, lock_sku_row, package_quantity_changed, has_transaction_history —
  the probe function retains its R1 name in the graph index; its R2 body is the identity-use history
  check).
- Real PG16 16.15 (task-private container, URL-safe task credential): focused suite 30/30 GREEN —
  re-run GREEN after EVERY mutation restore; regression batch 128 passed (pricing phase3/phase4, sku
  m1 catalog identity/api rbac/b2 serialization/r1 multipackaging closure, order creation/api, import
  apply, intake apply).
- Typecheck: mypy/ruff declared in pyproject but absent from the shared venv — py_compile executed on
  all five touched files: OK (recorded honestly as the available static gate).
- `git diff --check` clean; staged blobs strict UTF-8 / LF / no BOM / no NUL / no CR (byte-verified).
- detect-secrets-hook (pre-commit form) PASSED; `.secrets.baseline` sha256 03d01ade… verified identical
  before and after the scan (read-only proven).
- Candidate/parent/file-scope/worktree/remote-ref verified consistent; normal commit + normal push;
  local == remote verified after push.
- FULL_SUITE_RESULT=NOT_RUN (full 206-file suite not executed; recorded separately from the focused
  30/30 and regression 128 results). BROWSER_RUNTIME=NOT_RUN. No merge/deploy claims.

## INCIDENTS

None. No out-of-scope modification, no candidate drift, no test anomaly; STOP conditions not triggered.
