# E1 EVIDENCE-TRUTH CORRECTION — DC-12R1-MVP-L1-J1-H2-C-I1-R1-V1
## Authority Preflight Evidence-Truth Correction (V0_FORENSIC_EVIDENCE_CORRECTION)

- Executor: the original Lubuntu OpenCode2 executor of I1-R1-V1
- Candidate (never modified): `42c5d3286cacaf48604550eecd881e379cc76818`
- Base report (never modified): `0f6f790b11a3c2a316fc276df727fa19271b3616`
- Claim ceiling: `VOID_ENVIRONMENT_EVIDENCE_TRUTH_ONLY`
- No pytest, no Playwright, and no product runtime was run in this E1
  round. Every statement below is derived exclusively from evidence
  blobs already committed in the base report plus read-only inspection
  of the unchanged candidate tree.

## 1. Original verdict — preserved verbatim

**ORIGINAL_RUNTIME_VERDICT:** `STOP_AND_REPORT_CTO_WITH_FIRST_AUTHENTIC_RED`

The original verdict line is retained by reference and never deleted or
rewritten; the base-report branch remains byte-identical and published.

## 2. Current effective verdict — superseded by evidence truth

**EFFECTIVE_VERDICT: `VOID_ENVIRONMENT_PRECHECK`**

The effective round verdict is reclassified from
`STOP_AND_REPORT_CTO_WITH_FIRST_AUTHENTIC_RED` to
`VOID_ENVIRONMENT_PRECHECK`. VOID does not constitute a product,
candidate, or test RED (task-contract rule 二.12). The PASS verdict of
the I1-R1-V1 task remains **not awarded** — this correction changes the
classification of the round, not its outcome.

## 3. Withdrawals

| Withdrawn | Replacement statement |
|---|---|
| "Phase 2 — Fail-Closed Preflight: PASS" | WITHDRAWN. The formal preflight passed only the checks it implemented; it failed to bind or verify the three decisive environment dimensions listed in §6. The preflight PASS is therefore not valid evidence of a complete fail-closed precondition gate for this candidate's temp-DB and CWD contracts. |
| "Phase 4 — Single Authoritative Backend Run (AUTHENTIC RED)" | WITHDRAWN as an authoritative backend result. The run is VOID_ENVIRONMENT_PRECHECK: every one of its 88 red nodes is deterministically attributable to executor-environment omissions (§5), never to candidate behavior. |

The two VOID launcher invocations and all original execution evidence
(`evidence/void/*`, `evidence/backend/*`, `evidence/runner/*`) are
retained byte-for-byte and are NOT rewritten or reinterpreted in place;
this document is the sole interpretive correction layer.

## 4. The 3784-executed fact — retained, attribution invalidated

Fact retained: 3784 nodes were collected (frozen baseline) and 3784
nodes were executed once by the authority runner
(`sentinel_calls=1`), reconciled with gap=0
(`evidence/backend/backend-reconciliation.json`).

Declaration: because all 88 non-green nodes are attributable to the
executor environment (§5) and the runtime CWD/DB contracts were
unverifiably configured, **the execution has no product-attribution
validity**. No claim of product pass, product red, product regression,
or product health may be derived from this run. The counts are
process-facts, not product verdicts.

## 5. Deterministic attribution of the 88 red nodes (gap = 0)

Derived exclusively from the retained JUnit blob
(`evidence/backend/junit-authoritative.xml.gz`) and the unchanged
candidate source. Every red node falls into exactly one family:

| Family | Count | Exact failure signature | Candidate source binding | Root cause (executor environment) |
|---|---|---|---|---|
| CWD | **25** | 24× `FileNotFoundError` on repo-relative paths (e.g. `jobs/export_jobs.py`) + 1× `alembic.util.exc.CommandError: Path doesn't exist: alembic` | test files read backend-relative paths; `alembic.ini`/`alembic/` are backend-relative | The authority runner launched the product command with process CWD = worktree root instead of `backend/` |
| MPANGO_TEMP_DB_ALLOWED_PORTS | **57** | `RuntimeError: temporary database source port is not explicitly allowed` | `backend/tests/async_test_utils.py:112-116` — the temp-DB source port must appear in `MPANGO_TEMP_DB_ALLOWED_PORTS` (comma list) | The executor never set `MPANGO_TEMP_DB_ALLOWED_PORTS`; the task DB port (17432) was therefore not in the allowlist |
| unsafe test DB name | **6** | `RuntimeError: temporary database source must have an explicit test name` | `backend/tests/async_test_utils.py:119-120` with `_TEST_DATABASE_NAME = ^(?:test|pytest|ci)[_-][a-z0-9_-]+$` (line 22) | The task DB name `mpango_erp_test` does not match the candidate's mandatory test-name pattern (must start `test_`/`pytest_`/`ci_`/`test-`/…) |
| **total** | **88** | | | **gap = 88 − (25+57+6) = 0** |

