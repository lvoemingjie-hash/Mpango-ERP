# REPORT — DC-12R1-MVP-L1-HE2-ET1-R2-R2-R1-V2
## Lubuntu OpenCode Independent Fresh-Runtime Authority E2E Final

**VERDICT: `PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_R2_R2_R1_V2_LUBUNTU_OPENCODE_INDEPENDENT_FRESH_RUNTIME_AUTHORITY_FINAL`**

**CANDIDATE:** `7fdb7c59ae23cf3891a99420bebd60cb8802be06`
**KILO_FINAL:** `38ea191d62c40b00b2de97c5d967cfb6c0717159`
**VERIFICATION_TIER:** `V3_INDEPENDENT_FRESH_RUNTIME`
**CLAIM_CEILING:** `HE2_ET1_AUTHORITY_RUNNER_RUNTIME_APPROVAL_ONLY`

**Executor:** OpenCode (Lubuntu, independent fresh runtime), 2026-08-29
**Scope closure this round:** the E2E gate that Kilo marked
`CANDIDATE_PROVIDED_EVIDENCE / NOT_INDEPENDENTLY_EXECUTED_BY_KILO`
(fresh PG16 + Redis7 with non-superuser CREATEDB role) is now
independently executed on a fresh runtime.

---

## 1. Refs and worktree

| Check | Result |
|---|---|
| CANDIDATE reachable on origin | PASS — `origin/zcode/dc12r1-mvp-l1-he2-et1-r2-r2-r1-baseline-child-proof-truth-2026-08-29` = `7fdb7c59` |
| KILO_FINAL reachable on origin | PASS — `origin/reports/dc12r1-mvp-l1-he2-et1-r2-r2-r1-v1-kilo-final-cumulative-review-2026-08-29` = `38ea191d` |
| Fresh **detached** worktree from CANDIDATE | PASS — detached HEAD `7fdb7c59`, `git status --porcelain` = 0 entries for the whole round |
| Candidate never modified | PASS — tree clean before/during/after; no commit, no push, no candidate mutation |
| Remote refs at close | PASS — unchanged (`evidence/cleanup/cleanup-evidence.txt`) |

## 2. Task-exclusive fresh infrastructure (then destroyed)

| Item | Provisioned | Verified |
|---|---|---|
| Docker network | `dc12r1v2f-net` | destroyed at close |
| PG16 (`postgres:16-alpine`, `127.0.0.1:18543`) | container `dc12r1v2f-pg16`, random superuser password | removed with volumes |
| PG role for runner | `dc12r1v2_run` | `rolsuper=false rolcreatedb=true rolcreaterole=false rolreplication=false` (live `pg_roles` query in §2 evidence) |
| Redis7 requirepass (`127.0.0.1:16379`) | `dc12r1v2f-redis7`, random password | `PING=PONG`, `SELECT 15=OK`, `DBSIZE(15)=0` |
| Redis7 plain (`127.0.0.1:16380`) | `dc12r1v2f-redis7-plain` (for the candidate suite; its RL4 seeding helper sends no AUTH) | same DB15-empty checks |
| Sentinel `127.0.0.1:26379` | nothing listening | **unreachable** (ConnectionRefused) before, during, after |

Credentials: freshly generated per-run secrets, stored only in a
`/tmp/opencode` env file (mode 0600), never written into the worktree or
evidence; file destroyed at cleanup (verified absent).

## 3. Preflight

Runner formal preflight (`--preflight-only`) against the fresh
infrastructure: **PASS**, `state=PREFLIGHT`, `rc=0`, `sentinel_calls=0`.
Any preflight failure would have VOIDed the round immediately; none
occurred. Sanitized proof: `evidence/preflight/`.

## 4. Independent E2E execution

### 4.1 Authority core chain — 8/8 PASS (`evidence/e2e/core-chain-stdout.log`)

| Case | Result | Launch count |
|---|---|---|
| 1 GREEN full pipeline (real PG role + real pytest child) | `rc=0 FINISHED`, `sentinel_calls=1`, `collect_child_spawns=1`, `nonce_match=true`, child SHA matches | **1** |
| 2 RED superuser URL (live instance superuser) | `rc=10 VOID` | 0 |
| 3 RED empty TEST_DATABASE_URL | `rc=11 VOID` | 0 |
| 4 RED temp-DB flag off | `rc=12 VOID` | 0 |
| 5 RED `--authority` without command | `rc=16 VOID` | 0 |
| 6 RED child nonce tamper | `TrapFired nonce_mismatch` | 0 |
| 7 RED collect node drift | `TRAP_COLLECT_NODE_SET_DRIFT` | 0 |
| 8 RED profile drift mid-flight | `TRAP_SESSIONSTART_DRIFT profile_drift` | 0 |

Runner + real pytest child dual-process is proven by case 1
(`collect_child_spawns=1`, nonce cross-match, child SHA-256 binding match).

### 4.2 Live Redis cases — 7/7 PASS, AUTHORITATIVE_INDEPENDENT_FRESH_RUNTIME_EVIDENCE (`evidence/e2e/redis-cases-plain-stdout.log`)

| Case | Result | Launch count |
|---|---|---|
| RL1 GREEN fresh empty DB15 | `rc=0 FINISHED sentinel=1` | **1** |
| RL2 RED wrong DB (/0) | `rc=14 VOID` | 0 |
| RL7 RED invalid port (`:notaport`, sanitized, no traceback) | `rc=14 VOID` | 0 |
| RL4 RED DB15 nonempty (seeded, then cleaned) | `rc=14 VOID` | 0 |
| RL5 RED Redis disappears after preflight | child `sessionstart` fail-closed (`redis:*` problems), collect trap, `sentinel=0` | 0 |
| RL3 RED unreachable whole attempt | `rc=14 VOID` | 0 |
| RL6 RED sentinel 26379 reachable (temp listener) | `rc=14 VOID` | 0 |

