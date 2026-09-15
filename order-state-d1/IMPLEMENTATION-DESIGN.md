# IMPLEMENTATION-DESIGN — MPANGO-ORDER-STATE-AUTHORITY-D1 (R1)

R1 revision after Codex-L review `NEEDS_BOUNDED_EVIDENCE_AND_DESIGN_CORRECTION`
(review kind: source + retained evidence only). Replaces the D0 design in
full; the D0 document's contradictions identified by the reviewer are
resolved here as follows: notification timing is POST-COMMIT only (CTO
contract: no success facts may be observable while the transaction can
still roll back); the draft-cancellation matrix contradiction is resolved
by ONE normative matrix (Option A below) with the alternative spelled out;
the word "mechanical" is withdrawn — unifying the entry points changes
financial and state-compatibility behavior and every such change is listed
as a decision, not a consequence; service-path confirmation revenue is NOT
treated as approved (it is the single largest open CTO decision).

Author evidence by ZCode (executor) for Codex-L review. Claim ceiling:
`AUTHOR_ORDER_STATE_D1_R1_READY_FOR_CODEXL_REVIEW_ONLY`. Nothing here is
self-authorized for product implementation.

BASE: `1ee75d9faaa00cdcadfe9f46d1e0ac960efc632e`; candidate line:
`6f7e2efe` + one R1 commit. Evidence: `order-state-d1/BEHAVIOR-MATRIX.csv`
and `backend/tests/order_state_d1/` (33 tests; final R1 run
`evidence/2026-09-15T1240Z-r1-full-directory-run1.txt`: 27 passed,
6 named product REDs, pytest rc=1 — acceptance criterion "credible and
bounded, not all green" is met).

---

## 0. What the evidence establishes (current behavior, not contract)

Two divergent write paths plus one locked service (full table:
BEHAVIOR-MATRIX.csv):

| Writer | Matrix source | Order-row lock | Fresh after lock | Confirm ledger | Notifications |
|---|---|---|---|---|---|
| `crud/order.py` actions (HTTP confirm; both cancels) | CRUD `STATE_TRANSITIONS` | none | n/a | none | none |
| `OrderService.transition` (HTTP fulfill/return; pay via canonical) | domain `STATE_TRANSITION_MATRIX` | FOR UPDATE, **no populate_existing** | NO (stale identity-map attrs validated) | posts receivable/revenue | fired INSIDE the transaction (pre-commit) |
| `CanonicalPaymentService` (pay; declare) | computed target | FOR UPDATE, locked read is first read | yes | per transition method | via transition only |

Named REDs reproduced (assertions kept; each has GREEN legitimate-order and
duplicate-effect controls):

- **R1** racing cancel‖cancel: both accepted (200+200); no sequential history matches.
- **R2** confirm-committed-then-cancel: cancelled order keeps `reserved`
  reservations (orphaned inventory), release decision was made on a stale read.
- **R3** `transition` accepts CONFIRMED→PAID validating STALE identity-map
  state after taking the row lock (DID NOT RAISE); the separately labelled
  committed diagnostic (`test_preloaded_transition_committed_overwrite_DIAGNOSTIC`,
  fixture-only, fresh-session read) shows the flushed write DOES persist as
  PAID over the concurrent CANCELLED when committed.
- **R4** pay-committed-then-cancel: cancelled + completed payment +
  settlement ledger; matches no sequential history; no refund path exists.
- **R5** fault injection after the state write (non-domain RuntimeError mid
  fulfillment): the whole request rolls back correctly, but the FULFILLED
  SMS is dispatched INSIDE the transaction that later rolled back — a
  success fact emitted for a request that never happened.
- **R6** first-reference‖packaging-change (de-confounded: order reference is
  the ONLY possible history cause while create is parked before INSERT):
  BOTH the first order reference and the packaging change commit — the
  create path's SKU read holds no `skus` lock and the INSERT is not
  serialized against the shared guard lock (`skus` FOR UPDATE).

## 1. Target architecture

One state-write authority: `OrderService.transition` becomes the ONLY
order-status writer; CRUD action helpers stop writing status and the
endpoints delegate. Staleness is closed inside the service so callers
cannot get it wrong. Everything below is a DECISION LIST, not a mechanical
substitution: the two current entry points differ in state names AND
financial side effects, and each difference is either preserved (with a
guard) or explicitly approved before wiring.

### 1.1 Function-level changes

`backend/services/order_service.py` — `OrderService.transition`:

1. Locked-fresh read: add `.execution_options(populate_existing=True)` to
   the FOR UPDATE select (the codebase's own `lock_sku_row` pattern). The
   matrix check then decides on locked-fresh state. This closes R3.
2. Cancel/void guard (new, in-transition, locked): when target is
   CANCELLED or VOIDED, require `prior_paid == 0` (payments table, sum of
   completed/pending amounts for the order) and raise
   `OrderInvariantViolation` otherwise. Data-driven; it prevents the
   re-wiring from silently OPENING paid/partially_paid cancellation
   (domain matrix currently allows PAID→CANCELLED with non-existent
   "refund logic"). Whether to ever allow paid cancellation is CTO
   decision C below; this guard keeps it closed regardless of matrix.
3. Reservation decision (new, in-transition, locked): for CANCELLED/VOIDED,
   compute `had_active_reservations = EXISTS(reservations reserved WHERE
   order_id = …)` on locked state and expose it on the returned order
   (transient attribute `order._osd1_release_reservation`, set before
   return). Endpoints use this flag instead of the pre-lock
   `status == "confirmed"` read. Closes the decision half of R2 (the
   status half is closed by 1.2).
4. Notification intents (new): `_send_transition_notifications` no longer
   executes sends. It returns a list of intent dicts
   (`{"kind": "email"|"sms", "to": …, "subject": …, "body": …}`) attached
   to the returned order (transient `order._osd1_notification_intents`).
   Nothing is sent before commit. This closes R5's root cause.

`backend/api/v1/orders.py`:

- **confirm** (endpoint `confirm_order`): replace
  `crud_confirm_order(db, order, updated_by=…)` with
  `OrderService(db).transition(order_id, OrderState.CONFIRMED, updated_by=…)`;
  keep `InventoryService.reserve_on_confirm(db, order=order)` in the same
  request transaction, after the transition. Error mapping unchanged
  (domain errors → 409 INVALID_STATE_TRANSITION).
- **cancel** (`cancel_order`) and **client cancel**
  (`api/v1/client/orders.py cancel_order`): replace `crud_cancel_order`
  with `transition(order_id, OrderState.CANCELLED, updated_by=…)`;
  call `release_on_cancel` iff the service-returned flag (1.1.3) is true.
  Client route keeps the dual-key scoped fetch for ownership/404.
- **fulfill / return**: already service-based; they gain R3 protection
  from 1.1.1; keep the explicit `db.expire(order)` in fulfill (redundant
  after populate_existing, harmless) or drop it in the same commit —
  either is fine; keeping it minimizes diff.
- **pay**: unchanged (already canonical; payment_method/target_state
  computation stays).

`backend/crud/order.py`: delete `confirm_order`, `pay_order`,
`fulfill_order`, `cancel_order`, `return_order` and the CRUD
`STATE_TRANSITIONS` dict. Online callers (census): only the two cancel
endpoints and HTTP confirm — all re-wired above; no other production
callers (grep evidence in BEHAVIOR-MATRIX.csv census). `create_order`
(initial DRAFT INSERT, not a transition) and all read helpers stay.

### 1.2 Notification strategy (post-commit, no new framework)

`backend/api/middleware/auth.py` — after `finalize_tenant_context`
SUCCEEDS (commit landed, response status < 400): read
`order._osd1_notification_intents` from the response model where the
endpoint attached them, and `await notification_service.send_*` per intent
inside a `try/except Exception: logger.warning("post_commit_notification_failed", …)`
— failures are logged and never re-raised (no retry, no job queue; the
existing job-queue TODO remains future work and is NOT built in D1).
On rollback (status ≥ 400 or exception) the intents are dropped with the
session — nothing is sent. Endpoints attach the returned order's intents
onto the response (a one-line `response.history`-style side-channel is NOT
needed: the endpoint returns `OrderActionResponse`; attach intents as a
module-level request-state list populated by the endpoint from the service
result).

Semantics: at-most-once, post-commit, best-effort, logged failures.
Rollback suppression is structural (intents live in the transaction's
state). This satisfies CTO §C: customers never receive success facts for
requests that rolled back (R5 class closed).

### 1.3 Draft cancellation compatibility (the matrix contradiction, resolved)

Current facts: crud matrix allows DRAFT→CANCELLED (in production use via
both cancel endpoints); domain matrix allows only DRAFT→VOIDED; VOIDED is
written by no route. After unification exactly ONE matrix must govern.
The CTO decides between:

- **Option A (recommended): extend the domain matrix —
  `STATE_TRANSITION_MATRIX[DRAFT] = {CONFIRMED, CANCELLED, VOIDED}`.**
  Implementable draft: edit `backend/core/domain/order_state.py` matrix
  entry only; the DRAFT→CANCELLED edge keeps today's client-visible
  contract (both cancel surfaces return status "cancelled"); VOIDED stays
  service-only (no route writes it) until a CTO decision wires it. API
  impact: none (no response changes). This is an explicit matrix EDIT and
  requires CTO approval as such — the D0 design's "matrix not touched"
  exclusion is withdrawn because it contradicted retaining
  draft→cancelled.
- **Option B: map HTTP draft-cancel to VOIDED.** Domain matrix untouched;
  both cancel endpoints transition to VOIDED for pre-payment orders.
  API impact: response `status` becomes "voided" for draft cancellations —
  a client-visible change; client status mapping
  (`map_order_status_for_client` already maps voided→CANCELLED) hides it
  from retailer clients but not from wholesaler API consumers.

Recommendation: Option A. It preserves every current externally-observable
value; Option B changes wholesaler-visible status values.

### 1.4 Financial effects on confirm (decision, NOT approved by re-wiring)

- Current HTTP confirm: status + reservation ONLY (no ledger) — proven and
  asserted (group 1 control).
- Current service confirm: posts `post_order_confirmation`
  (receivable/revenue). After the 1.2 re-wiring, confirm goes through the
  service — WITHOUT a decision, every confirm would START posting revenue
  entries. That is a financial-behavior change and is therefore gated:
  the service gains a parameter `post_confirmation_ledger: bool` (read
  from settings, default **False** = preserve current HTTP behavior) and
  the confirm endpoint passes/inherit the default. The CTO chooses (with
  BC evidence) whether/when to flip it to True. The CTO directive also
  distinguishes confirmation-stage credit-reservation semantics from
  delivery-stage receivable semantics — that distinction lives in this
  flag's future semantics, not in this round.
- Ledger on confirm remains NONE until an explicit CTO decision says
  otherwise. This is the D0 design's largest correction.

### 1.5 Paid/partially_paid cancellation

HTTP stays 409 (crud matrix retired; domain matrix still lists
PAID→CANCELLED/PARTIALLY_PAID→CANCELLED). The 1.1.2 `prior_paid == 0`
guard keeps every path closed at the data layer regardless of matrix text.
Opening paid-cancel requires: a refund/settlement design, a BC-02/04
receipt-allocation decision, and an explicit CTO matrix decision. Out of
scope for D1 implementation.

### 1.6 Lock order (actual, including release vs reserve/fulfill)

Drawn from the current call sequences (unchanged by this design):

```
confirm :  orders(FOR UPDATE, in transition)          [proposed]
           → inventory_stocks(FOR UPDATE, sorted sku_code) → INSERT reservations
cancel  :  orders(FOR UPDATE, in transition)          [proposed]
           → inventory_reservations(FOR UPDATE, sorted sku_code,id)
           → inventory_stocks(FOR UPDATE, per reservation)
fulfill :  orders(FOR UPDATE, transition)
           → per item: inventory_stocks(FOR UPDATE)
             → reservations(FOR UPDATE, item-owned) → INSERT movements
return  :  orders(FOR UPDATE, transition) → ledger INSERTs
           → inventory_stocks(FOR UPDATE) → INSERT movements
pay     :  orders(FOR UPDATE, canonical first read)
           → INSERT payments → ledger INSERTs → retailers balance UPDATE
create  :  [today] binding SELECT → skus SELECT (join stocks/prices, NO lock)
           → INSERT orders/order_items → middleware commit
sku-guard: skus(FOR UPDATE, populate_existing) → history SELECTs → price SELECTs
           → (accepted) skus UPDATE
set_price: skus(FOR UPDATE) → retailer_prices write
```

Cycle analysis: order-path lock chains always take `orders` first, then
inventory tables in sorted order, then journals — strictly acyclic. The
SKU path (`skus` → history/price reads) never takes `orders` or inventory
locks while holding `skus`, so no cycle exists between the two families.

GAP (proven RED R6): `create` takes NO `skus` lock between its catalog
read and the order_items INSERT, so it is not serialized against
`sku-guard`/`set_price`. **Proposed closure (product change, CTO-approved
before implementation):** inside the creating transaction, take
`lock_sku_row(db, sku_id=item.sellable_unit_id)` for each item immediately
before building the OrderItem (locking read is the freshness read; the
snapshot fields come from that locked row). Cost: one extra row lock per
item on a low-frequency path. Alternative rejected: doing nothing (leaves
R6 open); doing it in the guard instead (impossible — the guard cannot
know an uncommitted in-flight create).

### 1.7 What deliberately does NOT change

`CanonicalPaymentService` (payments stay canonical; no new refund or cash
event paths), `core/domain/order_state.py` EXCEPT the single CTO-approved
Option A line, SKU/SMTP implementations, shared fixtures, governance
tooling, `protocol-deltas.json`. No second SKU guard is created; the
create-path lock reuses `lock_sku_row` exactly as set_price/update do.

## 2. Estimated file scope of the implementing round

| File | Change |
|---|---|
| `backend/services/order_service.py` | populate_existing; cancel/void paid-guard + reservation flag; notification intents (no sends) |
| `backend/api/v1/orders.py` | confirm/cancel delegate to service; reservation flag + intent plumbing; drop stale pre-write flag |
| `backend/api/v1/client/orders.py` | cancel delegates to service (dual-key fetch stays) |
| `backend/crud/order.py` | remove 5 status-writing helpers + CRUD matrix |
| `backend/api/middleware/auth.py` | post-commit notification dispatch (try/except logged) |
| `backend/core/domain/order_state.py` | Option A single-line matrix edit (ONLY with CTO approval) |
| `backend/api/v1/orders.py` (create) | per-item `lock_sku_row` before OrderItem build (R6 closure) |
| existing suites pinning CRUD actions | follow-ups only where they call removed helpers |

## 3. Adjudication items for the CTO (decisions, not implementations)

| # | Decision | Current behavior | Approved-contract status | Recommendation |
|---|---|---|---|---|
| A | Ledger on confirm | HTTP: none; service path: receivable/revenue | BC-01/02/04 originals not on disk; baseline v0.60 SHA known (`a20e13…8664`), original NOT on this host — nothing inferred | Default False (preserve HTTP); flip only with BC-backed CTO decision |
| B | Draft-cancel compatibility | DRAFT→CANCELLED in production; domain matrix says VOIDED only | same evidence gap | Option A (matrix gains CANCELLED edge); Option B documented |
| C | Paid/partially_paid cancel | 409 everywhere; data guard proposed | same evidence gap; no refund design exists | Keep closed via 1.1.2 guard; revisit with refund design |
| D | Notification timing | pre-commit fire-and-forget (RED R5) | CTO directive: no success facts pre-commit | Post-commit best-effort dispatch (1.2) |
| E | VOIDED reachability | unreachable from any route | domain matrix defines it | Keep service-only until a route is mandated |

## 4. Verification plan for the implementing round

1. The six named REDs must turn GREEN with assertions intact (they are the
   acceptance tests); all controls stay GREEN; the committed diagnostic
   flips with its explicit update note.
2. Focused suites that pin current behavior run unchanged or updated only
   where they call removed CRUD helpers.
3. Governance accounting for the re-wired product paths is part of the
   implementing round's protocol delta — not self-served here.
