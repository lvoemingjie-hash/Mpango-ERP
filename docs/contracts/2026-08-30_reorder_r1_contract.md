# DC-12R1-MVP-L1 REORDER-R1 Contract

Status: `BLOCKED_BY_STABLE_LINE_IDENTITY_PRICING_R1_AND_ORDER_PRICE_R1`

Baseline: `24a28d76d6d9483d8101f8e0f537c148dc262859`

## 1. Customer outcome

Order history shows a `Reorder` action. It saves data entry by carrying the
supplier, sellable units, packaging, and quantities into a new review flow.
It never guarantees or silently copies historical prices.

The retailer sees, before creating the new order:

- previous unit price;
- current effective unit price;
- amount and percentage difference;
- current availability;
- packaging or catalog changes;
- every unresolved legacy line.

## 2. Two-step server-authoritative flow

### 2.1 Preview

`POST /api/v1/client/orders/{source_order_id}/reorder-preview`

The server reads only an order owned by the authenticated retailer binding,
loads every historical line, resolves current stable identity and active offer,
and runs the canonical pricing resolver. The response includes all lines in
source order; none may be silently dropped.

Line outcomes:

- `READY`
- `PRICE_CHANGED`
- `UNAVAILABLE`
- `PACKAGING_CHANGED`
- `INSUFFICIENT_STOCK`
- `LEGACY_IDENTITY_UNRESOLVED`

The preview returns an opaque version bound to source order, line identities,
current offer versions, prices, and expiry. It is not an order and reserves no
stock.

### 2.2 Create draft

`POST /api/v1/client/orders/{source_order_id}/reorder`

Input contains only preview version, chosen quantities/lines, explicit
acknowledgements for changed lines, and an idempotency key. It contains no
price, subtotal, total, source retailer, or tenant.

The server re-resolves price and offer versions in one transaction. Drift from
the preview returns `409 REORDER_PREVIEW_STALE` plus a fresh comparison; no
draft is created. A successful call creates one new `DRAFT` order linked by
`source_order_id` and writes new immutable submitted snapshots.

## 3. Legacy and unavailable lines

- New order lines use stable sellable-unit identity.
- Legacy lines with no stable identity are never matched by code or name.
- `LEGACY_IDENTITY_UNRESOLVED` remains visible and requires manual product
  selection.
- Inactive, deleted, or inaccessible offers are `UNAVAILABLE`.
- The UI cannot create a draft while unresolved lines remain selected.
- Removing or replacing a line is an explicit retailer action recorded in the
  preview request; it is not silent server behavior.

## 4. Price and order semantics

- Previous price is display-only historical evidence.
- Current price always follows `RETAILER_OVERRIDE > BASE_PRICE` at execution.
- If both are absent, the line is unavailable.
- A new draft has its own identity, timestamps, snapshots, and future workflow.
- Reordering never mutates, reopens, or appends to the source order.
- Promotions, historical price guarantees, automatic supplier substitution,
  and cross-supplier carts are out of scope.

## 5. UX contract

- The action is available from eligible order list and detail views.
- One click opens a prefilled review page; it does not place an order without
  review.
- Price increases and decreases are equally visible; unchanged prices are
  labelled.
- Unavailable or changed lines remain in their original position with a clear
  remediation action.
- The final confirmation states that current prices apply.
- At 390px, all previous/current/delta information is readable without
  horizontal page overflow.

## 6. Security, idempotency, and evidence

- Read requires `client:orders:read`; create requires
  `client:orders:create`.
- Cross-retailer or cross-wholesaler source IDs reveal no order details.
- One idempotency key creates at most one draft; mismatched replay is a conflict.
- Source and draft remain tenant-isolated under concurrent catalog changes.
- Required tests cover price up/down/same, missing price, packaging change,
  inactive item, stock shortage, stale preview, legacy line, partial selection,
  double click, and cross-tenant denial.

## 7. Entry gate

Implementation starts only after:

1. stable sellable-unit identity is merged;
2. the effective-price resolver is the single authority;
3. order submitted/final snapshots are frozen;
4. `source_order_id` lineage and idempotency are approved;
5. `ORDER-PRICE-R1` lifecycle semantics are accepted.
