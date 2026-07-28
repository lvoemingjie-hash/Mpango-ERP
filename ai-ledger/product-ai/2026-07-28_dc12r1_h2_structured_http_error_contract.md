# DC-12R1-H2 Structured HTTP Error Serialization Boundary

Date: Tuesday, July 28, 2026
Branch: `zcode/dc12r1-h2-structured-http-error-contract-2026-07-28`
Created from: `origin/product-dev-recovered`
Expected base: `bb1b39f137fc7fc1de721b7131e80e5d89b1e2bc` (verified HEAD)
S2 freeze checkpoint (untouched): `zcode/dc12r1-s2-supplier-scoped-retailer-login-2026-07-28` @ `5b51f06ba46703df36f64345ffd658649779c831`

## Verdict

`PASS_FOR_CTO_DC12R1_H2_MERGE_REVIEW`

The production `http_exception_handler` now serializes **every** `HTTPException` into
the standard flat envelope `{code, message, request_id}` (optionally `details`). The
shared defect that stringified `detail=dict` into a Python `str(dict)` repr inside
`message` is closed **centrally** — not by patching the three RBAC raises in isolation.
Permission, tenant-context and platform-identity checks were not touched, and the
full backend gate passed twice on two fresh PG16/Redis7 environments with zero
exclusions, zero failures and zero errors.

## The Defect (RED)

`backend/core/error_codes.py` (base) line 183:

```python
message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
```

For every `HTTPException(detail={"code": ..., "message": ...})` — which is exactly the
shape the RBAC middleware, the auth context resolver and the platform-admin boundary
raise — the handler emitted:

```json
{"code": "PERMISSION_DENIED",
 "message": "{'code': 'PERMISSION_DENIED', 'message': \"Permission 'orders:read' required\"}",
 "request_id": "..."}
```

i.e. the **full Python dict repr** leaked into the public `message` field. This is an
information-disclosure boundary defect with an app-wide blast radius: the handler is
registered globally for `HTTPException` and `StarletteHTTPException` and serializes
every 4xx/5xx the framework emits.

### RED proof (three required codes, over the real handler at base)

```
PERMISSION_DENIED:       HTTP 403 | message="{'code': 'PERMISSION_DENIED', 'message': \"Permission 'orders:read' required\"}"
TENANT_CONTEXT_REQUIRED: HTTP 403 | message="{'code': 'TENANT_CONTEXT_REQUIRED', 'message': 'Please select a tenant first'}"
PLATFORM_ADMIN_REQUIRED: HTTP 403 | message="{'code': 'PLATFORM_ADMIN_REQUIRED', 'message': 'strict identity super admin'}"
```

- The dict repr leaks into `message` (required RED point 1). ✅
- All three codes reproduced (required RED point 2). ✅
- Status stayed `403` for all three; no handler was bypassed (required RED point 3). ✅

RED reproduction command (handler at base, env isolated):

```bash
cd backend
# base http_exception_handler.run on the three RBAC dict-details -> str(dict) in message
```

The RED was also reproduced through the real test app + the focused contract suite:
at base, `pytest tests/test_dc12r1_h2_structured_http_error_contract.py` →
**10 failed, 5 passed** (the dict-repr / preservation / fail-closed / no-leak / nested
assertions fail; only the string-detail and status-only variants pass).

## The Fix (GREEN)

Changed file:

- `backend/core/error_codes.py` (+146 / −15)

`http_exception_handler` now branches on the detail type and **never** stringifies a
whole dict/list/object:

- **dict detail**
  - preserves a non-empty, identifier-safe string `code` (validated by
    `_is_safe_code` — `UPPER_SNAKE`/alphanumeric only, so structure can't be smuggled
    via the code); falls back to the status-derived `ErrorCode`
  - preserves **only** a string `message`; everything else in the dict is dropped
  - optionally preserves an explicitly-public, JSON-safe `details` mapping
    (`_is_json_safe` / `_is_json_safe_nested` reject nested objects, callables, bytes,
    arbitrary types)
  - the complete dict is **never** stringified
- **string detail** — message preserved verbatim; code from the existing status mapping
  (backward compatible)
- **malformed / non-string detail** (list, int, None, object) — fixed sanitized
  fallback via `_status_fallback_message`; raw value never surfaced
- belt-and-braces `_sanitize_message` refuses any `str(dict)`/`str(list)` repr
  (`{'` / `'}` / `['`)
- **logging** carries only the sanitized `error_code` + `status_code`; the raw
  detail/message repr is never logged

GREEN proof (same three codes, fixed handler):

```
PERMISSION_DENIED:       HTTP 403 | code=PERMISSION_DENIED       | message="Permission 'orders:read' required"
TENANT_CONTEXT_REQUIRED: HTTP 403 | code=TENANT_CONTEXT_REQUIRED | message="Please select a tenant first"
PLATFORM_ADMIN_REQUIRED: HTTP 403 | code=PLATFORM_ADMIN_REQUIRED | message="strict identity super admin"
```

### Scope discipline (not weakened)

- No permission / RBAC / tenant-context / platform-identity logic was modified.
- `RequirePermission`, `RequirePlatformAdmin`, `attach/get_auth_context`,
  `attach/get_tenant_context` are byte-identical to base.
- The fix is in the **shared** handler, not a special-case for the three RBAC raises,
  so the whole class of dict-detail leaks is closed (requirement 7).

## Test Changes

New file:

