# P15-B Incident Triage Snapshot API -- Ledger

**Date:** 2026-06-14
**Branch:** `codex/platform-p15bcd-incident-triage-batch-2026-06-14`
**Base:** `5bbd75c` (origin/platform-dev -- P15-A contract merge)
**HEAD:** Final pushed branch HEAD externally verified after push.
**Author:** Codex (Claude worker)

---

## Summary

P15-B implements the read-only incident triage snapshot API defined in the P15-A
contract. A single GET endpoint aggregates existing P10/P13/P14 read-only
sources into an `IncidentTriageSnapshot` with graceful degradation, redaction,
and full unknown/unavailable/null semantics. No business/domain writes, no
repair/write endpoints, no migrations, no new data sources, no auth/RBAC changes.

**Read-only definition (P15-R1 clarification):** "read-only" means **no
business/domain mutation and no repair/write endpoints**. P15-B does append
best-effort **platform audit** entries on access-denied and successful reads,
matching the existing P13/P10 platform-audit pattern. These audit entries are
not business/domain writes; their metadata is redaction-safe (view_type,
actor_role, scope, path, code/reason only -- no payloads, credentials, or
business fields).

---

## Modified Files

- `backend/api/v1/platform/p15/__init__.py` -- new package
- `backend/api/v1/platform/p15/schemas.py` -- 5 contract models
  (IncidentSignal, IncidentClassification, IncidentRunbookHint,
  IncidentTriageSnapshot, IncidentHandoffSummary)
- `backend/api/v1/platform/p15/services.py` -- snapshot/handoff assembly,
  graceful degradation, doc-driven runbook hints
- `backend/api/v1/platform/p15/routes.py` -- GET-only endpoint + P10 guard +
  best-effort access-denied/view audit
- `backend/api/app.py` -- register P15 router (2 lines)
- `backend/tests/test_platform_p15_incident_triage.py` -- 31 tests
- `ai-ledger/platform/2026-06-14_p15b_incident_triage_api.md` -- this ledger

---

## Endpoint

`GET /api/v1/platform/p15/incidents/triage/snapshot`
- P10 identity-only platform operator guard (tenant-contextual denied).
- Aggregates: P14 `_database_health` (live probe), P10 system/tenant summaries
  (counts/status only), P13 ops summaries (source_status + reasons).
- graceful_degraded=true on any single source failure; never 500, never fabricated.
- GET-only; POST/PUT/PATCH/DELETE rejected (405).

---

## Checks

- `git diff --check` -- clean.
- P15-B tests: **31 passed** (schemas, shape, source_status semantics,
  permissions incl. tenant-contextual denied, redaction, graceful degraded,
  GET-only, P15-A counterexamples, P15-R1 DB-source-failure contract).
- Regression: P13 64 + P10 137 + P12 62 = **263 passed**, 0 failed.
- non-ASCII scan on new code/ledger: 0 hits.
- Forbidden path audit: only `backend/api/v1/platform/p15/`, `backend/api/app.py`,
  `backend/tests/`, `ai-ledger/platform/` touched.

---

## GitNexus

- `npx gitnexus analyze` -- index current: **6,548 nodes, 19,697 edges, 424
  clusters, 300 flows**.
- detect_changes (repo `platform-p15bcd-incident-triage-batch-2026-06-14`, base
  `origin/platform-dev`): **changed_files 17, changed_symbols 116,
  affected_processes 15, risk_level HIGH**.
- Risk explanation: **HIGH by graph** because P15 adds platform runtime API flows
  (new symbols/processes on the platform operations surface). **Mitigated to
  MEDIUM operational** because scope is platform-only, read-only, identity-only
  super_admin guarded, no product business mutation, no migrations, no auth/RBAC
  rewrite.

---

## Security / Redaction

- identity-only super_admin required; tenant-contextual denied (tested).
- No credentials/DSN/host/port/raw `pool.status()`/tenant business records.
- Redaction is structural (upstream models already allowlisted; handoff
  `redacted=true`, `sensitive_keys_dropped=0`).
- Support-operator narrower scope: **deferred** -- the current platform guard
  grants identity-only super_admin only; there is no distinct support-operator
  read-scope enforcement to wire in P15-B without fabricating permission. The
  contract records this; P15-B does not fake a narrower support scope.

---

## Risk

MEDIUM operational (HIGH by graph, mitigated). New read-only platform module; no
schema/auth/migration/business changes. graceful_degraded ensures source failures
degrade honestly. See GitNexus detect_changes evidence above for the graph-level
HIGH classification and mitigations.

---

## Blockers

None. (Support-operator narrower scope deferred per contract -- not faked.)
