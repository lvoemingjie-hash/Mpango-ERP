# DC-10G Platform UUID + Export Error Boundary Hardening

| Field | Value |
|---|---|
| Date | 2026-07-13 |
| Task ID | DC-10G (Platform UUID + Export Error Boundary Hardening) |
| Base | `547b0b294aa387d6179f53eca3ec162532a1e29e` (`release-2026-07-13`) |
| Branch | `opencode/dc10g-platform-uuid-export-error-hardening-2026-07-13` |
| R0 commit | `3e1b0653` |
| R1 commit | `f3dde606707b272dff04726d402948e4bf516476` |
| R2 commit | (this revision) |
| Verdict | `PASS_FOR_CTO_DC10G_MERGE_REVIEW` |

## 1. Problem Statement

Three platform route handlers passed raw string UUID path parameters directly to
SQLAlchemy `.where(Column.id == raw_string)` queries. A malformed ID (e.g.
`not-a-uuid`) would reach asyncpg's UUID column parser and raise a `DataError`,
surfacing as HTTP 500 with potential driver exception text leakage.

The export enqueue handler (`POST /exports`) used `str(e)` in its 500 response
body, leaking raw exception text (potentially containing internal hostnames,
connection strings, or credentials) to the API client.

## 2. Changes

### 2.1 Platform UUID validation (3 routes)

Added a `_parse_uuid_param` helper (or reused the existing `_coerce_tenant_id`)
at the top of each handler to parse the UUID path parameter BEFORE the DB query.
Malformed IDs return a controlled 404 (not 500). Authentication/identity-only
super_admin protection runs first (via `require_platform_operator` dependency).

| File | Route | Fix |
|---|---|---|
| `api/v1/platform/tenants.py` | `GET /{wholesaler_id}` | `_parse_uuid_param` guard; 404 on malformed |
| `api/v1/platform/audit.py` | `GET /{log_id}` | `_parse_uuid_param` guard; 404 on malformed |
| `api/v1/platform/p10/services.py` | `get_audit_event` | Reused `_coerce_tenant_id`; None -> 404 |

### 2.2 Export enqueue error boundary

| File | Route | Fix |
|---|---|---|
| `api/v1/exports.py` | `POST /exports` | Replaced `make_error("EXPORT_ENQUEUE_FAILED", str(e))` with fixed sanitized message `"Unable to enqueue export job. Please try again later."` Logs record only `type(e).__name__`. |

## 3. Test Corrections (R1)

### 3.1 All env mutations use monkeypatch
Every `os.environ` mutation in tests is done via `monkeypatch.setenv` /
`monkeypatch.delenv` which auto-restores after each test.

### 3.2 Export enqueue test executes the real handler
`test_enqueue_failure_sanitized_response_and_logs` calls `create_export` with:
- A sentinel exception containing a fake internal connection string with
  credential-like text (exact value redacted here; see test source)
- Mocked `_extract_tenant` and `get_job_queue`
- Asserts HTTP 500, `EXPORT_ENQUEUE_FAILED` code
- Asserts sentinel URL/text absent from response body
- Asserts sentinel URL/text absent from logs (via `capsys`)
- Asserts only `ConnectionError` (class name) appears in logs

### 3.3 Malformed UUID tests prove no SQL execution
Every malformed UUID test asserts `mock_db.execute.await_count == 0`,
proving the UUID parse fails BEFORE any SQL reaches the database.

### 3.4 Direct p10 get_audit_event test
Two tests call `get_audit_event` directly:
- Malformed UUID -> None, `db.execute.await_count == 0`
- Well-formed missing UUID -> None, `db.execute.await_count >= 1`

### 3.5 Integrated event-loop isolation correction
The stabilization candidate uses `@pytest.mark.asyncio` and direct `await`
for async handler tests. Integrated validation proved that `asyncio.run()`
clears the current event loop on Python 3.12 and breaks later legacy P10 tests
that call `asyncio.get_event_loop()`. Pytest-managed loops pass DC-10G,
route-authorization, and P10 tests in the same process without production-code
changes.

## 4. GitNexus Compare Result

| Field | Value |
|---|---|
| Risk level | CRITICAL |
| Files changed | 6 |
| Mapped symbols | 56 |
| Affected flows | 20 |

**Why CRITICAL is appropriate:** the changes touch `create_export` (the export
enqueue entry point) and platform route handlers (`get_tenant`,
`get_audit_log`, `get_audit_event`) that are on every platform API request
path. The blast radius of a regression in any of these would affect all
platform operations and all export operations.

**Why the semantic edits remain narrow despite the CRITICAL rating:**
- Each edit adds a UUID parse guard BEFORE an existing DB query; the query
  itself and everything after it is unchanged.
- The export error boundary only replaces the `str(e)` argument with a fixed
  string; the try/except structure and status code are unchanged.
- No new dependencies, no schema changes, no auth/RBAC weakening.
- All 318 regression tests pass (43 route-auth + 229 platform + 38 exports +
  8 dc10g), confirming the narrow scope.

## 5. Test Results

| Suite | Count |
|---|---|
| `test_dc10g_platform_uuid_export_error_hardening.py` | 8 passed |
| `test_dc10g + test_route_authorization_policy` (both orders) | 43 passed |
| `test_platform_p10_contracts + audit_api + stats_api` | 229 passed |
| `test_s6_4_async_exports` | 38 passed |
| **Total** | **318 passed, 0 failed** |

## 6. Changed Files

| File | Change |
|---|---|
| `backend/api/v1/platform/tenants.py` | Added `_parse_uuid_param` + guard in `get_tenant` |
| `backend/api/v1/platform/audit.py` | Added `_parse_uuid_param` + guard in `get_audit_log` |
| `backend/api/v1/platform/p10/services.py` | Added `_coerce_tenant_id` guard in `get_audit_event` |
| `backend/api/v1/exports.py` | Sanitized `EXPORT_ENQUEUE_FAILED` message |
| `backend/tests/test_dc10g_platform_uuid_export_error_hardening.py` | 8 tests (R2 cleanup: removed duplicate, HTTPException) |
| `ai-ledger/product-ai/2026-07-13_dc10g_platform_uuid_export_error_hardening.md` | Durable report (this file) |

## 7. Verdict

**PASS_FOR_CTO_DC10G_MERGE_REVIEW**
