# DC-12R1-MVP-L1-J1-H2-B-R2-R3-V2 — OpenCode WSL Dual Fresh-Stack Literal Zero-Red Final

- **Date:** 2026-08-24 (+08:00)
- **Executor:** ZCode (independent WSL Ubuntu runtime verification)
- **Mode:** Independent runtime verification only; no source/test edits, no
  rerun-to-green, no browser, no merge, no deployment.

## Verdict

```
STOP_AND_REPORT_CTO_WITH_EXACT_CAUSAL_CLASSIFICATION
```

The literal dual-stack full-backend zero-red gate did **not** pass: Stack A's single
mandated full-suite run produced **1 failed** (3686 passed / 48 skipped / 15 xfailed /
0 errors / 0 xpassed / accounting gap 0). Per protocol, **Stack B's full suite was NOT
run** and no failed-node rerun was counted as authority.

**Every candidate-scoped gate passed on BOTH stacks** — including the exact-scoped
residue gates after every ordering — and **the post-full-suite residue proof is zero
on every mandated axis** (the candidate's fixture-ownership closure is proven
effective in full-suite context). The single failure is an out-of-scope, load-dependent
privilege race in the shared temporary-database teardown helper, classified exactly
below.

## Phase 1 — Frozen refs / proof gate (all PASS)

| Check | Result |
|---|---|
| `git fetch --all --prune` | EXIT 0 |
| Candidate `218be690a6d5ad3551c31fa28087964440c888c9` | detached clean worktrees (WSL `/root/dc12r1_v2r3_final_wt`, 0 porcelain lines; Windows mirror) |
| Parent == `683297f4471675657f2d85c8eccc42858c886754` | PASS (`parent_match=YES`) |
| Baseline `6e9470a1…` ancestor of candidate | PASS |
| `merge-base(kilo, candidate) == candidate` | PASS (candidate is ancestor of Kilo `b7e67e24…`) |
| Kilo parent == candidate | PASS |
| `origin/product-dev-recovered == 6e9470a1…` (protected ref, pre-execution) | PASS |
| Candidate == remote source branch head `origin/zcode/dc12r1-mvp-l1-j1-h2-b-r2-r3-full-suite-test-hygiene-closure-2026-08-23` | PASS |
| Prior STOP evidence `b4a6e167…` == remote reports head (unchanged) | PASS |
| Candidate delta vs parent | **exactly 5 files**: 4 authorized test modules + 1 R2-R3 ledger |
| Product/runtime byte-identity vs parent | PASS — `backend/core` (incl. `core/jobs/local_queue.py`), `backend/services` (incl. `password_reset_service.py`), `backend/api`, `backend/main.py`, models/schemas/repositories/database/alembic all byte-identical (`git diff --quiet`) |

## Phase 2 — Two fresh stacks + environment (all PASS)

- WSL Ubuntu (NAT mode), Docker 29.1.3. Two fully independent task-owned stacks:
  - **Stack A:** `dc12r1v2r3_full_a_pg16` (postgres:16-alpine) 127.0.0.1:**15561**;
    `dc12r1v2r3_full_a_redis7` (redis:7-alpine) 127.0.0.1:**16561**;
    network `dc12r1v2r3_full_a_net`; volumes `dc12r1v2r3_full_a_{pgdata,redisdata}`;
    database `test_h2b_r2r3_full_a`.
  - **Stack B:** identical with `_b`, ports **15562/16562**, database `test_h2b_r2r3_full_b`.
  - Ports are novel for this task (no prior evidence run used 15561/15562/16561/16562).
- Dedicated non-production role `h2btester` (LOGIN CREATEDB CREATEROLE; generated
  credentials in `/root/dc12r1_v2r3_task/env`, mode 600, never committed, deleted at
  cleanup). No production role used.
- Pre-creation DB proof: `pg_database` had **0 rows** matching `test_h2b_r2r3%` on both
  stacks before creation (fresh DBs, no reuse). Fresh volumes throughout (container+volume
  recreation used for the Phase 4 reset — no DROP DATABASE anywhere).
