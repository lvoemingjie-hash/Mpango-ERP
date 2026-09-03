# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R6-R5-R2 — Host Preflight Runtime Truth Closure

- Date: 2026-09-03
- Branch: `zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r5-r2-runtime-truth-2026-09-03`
- Base: `6e96434ff11375d661417b7340dcb37508531f1d` (the R5-R1 candidate; unchanged)
- Prior candidate: `6e96434f` — preserved untouched (no amend/rebase/force-push);
  this candidate is ONE ordinary commit on top of it.
- Verification tier: `V2_SOURCE_TEST_AND_FALSIFICATION_AUTHENTICITY`
- Claim ceiling: `CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW_ONLY`

## Confirmed causes closed (this round)

- `PSQL_C_COMMAND_CANNOT_PROCESS_PSQL_VARIABLE_INTERPOLATION` — FIXED.
  All psql SQL now enters the psql PREPROCESSOR through stdin
  (`psql ... -f -` with the SQL text on the child's stdin,
  `buildPsqlInvocation`/`psqlTransport`); no `:'placeholder'` can ever
  travel in a `-c` argument, and R47/R48 assert the absence of `-c` and
  the presence of the stdin text on every invocation.
- `PG_DESCRIPTOR_NOT_BOUND_TO_CONNECTION_TARGET` — FIXED. The connection
  target is EXPLICITLY bound: `J1H2C_HOST_PG*` become `-h/-p/-d/-U` argv
  elements built from the descriptors (R47 asserts each flag and value).
- ambient PG leakage — FIXED: `stripAmbientPgEnv` removes every ambient
  `PG*` variable (ANY letter case, with or without underscore) from the
  child environment; ONLY the task-bound `PGPASSWORD` survives (R47
  asserts PGHOST/PGDATABASE/PGUSER/PGOPTIONS/PGSERVICE stripped and
  PGPASSWORD preserved, and no ambient value anywhere in argv/stdin).
- `ALEMBIC_REVISION_HEX_ONLY_VALIDATOR_REJECTS_REAL_HEAD` — FIXED.
  `alembicRevisionsVerdict` accepts the real revision charset
  (`[A-Za-z0-9_]+`, e.g. `002_phase_b2_invitation_binding`), requires
  EXACTLY ONE heads revision and EXACTLY ONE current revision, and
  compares FULL whole-token revision IDs — a prefix match is never a
  match (R49 proves underscore GREEN, multi-head RED, diverged RED,
  prefix RED, empty/malformed RED).
- `REDIS_AUTHORITY_DOES_NOT_PROVE_DB15_EMPTY_OR_SENTINEL_UNREACHABLE` —
  FIXED. The REAL socket conversation (`redisConversation`) exchanges
  `PING -> +PONG`, `SELECT 15 -> +OK` and `DBSIZE -> :0` (task DB 15
  proven EMPTY); `redisSessionVerdict` fixes the categories
  (`redis_unreachable` / `redis_select_failed` / `redis_db15_not_empty` /
  `redis_protocol_invalid`); the sentinel on the SAME host at 26379 must
  be proven UNREACHABLE (`sentinelProbe` + `sentinelVerdict`,
  `sentinel_reachable` RED otherwise). R50 proves the full matrix over a
  REAL local socket fixture speaking the wire replies — no real Redis is
  ever started — plus a deterministic sentinel-reachability leg (the
  green session MUST fall through to the sentinel proof, which is the
  semantic detector for a skipped sentinel step).
- Full-RED persistence — FIXED (fix 9): the runner ledger persists ALL
  fixed RED categories of a failed preflight (`red_categories` on the
  `preflight` failure record and on the `host_preflight` record; labels
  only, never raw output or values). R51 proves two simultaneous core
  REDs both persisted with a matching count, VOID before authorize with
  spawn = 0, and a sanitized sink; R46(b) additionally asserts all four
  host RED categories persisted.
