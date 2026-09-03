# Kilo Bounded Delta Review — V3 (Source + Real Consumer Gate + Falsification Mutations)

- **Candidate:** `ddba2d3e` (DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R6-R5-R2 — host preflight runtime truth closure)
- **Base:** `6e96434f` (R6-R5-R1)
- **Reviewed by:** Kilo (zai-coding-plan/glm-5.3-flash), bounded-source review V3
- **Date:** 2026-09-03
- **Verdict:** `SOURCE_GATES_PASS__REAL_CONSUMER_GATE_EXECUTED_4_GREEN__MUTATIONS_7_OF_7_RED_BYTE_IDENTICAL_RESTORES`
- **Next gate:** `CODEXL_TARGETED_REAL_BOUNDARY_VALIDATION`

---

## 1. Delta verification (git truth)

| Claim | Verified |
|---|---|
| CANDIDATE^ == BASE (`6e96434f`) | YES (`git rev-parse ddba2d3e^` == `6e96434f…`) |
| Exactly 1 commit between BASE and CANDIDATE | YES |
| Remote tip == CANDIDATE on `origin/zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r5-r2-runtime-truth-2026-09-03` | YES |
| Delta = 5 modified + 1 new file | YES: `README.md`, `tools/browser-authority-runner.mjs`, `tools/check-browser-authority-contracts.mjs`, `tools/host-preflight.mjs` modified; `ai-ledger/product-ai/2026-09-03_…_host_preflight_runtime_truth.md` added |
| Claim ceiling respected | YES — no extra files touched |
| Clean detached worktree at CANDIDATE used for all verification | YES (`_dc12r1_mvp_l1_j1_h2_c_i2_e2_b1_r6_r5_r2_wt`, HEAD == `ddba2d3e`) |

## 2. Source review — closed facts (read line-by-line)

`tools/host-preflight.mjs` (778 lines, fully read):

- **psql runtime truth:** SQL reaches the psql preprocessor via stdin (`psql -f -`, SQL on child stdin, `input: ${sql}\n`); no `:'placeholder'` can ever travel in `-c` (argv hardcodes `-f`, `-` as the terminal elements; `psqlTransport` spawns `argv[0]` with `shell:false`, `windowsHide:true`, 20 s budget).
- **Explicit binding:** `J1H2C_HOST_PGHOST/PGPORT/PGDATABASE/PGUSER` become `-h/-p/-d/-U` argv elements; `descriptorMissing()` fails closed on any empty/missing descriptor → `*_descriptor_missing` RED.
- **Ambient strip:** `stripAmbientPgEnv` drops every `/^pg/i` key except `PGPASSWORD` (case-insensitive; only the task-bound password survives).
- **Parameter-safe invitation probes:** fixed relation/column SQL text; values travel only as `-v name=value` argv elements with `:'name'` interpolation on stdin; `invitationProbeIsParameterSafe` refuses any value that would appear inside the SQL text.
- **Semantic PG booleans:** `parsePgBoolean` normalizes `t/true/on/yes/1` (any case/space) → true, `f/false/off/no/0` → false, anything else → null → RED; role policy enforced as `rolcanlogin=true` + `rolsuper/rolcreaterole/rolcreatedb/rolreplication=false`.
- **Alembic runtime truth:** charset `[A-Za-z0-9_]+` (accepts real underscored revision IDs); EXACTLY ONE head, EXACTLY ONE current, FULL whole-token equality; distinct REDs for `alembic_multi_head` / `alembic_head_diverged` / `alembic_unresolvable`; prefix match refused.
- **Redis runtime truth:** REAL socket conversation `PING→+PONG`, `SELECT 15→+OK`, `DBSIZE→:0` (DB 15 proven empty); `sentinelProbe` on the SAME host at 26379 must be UNREACHABLE (`sentinel_reachable` RED otherwise); full RED matrix `redis_unreachable/redis_select_failed/redis_db15_not_empty/redis_protocol_invalid`.
- **PID ownership:** PID file must be a whole positive integer (`${pid}` === trimmed text), the recorded process must be ALIVE via `ps -p PID -ww -o args=`, and its command line must carry `J1H2C_HOST_SERVICE_TOKEN`; truncated/stale/foreign → distinct REDs.
- **Fail-closed taxonomy:** the four check IDs are frozen (`pg_reachable`, `redis_reachable`, `alembic_head_current`, `authority_ports_owned`); a missing/renamed id hard-fails the module (`failClosed`, exit 3); a removed implementation is `host_check_missing` RED, never a silent skip; output never contains any input value (checked before emit).
- **Runner side (`browser-authority-runner.mjs`):** host module path derived from the runner's own location, HEAD-committed-blob proof, fresh node child (fixed argv, `shell:false`, sanitized env, private stdin), exact-shape payload parser, DIRECT authority runs require exactly 4 configured checks (0/unconfigured/never-invoked → VOID before authorize, spawn = 0); ALL fixed RED categories persisted labels-only (`red_categories` on `preflight` and `host_preflight` ledger records).

