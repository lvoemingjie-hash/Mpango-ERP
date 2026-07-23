# Mpango Product Positioning and Value Boundary

## Status

Approved product direction for MVP planning as of 2026-07-23.

This document is governed by
`decision-register/2026-07-23_wholesaler-private-channel-positioning.md` and
supersedes earlier PRD language that described a retailer-facing directory of
all linked wholesalers.

## Product Thesis

Mpango is a wholesaler-centric private B2B channel operating system.

It connects a wholesaler's internal operations with invited retailer customers
so that catalog access, ordering, payment, receivables, inventory, and customer
service can run inside one trusted commercial relationship.

Mpango is not:

- a public marketplace;
- a retailer price-comparison service;
- a cross-supplier procurement aggregator;
- a product-discovery network that redistributes a wholesaler's customer
  relationship to the platform.

The product promise is:

> One trusted identity, multiple private relationships, one commercial context
> at a time, and no cross-wholesaler aggregation.

## Primary Customer and Value Allocation

The wholesaler is the primary MVP customer and the principal beneficiary of the
product. The retailer is an invited external participant whose experience must
be reliable and convenient within the inviting wholesaler's private workspace.

| Domain | MVP authority and value boundary |
| --- | --- |
| Mpango identity and credential security | The user controls the credential lifecycle; Mpango operates authentication and security controls. |
| Tenant workspace | The wholesaler controls activation, branding, membership, and business policy for its workspace. |
| Catalog, assigned price, inventory, orders, payments, credit, and receivables | These are current-workspace business data and must never be aggregated across wholesalers in the retailer experience. |
| Retailer transaction records | The retailer may access the records made available within that wholesaler relationship. |
| Retailer-to-wholesaler relationship graph | Confidential platform relationship metadata; not visible to another wholesaler and not presented as a retailer supplier directory in MVP. |
| Platform operations | Mpango operates the service under least privilege, audit, and contractual data-handling rules. |

This table defines product authority. Jurisdiction-specific controller,
processor, retention, and data-subject obligations must be stated separately in
customer contracts and privacy documentation.

## Unified Identity Without Commercial Aggregation

A unified Mpango identity is a security and continuity capability, not a
marketplace profile.

The identity layer may provide one credential lifecycle, account recovery,
multi-factor authentication, device security, and audit continuity. It must not
implicitly create a retailer-facing catalog of supplier relationships.

For an invited retailer, the approved MVP experience is:

1. The retailer opens a wholesaler-specific invitation, tenant code, or private
   portal entry.
2. Mpango authenticates the user and verifies membership in that specific
   wholesaler workspace.
3. Mpango issues or selects a context that represents exactly one tenant.
4. All catalog, price, cart, order, payment, finance, export, cache, and audit
   operations remain scoped to that tenant.
5. Accessing another wholesaler requires that other wholesaler's private entry
   context. Mpango does not present an all-supplier picker to the retailer.

Organization switching for a wholesaler owner who administers multiple
businesses is a separate product capability. It must not be implemented by
reusing a retailer supplier directory.

## MVP Commercial Privacy Rules

The following rules are mandatory:

- A wholesaler must not learn whether a retailer is connected to another
  wholesaler.
- A wholesaler must not see another wholesaler's catalog, assigned prices,
  inventory, orders, payments, credit, receivables, exports, or activity.
- A retailer must see only the current wholesaler's offer and transaction data.
- The platform must not provide side-by-side prices, cheapest-supplier
  recommendations, cross-supplier search, a shared cart, or consolidated
  procurement reporting.
- Email, password recovery, notifications, logs, analytics, and public error
  responses must not disclose other wholesaler relationships.
- Client-visible tokens must not carry a complete retailer-to-wholesaler
  relationship map. A workspace token must represent one current tenant.
- Browser persistence, cache keys, background jobs, and exports must include
  and validate the current tenant boundary.
- Platform support access to tenant business data must be least-privilege,
  purpose-limited, and auditable.

Mpango cannot prevent a retailer from manually sharing information that the
retailer is authorized to receive. Mpango must not make that sharing or
cross-supplier comparison easier through product aggregation.

## Explicitly Prohibited MVP Experiences