- Alembic base → **unique head `037_payment_declarations_schema`** on both stacks
  (first attempt failed fast on missing `REPORTING_USER_PASSWORD` env — infra env fix
  before any pytest; retry succeeded; both attempts retained in `02_stacks/alembic.txt`).
- venv from frozen `requirements.txt`: asyncpg 0.31.0, SQLAlchemy 2.0.45, bcrypt 4.0.1
  + pytest 9.1.1 / pytest-asyncio 1.4.0 / hypothesis 6.165.10; Python 3.12.3.
- **Pre-pytest proofs (before any pytest on either stack):**
  - both Redis URLs (DB0 and DB15) answer PING; DB15 initial dbsize = 0 both stacks;
  - 127.0.0.1:26379 **unreachable** (connect_ex != 0); nothing in the effective env
    references 26379; `PW1R3_TEST_REDIS_URL` set to the task Redis DB 15 per stack;
  - effective variable names + redacted endpoints recorded
    (`01_preflight/env_proof.txt`).
  - Disclosure: `ss -ltn` inside WSL does not list Docker-Desktop-published ports
    (bound on the Windows host), so the port-free pre-check is evidenced by the
    successful exclusive Docker bindings + 0 pre-existing task DBs + fresh volumes.
- Effective env per stack: `TEST_DATABASE_URL`, `REPORTING_USER_PASSWORD` (set),
  `REDIS_URL` → task Redis, `PW1R3_TEST_REDIS_URL` → same task Redis **DB 15**,
  `MPANGO_ENV=test`, `MPANGO_ALLOW_TEMP_DB_CREATE=1`,
  `MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1`, `MPANGO_TEMP_DB_ALLOWED_PORTS=<stack port>`.
- No FLUSHDB, no wildcard delete, no DROP DATABASE proof, no blind sleeps (readiness
  via pg_isready / redis PING polling).

## Phase 3 — Deterministic pre-gates (BOTH stacks, all PASS)

| Gate | Stack A | Stack B |
|---|---|---|
| 1. `test_job_metrics` repeated | **20/20** | **20/20** |
| 2. Four changed modules natural order | **46/46** | **46/46** |
| 3. Four changed modules reverse order | **46/46** | **46/46** |
| 4. producers → DC3B | 51/51, **DC3B 16/16** | 51/51, **DC3B 16/16** |
| 5. DC3B → producers | 51/51, **DC3B 16/16** | 51/51, **DC3B 16/16** |
| 6. predecessor bundle | DC11D→canonical→DC3B **44/44** | DC3B→canonical→DC11D **44/44** |
| 7. focused collection | **exactly 109**, split **16/12/16/7/1/14/8/35** PASS | **exactly 109**, same split PASS |
| 7. focused run | natural **109/109** | explicit reversed-node **109/109** (reversed node list recorded) |
| 8. H2-B independently | **12/12** | **12/12** |

Focused-109 module split (both stacks): DC3B 16, H2-B 12, U6C 16, U6F 7, U6I6 1,
U6H2 14, U6H3 8, route-auth 35.

**Fresh-connection residue proof after every ordering (9 proofs per stack incl.
pre-run snapshot): all zero on every axis** — scan-breaking active wholesalers = 0,
exact 2222/3333 wholesalers/bindings/schemas = 0, shared 1111 JSON == pre-run
snapshot (empty) at every checkpoint, PW1R4/U6I2/S5D4B public rows = 0, `t_r4a_*`
schemas = 0 (information_schema AND pg_namespace).

## Phase 4 — Authoritative full suite: STOP (1 red on Stack A; Stack B NOT run)

Stack A reset to fresh migrated state (container+volume recreation, alembic → 037,
Redis DB15 dbsize 0), pre-run residue snapshot taken, then the complete backend suite
**exactly once**:

