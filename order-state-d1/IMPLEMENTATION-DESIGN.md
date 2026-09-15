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

OBSERVED RUN RESULT (evidence/2026-09-15T1240Z-r1-full-directory-run1.txt):
33 tests — 27 passed, 6 failed, pytest rc=1. Of the six failures, FIVE are
accepted product findings (R1–R5 below, each with GREEN legitimate-order
and duplicate-effect controls); the SIXTH (R6) is classified
TEST_ORACLE_AND_TRANSACTION_FIDELITY_GAP — a test-fidelity failure whose
product-defect status is UNPROVEN (supervisor F1; see §0 R6 and
D1-R1-SUPERVISOR-CORRECTION.md):

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
- **R5** fault injection after the state write (non-domain RuntimeError raised
  at the inventory-deduction ENTRY — i.e. after the FULFILLED transition and
  its flush, BEFORE any real stock deduction or reservation consumption):
  the whole request rolls back correctly, but the FULFILLED SMS is
  dispatched INSIDE the transaction that later rolled back — a success fact
  emitted for a request that never happened. Scope note (supervisor F4):
  this proves the post-state-write stage only; rollback of a fault landing
  mid-way through PARTIAL per-item inventory writes is NOT covered by this
  test and is not claimed.
- **R6 — CLASSIFIED TEST_ORACLE_AND_TRANSACTION_FIDELITY_GAP, product defect
  UNPROVEN (supervisor F1).** The failed race test closes its guard-verdict
  session (releasing the SKU lock) and then performs the packaging WRITE in
  a separate session WITHOUT re-running the history guard in that
  transaction, so it does not reproduce the real single
  lock/check/write guard transaction; its mutual-exclusion assertion also
  rejects an admissible sequential history (change the unused SKU, then
  create an order from the new values). The failure is retained verbatim
  as a test-oracle gap. The underlying create-path risk (SKU catalog read
  holds no `skus` lock before the order_items INSERT) remains
  source-confirmed; a product R6 claim requires a future proof that keeps
  ONE lock/check/write transaction, compares only admissible sequential
  outcomes against actual committed facts (including package_quantity and
  snapshot equality), and lets a correctly locking implementation
  complete. Future implementation-round work; NOT a D1 design-review
  prerequisite and NOT counted among the accepted product findings.

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
2. Cancel/void state policy (new, in-transition, locked): when target is
   CANCELLED or VOIDED, REJECT the transition explicitly when the
   locked-fresh status is PAID or PARTIALLY_PAID (raise
   `OrderInvariantViolation`). This is the mechanism that preserves
   today's HTTP 409 behavior: status, not a payment sum, is the policy —
   a row CAN carry PAID/PARTIALLY_PAID with a zero qualifying payment sum
   (legacy/inconsistent rows), so a payment-sum gate alone would OPEN
   cancellation for such rows (supervisor F3). Additionally, and only as
   a defense-in-depth INVARIANT whose exact pending/completed semantics
   await BC evidence: a paid-amount check may reject early — it must
   never be the sole gate, must not create a second accounting definition,
   and stays OFF until its semantics are approved. This keeps the
   re-wiring from silently OPENING the domain matrix's PAID→CANCELLED /
   PARTIALLY_PAID→CANCELLED edges (whose "refund logic" does not exist).
   Whether to ever allow paid cancellation is CTO decision C below.
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

Channel (supervisor F2 — one request-private channel, no module/global
mutable list, no public response leakage):

- `OrderService.transition` attaches intent dicts
  (`{"kind": "email"|"sms", "to": …, "subject": …, "body": …}`) to the
  returned order as transient attribute `order._osd1_notification_intents`
  and never sends anything itself. This covers transitions reached
  INDIRECTLY through `CanonicalPaymentService` (pay/declare): the payment
  service returns the same transitioned order object, so the intents ride
  on it unchanged — no separate propagation path exists or is needed.
- Each order endpoint copies `order._osd1_notification_intents` into
  `request.state.osd1_notification_intents` (Starlette request state —
  per-request, dies with the request) immediately after the service call.
  This service → route → middleware propagation is the ONLY channel.
- `backend/api/middleware/auth.py`: after `finalize_tenant_context`
  SUCCEEDS (commit landed, response status < 400), pop
  `request.state.osd1_notification_intents` and dispatch each intent via
  `notification_service.send_*` inside
  `try/except Exception: logger.warning("post_commit_notification_failed", …)`;
  after dispatch, `request.state.osd1_notification_intents = None`
  (release references). On commit failure / rollback (status ≥ 400 or
  exception) the middleware discards the list with the request — nothing
  is sent. No retry, no job queue (the existing job-queue TODO remains
  future work and is NOT built in D1).

