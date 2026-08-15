# DC-12R1-MVP-L1-PW1-R4-A — Cross-Tenant Prepared-Statement Runtime Closure (2026-08-15)

## Base & Branch

- Base: `2b7b959815a8f2454811303ca1bd13c64c413bb4` (verified: worktree HEAD at branch creation, clean tree)

> ## PW1-R4-A-R1 correction (2026-08-15, same branch, fast-forward)
>
> This original R4-A section is superseded by the R1 closure below. Key
> corrections: evidence artifacts were removed from the branch scope (final
> aggregate diff = exactly the 4 approved files); the exact production route
> GET /api/v1/client/orders?page=1&size=100 is now the causal surface;
> setup is fail-closed with forced-failure proofs; H5 ddl_engine binding
> risk fixed; wording corrected (per-POOL, not per-connection).
- Parent chain: `2b7b959` (R3-R2-R1) ← `11148b6` ← `1181ffe` ← `07013d2` (R3) ← `9f5d677` (R2-R2) ← … ← `d2e7e44` (baseline)
- Branch: `zcode/dc12r1-mvp-l1-pw1-r4-a-tenant-statement-cache-closure-2026-08-15`

## Root cause (reproduced empirically on real PG16, pool_size=1)

The SQLAlchemy asyncpg dialect keeps a per-POOL LRU of server prepared
statements keyed ONLY by SQL text. Tenant routing is per-transaction
`SET LOCAL search_path` on a SHARED pool, so a statement planned for one
tenant's relation OIDs can be re-executed on a pooled connection after
another tenant's provisioning/migration DDL invalidates those plans —
surfacing as `sqlalchemy.exc.NotSupportedError →
sqlalchemy.dialects.postgresql.asyncpg.InvalidCachedStatementError →
asyncpg.exceptions.InvalidCachedStatementError` (500 to the requesting
tenant). Reproduced on the production engine via `get_tenant_db`
(`probe_ddl_invalidation.py`).

Empirical invalidation rules discovered (probe evidence):
- The cached plan must REFERENCE the DDL-altered column; selecting an
  untouched column never reproduces (dependency-based invalidation).
- The DDL must change the column TYPE OID (text↔varchar). A typmod-only
  change (varchar(255)→(300)) never reproduces.
- A REPEATED same-direction ALTER is a no-op; the DDL storm flips the type
  (text↔varchar) each call so every storm genuinely invalidates.

## Fix candidate matrix (real RED, real PG16, pool_size=1)

| Candidate | Result |
|---|---|
| `prepared_statement_cache_size=0` (SQLAlchemy asyncpg dialect connect_args) | **RED closed** ✅ adopted |
| `statement_cache_size=0` (asyncpg kwarg) | `BufferError` (invalid on asyncpg 0.31 in this driver path) — NOT used |
| both | RED closed — no better than the single minimal setting |
| control (defaults) | RED alive (`InvalidCachedStatementError`) — causality anchor |

Minimal setting adopted: `prepared_statement_cache_size=0` alone, in
`backend/database/session.py` `async_engine` connect_args. No per-request
engine disposal, no per-tenant engines, no route retries, no swallowed
exceptions.

## Exact file list (scope)

| File | Change |
|---|---|
| `backend/database/session.py` | production engine connect_args += `prepared_statement_cache_size: 0` (with rationale comment) |
| `backend/tests/test_dc12r1_h5_prepared_statement_cache_isolation.py` | revised (see below) — no false-green under the new runtime policy |
| `backend/tests/test_pw1r4_cross_tenant_statement_cache.py` | NEW suite (4 tests) |
| `ai-ledger/product-ai/2026-08-15_dc12r1_mvp_l1_pw1_r4_a_tenant_statement_cache.md` | this ledger |

## New suite — test_pw1r4_cross_tenant_statement_cache.py

Real artifacts only: two tenant schemas created with the FORMAL bootstrap
(`scripts.bootstrap_tenant_schema.bootstrap` — the same module
TenantProvisioningService loads); synthetic active user rows (direct inserts,
documented as synthetic; no lifecycle claim); production `AsyncSessionLocal`
and a real `configure_app + JwtAuthStrategy` HTTP app.

