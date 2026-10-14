# S2 client reorder contract

This contract extends S1 pricing and draft creation at BASE
`41fd3adb1c355db8bab01ec77634413e27697f60`. The source is historical evidence;
accepting a reorder creates an independent draft using the current S1 resolver.

## HTTP boundary

Both endpoints use the existing client JWT/RBAC, tenant, retailer and active
binding checks. A missing source or a source outside the current retailer and
tenant returns the same `ORDER_NOT_FOUND` 404. Authorization is checked again
at submission and at committed replay.

* `POST /api/v1/client/orders/{source_id}/reorder/quote` accepts optional
  `selections`. Omitting them initially means keep every original line.
* `POST /api/v1/client/orders` accepts the distinct S2 body containing
  `source_order_id`, complete `selections`, `quote_token`, optional `notes`, and
  `X-Idempotency-Key`. The ordinary S1 body containing `items` is unchanged.

Each decision has `source_item_id` and `action`: `keep`, `remove`, or `replace`.
Keep uses the proven original sales-unit UUID and original quantity. Remove
explicitly excludes that original line. Replace requires a distinct, explicitly
selected `sellable_unit_id` and integer `quantity` (1–10000). Every source line
must occur exactly once; at least one valid selected line is required to submit.
Duplicate selected sales units are shown as unavailable until the client changes
a decision. Neither code nor name is used to infer historical identity.

## Preview and consent

Preview writes nothing. Its response includes every original line with its
historical snapshots, decision, status (`READY`, `UNAVAILABLE`, `REMOVED`),
reason, current line when resolvable, and safe `INSUFFICIENT_STOCK` warning.
The warning exposes no inventory quantity. Stable historical item UUID order
is disclosed as historical display order because no original click sequence
was persisted.

Stable identity and verified `linked_legacy` identity require a sales-unit UUID,
historical unit and positive package quantity. Keeping a line also requires the
current unit/package to match that evidence. Unknown identity, missing price,
inactive units and changed packaging stay visible. No missing price becomes
zero and no unavailable line is silently removed.

The response includes historical total/currency and, when all selected lines
are valid, a complete S1 quote, current total/currency and comparable delta.
Amounts follow S1 string precision: UGX integer strings and KES two decimals.
Retained historical amounts that predate the currency precision contract remain
readable without rounding and also produce no delta. Unknown or different
historical currency produces no delta. The full current
quote must be explicitly accepted. Fresh changes to any economic line reject
old consent even if the total is unchanged. Version, source, label or ABA
changes with equal economic details follow S1 and require no extra consent.

## Persistence and effects

The server fixes operation `client-reorder`; clients cannot select an operation
or pass a shortage bypass flag. Signed quote metadata and creation fingerprint
bind actor, retailer, tenant, source ID, every decision, historical identity/unit
evidence and the accepted complete economic lines. Existing `quote_seen` and
`quote_resolved` store a `reorder` object with `version: 1`. The response exposes
`source_order_id`; `replaces_order_id` is not used. No migration is added.

The existing durable create HTTP entry is reused so concurrent requests reach
the persistent intent lock. Its declared S2 permission dependency also performs
the live source/intent check during the existing cache authority evaluation; no
cache or authentication core is changed.

The existing persistent idempotency index and transaction advisory lock produce
one draft for concurrent equal key/intent requests. A committed replay returns
that result after fresh authorization and source/intent checks, even after quote
expiry. A different source, selection, accepted economics or notes under the
same key returns `ORDER_CREATE_IDEMPOTENCY_CONFLICT`. New keys permit independent
future reorders of the same source.

Creation produces DRAFT (client `CREATED`), preserving the requested quantity
even when stock is insufficient. It neither changes the source nor creates
payments, declarations, ledger entries, reservations, movements, credit holds
or binding balance effects. Ordinary S1 creation retains its stock gate.
Confirmation continues through the existing order command and inventory/credit
authorities; insufficient availability is rejected atomically.

## Draft detail actions

Ordinary S1 `CREATED` drafts retain their quote-review and replacement action.
A `CREATED` S2 draft with `source_order_id` does not offer ordinary replacement
or an immediate reorder action. The user must explicitly confirm cancellation
of that new draft; the historical source is never cancelled. Only a successful
response confirming that same draft as `CANCELLED` enables **Order again from
historical order**. The user selects that link separately to review a new quote
from the historical source. Cancellation failure or an unknown result does not
navigate, create another draft or enable continuation.

## Refusals

`REORDER_SELECTION_INVALID` covers missing/duplicate original decisions.
Schema-invalid decision shapes use the existing `VALIDATION_ERROR` 422. `REORDER_EMPTY_SELECTION` refuses all-removed intent.
`REORDER_SELECTION_UNAVAILABLE` refuses unresolved or changed historical unit
identity. `QUOTE_CONTEXT_CHANGED` refuses a token/intent/scope mismatch.
`REORDER_SOURCE_CHANGED` refuses changed source identity evidence.
`REORDER_PREVIEW_STALE` returns fresh economic quote information with no draft
write; the UI refreshes row eligibility before offering acceptance again.
Existing S1 availability, binding, authentication and permission refusals retain
their authority.

## Client retry

The client retains the accepted quote, source decisions, notes and original key
in session storage scoped by tenant, actor and source before sending. During an
unknown result, choices are locked and retry uses that accepted request. Reload
first reauthorizes the source preview before showing the retained request.
Denied access clears retention. A known rejection clears the pending acceptance;
changed price or eligibility must be reviewed before another submission.
