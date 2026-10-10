# Using S1 pricing and order consent

1. Open **Base and Customer Pricing**, choose an active bound customer, and
   complete the positive base price for each sellable unit. Add a customer
   override only when needed. Retire/restore reuses that customer's record.
   A version conflict means refresh before editing again.
2. The customer catalog shows their effective price and registered currency.
   UGX accepts integers; KES accepts up to two fractional digits. Missing base
   is preparation data, not a free item. Configure it before selling.
3. Select products and quantities, then click **Review server quote**. Check
   units/package, currency and server total. Click **Accept these prices and
   create draft** separately. A stale-price message requires a new explicit
   acceptance; it has not already created an order.
4. If the result is unknown, click **Retry same accepted submission**. Do not
   change the order or create a second one. The original key and intent are
   retained until the request has a definite result.
5. An old or changed-price draft may require **cancel old draft and create new
   draft**. Re-select verified items and review the explicit replacement
   warning before acceptance. The old amounts remain in history. A client
   without proven ownership/source must ask an authorized merchant.
6. Correct a display label without changing the underlying unit. Repackaging
   a used SKU requires a new SKU; names such as Box/box are not interchangeable
   identities or automatic conversions.
7. Print/history views use the order snapshot. `LEGACY_CURRENCY_UNVERIFIED`
   means historical currency has not been established. It is not KES, UGX or
   a permission to recompute old money. Mixed/unknown finance displays do not
   establish a safe currency aggregation.

This guide does not authorize deployment, establish S2/S3 workflows, provide
refund/FX behavior, or declare historical currency backfill complete.
