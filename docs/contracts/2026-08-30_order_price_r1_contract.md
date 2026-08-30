# DC-12R1-MVP-L1 ORDER-PRICE-R1 Contract

Status: `BLOCKED_BY_ORDER_LIFECYCLE_R0_CREDIT_POLICY_AND_PRICING_R1`

Baseline: `24a28d76d6d9483d8101f8e0f537c148dc262859`

## 1. Customer journey

After a retailer submits an order, the wholesaler can:

1. accept it unchanged;
2. reject it; or
3. publish one price and/or quantity adjustment.

After an adjustment, the retailer sees original and proposed values line by
line and has two choices only:

- accept by choosing cash payment or credit purchase; or
- reject and cancel the order.

There is no second wholesaler revision, counter-offer, chat negotiation, or
silent catalog-price mutation in MVP.

## 2. Revision persistence

One immutable revision header per order:

```text
order_id
revision_number = 1
status = AWAITING | ACCEPTED | REJECTED | EXPIRED
published_by
published_at
expires_at = published_at + 24 hours
decision_by / decision_at
idempotency keys
```

Each affected line records:

```text
order_item_id
submitted_quantity / submitted_unit_price
proposed_quantity / proposed_unit_price
currency_code
reason_code
reason_text
```

Unchanged lines remain explicit in the response so totals reconcile. The
submitted snapshots are immutable. Acceptance materializes separate final
snapshots; it does not overwrite the submitted values.

## 3. Wholesaler commands

- Accept unchanged: requires `orders:update`, locks order, resolves current
  stock, reserves it, and confirms. No retailer reconfirmation is needed.
- Publish adjustment: requires `orders:update`, an expected order version,
  positive prices/quantities, at least one actual line change, a reason for
  every changed line, and successful reservation of proposed quantities.
- Reject: requires `orders:update`, a reason, no completed decision, and
  idempotent reservation release.

Publishing the adjustment does not change `CatalogOffer.base_price` or a
retailer override. The response must say this explicitly.

## 4. Retailer commands

One version-bound endpoint accepts:

```text
decision = ACCEPT | REJECT
settlement_choice = CASH | CREDIT (required only for ACCEPT)
expected_revision = 1
idempotency_key
```

- Identity comes only from the authenticated retailer binding.
- A rejected decision produces derived workflow status
  `CANCELLED_RETAILER_REJECTED` and releases order-owned reservation.
- Cash acceptance produces `PAYMENT_PENDING`. It may create one pending cash
  declaration for the full accepted total, with zero accounting effect until
  wholesaler confirmation. Clicking accept must never claim payment received.
- Credit acceptance performs the credit policy check and receivable mutation
  in the same transaction. Success exposes `CONFIRMED_ON_CREDIT`; internally
  it remains distinguishable from cash-settled `PAID`.
- Insufficient limit, blocked credit, or overdue exposure leaves the order in
  `AWAITING_RETAILER_CONFIRMATION` and performs zero financial writes.

## 5. Credit prerequisite

The current binding stores only `outstanding_balance`. Before implementation,
the CTO must accept exact sources for:

- `credit_enabled`;
- `credit_limit`;
- available credit calculation under lock;
- overdue exposure and blocking policy;
- credit authorization audit and idempotent release.

Without these fields, the promised credit choice must remain unavailable. A
hard-coded unlimited credit path is forbidden.

## 6. Expiration contract

- `expires_at` is stored by the server when the adjustment is published.
- Any decision at or after the deadline first atomically expires the revision,
  voids the pending order with reason
  `PRICE_CONFIRMATION_EXPIRED`, releases reservations, and rejects the late
  action.
- A durable periodic sweep materializes expired rows after restarts.
- Worker delay does not extend retailer authority; the action endpoint always
  checks the database deadline itself.
- Multiple workers or retries result in one terminal transition and one release.

## 7. Failure and leakage contract

- Raw database, tenant, permission, stock, credit, and internal reason details
  are not exposed to the opposite party.
- Stale version, repeated action, expired action, and invalid state are
  structured conflicts with zero partial writes.
- Logs contain IDs and fixed categories, never payment credentials, tokens, or
  complete request bodies.
- Cross-tenant order IDs produce no mutation and no existence leak.

## 8. Required merge evidence

- Real PG concurrency tests for two wholesaler publishes, accept-vs-expire,
  accept-vs-reject, stock reservation, and credit-limit races.
- Mutation gates for a second revision, deadline bypass, client-supplied price,
  catalog mutation, credit-without-limit, and duplicate reservation release.
- Browser journeys for unchanged acceptance, adjusted cash acceptance,
  adjusted credit acceptance, rejection, insufficient credit, and timeout.
- Full reconciliation of order, revision, inventory, receivable, declaration,
  ledger, and audit rows after every terminal path.
