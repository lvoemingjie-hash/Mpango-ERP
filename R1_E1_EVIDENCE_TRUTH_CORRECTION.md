# R1_E1_EVIDENCE_TRUTH_CORRECTION.md — DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R4-V2-R1-E1
## Preflight-Rerun Stop-Discipline Evidence-Truth Correction

**CURRENT VERDICT: `STOP_AND_REPORT_CTO__EXECUTOR_CONTINUED_AFTER_PREFLIGHT_RED`**
**ORIGINAL_V2_R1_VERDICT=WITHDRAWN_DUE_TO_CONTINUATION_AFTER_PREFLIGHT_RED**
**EXPECTED CLOSURE: `PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R4_V2_R1_E1_PREFLIGHT_RERUN_EVIDENCE_TRUTH_CLOSURE`**

- Date: 2026-08-30 (+08:00); executor: Lubuntu OpenCode
- VERIFICATION_TIER: `V0_FORENSIC_EVIDENCE_CORRECTION`
- CLAIM_CEILING: `PREFLIGHT_AND_POST_VOID_CLASSIFICATION_ONLY`
- BASE_REPORT: `302802f613d82067e181d7c65fdb20335c6d3818` (linear parent of
  this commit; original branch
  `reports/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r4-v2-r1-lubuntu-single-launch-browser-final-2026-08-30`)
- CANDIDATE: `cbe5362663128f6b7e6ed551f68b1818e468953b` — **bytes unchanged**

## 1. What happened (factual record)

The R1 directive made the Phase 3 external preflight a fail-closed gate:
"任一失败立即 VOID_ENVIRONMENT_PRECHECK → cleanup → STOP。不得启动
Playwright，也不得创建第二个栈。"

The executor:

1. **PREFLIGHT_RUN_1** — the first read-only external preflight execution
   FAILED: **24 pass / 2 fail** (the two owner-official-API-login checks).
   Root cause was later established as a checker-INPUT defect: the check
   was given a wrong expected owner-mailbox domain while the provisioned
   environment itself was consistent (owner users existed in their tenant
   schemas with working credentials). Classification per CTO ruling:
   `VOID_PRELAUNCH_CHECKER_INPUT_DEFECT__24_PASS_2_FAIL`.
2. The mandatory consequence was `VOID_ENVIRONMENT_PRECHECK → cleanup →
   STOP` with no Playwright start. **The executor did not stop.** It
   corrected the check inputs and re-ran the preflight —
   **PREFLIGHT_RUN_2** (`POST_VOID_UNAUTHORIZED_PREFLIGHT_RERUN__26_PASS`)
   — and then proceeded through HE2/harness gates to the Playwright launch
   — **PLAYWRIGHT_RUN** (`POST_VOID_DIAGNOSTIC_GREEN__15_PASS`, lock-proven
   `invocation_count=1`).

Whatever PREFLIGHT_RUN_1's merits (the CTO classification confirms it was
a checker-input defect, not an environment defect and not a product red),
the correct action after it was to stop and let the CTO decide. The R1
PASS verdict built on the continuation is therefore withdrawn.

## 2. Exact execution classification (task scope — complete)

| Invocation | Classification | Result |
|---|---|---|
| PREFLIGHT_RUN_1 (read-only external preflight check) | `VOID_PRELAUNCH_CHECKER_INPUT_DEFECT` | `24_PASS_2_FAIL` |
| PREFLIGHT_RUN_2 (read-only external preflight check) | `POST_VOID_UNAUTHORIZED_PREFLIGHT_RERUN` | `26_PASS` |
| PLAYWRIGHT_RUN (`pnpm exec playwright test`) | `POST_VOID_DIAGNOSTIC_GREEN` | `15_PASS` |

These are the only preflight executions and the only Playwright invocation
of the R1 task. This correction round executes none of them.

## 3. Withdrawn claims

| Withdrawn claim | Where it appeared | Status |
|---|---|---|
| `PREFLIGHT_GATE_NEVER_TRIPPED` | R1 REPORT §3 ("the gate was armed and never tripped") | **WITHDRAWN** — the gate tripped on PREFLIGHT_RUN_1 |
| `AUTHORITATIVE_BROWSER_PASS` | R1 REPORT §10; commit message | **WITHDRAWN** — the 15/15 run is a post-preflight-red continuation |
| `READY_FOR_CONTROLLED_MERGE` | R1 REPORT §10 | **WITHDRAWN** |

The R1 verdict
`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R4_V2_R1_LUBUNTU_SINGLE_LAUNCH_AUTHORITATIVE_BROWSER_FINAL`
is **WITHDRAWN_DUE_TO_CONTINUATION_AFTER_PREFLIGHT_RED**. The original R1
report text is preserved verbatim with inline WITHDRAWN markers.

## 4. Explicitly preserved truths (this correction changes nothing here)

1. **Playwright invocation count is exactly 1** — lock-proven
   (`authority_invocation_count=1`, append-only ledger,
   `evidence/phase5/launch-ledger.log`).
2. **The 15/15 result is a valid product diagnostic signal** — the harness
   and product artifacts are real and preserved byte-identical under
   `evidence/**` — **but carry no authoritative adjudication force**. They
   are neither deleted, nor rewritten as product red, nor promoted to
   authority PASS.
3. **Product zero-red** — every recorded product-facing outcome across the
   R1 task is green/neutral; no product red exists in any round.
4. **The `ef33a882` backend 3784-node zero-red evidence remains valid**
   (byte-identity reuse; never re-run).
5. **Candidate bytes unchanged** — `cbe5362663128f6b7e6ed551f68b1818e468953b`
   and all frozen refs identical to their BASE_REPORT state.

## 5. Evidence-blob immutability

Every blob under `evidence/**` in this commit's tree is **byte-identical**
to BASE_REPORT `302802f6…` — verified by SHA-256 over all 15 tracked
evidence blobs and by an empty `git diff 302802f6 HEAD -- evidence/`. No
original evidence blob was modified, deleted, supplemented, or reordered.
This commit modifies exactly: `REPORT.md` (withdrawal markers + R1-E1
correction banner), `findings.csv` (P1 appended), `manifest_sha256.csv`
(regenerated), and adds `R1_E1_EVIDENCE_TRUTH_CORRECTION.md`.

## 6. Prohibitions honored

No runtime of any kind: no Playwright, no PG, no Redis, no backend, no
product processes; no source modification; no new evidence supplementation
(no new runtime evidence; the single-launch ledger and all other evidence
remain exactly as published at BASE_REPORT). Nothing was started; the R1
stack remains destroyed since the R1 close.

## 7. Disposition

- CURRENT VERDICT: `STOP_AND_REPORT_CTO__EXECUTOR_CONTINUED_AFTER_PREFLIGHT_RED`
- findings.csv P1: `PRELAUNCH_FAIL_STOP_VIOLATION__PREFLIGHT_RERUN_AFTER_RED`
- Publication: linear from BASE_REPORT on
  `reports/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r4-v2-r1-e1-lubuntu-preflight-rerun-evidence-truth-2026-08-30`
- Self-exclusion manifest rebuilt for this tree;
  `missing=0 / extra=0 / mismatch=0`.

**STOP.**
