# Pricing customer selection

The pricing screen has separate customer-list and SKU pagination controls.
Customer pages use the existing API, at most 100 customers per request. SKU
pages remain 20 items each. No background download of the entire customer list
is performed.

Selecting a customer resets the SKU page to one. Turning the customer-list page
does not select a different customer or reset the SKU page. If the selected
customer is outside the visible customer-list page, their name remains visible
both above the prices and as the selected option.

Price rows and editors belong to a specific customer and SKU page. A late
response or error from an abandoned page cannot replace the current rows. A
save or retire/restore operation already sent keeps its original customer,
SKU, amount and expected revision; completing it after switching customers
does not reload the new customer's prices. Switching away is not cancellation
of an already submitted server operation.

An unsaved input survives unrelated customer-list updates. Switching customer,
SKU page or row revision creates a new editor. During loading, writes are not
available; current failures remain visible. Read-only users can navigate but
cannot save or retire/restore prices. Existing base-price, customer override,
retirement fallback, currency and server revision rules are unchanged.

This finite change is covered by component tests using controlled service
promises, not by a new browser, HTTP or database acceptance run. Linux browser
validation and integrated release approval remain separate CTO decisions.