1. `test_http_abab_cycles_survive_ddl_storm` — real contextual routes
   (`GET /api/v1/auth/me`) A→B→A and B→A cycles with an interleaved
   type-OID DDL storm on tenant A's table; every request 200 with the
   CORRECT tenant's data.
2. `test_engine_aba_cycles_survive_ddl_storm` — `get_tenant_db` cycles on
   the production engine; selects the storm-altered column (dependency) so
   the leg cannot false-green.
3. `test_legacy_engine_without_fix_reproduces_invalid_cached_statement` —
   causal RED: a legacy engine (production config minus the fix,
   pool_size=1) raises InvalidCachedStatementError on the same cycle.
4. `test_no_cross_tenant_leak_across_cycles` — each tenant always observes
   its own rows across repeated alternation and after DDL storms.

Results: 4/4 natural order; 4/4 reverse order; mutation (fix removed from
session.py) → HTTP and engine legs RED (2 failed), legacy-RED and no-leak
still pass; restored → 4/4 GREEN. (pw1_r4a_evidence/MUTATION_session_fix_removed_RED.txt)

## H5 revision — causality preserved, false-green eliminated

Under the new runtime policy the OLD global-engine GREEN would pass even
WITHOUT dispose (the production engine no longer caches statements), i.e. it
would stop being dispose-causal. H5 was reshaped:
- RED — unchanged (test-local caching engine; no dispose; same SQL after
  DDL → error). Still the causal core.
- GREEN — reshaped onto a CACHING engine: same SQL cached → DDL → dispose →
  same SQL re-executed OK. Without dispose this exact shape is RED (proven
  by the RED test), so the GREEN is dispose-causal.
- NEW POLICY leg — the production global engine re-executes the SAME SQL
  after DDL WITHOUT dispose and must succeed; fails if
  `prepared_statement_cache_size=0` is ever removed (covered by the same
  mutation run).
Module docstring documents the policy update. H5 suite now 5 tests, 5/5
GREEN; mutation run confirms the POLICY leg fails when the fix is removed.

## Regression

Focused: R4-A + H5 + global tenant filter + R3 rate-limit context + auth
bypass + middleware tenant-context contract — all green (the single initial
R3 rate-limit failure was environment-only: its Redis default pointed at a
torn-down dev stack; 7/7 with the live gate Redis; no product code involved).

## Gates

- Two independent fresh PG16 + Redis7 full backend suites
  (`tests/`, disposable `test_*` DBs, alembic head, temp-db opt-in envs):
  see gateA/gateB evidence files for the machine-derived node/result
  accounting.
- Hygiene: py_compile (session.py + both test files), git diff --check,
  scoped detect-secrets, strict UTF-8, GitNexus re-analyze — all clean.

## Reproduction

```
docker run -d --name <pg16> -p 127.0.0.1:25440:5432 \
  -e POSTGRES_USER=mpango_tester -e POSTGRES_PASSWORD=... -e POSTGRES_DB=test_pw1r4a \
  -v <repo>/database/init.sql:/docker-entrypoint-initdb.d/init.sql postgres:16-alpine
docker run -d --name <redis7> -p 127.0.0.1:26387:6379 redis:7-alpine
DATABASE_URL=... python -m alembic upgrade head
TEST_DATABASE_URL=... REDIS_URL=... MPANGO_ENV=test \
  python -m pytest tests/test_pw1r4_cross_tenant_statement_cache.py \
                    tests/test_dc12r1_h5_prepared_statement_cache_isolation.py -q
```

## Gate results (machine-derived)

- Gate A (fresh PG16 `test_pw1r4a`@25440 + Redis7@26387): **3635 passed /
  48 skipped / 15 xfailed / 0 failed / 0 errors** (23:29).
- Gate B (independent fresh PG16@25441 + Redis7@26388): **3635 passed /
  48 skipped / 15 xfailed / 0 failed / 0 errors** (23:59).
- Reconciliation (`pw1r4a-evidence/gate_reconciliation.txt`): skip-location
  sets identical (48=48), xfail node-ID sets identical (15=15).
