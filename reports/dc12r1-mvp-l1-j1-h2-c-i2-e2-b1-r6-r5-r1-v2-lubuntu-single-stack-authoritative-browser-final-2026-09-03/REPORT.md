# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R6-R5-R1-V2 — Lubuntu Single-Stack Authoritative Browser Final

- Executor: OpenCode2 (Lubuntu), supervisor Codex-L, CTO authorization
  AUTHORIZE_LUBUNTU_SINGLE_STACK_SINGLE_PREFLIGHT_SINGLE_BROWSER_AUTHORITY
- Candidate: `6e96434ff11375d661417b7340dcb37508531f1d`
  (remote tip `zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r5-r1-host-authority-2026-09-02`)
- KILO_FINAL: `7ceda02de19e33c92732b69766701640ddc2dfec` (parent == candidate, verified)
- Verification tier: V4_INDEPENDENT_LINUX_BROWSER_RUNTIME_AUTHORITY
- Claim ceiling: AUTHORITATIVE_BROWSER_ONLY_AND_READY_FOR_CTO_MERGE_REHEARSAL
- Date: 2026-09-03 (+08:00)

## RESULT

**RESULT=TERMINAL_STOP_PRE_LAUNCH_HOST_PREFLIGHT_RED** (NOT_PASS; sanitized truthful report per MANDATORY_STOP).

The direct-process authority entrypoint was executed exactly once at the
exact candidate with a configured host. The runner-owned CORS preflight
probe passed (2xx, `Access-Control-Allow-Origin` exact). The runner-owned
host gate (`tools/host-preflight.mjs`, committed, spawned by the runner)
executed all four fixed checks in configured mode and returned **2 RED**
of 4; the runner-owned lifecycle preflight folded them in and VOIDed the
plane **before authorize** with `preflight_red:pg_role_unresolvable`,
launch starts = 0, **Playwright invocation count = 0**. Per MANDATORY_STOP:
no input correction, no check rerun, no stack swap, no reprovisioning, no
browser start; cleanup performed; this sanitized report published.

## REPORT_FIELDS

| Field | Value |
|---|---|
| CHANGED_OR_ADDED_TESTS_COVERING_NEW_PATHS | NONE_RUNTIME_ONLY |
| BACKEND_EVIDENCE_REUSE_CLASSIFICATION | PRIOR_LUBUNTU_BACKEND_EVIDENCE_REUSED_BY_BYTE_IDENTITY |
| FULL_SUITE_RESULT | REUSED_BY_BYTE_IDENTITY_NOT_RERUN |
| PREFLIGHT_INVOCATION_COUNT | 1 (runner-owned; ledger seq 2) |
| PLAYWRIGHT_INVOCATION_COUNT | 0 (STOP before authorize; REQUIRED_PASS not met) |
| STACK_COUNT | 1 (no backup stack; BACKUP_STACK_LIMIT=0 respected) |
| RECONCILIATION | NOT_REACHED (reconciliation is produced by the browser run; no launch) |
| SCANNER_RESULT | NOT_REACHED (artifact scanner runs inside the authority child) |
| CANDIDATE_TREE_INTEGRITY | tracked tree unchanged before==after (status porcelain empty, `git diff HEAD` empty for the whole task lifetime; untracked residue limited to gitignored `j1h2c-retailer-recovery/artifacts/` + `node_modules/`) |

## PROOF_GATE

- `git fetch --all --prune` performed.
- CANDIDATE == remote tip `zcode/...r6-r5-r1-host-authority-2026-09-02`; KILO_FINAL == remote tip
  `kilo/review/...r6-r5-r1-v1-kilo-bounded-delta-review-2026-09-03`; KILO_FINAL^ == CANDIDATE; CANDIDATE^ == `e16f39ca` (prior R4 candidate).
- Detached clean worktree created from CANDIDATE.
- Byte identity vs BACKEND_EVIDENCE_BASE `86f41b93a3aa0e3c55724b75fc2e2aa4c6dee35b`:
  `backend/` 0 changed files, `frontend/` 0, `backend/alembic*`+`backend/migrations`+`database/` 0, `backend/tests/` 0.
- Backend full suite NOT rerun (prohibition respected).

## CODE_PATH_TO_RUNTIME_EVIDENCE_MATRIX

