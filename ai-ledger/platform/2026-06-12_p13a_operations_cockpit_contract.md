# P13-A Operations Observability Cockpit Contract Ledger

**Date:** 2026-06-12
**Branch:** `codex/platform-p13a-operations-cockpit-contract-2026-06-12`
**Base:** `origin/platform-dev` at `51cfb41` (P12-D merge)
**A commit:** `fbdd9f0` (initial contract)
**R1 commit:** pending
**Status:** Contract/design/test-plan only -- no runtime code, no migrations, no API handlers, no frontend UI.

---

## Commit Chain

| # | Hash | Description |
|---|------|-------------|
| 1 | `fbdd9f0` | Initial P13-A contract, README update, ledger |
| 2 | pending | P13-A-R1: role model fix, unknown semantics fix, PRD alignment fix, ledger update |

## P13-A Deliverables

| # | File | Action |
|---|------|--------|
| 1 | `docs/ai/PLATFORM_PRODUCT_P13_OPERATIONS_COCKPIT_CONTRACT.md` | New -- P13 operations cockpit contract (605 initial, +R1 edits) |
| 2 | `docs/ai/README.md` | Modified -- add P13 to Platform Product Track read order (+3) |
| 3 | `ai-ledger/platform/2026-06-12_p13a_operations_cockpit_contract.md` | New -- this ledger |

## R1 Fixes Applied

### 1. Role Model Consistency

**Problem:** Contract granted engineering_operator and support_operator permissions in the matrix, test plan, and audit fields, but P13-B enforces identity-only super_admin only (matching P12-B implementation pattern).

**Fix:**
- Personas: engineering_operator and support_operator marked as **Deferred** with explicit "requires auth/RBAC gate" notes.
- Permission matrix: Split into P13-B active table (super_admin only) and Deferred Role Matrix (post-auth gate).
- Audit `actor_role`: Always `"super_admin"` in P13-B.
- AC/CE/test plan: Updated to deny any non-super_admin role.
- Counterexamples reference "any non-super_admin role" instead of named deferred roles.

### 2. Unknown/Unavailable Data Semantics

**Problem:** `ErrorRateSummary.total_errors` and `SlowRouteSummary.total_slow_requests` were `NOT NULL integer`, but telemetry source map showed they could be unavailable. Source map fallback said `0 with source_status: "unavailable"` which contradicts the core principle "unknown is not healthy."

**Fix:**
- Added `source_status` enum (`available | unavailable | unknown`) to both ErrorRateSummary and SlowRouteSummary.
- Changed `total_errors` and `total_slow_requests` from `NOT NULL integer` to `NULLABLE integer`.
- Source map fallback: `null` when `source_status` is not `"available"` (not `0`).
- Added explicit semantics: `null` = "we don't know" vs `0` = "we measured zero."
- Added counterexamples: source_status must be consistent with total (available + null = invalid; unavailable + 0 = misleading).
- Updated AC-07 to reference `null` with `source_status: "unavailable"`.

### 3. PRD/Roadmap Phase Alignment

**Problem:** References listed "PLATFORM_PRODUCT_PRD.md -- P13 feature definitions" but the PRD predates P13 scoping. No note explaining current platform-dev state.

**Fix:**
- Added "Phase Realignment Note" section documenting: current platform-dev state, P13's relationship to PRD (overall vision, not P13-specific spec), and role model alignment with P12 pattern.
- Qualified PRD reference: "Overall platform product vision (P13 scope comes from ROADMAP, not PRD)."

## P13 Scope

P13 adds system-wide and tenant-aware operational observability to the platform cockpit:

- System health overview (extends P10 SystemHealth with error rates, slow routes, resource indicators)
- Error rate analysis (aggregated error counts by class, route, tenant)
- Slow route analysis (routes exceeding latency thresholds)
- Resource health summary (DB pools, queue depth, CPU/memory/disk)
- Noisy-neighbor detection (tenants with disproportionate resource consumption)
- Tenant-scoped operational views

## P13 Principles

- Read-only. Only writes are audit events.
- No new observability infrastructure.
- No raw sensitive payloads.
- Unknown is not healthy. `null` != `0`.
- Identity-only super_admin enforcement in P13-B (P11-B0-R1).

## Data Contracts Defined

| Contract | Purpose | Key R1 Change |
|----------|---------|---------------|
| `ErrorRateSummary` | Aggregated error counts by class, route, and tenant | Added `source_status`; `total_errors` nullable |
| `SlowRouteSummary` | Routes exceeding latency thresholds with p50/p95/p99 | Added `source_status`; `total_slow_requests` nullable |
| `ResourceHealthSummary` | DB, queue, CPU, memory, disk health | Unchanged |
| `NoisyNeighborSummary` | Tenants with disproportionate error rates and slow routes | Unchanged |
| `OpsAuditEvent` | Extends PlatformAuditEvent with P13 ops-specific fields | `actor_role` always super_admin in P13-B |

## Permission Matrix (P13-B Active)

| Role | All P13 Views |
|------|---------------|
| super_admin (identity-only) | Allow + audit |
| any other role | Deny |

## Validation

| Check | Result |
|-------|--------|
| `git diff --check` | PASS |
| Non-ASCII scan | 0 hits |
| Forbidden path audit | PASS (0 hits) |
| GitNexus analyze | PASS |
| GitNexus detect_changes | LOW risk, docs-only |
| No backend changes | CONFIRMED |
| No frontend changes | CONFIRMED |
| No package/dependency changes | CONFIRMED |
| No auth/RBAC/session/tenancy/payment changes | CONFIRMED |

## Forbidden Path Audit

| Path Pattern | Files Found | Status |
|---|---|---|
| `backend/` | 0 | PASS |
| `migrations/` | 0 | PASS |
| `.github/` | 0 | PASS |
| `.claude/` | 0 | PASS |
| `product-dev-recovered/` | 0 | PASS |

## Risk

| Factor | Rating | Notes |
|--------|--------|-------|
| Scope | DOCS-ONLY | Contract doc edits, README update, ledger |
| Backend impact | NONE | No backend files |
| Frontend impact | NONE | No frontend files |
| Dependency changes | NONE | No package changes |

**Overall risk: NONE.** Documentation-only changes.

## Blockers

None. All gates passed.

## P13-A Entry Checklist (for P13-B gate)

- [x] P13-A contract document created
- [x] P13-A-R1 consistency fixes applied (role model, unknown semantics, PRD alignment)
- [x] P13-A ledger created and updated
- [x] README.md updated with P13 read order entry
- [x] Data contracts reviewed against P10-A and P12 for consistency
- [x] Redaction policy reviewed against security boundary
- [x] Permission matrix reviewed against P11-B0-R1
- [x] No runtime code changes (docs/ledger only)
- [x] Forbidden path audit clean
- [ ] CTO/product owner acceptance (pending)
- [ ] Merge to platform-dev (pending acceptance)
