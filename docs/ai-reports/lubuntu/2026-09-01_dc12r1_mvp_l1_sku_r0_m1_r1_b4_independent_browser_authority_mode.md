# DC-12R1-MVP-L1-SKU-R0-M1-R1-B4 Independent Browser Authority Mode

Date: 2026-09-01

Branch: `codexl/dc12r1-mvp-l1-sku-r0-m1-r1-b4-independent-browser-authority-mode-2026-09-01`

Base: `1a7b4f26bee02aa2a340d0639d2aa59e7d3050d9`

Frozen B3 functional harness candidate: `13fd597131befc3aaea672f79a5f684f9e818ad6`

B4 harness candidate evaluated at runtime: `c5215df80c8ea5e698cddea0a6809167356629da`

## Defect Closed

B3 shipped a harness that understood exactly one execution label. `src/runtime.ts`
exported `isAuthorDiagnosticMode()` / `requireAuthorDiagnosticMode()`, wrote
`mode: 'AUTHOR_DIAGNOSTIC'` into every ledger record unconditionally, selected its
reporter with `process.env.B3_AUTHOR_DIAGNOSTIC === '1'`, and the centralized fixture
recorder in `src/fixtures.ts` returned early unless that one variable was set. An
independent verifier therefore had no way to produce independently labelled authority
evidence, and omitting the author variable aborted execution instead of selecting a
mode.

B4 replaces that single-label design with a real, fail-closed two-mode control plane.
The four browser journey bodies and every product byte are untouched.

## Candidate Scope

Final changed paths from base (`1a7b4f26..c5215df8`):

```text
M    sku-m1-browser/README.md
M    sku-m1-browser/playwright.config.ts
A    sku-m1-browser/src/authority-reporter.ts
D    sku-m1-browser/src/diagnostic-reporter.ts
M    sku-m1-browser/src/fixtures.ts
M    sku-m1-browser/src/global-setup.ts
M    sku-m1-browser/src/reconcile.ts
M    sku-m1-browser/src/runtime.ts
M    sku-m1-browser/validator/mutations.py
M    sku-m1-browser/validator/reconciliation_truth_tests.py
M    sku-m1-browser/validator/static_validator.py
```

`sku-m1-browser/src/authority-reporter.ts` is the mode-neutral generalization of
`src/diagnostic-reporter.ts` (class `B3DiagnosticReporter` ->
`BrowserAuthorityReporter`). `src/fixtures.ts` and `src/reconcile.ts` are control-plane
files changed only because the mode contract requires the recorded mode to be stamped
onto every reconciliation record and cross-checked on every source; neither file
contains a functional assertion, a namespace, or a journey body, and the byte proofs
below are unaffected.

### Required byte proofs

```text
git diff --name-only 1a7b4f26bee02aa2a340d0639d2aa59e7d3050d9..c5215df8 -- backend frontend backend/alembic | wc -l
0
```

```text
git diff --name-only 13fd597131befc3aaea672f79a5f684f9e818ad6..c5215df8 -- \
  sku-m1-browser/tests sku-m1-browser/src/provision.ts sku-m1-browser/provisioning/official.json | wc -l
0
```

```text
B2_PRODUCT_BYTES_UNCHANGED
B3_FUNCTIONAL_BROWSER_BYTES_UNCHANGED
```

## Mode Contract

Exactly two mutually exclusive runtime modes; both run the identical frozen journeys.

| mode                    | selected with              | meaning                                 |
| ----------------------- | -------------------------- | --------------------------------------- |
| `AUTHOR_DIAGNOSTIC`     | `B3_AUTHOR_DIAGNOSTIC=1`   | author evidence; never independent      |
| `INDEPENDENT_AUTHORITY` | `B4_INDEPENDENT_AUTHORITY=1` | independent verifier authority evidence |

Rules enforced by `resolveRuntimeMode()` (`src/runtime.ts`) and invoked at
`playwright.config.ts` load, i.e. before Playwright can launch a browser:

- exactly one mode variable must equal the literal string `1`;
- neither set -> `mode_unset`, fail closed;
- both set -> `both_modes_set`, fail closed;
- any other value (e.g. `B4_INDEPENDENT_AUTHORITY=YES`) -> `mode_value_unknown`, fail
  closed;
