# S1 Bounded Repair R2

Retirement is a versioned state operation on an existing retailer override.
The submitted amount must equal its retained amount. Retirement neither
re-prices nor creates a missing row. Republishing validates current currency
precision and reuses the retained row. Retired audit formatting issues are
reported separately from effective-price orderability.

Quotes and both creation schemas have one 100000-character token budget.
The signing boundary returns QUOTE_BUDGET_EXCEEDED (422) before issuing an
unusable quote. The 100-line selection limit is not a promise that every
100-line catalog description fits the signed-token budget. No money, identity
or audit fields are truncated. Shorter selections can be quoted again.

Local SKU fields only update their target row. Shared product metadata first
determines and locks all current product SKU rows in ascending UUID order;
both SKU and catalog update entrances use this ordering. Unit/package history
guards and all draft-economic invariants remain unchanged. Concurrent addition
of a new sellable unit to this determined set is not proven by this finite run.

S1 catalog checks bind constraints and indexes to the expected table, not
schema-wide object names. Readiness and bootstrap require exactly one 040
revision. Migration 040 remains independent of runtime bootstrap.

The repair is author evidence only. Independent V3, full suite, cache R3
integration, CI, push, merge and deployment are not claimed.
