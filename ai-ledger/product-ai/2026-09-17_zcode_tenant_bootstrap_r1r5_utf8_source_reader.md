# ZCode-W R1-R5 — Tenant bootstrap: UTF-8 committed-candidate source reader (targeted verification tool closure)

- DATE=2026-09-17
- TASK_ID=MPANGO_TENANT_BOOTSTRAP_R1_R5_UTF8_SOURCE_READER
- AUTHORIZATION_ID=CTO-AUTH-TENANT-BOOTSTRAP-R1-R5-UTF8-SOURCE-READER-2026-09-17
- BASE=909d3e31b720fdc4f2008b90bb3e7bad2f76ac57 (origin R1-R4 branch tip, fetched and verified; no drift)
- BRANCH=zcode/tenant-bootstrap-r1r5-utf8-source-reader-2026-09-17
- WORKTREE=worktrees/zcode_tenant_bootstrap_r1r5_utf8_2026-09-17 (independent, created clean from BASE)
- CANDIDATE_COMMIT=9da7454fe78274afd83e46b758bdf96050715502
- EXECUTOR=Kimi (authorization EXECUTOR field); executed in a ZCode agent session
- VERIFICATION_TIER=V3_TARGETED_VERIFICATION_TOOL_CLOSURE
- CLAIM_CEILING=TEST_TOOL_REPAIR_AND_CANDIDATE_PREPARATION_ONLY
- EVIDENCE_DIR=ai-ledger/product-ai/evidence/2026-09-17_zcode_tenant_bootstrap_r1r5_utf8_source_reader/
- NEXT_GATE=CTO_REVIEW (then KILO only after the CTO point; no merge, no deployment)

## Defect and repair

`_candidate_source()` read `git show` with `subprocess.run(text=True)` and no
encoding, so on Windows (system codec cp936/GBK — codepage 936 on this
machine) any committed file with non-ASCII bytes raised `UnicodeDecodeError`,
and the broad `except` silently fell back to the working tree, breaking the
"checked source == committed candidate" boundary and failing the static
mutation-acceptance node.  Repaired (test tooling only): raw bytes decoded
STRICTLY as UTF-8; subprocess spawn error / non-zero rc / empty output /
invalid UTF-8 each raise RuntimeError; no ignoring, no byte replacement, no
None, and NO working-tree fallback (a git candidate-read failure must not
continue acceptance).

## Scope (verified, cumulative path set)

Changed in the candidate commit (9da7454f):
- `backend/tests/test_tenant_bootstrap_db_authority.py` — the helper + 6 new
  R1-R5 tests.
- `backend/tests/_fixtures/utf8_probe.txt` — new pure-test fixture (non-ASCII
  UTF-8 marker).

Everything else is evidence/journal under `ai-ledger/`.  No bootstrap, grants,
migrations, SMTP, SKU, order, payment, frontend, or mutation-declaration
changes.  Verified: `git diff 909d3e31..HEAD` touches only those two paths
plus `ai-ledger/`; the product scripts (bootstrap/grants) are byte-identical
to BASE (digests below).

## GitNexus impact (real tool run, not fabricated)

Repo indexed fresh (this worktree, commit 909d3e3).  `gitnexus context
_candidate_source` resolves exactly ONE incoming caller,
`test_static_every_mutation_is_parseable_and_fully_declared` (same file);
`gitnexus impact` resolves no other callers (its epistemic caveat is recorded
verbatim in the evidence).  Direct-call grep agrees.  Full output in
`impact_analysis.txt`.

## Encoding environment (environment.txt)

Windows 10.0.26200.9457, Python 3.12.10, system codepage 936 (GBK).  The
inherited shell happens to set PYTHONUTF8=1; the repair does NOT rely on it,
and the focused tests + counterexample were run with PYTHONUTF8=0 (true
Windows default codec cp936) — recorded with locale, utf8_mode, stdout
encoding and the PYTHON* variables for both environments.

## Results

- FINAL FROZEN ACCEPTANCE (single complete run, PYTHONUTF8=0):
  **15/15 PASSED** — exact RED-set validator 5/5, validator self-check +
  formal-gate statics 2/2, declaration integrity + mutation parseability 2/2,
  R1-R5 helper tests 6/6 (node list in the evidence README; full -rA log in
  `pytest_focused_acceptance.txt`).
- Bounded counterexample: the R1-R4 defect restored from BASE bytes → the six
  named assertions FAILED (rc=1) with the exact CTO signature
  `UnicodeDecodeError: 'gbk' codec … illegal multibyte sequence`; failures are
  semantic (missing RuntimeError refusal / working-tree open proven /
  content mismatch), never import or syntax errors.  Restored byte-identically
  (sha256 `685cf270a37335e5…` == original), post-restore 6/6 GREEN.