## 3. Real consumer gate — EXECUTED on this host

Environment (fresh, isolated):

| Component | Detail |
|---|---|
| PostgreSQL 16 | `postgres:16-alpine` Docker, port 15460, fresh DB `mpango` |
| Schema | `alembic upgrade head` 001 → `037_payment_declarations_schema` (all 37 migrations applied; `alembic heads` == `alembic current` == `037_payment_declarations_schema`) |
| Authority role | `h2c_checker` — `rolcanlogin=t`, `rolsuper=f`, `rolcreaterole=f`, `rolcreatedb=f`, `rolreplication=f`; SELECT granted on public schema |
| Fixtures | `public.invitations` seeded with verified + unverified pairs (active, unused, not deleted) |
| Redis 7 | `redis:7-alpine` Docker, port 16380; DB 15 empty; **no sentinel on 26379** |
| Authority process | live `node` process; PID file (ASCII, whole positive integer); `J1H2C_AUTHORITY_SERVICE_TOKEN_2026` present in its command line (proven via `ps`) |
| psql client | standalone Windows `psql.exe` implementing exactly the invoked surface (`-X -A -t -v VAR=VAL -h -p -d -U -f -`, `:'var'` preprocessor interpolation, `ON_ERROR_STOP` exit semantics) — see §5 disclosure |
| ps client | standalone Windows `ps.exe` implementing `ps -p PID -ww -o args=` — see §5 disclosure |

**Result (module executed directly, real descriptors):**

```json
{"schema":"j1h2c/host-preflight-result/1","ok":true,"configured":true,
 "provided_by":"outer_authority_preflight",
 "checks":[{"id":"pg_reachable","ok":true,"category":"check_green"},
           {"id":"redis_reachable","ok":true,"category":"check_green"},
           {"id":"alembic_head_current","ok":true,"category":"check_green"},
           {"id":"authority_ports_owned","ok":true,"category":"check_green"}],
 "counts":{"total":4,"red":0}}
```

**Ambient-hostility proof (runtime strip):** with `PGHOST=169.254.99.99`, `PGDATABASE=ambient_bogus_db`, `PGUSER=ambient_bogus_user`, `PGPORT=1`, `PGOPTIONS`, `PGAPPNAME`, `pgservicefile` all injected into the parent environment, the module still returned **4/4 GREEN** — every ambient `PG*` variable was stripped and only the explicit `-h/-p/-d/-U` target was contacted. Also proven: role capability query, both invitation probes (verified + unverified) returned `n=1` through the real stdin interpolation path; first-run RED path also observed live (`authority_ports_pid_truncated` when the PID file was non-ASCII — module failed closed exactly as designed, see F-03).

## 4. Falsification mutations — 7/7 RED, byte-identical restores

Baseline: contract suite **PASSED** (S0 + G + R1–R51) on unmutated sources. SHA-256 baselines recorded; every restore verified byte-identical; suite re-run **PASSED** after the final restore.

