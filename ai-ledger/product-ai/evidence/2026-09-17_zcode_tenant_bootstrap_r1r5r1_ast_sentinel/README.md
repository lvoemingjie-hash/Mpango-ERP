# MPANGO R1-R5-R1 — AST Sentinel Closure (one test-assertion repair)

- **Authorization:** CTO-AUTH-TENANT-BOOTSTRAP-R1-R5-R1-AST-SENTINEL-CLOSURE-2026-09-17
- **Executor:** KIMI (authorization EXECUTOR field); executed in a ZCode agent
  session on Windows 10.0.26200.9457 x64 (executed 2026-09-18)
- **FROZEN_BASE (reviewed R1-R5 tip):** `4057808df5b0811e3c16cc682d5c1a8337bf64b8`
  (remote `zcode/tenant-bootstrap-r1r5-utf8-source-reader-2026-09-17` verified
  equal before branching; original R1-R5 BASE
  `909d3e31b720fdc4f2008b90bb3e7bad2f76ac57` remains in ancestry)
- **Branch:** `zcode/tenant-bootstrap-r1r5-r1-ast-sentinel-closure-2026-09-17`
  (isolated worktree `worktrees/zcode_tenant_bootstrap_r1r5r1_ast_2026-09-17`)
- **Candidate:** `f440bfc856e021684e0772cb01cf579e938aae1e`
- **Verification tier:** V3_TARGETED_VERIFICATION_TOOL_CLOSURE
- **Claim ceiling:** ONE_TEST_ASSERTION_REPAIR_AND_TARGETED_EVIDENCE_ONLY

## F1 closure (the single structural blind spot)

The CTO found (and this round independently reproduced before fixing) that the
R1-R5 structural sentinel searched for the literal text `open(` inside
`ast.dump(...)` output, which renders a call as `Call(func=Name(id='open', …)`
— so the assertion never matched a real `open()` call and accepted a helper
containing one. Verified here on BASE bytes: the injected violating helper
carries a real `Name(id='open'` call node while `ast.dump` contains no `open(`
text, and the old predicate PASSED it (false green).

Repair — `_candidate_source` itself, product scripts, harness, mutation
declarations and the fixture are untouched:

- `_assert_helper_reads_only_committed_candidate()`: real AST-node inspection
  of the helper body — flags calls to `open()` **and** `builtins.open()`,
  bare/broad except handlers (`except:`, `Exception`, `BaseException`, alone
  or inside an except-tuple), and requires a strict `.decode("utf-8")` call.
  Documented as BOUNDED structural inspection (two explicit known APIs), not a
  general data-flow proof; indirect reads via other functions remain covered
  by the behavioral tests (working-tree open spy + refusal tests). Strict
  UTF-8 and refusal assertions elsewhere are unchanged.
- `test_static_candidate_source_has_no_working_tree_fallback`: SAME node ID,
  now the positive control running the real checker on the unmodified helper.
- `test_structural_checker_rejects_injected_file_read_call`: deterministic
  negative counterexample — injects a syntactically valid
  `with open(rel_path…) / handle.read()` into the helper source IN MEMORY
  (`ast.parse` proves validity; no worktree mutation), invokes the SAME real
  checker, requires its named AssertionError ("calls open()"), and proves
  inline that the OLD text-search predicate accepts the very same violating
  helper. No parallel checker; the checker under test is the production one.

## GitNexus (real tool run; limitations disclosed)

Repo indexed fresh at BASE (`gitnexus analyze`, 40,617 nodes). Impact resolved
both existing symbols — `_candidate_source` and
`test_static_candidate_source_has_no_working_tree_fallback` (upstream
impactedCount 0 with the tool's own epistemic caveat recorded verbatim in
`impact_analysis.txt`). The NEW checker `_assert_helper_reads_only_committed_candidate`
is **unresolvable in that index because the index predates this edit** — an
explicit tool limitation, not a no-callers inference; its callers are
established by direct grep (the sentinel at :2499 and the counterexample at
:2529 only). `gitnexus detect-changes` (unstaged, before commit): 1 file,
3 symbols, 0 affected processes, risk low. Note: the `--repo` disambiguator
only accepts the short project name (`Mpango-ERP`); path-qualified forms were
rejected — recorded for the reviewer.

## Frozen acceptance (single complete run, `PYTHONUTF8=0`, cp936)

**16 passed, 36 deselected (rc=0)** — the 15 R1-R5 node IDs retained plus the
new counterexample. Per-node list in `pytest_focused_acceptance.txt`; summary:

- exact RED-set validator: 5/5 PASS;
- validator self-check + formal-gate statics: 2/2 PASS;
- declaration integrity + mutation parseability: 2/2 PASS;
- R1-R5 helper tests: 6/6 PASS (unchanged);
- repaired structural sentinel (positive control): PASS;
- NEW `test_structural_checker_rejects_injected_file_read_call`: PASS.

`old_check_vs_repaired_checker.txt`: on the same syntactically-valid violating
helper, the R1-R5 text-search predicate ACCEPTS (false green) while the
repaired checker REJECTS ("calls open() at line …"); on the unmodified helper
both accept. Neither outcome comes from a syntax/import error.

## NOT_RUN (unchanged from R1-R5; nothing inherited)

No PG scenarios, no Docker, no Alembic, no 104-node regression, none of the
nine runtime mutations. R1-R4/R1-R5 evidence and journals preserved as-is
(zero drift verified). The R1-R5 acceptance is NOT re-run or re-issued here;
this round is one local correction.

## Pre-submission self-check

Scope: `git diff 4057808d..HEAD` (implementation commit) touches ONLY
`backend/tests/test_tenant_bootstrap_db_authority.py`; everything else under
`ai-ledger/` is new journal/evidence. Product scripts (grants
`b2ee0eb4…`/`25330f40…`, bootstrap `fc0db066…`/`3301a55b…`) and the harness
blob `b3580402…` are byte-identical to BASE; R1-R2/R1-R3/R1-R4/R1-R5 evidence
directories show zero drift vs their manifest tips. `git diff --check` clean.
detect-secrets pre-commit hook green on every commit (hook execution is the
real gate; the baseline file was not modified). Tested-byte/blob EOL
relationship: the suite working-tree file is CRLF and LF-normalized identical
to the committed blob (values in the journal manifest block); the checker
under test reads the committed blob via `git show` in the behavioral tests.

## Reproduce

```
cd backend
PYTHONUTF8=0 <venv-python> -m pytest tests/test_tenant_bootstrap_db_authority.py \
    -k "candidate_source or mutation_validator or formal_gate or parseable or parse_gate or static_formal_gate or structural_checker" -rA
```
