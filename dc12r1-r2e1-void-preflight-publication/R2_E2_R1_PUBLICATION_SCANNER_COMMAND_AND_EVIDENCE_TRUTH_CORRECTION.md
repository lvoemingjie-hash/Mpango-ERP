# R2_E2_R1_PUBLICATION_SCANNER_COMMAND_AND_EVIDENCE_TRUTH_CORRECTION.md
## DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R4-V2-R2-E2-R1 — Publication Scanner Command & Evidence-Truth Closure

CURRENT_R2_E2_R1_VERDICT=`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R4_V2_R2_E2_R1_PUBLICATION_SCANNER_COMMAND_AND_EVIDENCE_TRUTH_CLOSURE`

- Date: 2026-08-31 (+08:00); executor: Lubuntu OpenCode
- VERIFICATION_TIER: `V0_METADATA_CORRECTION`
- CLAIM_CEILING: `PUBLICATION_SCHEMA_AND_SCANNER_EVIDENCE_TRUTH_ONLY`
- BASE: `16d9519a5e35a7394cb8e3645ea26ad6161fa3a4` (E2-R1 parent, exact;
  remote tip of the E1 publication branch)
- CANDIDATE (read-only): `cbe5362663128f6b7e6ed551f68b1818e468953b`

## 1. Prior-round classification (E2)

`E2_CLASSIFICATION=VOID_EXECUTOR_COMMAND_SELECTION_DEFECT__MUTATING_BASELINE_COMMAND_USED`

Retained E2 facts (unchanged): zero commits, zero pushes; the mutating
command form `detect-secrets scan --baseline` was used contrary to the E2
prohibition and rewrote `.secrets.baseline`; the baseline was restored
byte-identical (`c8f3aa245b94d4f4b0242ae8c5a64fbf1f4716483baae91ad65f78735c0290e6`)
and the worktree was removed; frozen refs never drifted. E2's raw=1 and the
historical E1 "4" are **superseded metadata only** — neither is carried
forward as a current scan result, and neither product nor candidate is
blamed.

## 2. Authorized delta (exactly 4 paths vs BASE)

1. `dc12r1-r2e1-void-preflight-publication/REPORT.md`
2. `dc12r1-r2e1-void-preflight-publication/findings.csv`
3. `dc12r1-r2e1-void-preflight-publication/committed-blob-manifest.csv` (rebuilt)
4. `dc12r1-r2e1-void-preflight-publication/R2_E2_R1_PUBLICATION_SCANNER_COMMAND_AND_EVIDENCE_TRUTH_CORRECTION.md` (this file)

Everything else — especially `evidence/**` — is byte-identical to BASE.

## 3. CSV schema (findings.csv)

Strict five-column schema: `finding_id,severity,class,summary,evidence_path`.
All rows exactly 5 columns; IDs unique (F1–F5); F1/F2/F5 carry evidence
paths in `evidence_path`; F3/F4 carry an empty string in `evidence_path`
(column present). Verified with the standard csv parser: uniform width, no
empty IDs, no duplicates, no extra columns, no truncation.

## 4. Scanner execution contract (directive-fixed commands only)

- Tool: `detect-secrets` / `detect-secrets-hook` (version recorded in the
  closure record; 1.5.0 line).
- RAW (exact argv): `detect-secrets scan --all-files <the 4 authorized files>`
  — raw JSON output to task-private `/tmp/r2e2r1-raw.json` (not committed).
- BASELINE-AWARE (exact argv): `detect-secrets-hook --json --baseline
  .secrets.baseline <the 4 authorized files>` — JSON output to task-private
  `/tmp/r2e2r1-hook.json` (not committed).
- Forbidden forms were NOT used: no `detect-secrets scan --baseline`; no
  baseline update/audit/rebuild/format; no pipe that would lose the real
  rc; no scanner-parameter tuning toward any preset count.
- Recording rule: no counts were preset; the execution records (tool
  version, exact argv, rc, scanned file set, finding count, plugin/class,
  file:line, confirmed-secrets count) are reported externally in the
  closure record and are not embedded in the scanned files, so the scanned
  bytes are the final committed bytes.
- Interpretation rule applied: scanner findings that are provably false
  positives (public git SHAs / SHA-256 digest columns / the directive's own
  prohibition vocabulary) permit `SCANNER_EXECUTION_COMPLETED`,
  `CONFIRMED_SECRETS=0`, `AUDITED_FALSE_POSITIVES=<count>`; any
  unclassified or real secret mandates STOP.

## 5. Baseline anti-mutation gate

`.secrets.baseline` SHA-256 recorded before the scans; the file was set
read-only (chmod 444) for the duration of both scans; SHA-256 recomputed
immediately after both scans and the read-only bit released (mode restored;
bytes untouched). Requirement: before == after, and the final bytes equal
BASE. A before != after would have mandated STOP without self-restore.

## 6. Scope declaration

This correction closes EXACTLY the findings.csv CSV schema and the
scanner-command/evidence-truth record. It does NOT upgrade any product,
browser, merge, or release claim. RUN_VERDICT=`VOID_ENVIRONMENT_PRECHECK`,
PRODUCT_VERDICT=`NOT_EVALUATED`, BROWSER_STATUS=`NOT_RUN` and all E1 VOID
facts are retained unchanged; `evidence/**` is byte-identical to BASE.

**STOP — no launcher repair, no B1-R5, no browser run.**
