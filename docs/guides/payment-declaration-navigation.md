# Payment declaration navigation

Payment declarations have two ends. A declaration is **not** a payment:
submitting one has zero effect on payments, ledger, receivables, or order
status. The merchant verifies receipt offline and then explicitly
**Confirms** the declaration; confirmation books the payment through the
canonical path and links a receipt. The same money is never recorded twice:
**Record Payment / Collect are separate entry points, not a required step
after confirming a declaration.**

1. Retailer (declare): open your order from **Orders**. Orders you may
   declare on show a **Declare Payment** action next to **Order again** /
   **Print order**. It requires the `client:payments:declare` permission;
   the server remains the final arbiter of whether a declaration is
   accepted. The entry is a link only — nothing is submitted until you
   complete the form on the declaration page.
2. Retailer (history): **Payments** shows **My declarations** for users
   with the `client:payments:read` permission. It opens the existing
   declarations history; print links there keep their existing permission.
3. Merchant (queue): the ERP sidebar shows **Declarations** next to
   **Payments**. It opens the existing
   **Payment Declarations — Pending** queue. Reading it still requires
   `payments:read`; **Confirm / Reject** still require
   `payments:confirm_declaration`. Navigation adds no authorization.
4. Entries are discoverability only. Links use the order the page actually
   fetched; when an order fails to load or a permission is absent, the
   entry is not shown. Nothing is auto-submitted, auto-confirmed, or
   auto-collected by following a link, and no balance or "amount you may
   declare" is computed in the client.
5. An unauthorized or cross-tenant request to the underlying routes/APIs
   keeps the existing refusal. Fewer visible entries is not a substitute
   for those server-side checks.

This guide covers navigation only. It does not change pricing, order,
payment, idempotency, or ledger behavior, does not authorize deployment,
and does not add permissions or admin fallbacks.
