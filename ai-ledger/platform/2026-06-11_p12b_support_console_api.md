# P12-B Support Console API Ledger

**Date:** 2026-06-11
**Branch:** `codex/platform-p12b-support-console-api-2026-06-11`
**Base:** `origin/platform-dev` at `1ff8d3c` (P12-A merge)
**R1 commit:** (pending)
**Status:** P12-B + R1 complete -- request-scoped diagnostics, access-denied audit, reason sanitization, expiry audit

---

## Branch

- **Branch name:** `codex/platform-p12b-support-console-api-2026-06-11`
- **Base ref:** `origin/platform-dev` at `1ff8d3c`
- **Created from:** P12-A-R1 merge commit

## Base

- `origin/platform-dev` HEAD: `1ff8d3c merge: P12-A support console contract (A + R1)`

## Modified Files (7 total)

| # | File | Action |
|---|------|--------|
| 1 | `backend/api/v1/platform/p12/__init__.py` | **New** -- Package marker |
| 2 | `backend/api/v1/platform/p12/schemas.py` | **New** -- P12 Pydantic contract models |
| 3 | `backend/api/v1/platform/p12/services.py` | **New** -- In-memory session store, diagnostics, bundles, audit, reason sanitization, expiry tracking |
| 4 | `backend/api/v1/platform/p12/routes.py` | **New** -- 4 FastAPI endpoints with access-denied audit wrapper |
| 5 | `backend/api/app.py` | **Modified** -- P12 router registration (3 lines) |
| 6 | `backend/tests/test_platform_p12_support_console.py` | **New** -- 58 test cases (37 original + 21 R1 additions) |
| 7 | `ai-ledger/platform/2026-06-11_p12b_support_console_api.md` | **New** -- This ledger |

## R1 Changes Over P12-B

| Change | Detail |
|--------|--------|
| **support_access_denied audit** | `require_platform_operator_with_audit` wraps P10 guard; denied access (401/403) writes `support_access_denied` with actor_id null or extracted from auth context |
| **Reason sanitization** | `sanitize_reason()` strips credential-like patterns (password=, token:, api_key=, etc.) before storage in session and audit metadata |
| **Session expiry audit** | `SupportSessionStore._expired_queue` tracks lazily-expired sessions; `_audit_expired_sessions()` writes `support_session_expired` on next access attempt |
| **Route-level identity tests** | Tests for identity-only super_admin (allowed), tenant-contextual super_admin (denied), tenant user (denied), non-super_admin identity (denied) |
| **Non-ASCII cleanup** | All P12 source files are ASCII-only (box drawing U+2500 replaced with --) |
| **Ledger risk upgrade** | Risk rated HIGH (platform runtime API surface) mitigated by 58 tests |

## Endpoint List

| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| POST | `/api/v1/platform/p12/sessions` | Create support session (requires reason >= 10 chars) | 201 |
| GET | `/api/v1/platform/p12/sessions/{id}/diagnostics` | Get redacted diagnostics for active session | 200 |
| POST | `/api/v1/platform/p12/sessions/{id}/bundles` | Generate support bundle (full/technical/summary) | 201 |
| POST | `/api/v1/platform/p12/sessions/{id}/close` | Close support session | 200 |

## Contract Shape Mapping

| P12-A Contract | P12-B Schema | Source |
|----------------|-------------|--------|
| SupportReason | `CreateSessionRequest` | Request body |
| SupportSession | `SupportSession` | In-memory store |
| SupportBundle | `SupportBundle` | Generated from diagnostics |
| SupportDiagnosticItem | `SupportDiagnosticItem` | P10 services + redaction |
| SupportAuditEvent | `SupportAuditEventResponse` | Written via `append_audit_entry` |

## Audit Actions

| Action | Trigger | actor_id |
|--------|---------|----------|
| `support_session_start` | Session created | From auth context |
| `support_bundle_generated` | Bundle generated | From session |
| `support_session_end` | Session closed | From session |
| `support_session_expired` | Lazy TTL expiry detected on next access | From expired session |
| `support_access_denied` | Guard denies access (401/403) | Null if unauthenticated, or from auth context |

## Reason Sanitization

Patterns matched and replaced with `[REDACTED]`:
- `password=xxx`, `passwd=xxx`, `pwd=xxx`
- `token=xxx`, `token: xxx`
- `secret_key=xxx`, `secret=xxx`
- `api_key=xxx`, `api-key: xxx`
- `cookie=xxx`
- `card_number=xxx`
- `bearer=xxx`
- `authorization=xxx`

The keyword alone (e.g., "password reset failures") is preserved. Only key=value or key:value patterns are stripped.

## Tests

### P12-B-R1: 58 passed, 0 failed

