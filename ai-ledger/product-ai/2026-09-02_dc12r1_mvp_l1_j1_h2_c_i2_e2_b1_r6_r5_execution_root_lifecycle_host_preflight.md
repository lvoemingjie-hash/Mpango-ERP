# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R6-R5 — Execution-Root, Journey-Lifecycle and Host-Preflight Truth Closure

- Date: 2026-09-02
- Branch: `zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r5-execution-root-lifecycle-host-preflight-2026-09-02`
- Base: `e16f39cab7613a32bced21d1f8a5c6be6a54fe18` (verified tip of
  `origin/zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r4-real-playwright-child-preflight-authority-2026-09-01` after fetch)
- Prior Kilo: `446a42a988aeae645c93af5310f41eb6cbc82284`
  (verified tip of `origin/reports/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r4-v1-r1-kilo-bounded-review-2026-09-02`;
  parent == Base, chain intact)
- Verification tier: `V1_SOURCE_TEST_AND_FALSIFICATION`
- Claim ceiling: `CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW_ONLY`

## Confirmed findings closed (recorded at Base, fixed in this round)

- `P1-A PLAYWRIGHT_EXECUTION_ROOT_MISMATCH` — FIXED. The authority child
  spawned `[cli, "test"]` with cwd = repository root while
  `playwright.config.ts` and the frozen tests live under
  `j1h2c-retailer-recovery/`. The child now derives the canonical
  HARNESS_ROOT from its own module location
  (`realpathSync(join(TOOL_DIR, '..'))`), refuses a missing/out-of-root
  frozen config (`playwright_config_unresolvable`, exit 5, pre-spawn), and
  launches the frozen CLI with the FIXED
  `--config <HARNESS_ROOT>/playwright.config.ts` and `cwd = HARNESS_ROOT`.
  The child's own cwd stays the repository root and remains the ONLY
  `cwd_sha` + `git rev-parse HEAD` candidate-binding surface (closure 5).
  The invocation marker, reconciliation/run artifacts and the artifact
  scanner resolve from the SAME HARNESS_ROOT (closures 1-4).
- `P1-B PREFLIGHT_JOURNEY_LIFECYCLE_CONTRADICTION` — FIXED. The fixed
  preflight id `established_login_succeeds` (pre-run owner login must be
  200) contradicted the harness `beforeAll`, which requires the identity
  FRESH and performs register -> setup-credential -> login itself. The id
  is replaced by `owner_identity_fresh_unregistered` in BOTH fixed
  taxonomies (helper + runner): a REFUSED owner login (non-200) proves
  freshness and passes; a 200 login REDs
  (`owner_identity_already_established`) before authorize. The harness
  beforeAll remains the SOLE establishment lifecycle (closures 6-7).
- `P1-C AD_HOC_HOST_PREFLIGHT_NOT_REPRODUCIBLE` — FIXED. The unversioned
  Lubuntu script (misparsed PG booleans, shell-interpolated psql, trusted
  a truncated PID file) is replaced by the version-controlled
  `tools/host-preflight.mjs`: semantic PG boolean parsing across every
  display format; parameter-safe invitation probes (fixed
  `public.invitations` SQL text, values as psql variables in separate argv
  elements with `:'name'` quoting, a guard that refuses to spawn when a
  value would enter the SQL text, `shell: false` everywhere); PID
  ownership proven as full-integer record + ALIVE process-table evidence +
  ownership token in the command line (closures 8-11). Any configured host
  RED folded through the frozen `host_preflight` interface classifies
  `preflight_red` -> STOPPED -> VOID before authorize, spawn=0
  (closure 12).

## Scope (exact)

- `j1h2c-retailer-recovery/tools/browser-authority-child.mjs` (modified)
- `j1h2c-retailer-recovery/tools/browser-authority-preflight-helper.mjs` (modified)
- `j1h2c-retailer-recovery/tools/check-browser-authority-contracts.mjs` (modified — R41-R43 + fixture updates)
- `j1h2c-retailer-recovery/tools/validate-static.mjs` (modified — step [16], honest count 16/16)
- `j1h2c-retailer-recovery/tools/host-preflight.mjs` (NEW — the version-controlled host-preflight module)
- `j1h2c-retailer-recovery/README.md` (modified — B1-R6-R5 section)
- `ai-ledger/product-ai/2026-09-02_dc12r1_mvp_l1_j1_h2_c_i2_e2_b1_r6_r5_execution_root_lifecycle_host_preflight.md` (NEW, this file)

