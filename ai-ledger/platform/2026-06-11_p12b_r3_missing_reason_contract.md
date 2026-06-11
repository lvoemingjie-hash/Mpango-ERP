# P12-B-R3 Missing Reason Contract Patch Ledger

**Date:** 2026-06-11
**Branch:** `codex/platform-p12b-r3-missing-reason-contract-2026-06-11`
**Base:** `origin/platform-dev` at `04a004a` (P12-B + R1 merge)
**R3 commit:** (pending)
**Status:** Missing/short reason returns 400 + support_access_denied audit

---

## Branch

- **Branch name:** `codex/platform-p12b-r3-missing-reason-contract-2026-06-11`
- **Base ref:** `origin/platform-dev` at `04a004a`

## Modified Files (3 total)

| # | File | Action |
|---|------|--------|
| 1 | `backend/api/v1/platform/p12/schemas.py` | **Modified** -- `CreateSessionRequest.reason` changed from required `str` with `min_length=10` to `Optional[str]`; validation moved to route layer |
| 2 | `backend/api/v1/platform/p12/routes.py` | **Modified** -- `create_session` adds manual reason validation before service call; writes `support_access_denied` audit for missing/short reason; returns 400 not 422 |
| 3 | `backend/tests/test_platform_p12_support_console.py` | **Modified** -- Updated schema tests; changed 422 expectations to 400; added 4 new R3 audit tests |

## R3 Changes

| Change | Detail |
|--------|--------|
| **Missing reason -> 400** | `body.reason is None or empty` returns 400 with `MISSING_REASON` code + `support_access_denied` audit |
| **Short reason -> 400** | `len(reason) < 10` returns 400 with `REASON_TOO_SHORT` code + `support_access_denied` audit |
| **Reason validation audit** | `_write_reason_denied_audit()` helper writes `support_access_denied` with `denial_type: invalid_reason` metadata |
| **Schema relaxation** | `CreateSessionRequest.reason` changed to `Optional[str]` -- min 10 char constraint enforced at route layer |
| **Guard unchanged** | `require_platform_operator_with_audit` still runs first; 401/403 for unauthenticated/insufficient access |

## Audit Actions (R3 addition)

| Condition | HTTP | Audit action | Metadata code |
|-----------|------|-------------|---------------|
| Reason missing/null/empty | 400 | `support_access_denied` | `MISSING_REASON` |
| Reason < 10 chars | 400 | `support_access_denied` | `REASON_TOO_SHORT` |
| Valid reason (>= 10 chars) | 201 | `support_session_start` | (existing) |

## Tests

### P12-B-R3: 62 passed, 0 failed

| Class | Count | Change |
|-------|-------|--------|
| TestSchemas | 7 | 2 updated: schema now accepts null/short reason (route enforces) |
| TestCreateSession | 6 | 2 updated: missing/short reason now expect 400 not 422 |
| TestGetDiagnostics | 3 | unchanged |
| TestCreateBundle | 6 | unchanged |
| TestCloseSession | 4 | unchanged |
| TestGuardEnforcement | 4 | unchanged |
| TestSessionExpiry | 2 | unchanged |
| TestCounterexamples | 5 | unchanged |
| TestReasonSanitization | 11 | unchanged |
| TestAccessDeniedAudit | 4 | unchanged |
| TestRouteLevelIdentity | 4 | unchanged |
| TestSessionExpiryAudit | 3 | unchanged |
| TestReasonContractPatch | **4 new** | missing reason 400+audit, short reason 400+audit, valid reason session_start, missing category still 422 |

### P10/P11 Regression: 137 passed, 0 failed
### Agent Gate: 62 passed
### Runner Gate: 6 passed
### Directive Gate: 23 passed

## GitNexus

### detect_changes compare origin/platform-dev

| Field | Value |
|-------|-------|
| risk_level | CRITICAL (platform runtime API) |
| Nodes | 6,217 |
| Edges | 18,468 |
| Clusters | 401 |
| Flows | 273 |

CRITICAL because this modifies platform runtime API behavior for reason validation. No product business code touched.

## Validation

| Check | Result |
|-------|--------|
| P12-B-R3 tests | **62 passed**, 0 failed |
| P10/P11 regression | **137 passed**, 0 failed |
| Agent mission gate | **62 passed** |
| Runner gate | **6 passed** |
| Directive gate | **23 passed** |
| `git diff --check` | PASS |
| Forbidden path audit | PASS (0 hits) |
| GitNexus analyze | PASS -- 6,217 nodes, 18,468 edges |

## Risk

| Factor | Rating | Notes |
|--------|--------|-------|
| Scope | **HIGH** | Changes reason validation from Pydantic (422) to route layer (400) + audit |
| Guard behavior | **LOW** | Guard unchanged -- still enforces identity-only super_admin |
| Audit coverage | **LOW** | Missing/short reason now audited as `support_access_denied` |
| Schema change | **LOW** | `reason` relaxed to Optional; constraint moved, not removed |

**Overall risk: HIGH mitigated by 62 tests.** No product business code, auth middleware, RBAC, tenancy, payment, or session management touched.

## Note: platform-dev Not Merged or Pushed

`platform-dev` was **not merged** and **not pushed** as part of R3. Only the isolated branch was pushed.

## Blockers

None. All gates passed.
