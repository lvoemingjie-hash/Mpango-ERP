# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R6-R5-R1 — Host Authority Wiring, Exact-401 Freshness and Scope Discipline Closure

- Date: 2026-09-02
- Branch: `zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r5-r1-host-authority-2026-09-02`
- Base: `e16f39cab7613a32bced21d1f8a5c6be6a54fe18` (unchanged from the R5
  directive; verified)
- Prior candidate: `8a4aeec45eaac8db46180471317313464080035f`
- Prior classification: `SUPERSEDED_BY_R5_R1__SCOPE_VIOLATION_AND_INCOMPLETE_HOST_AUTHORITY`
  — the branch and history of 8a4aeec4 are preserved untouched (no
  amend/rebase/force-push); this candidate does NOT inherit its WIP
  lineage: the working tree was rebuilt from the BASE..8a4aeec4 patch and
  re-worked, then committed as ONE ordinary commit on Base.
- Verification tier: `V1_SOURCE_TEST_AND_FALSIFICATION`
- Claim ceiling: `CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW_ONLY`

## Reviewer findings closed (this round)

- `R1 FINDING 1: HOST PREFLIGHT NOT IN THE AUTHORITY CHAIN` — FIXED. The
  authority runner now owns and invokes the host gate itself:
  - `canonicalHostPreflightPath()` derives `tools/host-preflight.mjs`
    from the RUNNER module's own location — never from a caller, the
    entrypoint, env or any other source;
  - preflight proves the module's working-tree bytes equal its HEAD
    committed blob (`host_preflight_dirty_vs_head`,
    `host_preflight_module_missing`);
  - the runner spawns the module itself with the fixed argv
    `[process.execPath, <canonical module>]` through `execFile` (a shell
    is never involved), a GIT-x/NODE-x-stripped environment and a private
    stdin carrying only `{schema, timeout_ms, values}` (the deep-frozen
    materialized values);
  - the exact-shape payload parser (`parseHostPreflightPayload`) refuses
    forged/malformed results (`host_preflight_payload_invalid`): fixed
    schema, frozen hand-off marker `outer_authority_preflight`,
    `configured` flag, and either the transparent shape or the four fixed
    ids in order with consistent counts;
  - DIRECT authority mode REQUIRES exactly four host checks:
    `assertDirectAuthorityHostCoverage` VOIDs
    (`host_preflight_incomplete`) when `host_checks_present != 4`, and an
    unconfigured host (transparent module result, zero checks) VOIDs
    (`host_preflight_not_configured`) — both BEFORE authorize;
  - any RED host check folds into the helper verdict and classifies
    `preflight_red:<category>` -> STOPPED, authority child spawn = 0,
    Playwright invocation = 0;
  - the entrypoint's `control.preflight()` call therefore REALLY triggers
    the host module — no future Lubuntu outer script is required for the
    gate to bite; the Lubuntu gate's only remaining duty is configuring
    the descriptor environment (`J1H2C_HOST_PREFLIGHT=1` + fixed
    `J1H2C_HOST_*`/`PGPASSWORD` names) on the real host;
  - library / non-authority fixtures stay transparent
    (`host_checks_present = 0`, no host spawn) and can never mint
    authority seal/evidence — proven unchanged (R40, R29).
  Proofs: R45 (four direct-entrypoint VOID paths over REAL runs),
  R46 (four-check GREEN accepted by runner parser + REAL helper fold +
  coverage policy; configured all-RED host through a REAL direct
  entrypoint VOIDs before authorize with no start/finish/seal), R29-R1
  (the direct positive control now truthfully lands the host-gate VOID —
  including with committed forged/nonzero/incomplete child variants,
  which can never be reached).

- `R1 FINDING 2: ANY-NON-200-IS-FRESH MISFIRE` — FIXED.
  `owner_identity_fresh_unregistered` is GREEN ONLY when the formal login
  answers EXACTLY 401. 200 -> `owner_identity_already_established`;
  404 -> `owner_identity_lookup_missing`; 422 ->
  `owner_identity_unprocessable`; 429 -> `owner_identity_rate_limited`;
  5xx -> `owner_identity_backend_unavailable`; any other status ->
  `owner_identity_unexpected_status`. R44 proves 401 GREEN, 200 RED and
  404/422/429/500 RED (each with its fixed category, VOID before
  authorize, spawn = 0) against the REAL fixture server.

