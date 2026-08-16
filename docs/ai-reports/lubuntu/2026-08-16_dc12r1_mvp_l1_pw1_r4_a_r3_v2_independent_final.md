# DC-12R1-MVP-L1-PW1-R4-A-R3-V2 — Independent Linux Runtime & Merge-Readiness Final

**Date:** 2026-08-16 | **Host:** Lubuntu x86_64 (Ubuntu 24.04, Docker 29.1.3, Python 3.12.3) | **Verdict: PASS_DC12R1_MVP_L1_PW1_R4_A_R3_V2_LUBUNTU_INDEPENDENT_FINAL**

## Verdict summary

Frozen candidate `5e91e97326134805cc29b75492b187aae7c17985` verified end-to-end:
proof gate clean, 14/14 focused bundle in both orders on real PG16+Redis7,
exact-route tenant cycles green with legacy-leg causal RED, zero owned-schema
residue, mutation causality proven, and full backend suite at the expected
**3640 passed / 48 skipped / 15 xfailed / 0 failed / 0 errors** on two
independent stacks with byte-identical skip-location and xfail node-ID sets
(accounting gap = 0).

## 1. Phase 1 — Proof gate (ALL PASS)

| Proof | Result |
|---|---|
| Candidate remote equality | `origin/zcode/dc12r1-mvp-l1-pw1-r4-a-tenant-statement-cache-closure-2026-08-15` = `5e91e973` (ls-remote == rev-parse) ✓ |
| Candidate commit | `5e91e97326134805cc29b75492b187aae7c17985` "PW1-R4-A-R3: genuine cleanup exception closure", parent `aba791d281b812f96d89ccfcd1bed5f5ec955386` ✓ |
| Aggregate base ancestry | `2b7b959815a8f2454811303ca1bd13c64c413bb4` is ancestor ✓ |
| Accepted Kilo evidence | `efc206444053af5f568713f5de2a30931c2b3375` = commit ✓ |
| Protected baseline | `d2e7e44cf23e91cabfab545c494abd342fec3062` = commit, ancestor ✓ |
| Aggregate diff = exactly 4 files | `ai-ledger/product-ai/2026-08-15_dc12r1_mvp_l1_pw1_r4_a_tenant_statement_cache.md`, `backend/database/session.py`, `backend/tests/test_dc12r1_h5_prepared_statement_cache_isolation.py`, `backend/tests/test_pw1r4_cross_tenant_statement_cache.py` ✓ |
| `prepared_statement_cache_size=0` | session.py:52 present ✓ |
| R3 vs `aba791d` comment-only | AST dumps identical (sha256 `81c4b064…efc2b` both), bytes differ ✓ |

Detached worktree at candidate, `git status --porcelain` clean throughout.

## 2. Phase 2 — Fresh stacks (PASS)

Two independent stacks, unique project names, loopback ports, fresh DBs:

| | Stack A | Stack B |
|---|---|---|
| PG16 | `dc12r1-mvp-r4a-v2-pg-a` @127.0.0.1:5598 | `dc12r1-mvp-r4a-v2-pg-b` @127.0.0.1:5599 |
| Redis7 | `dc12r1-mvp-r4a-v2-redis-a` @127.0.0.1:6498 | `dc12r1-mvp-r4a-v2-redis-b` @127.0.0.1:6499 |
| Networks | `dc12r1-mvp-r4a-v2-net-a` | `dc12r1-mvp-r4a-v2-net-b` |
| Test DB | `test_pw1r4a_a` (role `test_runner`) | `test_pw1r4a_b` (role `test_runner`) |

- Alembic sole head **037_payment_declarations_schema** applied on both
  (`alembic current` = head; 37 migration files, single head verified).
- Repository temporary-database opt-in configured per guard rules
  (`tests/async_test_utils.py::_validate_temporary_database_source`):
  `MPANGO_ALLOW_TEMP_DB_CREATE=1`, `MPANGO_TEMP_DB_ALLOWED_PORTS=<stack port>`,
  `MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1`, `TEST_DATABASE_URL` with
  `test[-_]`-named DB and non-`mpango` user (initially missed → 29 collection
  errors + 8 failures; root-caused to the opt-in guard, fixed, re-run — see §8).
- Lock-governed env: `pip install -r backend/requirements.txt`; pins verified
  (asyncpg 0.31.0, SQLAlchemy 2.0.45, alembic 1.18.1, bcrypt 4.0.1,
  cryptography 46.0.5, openpyxl 3.1.5, et_xmlfile 2.0.0, passlib 1.7.4;
  pytest 9.1.1, pytest-asyncio 1.4.0, hypothesis 6.165.9).

## 3. Phase 3 — Focused runtime, Stack A (PASS)

Bundle: PW1-R4-A 9 tests + DC-12R1-H5 5 tests.

| Run | Result |
|---|---|
| Natural order (R4-A → H5) | **14 passed / 0 failed / 0 errors / 0 skipped / 0 xfailed**, exit 0 |
| Reverse order (H5 → R4-A) | **14 passed / 0 failed / 0 errors / 0 skipped / 0 xfailed**, exit 0 |

- **Exact route:** `EXACT_ROUTE = "/api/v1/client/orders?page=1&size=100"`
  (test:73) through real JwtAuthStrategy + real tenant DB dependency.
- **A→B→DDL→A and B→A return 200** with only the correct tenant's order
  (test asserts `status==200`, exactly 1 own order, per-tenant marker notes;
  source `test_exact_route_abab_cycles_survive_ddl_storm`:391).
- **Legacy cache-enabled leg reaches InvalidCachedStatementError** —
  `test_exact_route_without_fix_reproduces_invalid_cached_statement` (engine =
  production minus fix) asserts the chain contains `InvalidCachedStatement`
  after the same DDL storm.

