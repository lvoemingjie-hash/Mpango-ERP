# Cashier review and retailer portal context

These additive GETs do not confirm a payment, reserve a balance, assign a
receipt, or establish that money was received. The existing POST remains the
only confirmation authority. These are author-implemented interfaces pending
CTO review, not independent acceptance or a Mac implementation.

## Merchant read

`GET /api/v1/declarations/{declaration_id}/review-context` requires a canonical
current tenant/user/schema and current SQL `payments:read`. Identity-only,
retailer_operator, and mixed retailer/merchant audiences are refused. It does
not require or grant `orders:read` or `payments:confirm_declaration`.

The `DataResponse.data` contains `context`, `declaration`, `order`, `supplier`,
`retailer`, `binding`, `money`, `review_state`, `reason_codes`, `observed_at`.
Party names are trimmed live directory values, nullable with RESOLVED/MISSING.
Literal business names Supplier and Retailer are valid names, not blacklisted.
No email, phone, schema, aggregate binding balance, invoice, or payment row is
returned. `observed_at` is the statement timestamp in UTC, not a validity lock.

Money is a decimal string: KES has two places, UGX zero. Balance is this
order's total minus effective cash/transfer payments, including legitimate
pending and completed rows. Declarations are not deducted a second time;
credit is not cash. Invalid history and inconsistent hold/precision are
refused, not rounded or clamped. NULL legacy currency is unverified; it is not
guessed from the current country. Zero is a verified amount, not missing data.

The priority is integrity refusal, then NOT_ACTIONABLE, then UNRESOLVED, then
READY only when no reason remains. Fixed nonaction reasons, in order, are
DECLARATION_NOT_PENDING, ORDER_STATE_NOT_REVIEWABLE, NO_REMAINING_BALANCE,
DECLARATION_EXCEEDS_BALANCE. Unresolved reasons follow: NAME_UNRESOLVED,
CURRENCY_UNVERIFIED, TRANSFER_REFERENCE_MISSING. Draft/cancelled/voided/returned
orders have no current verified balance. READY is never `can_confirm`.

## Retailer self read

`GET /api/v1/client/auth/context` explicitly resolves the current client
identity and rechecks the current live user, role, directories and active
binding in its SELECT. It needs no additional client:finance:read permission.
Its data is exactly context/supplier/retailer/binding/observed_at, with the
same nonfinancial identity types. It never includes merchant financial data.

## Errors and consumption

All query selectors are rejected: 400 INVALID_CONTEXT_SELECTOR. Merchant
malformed/unknown/foreign/broken-attribution objects share 404
DECLARATION_NOT_FOUND. Missing context is 403 TENANT_CONTEXT_REQUIRED;
merchant audience/permission failure is 403 PERMISSION_DENIED. Existing client
resolver codes remain; a failed second relationship/directory check is 403
PORTAL_CONTEXT_UNAVAILABLE. Owned invalid payment history gives 409
PAYMENT_HISTORY_INTEGRITY; other read integrity failures give 409
REVIEW_CONTEXT_INTEGRITY. Existing authentication failures remain unchanged.

Mac must preserve account/tenant/portal/generation/request ownership, discard
late responses, and clear confirmation selections on invalidation. It still
requires current write permission and manual confirmation before using the
existing POST. Only the successful confirmation response identifies a receipt.
Neither GET nor KNOWN/READY is a prerequisite for strict legacy same-key/body
replay. No browser, frontend, production, or old P1 rerun is implied here.
