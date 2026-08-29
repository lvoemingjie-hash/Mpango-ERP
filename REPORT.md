# REPORT — DC-12R1-MVP-L1-HE2-ET1-R3-A1-V2
## Lubuntu Independent Fresh-Runtime Authority-Profile Final

**VERDICT: `PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_R3_A1_V2_LUBUNTU_INDEPENDENT_FRESH_RUNTIME_AUTHORITY_PROFILE_FINAL`**

- **CANDIDATE:** `483b8ab01dae41d52404ebfe197e205a16d56e85` (= remote tip `origin/zcode/dc12r1-mvp-l1-he2-et1-r3-backend-cwd-tempdb-authority-preflight-closure-2026-08-29`)
- **BASE:** `cdb39e96a50b308aff91d4e94fd8526e7540d921` — CANDIDATE^ verified equal
- **TREE:** `4c55e375f4b831635b8cfc913b342a5f3956f633` (byte-identical before/after the round)
- **KILO_REVIEW:** `origin/reports/dc12r1-mvp-l1-he2-et1-r3-a1-v1-kilo-final-cumulative-governance-review-2026-08-30` = `db87f0d3eb55…` (expected prefix `db87f0d3` ✓)
- **EXECUTOR:** Lubuntu OpenCode2 (independent; Codex-L supervision only)
- **VERIFICATION_TIER:** `V3_INDEPENDENT_FRESH_RUNTIME_AUTHORITY`
- **CLAIM_CEILING:** `GOVERNANCE_AUTHORITY_FRESH_RUNTIME_PASS_ONLY`

---

## Phase 1 — Proof Gate: PASS

`git fetch --all --prune` rc=0. CANDIDATE, KILO_REVIEW, and BASE all
match the remote exactly; CANDIDATE^ == BASE. Fresh detached worktree
at the candidate; delta vs BASE is **exactly 17 harness-governance
files**; zero changes to product code, migrations, frontend/backend
tests, dependencies, or lockfiles. `git status --porcelain` = 0
throughout; the candidate was never modified.

## Phase 2 — Fresh Runtime: PASS (all conditions runner+child proven)

Task-exclusive stack `dc12r1he2f-*` (destroyed at close): PG16 on a
task port, Redis7 on a task port, dedicated containers/volumes/network.

| Condition | Proof |
|---|---|
| PG test role `rolsuper=false` | live `pg_roles` truth + runner `eval_pg_role` + child sessionstart |
| PG test role `rolcreatedb=true` | live `pg_roles` truth + runner `eval_temp_db` create/drop + child |
| Safe test DB name | DB name matches the candidate's `^(?:test\|pytest\|ci)[_-][a-z0-9_-]+$`; enforced by `backend_env_facts` in runner AND child |
| `MPANGO_ENV=test` | runner preflight + child sessionstart (`mpango_env` facts digest) |
| `MPANGO_TEMP_DB_ALLOWED_PORTS` contains the task PG port | enforced by runner + child via the shared probe; digest-bound |
| Redis DB15 `DBSIZE=0` before run | verified before GREEN; re-verified 0 after all suites |
| sentinel 26379 unreachable | before, during, after (RL6 proves the reachable case VOIDs) |
| CWD precisely bound | authority CWD = canonical `<worktree>/backend` (derived, non-symlink); collect child runs the entry shim with absolute PYTHONPATH; authority command launches with `cwd=authority_cwd`; all digest-bound |
| Credentials | task-private 0600 file in `/tmp` only; destroyed at cleanup; never in worktree/evidence |

Formal preflight: `--preflight-only` **PASS**, `state=PREFLIGHT`,
`backend_env_bound=true`, `alembic_expected_bound=true`
(`evidence/runner/preflight-only/`).

## Phase 3 — Authoritative GREEN: PASS

1. Real Alembic head = **`037_payment_declarations_schema`** exactly
   (profile-bound single head; DB migrated base→037 on the fresh stack).
2. **Core chain 8/8 GREEN** — including case 1 (real PG role + real
   pytest child, rc=0 FINISHED, sentinel=1) and case 8 (profile drift
   mid-flight VOID, sentinel=0).
3. **Redis authority cases 7/7 GREEN** (RL1 fresh-DB15 GREEN
   sentinel=1; RL2/RL3/RL4/RL5/RL6/RL7 all VOID sentinel=0; DB15
   DBSIZE=0 after the suite).
4. **The authority command launched exactly once** (`sentinel_calls=1`,
   `collect_child_spawns=1`) in the single `--authority` run: the full
   harness truth suite executed under the gate — **186/186 PASS**
   (`evidence/green/authority-command-junit.xml`).
5. Child↔runner consistency: `nonce_match=true`, `tempdb_match=true`
   (CWD/env/DB-name/port/allowlist digest), `alembic_match=true`
   (expected/actual/parent binding), `child_sha_match`
   candidate/profile/manifest all true.
6. Final state **FINISHED / exit 0**
   (`RUN_VERDICT=AUTHORITY_EXECUTED_GREEN`).

## Phase 4 — Independent Negative Controls: 17/17 items VOID-correct

