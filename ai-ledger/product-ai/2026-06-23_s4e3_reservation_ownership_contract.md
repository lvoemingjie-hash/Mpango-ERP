# S4-E3: Reservation Ownership Contract

| Field | Value |
|-------|-------|
| Date | 2026-06-23 |
| Branch | `opencode/s4e3-reservation-ownership-contract-2026-06-23` |
| Base | `origin/product-dev-recovered` @ `7c660d4` (`merge: S4-D inventory movement ledger integrity gate`) |
| Final commit | Reported in handoff because a commit cannot contain its own final hash. |
| Verdict | PASS_FOR_CTO_REVIEW |

---

## Changed Files

Production code and schema:

- `backend/alembic/versions/023_inventory_reservations.py`
- `backend/models/inventory_reservation.py`
- `backend/models/__init__.py`
- `backend/services/inventory_service.py`
- `backend/api/v1/orders.py`
- `backend/api/v1/client/orders.py`
- `backend/scripts/bootstrap_tenant_schema.py`

Tests and ledger:

- `backend/tests/conftest.py`
- `backend/tests/business/test_s4e_reservation_schema_contract.py`
- `backend/tests/business/test_s4e_stock_reservation_lifecycle_audit.py`
- `ai-ledger/product-ai/2026-06-23_s4e3_reservation_ownership_contract.md`

No frontend, deployment, or product-dev branch changes were made.

---

## Implementation Summary

- Added tenant-schema table `inventory_reservations` as the reservation ownership source of truth.
- Kept `inventory_stocks.quantity_reserved` as aggregate fast-read projection only.
- Added ORM model `InventoryReservation` and exported it from `models`.
- Added production tenant bootstrap DDL and test tenant bootstrap DDL for fresh schema coverage.
- Added route/service wiring for exact order-owned reservation creation, release, and consumption.
- Kept `OrderService.transition()` unchanged.
- Kept reserve/release/consume out of `InventoryMovement`; only physical fulfill deduction writes movement rows.

---

## Reservation Table Contract

Table: `inventory_reservations`

Columns:

- `id UUID PRIMARY KEY`
- `order_id UUID NOT NULL`
- `order_item_id UUID NOT NULL`
- `sku_id UUID NOT NULL`
- `sku_code VARCHAR(64) NOT NULL`
- `quantity NUMERIC(12,2) NOT NULL`
- `status VARCHAR(32) NOT NULL`: `reserved`, `consumed`, or `released`
- `reserved_at TIMESTAMPTZ NOT NULL`
- `consumed_at TIMESTAMPTZ NULL`
- `released_at TIMESTAMPTZ NULL`
- `reference_type VARCHAR(50) NOT NULL DEFAULT 'order'`
- `reference_id UUID NOT NULL`
- audit columns from project convention: `created_at`, `updated_at`, `is_deleted`, `deleted_at`, `created_by`, `updated_by`

Indexes and constraints:

- `ix_inventory_reservations_order_id`
- `ix_inventory_reservations_sku_id`
- `ix_inventory_reservations_status`
- `ux_inventory_reservations_active_order_item` partial unique index where `status = 'reserved'`
- `ck_inventory_reservations_quantity_positive`
- `ck_inventory_reservations_status`

---

## Lifecycle Semantics

Confirm:

- Admin `confirm_order()` performs draft-to-confirmed status update, refreshes order items, then calls `InventoryService.reserve_on_confirm()` in the same request transaction.
- `reserve_on_confirm()` locks the stock row by SKU, checks `available = quantity_on_hand - quantity_reserved`, inserts one reservation row per order item, and increments aggregate `quantity_reserved`.
- If stock is insufficient or reservation creation fails, the route rolls back; order remains `draft`, no reservation row remains, and aggregate stock is unchanged.

Cancel:

- Admin and client cancel routes capture whether the order was `confirmed` before cancellation.
- Confirmed cancellations call `InventoryService.release_on_cancel()` in the same transaction.
- Release locks reservation rows by `order_id` with `status='reserved'`, marks only those rows `released`, and decrements aggregate reserved by the exact owned quantities.
- Other orders' reservation rows are not queried or modified.

Fulfill:

- Admin `fulfill_order()` calls `InventoryService.deduct_on_fulfillment()` with `order_id` and `order_item_id`.
- If reserved rows exist for that exact order item, fulfillment locks and consumes those rows, decrements aggregate reserved by the exact owned quantity, and deducts on-hand stock.
- If no reserved rows exist for the order item, fulfillment treats the order as legacy/direct-paid and deducts only on-hand stock, leaving aggregate reserved untouched.
- No `updated_by`, status, timestamp, or other proxy is used to infer ownership.

Return:

- Return path remains physical-only: restores `quantity_on_hand` via restock and creates no reservation rows.

---

## Direct Paid Proof

Test: `test_direct_paid_order_with_no_reservation_preserves_unrelated_reservations`

Proof scenario:

- Order A is confirmed and owns a reservation row for SKU `S4E3-DIRECT-PAID`, quantity `3`.
- Order B is a direct seeded `paid` order for the same SKU and quantity, with `updated_by` set to prove S4-E2's proxy would be unsafe.
- Fulfilling order B creates no reservation rows for B and does not consume A's row.
- Final stock is `on_hand=7,reserved=3,available=4`.
- Order A remains `confirmed`; A's reservation row remains `status='reserved'`.

This proves legacy/direct-paid fulfillment cannot steal unrelated reservations even when status/audit metadata exists.

---

## Aggregate Consistency Proof

