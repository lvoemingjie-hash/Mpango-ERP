# P10 Platform Read-Only Foundation — Batch Readiness Packet

**Date**: 2026-06-08
**Branch**: `codex/platform-p10-readonly-foundation-2026-06-08`
**Base**: `origin/platform-dev` at `aa952045b3e2a606149d2c72064ffc6245f57a8d`
**Status**: Ready for review

---

## Commits Per Slice

| Slice | Commit | Description |
|-------|--------|-------------|
| P10-B | `c1b36d3` | feat(platform): P10-B read-only API skeleton |
| P10-C | `8ddb52f` | test(platform): P10-C contract-backed tests |
| P10-D | (this commit) | docs(platform): P10-D batch readiness packet |
| P10-R1 | (this commit) | fix(platform): P10-R1 security boundary — guard + redaction + evidence |

## Modified Files

| File | Slice | Action |
|------|-------|--------|
| `backend/api/v1/platform/p10/__init__.py` | P10-B | New |
| `backend/api/v1/platform/p10/schemas.py` | P10-B, P10-C | New |
| `backend/api/v1/platform/p10/services.py` | P10-B, P10-R1-B | New / Modified (metadata redaction) |
| `backend/api/v1/platform/p10/routes.py` | P10-B, P10-R1-A | New / Modified (guard dependency on all 6 endpoints) |
| `backend/api/v1/platform/p10/guard.py` | P10-R1-A | New |
| `backend/api/app.py` | P10-B | Modified (4 lines added — P10 router registration) |
| `backend/tests/test_platform_p10_contracts.py` | P10-C, P10-R1 | New / Modified (guard + redaction tests) |
| `ai-ledger/platform/2026-06-08_p10_readonly_foundation_batch.md` | P10-D, P10-R1-C | New / Modified |

**Total**: 7 new files, 1 modified file, 0 deletions.

## Tests

| Category | Count | Status |
|----------|-------|--------|
| Contract structure (CS-001..CS-015) | 25 | ✅ PASS |
| Fixture conformance (FC-001..FC-009) | 9 | ✅ PASS |
| Counterexample rejection (CR-001..CR-006) | 6 | ✅ PASS |
| Read-only behavior (mutation rejection) | 17 | ✅ PASS |
| API response shape | 11 | ✅ PASS |
| No leakage (extra fields forbidden) | 4 | ✅ PASS |
| **P10 Pre-R1 Total** | **81** | **✅ ALL PASS** |
| Platform-only access boundary (P10-R1-A) | 16 | ✅ PASS |
| Metadata redaction (P10-R1-B) | 8 | ✅ PASS |
| **P10-R1 Total** | **105** | **✅ ALL PASS** |

### P0 Platform Regression Tests

| Suite | Count | Status |
|-------|-------|--------|
| test_platform_p0.py | 13 | ✅ PASS |
| test_platform_audit.py | 17 | ✅ PASS |
| test_platform_audit_api.py | 31 | ✅ PASS |
| test_platform_stats_api.py | 10 | ✅ PASS |
| **P0 Regression Total** | **71** | **✅ ALL PASS** |

## Endpoints

| Method | Path | Contract | Status |
|--------|------|----------|--------|
| GET | `/api/v1/platform/p10/tenants` | TenantSummary list | Implemented, guarded |
| GET | `/api/v1/platform/p10/tenants/{tenant_id}` | TenantSummary detail | Implemented, guarded |
| GET | `/api/v1/platform/p10/tenants/{tenant_id}/health` | TenantHealth detail | Implemented, guarded |
| GET | `/api/v1/platform/p10/system/health` | SystemHealth snapshot | Implemented, guarded |
| GET | `/api/v1/platform/p10/audit/events` | PlatformAuditEvent list | Placeholder, guarded |
| GET | `/api/v1/platform/p10/audit/events/{event_id}` | PlatformAuditEvent detail | Placeholder, guarded |

## P10-R1: Security Boundary Fix

### P10-R1-A: Platform-Only Access Boundary

**Problem**: P10 router was registered in the real FastAPI app with no explicit platform-only authorization. Any authenticated user (or tenant-level user) could access platform operator endpoints.

**Fix**: Added `guard.py` inside the P10 module implementing `require_platform_operator` as a FastAPI dependency:
- Deny by default — no marker → 401, wrong marker → 403.
- Production: requires `X-Platform-Operator` header matching `PLATFORM_OPERATOR_SECRET` env var.
- Non-production: accepts `X-Platform-Test-Override` header for test harness.
- All 6 P10 endpoints wired with the guard dependency.
- Does NOT modify auth/RBAC/session/tenancy — self-contained in P10 module.

**Tests**: 16 new tests proving:
- Unauthenticated/no platform marker → 401 on all 6 endpoints
- Wrong operator secret → 403
- Tenant auth header alone → 401
- Empty operator header → 401
- Platform test override → 200 on all endpoint types
- Structural check: all 6 routes have guard dependency wired

### P10-R1-B: Metadata Redaction

**Problem**: `PlatformAuditEvent.metadata_redacted` was returning `audit_metadata` directly from `PlatformAuditLog`, so raw payloads, tokens, passwords could leak through the API.

**Fix**: Added `redact_metadata()` helper in services.py with case-insensitive sensitive-key pattern matching:
- Sensitive keys removed: password, token, secret, authorization, cookie, raw_body, request_body, response_body, payload, stack_trace, traceback, card, payment.
- Recursive redaction for nested dicts and lists of dicts.
- Safe keys preserved: result, denial_code, reason_code, actor_assignment_status, requested_at, etc.
- Both `list_audit_events` and `get_audit_event` now use `redact_metadata()` instead of raw pass-through.