- an unknown mode label inside any evidence file -> `mode_label_unknown`, fail closed;
- `--list` ignores BOTH mode variables for runtime writes and stays read-only;
- the mode is recorded identically in the invocation ledger, the live execution
  contract, the authority report, the Playwright report metadata and the reconciliation
  records;
- after invocation start the mode is frozen (in-process and in
  `results/live-execution-contract.json`); `recordedMode()` consults the environment
  only while no invocation has been recorded, so no environment variable can relabel or
  override the recorded mode.

## Invocation Accounting

Append-only `results/invocation-ledger.jsonl`. One fresh task worktree / results
directory permits exactly one runtime invocation for its selected mode:

- second start in the same mode -> `second_invocation_refused`;
- `AUTHOR_DIAGNOSTIC` -> `INDEPENDENT_AUTHORITY` or the reverse ->
  `cross_mode_invocation_refused`;
- ledger holding evidence for another candidate SHA ->
  `candidate_sha_mismatch_void` (VOID before browser launch);
- every refusal is appended before the throw, so the ledger stays append-only.

## Reporter Contract

`src/authority-reporter.ts` writes `results/authority-report.json`:

```json
{
  "schema": "sku-m1-browser/authority-report/1",
  "execution_mode": "AUTHOR_DIAGNOSTIC",
  "candidate_sha": "c5215df80c8ea5e698cddea0a6809167356629da",
  "workers": 1,
  "retries": 0,
  "expected_execution_count": 4,
  "observed_execution_count": 4,
  "status": "passed",
  "executions": [
    {"node": "sku-m1-browser/tests/catalog-hist-001.spec.ts::CATALOG-HIST-001", "viewport": "desktop",    "status": "passed", "failure_class": "NO_FAILURE"},
    {"node": "sku-m1-browser/tests/catalog-id-001.spec.ts::CATALOG-ID-001",    "viewport": "desktop",    "status": "passed", "failure_class": "NO_FAILURE"},
    {"node": "sku-m1-browser/tests/catalog-hist-001.spec.ts::CATALOG-HIST-001", "viewport": "mobile-390", "status": "passed", "failure_class": "NO_FAILURE"},
    {"node": "sku-m1-browser/tests/catalog-id-001.spec.ts::CATALOG-ID-001",    "viewport": "mobile-390", "status": "passed", "failure_class": "NO_FAILURE"}
  ]
}
```

Reconciliation requires the same mode and the same candidate SHA across all five
sources via four distinct `checkBinding(...)` call sites in `src/reconcile.ts`
(`live_execution_contract`, `invocation_ledger`, `reconciliation_record`,
`playwright_report`). Any disagreement is an error, increments
`mode_mismatches` / `candidate_sha_mismatches`, feeds `gap`, and exits nonzero.

## Static And Mutation Evidence

Typecheck:

```text
pnpm --dir sku-m1-browser typecheck
$ tsc -p tsconfig.json --noEmit
tsc: clean
```

Strict validator (author mode, results absent):

```text
python3 sku-m1-browser/validator/static_validator.py --allow-missing-reconciliation
STATIC VALIDATOR: GREEN
```

Mutation suite:

```text
python3 sku-m1-browser/validator/mutations.py
MUTATION SUITE: all 36 mutations RED as intended, pristine and restored states GREEN
```

The 26 prior B3/B1 mutations were retargeted to the new sentinels (M23
`requireRuntimeMode()`, M25 `if (starts.length >= 1) {`) and remain RED. Ten new B4
mutations were added, each RED with byte-identical restore:

```text
M27-mode-exclusivity-removed
M28-independent-mode-mapped-to-author-diagnostic
M29-no-mode-execution-allowed
M30-ledger-mode-comparison-deleted
M31-reconciliation-mode-comparison-deleted
M32-cross-mode-second-invocation-permitted
M33-candidate-sha-ledger-drift-permitted
M34-reporter-enabled-only-for-author-mode
M35-list-writes-runtime-evidence
M36-author-evidence-relabelled-independent
```

Reconciliation + authority truth tests:

```text
python3 sku-m1-browser/validator/reconciliation_truth_tests.py
RECONCILIATION TRUTH TESTS: PASS
```

