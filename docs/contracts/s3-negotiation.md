# S3 minimum per-order negotiation

Authority: CTO-AUTH-S3-MINIMUM-NEGOTIATION-IMPLEMENTATION-R1-20261019 and
CTO-S3-MINIMUM-DECISION.zh-CN.md. This branch implements an author candidate;
it is not an acceptance, integration, CI or deployment decision. Its base is
6d003db6202f3e00ab465687919fa7b0e73bb5ee. Accepted RC2 remains unchanged.

## Commercial terms

A merchant with both live `pricing:write` and `orders:update` may offer new
unit prices for every existing line of an owned, zero-effect DRAFT. Original
SKU UUIDs, quantities, units/packages, tenant, customer and registration-based
UGX/KES cannot be edited. Positive finite bounded money retains S1 precision
(UGX zero, KES two decimal places). No missing price becomes zero.

The merchant must enter a future timezone-aware deadline. The API stores UTC;
the page labels the input timezone and displays the exact deadline. There is
no default, 24-hour rule, commercial duration cap or S1-token TTL substitution.
Both acceptance and first confirmation must occur before that deadline. The
server's post-lock `clock_timestamp()` is authoritative; equality is expired.
A click before the deadline is not a promise that a waiting transaction wins.
Successful confirmation is not reversed when the deadline later passes.

The actual mapped customer needs live `client:orders:read` and
`client:orders:create` plus an active supplier binding. Merchant permission
does not confer customer consent. Consent names one immutable proposal's ID,
version and SHA-256 digest, not request prices, currency or total.

## Routes and states

- Merchant GET/POST `/api/v1/orders/{source}/negotiations` lists/offers.
- Merchant POST `.../{proposal}/withdraw` withdraws a pending proposal.
- Customer GET `/api/v1/client/orders/{source}/negotiations` lists own history.
- Customer POST `.../{proposal}/accept` requires `X-Idempotency-Key`.
- Customer POST `.../{proposal}/reject` explicitly refuses a pending proposal.

Proposal states: pending -> accepted | rejected | withdrawn. Expired is a
derived eligibility condition, not an asynchronous state rewrite. At most one
pending proposal exists per source. Withdraw before offering a replacement,
including an expired pending proposal. A new price/deadline gets a new version;
old immutable offers and decisions remain. Retrying the same reject/withdraw
by the same actor returns that decision; conflicting decisions return 409.

`order_negotiation_proposals` has unique source/version, a partial unique
pending-source index, unique accepted order and a scoped durable accept-key
index. Checks enforce decision shape. A tenant-owned trigger rejects deletion,
immutable-field edits and further edits after a terminal decision. Migration
042 is forward-only; previous migrations and historical rows are not rewritten.

## Transaction and locking

All proposal mutations lock the fresh source order, then proposal. Acceptance
first serializes the customer/key with a transaction advisory lock, then locks
source/proposal and sorted units. It verifies zero retained payment, ledger,
movement, reservation and hold rows, original snapshots and live non-price
eligibility. Expiry is checked after those lock waits. Within one SAVEPOINT it
creates the linked replacement DRAFT, records exact customer consent and closes
the source via `OrderCommandService.cancel_order`. Any exception rolls back all
three, even if a service caller subsequently commits its outer transaction.
The source lines/notes/snapshots remain intact. Acceptance adds no stock,
reservation, hold, binding balance, payment, movement or ledger effect.

HTTP endpoints neither commit nor dispatch success facts outside the existing
request transaction boundary. The native middleware owns commit/rollback and
post-commit notification handling. No new financial/status writer is added.

Confirmation still runs exclusively through OrderCommandService. It locks the
replacement, then the accepted persistent proposal, then the existing globally
sorted stock/unit set. It does not lock the terminal source in reverse order.
It verifies source closure, durable actor/key/fingerprint, exact proposal bytes,
all accepted line snapshots, real registration/currency, active units/products,
stock and a second post-lock deadline decision before economic writes. Only
ordinary price-source recalculation is replaced: a genuine accepted price
survives subsequent base/override price changes. A JSON label or unbound DRAFT
cannot request this exception. Confirm creates only the existing reservation /
per-order hold / binding effects; canonical payments remain unchanged.

Original confirm/cancel competing with acceptance, and accept/reject/withdraw
competing with each other, serialize on the source lock. A changed/non-DRAFT or
economically touched source cannot be accepted. Different keys cannot produce
multiple replacement orders. S2 reorder resolves current ordinary prices and
never copies this agreement or deadline into a new commercial intent.

## Replay and refusal

An already committed same actor/key/proposal/version/digest returns the same
accepted order, even after expiry. A different intent under that scoped key,
or a different key/account accepting an already accepted offer, is a conflict.
The proposal transaction, not an in-memory response, owns this guarantee.
New routes bypass only the generic response cache; all actual live permissions,
identity, user activity, binding and order ownership dependencies still run.
The browser retains the original scoped key/intent across unknown responses
and never silently creates another order on retry.

Named refusals include `NEGOTIATION_PENDING`, `NEGOTIATION_EXPIRED`,
`NEGOTIATION_ALREADY_DECIDED`, `NEGOTIATION_INTENT_CONFLICT`,
`NEGOTIATION_IDEMPOTENCY_CONFLICT`, `NEGOTIATION_SOURCE_CHANGED`,
`NEGOTIATION_CONTEXT_CHANGED`, `NEGOTIATION_INTEGRITY`, and
`NEGOTIATION_CONSENT_REQUIRED`. Foreign ownership is a neutral 404. Existing
S1 money, live permission/binding and inventory error categories remain.

## Verification map and limits

- `tests/s3_negotiation/test_contract.py`: UG/KE, exact price/deadline,
  history, pending/reject/withdraw and live replay authority.
- `test_atomicity_and_races.py`: after-real-save/close failure rollback,
  independent PG source/stock-lock barriers, all conflicting command pairs,
  post-wait expiry and post-expiry committed replay.
- `test_provenance_and_safety.py`: counterfeit source, equal-total changed
  lines, unavailable units, stock, retained movements, S2 current pricing,
  live revocation and foreign tenant.
- `frontend/src/tests/S3Negotiation.test.tsx`: explicit exact consent,
  no default deadline, permission UI and unknown-response same-key retry.

These are implementation/test entry points, not prefilled execution results.
Migration parity, mutations, final frozen regressions and UG/KE native browser
results belong to task evidence and must be listed individually when executed.
Ordinary full backend CI, remote CI, multi-worker cache, refund, formal credit,
chat/approval flows, real notifications and deployment are not claimed here.
