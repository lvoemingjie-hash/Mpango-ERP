# DC-12R1-MVP-L1-PW1-R3 — Authenticated Rate-Limit Context Closure (2026-08-15)

## Base & Branch

- Product baseline: `d2e7e44cf23e91cabfab545c494abd342fec3062`
- Auth candidate (parent): `9f5d67712e64f21061bd3516c6f0240f9feafb26`
- Invalid browser evidence (superseded by this task): `ba9da9ba17f60e12d70e1e6bfefbce5a789dc5b0`
- Branch: `zcode/dc12r1-mvp-l1-pw1-r3-rate-limit-context-closure-2026-08-15`
- Worktree: `C:\Users\Jeff0\pw1_r2_worktree` (backend-focused task)

## Root cause closed

`configure_app` registered `RateLimitingMiddleware` AFTER
`AuthenticationMiddleware`; Starlette makes the LAST-registered middleware the
OUTERMOST, so the rate limiter ran BEFORE authentication and
`request.state.tenant_id/user_id` never existed when the key was derived —
every request, including fully authenticated browser sessions, landed on the
anonymous per-IP bucket (`rate_limit:ip:{ip}`, 100/min). A second latent
defect: `AuthenticationMiddleware` never set `request.state.user_id` at all, so
even a correct order would have left contextual requests on the IP bucket.

## Exact file list (scope)

| File | Change |
|---|---|
| `backend/api/app.py` | `configure_app`: RateLimitingMiddleware registered BEFORE AuthenticationMiddleware (auth is outermost of the two and runs first) |
| `backend/api/middleware/auth.py` | `dispatch`: attaches `request.state.user_id` (verified server-side JWT principal, contextual only); the 401 rejection path now enforces the anonymous IP bucket via `enforce_rate_limit_on_auth_rejection` so malformed/invalid Authorization can never bypass limiting |
| `backend/api/middleware/rate_limiting.py` | shared `RATE_LIMIT_EXEMPT_PATHS` (health/metrics preserved); extracted async `_rate_limit_rejection_response` (exact S2-5 429 headers preserved); new `enforce_rate_limit_on_auth_rejection` (fail-open on limiter errors, same exemptions) |
| `backend/core/rate_limiter.py` | `_get_rate_limit_key`: verified-context contract documented; tenant_id without a verified user_id degrades to the anonymous bucket (never an ambiguous partial context) |
| `backend/tests/test_pw1r3_rate_limit_context.py` | NEW integration suite (7 tests) |

No migration, dependency, lockfile, financial-semantic or frontend change.

## Mandatory outcomes

1. GitNexus impact BEFORE editing (pw1r3-evidence/impact_*.json):
   configure_app → 5 impacted, `_get_rate_limit_key` → 2,
   AuthenticationMiddleware → 26 (widest; includes frontend callers).
   Graph caveat: TS/JSX call composition is file-level only (unchanged
   limitation, documented since PW1-R2).
2. Verified contextual JWT → `rate_limit:tenant:{tenant_id}:{user_id}`,
   limit 1000 (`DEFAULT_TENANT_LIMIT`, pre-existing constant — unchanged).
3. Anonymous and identity-only requests stay on the IP bucket, limit 100.
4. tenant/user derived only from `request.state` fields that
   AuthenticationMiddleware sets from the server-side verified token.
5. Malformed/invalid Authorization is rejected WITH the same IP bucket
   enforced on the rejection path (no unlimited bypass; proven by test).
6. Health/metrics exclusions preserved via the shared
   `RATE_LIMIT_EXEMPT_PATHS`; the exact 429 headers
   (X-RateLimit-Limit/Remaining/Reset + Retry-After) preserved on both the
   inner middleware and the rejection path.
7. Integration tests run the REAL middleware stack (FastAPI + configure_app +
   production JwtAuthStrategy via httpx ASGITransport) with a REAL Redis
   client and a REAL provisioned tenant user in a real tenant schema. Only the
   Redis client endpoint is wired (dependency injection), no state mocks.
8. Mutation RED (both restored + re-verified GREEN):
   - MUT-A wrong middleware order restored → 6/7 tests fail
   - MUT-B `user_id` attachment removed → 5/7 tests fail
9. `test_101st_anonymous_is_429_and_contextual_independently_admitted`:
   window-aligned exact boundary — cumulative request #(prior+index)==101 is
   429 with limit 100 headers; a garbage-token request then also 429s (same IP
   bucket); a valid contextual request is independently admitted with
   X-RateLimit-Limit=1000.
10. OpenCode V2 report marked INVALID_EVIDENCE_RECONCILIATION and superseded
    (`docs/ai-reports/review/2026-08-15_PW1_R2_R2_V2_INVALID_EVIDENCE_RECONCILIATION.md`);
    the V2 branch itself is preserved untouched as historical evidence.
    Independent audit findings: V2 JUnit contains zero failure cases despite
    claiming 82 failures; no raw Playwright JSON; "all 429" not node-proven.

## Forbidden-practice compliance

- Test limit not increased (1000 is the pre-existing product tenant limit).
- No test-only bypass: tests exercise the production constants and paths.
- No FLUSHDB, no wildcard SCAN/delete (test Redis keys are unique per run via
  UUIDs; the shared anonymous IP key is only ever read via explicit GET;
  cleanup drops only this suite's own named schema).
- No retry-until-green (the exact-boundary test aligns to a fresh fixed window
  ONCE for determinism, then asserts; no reruns on failure).
- No spoofed XFF anywhere (tests send no X-Forwarded-For/X-Real-IP).

## Gates

- Focused regression (R3 suite + auth bypass + middleware tenant-context
  contract + S2.5 security): **45/45 passed**.
- Two independent fresh-stack full backend gates: see gate1/gate2 evidence
  (fresh disposable PG `mpango_test` + fresh Redis per gate, Alembic head
  applied, `MPANGO_ALLOW_TEMP_DB_CREATE=1` opt-in for the suite's own
  temporary-database tests).
- Frontend focused + full vitest + build: re-verified on this branch
  (frontend unchanged from 9f5d677).
- Hygiene: git diff --check, detect-secrets, mojibake — clean.
- Browser acceptance (162/162, machine-derived JUnit): assigned to OpenCode
  AFTER Kilo's bounded source review of this branch.

## Reproduction

```
# fresh disposable stack
docker run -d --name <pg> -p 127.0.0.1:25433:5432 -e POSTGRES_USER=mpango \
  -e POSTGRES_PASSWORD=... -e POSTGRES_DB=mpango_test \
  -v <repo>/database/init.sql:/docker-entrypoint-initdb.d/init.sql postgres:15-alpine
docker run -d --name <redis> -p 127.0.0.1:26380:6379 redis:7-alpine
DATABASE_URL=... python -m alembic upgrade head
TEST_DATABASE_URL=... REDIS_URL=... MPANGO_ENV=test MPANGO_ALLOW_TEMP_DB_CREATE=1 \
  python -m pytest tests/test_pw1r3_rate_limit_context.py -q
```
