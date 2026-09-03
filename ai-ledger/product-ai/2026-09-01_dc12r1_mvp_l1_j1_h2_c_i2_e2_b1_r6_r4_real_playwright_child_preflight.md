# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R6-R4 - Real Playwright Child and Runner-Owned Preflight Authority Closure

- Date: 2026-09-01
- Branch: `zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r4-real-playwright-child-preflight-authority-2026-09-01`
- Base: `854c680e6fab56e6b1f33a00350a155c443eb3e4` (tip of `origin/zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r3-authority-entrypoint-2026-09-01`)
- Kilo publication: `baf891ef7931b433c84f99d5d5d418f8d57d9bd4` (parent == Base, verified)
- Verification tier: `V3_MERGE_CRITICAL_BROWSER_AUTHORITY_CONTROL_PLANE`
- Claim ceiling: `CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY`

## Phase 2 — Confirmed defects (recorded, not retracted)

- `CONFIRMED_DEFECT_1 = FIXED_AUTHORITY_CHILD_DOES_NOT_EXECUTE_PLAYWRIGHT`
  At Base, `tools/browser-authority-child.mjs` was an intentionally tiny
  stdin-echo process: it validated the input shape and returned
  `rc=0 + reconciliation.complete=true` without spawning anything.
- `CONFIRMED_DEFECT_2 = DIRECT_ENTRYPOINT_PREFLIGHT_USES_CALLER_INDEPENDENT_HARDCODED_TRUE_CHECK`
  At Base, `tools/browser-authority-entrypoint.mjs` line 191 executed
  `control.preflight([{ ok: true, label: 'entrypoint_direct_process' }])` —
  a caller-independent hardcoded true check standing in for real preflight.
- `PRIOR_KILO_RESULT = SOURCE_VALID_FOR_DIRECT_PROCESS_AUTHORITY_BOUNDARY_ONLY`
  — retained; the Kilo conclusion about the authority boundary is NOT
  retracted, and it is NOT promoted to a browser-runnable conclusion.
- `BROWSER_AUTHORITY_STATUS = NOT_YET_EXECUTABLE`

## Scope (exact)

- `j1h2c-retailer-recovery/tools/browser-authority-entrypoint.mjs` (modified)
- `j1h2c-retailer-recovery/tools/browser-authority-runner.mjs` (modified)
- `j1h2c-retailer-recovery/tools/browser-authority-child.mjs` (rewritten — real child)
- `j1h2c-retailer-recovery/tools/browser-authority-preflight-helper.mjs` (NEW)
- `j1h2c-retailer-recovery/tools/check-browser-authority-contracts.mjs` (modified — R30-R40)
- `j1h2c-retailer-recovery/tools/validate-static.mjs` (modified — step [15])
- `j1h2c-retailer-recovery/README.md` (modified — B1-R6-R4 section)
- `ai-ledger/product-ai/2026-09-01_dc12r1_mvp_l1_j1_h2_c_i2_e2_b1_r6_r4_real_playwright_child_preflight.md` (NEW, this file)

No profile, no schema file, no package.json, no script, no backend,
frontend, migration, product test, product candidate, 15-node spec,
17-node inventory, Playwright config or pnpm lockfile was modified.
No amend/rebase/force-push. No Lubuntu browser gate started.

## Implementation notes

Real child (`browser-authority-child.mjs`):

- Fixed argv discipline: refuses any invocation that is not exactly
  `[node, THIS FILE]` (realpath-compared), before anything else.
- Playwright CLI resolved ONLY from the module-anchored frozen install
  `../node_modules/@playwright/test/cli.js`, package version pinned to the
  frozen `1.49.1`; refusal category `playwright_cli_unresolvable`.
- Playwright spawned as `[execPath, cli, 'test']` — argv array,
  `shell: false`, stdio silenced (values can never leak through the child's
  own stdout), cwd = canonical repo root.
- Atomic once-only marker `<repo>/artifacts/authority-invocation.json`
  created with flag `wx` BEFORE the spawn, recording
  `playwright_invocation_count = 1`, run id, candidate SHA, wrapper PID and
  start time; a second start is refused pre-spawn
  (`playwright_invocation_exceeded`).
- Input schema strict and exact: `{schema, input_sha, cwd_sha, candidate_sha,
  owner_email_label, values}`; the 15 `values` keys must equal the canonical
  profile keys exactly; the child RECOMPUTES `input_sha` over
  `{owner_email_label, values}` (cross-process binding of the runner's
  materialized input), re-derives `cwd_sha` and re-resolves the candidate
  with a GIT_*-stripped argv-array `git rev-parse HEAD`.