**Tests**: 8 new tests proving:
- Direct sensitive keys removed
- Nested sensitive keys removed
- All 13 sensitive keyword patterns covered
- Known safe keys pass through untouched
- None/empty handling correct
- List-of-dicts redaction works
- Case-insensitive matching works

### P10-R1-C: Evidence Correction

**Corrections from CTO rerun**:
- ~~GitNexus risk LOW~~ → **GitNexus risk HIGH**: Runtime platform API skeleton adds API surface that is platform-operator-only infrastructure. This is NOT product business mutation risk — it is platform API surface exposure risk, now mitigated by P10-R1-A guard.
- ~~P0 regression 41 passed~~ → **P0 regression: 71 passed** (verified by rerun: 13 + 17 + 31 + 10 = 71).
- P10 tests: 81 pre-R1 → **105 post-R1** (81 + 16 guard + 8 redaction).
- GitNexus risk explanation: HIGH because P10 exposes a runtime platform API skeleton — the risk is unauthorized access to platform operator data, not mutation of product business data. P10-R1-A mitigates this.

## Data Source Status Per Contract Field

### TenantSummary
| Field | Source Zone | P10 Status | Current Value |
|-------|------------|------------|---------------|
| `tenant_id` | proposed_public_metadata | Mapped from wholesalers.id | Live |
| `tenant_name` | proposed_public_metadata | Mapped from wholesalers.name | Live |
| `tenant_schema` | available_now | Mapped from wholesaler.get_tenant_schema() | Live |
| `status` | proposed_public_metadata | Mapped from wholesalers.status | Live |
| `tier` | proposed_public_metadata | null — subscription model not built | Placeholder |
| `created_at` | proposed_public_metadata | Mapped from wholesalers.created_at | Live |
| `last_activity_at` | tenant_aggregate_required | null — aggregation not built | Placeholder |
| `user_count` | tenant_aggregate_required | null — aggregation not built | Placeholder |
| `health_status` | manual_or_unknown | "unknown" — no health signals | Placeholder |
| `recent_error_count` | telemetry_required | null — telemetry not built | Placeholder |
| `support_mode_active` | proposed_public_metadata | false — not implemented | Placeholder |

### TenantHealth
All fields return null/unknown except `tenant_id` and `tenant_schema`.

### SystemHealth
All fields return null/unknown except `overall_status` ("unknown") and `generated_at`.

### PlatformAuditEvent
Mapped from existing `platform_audit_logs` (P0 schema). Fields `actor_role`, `reason`, `correlation_id` return null (deferred/telemetry_required). `metadata_redacted` now uses redaction helper (P10-R1-B).

## Report Path

`ai-ledger/platform/2026-06-08_p10_readonly_foundation_batch.md`

## GitNexus Risk

**HIGH** — Runtime platform API skeleton adds API surface. P10 endpoints expose platform operator data (tenant lists, health, audit events). Before P10-R1-A, these were unguarded — any request reaching the P10 router could read platform data. After P10-R1-A, all 6 endpoints require explicit platform-operator credentials. The risk category is **platform API surface exposure**, not product business mutation. GitNexus impact analysis on `configure_app` showed LOW structural risk (1 direct caller), but the runtime risk of exposing unauthenticated platform operator endpoints is HIGH, now mitigated.

## Forbidden Path Audit

| Path Pattern | Found |
|-------------|-------|
| `backend/` business code | ✅ Only platform API module + guard |
| `frontend/` | ❌ None |
| `.github/` | ❌ None |
| `.claude/` | ❌ None |
| `product/` | ❌ None |
| `auth/` (broad rewrite) | ❌ None — guard.py is P10-local only |
| `RBAC/` | ❌ None |
| `tenancy/` | ❌ None |
| `migration/` | ❌ None |
| `payment/` | ❌ None |
| `session/` | ❌ None |
| `product-dev-recovered/` | ❌ None |

## Known Limitations

1. **TenantSummary.health_status** is always `"unknown"` — no health signal infrastructure exists yet.
2. **TenantHealth** returns all null fields except identity — requires telemetry, aggregation, and health check infrastructure.
3. **SystemHealth** returns all null component statuses — requires metrics/telemetry infrastructure.
4. **PlatformAuditEvent** is a placeholder mapping from P0 audit logs — `actor_role`, `reason`, `correlation_id` are null.
5. **TenantSummary.tier** is null — subscription/billing model not yet built.
6. ~~No authentication/authorization on P10 endpoints~~ → **Fixed in P10-R1-A**: Platform-only guard now enforced on all 6 endpoints.
7. No rate limiting specific to P10 endpoints — relies on existing global middleware.
8. Guard uses shared-secret header model — P11 will replace with proper platform auth context.

## Recommended P11 Next Step

**P11-A: Health Signal Infrastructure**
- Build tenant health check infrastructure (schema reachability, login activity aggregation).
- Wire `TenantHealth` to real data sources: schema_status, last_login_at, activity_counters.
- Wire `SystemHealth` to real database/API/queue metrics.
- Requires: telemetry foundation, cross-schema read aggregation, health check scheduler.

**P11-B: Platform Auth Context**
- Build platform admin authentication and role context.
- Wire `actor_role` and `actor_id` in PlatformAuditEvent to real auth context.
- Implement support-mode access control with reason enforcement.
- Replace P10-R1-A shared-secret guard with proper platform role context.

**P11-C: Tenant Aggregate Pipeline**
- Build cross-schema aggregation for user_count, last_activity_at, recent_error_count.
- Wire TenantSummary fields to live aggregates.

## Push Status

Branch `codex/platform-p10-readonly-foundation-2026-06-08` **pushed** to origin. Not merged to `platform-dev`.
