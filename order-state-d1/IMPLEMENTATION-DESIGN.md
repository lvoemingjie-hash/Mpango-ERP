# IMPLEMENTATION-DESIGN — MPANGO-ORDER-STATE-AUTHORITY-D1

Author evidence by ZCode (executor) for Codex-L review. Claim ceiling:
`AUTHOR_ORDER_STATE_D1_READY_FOR_CODEXL_REVIEW_ONLY`. Nothing here is
self-authorized for product implementation; every product change listed
below requires CTO approval of this design first.

BASE: `1ee75d9faaa00cdcadfe9f46d1e0ac960efc632e` (tree
`5712eb85e6bf76d8662a6bb7890e609d09bd7ec0`). Behavior evidence:
`order-state-d1/BEHAVIOR-MATRIX.csv` (14 entries) and the six matrix
groups under `backend/tests/order_state_d1/` (26 tests; 22 GREEN, 4 honest
product REDs with GREEN controls).

---

## 0. Problem statement (what the evidence establishes)

Order state is written by two divergent machines plus one locked service:

| Writer | Matrix | Lock | Fresh after lock | Ledger | Inventory |
|---|---|---|---|---|---|
| `crud/order.py` (HTTP confirm/cancel, both client+wholesaler cancel) | 6-state CRUD | none | n/a (no lock) | none | reserve/release at endpoint |
| `OrderService.transition` (HTTP fulfill/return; pay via canonical) | 8-state domain | orders FOR UPDATE | **NO** (no `populate_existing`; identity map keeps stale attrs) | confirm/pay/return entries | at endpoint |
| `CanonicalPaymentService.confirm_payment` (HTTP pay, declare) | computed target (PAID/PARTIALLY_PAID/credit-collection) | orders FOR UPDATE (first read is the locking read) | yes (locked read is first read) | per transition + credit deltas | none |

Four demonstrated defects (all reproduced deterministically, controls
GREEN — see `order-state-d1/evidence/`):

- **D1 (RED: cancel||cancel)** both concurrent cancels succeed (200+200);
  no sequential history produces two successes.
- **D2 (RED: confirm||cancel)** cancel, validated on a pre-loaded DRAFT
  object, overwrites a committed CONFIRMED and leaves its committed
  reservations `reserved` forever (orphaned inventory).
- **D3 (RED: stale-after-lock)** `OrderService.transition` validates the
  stale identity-map status after taking the row lock and overwrites a
  committed concurrent CANCELLED with PAID.
- **D4 (RED: pay||cancel)** cancel, validated on a pre-loaded CONFIRMED
  object, overwrites a committed PAID: final state cancelled + completed
  payment + settlement ledger, no refund path, matches no sequential
  history.

Root cause common to all four: **state decisions are made on unlocked or
stale reads; the only locked writer does not refresh the ORM object after
locking.** The fix family is therefore mechanical, not semantic: decide
*after* locking, on locked-fresh data, inside one transaction owner.

## 1. Target architecture (proposed)

One state-write authority: `OrderService.transition` becomes the ONLY
order-status writer; the CRUD action helpers stop writing status and the
endpoints delegate to the service. Identity-map staleness is closed inside
the service itself so callers cannot get it wrong.

### 1.1 `OrderService.transition` hardening (function-level)

`backend/services/order_service.py`:

1. **Locked-fresh read.** Change the locking select to
   `.execution_options(populate_existing=True)` (mirrors
   `services/package_identity.py:lock_sku_row`). The FOR UPDATE statement
   then repopulates the identity-map object; matrix validation and
   invariants decide on locked-fresh state. This alone closes D3 and is
   the exact pattern the fulfill endpoint already applies manually via
   `db.expire(order)` (api/v1/orders.py:952) — after this change that
   manual `expire` becomes redundant-but-harmless (keep it this round;
   removing it is cosmetic).
2. **Lock order.** orders row lock FIRST (already the case), then
   inventory stock locks in the caller, then reservations — the existing
   sorted-by-`sku_code` discipline in `InventoryService` is kept. No
   change to inventory internals.

### 1.2 Endpoint re-wiring (call-level)

`backend/api/v1/orders.py`:

- **confirm** (line ~639): replace `crud_confirm_order(db, order, ...)` with
  `OrderService(db).transition(order_id, CONFIRMED)`; keep
  `InventoryService.reserve_on_confirm` in the same request transaction.
  The preflight `get_order_by_id` stays for the 404 only.
- **cancel** (line ~1039) and `client cancel`
  (`api/v1/client/orders.py:437`): replace `crud_cancel_order` with
  `OrderService(db).transition(order_id, CANCELLED)`; the
  `release_reservation = status == "confirmed"` flag is computed INSIDE
  the service after the lock (see 1.3) instead of on the stale preflight
  object; `release_on_cancel` stays at the endpoint, keyed off the value
  the service returns/records.
- **pay**: unchanged — already locked-fresh via
  `_get_order_by_id_for_update` + canonical service.
- **fulfill/return**: unchanged in structure (already service-based);
  they gain D3 protection from 1.1.

`backend/crud/order.py`: `confirm_order/pay_order/fulfill_order/
cancel_order/return_order` lose their status writes (either deleted or
reduced to validation-only helpers — deletion preferred; the CRUD
`STATE_TRANSITIONS` dict dies with them). `create_order` (initial DRAFT)
stays: initial creation is not a transition.

### 1.3 Cancel-with-release decision (new, small)