- `R1 FINDING 3: SCOPE DISCIPLINE` — CLOSED BY THE NEW DIRECTIVE. The
  runner and entrypoint are now EXPLICITLY inside the authorized scope
  (EXACT_SCOPE items 2 and 5). This candidate modifies exactly the nine
  authorized paths. The prior candidate's undisclosed-runner-delta
  classification stands as recorded; this ledger does not re-litigate it.

## Scope (exact — the nine authorized paths, nothing else)

1. `j1h2c-retailer-recovery/README.md` (modified)
2. `j1h2c-retailer-recovery/tools/browser-authority-entrypoint.mjs` (modified — doc comment only)
3. `j1h2c-retailer-recovery/tools/browser-authority-child.mjs` (modified — unchanged from the R5 closures: HARNESS_ROOT, fixed --config, harness cwd/artifacts/scanner)
4. `j1h2c-retailer-recovery/tools/browser-authority-preflight-helper.mjs` (modified — exact-401 freshness)
5. `j1h2c-retailer-recovery/tools/browser-authority-runner.mjs` (modified — runner-owned host gate + payload parser + coverage policy)
6. `j1h2c-retailer-recovery/tools/check-browser-authority-contracts.mjs` (modified — R29 truth update, R44/R45/R46)
7. `j1h2c-retailer-recovery/tools/host-preflight.mjs` (modified — `configured` flag in the result shape)
8. `j1h2c-retailer-recovery/tools/validate-static.mjs` (modified — step [16] extended)
9. `ai-ledger/product-ai/2026-09-02_dc12r1_mvp_l1_j1_h2_c_i2_e2_b1_r6_r5_r1_host_authority.md` (NEW, this file)

No other file was touched. No amend/rebase/force-push. No PG, Redis or
browser runtime. No full backend suite. No Lubuntu retry. No merge, no
deployment.

## CHANGED_OR_ADDED_TESTS_COVERING_NEW_PATHS

- R44 (NEW): exact-status freshness matrix — 401 GREEN (full flow to
  AUTHORIZED/FINISHED); 200 RED (`owner_identity_already_established`);
  404/422/429/500 RED (each `preflight_red`, category exact, STOPPED,
  spawn=0) over the REAL fixture server with new exact-status modes.
- R45 (NEW): direct authority host gate — (a) missing host configuration:
  REAL direct entrypoint VOIDs, void record category
  `host_preflight_not_configured`, no finish record, no sealed evidence
  payload; (b) zero host checks: configured-but-empty payload refused by
  `parseHostPreflightPayload` (`host_preflight_payload_invalid`), forged
  hand-off marker refused, `assertDirectAuthorityHostCoverage` refuses
  `host_checks_present = 0` and accepts 4; (c) missing module:
  `host_preflight_module_missing` void record; (d) dirty module bytes:
  `host_preflight_dirty_vs_head` void record.
- R46 (NEW): REAL module four-check GREEN block accepted by the runner
  parser (taxonomy byte-identical with `PREFLIGHT_HOST_CHECK_IDS`), folded
  green through the REAL helper (`host_checks_present = 4`), accepted by
  the coverage policy; configured all-RED host through a REAL direct
  entrypoint -> `preflight_red:<host-category>` void record, no start,
  no finish, no terminal seal, no sealed evidence payload.
- R29-R1 (CHANGED to the new truthful contract): the direct positive
  control now lands the host-gate VOID (`host_preflight_not_configured`)
  instead of a sealed TEST_RED; committed forged-stdout / nonzero /
  incomplete child variants can never be reached — the host gate fires
  first (the child's own result truth remains proven by R30-R35 direct
  runs).
- R41/R42/R43 (carried from the R5 closures, unchanged semantics): R43
  additionally asserts the `configured` flag and the transparent shape.

## CODE_PATH_TO_TEST_MATRIX

- runner `canonicalHostPreflightPath` + HEAD-blob proof -> R45(c)/R45(d).
- runner host spawn (fixed argv, sanitized env, private stdin) -> R45(a),
  R46(b) (REAL module process through REAL direct entrypoints).
- runner `parseHostPreflightPayload` -> R45(b), R46(a) (forged shapes and
  the real GREEN block).
- runner `assertDirectAuthorityHostCoverage` -> R45(b), R46(a).
- runner preflight folding -> helper `host_preflight` validation ->
  R46(a)/R46(b)/R29-R1.
