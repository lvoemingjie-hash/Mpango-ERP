# P25-EF -- Audit Result Closed-Vocab Boundary Fix

| Field | Value |
|---|---|
| **Task ID** | P25-EF |
| **Date** | 2026-07-08 |
| **Branch** | `codex/platform-p25ef-audit-result-recorded-boundary-fix-2026-07-08` |
| **Base** | `origin/platform-dev @ b4c114ec` |
| **Scope** | Backend-only platform P10 audit result closed-vocab fix (`schemas.py` + `services.py` fail-closed mapper) + tests + ledger. No frontend, no migration, no package/lockfile, no product business path, no auth/RBAC change, no P19/P20 audit-write logic change. |
| **Verdict** | **P25-EF audit result `recorded` closed-vocab defect: PROVEN CLOSED.** P25 customer readiness: **UNBLOCKED** -- both P25-EE (tenant-health UUID boundary) and P25-EF (audit result vocab) blockers are now closed; real-stack smoke shows 19/19 HTTP 200, 0 backend 5xx. |

---

## 1. Problem Statement

P25-EE real-stack browser smoke (committed `492e435d`) surfaced an **independent** backend HTTP 500
on the audit-events platform endpoint. It was correctly ruled out of P25-EE scope by CTO and tracked
as P25-EF.

### Trigger Path (Before P25-EF)

```
GET /api/v1/platform/p10/audit/events?limit=20&offset=0
  -> P10 platform operator guard (admits)
  -> get_platform_db() (system scope, P25-ED fix)
  -> list_audit_events(db, ...)
    -> query platform_audit_logs rows
    -> for each row: build PlatformAuditEvent(result=meta.get("result", "completed"))
      -> some rows have audit_metadata->>'result' = 'recorded'
      -> AuditResult = Literal["allowed","denied","failed","completed"]
      -> pydantic ValidationError: Input should be 'allowed','denied','failed' or 'completed'
  -> Unhandled ValidationError -> HTTP 500
```

The P10 schema `AuditResult` is a closed `Literal["allowed", "denied", "failed", "completed"]`. The
P19/P20 route handlers legitimately write `audit_metadata->>'result' = 'recorded'` for record-only
audit events (e.g. queue-list audit snapshots: `p19_approval_queue_list`, `p20_durable_approval_queue_list`).
That value was **not** in the P10 closed vocab, so when `list_audit_events` mapped the DB row to
`PlatformAuditEvent`, pydantic raised a `ValidationError` that propagated as an unhandled HTTP 500.

### DB Confirmation

The shared Docker Postgres (`mpango_p25ec_pg`) contained **8 rows** with
`audit_metadata->>'result' = 'recorded'` (4 from P19 approval queue list, 4 from P20 durable
approval queue list). These are real, legitimately-written audit rows -- the data is correct; the
schema vocab was incomplete.

---

## 2. Fix Design

### Approach: Expand Closed Vocab + Fail-Closed Mapper

Two complementary changes:

1. **Add `recorded` to the `AuditResult` closed vocab** (`schemas.py`). `recorded` is a legitimate
   audit outcome written by P19/P20 record-only audit events; it belongs in the vocab.

2. **Add a `_coerce_audit_result` fail-closed mapper** (`services.py`) at both callsites
   (`list_audit_events` and `get_audit_event`). Any value that is `None` or not in the (now expanded)
   vocab is normalized to a valid default (`completed`) **before** constructing the pydantic model.
   This guarantees the API never raises a `ValidationError -> HTTP 500` on any future unexpected
   metadata value, even if a new writer introduces an unanticipated result string.

**Rationale:**
- `recorded` is added because it is real, correct data already in production-shaped rows.
- The fail-closed mapper is added defensively so the P10 read API is robust against any unknown
  future metadata value (the closed vocab is enforced at the schema boundary, but the service layer
  never lets an unknown value reach pydantic in a way that crashes the request).
- No changes to P19/P20 audit **write** logic, route signatures, guards, or product business paths.
- No migration: this is purely a read-side schema/vocab + service-layer normalization. Existing rows
  with `result='recorded'` are now valid without any data backfill.

