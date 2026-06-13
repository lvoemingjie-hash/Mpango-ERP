# P14 Operations Cockpit — Real Signals Integration Readiness

**Date:** 2026-06-13
**Branch:** `codex/platform-p14-operations-real-signals-2026-06-13`
**Base:** `41181fc` (origin/platform-dev — P13 batch merge)
**HEAD:** Final pushed branch HEAD is externally verified by CTO/reviewer after push.
**Pre-R5 evidence commit:** `9a6d475`
**Author:** Codex (Claude Opus 4.8)

---

## Summary

P14 turns the P13 safe API/UI skeleton into a more useful **read-only** operations
cockpit by wiring the one **safe, honest real signal** available today — measured
**database health** (ping latency + engine pool stats + threshold status) — while
preserving the `unknown != healthy` and `null != 0` fallback semantics.

Error rate, slow routes, and noisy neighbors have **no honest real source** on
platform-dev (no correlation IDs, no latency telemetry, no cross-tenant business
data), so they stay `unavailable` and now carry an `unavailable_reason` so the UI
states *why*. This is the intended P14 outcome — real signal where honest,
documented unavailability everywhere else.

P14 is **platform-runtime scope only**. No backend product/tenant code, no
migrations, no auth/RBAC rewrite, no payment/billing, no write endpoints, no
dependency/lockfile changes.

---

## Stages

- **P14-A** — Source contract ledger
  (`ai-ledger/platform/2026-06-13_p14_operations_real_signals_source_contract.md`):
  per-field source/fallback/freshness/redaction map; documents why most fields
  stay unavailable.
- **P14-B** — Backend real database-health adapter + tests.
- **P14-C** — Frontend surfaces source_status/freshness/unavailable reason;
  fixes a latent loading-state bug so content actually renders.
- **P14-D** — This readiness packet.

---

## Commit Chain (P14)

| Commit | Message |
|--------|---------|
| `9a6d475` | feat(platform): P14-C surface real/unavailable signals in ops UI |
| `2b87503` | feat(platform): P14-B real database health signal adapter |
| `849c9fb` | docs(platform): P14-A real signals source contract |

(Branched from `41181fc` = origin/platform-dev P13 merge. Not merged into platform-dev.)

---

## Modified Files (all in allowed P14 scope)

Backend (3):
- `backend/api/v1/platform/p13/schemas.py` — additive optional `unavailable_reason` on ErrorRateSummary, SlowRouteSummary, NoisyNeighborSummary
- `backend/api/v1/platform/p13/services.py` — real `_database_health` adapter (ping + pool parse), `unavailable_reason` population; removed unused P10 stub call
- `backend/tests/test_platform_p13_operations_cockpit.py` — updated 3 fabricated-`unknown` tests to measured-health; +10 P14-B tests

Frontend (6):
- `frontend/src/types/platformOps.ts` — optional `unavailable_reason` on 3 summaries
- `frontend/src/types/__tests__/platformOps.test.ts` — optional-field coverage
- `frontend/src/pages/platform/ops/OpsErrorsPage.tsx` — surface reason + loading fix
- `frontend/src/pages/platform/ops/OpsSlowRoutesPage.tsx` — surface reason + loading fix
- `frontend/src/pages/platform/ops/OpsNoisyNeighborsPage.tsx` — surface reason + loading fix
- `frontend/src/pages/platform/ops/OpsResourcesPage.tsx` — "Live probe" badge + loading fix
- Frontend page tests (3) updated

Ledger (2): P14-A source contract, this P14-D readiness packet.

---

## Tests

- **Backend P13:** all passing, incl. 10 new P14-B tests (real ping, unhealthy
  fallback, pool-status parsing, no-sensitive-payload, unavailable_reason
  surfaced, read-only). Exact counts are captured in merge readiness gate output.
- **Backend P10/P12 regression:** all passing (no regressions).
- **Frontend:** all passing, incl. new real/available/unavailable-state tests.
- Combined gate total recorded at merge readiness (per R6 count-deferral policy).

---

## GitNexus

- `npx gitnexus analyze` — index current; exact node/edge/cluster/flow counts are
  captured in merge readiness gate output (per P13-D-R6 count-deferral policy).
- Impact analysis (manual; GitNexus MCP tools not in this toolset): each modified
  P13 service function has exactly one caller (its route handler) — internal /
  additive changes, LOW risk, no HIGH/CRITICAL product-business risk.
- Any HIGH/CRITICAL is **platform-runtime batch scope, mitigated; not product
  tenant business risk** (read-only platform ops cockpit).

---

## Forbidden Path Audit

- `git diff --check origin/platform-dev..HEAD` — no whitespace errors
- No `product-dev-recovered`, `.github`, `.claude`, `migrations/`, `alembic`,
  payment, billing, auth/RBAC rewrite, or tenant-business paths touched
- No write/mutation endpoints added (all endpoints remain GET-only)
- No dependency/lockfile changes (`pnpm install --frozen-lockfile` only)
- `Detect secrets` pre-commit hook — Passed (all commits)

---

## Risk Assessment

| Area | Risk | Mitigation |
|------|------|------------|
| Real DB ping per /ops/resources call | LOW — trivial SELECT 1, read-only, identity-only audience | One query/request; standard health-check cost |
| Pool introspection fragility | LOW — best-effort, falls back to honest null | Defensive parse; null preserves semantics |
| Additive optional schema field | NONE — optional, default None | Existing clients/tests unaffected |
| Loading-state fix in ops pages | LOW — fixes latent bug, content now renders | Full frontend suite green |
| Frontend tests reused shared venv/node_modules | NONE — runtime-only, untracked | Not committed; no lockfile change |

---

## Blockers

None. Fields without a safe real source are explicitly documented as
`unavailable` with a reason — the intended, honest P14 outcome. P14 is not merged
into platform-dev (deferred to a separate merge-readiness gate).