### Disclosed bounded scope delta (for Kilo review)

- `j1h2c-retailer-recovery/tools/browser-authority-runner.mjs` (modified —
  MINIMAL): the directive's authorized list does not name the runner, but
  closure 6/R42 mandate replacing `established_login_succeeds` in the
  FIXED preflight taxonomy, and that taxonomy lives in BOTH the helper and
  the runner (`parsePreflightHelperPayload` refuses unknown ids; the
  helper's own contract is "keep byte-identical with the runner's exported
  fixed taxonomy"). The delta is exactly: one id swapped inside
  `PREFLIGHT_CHECK_IDS` plus its doc comment. No runner logic changed.
- Two dev-checkpoint commits (2fed16e6, 8f4c57e1) plus two fixture-fix
  commits (rollback-free iterations; 8f4c57e1 was forced by the REAL
  src/preconditions.ts reading `J1H2C_FORGED_RESET_TOKEN` from the runtime
  environment; 9c5720e9 by the scanner's strict setup-token cardinality in
  the R41 nested fixture). The candidate tree is the branch tip.

No profile, no schema file, no package.json, no script, no backend,
frontend, migration, product test, product candidate, 15-node spec,
17-node inventory, Playwright config or pnpm lockfile was modified.
No amend/rebase/force-push. No PG, Redis or browser runtime was started.
No full backend suite. No Lubuntu retry. No merge, no deployment.

## Implementation notes

Execution root (child):

- `HARNESS_ROOT = realpathSync(join(TOOL_DIR, '..'))` and
  `PLAYWRIGHT_CONFIG_PATH = join(HARNESS_ROOT, 'playwright.config.ts')`,
  both derived from the module location only — never cwd/env/caller.
- Config must realpath-resolve INSIDE the harness root, else
  `playwright_config_unresolvable` (exit 5) BEFORE any spawn.
- Spawn: `[process.execPath, cliPath, 'test', '--config', configPath]`,
  `cwd: HARNESS_ROOT`, argv array, `shell: false`, silenced stdio.
- `ARTIFACTS_DIR = join(HARNESS_ROOT, 'artifacts')` (marker, evidence
  gating) and the scanner spawn uses `cwd: HARNESS_ROOT`.
- `CWD`/`cwdReal` (repository root) unchanged as the sole candidate
  binding surface: `cwd_sha` recompute, GIT_*-stripped `git rev-parse
  HEAD` pre/post run.

Lifecycle-compatible pre-run proof (helper):

- `checkOwnerIdentityFresh`: formal `POST /api/v1/client/auth/login` with
  the owner identity; `status === 200` ->
  `owner_identity_already_established` (RED); any other status -> green.
  Timeout -> `check_timeout` (RED). Check order and payload shape
  unchanged; the taxonomy stays 9 core ids + 4 host ids.

Host preflight module (`tools/host-preflight.mjs`, NEW):

- Fixed result block: `{ schema: 'j1h2c/host-preflight-result/1', ok,
  provided_by: 'outer_authority_preflight', checks, counts }`; ids
  byte-identical with the runner's `PREFLIGHT_HOST_CHECK_IDS`; labels/
  booleans/categories/counts only — the module fails closed (exit 3, no
  payload) if a profile value would ever appear in its own output.
- Transparent mode: without `J1H2C_HOST_PREFLIGHT=1` it emits
  `checks: []` (an unconfigured host is NOT a RED; the authority report
  stays `host_checks_present = 0`). Configured mode requires ALL
  descriptors (`J1H2C_HOST_*` + `PGPASSWORD`); a missing one is a RED of
  the owning check, never a silent skip.
- `parsePgBoolean`: `t/f, true/false, on/off, yes/no, 1/0` (any case,
  any surrounding space, boolean and 0/1 forms) -> true/false; anything
  else -> null -> RED (`pg_role_capabilities_invalid`).
- Role policy: `rolcanlogin` MUST be true; `rolsuper/rolcreaterole/
  rolcreatedb/rolreplication` MUST all be false; unparsable rows RED.
- `checkInvitationAvailability`: fixed parameter-safe probe over
  `public.invitations` (migration 002 columns: code, retailer_phone,
  status, used_at, is_deleted) for BOTH invitation pairs;
  `pg_invitation_parameterization_invalid` when the runner fails or the
  values would enter the SQL text; `pg_invitation_missing` when no
  unconsumed active invitation exists.
- `checkPidOwnership`:
  `authority_ports_pid_truncated` (empty/non-integer/non-positive),
  `authority_ports_pid_stale` (recorded process not in the process
  table), `authority_ports_owner_mismatch` (alive but without the
  ownership token). The PID file alone is never trusted.
- Default production deps use argv-array `psql`/`alembic`/`ps` with
  `shell: false`; all check functions accept injected doubles, so the
  contract tests run with NO PG/Redis/Alembic/browser runtime.

## MANDATORY TEST DELTA (R41-R43, all GREEN in the committed candidate)

Checker (`tools/check-browser-authority-contracts.mjs`) now proves
S0 + G + R1-R43 in a single run.

- R41 execution root:
  - (a) REAL frozen CLI `test --list --config <HARNESS_ROOT config>`
    started from the canonical REPOSITORY ROOT cwd: exactly 15 tests /
    1 spec, every listed test a `recovery.spec.ts` line (listing only;
    no browser).
  - (b) nested fixture (repository root ABOVE harness root, decoy
    config + decoy spec at the repository root): the child started from
    the repo-root cwd launches the fake frozen CLI at cwd = HARNESS_ROOT
    with argv exactly `['test', '--config', <harness config path>]`;
    no spawn evidence exists at the repository root (default-config
    discovery and cross-tree specs impossible).
  - (c) missing frozen config -> `playwright_config_unresolvable`
    (exit 5) with `playwright.launched === false` and no spawn evidence.
- R42 lifecycle:
  - taxonomy truth: `owner_identity_fresh_unregistered` present,
    `established_login_succeeds` absent from BOTH fixed taxonomies;
  - fresh identity (login refused) passes preflight into AUTHORIZED and
    FINISHES;
  - already-established identity (fixture admits the owner login) ->
    `preflight_red`, STOPPED, `owner_identity_already_established` in
    `preflightRedCategories`, durable `void` record, spawn=0;
  - the REAL `src/preconditions.ts` (transpiled with the frozen
    `typescript` package — no parallel implementation) completes the full
    register -> setup-credential -> login lifecycle against a dedicated
    fixture lifecycle server (register 201 + setup mail delivery,
    setup-credential 200, login 200; unverified stopped before
    verification; retailer not bound to W2), and the same identity
    afterwards can never register again (409) — the exact contradiction
    the retired pre-run login demand implied.
- R43 host preflight:
  - semantic boolean matrix (true/false display forms, unparsable ->
    null);
  - parameter-safety (SQL text carries no values; named parameter
    binding present; interpolated SQL detected);
  - role capability matrix (least-privilege pass; nologin/super/
    createrole/createdb/replication/unparsable/short-row all RED);
  - invitation RED paths (missing pair; runner failure);
  - PID ownership matrix (truncated/stale/foreign RED; live+owned pass);
  - removed host checks RED (`host_check_missing`), taxonomy always
    complete and byte-identical with the runner ids; unconfigured host
    transparent;
  - REAL module process, configured RED: all four ids present, fixed
    categories only (truncated then stale PID evidence), zero sensitive
    values in stdout/stderr;
  - host RED -> VOID fold: module green/RED blocks folded through the
    REAL helper process over the frozen `host_preflight` interface
    (`host_checks_present = 4`; green folds green, RED folds RED);
    the runner parser accepts the folded RED payload; the control plane
    classifies any parsed payload with ok=false as `preflight_red` ->
    STOPPED before authorize with spawn=0 (the same machine-checked
    branch R37 proves end-to-end).

### Honest seam (disclosed, not hidden)

The runner-owned preflight spawns the helper with the materialized values
ONLY; the host block enters the verdict through the frozen
`provided_by: 'outer_authority_preflight'` hand-off, which the OUTER
Lubuntu layer owns (B1-R6-R4 contract, unchanged this round because the
runner is outside the authorized scope). The fold-to-VOID machinery is
proven at every link (module RED real, helper fold real, parser real,
control-plane ok=false -> VOID real in R37); what a future Lubuntu task
must add is the outer-layer invocation of `tools/host-preflight.mjs` and
its `host_checks_present > 0` assertion. `UNCOVERED_NEW_PATHS = 0` within
this round's authorized scope.

## File-level mutations (each RED, then byte-identical restore)

Driven against the committed candidate tree; after each mutation the file
was restored with `git checkout --` and the SHA-256 was verified identical
to the pre-mutation value; the final tree is CLEAN.

- M6 child spawn `cwd: HARNESS_ROOT` -> `cwd: cwdReal` (repo-root cwd
  mutation): checker exit 1 — the frozen-config proof file the closure
  requires no longer exists at the harness root (Playwright provably ran
  at the wrong root). RED.
- M7 child spawn argv omits `--config`: checker exit 1 with the exact
  assertion failures "R30/R41: fixed Playwright argv carries the frozen
  --config exactly" and "R41: fixed --config selects the exact frozen
  config path". RED.
- M8 helper CORE_CHECK_IDS restored to the retired established-login id:
  checker exit 1 (`preflight_helper_dirty_vs_head` — the committed-byte
  binding refuses the mutated helper). RED.
- M9 host module `redis_reachable` check removed from the execution list:
  checker exit 3 — the module's fail-closed taxonomy guard
  (`host_check_missing` -> failClosed, no payload) kills the run. RED.
- M10 runner taxonomy restored to the retired id: checker exit 1
  (`preflight_helper_payload_invalid` — the helper's lifecycle id becomes
  unknown to the parser). RED.

## Frozen gates (final restored candidate tree)

- `pnpm install --frozen-lockfile` PASS (@playwright/test 1.49.1).
- `pnpm run test:list` PASS — `Total: 15 tests in 1 file`.
- `pnpm run validate:static` PASS — 16/16 steps (new step [16]).
- `pnpm run check:neutrality` PASS — G1-G6.
- `pnpm run check:runtime-contracts` PASS.
- `pnpm run check:browser-authority` PASS — S0 + G + R1-R43.
- `pnpm run typecheck` PASS.
- `git diff --check` PASS (candidate diff e16f39ca..HEAD and working tree).
- UTF-8 / no BOM / no NUL / LF-only PASS over all seven changed files
  (validate-static step [6] over the harness tree).
- detect-secrets: READ-ONLY scan of the seven changed files — zero raw
  findings; `.secrets.baseline` SHA-256
  `f49c86223abc95af12d0f6c60938050a68a84e332a94a444800cd93450bd16bf`
  identical before and after. (One first invocation with the
  `--baseline` comparison form rewrote the baseline; it was restored
  byte-identical via `git checkout --` BEFORE the authoritative
  stdout-only scan — the same trap the prior round recorded.)
- GitNexus: `analyze` indexed the worktree at the Base commit (16,924
  nodes / 50,943 edges) and again on the candidate tree (16,983 nodes /
  51,102 edges); upstream impact over the authority surfaces BEFORE edits
  was all LOW (`launchAuthorityChild` 1 direct dependant,
  `checkEstablishedLogin` 1, `canonicalAuthorityChildArgv` 3, ControlPlane
  LOW — no HIGH/CRITICAL). `detect_changes(scope=staged)` was executed
  through the GitNexus MCP server immediately before the final commit: it
  classified the staged delta (this ledger's sections; the code delta was
  already indexed by the candidate re-analyze) with risk_level "none" and
  no affected processes.
- Candidate tree byte-identical across all mutations (SHA-256 verified).

## Falsification result

Every mandated mutation was detected RED and every restore returned the
tree to a byte-identical GREEN state (full gate battery re-run on the
restored tree: all PASS). R41 mutation coverage: repo-root cwd (M6) and
omitted --config (M7) both RED. R42 mutation coverage: restoring
`established_login_succeeds` (M8 helper, M10 runner) RED.

## Verdict

`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R6_R5_CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW`

TEST_FILES_ADDED: tools/host-preflight.mjs; this ledger.
TEST_FILES_MODIFIED: browser-authority-child.mjs,
browser-authority-preflight-helper.mjs, browser-authority-runner.mjs
(disclosed bounded delta), check-browser-authority-contracts.mjs,
validate-static.mjs, README.md.
TEST_NODES_ADDED_OR_CHANGED: R41, R42, R43 (new); R30 argv assertion, R37
established-mode map, R40 taxonomy pin (changed).
FULL_SUITE_RESULT=NOT_RUN. BROWSER_RUNTIME=NOT_RUN.

No browser PASS, no merge-ready and no deployment-ready claim is made.
The authoritative browser journey remains NOT_YET_EXECUTABLE and requires
the separately authorized Lubuntu gate — which must run THIS repository's
`tools/host-preflight.mjs` (never another ad hoc script) and fold its
block through the frozen host interface.

STOP after publishing this candidate. NEXT_GATE=KILO_BOUNDED_DELTA_REVIEW.