The following experiences are not approved for the wholesaler MVP:

- an application home page listing every wholesaler linked to a retailer;
- searching or sorting a retailer's linked wholesalers;
- showing competitor names or relationship counts inside a wholesaler portal;
- cross-wholesaler product or price search;
- cross-wholesaler price comparison;
- cross-wholesaler cart, checkout, order history, finance, or export views;
- a client-decodable identity claim that enumerates every supplier membership;
- using one wholesaler's data to recommend another wholesaler without explicit
  contractual authorization.

Any future retailer procurement product requires a separate product decision,
commercial model, consent boundary, threat model, and release gate. It must not
emerge as an implicit extension of the wholesaler MVP.

## Tenant Identity and Co-Branding Direction

Real-customer MVP onboarding must establish a verified business identity before
a tenant is fully activated. The minimum planning requirements are:

- legal or registered business name;
- trading or display name;
- country and business address;
- primary business contact;
- locally appropriate registration type and registration number;
- business registration evidence where applicable;
- tenant logo;
- application, review, approval, rejection, suspension, and activation states;
- reviewer identity, timestamps, reason codes, and audit history.

"Business registration evidence" is intentionally broader than "business
license" because acceptable documents vary by jurisdiction. Sensitive evidence
must use private object storage with restricted access; it must not be placed in
public static assets or stored as repository content.

The approved customer-facing brand hierarchy is:

1. the wholesaler's logo and trading name as the primary workspace identity;
2. a visible "Powered by Mpango" trust mark as the platform identity;
3. a safe default brand when tenant branding is incomplete.

The same SaaS deployment should resolve branding dynamically from a verified
tenant context. Per-tenant frontend builds, custom domains, arbitrary CSS, and
full white-labeling are not required for the initial MVP.

## MVP Scope Boundary

Required before the first broadly available real-customer rollout:

- an operator-assisted business application and approval path;
- minimum verified tenant profile data;
- tenant logo and display-name co-branding;
- a wholesaler-specific private portal entry;
- supplier-scoped retailer sessions;
- no retailer-facing supplier directory or relationship enumeration;
- wholesaler, retailer, and platform-operator user guidance;
- cross-tenant negative tests covering catalog, prices, orders, payments,
  finance, exports, notifications, browser state, and logs.

Deferred beyond the initial MVP:

- automated government-registry verification;
- OCR-based document verification;
- custom domains;
- full white-labeling or arbitrary theme builders;
- automated subscription billing;
- retailer procurement aggregation or price comparison;
- per-tenant deployment infrastructure except under a separately approved
  enterprise offering.

## Known Implementation Gaps

DC-12A is a documentation and product-decision slice. It does not claim the
current implementation already satisfies this boundary.

The current authentication behavior must be audited before a multi-wholesaler
retailer journey is enabled. In particular, retailer-facing
`available_tenants` behavior and client-visible membership maps such as `tmap`
are not the approved final retailer MVP contract. The corrective design belongs
in a separate contract-first authentication and UX slice.

The existing automatic tenant provisioning sequence must also be reviewed
against the approved business-application and operator-approval requirement.
Initial pilots may use operator-assisted onboarding, but no production process
may rely on undocumented manual database changes.

## Release Gates

A retailer multi-wholesaler capability is not release-ready until evidence
proves all of the following:

- retailer login through wholesaler A reveals no relationship with wholesaler B;
- tenant A cannot read or infer tenant B data;
- client tokens and public responses do not enumerate unrelated memberships;
- all browser storage and caches are tenant-scoped and clear safely on context
  termination;
- exports and background jobs reconstruct and validate the intended tenant;
- tenant branding cannot alter authorization or data resolution;
- platform support access is audited;
- relationship termination revokes future access while preserving required
  historical transaction records.

## Required Follow-Up Slices

- DC-12B: tenant application, verification, activation, branding, and security
  contract.
- DC-12C: backend schema, private evidence storage, review workflow, and
  activation gate.
- DC-12D: co-branded private portal UX, supplier-scoped retailer entry, and
  authentication-boundary correction.
- DC-12E: user manuals, operator runbook, cross-tenant security matrix, and
  real-customer runtime acceptance.