- 3635 = prior 3630 + 5 new nodes (4 R4-A + 1 H5 POLICY).

---

# PW1-R4-A-R1 — Exact route, fail-closed cleanup and scope truth (same branch)

## 1. Exact-route causal proof (the production route, not /auth/me)

`GET /api/v1/client/orders?page=1&size=100` through the REAL stack:
JwtAuthStrategy (production wiring via configure_app), AuthenticationMiddleware
tenant context (real tenant DB session + ORM user load), real
`resolve_client_identity` (authoritative binding lookup), real
`RequirePermission("client:orders:read")`, real `get_orders_for_retailer`.
Two formally bootstrapped tenants carry the required readiness rows
(retailer_operator role + client:orders:read permission + active
wholesaler_retailer_binding keyed on token.tenant_id = seeded
public.wholesalers.id + retailer + one tenant-distinct order).

- GREEN: A -> B -> DDL -> A and B -> A cycles — every request 200, exactly 1
  own order, correct tenant marker, zero cross-tenant leakage.
- CAUSAL RED: the same exact route with the tenant-context session factory
  rerouted onto a legacy engine (production config minus the fix) fails after
  the DDL storm with InvalidCachedStatementError in the error chain.
- Mutation: removing `prepared_statement_cache_size=0` from session.py turns
  the exact-route GREEN and engine legs RED (2 failed), restored GREEN 8/8.
  (R1_MUTATION_fix_removed_RED evidence, kept off-branch.)

## 2. Fail-closed setup (owned-schema tracking from the first bootstrap)

`_setup_two_tenants` wraps EVERY step from the first bootstrap in try/finally
with an `owned` schema list; any failure drops all owned schemas, asserts
zero `pg_namespace` residue, and propagates the ORIGINAL exception (a cleanup
failure is chained, never masking). `ddl_engine` is created before the
protected path returns. Forced-failure tests (order-independent, each
verified GREEN individually and in reverse order):
- second-bootstrap failure -> tenant A cleaned, zero residue
- user-seed failure -> both tenants cleaned, zero residue
- before-ddl_engine failure -> both tenants cleaned, zero residue

## 3. H5 truth repairs

- GREEN-leg `ddl_engine` hoisted BEFORE the protected try (unbound-name risk
  eliminated if phase 1 fails).
- Docstring now states precisely: RED/GREEN use DEDICATED cache-enabled
  engines; ONLY the POLICY leg uses the production global engine.
- No weakening: RED unchanged; dispose-GREEN same-SQL causal; POLICY leg
  mutation-sensitive.

## 4. Exact scope truth

- All `pw1r4a-evidence/*` artifacts REMOVED from the branch; `f348f4a`
  retains its historical copy. Final aggregate `2b7b959..HEAD` contains
  EXACTLY the 4 approved files: backend/database/session.py,
  backend/tests/test_dc12r1_h5_prepared_statement_cache_isolation.py,
  backend/tests/test_pw1r4_cross_tenant_statement_cache.py, and this ledger.
- `git diff --check 2b7b959..HEAD` exits 0.

## 5. Evidence facts corrected

- Cache wording: per-POOL (SQLAlchemy asyncpg dialect per-pool LRU), not
  per-connection.
- GitNexus impact: HIGH risk, 3 DIRECT impacted (seed, find_user_across_tenants,
  get_tenant_db_session), 6 total impacted (create_tenant_session chain).
- Route suite is now 8 tests (exact-route GREEN + exact-route causal RED +
  engine GREEN + legacy RED + no-leak + 3 forced-failure cleanup tests);
  H5 suite is 5 tests; combined focused run 13/13 both natural and reverse
  order.

## 6. Gates (this round)

- R4-A (8) + H5 (5): natural order 13/13; reverse order 13/13.
- Forced-failure tests order-independent (reverse run green).
- Two independent fresh PG16+Redis7 full backend suites with node, skip,
  xfail and accounting reconciliation (see gate evidence off-branch).
- py_compile, git diff --check, scoped detect-secrets, strict UTF-8,
  GitNexus re-analyze — clean.