All 14 required truth tests pass, several in both directions:

```text
T01-author-mode-accepted-and-recorded
T02-independent-mode-accepted-and-recorded
T03-no-mode-rejected / T03-no-mode-playwright-aborts / T03-no-mode-zero-runtime-writes
T04-both-modes-rejected / T04-both-modes-playwright-aborts / T04-both-modes-zero-runtime-writes
T05/T05b-unknown-mode-value-rejected (both variables)
T06a/T06b-author-evidence-fails-independent-reconciliation (--require-mode)
T07a/T07b-independent-evidence-fails-author-reconciliation (--require-mode)
T08/T08b-second-invocation-refused (both modes)
T09/T09b-cross-mode-second-invocation-refused (both directions)
T10/T10b-stale-candidate-ledger-rejected (both modes)
T11-recorded-mode-frozen-in-process / T11b-env-cannot-override-recorded-mode
T12-list-succeeds / exactly-4-executions / zero-runtime-writes (no-mode, author,
  independent, both)
T13/T13b-report-vs-record and report-metadata mode mismatch rejected
T14-candidate-sha-mismatch-rejected
T15-failed-execution-is-red, stays FAIL, mode still recorded
T16-T21b: prior B3 phase-A truth tests retained
```

Mode probes are executed against the REAL compiled control plane: `src/runtime.ts` is
compiled into an isolated probe worktree whose `results/` directory is per-probe, so
each probe models one fresh task worktree. The four end-to-end fail-closed probes
(no mode / both modes / unknown mode / unknown author value) run an actual
`playwright test` process and assert `rc != 0`, the exact `[code]` marker on stderr,
and a byte-identical `results/` tree afterwards.

`--list` remains read-only in all four mode configurations and still reports exactly
four executions:

```text
Listing tests:
  [desktop] › catalog-hist-001.spec.ts:32:5 › CATALOG-HIST-001
  [desktop] › catalog-id-001.spec.ts:31:5 › CATALOG-ID-001
  [mobile-390] › catalog-hist-001.spec.ts:32:5 › CATALOG-HIST-001
  [mobile-390] › catalog-id-001.spec.ts:31:5 › CATALOG-ID-001
Total: 4 tests in 2 files
```

## Fresh Runtime Evidence (AUTHOR_DIAGNOSTIC, control-plane integration)

Fresh stack, loopback only:

```text
PostgreSQL 16: sku_b4_pg16 on 127.0.0.1:17801 (database sku_b4, fresh, alembic from empty)
Redis 7: sku_b4_redis7 on 127.0.0.1:17802, DB15 dbsize 0 before run
Sentinel: 127.0.0.1:26379 unreachable
Backend: real uvicorn api.app:app on 127.0.0.1:17804 (MPANGO_ENV=production, real SMTP delivery)
Frontend: production build served over local HTTPS on 127.0.0.1:17805
SMTP: local fake SMTP/Maildir sink on 127.0.0.1:17803
Browser: real Chromium via /usr/bin/chromium-browser
```

Alembic:

```text
alembic current
038_catalog_identity_vertical_slice (head)
```

Preflight:

```json
{
  "outcome": {
    "kind": "OK"
  },
  "sharedIdentitiesOnly": true
}
```

Single author diagnostic invocation (append-only ledger, exactly one start + one end):

```json
{"schema":"sku-m1-browser/invocation-ledger/1","event":"start","mode":"AUTHOR_DIAGNOSTIC","candidate_sha":"c5215df80c8ea5e698cddea0a6809167356629da","invocation_count":1,"status":"started","workers":1,"retries":0,"expected_node_count":4,"observed_node_count":0}
{"schema":"sku-m1-browser/invocation-ledger/1","event":"end","mode":"AUTHOR_DIAGNOSTIC","candidate_sha":"c5215df80c8ea5e698cddea0a6809167356629da","invocation_count":1,"status":"passed","workers":1,"retries":0,"expected_node_count":4,"observed_node_count":4}
```

Live execution contract (frozen at invocation start):

```json
{
  "schema": "sku-m1-browser/live-execution-contract/1",
  "execution_mode": "AUTHOR_DIAGNOSTIC",
  "candidate_sha": "c5215df80c8ea5e698cddea0a6809167356629da",
  "workers": 1,
  "retries": 0,
  "expected_execution_count": 4,
  "frozen_at_invocation_start": true
}
```