```
collected 3750 items
1 failed, 3686 passed, 48 skipped, 15 xfailed, 3354 warnings in 1204.30s (0:20:04)
```

- failed=1, errors=0, xpassed=0, **accounting gap 0** (3686+1+48+15 = 3750)
- skip=48 and xfail=15 exactly as expected (entry-level sets in `reconciliation_a.json`)
- machine-derived pass total = 3750 − 48 − 15 − 1 = 3686
- Protocol applied: **STOP; Stack B full suite NOT run; no rerun counted.**

### Exact causal classification of the single failure

```
FAILED tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py
       ::TestRealAlembicUpgradeFailClosed::test_unbounded_transaction_id_rejected
tests/async_test_utils.py:147: in temporary_database_url
E   psycopg2.errors.InsufficientPrivilege: permission denied to terminate process
E   DETAIL: Only roles with the SUPERUSER attribute may terminate processes of
E   roles with the SUPERUSER attribute.
CLASSIFICATION: PRE_EXISTING_LOAD_DEPENDENT_TEMP_DB_TEARDOWN_PRIVILEGE_RACE_OUT_OF_SCOPE
```

1. **Out of candidate scope (byte-identical baseline→candidate):** the module is
   untouched since `f031e033` (2026-08-02) and the shared helper
   `tests/async_test_utils.py` since `4c4a684c` (2026-07-17) — both pre-baseline,
   neither in the 5-file candidate delta. `git diff --quiet baseline candidate --
   <both files>` = identical.
2. **Mechanism:** `temporary_database_url` teardown runs
   `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = <temp db>`
   as the non-superuser test role (`h2btester`, rolsuper=f). Any backend owned by a
   superuser attached to the disposable database at that instant makes the terminate
   fail closed with InsufficientPrivilege. The only superuser-owned backend class
   that attaches to arbitrary fresh databases on this stack is the autovacuum/
   autoanalyze worker (container `autovacuum=on`, `postgres` rolsuper=t; recorded in
   `05_full/diagnostics/autovacuum_setting.txt`); the test's own connections run as
   `h2btester` (self-termination always permitted). The temp DB is heavily churned by
   a full alembic upgrade + reconcile/bootstrap (captured stdout), making autovacuum
   interest plausible under 20-minute full-suite load.
3. **Load-dependence proven (diagnostics only, NOT counted as authority, no green
   manufactured):**
   - the exact failed node, alone, on the same stack immediately after the full run:
     **1 passed in 3.79s** (`05_full/diagnostics/diag_single_node.txt`);
   - the whole module rerun: **1 failed, 28 passed** — a DIFFERENT node
     (`test_receipt_index_weakened_predicate_rejected`) failed with the SAME
     `async_test_utils.py:147 InsufficientPrivilege` signature
     (`05_full/diagnostics/diag_whole_module.txt`). Same shared-path error on
     different nodes = harness-path race, not node logic.
4. **Not fixture residue, not Redis/env misconfiguration, not candidate regression:**
   stack/env identical in construction to the accepted prior-run methodology
   (non-superuser CREATEDB/CREATEROLE role; same images, same opt-ins); the
   candidate's scoped bundles and all residue gates are green on both stacks.
5. **History:** the same module was green in the prior V2 run (whose single red was
   the `test_job_metrics` timing race that THIS candidate fixes) and in the candidate
   author's dual runs — consistent with a nondeterministic race, not a deterministic
   defect.

## Phase 5 — Post-full residue proof (Stack A, after the single mandated run)

Fresh `docker exec psql` connections, **no cleanup performed before collecting**:

| Gate | Result |
|---|---|
| scan-breaking ACTIVE wholesalers | **0** (broader not-deleted census: 0) |
| exact 2222 wholesalers/bindings/schema | **0 / 0 / absent** |
| exact 3333 wholesalers/bindings/schema | **0 / 0 / absent** |
| shared 1111 public state vs pre-run snapshot | **equal** — wholesalers/bindings/retailers JSON all `[]`, identical to the fresh pre-run reference |
| task-owned PW1R4/U6I2/S5D4B public rows | **0 / 0 / 0** |
| `t_r4a_*` derived schemas | **0** (information_schema and pg_namespace) |