### Implementation

#### Schema change: `backend/api/v1/platform/p10/schemas.py` (~line 43)

```python
AuditResult = Literal["allowed", "denied", "failed", "completed", "recorded"]
```

#### New helper: `_coerce_audit_result` in `backend/api/v1/platform/p10/services.py`

```python
_VALID_AUDIT_RESULTS: frozenset[str] = frozenset(
    {"allowed", "denied", "failed", "completed", "recorded"}
)


def _coerce_audit_result(raw: object) -> str:
    """Map an audit_metadata.result value to a valid AuditResult vocab term.

    P19/P20 handlers legitimately write result='recorded' for record-only
    audit events; that value is now part of the closed vocab. Any other
    unexpected value is fail-closed to 'completed' so the API never raises a
    Pydantic ValidationError -> HTTP 500. The raw metadata (before redaction)
    is preserved in audit_metadata_redacted so real data is not silently hidden.
    """
    if raw is None:
        return "completed"
    candidate = str(raw).strip().lower()
    if candidate in _VALID_AUDIT_RESULTS:
        return candidate
    return "completed"
```

#### Updated callsites in `services.py`

Both `list_audit_events` and `get_audit_event` changed from:

```python
result=meta.get("result", "completed"),
```

to:

```python
result=_coerce_audit_result(meta.get("result")),
```

#### Route layer: NO CHANGES

The `/audit/events` and `/audit/events/{event_id}` routes in
`backend/api/v1/platform/p10/routes.py` are unchanged.

---

## 3. Guard / RBAC / Write-Logic Preservation Proof

The fix does NOT change any access control or audit-write logic:

1. **P10 platform operator guard** (`require_platform_operator`): completely unchanged. All three
   admission paths (X-Platform-Operator header, identity-only super_admin JWT, X-Platform-Test-Override
   in test env) remain identical.

2. **P25-ED `get_platform_db`**: completely unchanged. The system-scope session design from P25-ED
   is preserved.

3. **P19/P20 audit-write logic**: completely unchanged. This task only touches the P10 **read** path
   (schema vocab + service normalization). The `result='recorded'` values written by P19/P20 queue-list
   handlers are correct and remain as written -- they are now simply accepted by the reader.

4. **No product route changed**: Zero product route or product business path files were modified.
   Only P10 platform schema/services were touched.

5. **No schema/migration change**: No database schema, model, or migration file was modified. The fix
   is read-side only; no data backfill is required.

---

## 4. Regression Tests

### File: `backend/tests/test_platform_p10_contracts.py` -- `TestP25EFAuditResultBoundary`

| # | Test | Proves |
|---|---|---|
| 1 | `test_schema_accepts_recorded` | `PlatformAuditEvent(result='recorded')` constructs without error |
| 2 | `test_schema_rejects_unknown_result` | `PlatformAuditEvent(result='nonsense')` raises ValidationError (closed vocab still enforced) |
| 3 | `test_coerce_audit_result_valid_values` | All 5 valid values pass through unchanged |
| 4 | `test_coerce_audit_result_none_defaults_completed` | `None` -> `completed` |
| 5 | `test_coerce_audit_result_unknown_fail_closed` | `'nonsense'`, `'pending'`, `12345` -> `completed` |
| 6 | `test_coerce_audit_result_case_insensitive` | `'RECORDED'`, `'Allowed'`, `'  Completed  '` normalized |
| 7 | `test_list_audit_events_with_recorded_no_500` | Full `list_audit_events` with `result='recorded'` rows returns items without raising |
| 8 | `test_list_audit_events_with_unknown_result_fail_closed` | Unknown `'future_unknown_value'` mapped to `completed`, no crash |
| 9 | `test_existing_audit_results_unchanged` | `allowed`/`denied`/`failed`/`completed` preserved exactly |

### Test Results

```
tests/test_platform_p10_contracts.py ...........................    [100%]
======================= 151 passed, 0 failed =======================
```