Reconciliation identity: 67 failures + 21 errors = 88 red nodes =
25 + 57 + 6 + 0. Every red node is an executor-environment omission
manifested through the candidate's own fail-closed safety gates. **None
of the 67 failures / 21 errors is attributable to a product defect.**

## 6. Preflight omissions (why the preflight could not catch this)

The formal preflight (`AUTHORITY_H2C_BACKEND`, `--preflight-only`,
`state=PREFLIGHT`) verified: PG role truth, temp-DB create/drop
capability, alembic single head, Redis DB15 emptiness, sentinel
unreachability, env-var presence, canonical origin, lineage, email
domain. It did NOT verify — and its grep-count is 0 occurrences for
each of these in both the runner (`harness-governance/validator/
authority_runner.py`) and the runner-owned child plugin
(`harness-governance/tests/pytest_et1_collector.py`):

1. **Real process CWD was never bound or validated.** The runner
   launches the product command via `subprocess.run(command,
   shell=False)` inheriting the runner's CWD; no check pins it to the
   `backend/` directory that the suite's relative-path contract
   assumes.
2. **`MPANGO_TEMP_DB_ALLOWED_PORTS` was never verified.** The runner's
   `eval_temp_db` proves CREATEDB capability by direct
   create/drop but never consults the candidate's own port allowlist
   contract, so a suite run whose temp-DB helpers enforce the allowlist
   was predictable-ly red.
3. **`TEST_DATABASE_URL` database-name safety was never verified**
   against `_TEST_DATABASE_NAME` (`async_test_utils.py:22`).
4. **`pytest_sessionstart` re-verified none of the above three** — the
   child-side proof re-checks role, URL presence, capability flag and
   nonce/SHA bindings only (`pytest_et1_collector.py`, sessionstart
   section). All three decisive dimensions passed the round unbound.

## 7. Strict-reverse 11 errors — separate classification

The strict whole-list file-reversal diagnostic
(`evidence/backend/bundle-reverse-strict-diagnostic.log.gz`, 38 passed
+ 11 errors) is a PRE-GATE-phase test-global-state coupling: the H2-C
module's own fail-closed entry gate fires on in-process retailer email
sink residue left by S1-family modules. It is hereby single-classified
**`TEST_GLOBAL_STATE_RESIDUE`** and is NOT part of, and must not be
mixed into, the (now VOID) Phase 4 authority result. It was never
counted in the 3784/88 figures; this entry fixes its classification
label only.

## 8. Browser phase

Browser remains **NOT_RUN**; `pnpm exec playwright test` invocation
count = **0** (unchanged from the base report).

## 9. Blob immutability statement

All evidence blobs of the base report are carried into this branch
byte-for-byte. The E1 commit tree differs from the base-report tree in
exactly four paths — `REPORT.md`, `findings.csv`,
`E1_EVIDENCE_TRUTH_CORRECTION.md`,
`committed-blob-manifest.csv` — as verified by the tree-diff recorded
at commit time. No evidence blob was modified, deleted, or rewritten.

## 10. E1 verdict

**`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I1_R1_V1_E1_AUTHORITY_PREFLIGHT_EVIDENCE_TRUTH_CLOSURE`**

Scope: evidence-truth classification only, per
`VOID_ENVIRONMENT_EVIDENCE_TRUTH_ONLY`. No product, backend, browser,
merge, or deployment claim is made. The round's effective verdict is
`VOID_ENVIRONMENT_PRECHECK`; any authoritative re-run requires a
follow-up round that first closes the four preflight omissions of §6.

**STOP.**