## 4. Phase 4 — Cleanup boundary (PASS with disclosure)

Independent `pg_namespace` query (excluding `pg_catalog`/`information_schema`/
`public`/`pg_%`) before and after EACH forced-failure test — run twice
(initial DB and final disposable DB):

| Forced-failure node | before → after | result |
|---|---|---|
| `test_forced_failure_second_bootstrap_cleans_first_schema` | EMPTY → EMPTY | 1 passed |
| `test_forced_failure_user_seed_reraises_same_original_object` | EMPTY → EMPTY | 1 passed |
| `test_forced_failure_before_ddl_engine_cleans_both_schemas` | EMPTY → EMPTY | 1 passed |
| `test_cleanup_failure_raises_exception_group_with_original_and_cleanup` | EMPTY → EMPTY | 1 passed |

- Zero owned-schema residue; dual-error finally cleanup proven zero-residue.
- Task-created public rows in disposable test DB: `retailers=10`,
  `wholesalers=10`, `bindings=10` (name-prefixed `R4A …`). **Recorded:
  KNOWN_NON_BLOCKING_TEST_FIXTURE_RESIDUE** — fixture rows inside
  task-owned disposable test DBs only; NOT claimed as zero database residue.
  DBs destroyed with their containers at cleanup.
- No residue outside task-owned disposable DBs → no STOP.

## 5. Phase 5 — Mutation causality (PASS)

In disposable copied worktree (`/tmp` worktree at candidate, main tree
untouched):

1. Removed `"prepared_statement_cache_size": 0,` from `backend/database/session.py`
   (py_compile valid; blob pre-mutation `9d52408c…`).
2. Mutated run — all three policy legs **RED**:
   `test_exact_route_abab_cycles_survive_ddl_storm` FAILED,
   `test_engine_aba_cycles_survive_ddl_storm` FAILED,
   `test_runtime_policy_global_engine_survives_ddl_without_dispose` FAILED
   (3 failed; verified twice — also on final env config).
3. Restored via `git checkout` — blob `9d52408c16a2c6de303789f27b5e452394ca868d`
   == candidate blob; worktree `status --porcelain` clean; all 3 legs **GREEN**.
4. No retries, no conditional assertions, no test weakening (only the single
   line deleted/reverted). Post-mutation residue check: 0 schemas.

## 6. Phase 6 — Full backend gates (PASS)

| Stack | passed | skipped | xfailed | failed | errors | exit |
|---|---|---|---|---|---|---|
| A (port 5598/6498) | **3640** | **48** | **15** | **0** | **0** | 0 |
| B (port 5599/6499) | **3640** | **48** | **15** | **0** | **0** | 0 |

- **Skip-location sets: identical** (48 nodes, junitxml `<skipped>` non-xfail,
  per-node diff A△B = ∅).
- **Complete xfail node-ID sets: identical** (15 nodes, diff = ∅).
- Accounting: 3640+48+15 = 3703 both stacks; **gap = 0**.

## 7. Phase 7 — Quality & cleanup (PASS)

| Gate | Result |
|---|---|
| `py_compile` (session.py + both test files) | OK ✓ |
| `git diff --check` | no whitespace errors ✓ |
| Scoped pre-commit (4 delta files) incl. detect-secrets | all Passed (incl. baseline hook) ✓ |
| `detect-secrets scan` delta files | 0 findings ✓ |
| Strict UTF-8 decode (4 delta files) | all valid; no mojibake ✓ |
| GitNexus analyze @ candidate | 33,497 nodes / 54,979 edges / 711 clusters / 300 flows; meta `lastCommit=5e91e973…` ✓ |
| GitNexus status @ candidate | 索引提交 5e91e97 == 当前提交 → ✅ 已是最新 ✓ |
| Candidate ref unchanged (post-run ls-remote) | `5e91e97326134805cc29b75492b187aae7c17985` ✓ |
| Protected refs | main `134ea59e…` unchanged; protected baseline object untouched ✓ |
| Cleanup | 4 task containers + 2 networks removed (0 task volumes existed); task DBs destroyed with containers; clone+venv+logs removed; GitNexus index removed (registry clean) ✓ |
| Host-owner resources | container count 65 == pre-task baseline 65; all host-owner stacks still Up/healthy; task ports 5598/5599/6498/6499 released ✓ |

## 8. Calibration record (full transparency)

Four full-suite executions total; the first two were invalid due to MY
verification-environment configuration, not candidate defects:

1. **Run 1** (29 collection errors + 8 failed): temp-DB opt-in env not yet
   configured; guard (`async_test_utils.py`, `test_dc11p1_…`) refuses
   non-disposable names/`mpango` user. Plus `test_pw1r3_rate_limit_context`
   429 test fail-open against its default Redis port 26379 (`PW1R3_TEST_REDIS_URL`
   documented default; nothing listening). Single-test diagnosis with the env
   var pointed at the task Redis → 1 passed.
2. **Run 2** (3659/29): `t_u1r1_test` bootstrap residue from Run 1 on the same
   DB caused 19 s3b live-proof tests to execute (pass) instead of skip.
   Proven by fresh-DB reset → canonical counts returned.
3. **Runs 3+4 (canonical, fresh DBs, full env)**: the §6 results — identical
   on both stacks.

No candidate code was modified at any point (HEAD stayed `5e91e973…`; tree
clean after every phase; mutation confined to the disposable worktree and
restored byte-identical).

## 9. Verification

Report branch `reports/dc12r1-mvp-l1-pw1-r4-a-r3-v2-lubuntu-independent-final-2026-08-16`; local and remote HEAD SHA identical (verified post-push).
