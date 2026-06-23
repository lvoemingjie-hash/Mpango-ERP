# S4-D: Inventory Movement Ledger Integrity Gate

| Field | Value |
|-------|-------|
| Date | 2026-06-23 |
| Branch | `opencode/s4d-inventory-movement-ledger-integrity-gate-2026-06-23` |
| Base | `origin/product-dev-recovered` @ `3accdfd` (`merge: S4-C2 concurrent fulfillment oversell guard`) |
| Commit | Pending until branch push; final commit is reported in handoff because the commit hash cannot be embedded in the same commit that creates this ledger. |
| Verdict | PASS_FOR_CTO_REVIEW |

---

## Changed Files

- `backend/tests/business/test_s4d_inventory_movement_ledger_integrity.py`
- `ai-ledger/product-ai/2026-06-23_s4d_inventory_movement_ledger_integrity_gate.md`

No production, migration, frontend, or deployment files were changed.

---

## Gate Scope

S4-D upgrades `InventoryMovement` from "record exists" coverage to audit ledger integrity coverage.

The new test-only gate verifies:

- Movement math: `quantity_before + quantity == quantity_after`.
- Movement type correctness: `deduction`, `restock`, and `adjustment` are not mixed.
- Reference integrity: order-driven movements use `reference_type='order'` and `reference_id=order.id`; manual adjustments use `reference_type='manual'` and no order reference.
- Failed operation integrity: failed fulfillment/return paths do not leave orphan movements or refund ledger entries.
- Multi-item order integrity: each SKU gets its own independent movement math.
- Concurrent fulfillment integrity: constrained stock produces one deduction only.
- Tenant isolation: another tenant schema with the same SKU code is not mutated.
- Movement list endpoint consistency: `/inventory/logs` response matches DB movement rows.

All tests use real tenant DB state and real `AsyncSession` / route/service handlers. No mocks are used for movement integrity.

---

## GitNexus Impact Summary

Pre-change impact analysis was run before adding the S4-D tests.

- `InventoryMovement`: HIGH risk. Directly used by `deduct_on_fulfillment`, `restock_on_return`, `adjust_stock`, and imported by `InventoryService`; affected processes include fulfillment, return, and manual inventory adjustment.
- `InventoryService.adjust_stock` / indexed as `adjust_stock`: LOW risk. Direct upstream caller is `adjust_inventory`.
- `InventoryService.deduct_on_fulfillment` / indexed as `deduct_on_fulfillment`: LOW risk. Direct upstream caller is `fulfill_order`.
- `InventoryService.restock_on_return` / indexed as `restock_on_return`: LOW risk. Direct upstream caller is `return_order`.
- `fulfill_order`: LOW risk. No upstream callers detected by GitNexus when tests are excluded.
- `return_order`: LOW risk. No upstream callers detected by GitNexus when tests are excluded.
- `adjust_inventory`: LOW risk. No upstream callers detected by GitNexus when tests are excluded.

Indexer note:

- Initial method impact for `deduct_on_fulfillment` and `restock_on_return` did not resolve until `gitnexus analyze` reindexed the branch containing the S4-C2 merge.

Final `gitnexus_detect_changes(scope="staged")`:

- Risk: LOW.
- Changed files: 2.
- Changed symbols: 0.
- Affected processes: 0.

Reason: S4-D is test-only plus ledger documentation; no indexed production symbol changed.

---

## Exact Test Results

S4-D target suite:

```text
poetry run pytest tests/business/test_s4d_inventory_movement_ledger_integrity.py -q -rxX --tb=short
9 passed, 13 warnings
```

S4 full invariant regression:

```text
poetry run pytest tests/business/test_s4_order_fulfillment_inventory_invariants.py tests/business/test_s4b_inventory_reversal_invariants.py tests/business/test_s4c_concurrent_fulfillment_oversell_invariants.py -q --tb=short
20 passed, 22 warnings
```

S5/Phase5 regression:

```text
poetry run pytest tests/test_s5_order_state_machine.py tests/test_phase5_order_payment.py -q --tb=short
66 passed, 1 xfailed, 46 warnings
```

The remaining `1 xfailed` is pre-existing in `tests/test_phase5_order_payment.py` and is not introduced by S4-D.

Environment note:

- Final test runs used explicit local env values from running containers without printing secrets:
  - `POSTGRES_HOST=127.0.0.1`
  - `POSTGRES_PORT=5432`
  - `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` from `mpango_postgres`
  - `REPORTING_USER_PASSWORD` from `mpango_prod_backend`
  - `REDIS_URL=redis://127.0.0.1:6379/0`
  - `DATABASE_URL` and `TEST_DATABASE_URL` unset

Hygiene:

```text
git diff --check
PASS
```

```text
Changed-file mojibake / non-ASCII scan
PASS
```

---

## Movement Invariant Findings

### Math consistency

PASS.

- Fulfillment: initial stock `10.00`, quantity `3.00`, final stock `7.00`, movement `10.00 + -3.00 == 7.00`.
- Return: fulfilled stock `7.00`, restock quantity `3.00`, final stock `10.00`, movement `7.00 + 3.00 == 10.00`.
- Manual adjustment: `+5.00` from `10.00` to `15.00`, then `-2.00` from `15.00` to `13.00`.
- Multi-item fulfillment: each SKU has independent before/after math.

### Reference integrity

PASS.

- Fulfillment and return movements use `reference_type='order'` and `reference_id=order.id`.
- Manual adjustment movements use `reference_type='manual'` and no order `reference_id`.
- Movement list endpoint returns the same id, SKU id/code, quantities, type, and reference fields as the DB row.

### Type correctness

PASS.

- Fulfillment writes `deduction`.
- Return writes sequence `deduction -> restock`.
- Manual adjustment writes `adjustment`, not `order` or `restock` semantics.

### Failed operation no orphan movement

PASS.

- Insufficient-stock fulfillment leaves stock unchanged and writes no deduction movement.
- Return/restock failure leaves only the prior deduction movement and writes no orphan restock.
- Return/restock failure writes no refund ledger entries.

### Concurrent no duplicate movement

PASS.

- Concurrent fulfillment with stock only enough for one allows one success only.
- Final stock is zero.
- Exactly one deduction movement exists.
- Movement quantity is `-5.00`, before is `5.00`, after is `0.00`, and total deduction cannot exceed initial stock.

### Tenant isolation

PASS.

- Tenant A fulfillment writes one tenant A movement and decrements tenant A stock.
- Tenant B shadow schema with same SKU code retains stock `99.00` and has zero movement rows.

---

## Xfail Status

- S4-D target suite has no xfails.
- S4 full invariant regression has no xfails.
- S5/Phase5 regression still has `1 xfailed` in existing payment tests; not introduced by S4-D.

---

## Final Verdict

PASS_FOR_CTO_REVIEW

No movement math, reference integrity, type correctness, orphan movement, duplicate movement, or tenant isolation gap was found by the S4-D test-only gate.

---

## Constraint Confirmations

- Production code changed: no.
- Migration changes: no.
- Frontend changes: no.
- Deployment: no.
- Pushed `product-dev-recovered`: no.
- `OrderService.transition()` changed: no.
- S4/S4-B/S4-C tests deleted or relaxed: no.
- Movement integrity mocked: no.
- Secrets printed: no.
