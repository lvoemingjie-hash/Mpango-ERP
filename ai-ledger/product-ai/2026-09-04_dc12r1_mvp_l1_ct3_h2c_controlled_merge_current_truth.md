# DC-12R1-MVP-L1-CT3 H2-C Controlled-Merge Current Truth

## Classification

- `TASK=DC-12R1-MVP-L1-CT3`
- `VERIFICATION_TIER=V0_DOCUMENTATION_CURRENT_TRUTH`
- `CLAIM_CEILING=CURRENT_TRUTH_DOCUMENTATION_CANDIDATE_ONLY`
- `BASE=bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f`
- `PRODUCT_DELTA=0`
- `TEST_FILES_ADDED_OR_MODIFIED=NONE`
- `FULL_SUITE_RESULT=NOT_RUN_DOCS_ONLY`
- `BROWSER_RUNTIME=NOT_RUN_DOCS_ONLY`

## Accepted H2-C Chain

- Controlled merge: `bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f`
- Merge parents: `24a28d76d6d9483d8101f8e0f537c148dc262859`
  and `ddba2d3eda847f2c15a0f057b5f7ff2f598f38d0`
- Merge tree: `29a1c39a0b0f8f3e620c4feb4ee6dccb84448d9b`
- Kilo source/test authenticity review: `3db164dd7146b27ee7b324c0582649680e341ce2`
- Lubuntu authoritative browser final:
  `da6bf9e7f58aaf732fef40aaf3f05735644fbf74`
- Two-stage merge-readiness rehearsal:
  `ba65ecf668fdfafae503287f0924fb193c4664d6`
- Controlled merge report: `76b837f8c4f522173bc38e4f9d56085dc218cc75`
- Browser reconciliation: 15 browser + 2 static PASS; zero
  FAIL/NOT_RUN/PENDING; gap 0.
- Backend zero-red evidence: `ef33a882`, reused by byte identity for the final
  source and not rerun by the controlled merge task.

The earlier H2-C candidate `42c5d328` and the corrected
`VOID_ENVIRONMENT_PRECHECK` report `31adf492` remain immutable historical
evidence. They are superseded for current H2-C qualification and were not
deleted or reclassified.

## Current Product Truth

- `origin/product-dev-recovered@bd2373cb` is the reviewed product baseline.
- H2-C is `MERGED_AND_INDEPENDENTLY_BROWSER_VERIFIED`.
- The former `RT0 = BLOCKED_BY_H2_C` discovery blocker is closed.
- Product migration head remains `037_payment_declarations_schema`.
- SKU migration `038` is not in the baseline.
- SKU candidate `c05c5ff1` is outside the current baseline and still requires
  evidence-integrity disposition, current-baseline integration, independent
  final review, and controlled merge.
- `PRICING-R0`, `PRICING-R1`, `ORDER-PRICE-R1`, and `REORDER-R1` remain frozen
  until SKU convergence is accepted.
- `REMOTE_PUSH_SUCCEEDED=true` for the H2-C controlled merge.
- `REMOTE_ENFORCEMENT_NOT_VERIFIED=true`.
- No deployment, VPS, HTTPS, real-device, customer-ready, or release-approved
  claim is made.

## Documentation Scope

This task updates only:

- `docs/ai/CTO_CURRENT_OPS.md`
- `docs/ai/PROJECT.md`
- `docs/planning/2026-08-26_mvp_pre_delivery_execution_queue.md`
- this ledger

No product source, migration, test, dependency, workflow, harness, candidate,
historical evidence, or protected ref is modified by this documentation task.

## Verification

- `origin/product-dev-recovered` was fetched and matched `bd2373cb` before the
  documentation update.
- Source `ddba2d3e`, Kilo `3db164dd`, Lubuntu `da6bf9e7`, rehearsal
  `ba65ecf6`, and merge report `76b837f8` matched their remote refs.
- The staged delta contains exactly the four documentation paths listed above.
- GitNexus staged `detect_changes` reported 4 files, 15 documentation nodes,
  0 affected execution processes, and `risk_level=low`.
- `git diff --cached --check` passed.
- All four staged blobs are strict UTF-8, no BOM, no NUL, no CR, and LF-ended.
- Read-only `detect-secrets-hook` returned 0 and `.secrets.baseline` remained
  byte-identical with SHA-256
  `f49c86223abc95af12d0f6c60938050a68a84e332a94a444800cd93450bd16bf`.
- Product and browser test suites were not run because the delta is docs-only.
