# P15-D Incident Triage Batch Readiness Packet

**Date:** 2026-06-14
**Branch:** `codex/platform-p15bcd-incident-triage-batch-2026-06-14`
**Base:** `5bbd75c` (origin/platform-dev -- P15-A contract merge)
**HEAD:** Final pushed branch HEAD externally verified by reviewer after push.
**Author:** Codex (Claude worker)

---

## Summary

P15-B/C/D implements the read-only Incident Triage surface defined in the P15-A
contract: a GET-only snapshot API (P15-B) aggregating P10/P13/P14 read-only
sources with graceful degradation and redaction, plus a read-only frontend view
(P15-C). No writes, no migrations, no auth/RBAC rewrite, no tenant business data.

This packet is **not** merged into platform-dev. It is pushed to the isolated
branch for CTO review.

---

## Commit Chain (P15-B/C/D + R1)

| Commit | Message |
|--------|---------|
| (P15-R1) | fix(platform): P15-R1 graceful degraded contract |
| (P15-D) | docs(platform): P15-D incident triage readiness packet |
| (P15-C) | feat(platform): P15-C incident triage frontend |
| (P15-B) | feat(platform): P15-B incident triage snapshot API |

Branched from `5bbd75c` (origin/platform-dev, post P15-A.1 merge).

### P15-R1 changes (CTO review fixes)

- **[P1] DB-failure graceful-degraded contract:** `build_triage_snapshot` now
  detects a P14 DB probe that represents a *failed source*
  (`status="unhealthy"`, `latency_ms is None`, all pool fields `None` -- the
  shape P14 returns when it swallows a ping exception). Such a probe is treated
  as an unavailable DB source: `graceful_degraded=true`, `unavailable_reason`
  names the DB probe, and the database signal is `source_status="unavailable"`
  with a visible reason. A *measured* unhealthy (latency present, critical) is
  NOT treated as a failed source. See the counterexample replay below.
- **[P2] Read-only / audit evidence correction (Option A):** kept the best-effort
  platform audit writes (consistent with P13/P10). Updated ledgers/docstrings to
  state: "read-only" means no business/domain mutation and no repair/write
  endpoints; best-effort platform audit entries may be appended. Audit metadata
  is redaction-safe (no payloads/credentials/business fields).
- **[P3] `IncidentSignal.observed_value` type:** backend schema now
  `Optional[Union[str, int]]`; frontend type `string | number | null`, matching
  the P15-A contract. Added schema/type tests proving integer observed values are
  accepted. No sensitive/business data.

---

## Modified Files

Backend (P15-B):
- `backend/api/v1/platform/p15/__init__.py` (new)
- `backend/api/v1/platform/p15/schemas.py` (new, 5 contract models)
- `backend/api/v1/platform/p15/services.py` (new, snapshot/handoff + graceful degradation)
- `backend/api/v1/platform/p15/routes.py` (new, GET-only + P10 guard + audit)
- `backend/api/app.py` (router registration)
- `backend/tests/test_platform_p15_incident_triage.py` (new, 26 tests)

Frontend (P15-C):
- `frontend/src/types/platformIncident.ts` (new)
- `frontend/src/types/__tests__/platformIncident.test.ts` (new)
- `frontend/src/services/platformApi.ts` (P15 method)
- `frontend/src/services/__tests__/platformOpsApi.test.ts` (P15 path test)
- `frontend/src/pages/platform/ops/IncidentTriagePage.tsx` (new)
- `frontend/src/pages/platform/ops/__tests__/IncidentTriagePage.test.tsx` (new)
- `frontend/src/router/AppRouter.tsx` (route under PlatformRoute guard)
- `frontend/src/components/layout/Sidebar.tsx` (link)

Ledger:
- `ai-ledger/platform/2026-06-14_p15b_incident_triage_api.md`
- `ai-ledger/platform/2026-06-14_p15c_incident_triage_frontend.md`
- `ai-ledger/platform/2026-06-14_p15d_incident_triage_batch_readiness.md` (this)

---

## Read-only definition (P15-R1 [P2] clarification)

"Read-only" in P15 means **no business/domain mutation and no repair/write
endpoints**. P15-B appends best-effort **platform audit** entries (access-denied
and successful read), matching the existing P13/P10 platform-audit pattern. These
are not business/domain writes; their metadata is redaction-safe (view_type,
actor_role, scope, path, code/reason -- no payloads, credentials, or business
fields). No contradiction remains.

## Counterexample Replay (P15-R1 [P1])