- Preparation-phase failures kept and documented in `failed_attempts.txt`
  (fixture not yet in HEAD on the pre-commit run — which incidentally proved
  the real-git refusal path; two safe anchor aborts of my counterexample
  script that never modified the file; the GBK `chcp` capture issue).

## NOT executed (authorization boundary)

No PG scenarios, no second cluster, no `alembic upgrade head`, no 104-node
BASE-vs-candidate regression, none of the nine runtime mutations.  The R1-R4
evidence pack is preserved as-is and explicitly marked as NOT re-run this
round; it is NOT inherited as an independent R1-R5 PASS.

## Pre-commit self-check

- Scope: `git diff 909d3e31..HEAD --name-only` shows only the two allowed
  paths plus `ai-ledger/`; product scripts byte-identical to BASE (grants
  `b2ee0eb4320691c0…` wt / `25330f40794f08a2…` blob, bootstrap
  `fc0db06666b44f69…` wt / `3301a55ba995359c…` blob — unchanged from R1-R4).
- `git diff --check`: clean (no whitespace errors).
- Secret scan: the detect-secrets pre-commit hook passed on every commit; no
  new secret-shaped strings were introduced (the fixture marker is plain
  probe text).
- R1–R4 commits, evidence and failure records untouched: empty diffs for the
  R1-R2 evidence (vs its manifest tip 27dd16b8), the R1-R3 evidence (vs
  69e2d5b6) and the R1-R4 evidence (vs 909d3e31) across the new branch.
- Tested bytes vs committed-blob EOL relationship: the helper checks the
  committed blob (LF form via `git show`), which is exactly what the mutation
  declarations are written against; the working-tree CRLF form is
  LF-normalized-identical to the blob (same relationship as the R1-R3/R1-R4
  manifests record for source files).
- Actual call paths verified: the new tests call the real `_candidate_source`
  helper (fake only the `subprocess.run` boundary for the refusal cases);
  the non-ASCII test performs a real `git show` of a real committed file.
- Commits with normal hooks; no `--no-verify`, no amend, no rebase, no
  force-push, no merge, no deployment.

## Successor manifest

- SUCCESSOR_COMMIT=9da7454fe78274afd83e46b758bdf96050715502 (`fix(tests): MPANGO-TENANT-BOOTSTRAP-R1-R5-UTF8-SOURCE-READER …`, normal hooks, no --no-verify, no amend/rebase/force)
- EVIDENCE_COMMIT=e707431d368e7d1309ff21e6bef99c964888652c (targeted evidence pack; R1-R4 and earlier evidence untouched)
- SUCCESSOR_DIGESTS (working-tree CRLF vs committed-blob LF, grouped):
  - v3_suite wt=685cf270 a37335e5 3cb2d19c 8bc154d1 a834a415 0f105c42 f84c7855 b30daa90
  - v3_suite blob=2225bc79 525ca8ac b579d51c 75e4ad45 cdb92b4f b96744cf cdc25ae7 ea8fe822
  - utf8_fixture wt=blob=748639f2 1dfa527e 15a4e726 2eba6f6b ce93005c aab12768 b1ef2598 864630d4
  - NOTE: the v3_suite wt digest equals the sha256 recorded before the counterexample and re-verified after the byte-identical restore — the counterexample left the file exactly at the committed-candidate bytes.
- UNCHANGED-PRODUCT-DIGESTS (proof of zero product drift, identical to R1-R4):
  - grants wt=b2ee0eb4 320691c0 8256daf0 468dd521 361c834c f6e4abd0 b6f56d72 23630764
  - grants blob=25330f40 794f08a2 4213c82f d9fbd3a4 eafa4719 7ed866a4 5761613d 193f4861
  - bootstrap wt=fc0db066 66b44f69 c96463cb 0fea076a 69f90f88 dc4c1885 c1d2abd3 524a4818
  - bootstrap blob=3301a55b a995359c 23da826c 566d821d 17307471 5fbb5c8c d3278e12 74aeff6d
  - harness blob=b3580402 a19b9e9e 190e686d 0e1b69dc 062008a5 d161e3c8 5a8de9d7 9d351fce (worktree is the CRLF form of the same bytes, eol-normalized identical)
- FORMAL_INVOCATIONS=1 focused frozen acceptance (15/15 PASSED); PRE-FORMAL_ITERATIONS documented in failed_attempts.txt (fixture pre-commit failure, two safe counterexample aborts, chcp capture issue) — none deleted
- COUNTEREXAMPLE=bounded, defect restored from BASE bytes -> 6/6 named assertions RED (rc=1) -> byte-identical restore -> 6/6 GREEN; failures semantic, never import/syntax
- NOT_EXECUTED=PG scenarios, second cluster, alembic, 104-node regression, the nine runtime mutations — R1-R4 evidence preserved as-is and NOT inherited as an R1-R5 PASS
- RESULT=R1_R5_CANDIDATE_READY_FOR_CTO_REVIEW