- helper `checkOwnerIdentityFresh` exact statuses -> R44(a)-(c).
- entrypoint `control.preflight()` -> R29-R1, R45(a)/(c)/(d), R46(b).
- library transparency -> R40/R37/R42 (host_checks_present = 0, no host
  spawn, seal/evidence still refused).
- child execution-root closures (unchanged) -> R41 + R30-R35.

## NEGATIVE_AND_FAILURE_PATHS

missing host configuration; zero host checks (forged payload and policy
probe); forged hand-off marker; missing host module; dirty host module
bytes; host module crash/timeout (`host_preflight_no_response` path
retained); any RED host check (pg/redis/alembic/ports categories);
non-401 owner login statuses 200/404/422/429/500/other; caller check
injection (preflight_input_rejected, R26-FAKE — the Mutation D detector);
library seal/evidence attempts (authority_mode_required).

## FALSIFICATION_RESULT (Mutations A-D, each RED, then SHA-256-verified
byte-identical restore; final tree CLEAN)

- Mutation A (host module invocation deleted from preflight): checker
  exit 1 — the R29-R1 direct scenarios fail (no host-gate refusal
  category, no void record, sealed-evidence assertions). RED.
- Mutation B (direct coverage policy allows host_checks_present = 0):
  checker exit 1 — "R45: zero host coverage refused by the direct policy
  did NOT throw". RED.
- Mutation C (any-non-200-is-fresh restored in the helper): checker
  exit 1 — the committed-byte binding refuses the mutated helper
  (`preflight_helper_dirty_vs_head`). RED.
- Mutation D (caller-injected forged host payload accepted by preflight):
  checker exit 1 — "R26-FAKE: caller ok=true boolean refused did NOT
  throw". RED.

## Frozen gates (final candidate tree)

- `pnpm install --frozen-lockfile` PASS (@playwright/test 1.49.1).
- `pnpm run test:list` PASS — `Total: 15 tests in 1 file`.
- `pnpm run validate:static` PASS — 16/16 steps (step [16] extended).
- `pnpm run check:neutrality` PASS — G1-G6.
- `pnpm run check:runtime-contracts` PASS.
- `pnpm run check:browser-authority` PASS — S0 + G + R1-R46.
- `pnpm run typecheck` PASS.
- `git diff --check` PASS (candidate diff e16f39ca..HEAD and working tree).
- detect-secrets: READ-ONLY stdout-only scan of the eight changed files —
  zero findings; `.secrets.baseline` SHA-256
  `f49c86223abc95af12d0f6c60938050a68a84e332a94a444800cd93450bd16bf`
  identical before and after (no baseline-rewriting invocation form used
  this round).
- strict UTF-8, no BOM, no NUL, LF-only over all changed files PASS.
- GitNexus: `analyze` on the candidate tree; upstream impact before edits
  all LOW (`canonicalHostPreflightPath` / `parseHostPreflightPayload` /
  `assertDirectAuthorityHostCoverage` / `isDirectAuthorityEntrypointProcess`
  / `preflight` / `ControlPlane` each LOW with 0-2 direct dependants).
  `detect_changes(scope=staged)` executed through the GitNexus MCP server
  against the FULL staged candidate (Base -> candidate): independent
  measurement GITNEXUS_COMPARE_RISK=HIGH — 133 changed symbols /
  9 affected processes (the reviewer's prior-candidate compare measured
  MEDIUM with 125 / 5; this candidate adds the runner-owned host gate
  wiring and the R44-R46 test delta, and the higher measured risk is
  recorded as measured, not smoothed).
- Candidate tree byte-identical across all mutations.

## UNCOVERED_NEW_PATHS

0 within this round's scope. Disclosed boundary (not a new path, an
environmental one): the four host checks exercise REAL psql/Redis/Alembic/
process-table probes only in the configured Lubuntu gate; source-level
tests prove the module logic with injected runners and the chain behavior
with real processes against descriptor REDs. `FULL_SUITE_RESULT=NOT_RUN`,
`BROWSER_RUNTIME=NOT_RUN`. `BROWSER_AUTHORITY_STATUS = NOT_YET_EXECUTABLE`.

## Verdict

`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R6_R5_R1_CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW`

STOP after publishing this candidate. NEXT_GATE=KILO_BOUNDED_DELTA_REVIEW.