Playwright:

```text
B3_AUTHOR_DIAGNOSTIC=1
B1_CANDIDATE_SHA=c5215df80c8ea5e698cddea0a6809167356629da
workers=1
retries=0
no grep
no shard
no rerun

  ✓  1 [desktop] › catalog-hist-001.spec.ts:32:5 › CATALOG-HIST-001 (5.5s)
  ✓  2 [desktop] › catalog-id-001.spec.ts:31:5 › CATALOG-ID-001 (6.1s)
  ✓  3 [mobile-390] › catalog-hist-001.spec.ts:32:5 › CATALOG-HIST-001 (5.0s)
  ✓  4 [mobile-390] › catalog-id-001.spec.ts:31:5 › CATALOG-ID-001 (12.2s)

  4 passed (43.2s)
```

Playwright JSON stats:

```json
{"duration":43160.451,"expected":4,"flaky":0,"skipped":0,"startTime":"2026-09-01T09:21:37.507Z","unexpected":0}
```

Playwright report mode binding (emitted by the run itself, not by the report writer):

```json
{"execution_mode": "AUTHOR_DIAGNOSTIC", "candidate_sha": "c5215df80c8ea5e698cddea0a6809167356629da", "workers": 1, "retries": 0, "actualWorkers": 1}
```

Reconciliation accounting:

```json
{"candidate_sha_mismatches":0,"duplicates":0,"fail":0,"gap":0,"mode_mismatches":0,"not_run":0,"pass":4,"playwright_without_reconciliation":0,"reconciliation_without_playwright":0,"recorded_combinations":4,"report_disagreements":0,"required_combinations":4,"skipped":0,"unknown_nodes":0,"unknown_viewports":0}
```

Recorded combinations:

```text
CATALOG-HIST-001 / desktop      passed
CATALOG-ID-001   / desktop      passed
CATALOG-HIST-001 / mobile-390   passed
CATALOG-ID-001   / mobile-390   passed
```

Post-run gates on the real evidence:

```text
python3 sku-m1-browser/validator/static_validator.py
STATIC VALIDATOR: GREEN

python3 sku-m1-browser/validator/static_validator.py --require-mode AUTHOR_DIAGNOSTIC
STATIC VALIDATOR: GREEN

python3 sku-m1-browser/validator/static_validator.py --require-mode INDEPENDENT_AUTHORITY
STATIC VALIDATOR: RED
  - authority:required_mode_not_met:authority_report:AUTHOR_DIAGNOSTIC
  - authority:required_mode_not_met:invocation_ledger:AUTHOR_DIAGNOSTIC
  - authority:required_mode_not_met:live_execution_contract:AUTHOR_DIAGNOSTIC
  - authority:required_mode_not_met:playwright_report:AUTHOR_DIAGNOSTIC
  - authority:required_mode_not_met:reconciliation_records:AUTHOR_DIAGNOSTIC

python3 sku-m1-browser/tools/scan_artifacts.py
ARTIFACT SCANNER: GREEN (9 files scanned, 0 findings)
```

The `--require-mode INDEPENDENT_AUTHORITY` RED result is the contract working on real
runtime evidence: this author run cannot be presented as independent authority.

Functional proof retained from the frozen journeys:

```text
CATALOG-ID-001 desktop    namespace: CATID-DESKTOP
CATALOG-ID-001 mobile     namespace: CATID-MOBILE-390
CATALOG-HIST-001 desktop  namespace: CATHIST-DESKTOP
CATALOG-HIST-001 mobile   namespace: CATHIST-MOBILE-390
No cross-node namespace collision was observed.
Zero HTTP 401 was observed in backend runtime output (grep -c '401' = 0).
Only the expected negative-path rejections (mismatched uuid/code, cross-tenant uuid,
retired SKU-code reuse) were observed.
Every direct Playwright API request is statically guarded for explicit Authorization
bearer headers.
Mobile navigation is explicitly opened through the `Toggle navigation menu` button.
Back navigation uses the product's actual accessible button roles.
Unavailable unit absence is asserted through unit-level catalog truth.
Historical order snapshot assertions passed after product rename and package deactivation.
```

