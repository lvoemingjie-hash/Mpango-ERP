# P10-A-R1 Data Contract Aligned to P9-R2

**Date**: 2026-06-05
**Agent**: claude
**Branch**: codex/platform-p10a-r1-data-contract-aligned-2026-06-05
**Base**: platform-dev (948cd2e, includes P9 merge)
**Phase**: P10-A-R1

---

## Objective

Rebuild platform data contracts to align field-by-field with P9-R2 data source map (`PLATFORM_PRODUCT_P10_DATA_SOURCE_MAP.md`). Original P10-A was rejected for inventing contracts independent of the approved source map.

## Contracts Defined

| Contract | Fields | Aligned to P9-R2 |
|----------|--------|------------------|
| TenantSummary | 11 | Yes - all fields from source map |
| TenantHealth | 10 + 3 sub-structures | Yes - all fields from source map |
| SystemHealth | 11 | Yes - all fields from source map |
| PlatformAuditEvent | 11 | Yes - all fields from source map |

## Key Changes from P10-A (Rejected)

| Change | P10-A (Rejected) | P10-A-R1 (This) |
|--------|------------------|-----------------|
| TenantSummary fields | `schema_name`, `plan`, `retailer_count` | `tenant_schema`, `tier`, `user_count`, `health_status`, `recent_error_count`, `support_mode_active` |
| TenantHealth fields | Simple `CheckResult[]` | `schema_status`, `last_login_at`, `activity_counters`, `recent_errors`, `slow_routes`, `failed_jobs`, `last_health_check_at` |
| SystemHealth fields | Tenant counts only | `api_status`, `database_status`, `database_connections`, `queue_status`, `cpu_status`, `memory_status`, `disk_status`, `error_rate`, `slow_request_count` |
| AuditEvent fields | `event_type`, `actor_type`, `payload` | `actor_role`, `scope`, `action`, `reason`, `result`, `metadata_redacted`, `correlation_id` |
| Implementation assertions | "All platform data lives in public schema" | Removed - only proposed/source status labels |
| Source status | Custom (platform/tenant/unknown) | P9-R2 vocabulary: available_now, proposed_public_metadata, tenant_aggregate_required, telemetry_required, manual_or_unknown, deferred |

## Deliverables

- `docs/ai/PLATFORM_PRODUCT_CONTRACTS.md` - 4 contracts aligned to P9-R2
- `docs/ai/PLATFORM_PRODUCT_CONTRACT_FIXTURES.md` - 9 valid + 6 rejected
- `docs/ai/PLATFORM_PRODUCT_P10A_TEST_PLAN.md` - scope boundary + structure + conformance
- `ai-ledger/platform/2026-06-05_p10a_r1_data_contract_aligned.md` - this file

## Out of Scope

- No backend/frontend code
- No database migrations
- No API endpoints or handlers
- No auth/RBAC/tenancy/session/payment changes
- No tenant business-data edits
- No product-dev-recovered changes
- No platform-dev merge
- No unapproved implementation assertions

## P10-A-R2 CTO Index Fix

Codex CTO review found that the P10-A contract documents were not included in the `docs/ai/README.md` Platform Product Track entry. That would let a future P10-B worker start from P9 product docs without reading the accepted P10-A contracts, fixtures, and test plan.

R2 adds these startup-index entries:

- `docs/ai/PLATFORM_PRODUCT_CONTRACTS.md`
- `docs/ai/PLATFORM_PRODUCT_CONTRACT_FIXTURES.md`
- `docs/ai/PLATFORM_PRODUCT_P10A_TEST_PLAN.md`

No PRD body, runtime code, migrations, API handlers, UI, auth/RBAC/tenancy/session/payment, or tenant business-data files were changed.

## Changed Files vs origin/platform-dev (5 files)

| # | File |
|---|------|
| 1 | `docs/ai/PLATFORM_PRODUCT_CONTRACTS.md` |
| 2 | `docs/ai/PLATFORM_PRODUCT_CONTRACT_FIXTURES.md` |
| 3 | `docs/ai/PLATFORM_PRODUCT_P10A_TEST_PLAN.md` |
| 4 | `docs/ai/README.md` |
| 5 | `ai-ledger/platform/2026-06-05_p10a_r1_data_contract_aligned.md` |