- Subprocess environment: every `NODE_*` and `GIT_*` variable stripped in
  ALL letter cases; every non-authorized `J1H2C_*` stripped; the 15 exact
  profile-mapped `J1H2C_*` values set.
- Awaits the real PID/exit (never pre-classified); rc != 0 → RED result.
  rc == 0 still must pass: intact marker + unchanged candidate; fresh
  (`>= marker start`) reconciliation.json + reconciliation.csv +
  results.json + results-junit.xml; reconciliation = 15 BROWSER PASS +
  2 STATIC PASS + total 17 + gap 0 + PRECONDITION_PASS + zero
  FAIL/NOT_RUN/PENDING (node list and CSV content matched exactly);
  JSON reporter stats `expected=15, unexpected=0, skipped=0, flaky=0`
  (Playwright 1.49.1 shape); JUnit `tests="15"`, `failures="0"`,
  `errors="0"`, `skipped="0"`, no `<failure`/`<error`; artifact scanner
  spawned from the frozen tools directory (exact argv, exit 0 +
  `ARTIFACT SCAN PASSED`). Only then `complete=true, exit 0`.
- Wrapper PID, Playwright PID, awaited exit and candidate SHA are
  cross-bound in the exact result payload; the runner re-verifies the
  wrapper binding, the Playwright binding invariants and the candidate
  equality (`authority_child_candidate_mismatch` → TEST_RED).
- The child never writes PASS reconciliation artifacts itself.

Runner-owned preflight (runner + `browser-authority-preflight-helper.mjs`):

- `preflight()` now takes NO caller input; any argument is refused
  (`preflight_input_rejected`). The runner derives the helper path from its
  own module location (`canonicalPreflightHelperPath`), proves the helper's
  committed-blob equality (`preflight_helper_dirty_vs_head`) and spawns a
  fresh node child — argv array, sanitized env, private stdin.
- Helper checks (fixed ids, fixed order): frontend origin page (real SPA
  marker), backend `/healthz`, maildir exists + writable + EMPTY, W1/W2
  canonical format + distinct, identity distinctness after
  trim+lowercase normalization, invitation code/phone pairs present +
  pairwise distinct, forged token not reused against any of the other 14
  values, established retailer login through the FORMAL API
  (`POST /api/v1/client/auth/login` → 200), unverified identity still
  refused (status ≠ 200). Categories/labels/booleans/counts only —
  never URLs, emails, passwords, tokens or codes.
- Host-level checks (PG, Redis, Alembic head, port ownership) are NOT
  executed by the helper. They are specified as a task-private execution
  contract interface (`host_preflight` block with ids `pg_reachable`,
  `redis_reachable`, `alembic_head_current`, `authority_ports_owned`) to be
  satisfied by the OUTER authority preflight in the future Lubuntu task;
  malformed blocks fail closed; absence is reported transparently as
  `host_checks_present = 0`. No infrastructure was started this round.
- The runner validates the helper payload with an exact-schema parser
  (`parsePreflightHelperPayload`): fixed taxonomy, no duplicates,
  counts consistency, `ok:true` only with every core check green; any
  RED check → STOPPED/VOID before authorize with starts = 0
  (`preflight_red:<category>`); helper crash/timeout →
  `preflight_helper_no_response`.
- Helper spawn is ASYNC (`execFile`) — a synchronous wait would freeze the
  parent event loop and deadlock the very origins the helper probes (the
  same closure the CORS probe already carries). This bit us during
  verification and is itself evidence for the process-isolation design.
- Post-binding drift: the control plane snapshots the working-tree bytes of
  entrypoint, runner, CORS helper, child and preflight helper at
  construction and re-verifies at authorize and launch
  (`authority_module_byte_drift`), so a swapped helper or child can never be
  launched.
- The preflight helper joined `authorityCriticalPaths` (HEAD-blob proof at
  the entrypoint boundary and at capability minting).

## Phase 5 — R30-R40 (all GREEN, real module/process tests, no copied implementation)

- R30 fixed child launches a FAKE frozen Playwright executable
  (`node_modules/@playwright/test/cli.js`, version 1.49.1) — PID awaited and
  cross-bound against the CLI's own spawn proof; fixed argv `['test']`;
  invocation_count = 1; candidate + wrapper bound; full consistent evidence
  set → complete=true, exit 0.
- R31 extra argv refused pre-spawn (spawn proof absent); env path overrides
  (`PLAYWRIGHT_CLI_PATH`, `J1H2C_BROWSER_AUTHORITY_CHILD`) ignored by
  construction.