Move the decision into `transition`: when target is CANCELLED (or VOIDED),
after the locked-fresh read, determine `had_active_reservations =
exists(reservations reserved for order)` and expose it on the returned
order (e.g. a transient attribute or a small result object). Endpoints
call `release_on_cancel` iff that flag is true — computed on locked state,
not on the preflight snapshot. This closes D2's release half; the status
half is closed by 1.2.

### 1.4 Transaction ownership & exception propagation (unchanged contract)

- The tenant-context middleware stays the single committer
  (`finalize_tenant_context`, api/middleware/auth.py:97). No endpoint
  gains its own commit.
- Service raises `InvalidStateTransitionError`/`OrderInvariantViolation` →
  endpoints map to 409 `INVALID_STATE_TRANSITION` exactly as today
  (fulfill/return already do; confirm/cancel adopt the same mapping —
  the CRUD-flavored message with allowed-statuses text is retired).
- Notifications stay fire-and-forget after refresh inside the request
  transaction (failure semantics unchanged: logged, never raised).

## 2. Estimated file scope

Product (all behind CTO approval of this design):

| File | Change |
|---|---|
| `backend/services/order_service.py` | populate_existing on lock; cancel/void reservation-flag decision; (optional) accept reason metadata |
| `backend/api/v1/orders.py` | confirm/cancel delegate to service; error mapping; drop stale pre-write release flag |
| `backend/api/v1/client/orders.py` | cancel delegates to service (dual-key fetch stays for the 404/ownership) |
| `backend/crud/order.py` | remove 5 status-writing action helpers + CRUD matrix; keep create/reads |
| `backend/tests/...` (existing suites touching crud actions) | follow-ups where they monkeypatch/call the removed helpers |

NOT touched: `CanonicalPaymentService` (payments stay canonical — no new
refund/cash-event paths), `core/domain/order_state.py` matrix, SKU/SMTP
implementations, shared fixtures, governance runner, status enum, ledger
service internals.

## 3. Adjudication items (separated deliberately)

These are decisions, not implementations. Each states current behavior,
the approved-contract status, and a recommendation; the CTO decides.

### A. Should confirmation post ledger entries?

- **Current:** HTTP confirm posts NONE (asserted GREEN in group 1); the
  service path posts `post_order_confirmation` (receivable/revenue) — but
  no HTTP route reaches it for confirm today; pay/fulfill/return do run
  through the service, so a service-routed confirm WILL start posting
  confirmation ledger for every confirmed order.
- **Approved contract:** BC-01/02/04 approved texts were NOT found on disk
  (marked 待取证); business baseline v0.60 SHA not verifiable without the
  CTO-given SHA. No guessed semantics applied.
- **Recommendation:** treat posting-on-confirm as the majority behavior of
  the codebase's own service layer (S5-B design) — but require an explicit
  CTO decision because it changes reported revenue timing for every order.
  If approved, the four group-1/6 assertions documenting "no ledger on
  confirm" flip to asserting presence (test change listed in scope).

### B. DRAFT-cancel compatibility

- **Current:** HTTP cancel allows DRAFT→CANCELLED (crud matrix); domain
  matrix allows only DRAFT→VOIDED, and VOIDED is unreachable from any HTTP
  route (nothing ever writes it).
- **Recommendation:** keep DRAFT→CANCELLED reachable (both matrices stay
  in use in production data expectations) and add DRAFT→VOIDED as an
  explicit service-only capability for the clean pre-payment cancellation
  the domain matrix describes. Requires CTO confirmation of the intended
  client-visible contract before wiring any route to VOIDED.

### C. Paid/partially-paid cancel boundary

- **Current:** domain matrix allows PAID→CANCELLED ("with refund logic" —
  which does not exist anywhere) and PARTIALLY_PAID→CANCELLED; HTTP forbids
  both (409, asserted GREEN).
- **Recommendation:** keep the HTTP boundary as-is (409) until a refund
  design exists; alternatively tighten the domain matrix to forbid both
  until then. Do NOT silently enable paid-cancel via the service re-wiring:
  `transition(CANCELLED)` from paid would otherwise become reachable
  through any future caller. Guard: the service checks, before
  CANCELLED/VOIDED, `prior_paid == 0` (payments table) and raises
  `OrderInvariantViolation` otherwise — a data-driven guard, not a matrix
  edit, leaving the matrix decision with the CTO.

### D. Post-commit notifications and failure semantics

- **Current:** fire-and-forget inside the request transaction; failures
  logged, swallowed. With 1.2 the confirm email would be sent by the
  service path (CONFIRMED target) — i.e., confirm starts emailing.
- **Recommendation:** acceptable for MVP (stub transport); if the CTO
  wants post-commit semantics, move dispatch after middleware commit via
  the existing job-queue TODO — out of scope for D1.

## 4. Verification plan for the implementing round

1. The four RED tests in `backend/tests/order_state_d1/` must turn GREEN
   with no assertion weakening (they are the acceptance tests; controls
   must stay GREEN too).
2. Existing suites that pin current CRUD behavior
   (`test_orders_api.py` mock family, `test_s5_order_state_machine.py`,
   `test_phase5_order_payment.py`, sku/BC-06 real-PG suites) run
   unchanged-or-updated only where they monkeypatch removed helpers.
3. Governance accounting: `backend/` is a governed prefix; the
   implementing round must carry its own protocol-delta/semantic record
   authorization (this task deliberately did NOT self-serve it).

## 5. Explicitly out of scope (per task contract)

No new refunds, cash events, second SKU guard, repricing, snapshot
rewrites, legacy-identity rewrites, matrix edits, or migration of historical
statuses. Payments remain exclusively on `CanonicalPaymentService`.
