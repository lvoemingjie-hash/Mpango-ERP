# R1 LOCK ORDER — actual discipline across ≥2 orders and ≥2 SKUs

Scope: the R1 order-state implementation
(`services/order_command_service.py`, the single status writer), F3
state. This is the analysis CTO §3 requires: the actual lock order, the
inverse-order exposure, and the exact unresolved risk — no unproven
global-acyclicity claim.

## 1. Per-command lock acquisition order

Row locks, in acquisition order, per command (every command locks the
order row FIRST):

```
confirm(o):  orders#o  (FOR UPDATE, populate_existing)
             → stocks#s   (FOR UPDATE via _prelock_stocks: EVERY distinct
               sku_id, deduplicated, ONE global sorted-sku_id (UUID)
               order, before any inventory write)
             → INSERT reservations(r_o,s)
             → bindings#w,r  (credit reservation UPDATE)
cancel(o):   orders#o  (FOR UPDATE, populate_existing)
             → stocks#s   (FOR UPDATE via _prelock_reservation_stocks:
               the stock set derives from the order's ACTIVE reservations,
               locked by reservation.sku_id in the same global sorted
               order; a legacy order with no active reservations locks
               nothing — pure status transition)
             → reservations(r_o,*)  (FOR UPDATE, ordered by (sku_code,
               id), populate_existing) → released in place
fulfill(o):  orders#o  (FOR UPDATE, populate_existing)
             → NULL-identity guard (409 ORDER_ITEM_SELLABLE_ID_REQUIRED
               before any lock or write)
             → stocks#s   (FOR UPDATE via _prelock_stocks, global
               sorted-sku_id order, ALL rows BEFORE the first write)
             → per item: deduct (consumes reservation, updates stock,
               INSERT movements)
return(o):   orders#o  (FOR UPDATE, populate_existing)
             → NULL-identity guard (409 ORDER_ITEM_SELLABLE_ID_REQUIRED
               before ledger or inventory effects)
             → ledger INSERTs (return reversal)
             → stocks#s   (FOR UPDATE via _prelock_stocks, global
               sorted-sku_id order) → per item: restock + INSERT movements
pay(o):      orders#o (canonical locked first read) → INSERT payments
             → ledger INSERTs → bindings#w,r (credit delta)
```

## 2. Inverse order exposure (confirm vs cancel/fulfill)

The historical exposure — confirm taking `stocks` then inserting
`reservations` while cancel took `reservations` then `stocks` — is
CLOSED: since F2 every command pre-locks ALL of its stock rows in ONE
global sorted-sku_id (UUID) order BEFORE any inventory-row write, and F3
keeps that discipline for cancel by deriving the stock set from the
order's active reservations (sorted by reservation.sku_id) instead of
from `order.items`. Confirm, cancel, and fulfill therefore all acquire
`stocks` before touching `reservations`; the table-level order IS
uniform across commands.

Why the demonstrated matrix stays cycle-free (two orders o1/o2, two SKUs
sA/sB — exercised by
`tests/order_state_r1/test_concurrency.py::test_two_orders_two_skus_reverse_order_confirm_matrix`
with reverse item order, by
`tests/order_state_r1/test_f1_faces.py::test_confirm_vs_fulfill_two_orders_two_skus_reverse`,
and by
`tests/order_state_r1/test_f1_faces.py::test_cancel_vs_fulfill_two_orders_two_skus_reverse`):

- Every command locks `orders#o` first. Two commands on the SAME order
  are serialized there, so same-order pairs can never interleave their
  inventory locks.
- Different orders lock stock rows in the SAME global sorted-sku_id
  order, so cross-order stock acquisition cannot form a hold-and-wait
  cycle; reservation rows are order-owned and disjoint, so no
  cross-order reservation wait edge exists at all.

## 3. Unresolved risk (stated, not asserted away)

The argument above rests on the INVARIANT "order row locked before any
inventory row, by every writer, and all stock locks in the one global
sorted-sku_id order". That is true of all writers today (command service
confirm/cancel/fulfill/return, canonical pay) and is enforced by the
static guards (`test_static_guards.py`: single status writer, shared
prelock strategy — `_prelock_stocks` / `_prelock_reservation_stocks`
funnel every `_locked_stock_by_sku_id` call), but the acyclicity claim
is a reasoned invariant argument over the CURRENT call graph — not a
formal proof over arbitrary future writers. If a future writer bypasses
the command service for a status write while taking inventory locks, or
locks stocks outside the shared helpers, the deadlock window reopens.

Mitigation options recorded for the implementing reviewer: (a) keep the
single-writer discipline, the orders-first invariant and the single
global sorted-sku_id stock order (current choice); (b) add a
lock-ordering assertion to the static guards for any NEW inventory
writer. No change is made in this round beyond documenting the
invariant.