- R32 second invocation refused BEFORE spawn; spawn count still exactly one.
- R33 rc=0 without genuine reconciliation → complete=false
  (`reconciliation_json_missing`).
- R34 forged PASS reconciliation (stats lie) refused; wrong candidate
  refused pre-spawn; stale mtimes refused; tampered run id refused.
- R35 scanner missing / scanner nonzero → complete=false.
- R36 helper omission refuses authority (`working_tree_dirty_vs_head`);
  forged helper payloads refused by the exact parser matrix (extra key,
  missing core check, unknown id, duplicate id, forged ok=true over RED,
  ok=false without red, counts mismatch; valid core/host matrices accepted);
  repeat preflight terminal; host-block interface folds RED/GREEN and fails
  closed on malformed blocks.
- R37 nine failure modes (frontend down, health down, owner login denied,
  unverified login allowed, maildir non-empty, W1==W2, identity collision,
  invitation collision, forged-token reuse) each VOID before authorize with
  spawn=0 and a durable `void` record.
- R38 child/helper byte drift after preflight blocks launch
  (`authority_module_byte_drift`, spawn=0), byte-identical restores
  verified; drifted input expectation refused at authorize.
- R39 all fixture secret values absent from child/entrypoint stdout+stderr
  and from every ledger sink.
- R40 library ControlPlane still cannot seal/evidence
  (`authority_mode_required`); `sealAuthorityEvidence` still refuses library
  import; R1-R29 remain GREEN (single checker run: S0 + G + R1-R40 PASSED).

## File-level mutations (each RED, then SHA-256-verified byte-identical restore)

Driven by a scratch script against the committed candidate tree; after each
mutation the file was restored with `git checkout --` and the SHA-256 was
verified against the pre-mutation value.

- M1 dummy child restored (the CONFIRMED_DEFECT_1 state: child bytes from
  the BASE commit `854c680e6fab56e6b1f33a00350a155c443eb3e4`) → checker RED.
- M2 hardcoded `preflight([{ ok: true, label: 'entrypoint_direct_process' }])`
  restored into the entrypoint → checker RED.
- M3 `complete=true` without reconciliation (evidence gates no-op'd) →
  checker RED.
- M4 child path/argv override accepted (fixed argv discipline relaxed to
  accept extra argv elements) → checker RED.
- M5 second-launch guard deleted (`wx` → `w`) → checker RED.
- Final restored tree: checker exit 0 (GREEN).

## Phase 6 — Frozen gates (candidate tree)

- `pnpm install --frozen-lockfile` PASS (Playwright 1.49.1).
- `pnpm run test:list` PASS — exactly 15 tests / 1 file, order unchanged.
- `pnpm run validate:static` PASS — 15/15 steps (new step [15]).
- `pnpm run check:neutrality` PASS — G1-G6.
- `pnpm run check:runtime-contracts` PASS.
- `pnpm run check:browser-authority` PASS — S0 + G + R1-R40.
- `pnpm run typecheck` PASS.
- `git diff --check` PASS.
- UTF-8, no BOM/NUL/CR, LF-only PASS (validate-static step [6] over all
  text files, including the new helper).
- detect-secrets: READ-ONLY scan of the six changed tool files against the
  committed baseline — zero findings; `.secrets.baseline` SHA-256
  `f49c86223abc95af12d0f6c60938050a68a84e332a94a444800cd93450bd16bf`
  identical before and after. (One earlier invocation from the harness
  subdirectory accidentally rewrote the baseline; it was restored
  byte-identical from HEAD before the authoritative scan.)
- GitNexus: `analyze` indexed the worktree at the Base commit
  (16,893 nodes / 50,827 edges); upstream impact over the authority
  surfaces reported NO HIGH/CRITICAL (`corsPreflightProbe` MEDIUM with 6
  direct dependants, all within the harness/checker surface; expected for
  this round's preflight change). `detect_changes(scope=staged)` executed
  against the staged candidate immediately before commit (see below).
- Candidate tree byte-identical across all mutations (SHA-256 verified).

## Falsification results

See the mutation section above: every required file-level mutation was
detected RED by the checker, and every restore returned the tree to a
byte-identical GREEN state.

## Verdict

`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R6_R4_CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW`

No browser PASS, no merge-ready and no deployment-ready claim is made.
The authoritative browser journey remains NOT_YET_EXECUTABLE and requires
the separately authorized Lubuntu gate (host-level preflight per the
task-private execution contract, real PG/Redis/backend/frontend).