- `inventory_reservations` is the ownership source of truth.
- `quantity_reserved` changes only in the same transaction as reservation row creation, release, or consumption.
- Release/consume fail closed with `RESERVATION_AGGREGATE_MISMATCH` if aggregate reserved is lower than the exact owned quantity.
- Confirm fail closes with `INSUFFICIENT_AVAILABLE_STOCK` before any reservation row or aggregate change can commit.
- Tests assert reservation row statuses and aggregate stock after confirm, cancel, fulfill, direct-paid fulfill, return, and concurrency paths.

---

## GitNexus Impact Summary

Pre-change required GitNexus checks:

- `reserve_on_confirm`: not present on S4-D base, so impact/context returned target not found. S4-E3 adds it.
- `release_on_cancel`: not present on S4-D base, so impact/context returned target not found. S4-E3 adds it.
- `deduct_on_fulfillment`: LOW risk; direct upstream caller was API `fulfill_order`.
- `confirm_order`: LOW risk; no production upstream callers indexed.
- `cancel_order`: LOW risk; no production upstream callers indexed, test callers present in context.
- `fulfill_order`: LOW risk by impact; context showed many S4/S4-C/S4-D tests covering route behavior.
- `OrderService.transition`: HIGH risk; direct callers include `pay_order`, `fulfill_order`, `return_order`, seed data, and S5 tests. It was not modified.

Final staged `gitnexus_detect_changes(scope="staged")`:

- Risk: CRITICAL.
- Changed files: 11.
- Changed symbols: 59.
- Affected processes: 38.

Final compare `gitnexus_detect_changes(scope="compare", base_ref="origin/product-dev-recovered")`:

- Risk: CRITICAL.
- Changed files: 11.
- Changed symbols: 59.
- Affected processes: 38.

Reason:

- Route, bootstrap, and test fixture files are indexed broadly, so GitNexus attributes changes to adjacent client order reads, order route flows, bootstrap flows, and adjustment flows.
- Manual line-level review: production behavior changes are scoped to reservation ownership table creation, confirm reservation creation, confirmed cancel release, and fulfillment reservation consumption. `OrderService.transition()` and physical movement semantics were not changed.

---

## Exact Test Results

Schema + S4-E3 target contract:

```text
poetry run pytest tests/business/test_s4e_reservation_schema_contract.py tests/business/test_s4e_stock_reservation_lifecycle_audit.py -q -rxX --tb=short
15 passed, 28 warnings
```

S4-E3 target suite:

```text
poetry run pytest tests/business/test_s4e_stock_reservation_lifecycle_audit.py -q -rxX --tb=short
12 passed, 28 warnings
```

S4/S4-B/S4-C/S4-D/S4-E regression:

```text
poetry run pytest tests/business/test_s4_order_fulfillment_inventory_invariants.py tests/business/test_s4b_inventory_reversal_invariants.py tests/business/test_s4c_concurrent_fulfillment_oversell_invariants.py tests/business/test_s4d_inventory_movement_ledger_integrity.py tests/business/test_s4e_stock_reservation_lifecycle_audit.py -q --tb=short
41 passed, 59 warnings
```

S5/Phase5 regression:

```text
poetry run pytest tests/test_s5_order_state_machine.py tests/test_phase5_order_payment.py -q --tb=short
66 passed, 1 xfailed, 45 warnings
```

The remaining `1 xfailed` is pre-existing in Phase5 payment tests and is unrelated to S4-E3.

---

## Test Coverage Added

Schema/bootstrap contract:

- Model export exists.
- `inventory_reservations` table exists with required columns.
- Required indexes and constraints exist.
- Fresh tenant bootstrap creates the reservation table and indexes.

Business invariants:

- Confirm creates owned reservation rows and increments aggregate reserved.
- Confirm insufficient available rolls back order, stock, and reservation rows.
- Concurrent confirm does not over-reserve.
- Duplicate confirm does not create duplicate reservation rows.
- Cancel releases only this order's reservation rows.
- Duplicate cancel does not double release.
- Fulfill consumes only this order's reservation rows and leaves other orders reserved.
- Direct paid/no-reservation order preserves unrelated reservations even with `updated_by` set.
- Return restores on-hand and does not create reservations.
- Concurrent fulfill consumes once and writes one physical movement.
- Tenant isolation for reservation table and aggregate stock.
- Reserve/release write no physical movement; fulfill consume writes only the deduction movement.

---

## Remaining Risks

- Partial fulfillment is not modeled; service fails closed if owned reservation quantity does not exactly match the order item fulfillment quantity.
- Existing legacy/direct-paid orders without reservation rows still bypass reservation ownership and only deduct on-hand. This is intentional compatibility behavior.
- `quantity_reserved` is maintained transactionally as a projection, not recomputed on every read. If manual DB edits corrupt it, service fail-closed guards catch lower-than-owned aggregate values during release/consume.
- Existing test/bootstrap infrastructure still contains older S4 helper DDL in other test files; S4-E3's own tests and production bootstrap now cover the reservation table contract.

---

## Constraint Confirmations

- Product code changed: YES.
- Migration changed: YES, after adding contract tests.
- Frontend changed: NO.
- Deployment: NO.
- Pushed `product-dev-recovered`: NO.
- `OrderService.transition()` changed: NO.
- Existing S4/S4-B/S4-C/S4-D/S4-E tests deleted, skipped, or relaxed: NO.
- Used `updated_by` / status / timestamps as reservation ownership proxy: NO.
- Reservation writes to `InventoryMovement`: NO.
- Secrets printed: NO.