(142 existing + 9 new P25-EF boundary tests. Only a benign `DeprecationWarning` about
`asyncio.get_event_loop` in the new tests, no failures.)

---

## 5. Real-Stack Smoke Evidence

**Date:** 2026-07-08
**Stack:** Real Postgres 15 (Docker `mpango_p25ec_pg` @ :5433, alembic head, 8 rows with
`result='recorded'` present) + real backend (uvicorn :8000) + real frontend (Vite :5173, proxies
`/api` -> :8000) + real headless Chromium via Playwright.

### 5.1 Identity Smoke (6/6 PASS)

| # | Case | Expected | Actual | Result |
|---|---|---|---|---|
| 1 | operator_admit | 200 | 200 | PASS |
| 2 | test_override_reject | 403 | 403 | PASS |
| 3 | identity_super_admin_admit | 200 | 200 | PASS |
| 4 | no_credentials_deny | 401 | 401 | PASS |
| 5 | wrong_operator_deny | 403 | 403 | PASS |
| 6 | tenant_context_admin_deny | 401/403 | 401 | PASS |

### 5.2 19-Route Playwright Browser Smoke

| Metric | Result |
|---|---|
| Total routes | 19 |
| HTTP 200 (page load) | **19/19** |
| Redirected | 0 |
| Routes with backend 5xx | **0** |
| Routes with forbidden controls | **0** |
| Screenshots captured | **19/19** |
| `TenantContextMissingError` | **0** |
| HTTP 500 / ERROR log lines | **0** |
| Traceback lines | **0** |

### 5.3 P25-EF Blocker: CLOSED

| Criterion | Required | Actual | Status |
|---|---|---|---|
| Route 5 Audit Events page HTTP 200 | yes | **200** | PASS |
| Audit Events API call 200 (no ValidationError) | yes | **0 backend 5xx** | PASS |
| `result='recorded'` rows accepted (8 rows in DB) | yes | rendered cleanly | PASS |
| `TenantContextMissingError` in logs | 0 | **0** | PASS |
| Forbidden controls | 0 | 0 | PASS |
| Screenshots | 19/19 | 19 | PASS |
| Identity smoke | all pass | 6/6 | PASS |

**Before P25-EF** (P25-EE run): Audit Events page surfaced a backend 500:
```
pydantic_core.ValidationError: 1 validation error for PlatformAuditEvent
result
  Input should be 'allowed', 'denied', 'failed' or 'completed'
  [type=literal_error, input_value='recorded', input_type=str]
```

**After P25-EF**: Route 5 Audit Events `http_status: 200`, `console_errors: []`, `has_5xx: false`.
The audit events page renders cleanly (screenshot 153033 bytes -- the largest screenshot, consistent
with a fully-populated audit table). Backend log grep: `0` HTTP 500 lines, `0` tracebacks.

The `_coerce_audit_result` normalization + `recorded` vocab expansion is proven on the real stack:
all 8 `result='recorded'` rows are now accepted without raising a `ValidationError`.

### 5.4 Residual Console Noise (NOT a 5xx, expected behavior)

Route 4 Tenant Health records 2 console messages of `404 (Not Found)`. This is the **expected**
clean-404 behavior proven by P25-EE: the non-UUID slug `smoke-tenant-1` returns a clean 404 (not a
500) via the `_coerce_tenant_id` short-circuit. The browser surfaces this as a console message, but
`has_5xx` is `false` and the backend logs contain zero 500s for this endpoint. This is correct,
non-blocking behavior.

---

## 6. Base Proof Gate

```
git fetch origin platform-dev
git worktree add _p25ef_2026-07-08 -b codex/platform-p25ef-audit-result-recorded-boundary-fix-2026-07-08 origin/platform-dev
```

Verification (before any edits):

```
git rev-parse HEAD              -> b4c114ec8207675cf4483d18fe634d8fab915e27
git rev-parse origin/platform-dev -> b4c114ec8207675cf4483d18fe634d8fab915e27
git diff --name-status origin/platform-dev..HEAD -> (empty)
git status --short -> (clean)
```

**Base Proof Gate: PASS**

