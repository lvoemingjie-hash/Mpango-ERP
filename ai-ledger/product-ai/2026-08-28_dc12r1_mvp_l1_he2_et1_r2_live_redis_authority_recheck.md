# DC-12R1-MVP-L1-HE2-ET1-R2 — Live Redis Authority and Child Recheck Closure

- Date: 2026-08-28 (+08:00); Executor: Zcode
- Task: DC-12R1-MVP-L1-HE2-ET1-R2
- Verification tier: V3_GOVERNANCE_AUTHORITY_SECURITY
- Claim ceiling: CANDIDATE_READY_FOR_KILO_REVIEW_ONLY
- Base: 2582750dedfb591e801703ff57bea69fbe91c605
- PRIOR_M0: 58b8e2ac9295eabd839790a1db1b38c768537f6c is marked
  **SUPERSEDED_BY_HE2_ET1_R2_REDIS_AUTHORITY_DEF** — the M0 rehearsal
  validated a tree whose Redis gate was URL-string parsing only; R2 closes
  that authority defect. The supersession is recorded here and in the R2
  protocol delta; the M0 report bytes are historical evidence, not a
  current clearance.
- Forbidden: no product source/dependencies/migrations, no protected-ref
  changes, no merge re-execution. Claim ceiling is candidate-readiness for
  Kilo review ONLY — this round grants no merge approval.

## 1. Defect closed

Before R2, `eval_redis` parsed `PW1R3_TEST_REDIS_URL` and probed only the
sentinel port; a mis-pointed or dead Redis passed preflight as long as the
URL string ended in `/15`. R2 makes the Redis gate a LIVE authority.

## 2. Runner authority (`harness-governance/validator/authority_runner.py`)

- `redis_live_check(url)`: URL present + well-formed (`redis`/`rediss`) +
  DB15 (wrong-DB traps BEFORE any connection); TCP connect to the URL's
  OWN host/port (`connect_failed` on any OSError — original exception
  never propagated); optional AUTH from URL credentials (`auth_failed`);
  `PING == PONG` (`ping_failed`); `SELECT 15 == OK` (`select_failed`);
  `DBSIZE == 0` (`db_nonempty`). Pure stdlib RESP (inline encode, simple/
  error/integer replies; error TEXT is dropped — servers may echo request
  bytes). TLS (`rediss`) supported via `ssl` wrap.
- `eval_redis(url)` = `redis_live_check` + sentinel-26379 unreachability
  (`sentinel_reachable`). Constants `REDIS_REQUIRED_DB`,
  `SENTINEL_PROBE_ENDPOINT` (probe endpoint patchable for tests only).
- Sanitization: every published artifact carries the fixed boolean
  category set `url_absent / url_malformed / wrong_db / connect_failed /
  auth_failed / ping_failed / select_failed / db_nonempty /
  sentinel_reachable / ok` — never URL, host, port, password, or any
  environment value (unit-proven: secret fixture absent from evidence,
  exception text, and host absent from published blobs).
- Whitelist: `EVAL_REDIS_LIVE` added to `EVALUATOR_WHITELIST`.

## 3. Child recheck (`harness-governance/tests/pytest_et1_collector.py`)

`_redis_recheck_problems(env)` performs the same live probe inside the
collect child and appends fixed `redis:*` labels to the sessionstart gate
problems; sentinel unreachability included. Redis disappearing after the
runner's preflight fails the CHILD closed: `pytest_sessionstart` exits
before collection, no proof file is written, the runner traps
(`no_child_proof`), and the authority command is never launched —
sentinel stays 0 (live-proven in RL5, including the child's recorded
`redis:*` problems in its sessionstart proof).

## 4. Registry / profile / schema (config cannot disable the check)

`TRAP_REDIS_WRONG_DB` extended in `inventory/execution-traps.json`:
evaluator `EVAL_REDIS_LIVE`, risk **P1**, status **ACTIVE** (the validator
enforces P0/P1 ACTIVE and profile-referenced — the check cannot be
retired via config), `applies_to` now `["runner.preflight",
"child.sessionstart"]`, exit 14 unchanged, required_evidence now names
the live probes and the credential-never-published invariant. The profile
`AUTHORITY_H2C_BACKEND` already references the trap. The schema needed no
change (the extension stays inside the existing draft-07 contract:
required_evidence is a free string array). The validator's mirrored
`ET1_EVALUATOR_WHITELIST` gained the single line `"EVAL_REDIS_LIVE"` so
the registry stays valid.

