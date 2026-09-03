# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R6-R3-R1 - Direct Authority Entrypoint

- Date: 2026-09-01
- Branch: `zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r3-authority-entrypoint-2026-09-01`
- Base: `a0991a8` (R6-R2 candidate)
- Verification tier: `V3_MERGE_CRITICAL`
- Claim ceiling: `CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW_ONLY`

## Scope

This round keeps library `ControlPlane` instances non-authority while adding
the only direct-process authority evidence path.

Library functional mode can still exercise materialize, CORS probe, preflight,
authorize, and fake child classification for source tests. It cannot mint a
terminal seal or evidence. Public `authority:true`, imported entrypoint code,
env, argv, and JSON never receive the module-private authority capability.

The direct entrypoint now executes:

`materialize -> process-isolated CORS probe -> preflight -> authorize -> fixed real child -> FINISHED/TEST_RED -> terminal seal -> authority evidence`

## Implementation Notes

- `tools/browser-authority-runner.mjs` owns a module-private Symbol-branded
  capability. `sealAuthorityEvidence()` mints it only after direct entrypoint
  process checks, HEAD-blob checks, live bindings, terminal state, real child
  observation, and contract/input/argv/cwd SHA binding facts are present.
- `tools/browser-authority-entrypoint.mjs` accepts only `--contract` and
  `--ledger` paths. It never accepts an executor or child command override.
- `tools/browser-authority-child.mjs` is the fixed child argv target for this
  source-level authority proof. It returns exact schema stdout with parent
  verifiable pid, exit, and reconciliation fields.
- `tools/browser-authority-cors-probe-helper.mjs` now emits exact
  `j1h2c/cors-probe-result/1` payloads. `ok:true` requires
  `status_2xx`, `allow_origin_present`, and `allow_origin_exact` all true.

## R29-R1 Coverage

Positive control:

- Directly starts `tools/browser-authority-entrypoint.mjs` from a scratch source
  whose authority files are committed to HEAD.
- Observes a real child pid and exit 0.
- Requires FINISHED, terminal seal, readable evidence, and a valid hash chain.

Negative controls:

- Imported entrypoint.
- Public `authority:true`.
- Fake sync and async executors.
- Forged child stdout.
- Malformed CORS helper payloads, including `ok:true` with the three required
  booleans false.
- `NODE_OPTIONS`, `NODE_PATH`, and `GIT_*` injection.
- Dirty entrypoint, runner, CORS helper, and profile files.
- Child nonzero and incomplete reconciliation, both sealed as TEST_RED rather
  than FINISHED.

## Gate Notes

The full browser-authority checker requires committed authority file bytes
because the production boundary compares entrypoint, runner, helper, child,
and profile bytes against the owning repository HEAD blob. As in R6-R2, the
full checker is a candidate-commit-state gate.

No PG, Redis, product runtime, non-list Playwright, merge, or deploy is in
scope for this round.

## Verification

Pre-commit source-state gates run so far:

- `pnpm run validate:static` PASS.
- `pnpm run test:list` PASS: 15 tests / 1 file.
- `pnpm run check:neutrality` PASS: G1-G6.
- `pnpm run check:runtime-contracts` PASS.
- `pnpm run typecheck` PASS.
- `git diff --check` PASS.
- `detect-secrets-hook --baseline .secrets.baseline <changed files>` PASS.

Authority checker note:

- The production authority path rejects dirty authority files by comparing
  entrypoint, runner, helper, child, and profile bytes to HEAD blobs. Therefore
  the full checker is run pre-commit in a scratch source tree where those
  current files are first committed to HEAD.
- Scratch committed-source `node tools/check-browser-authority-contracts.mjs`
  PASS: S0 + G + R1-R29, including R29-R1 direct entrypoint positive control.

Falsification:

- Scratch mutation M-R6R3R1 changed runner default `this.#authority = false` to
  `this.#authority = true`. The checker went RED with library/fake-child seal
  and evidence failures, including R29 fake sync/async child evidence attempts.

GitNexus:

- Impact checks before edits found no HIGH/CRITICAL risk. `corsPreflightProbe`
  was MEDIUM limited to harness/checker callers; `launch` and `evidence` were
  LOW.
- CLI `gitnexus` does not expose `detect_changes`, but MCP tool listing exposes
  `detect_changes`.
- MCP `detect_changes(scope: staged)` PASS: changed files 8, changed symbols
  62, affected processes 4, risk `medium`. Affected processes were limited to
  the control-plane/git/live-binding harness flows:
  `Constructor -> GitEnv`, `#assertLiveBindings -> BrowserAuthorityError`,
  `#assertLiveBindings -> Sha256Hex`, and `#assertLiveBindings -> GitEnv`.