## Fail-Closed Probes (real Playwright processes, zero browser launches)

```text
no mode            -> ModeResolutionError [mode_unset]            rc=1, results tree byte-identical
both modes         -> ModeResolutionError [both_modes_set]        rc=1, results tree byte-identical
B4_...=YES         -> ModeResolutionError [mode_value_unknown]    rc=1, results tree byte-identical
B3_...=0           -> ModeResolutionError [mode_value_unknown]    rc=1 (probe only)
```

An earlier authoring-time probe also proved the full reporter chain under a VOIDed
preflight: `global-setup` -> preflight VOID -> ledger start/end -> authority report ->
reconciliation produced `mode_mismatches` against the refused cross-mode record and a
nonzero gap with 0 browser launches. That scratch `results/` state was discarded; it is
not part of any evidence set.

## Disclosures

- Five throwaway verification worktrees were consumed while bringing up the fresh
  stack (SMTP sink maildir path, database schema-creation privilege, and the frontend
  `VITE_API_URL` build binding). Every one of those runs aborted during environment
  bring-up or was a non-harness debug script; each left a FAILED ledger in its own
  generated, gitignored `results/` directory. The one completed 4/4 run documented
  above used its own fresh worktree with its own fresh ledger, so the "one invocation
  per fresh worktree" accounting was never bypassed.
- `MPANGO_ENV=production` is required for the backend to deliver real SMTP into the
  local maildir sink (`record_verification_email` only calls the SMTP path in
  production; in `test` it captures into an in-process dev sink that the harness cannot
  read). This is a runtime-stack configuration fact, not a harness change.
- The frontend production build needs `VITE_API_URL` pointing at the backend, otherwise
  it defaults to the relative `/api/v1` on the frontend origin.
- The database role must own the database (tenant schema creation) for
  `provision_wholesaler_and_schema` to succeed.
- `src/fixtures.ts` and `src/reconcile.ts` were touched as control-plane files; the
  byte proofs over `tests/`, `src/provision.ts` and `provisioning/official.json` are
  empty and no functional assertion or namespace was modified.

## Report Correction (B3)

B3's functional author-diagnostic result of 4/4 remains valid, and its evidence is
untouched — no historical B3 evidence is rewritten.

B3's verdict string `READY_FOR_INDEPENDENT_AUTHORITY`, however, was premature. Under
B3 no independent runtime mode existed: the harness could only ever write
`mode=AUTHOR_DIAGNOSTIC`, and the reporter and the fixture recorder were both gated on
the single author variable. An independent verifier executing the B3 runbook would have
produced author-labelled evidence, not independently labelled authority evidence. B4
removes that gap by adding the `INDEPENDENT_AUTHORITY` mode.

## Cleanup Proof

```text
docker ps -a filtered for sku_b4: empty
docker network ls filtered for sku-b4-net: empty
ss filtered for 17801/17802/17803/17804/17805: empty
verification worktrees: removed
```

## Required Statements

```text
H2-C_NOT_EVALUATED
B2_PRODUCT_BYTES_UNCHANGED
B3_FUNCTIONAL_BROWSER_BYTES_UNCHANGED
INDEPENDENT_BROWSER_AUTHORITY_NOT_RUN
PRICING_NOT_STARTED
ORDER_PRICE_NOT_STARTED
REORDER_NOT_STARTED
```

## Handoff

The verifier executes the runbook in `sku-m1-browser/README.md` section 6 with
`B4_INDEPENDENT_AUTHORITY=1` in a fresh worktree at the committed B4 candidate SHA,
then runs:

```text
python3 sku-m1-browser/validator/static_validator.py --require-mode INDEPENDENT_AUTHORITY
```

which is GREEN only when the invocation ledger, the live execution contract, the
authority report, the Playwright report metadata and the reconciliation records all
carry `INDEPENDENT_AUTHORITY` for the same candidate SHA.

Verdict:

```text
PASS_FOR_CTO_DC12R1_MVP_L1_SKU_R0_M1_R1_B4_INDEPENDENT_BROWSER_AUTHORITY_MODE_READY_FOR_EXTERNAL_VERIFIER
```