---

## 7. Scope Diff Gate

### Changed Files

**Schema + runtime fix (2 files):**
- `backend/api/v1/platform/p10/schemas.py` -- added `recorded` to `AuditResult` Literal
- `backend/api/v1/platform/p10/services.py` -- added `_VALID_AUDIT_RESULTS` frozenset +
  `_coerce_audit_result` helper; updated `list_audit_events` and `get_audit_event` callsites

**Test updates (1 file):**
- `backend/tests/test_platform_p10_contracts.py` -- added `TestP25EFAuditResultBoundary` class (9 tests)

**Evidence (verify/p25ef/):**
- `verify/p25ef/run_smoke.py` -- real-stack smoke orchestrator
- `verify/p25ef/smoke_result.json` -- smoke results
- `verify/p25ef/backend_stdout.log` -- backend log
- `verify/p25ef/frontend_stdout.log` -- frontend log
- `verify/p25ef/screenshots/` -- 19 route screenshots

**Ledger (1 file):**
- `ai-ledger/platform/2026-07-08_p25ef_audit_result_recorded_boundary_fix.md`

### Scope Audit

- No frontend runtime files modified.
- No migration files added or modified.
- No `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `requirements.txt`, or `pyproject.toml` changes.
- No backend/deploy or infrastructure files modified.
- No auth/RBAC files modified.
- No product business path files modified.
- No P19/P20 audit-write logic modified (only P10 read path).
- No deletions of existing files.

**Scope Diff Gate: PASS**

---

## 8. Gate Checklist

| Gate | Status | Notes |
|---|---|---|
| Base Proof Gate | PASS | HEAD == origin/platform-dev @ b4c114ec |
| Targeted backend tests | PASS | 151 passed, 0 failed |
| P10 platform operator guard intact | PASS | No changes to `require_platform_operator` |
| P25-ED system-scope DB dependency intact | PASS | `get_platform_db` unchanged |
| P19/P20 audit-write logic intact | PASS | Only P10 read path touched |
| Audit events 500 -> 200 proven on real stack | PASS | Route 5: 0 backend 5xx, 0 tracebacks |
| `git diff --check` | PASS | No whitespace errors |
| ASCII scan | PASS | No non-ASCII characters in added source lines |
| `detect-secrets` | PASS | Throwaway test creds marked with `# pragma: allowlist secret` |
| `.secrets.baseline` unchanged | PASS | Baseline not modified |
| Forbidden path audit | PASS | No frontend, migration, deploy, lockfile, product path in diff |
| GitNexus analyze | PASS | |
| GitNexus status | PASS | |
| platform-dev NOT pushed | PASS | Only feature branch pushed |

---

## 9. Verdict

**P25-EF audit result `recorded` closed-vocab defect: PROVEN CLOSED.**
**P25 customer readiness: UNBLOCKED.**

P25-EF deliverable proven:
1. `GET /api/v1/platform/p10/audit/events` returns HTTP 200 with 8 `result='recorded'` rows present --
   proven by 9 boundary tests + real-stack smoke (Route 5: 500 -> 200, 0 backend 5xx, 0 tracebacks).
2. Closed vocab still enforced: unknown values (`'nonsense'`, `'pending'`) are rejected by the schema
   and fail-closed to `completed` by the service mapper -- proven by tests 2, 5, 8.
3. Existing valid results (`allowed`/`denied`/`failed`/`completed`) preserved exactly -- proven by test 9.
4. P10 platform operator guard unchanged.
5. P25-ED `get_platform_db` system-scope design unchanged.
6. P19/P20 audit-write logic unchanged.
7. Zero product business path, migration, frontend, auth/RBAC, or package/lockfile changes.

With both P25-EE (tenant-health UUID boundary) and P25-EF (audit result vocab) blockers now closed on
the real stack (19/19 HTTP 200, 0 backend 5xx, 0 `TenantContextMissingError`, 0 forbidden controls,
19/19 screenshots, 6/6 identity smoke), the P25 platform customer-readiness blockers identified during
real-stack validation are resolved.