| Committed code path | Runtime evidence from THIS task |
|---|---|
| `tools/browser-authority-entrypoint.mjs` direct-process boundary | executed directly once; stderr `{"authority":false,"category":"preflight_red"}` rc=1 (`evidence/authority-stderr.txt`) |
| entrypoint committed-byte checks (entrypoint/runner/cors/preflight/child/profile) | passed (run proceeded past startup into materialize/probe) |
| `materialize()` 15-field J1H2C_* contract materialization | passed (run reached preflight; contract reconciled 15/15, `evidence/contract-reconciliation.json`) |
| `corsPreflightProbe()` (B1-R6, process-isolated helper) | ledger seq 0: `cors_preflight ok=true status_2xx=true allow_origin_exact=true` |
| `#runHostPreflightModule()` (B1-R6-R5-R1 host gate) | ledger seq 1: `host_preflight ok=false checks=4 red=2`; configured=true; exactly four checks; first red `pg_role_unresolvable` |
| `preflight()` once-only + host coverage policy | ledger seq 2: `preflight ok=false red_checks=2 host_checks_present=4`; VOID before authorize |
| fail-stop VOID path | ledger seq 3: `void category=preflight_red:pg_role_unresolvable started=0`; starts preserved at 0 |
| `authorize()` / fixed real child / Playwright invocation marker | NOT_REACHED (by design of the fail-stop; PLAYWRIGHT_INVOCATION_COUNT=0) |
| reconciliation / artifact scanner / terminal seal | NOT_REACHED |

## NEGATIVE_AND_FAILURE_PATHS

Recorded by this run (value-firewalled evidence; counts and fixed categories only):

1. `pg_reachable` RED with fixed category `pg_role_unresolvable` — the host
   gate's parameter-safe psql role probe did not return a parsable role row
   (ledger seq 1 + seq 3 stop category).
2. One further host check RED (4 checks, 2 red); its fixed category is not
   persisted by design (the evidence firewall records counts, not per-check
   detail, on the failure path).
3. Subsequent behavior matched the committed fail-stop contract exactly:
   preflight RED → STOPPED → `authority:false` → rc 1 → zero spawns.

Root cause is NOT adjudicated in this task (MANDATORY_STOP forbids check
reruns/diagnostics here). Static, UNVERIFIED observations for the next
read-only forensics round (D1), clearly labeled as analysis-only:

- The host gate's role probe spawns `psql -X -A -t -v ON_ERROR_STOP=1 -v
  ON_ERROR_STOP=1 ... -v <vars> -c <sql>` relying on libpq env for the
  connection and on psql `:'var'` interpolation inside `-c`; any psql-level
  or connection-level failure surfaces identically as
  `pg_role_unresolvable`.
- `alembic_head_current` compares `alembic heads`/`alembic current` output
  against `/^[0-9a-f]+$/`; this repository's single head id is
  `037_payment_declarations_schema` (non-hex characters), which the regex
  cannot accept — a plausible static mismatch for the second RED (unverified;
  not persisted in evidence).

## ENVIRONMENT FACTS AT INVOCATION (sanitized)

- Single task stack: PostgreSQL 16 (task port 15422; database
  `test_dc12r1_b1r6r5r1v2_backend`; authority role `rolcanlogin=t`,
  `rolsuper=f`, `rolcreaterole=f`, `rolcreatedb=f`, `rolreplication=f` —
  matches the committed `ROLE_MUST_BE_FALSE` policy; temporary CREATEROLE
  was used only during migration application and revoked before the run),
  Redis 7 (task port 16322; DB15 DBSIZE=0; sentinel 26379 unreachable),
  backend healthz 200 (MPANGO_ENV=test, task port 18122), frontend SPA
  marker served (task port 15122).
- Alembic single head `037_payment_declarations_schema`, current == head.
- Task-private 1:1 maildir infrastructure: authority maildir mode 700 and
  EMPTY at invocation; every product delivery mirrored 1:1 to a raw task
  spool; scenario-scoped mailboxes only are mirrored into the authority
  maildir. No product byte modified.
- Provisioning: W1/W2 onboarded through the official public lifecycle with
  owner login proofs (200/200); both canonical codes product-generated and
  distinct; two fresh active W1 invitations created via the product's
  InvitationService; the retailer owner identity remained fresh and
  unregistered — formal login answered EXACTLY 401 pre-run (R44-aligned).
- Contract: task-private, schema-valid, profile↔contract 15/15 by env name,
  owner field sensitive, loopback-only hosts (no localhost/127.0.0.1 mix).
- Host descriptors: `J1H2C_HOST_PREFLIGHT=1` with the full descriptor set
  (PG host/port/db/user/role + PGPASSWORD + libpq PG* env, Redis
  host/port, backend dir, PID file + service token). Authority port
  ownership proven pre-run: PID file exact integer, process alive, command
  line carried the task service token.

## CLEANUP

Task containers and their anonymous volumes removed; no custom network was
created; all task ports released; task credentials, maildir, spool and
scratch destroyed; worktree deregistered and removed after publication;
protected refs re-verified (candidate/KILO/baseline/main unchanged,
candidate not merged). Closure evidence appended to `evidence/`.

## VERDICT

NOT_PASS_FOR_CTO — REQUIRED_PASS not met (PLAYWRIGHT_INVOCATION_COUNT=0;
15 BROWSER PASS / 2 STATIC PASS not reached). STOP. No merge, no deploy.
Next gate: CTO adjudication with D1 read-only forensics on the host-gate
failure path.
