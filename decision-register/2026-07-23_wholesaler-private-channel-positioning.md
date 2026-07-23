# DR-2026-07-23-001: Wholesaler-Centric Private Channel Positioning

## Decision ID

`DR-2026-07-23-001`

## Title

Position Mpango as a Wholesaler-Centric Private B2B Channel Operating System

## Status

**Approved**

## Date

2026-07-23

## Context

Mpango supports wholesaler tenants and retailer participants. A retailer may
have legitimate commercial relationships with more than one wholesaler. Earlier
PRD language converted that many-to-many data relationship into a retailer home
page that listed, searched, and switched among all linked wholesalers.

That experience would shift product value toward retailer procurement and make
Mpango appear to be a supplier-comparison platform. It would also create a
commercial trust problem even when tenant database isolation remained correct.

The product requires one coherent answer for:

- who the primary customer is;
- what unified identity means;
- whether supplier relationships are aggregated;
- how tenant branding is presented;
- which capabilities belong in the real-customer MVP.

## Decision

Mpango is a wholesaler-centric private B2B channel operating system.

The following rules are approved:

1. The wholesaler is the primary MVP customer and controls its tenant workspace.
2. A retailer participates only through a wholesaler invitation or another
   explicitly approved tenant-scoped entry.
3. A retailer may have multiple wholesaler relationships in the data model, but
   the MVP must not expose them as a supplier directory, marketplace, or
   comparison experience.
4. Mpango may provide one secure identity and credential lifecycle, but each
   business session represents one tenant only.
5. Client-visible tokens and public responses must not enumerate the retailer's
   complete supplier relationship graph.
6. Catalog, assigned price, cart, order, payment, receivable, export, cache, and
   audit behavior must remain scoped to the current tenant.
7. Cross-wholesaler search, price comparison, recommendations, carts, reports,
   and exports are prohibited in the wholesaler MVP.
8. The retailer enters through a wholesaler-specific private portal context.
9. The real-customer MVP must introduce verified tenant business identity and
   co-branding, with the wholesaler brand primary and Mpango visible as the
   trusted platform provider.
10. A future retailer procurement product requires a separate approved decision
    and may not be introduced as an implicit extension of this MVP.

## Rationale

The decision preserves the useful part of a networked SaaS identity while
protecting the business relationship that motivates wholesalers to adopt the
system.

Database isolation alone is insufficient. The UI, token model, notifications,
exports, browser state, platform operations, and product language must all
respect the same commercial boundary.

The decision also avoids per-wholesaler credential fragmentation. One identity
can provide consistent recovery and security without exposing or aggregating
supplier relationships.

## Alternatives Considered

### Retailer-Centric Marketplace

Rejected for the wholesaler MVP. It would optimize discovery and price
comparison for retailers and conflict with the primary customer's interest.

### Fully Separate Account Per Wholesaler

Rejected as the long-term identity model. It creates password duplication,
recovery inconsistency, and avoidable security and support costs.

### Unified Retailer Supplier Dashboard Without Comparison

Rejected for MVP. Even without an explicit comparison button, listing every
supplier materially lowers the cost of aggregation and signals marketplace
intent.

### Unified Identity With Private Supplier-Scoped Portals

Approved. It preserves credential continuity while keeping every commercial
session private and tenant-specific.

## Impact

This decision affects:

- product positioning and sales messaging;
- retailer invitation, login, and tenant selection;
- identity and JWT claims;
- frontend navigation and browser persistence;
- tenant onboarding, activation, and branding;
- email and notification templates;
- exports and background jobs;
- customer contracts, privacy terms, and support operations;
- wholesaler, retailer, and platform-operator documentation.

## Authority

- Product Owner approval in the 2026-07-23 CTO product review.
- L0 `docs/contracts/multi_tenancy_spec.md`: one wholesaler is one tenant and
  login resolves an explicit tenant context.
- DR-001: schema-per-tenant isolation.
- `docs/MPANGO_PRODUCT_POSITIONING_AND_VALUE_BOUNDARY.md`.

## Implementation

DC-12A changes documentation only. Implementation is intentionally split into
contract, backend, frontend, and runtime acceptance slices.

No engineer may interpret this decision as permission to change authentication,
provisioning, storage, or frontend behavior without an approved follow-up
contract and migration plan.

## Validation

The decision is considered implemented only when:

- no retailer-facing workflow lists all linked wholesalers;
- authentication creates one tenant context without exposing the full
  relationship graph;
- cross-tenant negative tests cover every business and asynchronous path;
- tenant application, approval, activation, and co-branding are runtime-proven;
- customer-facing and operator manuals describe the same boundary;
- release evidence contains no contradictory product wording.

## Related Decisions

- DR-001: Schema-per-Tenant Multi-Tenancy Strategy
- DR-003: Alembic Multi-Schema Migration Strategy
- DR-005: Constitution Sync Policy

## Notes

This is a product and commercial-boundary decision. It does not claim that a
recipient can be technically prevented from manually sharing information that
the recipient is authorized to see. Mpango's obligation is to prevent
unauthorized disclosure and to avoid platform-assisted cross-supplier
aggregation.