- Fix 10 (any exception VOIDs before authorize with child/playwright
  starts = 0) — preserved and re-proven: R51 asserts
  `STOPPED && launchStarts === 0` on the multi-RED path; R45/R46/R29
  re-run GREEN (unchanged machinery).

## Scope (exact — the seven authorized paths, nothing else)

1. `j1h2c-retailer-recovery/tools/host-preflight.mjs` (modified)
2. `j1h2c-retailer-recovery/tools/browser-authority-runner.mjs` (modified — red_categories persistence)
3. `j1h2c-retailer-recovery/tools/browser-authority-preflight-helper.mjs` (NOT modified — the fold interface is unchanged; listed as authorized, no change required)
4. `j1h2c-retailer-recovery/tools/check-browser-authority-contracts.mjs` (modified — R47-R51, R46(b) extension)
5. `j1h2c-retailer-recovery/tools/validate-static.mjs` (modified — step [16] runtime-truth anchors)
6. `j1h2c-retailer-recovery/README.md` (modified — runtime-truth contract section)
7. `ai-ledger/product-ai/2026-09-03_dc12r1_mvp_l1_j1_h2_c_i2_e2_b1_r6_r5_r2_host_preflight_runtime_truth.md` (NEW, this file)

No other file was touched. No amend/rebase/force-push. No product,
runtime, PG, Redis or browser execution (the psql transport is proven
with a capturing spawnSync double; the Redis session against a local
fixture socket speaking the wire replies; nothing real is ever started).
No scope expansion.

## CHANGED_OR_ADDED_TESTS_COVERING_NEW_PATHS

- R47 (NEW): REAL transport with a capturing spawnSync double — binary
  from the descriptor override; explicit `-h/-p/-d/-U` values; NO `-c`;
  `-f -` with the SQL text on stdin; ambient PG* stripped; PGPASSWORD
  preserved; no ambient value anywhere in argv/stdin.
- R48 (NEW): the REAL `defaultHostDeps().pgProbe` through the REAL
  transport — exactly four invocations (reach + role + one per
  invitation pair); role `:'authority_role'` placeholder on stdin with
  the value out of band via `-v`; both invitation pairs' placeholders on
  stdin, values out of band, never inside the SQL text; every invocation
  `-c`-free, `-f -`, explicitly bound.
- R49 (NEW): Alembic matrix — underscored full-ID GREEN (with the real
  `(head)` suffix), multi-head RED, diverged RED, PREFIX-match refused,
  empty heads/current RED, malformed charset RED, duplicated head lines
  RED.
- R50 (NEW): pure verdict matrix (PING/SELECT/DBSIZE/sentinel) plus the
  REAL socket driver against a local fixture server: green session ->
  `sentinel_reachable` (deterministic 26379 binding proves the sentinel
  step runs), wrong PING, SELECT refusal, non-empty DB15, malformed
  DBSIZE.
- R51 (NEW): two simultaneous core REDs -> `red_categories` persisted in
  full with a matching count, VOID before authorize with spawn = 0,
  sanitized sink.
- R46(b) (CHANGED): the host gate record must persist all four host RED
  categories.

## TEST_NODES_ADDED_OR_CHANGED

Added: R47, R48, R49, R50, R51. Changed: R46(b) (host red_categories
assertion). Unchanged: R1-R45, R29 truth, R44.

## CODE_PATH_TO_TEST_MATRIX

- `buildPsqlInvocation` / `stripAmbientPgEnv` / `psqlTransport` -> R47.
- `defaultHostDeps().pgProbe` -> `spawnPsql` -> the same builder +
  transport -> R48 (role + both invitation pairs, real wiring).
- `alembicTokens` / `alembicRevisionsVerdict` -> R49;
  `defaultHostDeps().alembicRevisions` feeds them the REAL spawn output.
- `redisConversation` / `redisSessionVerdict` / `sentinelProbe` /
  `sentinelVerdict` / `defaultHostDeps().redisProbe` -> R50.
- runner `preflight()` failure record + `#runHostPreflightModule` host
  record -> R51 / R46(b).
