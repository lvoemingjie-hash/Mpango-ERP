# ZCode-W R1-R5-R1 — Tenant bootstrap: AST sentinel closure (one test-assertion repair)

- DATE=2026-09-17 (authorization; executed 2026-09-18)
- TASK_ID=MPANGO_TENANT_BOOTSTRAP_R1_R5_R1_AST_SENTINEL_CLOSURE
- AUTHORIZATION_ID=CTO-AUTH-TENANT-BOOTSTRAP-R1-R5-R1-AST-SENTINEL-CLOSURE-2026-09-17
- FROZEN_BASE=4057808df5b0811e3c16cc682d5c1a8337bf64b8 (reviewed R1-R5 tip; remote verified equal before branching; original R1-R5 BASE 909d3e31b720fdc4f2008b90bb3e7bad2f76ac57 remains in ancestry)
- BRANCH=zcode/tenant-bootstrap-r1r5-r1-ast-sentinel-closure-2026-09-17
- WORKTREE=worktrees/zcode_tenant_bootstrap_r1r5r1_ast_2026-09-17 (isolated, created clean)
- CANDIDATE_COMMIT=f440bfc856e021684e0772cb01cf579e938aae1e
- EXECUTOR=KIMI (authorization EXECUTOR field); executed in a ZCode agent session
- VERIFICATION_TIER=V3_TARGETED_VERIFICATION_TOOL_CLOSURE
- CLAIM_CEILING=ONE_TEST_ASSERTION_REPAIR_AND_TARGETED_EVIDENCE_ONLY
- EVIDENCE_DIR=ai-ledger/product-ai/evidence/2026-09-17_zcode_tenant_bootstrap_r1r5r1_ast_sentinel/
- NEXT_GATE=CTO_REVIEW, then fresh Kilo targeted source/encoding/checker review on the NEW candidate (no broad DB rerun required for this test-only delta)

## CTO finding F1 (P2) — confirmed independently before fixing

The R1-R5 structural sentinel searched for the literal text `open(` inside
`ast.dump(...)`; `ast.dump` renders a call as `Call(func=Name(id='open', …)`,
so the text never matched and the assertion accepted a helper containing a
real `open()` call. Reproduced here on BASE bytes before any edit: an injected
`with open(rel_path…) / handle.read()` produced a real `Name(id='open'` call
node while `ast.dump` contained no `open(` text, and the old predicate PASSED
(false green). PRODUCT_DEFECT_FOUND_THIS_REVIEW=NO is unchanged: the helper's
raw-byte capture, strict UTF-8 decode and refusals were confirmed intact.

## The repair (one assertion + its counterexample; nothing else changed)

- `_assert_helper_reads_only_committed_candidate()`: real AST-node inspection
  — flags `open()` and `builtins.open()` calls, bare/broad except handlers
  (`except:`, `Exception`, `BaseException`, alone or in an except-tuple), and
  requires a strict `.decode("utf-8")`. Documented as BOUNDED structural
  inspection of the named helper's own AST (two explicit known APIs), not a
  general data-flow proof; indirect reads via other functions are covered by
  the behavioral tests (working-tree open spy + refusal tests).
- `test_static_candidate_source_has_no_working_tree_fallback`: SAME node ID,
  now the positive control running the real checker on the unmodified helper.
- `test_structural_checker_rejects_injected_file_read_call`: deterministic
  negative counterexample — in-memory source substitution (no worktree
  mutation), `ast.parse` proves the injected module is valid, the SAME real
  checker raises its named AssertionError ("calls open()"), and the OLD
  text-search predicate is shown inline to ACCEPT the same violating helper.
- `_candidate_source`, product scripts, harness, mutation declarations and the
  fixture are byte-identical to the reviewed tip (digests below).

## GitNexus (real tool run; limitations disclosed)

