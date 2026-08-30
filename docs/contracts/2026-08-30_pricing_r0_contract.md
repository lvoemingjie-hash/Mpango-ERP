# DC-12R1-MVP-L1 PRICING-R0 Contract

Status: `READ_ONLY_CONTRACT_READY_FOR_CTO_DECISION`

Baseline: `24a28d76d6d9483d8101f8e0f537c148dc262859`

## 1. Customer outcome

A wholesaler sets one normal selling price for a sellable offer and may set a
different price for a specific retailer. Retailers always see the exact price
that the server will use when they submit an order.

The phrase "SKU base price" is normalized to `CatalogOffer.base_price`. Price
belongs to the commercial offer layer, not the product identity or physical
packaging layer. This aligns with the proposed
`CatalogProduct -> SellableUnit -> CatalogOffer` architecture without claiming
that those models already exist in the baseline.

## 2. Current source truth

- `backend/models/retailer_price.py` stores only retailer-specific
  `(retailer_id, sku_id) -> price` rows.
- Migration `017_retailer_prices.py:160` has no base-price or currency field.
- `backend/repositories/pricing_repository.py:18` returns only an exact
  retailer+SKU price and has no fallback.
- `backend/api/v1/client/products.py` treats a missing special row as no price
  and not orderable.
- Client and wholesaler order creation independently repeat the price lookup.
- `frontend/src/pages/pricing/RetailerPricingPage.tsx` is a special-price-only
  UI and hard-codes KES.

Therefore the desired precedence is not present. This contract does not call
the existing table a base-price implementation.

## 3. Frozen price resolution rule

For a tenant, authenticated retailer binding, active catalog offer, and server
time:

1. Use one active retailer override for the exact retailer and offer.
2. Otherwise use the active offer base price.
3. If neither exists, the line is `NOT_ORDERABLE_MISSING_PRICE`.

Resolution returns:

```text
offer_id
sellable_unit_id
amount
currency_code
source = RETAILER_OVERRIDE | BASE_PRICE
source_record_id
price_version
resolved_at
```

MVP currency is `KES`; multi-currency conversion is out of scope. Currency is
still explicit in response and order snapshots so historical documents never
depend on a future tenant-default change.

`FINANCE_LOCALIZATION_R0` remains an audit-only, non-blocking follow-up. This
contract does not add a country selector or claim Kenya/Uganda currency
automation.

The server is the only price authority. Create/reorder requests never accept
unit price, subtotal, total, source, or currency from the client.

## 4. Base and override semantics

- Base price is optional while catalog data is being prepared. An active offer
  without a base or override is visible as unavailable for ordering.
- Override price must be positive and finite.
- At most one active override exists for `(tenant, retailer, offer)`.
- Deleting an override means "return to base-price fallback"; it does not
  delete or change the base price.
- Editing an order price never edits base or override data.
- Saving an order adjustment as a future customer override is a separate,
  explicit action requiring `pricing:write`; it is not in MVP
  `ORDER-PRICE-R1`.
- Promotions, coupons, date ranges, quantity tiers, tax-inclusive pricing,
  exchange rates, and multi-round negotiation are out of scope.

## 5. Historical truth

Every submitted order line freezes at least:

- stable sellable-unit identity for new rows;
- optional offer/provenance identity;
- product, packaging, unit, and code display snapshots;
- submitted quantity;
- submitted unit price, currency, and price source;
- submitted subtotal.

Catalog price edits never rewrite existing orders. Legacy order rows keep null
stable IDs plus a legacy marker; a migration must not infer IDs from codes.

## 6. One resolver, all consumers

The implementation must create one tenant-scoped effective-price service used
by:

- retailer catalog list/detail;
- wholesaler order creation;
- retailer order creation;
- reorder preview and draft creation;
- future price provenance displays.

Duplicated route-level price SQL is forbidden after migration. A mutation that
restores special-only lookup in any consumer must turn the contract tests RED.

## 7. Decision and implementation gates

`PRICING-R0` may be accepted as a contract now. `PRICING-R1` may not start until:

1. the sellable-offer identity from SKU work is accepted;
2. the legacy `retailer_prices.sku_id` mapping is deterministic or explicitly
   quarantined;
3. the shared order-line snapshot contract is accepted;
4. `KES` as the MVP currency is confirmed without claiming multi-currency.