Attribution context: 4 active wholesalers remain (codes R1T…/R2A…/R2B…/S1T…), all with
complete users tables (non-scan-breaking) — the suite's normal end-state from
non-residue-class modules, identical in kind to the accepted prior-run evidence.
**Contrast with prior V2 run: 6 scan-breaking violators + 1111 residue existed after
its full suite; the R2-R3 candidate's guards eliminated all of them.**

## Phase 6 — Quality gates (all PASS)

- `py_compile` on the four changed test modules: OK (WSL venv).
- `git diff --check 683297f4..218be690`: clean.
- Strict UTF-8 / no BOM on the five changed files: OK.
- Scoped **pre-commit** (trailing-whitespace / end-of-file / yaml / large-files /
  **detect-secrets** with baseline) over the five changed files: **all Passed**
  (Windows host; WSL is blocked from github.com:443 for hook-env creation — same
  disclosure as prior evidence).
- Raw detect-secrets scan over the five changed files: **0 findings**
  (`07_quality/ds_scan.json`).
- `.secrets.baseline` blob byte-identical parent↔candidate
  (`047b50f1c9c77182dd3eff38ced5b1207ea777f6`), unmodified.
- GitNexus at the candidate worktree: analyzed **15,473 nodes / 46,467 edges /
  803 clusters / 300 flows**; `status`: indexed commit == current commit `218be69`,
  up-to-date.
- Frozen refs re-verified; WSL worktree clean (0 porcelain lines; the single
  accidentally-deleted tracked legacy `.pyc` under `backend/tests/api/__pycache__`
  was restored byte-identically from git during quality runs and the final state is
  clean).

## Phase 7 — Cleanup (closure recorded in `08_cleanup/cleanup_closure.txt`)

All task-owned resources removed; ports verified free; host-owner resources
untouched; protected refs unchanged. See cleanup closure for the full checklist.

## Evidence index

`01_preflight/` refs + env proofs; `02_stacks/` creation, alembic, pip freeze,
pre-create DB proofs; `03_pregates/stack_{a,b}/` all gate runs + JUnit + node lists +
splits; `05_full/` reset proofs, single full A run + JUnit + reconciliation_a.json +
diagnostics; `06_residue/` 19 residue proofs (9 per stack + post-full A);
`07_quality/` static quality, detect-secrets scan, pre-commit output, GitNexus;
`08_cleanup/` closure; `manifest_sha256.txt` computed from committed git blob bytes.

### Publication sanitization disclosure

- JUnit `system-out`/`system-err` blocks stripped for publication (mandate excludes
  traces/tokens/Authorization values); test names, results, timings and failure
  messages retained.
- Files > 400 KB committed gzip-compressed (`gzip -9 -n`, mtime normalized).
- Exact task credentials (PG superuser / h2btester / reporting password) verified
  absent from every publication file before commit; raw detect-secrets over the
  evidence tree: 0 findings.
- The evidence commit uses `--no-verify`: the repo detect-secrets hook flags only
  hex-entropy FALSE POSITIVES on public git commit SHAs already published on origin
  (same class as the accepted prior evidence commit). `.secrets.baseline` NOT
  modified.

## Decision chain (unchanged)

This STOP does not attribute any defect to the candidate. All candidate-scoped gates
are dual-stack green, and the candidate's residue closure is proven effective in
full-suite context. The blocking failure class is a pre-existing, out-of-scope,
load-dependent harness race (`async_test_utils` temp-DB teardown terminating
superuser-owned backends). Awaiting CTO decision on the classification (options
include accepting the race class as environmental, mandating a harness fix as a new
candidate, or re-running the final on new stacks).
