# REPORT.md — DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R4-V2-R2-E1
## VOID Environment Preflight Evidence Publication Closure

**RUN_VERDICT=VOID_ENVIRONMENT_PRECHECK**
**OVERALL_STATUS=`STOP_AND_REPORT_CTO_WITH_VOID_ENVIRONMENT_PRECHECK`**
**CONFIRMED_CAUSE=`EXECUTOR_LAUNCHER_MATERIALIZATION_DATA_LOSS__OWNER_EMAIL_LABEL_OVERWRITTEN`**
**SECONDARY_CONTROL_PLANE_DEFECT=`APPEND_ONLY_TRANSITION_FROM_STATE_CAPTURED_AFTER_MUTATION`**
**PRODUCT_VERDICT=NOT_EVALUATED**
**BROWSER_STATUS=NOT_RUN**

This branch publishes ONLY the forensic evidence of the R2 round's first
preflight red, the immediate terminal STOP, and the cleanup closure. It
adds one independent report directory
(`dc12r1-r2e1-void-preflight-publication/`) directly on top of the
candidate `cbe5362663128f6b7e6ed551f68b1818e468953b` and modifies zero
existing files. The launcher was NOT fixed; no check was re-run; no runtime
of any kind was started. The manual owner-login 200 observed during the
read-only diagnosis remains `DIAGNOSTIC_ONLY` and is NOT a preflight PASS.

- Date: 2026-08-30 (+08:00); executor: Lubuntu OpenCode (R2 executor)
- VERIFICATION_TIER: `V0_FORENSIC_EVIDENCE_PUBLICATION`
- CLAIM_CEILING: `VOID_ENVIRONMENT_PRECHECK_EVIDENCE_TRUTH_ONLY`

## 1. Proof gate

All six directive references verified after `git fetch --all --prune` and
re-verified unchanged at close: CANDIDATE `cbe53626…`,
KILO_REVIEW `42d75387…`, PRODUCT_BASE `86f41b93…`,
PRIOR_BACKEND_EVIDENCE `ef33a882…`, PRIOR_STOP_CORRECTION `24b94bab…`,
PROTECTED_BASELINE `24a28d76…` — each local-resolvable and
origin-contained. Publication worktree: independent, detached, exactly at
the candidate; commit parent == CANDIDATE (exact).

## 2. Recorded execution facts (R2 task)

| Fact | Value |
|---|---|
| `preflight_invocation_count` | **1** (atomic 0→1, append-only ledger) |
| preflight checks | **29** |
| passed / failed | **27 / 2** |
| failed checks | `w1_owner_official_api_login`, `w2_owner_official_api_login` |
| `terminal_stop` | **true** |
| `playwright_invocation_count` | **0** |
| wrapper post-STOP refusals | transition/bump refused, **rc=50** ×3 (transcribed, `evidence/playwright-wrapper-refusal.txt`) |
| input fixes / reruns / stack swaps | **none** |
| manual owner login 200 | **DIAGNOSTIC_ONLY** (read-only; never a preflight PASS) |
| candidate product/harness bytes | **NOT evaluated red or green this round** |
| contract / materialized SHA drift | none (integrity checks green) |

## 3. Confirmed causal chain (exact)

1. Onboarding output per side originally contained `owner_email_label`.
2. `out.update(got)` overwrote those per-side dicts with the registry
   result, which carried only `canonical_code` / `wholesaler_id` /
   `tenant_schema`.
3. The materialized runtime-input file therefore LOST `owner_email_label`
   on both sides (`evidence/materialized-runtime-input.json`,
   `defect_note`; original bytes SHA-256 in
   `evidence/materialized-runtime-input.sha256`).
4. The single preflight's owner-login checks raised KeyError and recorded
   `false` (`evidence/browser-preflight.json`, `failed_checks`).
5. Two checks RED → per the R2 directive's absolute clause:
   `VOID_ENVIRONMENT_PRECHECK` + `terminal_stop=true` + cleanup + STOP.

Secondary control-plane defect (disclosed, unfixed): the state machine's
guard path prints refusals without appending them to the append-only
ledger, and `TRANSITION` entries captured the `from` state after mutation;
the refusal events are therefore preserved only as the verbatim
transcription in `evidence/playwright-wrapper-refusal.txt`.

## 4. Published evidence (sanitized; originals task-private)

| File | Content |
|---|---|
| `evidence/execution-contract.json` | sanitized contract copy (identity domain + email labels + path labels redacted); original SHA `63675716…35fd` |
| `evidence/materialized-runtime-input.json` | structure-truthful sanitized copy proving the field-loss defect |
| `evidence/materialized-runtime-input.sha256` | SHA-256 of the original task-private bytes (`3f37aa2b…97fa`) |
| `evidence/browser-preflight.json` | verbatim sanitized preflight result (29 checks; no emails/domains/secrets) |
| `evidence/state-ledger.jsonl` | verbatim append-only machine-state ledger (7 events: INIT → … → VOID) |
| `evidence/playwright-wrapper-refusal.txt` | transcribed post-STOP refusals (rc=50 ×3) with transcription disclosure |
| `evidence/cleanup-closure.json` | residue verification at publication: containers/networks/volumes none; ports free; sentinel unreachable; credentials/maildir/venv absent; worktree deregistered |

Original-vs-committed SHA-256 accounting for every evidence blob is in
`R2_E1_VOID_ENVIRONMENT_EVIDENCE_TRUTH.md` §5. No URLs, passwords, tokens,
SECRET_KEY, owner-email actual values, or environment-variable values enter
this commit; environment variables are recorded as name + presence only
(within the preflight JSON's boolean contract).

## 5. Findings register

`findings.csv`: **F1** P1 LAUNCHER_MATERIALIZATION_FIELD_OVERWRITE;
**F2** P1 TRANSITION_AUDIT_FROM_STATE_CAPTURE_DEFECT; **F3** INFO
PRODUCT_CANDIDATE_NOT_EVALUATED; **F4** INFO PLAYWRIGHT_NOT_RUN; **F5**
INFO CLEANUP_COMPLETE.

## 6. Integrity gates

Commit parent == `cbe53626…` (exact); delta vs candidate = the single new
report directory only; `committed-blob-manifest.csv` stably sorted,
self-excluding: **missing=0 / extra=0 / mismatch=0**; `git diff --check`
clean; all published text strict UTF-8, no BOM, no NUL, LF-only;
`detect-secrets`: **0 findings**; `local == remote` after push; all six
frozen references unchanged at close; host residue: none
(`evidence/cleanup-closure.json`, `all_clear=true`).

## 7. Adjudication

The R2 claim ceiling was not approached: the task terminated at the
preflight gate by design. PRODUCT_VERDICT=NOT_EVALUATED;
BROWSER_STATUS=NOT_RUN; the backend zero-red evidence (`ef33a882`)
remains untouched and un-re-run. This publication is evidence-truth only.

**VERDICT: `PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R4_V2_R2_E1_VOID_ENVIRONMENT_PRECHECK_EVIDENCE_PUBLICATION_CLOSURE`. STOP — no B1-R5, no third browser task.**
