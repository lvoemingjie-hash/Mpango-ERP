# R1 LOCK ORDER — actual discipline across ≥2 orders and ≥2 SKUs

Scope: the R1 order-state implementation
(`services/order_command_service.py`, the single status writer). This is
the analysis CTO §3 requires: the actual lock order, the inverse-order
exposure, and the exact unresolved risk — no unproven global-acyclicity
claim.

## 1. Per-command lock acquisition order

Row locks, in acquisition order, per command (every command locks the
order row FIRST):

```
confirm(o):  orders#o  (FOR UPDATE, populate_existing)
             → stocks#s   (FOR UPDATE, ordered by (sku_code, sku_id))
             → INSERT reservations(r_o,s)
             → bindings#w,r  (credit reservation UPDATE)
cancel(o):   orders#o  (FOR UPDATE, populate_existing)
             → reservations(r_o,*)  (FOR UPDATE, ordered by (sku_code, id))
             → stocks#s  (FOR UPDATE, per reservation, same sku order)
fulfill(o):  orders#o  (adapter -> command)
             → per item: stocks#s (FOR UPDATE) → reservations(r_o,item)
               (consumed) → INSERT movements
return(o):   orders#o → ledger INSERTs → stocks#s → INSERT movements
pay(o):      orders#o (canonical locked first read) → INSERT payments
             → ledger INSERTs → bindings#w,r (credit delta)
```

## 2. Inverse order exposure (confirm vs cancel/fulfill)

confirm takes `stocks` then inserts `reservations`; cancel takes
`reservations` then `stocks`; fulfill takes `stocks` then `reservations`.
The table-level order is therefore NOT uniform.

Why the risk has not produced a cycle in the demonstrated matrix (two
orders o1/o2, two SKUs sA/sB — exercised by
`tests/order_state_r1/test_concurrency.py::test_two_orders_two_skus_
reverse_order_confirm_matrix` with reverse item order):

- Every command locks `orders#o` first. Two commands on the SAME order are
  serialized there, so same-order inverse pairs (fulfill(o) stocks→resv
  vs cancel(o) resv→stocks) can never run concurrently.
- Different orders touch DISJOINT reservation rows (reservations are
  order-owned), so a cross-order cycle needs T1 holding stocks#sA waiting
  for reservations#r_o1 while T2 holds reservations#r_o2 waiting for
  stocks#sA — the wait edge T2→T1 exists, but T1 never waits on a row
  owned by o2 (o1's reservations are not touched by o2), so the reverse
  edge does not exist.

## 3. Unresolved risk (stated, not asserted away)

The argument above rests on the INVARIANT "order row locked before any
inventory row, by every writer". That is true of all writers today
(command service confirm/cancel/apply_transition, canonical pay, fulfill/
return routes) and enforced by the single-writer guard
(`test_static_guards.py`), but the acyclicity claim is a reasoned
invariant argument over the CURRENT call graph — not a formal proof over
arbitrary future writers, and not verified under a locking-discipline
mutation (there is no mechanism in this round that would make a future
writer lock inventories first; only the static single-status-writer guard
protects the write, not the lock order). If a future writer bypasses the
command service for a status write while taking inventory locks, the
inverse-order deadlock window reopens.

Mitigation options recorded for the implementing reviewer: (a) keep the
single-writer discipline and the orders-first invariant (current choice);
(b) make cancel take stocks before reservations (uniform order, extra
lock traffic). No change is made in this round beyond documenting the
invariant.
