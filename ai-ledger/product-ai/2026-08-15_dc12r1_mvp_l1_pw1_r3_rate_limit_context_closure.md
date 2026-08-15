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

---

# PW1-R3-R1 — Evidence-truth and deterministic-test correction (same branch)

## 1. Product files byte-unchanged
`git diff 07013d2 --stat -- backend/api/app.py backend/api/middleware/auth.py
backend/api/middleware/rate_limiting.py backend/core/rate_limiter.py` = **0
lines**. All R1 work touched only the test file, ledger/report, and evidence.

## 2. V2 facts corrected (artifact-verified)
V2 `junit.xml` (committed on the V2 branch) actually contains **162
testcases / 58 failures ⇒ 104 passed**; **47** failure blocks mention 429,
**11** do not (incl. 3× "public auth pages are reachable anonymously",
Phase 4 idempotency/print nodes, Phase 5 isolation nodes). The V2 report's
80/82/"all 429" contradicts its own JUnit → INVALID_EVIDENCE_RECONCILIATION.
PW1-R3's own earlier "zero failure cases" claim was a reviewer regex error
and is corrected in the marker.

## 3. Branch inventory — 18 files, 4+1+2+11
- 4 product: `backend/api/app.py`, `backend/api/middleware/auth.py`,
  `backend/api/middleware/rate_limiting.py`, `backend/core/rate_limiter.py`
- 1 test: `backend/tests/test_pw1r3_rate_limit_context.py`
- 2 ledger/report: `ai-ledger/product-ai/2026-08-15_...r3...md`,
  `docs/ai-reports/review/2026-08-15_PW1_R2_R2_V2_INVALID_EVIDENCE_RECONCILIATION.md`
- 11 evidence: `pw1r3-evidence/{impact_×6, gate1/2_full_backend, frontend_full_vitest,
  R3_MUT_A/B}` (+ R1 additions below)

## 4. Two backend rounds, truthfully recorded; skip/xfail set comparison
R1 re-ran both full rounds with `-rN` so node sets are machine-captured:
- Round A: 3630 passed / 48 skipped / 15 xfailed / 0 failed / 0 errors
- Round B: 3630 passed / 48 skipped / 15 xfailed / 0 failed / 0 errors
- skipped/xfailed node sets extracted; see `r1_gateA/B_full_backend.txt` and
  the set-comparison summary in `pw1r3-evidence/r1_skip_xfail_comparison.txt`.

## 5. Deterministic test keys (no conditional assertions)
The suite now uses a task-exclusive Redis DB (`PW1R3_TEST_REDIS_URL`, default
.../15) with exact task-owned keys and a deterministic start per test:
- tenant bucket: fresh UUIDs per test (function-scoped `rl_tenant`),
- anonymous bucket: per-RUN random `10.x.y.*` ASGI client peer per test
  (transport-level peer, NOT XFF/X-Real-IP spoofing) — each test begins at
  count 0 even across rapid consecutive runs.
- No FLUSHDB, no SCAN/wildcard delete, no retries-until-green, no sleeps.
- The (401,429)/(200,429) conditional assertions are gone: every test now
  asserts a single exact status.

## 6. Sleeps removed
No `time.sleep` remains; window-alignment is unnecessary with per-run keys
(no `asyncio.sleep` needed either).

## 7. Wording corrected
"provisioned tenant user" → "synthetic real-PG auth schema": the tenant
schema + user are created by the test via direct DDL/INSERT (not the formal
owner/retailer lifecycle); the docstring and ledger now say exactly that.

## 8. Re-runs (all GREEN)
- Natural order ×3 rapid consecutive: 7/7 each
- Reverse order: 7/7
- MUT-A (wrong middleware order): RED 4 failed; restored → GREEN
- MUT-B (user_id omitted): RED 3 failed; restored → GREEN
- Fresh full-stack rounds A/B above.

## 9. Push-only
Only the isolated branch is pushed; no merge, no OpenCode browser gate started.
