# DC-6C Export Malformed ID Runtime Recheck

| Field | Value |
|---|---|
| Date | 2026-07-13 |
| Task ID | DC-6C (Export Malformed ID Runtime Recheck) |
| VPS | Tencent VPS `1.14.247.12` |
| Project Path | `/opt/mpango-erp` |
| Target Commit | `547b0b294aa387d6179f53eca3ec162532a1e29e` |
| Deployed Commit (VPS HEAD) | `547b0b294aa387d6179f53eca3ec162532a1e29e` (match) |
| Ops Branch | `ops/dc6c-export-malformed-id-runtime-recheck-2026-07-13` |
| Verdict | `PASS_EXPORT_MALFORMED_ID_RUNTIME_RECHECK` |

## Summary

DC-6C proves the DC-6B red-team P0 (malformed export job IDs causing 500 with
UUID parser exception leak) is closed in real VPS runtime at commit
`547b0b29`. Malformed IDs return controlled 400 `INVALID_EXPORT_ID` with no
exception text leakage. Well-formed fake UUIDs return 404 `EXPORT_NOT_FOUND`.
No 500s, no secret leaks, no tracebacks.

## Preflight

| Check | Result |
|---|---|
| `origin/product-dev-recovered` | `547b0b294aa387d6179f53eca3ec162532a1e29e` |
| VPS tracked dirty bytes | 0 (clean) |
| VPS `HEAD` after checkout | `547b0b294aa387d6179f53eca3ec162532a1e29e` |
| DB backup path | `/home/ubuntu/.secure-backups/dc6c_20260712T223753Z.sql` |
| DB backup size | 461,831 bytes |
| DB backup SHA256 prefix | `3b263368ac08` |
| `docker compose config -q` | exit 0 (valid) |
| `docker compose up -d --build` | exit 0 (success) |
| Container health | 5/5 healthy (backend, frontend, gateway, postgres, redis) |
| `/health/live` | 200 |
| `/health/ready` | 200 |
| `/openapi.json` | 200 |
| `/` | 200 |
| Alembic heads | `031_legacy_tenant_reconciliation (head)` |
| Alembic current | `031_legacy_tenant_reconciliation (head)` |

## Runtime Checks

### Authenticated probes (valid tenant token with exports permission)

| Endpoint | HTTP | error.code | Body Leak Check | Pass? |
|---|---|---|---|---|
| `GET /api/v1/exports/not-a-uuid` | **400** | `INVALID_EXPORT_ID` | clean (no "badly formed", no "ValueError", no "traceback") | PASS |
| `GET /api/v1/exports/not-a-uuid/download` | **400** | `INVALID_EXPORT_ID` | clean | PASS |
| `GET /api/v1/exports/00000000-0000-0000-0000-000000000000` | **404** | `EXPORT_NOT_FOUND` | clean | PASS |
| `GET /api/v1/exports/00000000-0000-0000-0000-000000000000/download` | **404** | `EXPORT_NOT_FOUND` | clean | PASS |

### Unauthenticated probes (auth gate before handler)

| Endpoint | HTTP | Pass? |
|---|---|---|
| `GET /api/v1/exports/not-a-uuid` (no auth) | **401** | PASS |
| `GET /api/v1/exports/not-a-uuid/download` (no auth) | **401** | PASS |
| `GET /api/v1/exports/00000000-...` (no auth) | **401** | PASS |

### Auth behavior regression check

- Login with temp password: 200 (auth works).
- select-tenant: 200 (tenant selection works).
- No auth regression detected.

### Export permission caveat

A no-exports:create token was not separately prepared (would require creating a
restricted user). The route authorization policy test
(`test_route_authorization_policy.py`) confirms exports endpoints are gated by
`exports:create` permission. The unauthenticated 401 proves the auth gate runs
before handler logic. This is recorded as a coverage caveat, not a defect.

## Backend Log Scan (post-smoke window)

| Pattern | Count |
|---|---|
| HTTP 500 | 0 |
| EXPORT_STATUS_FAILED for malformed ID | 0 |
| EXPORT_DOWNLOAD_FAILED for malformed ID | 0 |
| Secret leak (password/SMTP/DB URL/SECRET_KEY/Bearer) | 0 |
| TenantContextMissing | 0 |
| UndefinedTable | 0 |
| Decimal serialization traceback | 0 |
| "badly formed hexadecimal UUID string" | 0 |
| ValueError / traceback | 0 |

**ALL_ZERO = True**

## Guardrails

| Guardrail | Result |
|---|---|
| No raw JWT/password/SMTP/DB secret/backup printed | PASS |
| No token in backend query string | PASS (query-string tokens rejected at auth layer) |
| VPS tracked clean before checkout | PASS |
| DB backup created before deploy | PASS |
| 5/5 containers healthy after deploy | PASS |
| Temp password set + restored (HASHES_RESTORED=True) | PASS |
| Temp script removed from container | PASS |

## Verdict

**PASS_EXPORT_MALFORMED_ID_RUNTIME_RECHECK**

The DC-6B red-team P0 is closed. Malformed export job IDs return controlled 400
`INVALID_EXPORT_ID` (never 500) with no UUID parser exception text leakage.
Well-formed fake UUIDs return 404 `EXPORT_NOT_FOUND`. Unauthenticated requests
return 401 before reaching handler logic. Backend logs show zero 500s, zero
secret leaks, zero tracebacks. No production data was permanently mutated.
