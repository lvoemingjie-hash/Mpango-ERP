# S1 pricing, consent and draft contract

Authorization: CTO-AUTH-MPANGO-S1-PRICING-QUOTE-CREATE-IMPLEMENTATION-R1-20261010.
This is an implementation contract, not a release or independent acceptance.

## Pricing authority

An active SKU must have a positive base price before it can be quoted. A
customer override then takes precedence. Missing base remains
`BASE_PRICE_REQUIRED` even when a legacy override exists. Retiring/restoring
an override reuses its original unique row. Both writes lock and refresh the
SKU, require the API's expected revision, and advance its pricing revision.

Country comes only from one completed, active, canonical tenant registration
for the active wholesaler. UG uses UGX (zero fractional digits); KE uses KES
(two). Missing/ambiguous/invalid source is `TENANT_CURRENCY_UNRESOLVED`, not a
fallback country. Money is Decimal and exact API strings, bounded by the
existing NUMERIC(12,2) contract. Nonzero excess precision is refused; trailing
zeros can be canonicalized without changing value. No FX or new rounding.

## Quote and creation

Merchant: POST `/orders/quote`, then POST `/orders` with `quote_token` and
`X-Idempotency-Key`. Client: the corresponding `/client/orders` endpoints.
The signed, purpose-separated HMAC quote expires after 900 seconds. It binds
tenant, wholesaler, customer, actor, operation, selected stable SKU/quantity,
unit/package, country, currency, price and audit revision/source. Preview
does not reserve stock. Submission re-resolves sorted SKU locks, fresh.

A changed economic line produces `PRICE_PREVIEW_STALE` before any order or
economic write, with old/new totals, difference, changed lines and a fresh
quote. Users must accept again; a second change is rejected again. Comparing
only totals is forbidden. Same-value ABA/revision/source/label changes do
not require an extra acceptance; both seen/resolved versions are retained.

Authentication, current RBAC and binding precede persistent replay. Actor,
customer, operation and key identify one committed intent. Advisory locking
and tenant uniqueness serialize processes; metadata and items share the
transaction. A committed replay returns the original snapshot despite later
price changes or quote expiry. A different successful intent under that key
is a conflict. Failed quotes do not consume the key. Unknown network/5xx/408
results retain the accepted intent and original key in the UI.

## Replacement and confirmation

Confirmation checks stored accepted snapshots and current economic lines
before the existing inventory/credit path. It never overwrites item prices.
Unverifiable legacy drafts require explicit replacement, not guessed units
or currency. Authorized replacement locks a zero-effect DRAFT, creates one
successor and calls the existing cancellation command in the same transaction.
Failure rolls both back; old amounts/items remain intact. Merchants need
both create/update. Clients can replace only their own proven client-source
draft for the same customer; legacy/other-actor/merchant-source drafts require
an authorized merchant. No new state or financial authority is introduced.

## Units and historical views

`unit` is opaque and case-sensitive. Display label is independent. Actual
unit/package changes after identity-use history require a new SKU; configured
base/active override also participates in repricing protection. All-zero
unused/unpriced preparation rows and same-value updates remain valid.
Quantity 2 boxes with package 12 uses the existing quantity contract once.
Quotes/items retain unit, package and label snapshots.

New orders store their currency and registration source. Old NULL currency
is `LEGACY_CURRENCY_UNVERIFIED`, never inferred from today's country. Read-only
finance/print projections report UNKNOWN or mixed currency instead of claiming
a known currency total. No ledger, collection, refund or credit algorithm is
changed. Migrations 001-039 are unchanged; 040 adds nullable preparation and
snapshot fields without inventing historic values. Bootstrap/readiness use
the exact new head and catalog while retaining role and guard requirements.