| # | Mutation | Suite result | Semantic assertions hit |
|---|---|---|---|
| M1 | psql `-c` restored (SQL as `-c` arg, empty stdin) | **FAILED (11)** | `R47: NO -c argument`, `R47: SQL enters preprocessing via -f - (stdin)`, `R47: SQL text travels on the child stdin`, `R48: invocation N carries no -c`, `R48: reads stdin via -f -`, `R48: role/invitation placeholder reaches psql preprocessing via stdin` |
| M2 | `-h/-p/-d/-U` dropped | **FAILED (8)** | `R47: host/port/database/user explicitly bound`, `R48: invocation N binds host/port/database/user explicitly` |
| M3 | ambient PG* pass-through (`stripAmbientPgEnv` → identity) | **FAILED (1)** | `R47: ambient PG* stripped from the child environment` |
| M4 | hex-only Alembic charset `/^[0-9a-f]+$/` | **FAILED (4)** | `R49: underscored real head == current GREEN`, `R49: second real-shaped revision GREEN`, `R49: diverged head RED`, `R49: PREFIX match refused` |
| M5 | `SELECT 15` + `DBSIZE` skipped (bare PING) | **FAILED (3)** | `R50: real driver …` full-matrix verdicts (wire fixture answers only commands actually sent) |
| M6 | sentinel probe skipped (hardcoded unreachable) | **FAILED (1)** | `R50: green session + reachable sentinel -> sentinel_reachable (the sentinel step really runs)` |
| M7 | second RED category dropped from persistence (`.slice(0,1)`) | **FAILED (1)** | `R51: ALL red categories persisted` (only `["frontend_origin_unreachable"]` survived) |

Restores: `host-preflight.mjs` SHA-256 `A81AFB35A016B40C3B6FAC9350FF41483E92382B32489E0DE1DF951B9D0FD67E`, `browser-authority-runner.mjs` SHA-256 `7B9FFAF7C1C5B7135E6C042CA1B976F7546FCEB4EE971CCD547291B31A77AFE8` — both match HEAD blob hashes after every mutation cycle; `git status` clean.

## 5. Host adaptations disclosure (consumer-side only; candidate sources unmodified)

- Windows host had no `psql`/`redis-cli`. A minimal psql-compatible client (Python 3.12 + psycopg2, compiled via PyInstaller to a standalone `psql.exe`) was built to implement **exactly the flag surface the candidate invokes** (`-X -A -t`, `-v VAR=VAL` incl. `ON_ERROR_STOP`, `-h/-p/-d/-U`, `-f -` with SQL on stdin, `:'var'` preprocessor interpolation, non-zero exit on SQL error). The candidate's own contract tests independently prove the invocation shape via spawn capture (R47/R48), so the client choice does not weaken the transport assertions.
- `ps` is not POSIX-native on Windows; a `ps.exe` implementing `ps -p PID -ww -o args=` (via psutil) was built. The PID-ownership proof (live process + token in command line) was additionally demonstrated manually.
- `npm install` (no lockfile in repo; devDependencies exact-pinned) was used to run the candidate's own contract suite; the transient `package-lock.json` was removed after verification (tree pristine).
- Alembic run needed host-side env (`PYTHONUTF8=1` for GBK console, `REPORTING_USER_PASSWORD`) — environmental, not candidate defects (see findings).

## 6. Not executed (out of V3 scope / host limits)

- `FULL_SUITE_RESULT=NOT_RUN` (backend pytest, Playwright browser runtime) — out of bounded-delta scope.
- DIRECT end-to-end `browser-authority-runner.mjs` authority run (requires full browser stack + app servers): the in-scope consumer gate (the host preflight plane with real PG/Redis/Alembic/ps) was executed directly per §3; the runner-side plumbing is proven by the candidate's R43–R51 contract suite + my M1–M7 falsifications.
- GitNexus impact re-run: author recorded all-LOW + staged detect_changes LOW(12/0); not re-measured here (no local index for this candidate).

## 7. Conclusion

The candidate's delta does what its ledger claims: psql stdin preprocessing with explicit binding and ambient strip, underscore-tolerant exactly-one-head/current Alembic truth, real Redis session + sentinel-unreachable proof, sanitized full-RED persistence with VOID-before-authorize. All four checks returned GREEN against real PG16 + Redis7 + real migrations + real process ownership on this host; ambient-variable hostility was repelled at runtime; all seven mandated falsifications were caught by their named semantic assertions and reverted byte-identically. No blocking findings.

**Verdict: PASS_FOR_CTO — candidate CONFIRMED by Kilo bounded delta review V3 (source + real consumer gate). NEXT_GATE=CODEXL_TARGETED_REAL_BOUNDARY_VALIDATION.**