## 5. Truth-node proof matrix

Live (`tests/run_e2e_redis_cases.py`, fresh throwaway redis7, 6/6 PASS):

- RL1 fresh empty DB15 → full authority chain rc=0 FINISHED
  sentinel_calls=1.
- RL2 URL `/0` (same live server) → rc 14 VOID sentinel 0.
- RL3 redis stopped → rc 14 VOID sentinel 0 (redis confirmed down).
- RL4 one key seeded into DB15 → rc 14 VOID sentinel 0 (key removed
  after).
- RL5 preflight-era Redis up (`redis_live_check` ok) → container stopped
  → child sessionstart fail-closed (proof records `redis:*` problems) →
  collect trap → sentinel 0 → container restarted.
- RL6 temporary listener on 127.0.0.1:26379 → rc 14 VOID sentinel 0.

Unit (`tests/test_authority_runner_r2.py`, 15/15 OK, threaded fake RESP
server = REAL sockets, controlled replies):

- PING not PONG → `ping_failed` VOID.
- SELECT `-ERR` → `select_failed` VOID.
- AUTH `-WRONGPASS` → `auth_failed` VOID without leaking the secret.
- absent/malformed URL, unreachable port, non-empty DBSIZE, sentinel
  reachable/unreachable, GREEN auth path, registry contract
  (P1/ACTIVE/EVAL_REDIS_LIVE whitelisted in runner AND validator,
  profile-referenced).

## 6. Mutations (`tests/et1_r2_mutations.py`, wired into the gate)

R201 connect deleted · R202 PING skipped · R203 DBSIZE skipped · R204
connection errors swallowed (unreachable reports ok) · R205 child Redis
recheck deleted — each patches the candidate and a hermetic probe must
report the gate WEAKENED; pristine control RG-C01 holds all probes;
restores are sha256 + bytes verified. Gate total: **71 RED / 9 GREEN,
candidate tree byte-identical** (original 66 RED preserved).

## 7. Final gate table (fresh PG16 `he2et1r2_pg16` :15448 role `r2_gate`
rolsuper=f/createdb=t + fresh redis7 `he2et1r2_redis7` :16381; both
throwaway, removed after the round)

- unittests: **131/131 OK** (original 116 + 15 new).
- mutation gate: **71 RED / 9 GREEN** + RG-C01/E2E-GC01 pristine
  controls, tree integrity OK.
- runner `--self-test`: OK (now includes hermetic R2 categories).
- 8-case E2E core chain on the fresh stack: **8/8 PASS**.
- live Redis E2E: **6/6 PASS** (§5).
- structural validator: exit 0 PASS. release validator: exit 3 BLOCKED —
  attribution limited to the pre-existing P0/P1 debt
  (`DEBT-AUTH-CRITICAL-TUPLES`, `DEBT-COMMERCE-CRITICAL-TUPLES`), which
  this round neither adds to nor resolves.
- `git diff --check`: clean. detect-secrets vs `.secrets.baseline`: no
  new findings (baseline snapshot-protected). Strict UTF-8/no-BOM/no-NUL/
  no-U+FFFD/no-raw-0x97 over changed files: clean.
- Dual autocrlf: LF worktree all gates green; detached CRLF checkout
  (re-smudged, CR>0) re-ran self-test + 131 unittests + 71/9 gate + 8/8 +
  6/6 identically; restore proven byte-identical.
- GitNexus pre-edit impact: attempted, failed closed on index/CLI storage
  version skew (42 vs 40; same as R1) — documented; consumer census
  substitute (tracked ET1 tests, mutation anchors, plugin child, validator
  whitelist mirror). Post-commit `detect_changes` attempt recorded in the
  transcript with the same skew.

## 8. Verdict

**PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_R2_CANDIDATE_READY_FOR_KILO_REVIEW**

STOP. No merge is re-executed; candidate readiness for the Kilo bounded
review is the only claim. Task resources (both containers + volumes,
ports 15448/16381) are removed with cleanup proof below.

## 9. Resource cleanup proof

- `docker rm -f -v he2et1r2_redis7 he2et1r2_pg16` → both removed with
  anonymous volumes.
- Post-cleanup `docker ps -a | grep he2et1r2` → 0 containers;
  `docker volume ls | grep -ci et1` → 0.
- Port probes: 127.0.0.1:15448 CLOSED, 127.0.0.1:16381 CLOSED.