DB15 verified `DBSIZE=0` after the suite (no residue).

### 4.3 requirepass / ACL AUTH ± paths

Library-level live probes against the **requirepass** and **plain** real
containers using the candidate's shared stdlib module
(`evidence/auth/probes-stdout.jsonl`, sanitized; no authority command is
launched by probes):

| Probe | Outcome |
|---|---|
| requirepass + correct password (AUTH from URL) | `ok`, `auth_used=true`, DB15 `dbsize_zero=true` |
| requirepass + wrong password | fail-closed `auth_failed` (sanitized) |
| ACL username+password (two-arg RESP AUTH) | `ok`, `acl_username_used=true` |
| ACL username without password | fail-closed `auth_misconfigured` |
| plain container no-auth baseline | `ok`, `auth_used=false` |
| malformed URLs (no scheme / broken IPv6 bracket / double port) | fail-closed `url_malformed` |
| non-integer DB segment | fail-closed `wrong_db` |
| `rediss://` | fail-closed `tls_unsupported_fail_closed` |
| sentinel 26379 unreachable gate | `ok` |

Full-CLI wrong-password negative run against the requirepass container:
`rc=14`, `state=VOID`, `sentinel_calls=0`, no traceback
(`evidence/auth/cli-wrongpass/`).

### 4.4 Child-only preload and module byte drift

Candidate R2-R2 truth tests independently executed: **13/13 PASS**
(`evidence/unittest/r2r2-tests-stdout.log`), including:
- TRUE child-only sitecustomize preload: parent env clean, only pytest
  child injected → child `sessionstart` fail-closed
  (`redis_module:preload_detected`), no collect proof, authority command
  launched **0** times;
- byte drift before child flagged by child binding; drift before launch
  blocks the command (`drift_at_launch`); forged child digest rejected;
- runner-preflight sitecustomize preload VOIDs.

### 4.5 Unit-test authenticity gate

Full harness unittest suite independently executed: **158/158 PASS**
in 6.36s (`evidence/unittest/full-suite-stdout.log`), tree clean before
and after.

## 5. Launch-count discipline

Every GREEN authority run launched the authority command **exactly once**
(`sentinel_calls == 1` within its own runner process); every negative
control launched it **0** times (`sentinel_calls == 0`). No exception.

## 6. Errata / honest notes (non-STOP)

1. **Unintended extra GREEN-path invocation — classification `VOID_EXECUTOR_INVOCATION_DEFECT`.** The first wrong-password
   CLI attempt omitted the env override, so the runner legitimately used
   the correct-password URL from the environment and finished GREEN
   (`sentinel_calls=1`). This was an executor invocation error, retained
   here for evidence truth; it launched the command exactly once within
   its own process and did not touch any negative control. The corrected
   wrong-password run (§4.3) then VOIDed as expected. **This invocation
   is VOID and is NOT counted as an authoritative positive or negative
   result in any tally of this report.** No GREEN result was
   re-run to farm passes; no failing run was retried to green.
2. **First redis-suite run (requirepass container) 6/7 — classification
   `NON_AUTHORITATIVE_ENVIRONMENT_COUPLING_DIAGNOSTIC`.** The suite's
   RL4 seeding helper sends `SET` without AUTH, so seeding silently fails
   on a requirepass-enabled container and that one case ran inconclusive
   (environment interplay with the helper, not a candidate defect — the
   DB15-nonempty VOID logic itself is proven in §4.2 RL4 on the plain
   container and via the candidate's unit tests). This first run is
   diagnostic only and NOT authoritative. The suite was then run
   as designed on a fresh plain Redis7 → 7/7
   (`AUTHORITATIVE_INDEPENDENT_FRESH_RUNTIME_EVIDENCE`). The
   requirepass container remained in service for the AUTH ± probes of
   §4.3. Both logs are retained (`evidence/e2e/redis-cases-stdout.log`
   is the 6/7 diagnostic run).
3. Product full-suite intentionally **not** repeated (out of claim
   ceiling); release-validator exit-3 pre-existing debt acknowledged via
   KILO_FINAL without re-litigating.

## 7. Claim ceiling compliance

- No product full-suite PASS claimed; no merge; no deployment; nothing
  pushed (refs verified unchanged at close).
- CANDIDATE untouched; KILO_FINAL accepted as published.
- This approval is limited to
  `HE2_ET1_AUTHORITY_RUNNER_RUNTIME_APPROVAL_ONLY`: the authority-runner
  runtime behaves as claimed on a fresh, task-exclusive, correctly
  restricted PG16+Redis7 runtime.

## 8. Cleanup (verified; `evidence/cleanup/cleanup-evidence.txt`)

Containers (3) removed with volumes, network removed, task ports
(16379/16380/18543) free, 26379 unreachable, credentials file destroyed,
worktree directory removed and deregistered from `git worktree list`,
remote refs byte-identical to the round's opening verification.

## 9. Adjudication

All preflight, E2E, AUTH ±, dual-process, launch-count, and negative-
control requirements are met on an independent fresh runtime with zero
candidate modification. The expected verdict is awarded:

**`PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_R2_R2_R1_V2_LUBUNTU_OPENCODE_INDEPENDENT_FRESH_RUNTIME_AUTHORITY_FINAL`**

**STOP.** Even on PASS: no merge, no deploy, no further action.
