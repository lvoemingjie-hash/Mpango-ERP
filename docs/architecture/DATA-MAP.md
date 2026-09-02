# Data Ownership Map

## Public schema: identity and relationship control plane

The public schema stores global records needed before or across tenant business
sessions.

| Data family | Representative models | Ownership rule |
|---|---|---|
| Tenant registry | `wholesalers`, `tenant_registrations` | One wholesaler owns one derived tenant schema |
| Onboarding tokens | email verification, onboarding status, owner setup/reset | Store lifecycle state and token hashes; never expose raw secrets in reports/logs |
| Retailer identity | `retailers` | Global retailer identity, not tenant business data |
| Supplier relationship | `wholesaler_retailer_bindings`, `invitations` | Relationship scope is explicit; email alone is not a binding |
| Retailer credentials | setup/reset token records | Credential lifecycle tied to the retailer identity and supplier portal contract |
| Platform control | platform tenants, operators, audit/control records | Separate platform-operator trust boundary |

Public tables may reference tenant identities by UUID, but cross-schema foreign
keys are intentionally limited. Services must validate both sides of a
relationship before entering tenant business state.

## Tenant schema: wholesaler business data

Each wholesaler schema is derived from the wholesaler UUID and contains the
business records operated by that wholesaler.

| Data family | Representative models | Important invariant |
|---|---|---|
| Access control | users, roles, permissions, user-role mappings | Server-derived tenant context plus permission enforcement |
| Catalog | current flat `skus` | SKU code unique inside the tenant baseline model |
| Inventory | stocks, movements, reservations, intake/import runs | Atomic stock changes and auditable movement/reservation lifecycle |
| Orders | orders and order items | Order items preserve product name, SKU code, quantity, unit price and subtotal snapshots |
| Payments | payments, declarations, receipt sequences | Idempotent writes and supplier/retailer relationship scope |
| Finance | receivables and immutable ledger entries | Canonical write paths; retailer reads do not settle balances |
| Reporting | jobs, reports, materialized/semantic reads | Reads must retain tenant context and avoid cross-tenant cache keys |

## External and ephemeral state

| Store | Use | Boundary |
|---|---|---|
| Redis | cache, jobs, coordination/rate-limit state | Test authority uses isolated DB and proves it is empty before execution |
| Mail adapter | onboarding and credential messages | Production provider status is separate from local/test sinks |
| Object/file storage | imports, exports, artifacts | Do not place secrets or raw customer evidence in Git reports |
| Browser storage | access/refresh and portal context | Public recovery tokens must not be persisted or logged |

## Tenant selection and request flow

1. Authentication verifies identity and issues claims appropriate to the user type.
2. Server middleware/context resolves the allowed tenant schema.
3. Database sessions establish the tenant search path with `public` available for
   global identity lookups.
4. Route and service layers enforce RBAC and relationship scope.
5. Logs, jobs, exports, caches, and retries must carry the same tenant identity.

No URL, header, proof JSON, or caller-supplied schema name may independently
authorize tenant selection.

## Cross-boundary invariants

- Retailer identity is global; business access is supplier-relationship scoped.
- Tenant business rows cannot be selected using retailer identity alone when a
  wholesaler/binding dimension is required.
- Public onboarding state must reach explicit terminal or retryable states.
- Password, setup, reset, invitation, and onboarding tokens are secret-bearing
  inputs; reports may record only categories, presence booleans, or hashes where
  the contract explicitly permits them.
- Payment confirmation, receivables, and ledger mutation remain server-authoritative.
- Printed and client finance views are read-only projections of authoritative data.

## Catalog migration boundary

The protected baseline does not contain `CatalogProduct`, `SellableUnit`, or
`CatalogOffer` tables. The SKU candidate proposes those identities and migration
`038`, including legacy behavior. Until a controlled merge:

- do not write docs or new code as if those tables exist in production;
- do not guess legacy product identity from SKU code;
- do not start pricing/reorder contracts that require the new identity;
- keep current order item snapshots authoritative for historical display.

## Schema evolution rule

Alembic is the schema authority. The current baseline has one head:
`037_payment_declarations_schema`. A future `038` must be an exact declared
successor, pass all-tenant preflight, fail without partial mutation, and retain
bootstrap parity before it can become current truth.
