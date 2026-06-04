# P10-A Data Contract Only

**Date**: 2026-06-04
**Agent**: claude
**Branch**: codex/platform-p10a-data-contract-only-2026-06-04
**Base**: platform-dev (c136e53)
**Phase**: P10-A

---

## Objective

Define platform data contracts for observability and tenant-management surfaces. Contract-only: no backend, no frontend, no migrations, no API handlers. Four contracts with field types, nullable/unknown behavior, source zones, fixtures, and counterexample rejection.

## Contracts Defined

| Contract | Purpose |
|----------|---------|
| TenantSummary | Read-only tenant operational state for operator dashboards |
| TenantHealth | Per-tenant health assessment for monitoring/alerting |
| SystemHealth | Aggregate platform health for operator cockpit |
| PlatformAuditEvent | Append-only audit trail for compliance/debugging |

## Deliverables

- `docs/ai/PLATFORM_PRODUCT_CONTRACTS.md` — 4 contract definitions with field types, nullability, source zones, enum values, derived rules, counterexamples
- `docs/ai/PLATFORM_PRODUCT_CONTRACT_FIXTURES.md` — 9 valid fixtures + 6 rejected counterexamples
- `docs/ai/PLATFORM_PRODUCT_P10A_TEST_PLAN.md` — test plan with scope boundary, structure, conformance, and rejection tests
- `ai-ledger/platform/2026-06-04_p10a_data_contract_only.md` — this file

## Out of Scope

- No backend/frontend code changes
- No database migrations
- No API endpoints or handlers
- No auth/RBAC/tenancy/session/payment changes
- No tenant business-data edits
- No product-dev-recovered changes
- No platform-dev merge

## Key Design Decisions

1. **Source zone tracking**: Every contract carries `source_zone` (platform/tenant/unknown) so consumers know data freshness.
2. **Sentinel values**: `retailer_count = -1` for unreachable tenants (field is NOT NULL, so null is not an option).
3. **Event namespace**: `PlatformAuditEvent.event_type` uses `{domain}.{action}` format for extensibility.
4. **Append-only audit**: `PlatformAuditEvent` records are immutable — no updates, no deletes.
5. **Cross-contract UUID rule**: All UUIDs must be v4 or v7. No v1 (leaks MAC) or nil UUIDs.

## Changed Files vs origin/platform-dev (4 files)

| # | File |
|---|------|
| 1 | `docs/ai/PLATFORM_PRODUCT_CONTRACTS.md` |
| 2 | `docs/ai/PLATFORM_PRODUCT_CONTRACT_FIXTURES.md` |
| 3 | `docs/ai/PLATFORM_PRODUCT_P10A_TEST_PLAN.md` |
| 4 | `ai-ledger/platform/2026-06-04_p10a_data_contract_only.md` |
