# INVALID_EVIDENCE_RECONCILIATION — OpenCode V2 Full Browser Report

**Supersedes**: `reports/dc12r1-mvp-l1-pw1-r2-r2-v2-opencode-full-browser-2026-08-15` (ba9da9b)
**Date**: 2026-08-15 (PW1-R3; facts corrected by PW1-R3-R1)
**Status**: INVALID_EVIDENCE_RECONCILIATION — superseded; preserved as historical evidence.

## Corrected facts (verified against the committed V2 artifacts, 2026-08-15)

| Metric | V2 report claimed | Artifact-verified (V2 junit.xml) |
|---|---|---|
| Collected | 162 | **162** testcases ✓ |
| Passed | 80 | **104** (162 − 58) |
| Failed | 82 | **58** `<failure>` blocks |
| 429-caused failures | "all 82" | **47** failure blocks mention 429 (message or body) |
| Non-429 failures | — | **11** failure blocks do not mention 429 (incl. 3× "public auth pages are reachable anonymously", Phase 4 idempotency/print nodes, Phase 5 isolation nodes) |

## Why the evidence chain is invalid

1. The report's headline numbers (80 passed / 82 failed, "all 429") contradict
   the machine-derived JUnit accounting (104 passed / 58 failed; 47 with 429,
   11 without). The narrative is not reconcilable with the committed artifact.
2. No raw Playwright per-node JSON exists on the branch; `results.json` is a
   hand-built summary. Node-level attribution is therefore unverifiable.
3. The 11 non-429 failures (element-visibility/timeout-class errors) were
   neither counted nor root-caused in the report.

## Correction of PW1-R3's own earlier audit note

PW1-R3's first marker (commit 07013d2) claimed the V2 JUnit contained "zero
failure cases" — that was an audit REGEX error by the reviewer (the failure
elements exist but attribute ordering did not match the pattern used). The
correct audit is the table above: 162 testcases / 58 failures / 47 with 429 /
11 without. The supersede verdict stands, for the corrected reason: the
REPORTED counts contradict the machine artifacts.

## Disposition

- The V2 branch and its artifacts remain untouched as historical evidence.
- PW1-R3 closes the underlying product defect (contextual JWTs use
  `rate_limit:tenant:{tenant_id}:{user_id}` limit 1000; anonymous/identity-only
  stay on the IP bucket limit 100; rejected auth is rate-limited on the same
  IP bucket — no unlimited bypass).
- Browser acceptance reruns (162/162 with machine-derived JUnit accounting)
  are to be executed by OpenCode after the PW1-R3-R1 Kilo bounded source review.
