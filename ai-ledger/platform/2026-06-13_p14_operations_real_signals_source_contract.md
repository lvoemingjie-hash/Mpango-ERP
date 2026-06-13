# P14 Operations Cockpit -- Real Signals Source Contract

**Date:** 2026-06-13
**Branch:** `codex/platform-p14-operations-real-signals-2026-06-13`
**Base:** `41181fc` (origin/platform-dev -- P13 batch merge)
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

## Governing principles

1. **Real only where honest.** A field is marked `available` only when a real,
   safe, read-only source backs it. If no such source exists, the field stays
   `unavailable`/`unknown` and the reason is documented below (and surfaced to
   the UI via `unavailable_reason`).
2. **unknown != healthy.** Unknown is gray, never green.
3. **null != 0.** Unavailable totals are `null`, never a fabricated `0`.
4. **Read-only.** No mutation endpoints, no writes except the existing best-effort
   ops audit event.
5. **Identity-only.** All endpoints require identity-only platform operator
   (P10 guard). No tenant-contextual access.
6. **No sensitive payloads.** No host/port/DSN/credentials/request bodies. Only
   counts, redacted route paths, and statuses.

---

## Real sources available on platform-dev (P14-A inspection)

| Source | Table / object | Safe? | Used by P14 |
|--------|----------------|-------|-------------|
| SQLAlchemy async engine pool | `async_engine.pool` (QueuePool, `pool_size`/`max_overflow`) | Yes -- local runtime object, no credentials | Database pool stats |
| DB connectivity ping | `SELECT 1` on the public-schema session | Yes -- trivial read-only query | Database latency + status |
| Platform audit log | `public.platform_audit_logs` (append-only) | Yes -- but lacks correlation IDs | Not wired (see below) |
| P10 `get_system_health` | stub -- returns all `None` | N/A (stub) | Not a real source today |

**Key finding (why most fields stay unavailable):** The platform audit log records
`ops_*_view` and `ops_access_denied` events, but it has **no request correlation
ID** and **no request-latency telemetry** (P10 marks `correlation_id` and all
latency/error-rate fields `telemetry_required`). The P13 `error_classes`,
`top_routes`, and `slow_routes` breakdowns all *require* `sample_correlation_ids`
(schema-enforced), and noisy-neighbor analysis requires **cross-tenant business
telemetry** (forbidden product scope). Wiring those from the audit log would
fabricate or mislabel signals. Per principle #1, they stay `unavailable` with a
documented reason.

---

## Per-field source map

### Database health (`ResourceHealthSummary.database`) -- **Wired REAL in P14-B**

| Attribute | Value |
|-----------|-------|
| `status` | **Real.** Derived from ping latency: `healthy` < 200 ms, `degraded` < 1000 ms, `unhealthy` >= 1000 ms or ping failed. Replaces the fabricated `unknown`. |
| `latency_ms` | **Real.** Wall-clock duration of `SELECT 1` on the request's session (ms, int). `null` only if the ping itself errored. |
| `connection_pool_active` | **Real (best-effort).** Checked-out connections parsed from `async_engine.pool.status()`. `null` if pool introspection unavailable (e.g. NullPool / non-standard pool). |
| `connection_pool_idle` | **Real (best-effort).** Idle connections in pool from `pool.status()`. `null` if unavailable. |
| `connection_pool_max` | **Real (best-effort).** `pool_size + max_overflow` from settings, or parsed from `pool.status()`. `null` if unavailable. |
| Freshness | `generated_at` = ping time (UTC ISO-8601). Live per request. |
| Fallback | Ping failure -> `status="unhealthy"`, `latency_ms=null`, pool stats `null`. Pool introspection failure -> pool stats `null` but latency/status still real. |
| Redaction | No host/port/DSN/credentials. Only integer counts + latency + status. `pool.status()` raw string is parsed server-side and never serialized. |

### Queue / CPU / Memory / Disk (`ResourceHealthSummary.*`) -- **unavailable**

| Attribute | Value |
|-----------|-------|
| Source | None on platform-dev. Requires host runtime metrics infra. |
| Freshness | N/A |
| Fallback | `null` (component omitted). UI shows "Not instrumented". |
| Redaction | N/A |

### Error rate (`ErrorRateSummary`) -- **unavailable**

| Attribute | Value |
|-----------|-------|
| Source | None honest. Application error telemetry not instrumented; audit log lacks correlation IDs. |
| `total_errors` | `null` (not `0`). |
| `error_classes` / `top_routes` | `[]` -- require `sample_correlation_ids`. |
| `top_tenants` | `null` -- identity-only operator has no cross-tenant scope. |
| `unavailable_reason` | **NEW (P14-B):** surfaced so the UI can state why. Value: `"Request error telemetry is not instrumented; correlation IDs are required for class/route breakdown."` |
| Freshness | `generated_at` = request time. |
| Redaction | N/A (no payloads). |

### Slow routes (`SlowRouteSummary`) -- **unavailable**

| Attribute | Value |
|-----------|-------|
| Source | None honest. Per-request latency telemetry not instrumented. |
| `total_slow_requests` | `null`. `routes` = `[]`. |
| `unavailable_reason` | **NEW (P14-B):** `"Per-request latency telemetry is not instrumented."` |
| Freshness | `generated_at` = request time. |
| Redaction | N/A. |

### Noisy neighbors (`NoisyNeighborSummary`) -- **unavailable**

| Attribute | Value |
|-----------|-------|
| Source | None honest. Requires cross-tenant business-activity telemetry (forbidden product scope). |
| `tenants` | `[]`. |
| `unavailable_reason` | **NEW (P14-B):** `"Cross-tenant activity telemetry is not available; requires business-scope instrumentation outside platform-runtime scope."` |
| Freshness | `generated_at` = request time. |
| Redaction | N/A. |

### System health (`GET /ops/health`) -- unchanged

Delegates to P10 `get_system_health` (currently a stub returning `unknown`/`None`).
P14 does not alter this endpoint; it remains honest about its stub state.

---

## Contract changes introduced by P14

Additive, backward-compatible optional fields (default `None`):

- `ErrorRateSummary.unavailable_reason: Optional[str]`
- `SlowRouteSummary.unavailable_reason: Optional[str]`
- `NoisyNeighborSummary.unavailable_reason: Optional[str]`

These let the frontend state *why* a signal is unavailable (P14-C requirement)
without changing any existing field semantics. `extra="forbid"` is preserved on
input; the new fields are declared, not extra.

No new dependencies, no migrations, no tenant/business paths, no mutation
endpoints.

---

## Risk

| Area | Risk | Mitigation |
|------|------|------------|
| DB ping on each `/ops/resources` call | LOW -- trivial `SELECT 1`, read-only, identity-only audience | One query/request; same cost as any health check |
| Pool introspection fragility | LOW -- best-effort, falls back to `null` | Defensive parse; `null` preserves honest semantics |
| Audit-log access-denied mislabel as "error rate" | AVOIDED -- kept `unavailable` | Principle #1: no fabricated/mislabeled signals |

## Blockers

None. Fields without a safe real source are explicitly documented as
`unavailable` with a reason -- this is the intended, honest P14 outcome.
