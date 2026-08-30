# R2_E1_VOID_ENVIRONMENT_EVIDENCE_TRUTH.md
## DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R4-V2-R2-E1 — Forensic Evidence-Truth Record

RUN_VERDICT=VOID_ENVIRONMENT_PRECHECK
OVERALL_STATUS=STOP_AND_REPORT_CTO_WITH_VOID_ENVIRONMENT_PRECHECK
CONFIRMED_CAUSE=EXECUTOR_LAUNCHER_MATERIALIZATION_DATA_LOSS__OWNER_EMAIL_LABEL_OVERWRITTEN
SECONDARY_CONTROL_PLANE_DEFECT=APPEND_ONLY_TRANSITION_FROM_STATE_CAPTURED_AFTER_MUTATION
PRODUCT_VERDICT=NOT_EVALUATED
BROWSER_STATUS=NOT_RUN

## 1. Scope

This document is the evidence-truth record for the R2 round's terminal
VOID. It publishes only what the directive requires: the first-preflight
red, the immediate terminal STOP, and the cleanup closure. Nothing was
repaired, re-run, restarted, or re-probed for this publication.

## 2. Timeline (append-only ledger, `evidence/state-ledger.jsonl`)

| # | Event | Meaning |
|---|---|---|
| 1 | INIT | state=INIT, counts 0/0, terminal_stop=false |
| 2 | MATERIALIZED | onboarding completed; materialized-identity frozen (0444) with contract SHA binding |
| 3 | TRANSITION → STACK_READY | one stack up, services healthy |
| 4 | SHA_POINTERS_FROZEN | contract+materialized SHA pointers written (0444) |
| 5 | TRANSITION → PREFLIGHT_RUNNING | gate armed |
| 6 | ATOMIC_INCREMENT preflight_invocation_count=1 | the ONE preflight began |
| 7 | VOID (terminal_stop=true) | 2/29 checks red → VOID_ENVIRONMENT_PRECHECK, cleanup, STOP |

Ledger-side disclosure (F2): `TRANSITION` entries recorded the `from`
state after mutation (`from == to`), and the three post-STOP wrapper
refusals were printed but not ledger-appended; their verbatim transcript is
`evidence/playwright-wrapper-refusal.txt`. Both aspects are preserved
as-published; the launcher was not repaired in this round.

## 3. The single preflight (facts)

- `preflight_invocation_count=1` (atomic 0→1 before execution).
- 29 checks total: **27 passed, 2 failed**.
- Failed: `w1_owner_official_api_login`, `w2_owner_official_api_login`
  (`evidence/browser-preflight.json`, `failed_checks`).
- Integrity checks inside the same preflight were GREEN: contract SHA and
  materialized SHA unchanged vs the frozen pointers.
- Per the R2 directive's absolute clause, checker/input/environment defects
  count identically: VOID_ENVIRONMENT_PRECHECK → cleanup → STOP. No input
  modification, no read-only rerun, no stack swap, no preflight re-execution.
- `terminal_stop=true`; subsequent transition/bump attempts refused with
  rc=50 (`evidence/playwright-wrapper-refusal.txt`).
- `playwright_invocation_count=0` for the whole task; no second stack was
  ever created.

## 4. Confirmed causal chain (exact)

1. Onboarding output per side originally contained `owner_email_label`.
2. `out.update(got)` was overwritten by the codes/schema-only registry
   result.
3. The materialized file lost `owner_email_label`
   (`evidence/materialized-runtime-input.json`, `defect_note`; original
   bytes SHA-256 in `evidence/materialized-runtime-input.sha256`).
4. The preflight login checks KeyError'd and returned false.
5. Two checks RED → VOID + terminal STOP.

The manual owner-login probe (HTTP 200) performed during the read-only
diagnosis is recorded as **DIAGNOSTIC_ONLY** — it is NOT a preflight PASS
and never entered any verdict. No probe was re-performed for this
publication.

## 5. Original-vs-committed SHA-256 accounting

| Original (task-private; NOT committed) | SHA-256 | Committed sanitized copy |
|---|---|---|
| `execution-contract.json` | `636757163ebfcb8afd3bd919111018bc17a2692d4ef56b7683a84f6db65835fd` | `evidence/execution-contract.json` (domain/email/path labels redacted) |
| `materialized-identity.json` | `3f37aa2bd271a123803883fd107a396d28ad5db5c27a2d27ad966eb23f0597fa` | `evidence/materialized-runtime-input.json` (structure-truthful; ids/schemas/codes/codes redacted) + `evidence/materialized-runtime-input.sha256` |
| `browser-preflight.json` | `205652349a9128f359e40425045eb1e345ff703444963fee79c063fe6ed675be` | `evidence/browser-preflight.json` (verbatim; already value-free) |
| `frozen-sha-pointers.json` | `472d16a8d803ac9bd6c8c9bc8edd2343cec98ca3897fb70796317344b665fa74` | integrity facts mirrored in `browser-preflight.json.integrity` |
| `machine-state/state-ledger.log` | `f1dc87d2999f2edead6702c760af01091d2b59845e621483a6ea43f4cc6811ba` | `evidence/state-ledger.jsonl` (verbatim) |

Sanitized-copy SHA-256 values are recorded in `committed-blob-manifest.csv`
(which covers this commit's tree, stably sorted, self-excluding).

## 6. Prohibitions honored

No preflight, Playwright, pytest, or product-test execution; no PG, Redis,
backend, frontend, or container start; no input fixes, read-only reruns,
stack swaps, or retroactive probes; no modification of the candidate,
harness, product source, or historical evidence; the manual login 200 is
not promoted to a preflight PASS; B1-R5 not started; no merge, deploy,
amend, rebase, or force-push.

## 7. Closure

RUN_VERDICT=VOID_ENVIRONMENT_PRECHECK; OVERALL_STATUS=
STOP_AND_REPORT_CTO_WITH_VOID_ENVIRONMENT_PRECHECK; PRODUCT_VERDICT=
NOT_EVALUATED; BROWSER_STATUS=NOT_RUN. Cleanup verified complete
(`evidence/cleanup-closure.json`, `all_clear=true`).

**STOP — no B1-R5, no third browser task.**