- `backend/tests/test_dc12r1_h2_structured_http_error_contract.py` (473 lines, 15 tests)

The suite builds a minimal FastAPI app that registers the **production** exception
handlers (`register_exception_handlers`) and exercises the **real** `RequirePermission`
/ `RequirePlatformAdmin` dependencies plus raw `HTTPException(detail={...})` raises,
so the full `HTTPException -> response` path is tested exactly as production serves it.

Coverage:

- production `register_exception_handlers` app
- real-HTTP RBAC / platform / tenant-context denial matrix — the three codes over the
  real RBAC deps AND raw dict-detail raises, all returning `403`
- arbitrary valid product error-code preservation from a dict detail
- malformed detail (list, int, None) fail-closed to a sanitized fallback
- string-detail backward compatibility
- no braces / single-quoted dict repr / internal exception content in responses
- logging carries only sanitized `code`+`status`, never the raw detail repr
  (asserts directly on `logger.warning` via `mock.patch`, robust to the full-suite
  structured-logging reconfiguration — `caplog`/propagation-based capture is not
  reliable across the whole gate)
- handler-level contract for every status code (400/401/403/404/409/422/429/500),
  status preserved; nested/extra dict keys never leak

No skip, xfail, deselection, exclusion, assertion weakening, migration edit, permission
change, RBAC change, or S2 work was introduced.

## Production Code-Code Safety Audit

- All 125 distinct `"code"` strings raised as dict-detail across the backend pass the
  `_is_safe_code` allowlist (verified by scanning every `detail={"code": "..."}` raise).
  The 5 values that would fail (`MILK-500ML`, `OIL-1L`, `RICE-5KG`, `SUGAR-1KG`,
  `UNGA-2KG`) are product **SKU** codes in `scripts/onboard_tenant.py`, never
  HTTPException detail codes, so they never reach the handler. No regression.

## Test-Safe Environment

Fresh, isolated, single-use infrastructure (no production data, loopback only):

- PostgreSQL 16.14 container `mpango_h2_pg16` on `127.0.0.1:5433`
- Redis 7.4.10 container `mpango_h2_redis7` on `127.0.0.1:6380`
- Python 3.12.10 isolated venv (project-pinned: `fastapi==0.128.0`,
  `bcrypt>=4.0,<4.1` to satisfy passlib 1.7.4's 72-byte contract,
  `pytest==8.4.2`, `httpx==0.28.1`, `openpyxl==3.1.5`, …)
- Main gate DB `mpango_test_s2` dropped + re-migrated from scratch to head
  `036_retailer_mvp_identity` before each run
- Temp-DB migration tests opted in explicitly:
  `MPANGO_ALLOW_TEMP_DB_CREATE=1`, `MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1,localhost`,
  `MPANGO_TEMP_DB_ALLOWED_PORTS=5433`, test-safe source user
  `mpango_test_runner` (never `mpango`, never `prod`) on disposable `test_h2`
- All credentials disposable test-only; Redis flushed between runs

## Full Backend Gate (twice, fresh PG16/Redis7, zero exclusions)

Both runs: full suite, no `-k`, no `--deselect`, no skip/xfail introduced, zero
exclusions, zero failures, zero errors.

| Run | Passed | Skipped | XFailed | Failed | Errors | Wall |
|-----|--------|---------|---------|--------|--------|------|
| 1 (fresh PG16 + Redis7) | 2920 | 29 | 15 | 0 | 0 | 8m05s |
| 2 (fresh PG16 + Redis7) | 2920 | 29 | 15 | 0 | 0 | 8m11s |

Pre-existing skips/xfails only (DB-optional / known-incomplete features); no test was
deselected or weakened. The 7 migration/temp-DB infra tests that initially errored
were environment-only (`TEST_DATABASE_URL` + temp-DB opt-in flags) and pass once the
documented test-safe environment is provided — not a code change.

## Quality Gates

- `py_compile` on both changed files — OK
- `git diff --check` — clean (no whitespace errors), exit 0
- `detect-secrets scan` on both files — **0 findings** (the one initial Secret-Keyword
  hit was a deliberate negative-test fixture `"secret": "leak"`; renamed to
  `"internal_field": "leak"` to avoid the false positive without weakening the test)
- scoped `pre-commit run --files` (trailing-whitespace, end-of-files, large-files,
  detect-secrets `--baseline .secrets.baseline`) — all Passed
- `gitnexus status` — index up-to-date at base `bb1b39f`
- `gitnexus impact http_exception_handler -d upstream` — graph returns **LOW /
  impactedCount 0**, exactly as the task anticipated: the handler is registered
  dynamically via `app.add_exception_handler` in `register_exception_handlers`
  (which `gitnexus impact` confirms is called by `backend/main.py`, the app entry
  point), so the static call graph cannot see its dependants.
  **Effective blast radius is treated as HIGH** (it serializes every HTTPException
  app-wide). The double full-backend-gate on fresh environments is the real
  regression proof for that HIGH radius.

## Files Touched (only these two)

- `backend/core/error_codes.py` (modified)
- `backend/tests/test_dc12r1_h2_structured_http_error_contract.py` (new)

No S2 files, permissions, RBAC decisions, migrations, frontend, or any other file were
modified.

## Push

Only the isolated H2 branch `zcode/dc12r1-h2-structured-http-error-contract-2026-07-28`
is pushed. No protected push, merge, deploy, S3 or S4.
