# DC-12A Product Positioning and Value Boundary

## AI Role

CTO / Product Architect

## Scope

Documentation-only product authority correction covering:

- primary customer and value allocation;
- unified identity versus private commercial context;
- wholesaler-retailer many-to-many boundaries;
- retailer aggregation prohibitions;
- tenant verification and co-branding direction;
- MVP and post-MVP boundaries.

## Baseline

- Base branch: `origin/product-dev-recovered`
- Base commit: `1be053e0ad362df66b2e153e8317d6a559eed61a`
- Working branch: `codex/dc12a-product-positioning-value-boundary-2026-07-23`

## Inputs

- L0: `docs/contracts/multi_tenancy_spec.md`
- L0: `docs/contracts/api_contract.md`
- L1: `docs/contracts/domain_workflows.md`
- L1: `docs/contracts/nonfunctional_ops_spec.yaml`
- Existing PRD: `docs/#1Mpango_ERP_PRD_v10(DETAIL).md`
- DR-001: schema-per-tenant multi-tenancy
- DR-005: constitution sync policy
- Product Owner direction from the 2026-07-23 CTO product review

## Findings

The existing PRD correctly stated that wholesalers invite retailers and that
tenant data is isolated. It also required the retailer application to list,
search, and switch among every linked wholesaler.

Those two positions were technically compatible but commercially inconsistent.
The second position would turn a many-to-many relationship model into a
retailer-facing supplier aggregation experience and weaken the product's
wholesaler-centric value proposition.

## Decisions

- Mpango is a wholesaler-centric private B2B channel operating system.
- Unified identity is retained as a security capability.
- Retailer sessions are supplier-scoped and represent one tenant at a time.
- Retailer-facing supplier directories and cross-wholesaler aggregation are
  prohibited for MVP.
- Multiple wholesaler relationships may exist internally without being exposed
  as a marketplace experience.
- Real-customer MVP planning must include tenant business verification,
  operator approval, and tenant-first co-branding with a visible Mpango trust
  mark.
- A future retailer procurement product requires a separate product decision.

## Outputs

- Added `docs/MPANGO_PRODUCT_POSITIONING_AND_VALUE_BOUNDARY.md`.
- Added `decision-register/2026-07-23_wholesaler-private-channel-positioning.md`.
- Updated both synchronized PRD copies to remove the retailer supplier-directory
  contract.
- Updated `decision-register/README.md`.
- Added this ledger.

## Scope Boundary

No product code, tests, migrations, schemas, configuration, lockfiles,
deployment files, or runtime environments were changed.

DC-12A does not claim that the current authentication and frontend
implementation already complies. `available_tenants`, client-visible membership
maps, tenant activation sequencing, and branding implementation require
contract-first follow-up work.

## Required Follow-Up

- DC-12B: tenant application, verification, activation, branding, and security
  contract.
- DC-12C: backend implementation.
- DC-12D: co-branded private portal and supplier-scoped authentication UX.
- DC-12E: manuals, security matrix, and runtime acceptance.

## Risk

Documentation risk is low. Downstream implementation impact is high because the
decision affects authentication, onboarding, frontend navigation, tenant
branding, notifications, exports, and customer operations. Follow-up work must
remain contract-first and independently reviewed.

## Validation

- Both PRD copies have identical SHA256 content after the amendment.
- The five superseded retailer supplier-directory phrases have zero matches in
  both PRD copies.
- `git diff --check`: passed.
- New English documents contain ASCII only.
- Mojibake candidate scan: passed.
- Email, secret, token, private-key, SMTP, and database-URL pattern scan:
  passed.
- Scoped pre-commit: passed after the standard end-of-file hook normalized the
  three new Markdown files.
- Scoped detect-secrets hook: passed.
- GitNexus pre-commit change analysis: low risk, no affected execution flows;
  no code symbol was modified, so symbol impact analysis was not applicable.

## Verdict

`PASS_FOR_CTO_DC12A_PRODUCT_DIRECTION_LOCK`