- VOID-before-authorize with spawn = 0 -> R51 (and R29/R45/R46 unchanged).

## NEGATIVE_AND_FAILURE_PATHS

`-c` carrying placeholders (refused by construction, asserted absent);
missing/ambient-redirected connection binding; ambient PG* leakage;
multi-head; diverged head; prefix "match"; empty/malformed alembic
output; wrong PING reply; SELECT 15 refusal; non-empty DB15; malformed
DBSIZE reply; reachable sentinel; dropped RED categories; values into
ledger text.

## FALSIFICATION_RESULT (seven mandated mutations, each RED at its
corresponding SEMANTIC assertion, then SHA-256-verified byte-identical
restore; final tree CLEAN — no dirty-vs-HEAD, anchor-missing or syntax
error substituted)

- Mutation "恢复 psql -c" (`-f -`/stdin replaced by `-c sql`): exit 1 —
  R47 "NO -c argument" + "SQL enters preprocessing via -f -" + "SQL text
  travels on the child stdin". RED (semantic).
- Mutation "删除显式 -h/-p/-d/-U": exit 1 — R47 "host explicitly bound
  via -h" / "-p" / "-d" (and -U). RED (semantic).
- Mutation "ambient PG target 替换" (strip disabled): exit 1 — R47
  "ambient PG* stripped from the child environment". RED (semantic).
- Mutation "恢复 hex-only Alembic regex": exit 1 — R49 "underscored real
  head == current GREEN" + "second real-shaped revision GREEN" (and the
  diverged leg). RED (semantic).
- Mutation "跳过 SELECT 15 或 DBSIZE" (session verdict reduced to PING):
  exit 1 — R50 "SELECT 15 refusal RED" / "wrong SELECT reply RED" /
  "non-empty DB15 RED". RED (semantic).
- Mutation "跳过 sentinel 检查": exit 1 — R50 "green session + reachable
  sentinel -> sentinel_reachable (the sentinel step really runs)". RED
  (semantic).
- Mutation "丢弃第二个 RED category" (`red_categories.slice(0, 1)`):
  exit 1 — R51 "ALL red categories persisted" + "red_checks count
  matches the persisted category list". RED (semantic).

## UNCOVERED_NEW_PATHS

0 within this round's scope. Disclosed environmental boundary: the
REAL psql binary, real Redis daemon and real alembic CLI are never
executed at source level (capture double + wire-replies fixture socket +
verdict units); their runtime behavior binds at the configured Lubuntu
gate. `FULL_SUITE_RESULT=NOT_RUN`. `BROWSER_RUNTIME=NOT_RUN`.

## Frozen gates (final candidate tree)

- GitNexus impact BEFORE edits: all LOW (`host-preflight.mjs`,
  `preflight`, `ControlPlane`, `runHostPreflight`, `redisProbe`,
  `alembicRevisions`, `pgProbe`, `parseHostPreflightPayload`).
- `pnpm install --frozen-lockfile` PASS; `pnpm run test:list` PASS
  (`Total: 15 tests in 1 file`, unchanged).
- `pnpm run validate:static` PASS — 16/16 (step [16] extended).
- `pnpm run check:neutrality` PASS — G1-G6.
- `pnpm run check:runtime-contracts` PASS.
- `pnpm run check:browser-authority` PASS — S0 + G + R1-R51.
- `pnpm run typecheck` PASS.
- `git diff --check` PASS; read-only detect-secrets: zero findings,
  `.secrets.baseline` SHA-256 `f49c86223abc95af12d0f6c60938050a68a84e332a
  94a444800cd93450bd16bf` unchanged; strict UTF-8, no BOM/NUL/CR, LF-only
  PASS over all changed files.
- GitNexus `detect_changes(scope=staged)` executed through the MCP server
  immediately before the final commit (staged candidate vs Base).
- Candidate tree byte-identical across all seven mutations.

## Verdict

`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R6_R5_R2_CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW`

STOP after publishing this candidate. NEXT_GATE=KILO_BOUNDED_DELTA_REVIEW.