| Class | Count | Coverage |
|-------|-------|----------|
| TestSchemas | 7 | Reason min_length, enums, extra fields, redaction_applied |
| TestCreateSession | 6 | Success, short reason, missing reason/category, no tenant, audit event |
| TestGetDiagnostics | 3 | Success, not found, unknown stays unknown |
| TestCreateBundle | 6 | Full/technical/summary, not found, audit event, redaction_applied |
| TestCloseSession | 4 | Success, not found, already closed, audit event |
| TestGuardEnforcement | 4 | No headers, wrong secret, test override, operator secret |
| TestSessionExpiry | 2 | Expired diagnostics 404, expired bundle 404 |
| TestCounterexamples | 5 | Sensitive keys redacted, raw payloads excluded, unknown!=healthy, null!=0, default bundle type |
| TestReasonSanitization | 11 | password/token/secret/api_key/cookie/bearer stripped, plain words preserved, stored session sanitized, audit metadata sanitized |
| TestAccessDeniedAudit | 4 | No headers writes audit, wrong secret writes audit, contextual super_admin denied writes audit, path metadata included |
| TestRouteLevelIdentity | 4 | Identity-only super_admin allowed, contextual super_admin denied, tenant user denied, non-super_admin identity denied |
| TestSessionExpiryAudit | 3 | Expired session writes expiry audit, expired bundle writes expiry audit, not-found does not write expiry audit |

### P10/P11 Regression: 137 passed, 0 failed

## GitNexus

| Field | Value |
|-------|-------|
| Nodes | 6,204 |
| Edges | 18,405 |
| Clusters | 404 |
| Flows | 270 |
| Impact (sanitize_reason) | LOW (1 caller: create_support_session) |
| Impact (require_platform_operator_with_audit) | LOW (0 upstream callers, route-level only) |

## Forbidden Path Audit

| Path Pattern | Files Found | Status |
|---|---|---|
| `frontend/` | 0 | PASS |
| `migrations/` | 0 | PASS |
| `product-dev-recovered/` | 0 | PASS |
| `.github/` | 0 | PASS |
| `.claude/` | 0 | PASS |
| auth/RBAC/session/tenancy/payment | 0 | PASS |

**Only backend/api/ and backend/tests/ files modified.**

## Validation

| Check | Result |
|-------|--------|
| P12-B-R1 tests | 58 passed, 0 failed |
| P10/P11 regression | 137 passed, 0 failed |
| `git diff --check` | PASS |
| Non-ASCII scan | 0 hits (all files ASCII-only) |
| Forbidden path audit | PASS |
| GitNexus analyze | PASS -- 6,204 nodes, 18,405 edges |
| GitNexus impact | LOW on all new R1 symbols |
| No frontend files changed | CONFIRMED |
| No migrations introduced | CONFIRMED |
| No auth/RBAC/session/tenancy/payment changes | CONFIRMED |

## Counterexamples Rejected

| # | Counterexample | Result |
|---|---------------|--------|
| CE-01 | Reason shorter than 10 chars | 422 PASS |
| CE-02 | Missing reason field | 422 PASS |
| CE-03 | Missing category field | 422 PASS |
| CE-04 | Bundle on non-existent session | 404 PASS |
| CE-05 | Bundle on expired session | 404 PASS |
| CE-06 | No auth headers | 401 PASS |
| CE-07 | Wrong operator secret | 403 PASS |
| CE-08 | redaction_applied=false rejected by schema | ValidationError PASS |
| CE-09 | Unknown metrics stay null/unavailable | PASS |
| CE-10 | Raw business payloads excluded by redaction | PASS |
| CE-11 | password=xxx in reason stripped before storage | PASS |
| CE-12 | token: xxx in reason stripped before storage | PASS |
| CE-13 | Plain "password reset" text preserved | PASS |
| CE-14 | Contextual super_admin denied (no platform headers) | 401 PASS |
| CE-15 | Tenant user denied | 401 PASS |

## Risk

| Factor | Rating | Notes |
|--------|--------|-------|
| Scope | **HIGH** | Platform runtime API surface under /platform/p12/ |
| Test coverage | **HIGH** | 58 P12 tests + 137 regression tests |
| Runtime impact | **LOW** | Reuses P10 guard and services, no existing code paths changed |
| Session storage | **LOW** | In-memory only -- process-local, acceptable for request-scoped design |
| Audit persistence | **LOW** | Only allowed write via existing platform_audit_service |
| Redaction | **LOW** | Reuses P10 redact_metadata, applied at gathering layer |
| Reason sanitization | **LOW** | Regex-based, strips credential patterns only |
| Access-denied audit | **LOW** | Best-effort write, failure does not prevent denial |
| Expiry audit | **LOW** | Lazy on next access, best-effort write |

**Overall risk: HIGH (platform runtime API surface) -- mitigated by 58 tests covering all paths.**

## Limitations Stated Honestly

1. **Session expiry is lazy** -- no background timer. Expired sessions are only detected on next access attempt. Sessions that expire and are never accessed again are never audited as expired. This is acceptable for in-memory, request-scoped design.
2. **support_access_denied is best-effort** -- if the audit write fails, access is still denied. The denial is not dependent on audit success.
3. **Reason sanitization is pattern-based** -- it catches common credential key=value patterns but cannot guarantee coverage of all possible credential formats.

## Note: platform-dev Not Merged or Pushed

`platform-dev` was **not merged** and **not pushed** as part of P12-B or R1. Only the isolated branch was pushed.

## Blockers

None. All gates passed.
