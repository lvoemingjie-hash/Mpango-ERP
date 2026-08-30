# DC-12R1-MVP-L1 PRICING-R1 Implementation Contract

Status: `BLOCKED_PENDING_PRICING_R0_AND_STABLE_OFFER_IDENTITY`

Baseline: `24a28d76d6d9483d8101f8e0f537c148dc262859`

This is a target implementation contract, not an implementation authorization.

## 1. Minimum data contract

The accepted catalog-offer model gains:

- nullable `base_price NUMERIC(12,2)` with a positive check when present;
- explicit `currency_code`, fixed to `KES` for MVP;
- monotonically increasing price version or equivalent optimistic token.

The special-price model is keyed by stable offer identity:

```text
retailer_offer_prices
  id
  retailer_id
  catalog_offer_id
  price NUMERIC(12,2) > 0
  currency_code = KES
  created_at / updated_at
  created_by / updated_by
  is_deleted / deleted_at
  unique active (retailer_id, catalog_offer_id)
```

It remains tenant-local. Retailer validity is proved through the public binding
for the current wholesaler; no cross-tenant price is accepted.

## 2. Migration contract

- Migration is forward-only and runs a semantic preflight before mutation.
- Existing `retailer_prices` rows map only through a deterministic legacy SKU
  to one offer mapping produced by the accepted SKU migration.
- Zero or multiple target offers cause the entire tenant migration to fail
  before writes. There is no "first match" and no code/name guessing.
- Existing amounts and audit timestamps remain byte/decimal equivalent.
- Active uniqueness and positive-price constraints are catalog-verified.
- Bootstrap schema and Alembic upgrade must produce equivalent objects.
- Legacy order snapshots are never rewritten by the pricing migration.

## 3. API contract

Wholesaler endpoints, protected by exact tenant context:

- `GET /api/v1/pricing/offers`: base, override, effective price, source, and
  version for a selected retailer.
- `PUT /api/v1/pricing/offers/{offer_id}/base`: update base price using
  optimistic version.
- `PUT /api/v1/pricing/retailers/{retailer_id}/offers/{offer_id}`: create or
  replace an override using optimistic version.
- `DELETE /api/v1/pricing/retailers/{retailer_id}/offers/{offer_id}`: remove
  only the override and reveal base fallback.

Reads require `pricing:read`; mutations require `pricing:write`. Existing RBAC
codes are reused; no broad `orders:update` substitute is accepted.

Every response exposes `base_price`, `override_price`, `effective_price`,
`currency_code`, and `source`. The API must never require the browser to
recompute precedence.

## 4. UI contract

- The page clearly distinguishes "Base price" and "Special price for this
  retailer".
- Clearing a special price immediately previews fallback to the base price.
- Missing both values displays "Not available to order", not zero.
- All amounts are formatted from the returned currency code; MVP still accepts
  only KES.
- Save controls are disabled without `pricing:write`; read-only users can see
  effective price and source.
- Mobile 390px layout has no horizontal overflow and retains source labels.

## 5. Transaction and concurrency contract

- Mutations lock the target offer or special-price row.
- A stale version returns `409 PRICE_VERSION_CONFLICT` with zero writes.
- Delete replay is idempotent.
- A base-price change cannot mutate customer overrides.
- An override change cannot mutate the base price or historical order rows.
- Decimal arithmetic is server-side; float conversion is forbidden.

## 6. Required evidence before merge consideration

- Real PG migration upgrade, preflight rollback, bootstrap equivalence, and
  dual-tenant isolation.
- Resolver tests for override, fallback, missing price, deleted override,
  inactive offer, and stale versions.
- Backend and frontend mutation tests proving each consumer uses the same
  resolver semantics.
- Focused API/UI dual-order suites, full backend and frontend gates selected by
  the V3/V4 risk tier, and independent Lubuntu runtime before controlled merge.