Every live control: `RUN_VERDICT=VOID_ENVIRONMENT_PRECHECK` or the
matching fixed VOID category, authority command launch count **0**,
`sentinel_calls=0`, sanitized fixed-category output only. The candidate
was never modified; live controls used an isolated `/tmp` copy of the
tree (own throwaway git lineage) and task-private env inputs; the
drift/binding/byte-equality counterexamples used the candidate's own
executable fixtures.

| # | Control | Mechanism | Result |
|---|---|---|---|
| 1 | sibling CWD | isolated copy, `backend` renamed | rc=12 `cwd_not_canonical` VOID |
| 2 | symlink CWD | isolated copy, `backend` → symlink | rc=12 `cwd_not_canonical` VOID |
| 3 | MPANGO_ENV missing | env unset | rc=12 `mpango_env_missing` VOID |
| 4 | MPANGO_ENV wrong | `=staging` | rc=12 `mpango_env_invalid` VOID |
| 5 | allowlist missing | env unset | rc=12 `db_port_allowlist_missing` VOID |
| 6 | PG port not in allowlist | allowlist=5432 | rc=12 `db_port_not_allowed` VOID |
| 7 | unsafe DB name | `mpango_erp_test` | rc=12 `db_name_unsafe` VOID |
| 8 | CWD drift after preflight | live mid-flight rename | rc=18 phase=AUTHORIZED `drift_at_authorize` VOID |
| 9 | TEST_DATABASE_URL drift after preflight | candidate probes (launch-env-drift, runner/child digest compare) | counterexamples HELD |
| 10 | allowlist drift after preflight | port-membership probe + binding-digest drift test | HELD |
| 11 | SKU profile on 037 tree | `--profile-id AUTHORITY_SKU_M1_BACKEND` | rc=13 alembic head-drift VOID |
| 12 | expected head wrong | isolated-copy profile edit | rc=13 alembic VOID |
| 13 | expected parent wrong | isolated-copy profile edit | rc=13 alembic VOID |
| 14 | multi-head fixture | isolated-copy extra standalone revision | rc=13 `alembic_multiple_heads` VOID |
| 15 | prefix-similar / whitespace revision | candidate byte-equality fixtures | HELD (not byte-equal → rejected) |
| 16 | profile bytes drift after preflight | live mid-flight byte append | rc=18 phase=AUTHORIZED `profile_drift` VOID |
| 17 | child profile/migration recheck broken | candidate counterexamples (child benv + alembic recheck deletion) | HELD |

Raw sanitized outputs: `evidence/negctl/`.

## Phase 5 — 038 Evidence Boundary: enforced

The candidate contains **no real 038 product migration**. The SKU
profile was verified at schema, byte-binding, and fixture level only;
selecting it on this 037 tree VOIDs (control 11). **No real SKU-M1 038
product runtime PASS is claimed** — see `evidence/sku-038-boundary.md`.
The real 038 authority run is reserved for a future round after Codex-L
freezes an SKU candidate.

## Phase 6 — Auxiliary Gates: PASS

| Gate | Result |
|---|---|
| authority runner `--self-test` | OK, rc=0 |
| structural validator | exit **0** (structural=PASS) |
| release validator | exit **3** with exactly the two pre-existing debts (`DEBT-AUTH-CRITICAL-TUPLES`, `DEBT-COMMERCE-CRITICAL-TUPLES`) |
| `git diff --check` | clean |
| detect-secrets (read-only) | 12 findings, all `base_sha` git-SHA provenance hex strings in `protocol-deltas.json` — benign, no credentials |
| strict UTF-8 / no BOM / no NUL / LF | 17/17 delta files, 0 violations |
| candidate tree integrity | `4c55e375…` before == after |
| worktree clean | porcelain 0 (runtime debris removed) |

## Phase 7 — STOP conditions: none triggered

No frozen-ref mismatch; no authority launch without satisfied
preflight; the 037 profile went GREEN; wrong profile/head/parent/
multi-head never launched (sentinel=0); runner/child proofs consistent;
negative controls never incremented sentinel; evidence contains no
secret values; candidate bytes never drifted; the PASS required no
candidate modification; no fixture 038 proof was promoted to a real
SKU product claim.

## Cleanup (verified)

Both stacks' containers, volumes, and network destroyed; task ports
freed; sentinel 26379 unreachable; credentials file destroyed;
isolated-copy negative-control tree destroyed; worktree removed and
deregistered; frozen refs re-verified byte-identical at close. See
`evidence/cleanup/cleanup-evidence.txt`.

## Adjudication

All proof-gate, fresh-runtime, authoritative-GREEN, negative-control,
038-boundary, and auxiliary-gate requirements are met on an independent
Lubuntu fresh runtime with zero candidate modification. The expected
verdict is awarded:

**`PASS_FOR_CTO_DC12R1_MVP_L1_HE2_ET1_R3_A1_V2_LUBUNTU_INDEPENDENT_FRESH_RUNTIME_AUTHORITY_PROFILE_FINAL`**

Claim scope: `GOVERNANCE_AUTHORITY_FRESH_RUNTIME_PASS_ONLY` — no SKU
work resumed, no merge, no product full-suite, no Playwright, no
deployment.

**STOP.**
