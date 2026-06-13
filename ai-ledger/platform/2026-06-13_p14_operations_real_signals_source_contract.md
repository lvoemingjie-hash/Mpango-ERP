# P14 Operations Cockpit - Real Signals Source Contract

**Date:** 2026-06-13
**Branch:** `codex/platform-p14-operations-real-signals-2026-06-13`
**Base:** `41181fc` (origin/platform-dev P13 batch merge)
**Phase:** P14-A Source Contract

---

## Purpose

P14 turns the P13 safe API/UI skeleton into a more useful **read-only** operations
cockpit by wiring **real, safe platform signals where available**, while preserving
the `unknown != healthy` and `null != 0` fallback semantics.

This document is the authoritative source map for every P13 ops field: what feeds
it, what is shown when the source is unavailable, how fresh it is, and how it is
redacted. It is the contract P14-B (backend adapters) and P14-C (frontend
presentation) implement.

---

## Governing Principles

1. **Real only where honest.** A field is marked `available` only when a real,
   safe, read-only source backs it. If no such source exists, the field stays
   `unavailable`/`unknown` and the reason is documented below and surfaced to the
   UI via `unavailable_reason`.
2. **unknown != healthy.** Unknown is gray, never green.
3. **null != 0.** Unavailable totals are `null`, never a fabricated `0`.
4. **Read-only.** No mutation endpoints, no writes except the existing best-effort
   ops audit event.
5. **Identity-only.** All endpoints require identity-only platform operator
   through the P10 guard. No tenant-contextual access.
6. **No sensitive payloads.** No host, port, DSN, credentials, or request bodies.
   Only counts, redacted route paths, and statuses.

---

## Real Sources Available On Platform-Dev

| Source | Table / object | Safe? | Used by P14 |
|--------|----------------|-------|-------------|
| SQLAlchemy async engine pool | `async_engine.pool` (QueuePool, `pool_size`/`max_overflow`) | Yes, local runtime object and no credentials | Database pool stats |
| DB connectivity ping | `SELECT 1` on the public-schema session | Yes, trivial read-only query | Database latency and status |
| Platform audit log | `public.platform_audit_logs` (append-only) | Yes, but lacks correlation IDs | Not wired |
| P10 `get_system_health` | Stub returning all `None` | N/A | Not a real source today |

**Key finding:** The platform audit log records `ops_*_view` and
`ops_access_denied` events, but it has no request correlation ID and no
request-latency telemetry. P13 error classes, top routes, and slow routes require
`sample_correlation_ids`; noisy-neighbor analysis requires cross-tenant business
telemetry outside platform-runtime scope. Wiring those from audit logs would
fabricate or mislabel signals, so they remain unavailable with documented reasons.

---

## Per-Field Source Map

### Database Health (`ResourceHealthSummary.database`) - Wired Real In P14-B

| Attribute | Value |
|-----------|-------|
| `status` | Real. Derived from ping latency: `healthy` < 200 ms, `degraded` < 1000 ms, `unhealthy` >= 1000 ms or ping failed. |
| `latency_ms` | Real. Wall-clock duration of `SELECT 1` on the request session, in integer milliseconds. `null` only if the ping errored. |
| `connection_pool_active` | Real best-effort. Checked-out connections parsed from `async_engine.pool.status()`. `null` if pool introspection is unavailable. |
| `connection_pool_idle` | Real best-effort. Idle connections from `pool.status()`. `null` if unavailable. |
| `connection_pool_max` | Real best-effort. `pool_size + max_overflow` or parsed from `pool.status()`. `null` if unavailable. |
| Freshness | `generated_at` equals ping time in UTC ISO-8601. Live per request. |
| Fallback | Ping failure returns `status="unhealthy"`, `latency_ms=null`, and pool stats `null`. Pool introspection failure leaves pool stats `null` but keeps latency/status real. |
| Redaction | No host, port, DSN, or credentials. `pool.status()` raw text is parsed server-side and never serialized. |

### Queue / CPU / Memory / Disk (`ResourceHealthSummary.*`) - Unavailable

| Attribute | Value |
|-----------|-------|
| Source | None on platform-dev. Requires host runtime metrics infrastructure. |
| Freshness | N/A |
| Fallback | `null`; UI shows "Not instrumented". |
| Redaction | N/A |

### Error Rate (`ErrorRateSummary`) - Unavailable

| Attribute | Value |
|-----------|-------|
| Source | None honest. Application error telemetry is not instrumented and audit log lacks correlation IDs. |
| `total_errors` | `null`, not `0`. |
| `error_classes` / `top_routes` | `[]`; require `sample_correlation_ids`. |
| `top_tenants` | `null`; identity-only operator has no tenant business scope. |
| `unavailable_reason` | `Request error telemetry is not instrumented; correlation IDs are required for class/route breakdown.` |
| Freshness | `generated_at` equals request time. |
| Redaction | N/A; no payloads. |

### Slow Routes (`SlowRouteSummary`) - Unavailable

| Attribute | Value |
|-----------|-------|
| Source | None honest. Per-request latency telemetry is not instrumented. |
| `total_slow_requests` | `null`; `routes=[]`. |
| `unavailable_reason` | `Per-request latency telemetry is not instrumented.` |
| Freshness | `generated_at` equals request time. |
| Redaction | N/A |

### Noisy Neighbors (`NoisyNeighborSummary`) - Unavailable

| Attribute | Value |
|-----------|-------|
| Source | None honest. Requires cross-tenant business-activity telemetry outside platform-runtime scope. |
| `tenants` | `[]`. |
| `unavailable_reason` | `Cross-tenant activity telemetry is not available; requires business-scope instrumentation outside platform-runtime scope.` |
| Freshness | `generated_at` equals request time. |
| Redaction | N/A |

### System Health (`GET /ops/health`) - Unchanged

Delegates to P10 `get_system_health`, currently a stub returning `unknown`/`None`.
P14 does not alter this endpoint; it remains honest about its stub state.

---

## Contract Changes Introduced By P14

Additive, backward-compatible optional fields, defaulting to `None`:

- `ErrorRateSummary.unavailable_reason: Optional[str]`
- `SlowRouteSummary.unavailable_reason: Optional[str]`
- `NoisyNeighborSummary.unavailable_reason: Optional[str]`

These let the frontend state why a signal is unavailable without changing any
existing field semantics. `extra="forbid"` is preserved on input; the new fields
are declared, not extra.

No new dependencies, no migrations, no tenant/business paths, no mutation
endpoints.

---

## Risk

| Area | Risk | Mitigation |
|------|------|------------|
| DB ping on each `/ops/resources` call | LOW, trivial `SELECT 1`, read-only, identity-only audience | One query per request; same cost as a health check |
| Pool introspection fragility | LOW, best-effort and falls back to `null` | Defensive parse; `null` preserves honest semantics |
| Audit-log access-denied mislabel as error rate | AVOIDED | Kept unavailable; no fabricated or mislabeled signals |

## Blockers

None. Fields without a safe real source are explicitly documented as
`unavailable` with a reason. This is the intended P14 outcome.