Semantics: per-request best-effort, post-commit; send failures are logged
and otherwise dropped; NO global exactly-once guarantee is claimed
(at-most-once per request; duplicate delivery across process crashes is
out of scope). Rollback suppression is structural (intents never survive
the request that failed). This satisfies CTO §C: customers never receive
success facts for requests that rolled back (R5 class closed).

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
- Effect on EXISTING direct service callers (supervisor F3), not just
  HTTP: today's production callers of `transition` are the pay path (via
  `CanonicalPaymentService`, targets PAID/PARTIALLY_PAID only — never
  CONFIRMED), fulfill and return (targets FULFILLED/RETURNED). NONE of
  them reaches a CONFIRMED transition, so the default-False gate changes
  no existing behavior; the gate only matters for the newly re-wired
  confirm endpoint and any FUTURE caller. This is a proposal, pending CTO
  approval — not an approved rule.
- Ledger on confirm remains NONE until an explicit CTO decision says
  otherwise. This is the D0 design's largest correction.

### 1.5 Paid/partially_paid cancellation

HTTP stays 409. Preserving that after unification requires the 1.1.2
EXPLICIT LOCKED-STATE REJECTION of CANCELLED/VOIDED from
PAID/PARTIALLY_PAID — status is the policy. Any paid-amount sum is at most
an ADDITIONAL invariant whose pending/completed semantics await BC
evidence; it must not be relied on as the state policy (zero-sum paid rows
exist) and must not introduce a second accounting definition. Opening
paid-cancel requires: a refund/settlement design, a BC-02/04
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

Cycle analysis — LIMITED, not a global proof (supervisor F4): within one
order's path the lock chains take `orders` first, then inventory tables,
then journals; the SKU family (`skus` → history/price reads) takes no
`orders` or inventory locks while holding `skus`, so no cycle is visible
between those two families. NOT proven: the complete cross-order/SKU
graph. Known unresolved aspect: confirm takes stock-then-reservation
while cancel/fulfill touch reservation-then-stock (fulfill) on the SAME
tables in inverse order across different orders — today these serialize
on the orders row and the state matrix makes conflicting same-order pairs
illegal, but a formal cross-order acyclicity argument (e.g. two orders
sharing one SKU where one fulfills while another cancels) has NOT been
made. Listed as an open item for the implementing round to argue or
enforce (e.g. a single fixed table order), not asserted away.

GAP (source-confirmed risk; product defect UNPROVEN — see R6
classification in §0 and D1-R1-SUPERVISOR-CORRECTION.md): `create` takes
NO `skus` lock between its catalog read and the order_items INSERT, so it
is not serialized against `sku-guard`/`set_price`. **Proposed closure
(product change, CTO-approved before implementation):** inside the
creating transaction, for EVERY item take `lock_sku_row(db,
sku_id=item.sellable_unit_id)` with identifiers DEDUPLICATED and acquired
in ONE FIXED GLOBAL ORDER (sorted by sku_id), BEFORE any snapshot/pricing
validation — for BOTH the client and wholesaler create paths (locking
read is the freshness read; the snapshot fields come from that locked
row). Cost: one extra row lock per distinct SKU on a low-frequency path.
Alternative rejected: doing nothing (leaves the risk open); doing it in
the guard instead (impossible — the guard cannot know an uncommitted
in-flight create).

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
| `backend/api/v1/orders.py` + `backend/api/v1/client/orders.py` (create) | deduplicated SKU ids locked via `lock_sku_row` in one fixed global order (sorted sku_id) BEFORE snapshot/pricing validation, both create paths (proposed closure for the unlocked-read risk) |
| existing suites pinning CRUD actions | follow-ups only where they call removed helpers |

## 3. Adjudication items for the CTO (decisions, not implementations)

| # | Decision | Current behavior | Approved-contract status | Recommendation |
|---|---|---|---|---|
| A | Ledger on confirm | HTTP: none; service path: receivable/revenue | BC-01/02/04 originals not on disk; baseline v0.60 SHA known (`a20e13…8664`), original NOT on this host — nothing inferred | Default False (preserve HTTP); flip only with BC-backed CTO decision |
| B | Draft-cancel compatibility | DRAFT→CANCELLED in production; domain matrix says VOIDED only | same evidence gap | Option A (matrix gains CANCELLED edge); Option B documented |
| C | Paid/partially_paid cancel | 409 everywhere; explicit locked-state rejection proposed (payment sum = optional additional invariant, semantics pending) | same evidence gap; no refund design exists | Keep closed via the 1.1.2 status-based rejection; revisit with refund design |
| D | Notification timing | pre-commit fire-and-forget (RED R5) | CTO directive: no success facts pre-commit | Post-commit best-effort dispatch (1.2) |
| E | VOIDED reachability | unreachable from any route | domain matrix defines it | Keep service-only until a route is mandated |

## 4. Verification plan for the implementing round

1. The five accepted product findings (R1–R5) must turn GREEN with
   assertions intact; all controls stay GREEN; the committed diagnostic
   flips with its explicit update note. R6 and partial-inventory-fault
   rollback coverage are FUTURE implementation-round work (requiring the
   corrected oracle: one lock/check/write transaction, admissible-sequential
   outcome comparison against committed facts) and are NOT prerequisites to
   this D1 design review.
2. Focused suites that pin current behavior run unchanged or updated only
   where they call removed CRUD helpers.
3. Governance accounting for the re-wired product paths is part of the
   implementing round's protocol delta — not self-served here.