- Index built fresh at FROZEN_BASE (40,617 nodes / 71,494 edges).
- `impact` resolved `_candidate_source` and the structural sentinel (upstream
  impactedCount 0 with the tool's epistemic caveat recorded verbatim).
- The NEW checker does not resolve in that index because the index predates
  the edit — an explicit tool limitation, NOT a no-callers inference; direct
  grep establishes its callers (sentinel :2499, counterexample :2529 only).
- `detect-changes` (unstaged, BEFORE commit): 1 file, 3 symbols, 0 affected
  processes, risk low (two sentinels listed only for line-position shift).
- Tool note: `--repo` accepts only the short project name (`Mpango-ERP`);
  path-qualified and directory-name forms were rejected (recorded).

## Frozen acceptance (single complete run, PYTHONUTF8=0, cp936; executed 2026-09-18)

16 passed / 36 deselected / rc=0 — the 15 R1-R5 node IDs retained plus the new
counterexample node. Node IDs and outcomes are in
`pytest_focused_acceptance.txt` (exact selected count 52 collected / 16
selected). `old_check_vs_repaired_checker.txt`: old text-search ACCEPTS the
violating helper (false green), repaired checker REJECTS it; on the unmodified
helper both accept. Neither outcome comes from a syntax/import error.

## NOT_RUN (unchanged; nothing inherited)

No PG scenarios, no Docker, no Alembic, no 104-node regression, none of the
nine runtime mutations. R1-R2/R1-R3/R1-R4/R1-R5 journals, evidence, fixture
and failure records preserved (zero drift verified). The R1-R5 acceptance is
NOT re-run or re-issued; this is one local correction.

## Pre-submission self-check

- Scope: implementation commit touches ONLY
  `backend/tests/test_tenant_bootstrap_db_authority.py`; the rest is new
  journal/evidence.
- Zero drift: R1-R2 evidence vs 27dd16b8, R1-R3 vs 69e2d5b6, R1-R4 vs
  909d3e31, R1-R5 evidence vs 4057808d — all empty diffs.
- Product/harness zero drift: grants `b2ee0eb4…`wt/`25330f40…`blob, bootstrap
  `fc0db066…`wt/`3301a55b…`blob, harness blob `b3580402…` — identical to the
  reviewed tip.
- Checker negative sensitivity: proven by the committed negative test AND
  `old_check_vs_repaired_checker.txt` (old accepts / new rejects on the same
  valid-Python violating helper).
- Node/outcome completeness: exact node IDs + selected count in
  `pytest_focused_acceptance.txt`.
- Tested-byte/blob EOL relationship: suite file wt CRLF, LF-normalized
  identical to the committed blob (digests in the manifest block); the helper
  under test reads the committed blob via `git show`.
- `git diff --check`: clean. detect-secrets pre-commit hook green on every
  commit (real hook execution; baseline file untouched/read-only).
- Commits: normal successor commits with normal hooks; no --no-verify, no
  amend, no rebase, no force-push, no merge, no deployment.

## Successor manifest

- SUCCESSOR_COMMIT=f440bfc856e021684e0772cb01cf579e938aae1e (`fix(tests): MPANGO-TENANT-BOOTSTRAP-R1-R5-R1-AST-SENTINEL-CLOSURE …`, normal hooks, no --no-verify, no amend/rebase/force)
- EVIDENCE_COMMIT=1e4228f75884620f77047ede8ecf0523179d162d (targeted evidence pack; every prior journal/evidence byte preserved)
- SUCCESSOR_DIGESTS (working-tree CRLF vs committed-blob LF, grouped):
  - v3_suite wt=c0d8db53 979901c1 e9ed1e43 8307028a aa86e3fc 8bf38d50 bf914819 d4c1ecc7
  - v3_suite blob=bd86ad91 93309d6d 389dc0e6 bced5d43 c644c285 f4f259b8 68642761 124fea7e
- UNCHANGED-DIGESTS (zero product/harness/fixture drift vs FROZEN_BASE, EOL-normalized verified):
  - grants wt=b2ee0eb4 320691c0 8256daf0 468dd521 361c834c f6e4abd0 b6f56d72 23630764 / blob=25330f40 794f08a2 4213c82f d9fbd3a4 eafa4719 7ed866a4 5761613d 193f4861
  - bootstrap wt=fc0db066 66b44f69 c96463cb 0fea076a 69f90f88 dc4c1885 c1d2abd3 524a4818 / blob=3301a55b a995359c 23da826c 566d821d 17307471 5fbb5c8c d3278e12 74aeff6d
  - harness blob=b3580402 a19b9e9e 190e686d 0e1b69dc 062008a5 d161e3c8 5a8de9d7 9d351fce
  - utf8_fixture blob=748639f2 1dfa527e 15a4e726 2eba6f6b ce93005c aab12768 b1ef2598 864630d4
- KEY_EVIDENCE_DIGESTS (blob form): pytest_focused_acceptance.txt=35b0ff20 674bf918 644e3b38 09576388 2a8ad50d 7658201e 18cff825 8e138458; old_check_vs_repaired_checker.txt=970d83e3 f000b8d4 f34df040 26b0c5a8 1e86d58b 92d991a6 c25e94da 8859d875
- FROZEN_ACCEPTANCE=1 complete run, PYTHONUTF8=0 (cp936), 52 collected / 16 selected / 16 PASSED / rc=0 (15 R1-R5 node IDs retained + test_structural_checker_rejects_injected_file_read_call)
- OLD_VS_NEW_CONTRAST=old text-search predicate ACCEPTS the injected violating helper (false green, CTO F1); repaired AST checker REJECTS it (named AssertionError "calls open()"); positive control ACCEPTS the unmodified helper; neither outcome from syntax/import errors
- NOT_EXECUTED=PG scenarios, Docker, Alembic, 104-node regression, the nine runtime mutations — all prior evidence preserved, nothing inherited as this round's PASS
- RESULT=R1_R5_R1_CANDIDATE_READY_FOR_CTO_REVIEW
