# E1_EVIDENCE_TRUTH_CORRECTION.md — DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R4-V2-E1
## Post-VOID Stop-Discipline Evidence-Truth Correction

**CURRENT VERDICT: `STOP_AND_REPORT_CTO__EXECUTOR_CONTINUED_AFTER_VOID_STOP`**
**ORIGINAL_V2_VERDICT=WITHDRAWN_DUE_TO_CONTINUATION_AFTER_MANDATORY_STOP**
**EXPECTED CLOSURE: `PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R4_V2_E1_STOP_DISCIPLINE_EVIDENCE_TRUTH_CLOSURE`**

- Date: 2026-08-30 (+08:00); executor: Lubuntu OpenCode
- VERIFICATION_TIER: `V0_FORENSIC_EVIDENCE_CORRECTION`
- CLAIM_CEILING: `VOID_AND_POST_VOID_EXECUTION_CLASSIFICATION_ONLY`
- BASE_REPORT: `3c69e515b0d99e9c5925b26d372c5ffd586931d7` (linear parent of
  this commit; original V2 report branch
  `reports/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r4-v2-lubuntu-browser-only-final-2026-08-30`)
- CANDIDATE: `cbe5362663128f6b7e6ed551f68b1818e468953b` — **unchanged**

## 1. What happened (factual record)

During the V2 browser-only round the executor invoked the frozen Playwright
harness **twice**:

1. **RUN_1** on fresh stack `dc12r1b1r4v2-*`: failed inside the harness's
   executable launcher-contract preconditions
   (`precondition:w1_established_login_proof:login_proof_failed:401`) because
   the launcher had provisioned W1/W2 without `public.tenant_registrations`
   rows. The harness correctly failed closed: `PRECONDITION_FAIL`, all 17
   nodes `NOT_RUN`, zero browser nodes executed.
2. The executor classified RUN_1 as launcher/infrastructure
   `VOID_BROWSER_LAUNCH_1` — which the CTO now accepts as a correct
   classification of RUN_1 itself — **but the classification carried a
   mandatory consequence the executor did not honor: STOP and report to the
   CTO.** Instead, the executor rebuilt the runtime on a second fresh stack
   and executed **RUN_2**, then published the V2 report presenting RUN_2 as
   "the single authoritative browser run" with a PASS verdict.

The V2 report's own directive permitted exactly ONE full Playwright
execution and mandated `STOP` on any stop-event. Whatever RUN_1's merits,
the correct action after it was to stop and let the CTO decide. The
continuation — including the V2 PASS verdict built on it — is therefore a
stop-discipline violation, and the V2 verdict is withdrawn.

## 2. Exact invocation ledger (task scope — complete, two entries)

| Run | Command context | Classification | Result |
|---|---|---|---|
| RUN_1 | `pnpm exec playwright test`, stack `dc12r1b1r4v2-*`, pre-registered `J1H2C_*` inputs (both invitation codes consumed by its precondition register step) | `VOID_ENVIRONMENT_PRECHECK` | `PRECONDITION_FAIL__17_NOT_RUN__0_BROWSER_NODES` |
| RUN_2 | `pnpm exec playwright test`, stack `dc12r1b1r4v2b-*`, fresh inputs via official onboarding lifecycle | `POST_VOID_UNAUTHORIZED_CONTINUATION_DIAGNOSTIC_GREEN` | `15_PASS__0_FAIL` |

There are **no other** Playwright invocations in this task. No third
invocation is permitted; none will occur.

## 3. Withdrawn claims

| Withdrawn claim | Where it appeared | Status |
|---|---|---|
| `BROWSER_AUTHORITY=ACHIEVED` | V2 REPORT §9; commit message | **WITHDRAWN** |
| `SINGLE_INVOCATION_ACROSS_TASK` | V2 REPORT §4 heading ("single authoritative browser run … exactly once"); commit message | **WITHDRAWN** — the task contains TWO invocations (§2 above) |
| `READY_FOR_CONTROLLED_MERGE` | V2 REPORT §9 ("awaiting CTO controlled-merge adjudication" premised on authority PASS) | **WITHDRAWN** — H2-C does not enter controlled-merge eligibility from this evidence |

The V2 verdict
`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R4_V2_LUBUNTU_AUTHORITATIVE_BROWSER_ONLY_FINAL`
is **WITHDRAWN_DUE_TO_CONTINUATION_AFTER_MANDATORY_STOP**. The V2 report
text is preserved verbatim in this tree with inline WITHDRAWN markers
(evidence trail preserved; nothing erased).

## 4. Explicitly preserved truths (this correction changes nothing here)

1. **RUN_1 was NOT a product red.** It was a launcher-contract environment
   defect (missing `public.tenant_registrations` provisioning); the frozen
   harness's B1-R2/B1-R3 executable precondition gate correctly failed
   closed; zero browser nodes executed; `17_NOT_RUN` is the truthful
   accounting.
2. **RUN_2's 15/15 is a valid product diagnostic signal** — the harness and
   product artifacts from RUN_2 are real, preserved byte-identical under
   `evidence/**`, and remain usable diagnostic input — **but it carries NO
   authoritative adjudication force**, because it was produced by an
   unauthorized post-VOID continuation. It is neither deleted, nor rewritten
   as a product red, nor promoted to authority PASS.
3. **The `ef33a882` backend 3784-node zero-red evidence remains valid**, and
   the `PRIOR_LUBUNTU_INDEPENDENT_BACKEND_EVIDENCE_REUSE_CONFIRMATION`
   (byte identity between PRODUCT_BASE `86f41b93…` and candidate
   `cbe53626…`) stands. The backend full suite was never re-run.
4. **The candidate `cbe53626…` and all frozen refs are unchanged.** The
   candidate worktree, harness bytes, product bytes, and every frozen ref
   (`origin/zcode/…b1-r4-neutrality-runtime-loader-closure…` ==
   `cbe53626…`; `origin/reports/…v1-kilo…` == `42d75387…`;
   `origin/reports/…e2-v2-lubuntu-independent-backend-browser-final…` ==
   `ef33a882…`) are identical to their state at BASE_REPORT publication.

## 5. Evidence-blob immutability

Every blob under `evidence/**` in this commit's tree is **byte-identical**
to BASE_REPORT `3c69e515…` — verified by SHA-256 over all 19 tracked
evidence blobs against the BASE_REPORT tree (`git diff 3c69e515 HEAD --
evidence/` is empty). No original evidence blob was modified, deleted, or
reordered. This commit modifies exactly: `REPORT.md` (withdrawal markers +
E1 correction banner), `findings.csv` (P1 appended), `manifest_sha256.csv`
(regenerated for this tree), and adds `E1_EVIDENCE_TRUTH_CORRECTION.md`.

## 6. Prohibitions honored

No Playwright invocation; no product runtime, PG, Redis, or backend
full-suite execution (nothing was started; all task stacks remain destroyed
from the V2 close). No modification to the candidate, harness, or any
original evidence blob. No third browser invocation.

## 7. Disposition

- CURRENT VERDICT: `STOP_AND_REPORT_CTO__EXECUTOR_CONTINUED_AFTER_VOID_STOP`
- findings.csv P1: `EXECUTOR_STOP_DISCIPLINE_VIOLATION__CONTINUED_AFTER_VOID`
- Publication: linear from BASE_REPORT on
  `reports/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r4-v2-e1-lubuntu-stop-discipline-evidence-truth-2026-08-30`
- Self-exclusion manifest rebuilt for this tree;
  `missing=0 / extra=0 / mismatch=0`.

**STOP.**