- **Counterexample (exact CTO case):** P10 system health and tenant summaries
  succeed; the DB ping raises (e.g. `db.execute` -> `RuntimeError`). P14
  `_database_health` swallows the ping error and returns
  `DatabaseHealth(status="unhealthy", latency_ms=None, connection_pool_active=None,
  connection_pool_idle=None, connection_pool_max=None)` instead of raising.
- **Pre-fix actual result (the bug):** P15 saw `status="unhealthy"`, treated the
  probe as a measured/available signal (`source_status="available"`), and left
  `graceful_degraded=false` with no DB unavailable reason -- violating the P15-A
  source-failure contract.
- **Expected result (contract):** `graceful_degraded=true`;
  `unavailable_reason` mentions the DB probe; the database signal
  `source_status != "available"` (it is `"unavailable"`) with a visible
  `unavailable_reason`; `database_probe` is None or its `latency_ms` is None
  (`null != 0`); HTTP 200 (no 500).
- **Post-fix actual result:** all expected conditions hold. Verified by
  `TestGracefulDegraded::test_db_source_failure_is_graceful_degraded_and_unavailable_unit`
  (service-level, P10 patched to success, only DB fails) and
  `TestGracefulDegraded::test_db_source_failure_is_graceful_degraded_route`
  (same case through `GET /api/v1/platform/p15/incidents/triage/snapshot`).
  P10-only source failures remain gracefully degraded
  (`test_p10_source_failures_still_graceful_degraded`).
- **Tests that cover it:**
  `test_db_source_failure_is_graceful_degraded_and_unavailable_unit`,
  `test_db_source_failure_is_graceful_degraded_route`,
  `test_p10_source_failures_still_graceful_degraded`,
  `test_snapshot_returns_200_with_reason_on_db_failure`,
  `test_db_probe_null_when_ping_fails`.

## Tests

- **P15-B backend:** 26 passed (schemas, shape, source_status semantics,
  permissions incl. tenant-contextual denied, redaction, graceful degraded,
  GET-only, P15-A counterexamples).
- **P15-C frontend:** 194 passed (22 files), incl. IncidentTriage page + type +
  service-path tests.
- **Regression:** P13 64 + P10 137 + P12 62 = 263 backend passed, 0 failed.
- Exact combined counts captured in merge readiness gate output (per the
  P13-D-R6 count-deferral policy).

---

## Checks

- `git diff --check origin/platform-dev..HEAD` -- no whitespace errors.
- Non-ASCII scan on new/changed ledger docs -- **0 hits** (ASCII-only).
- Forbidden path audit -- PASS (see below).
- `pnpm install --frozen-lockfile` -- no lockfile change, no new dependencies.
- Pre-commit hooks (trim trailing whitespace, end-of-file, detect-secrets, large
  files) -- passed on every commit.

---

## GitNexus

- `npx gitnexus analyze` -- index current; exact node/edge/cluster/flow counts are
  captured in the merge readiness gate output (per P13-D-R6 count-deferral policy).
- Impact: P15-B is a new self-contained read-only module that calls existing
  P10/P13/P14 read-only helpers; no existing symbols modified. P15-C is a new
  read-only page + types + service method. **LOW risk**.
- detect_changes vs origin/platform-dev: expected **LOW, platform-runtime scope**.
  Any HIGH/CRITICAL would be read-only ops flows only -> "CRITICAL by graph /
  MEDIUM mitigated platform-runtime, no product business risk."

---

## Forbidden Path Audit

PASS. Touched only:
- `backend/api/v1/platform/p15/`, `backend/api/app.py`, `backend/tests/`
- `frontend/src/{types,services,pages/platform/ops,router,components/layout}/`
- `ai-ledger/platform/`

No `product-dev-recovered`, `.github`, `.claude`, `migrations/`, `alembic`,
payment, billing, auth/RBAC/session rewrite, tenancy, or tenant business paths.
No write/mutation endpoints (GET-only). No lockfile change.

---

## Risk

LOW. Read-only triage surface; consumes existing helpers; graceful_degraded
ensures honest degradation on source failures; no schema/auth/migration/business
changes.

---

## Known Deferred Items

- **Support-operator narrower read scope:** the current platform guard grants
  identity-only super_admin only; there is no distinct support-operator read-scope
  enforcement to wire without fabricating permission. The contract records this;
  P15-B does not fake a narrower support scope. Deferred to a future
  permission-matrix change (separate approval).
- **No write/persistence for triage conclusions:** recording a conclusion note is
  contract-described as a labeled observation only; any persistence write is
  deferred to a separately-approved phase (P15-B is read-only by gate).

---

## Blockers

None. P15-B/C/D complete and gated; pushed to the isolated branch for CTO
review. Not merged into platform-dev.
