# MPANGO R1-R5 — UTF-8 Committed-Candidate Source Reader (Targeted Verification Tool Closure)

- **Authorization:** CTO-AUTH-TENANT-BOOTSTRAP-R1-R5-UTF8-SOURCE-READER-2026-09-17
- **Executor:** Kimi (authorization EXECUTOR field); executed in a ZCode agent
  session on Windows 10.0.26200.9457 x64
- **BASE:** `909d3e31b720fdc4f2008b90bb3e7bad2f76ac57`
  (origin `zcode/tenant-bootstrap-db-authority-r1-r4-2026-09-16` tip; fetched
  and verified before branching — no drift)
- **Branch:** `zcode/tenant-bootstrap-r1r5-utf8-source-reader-2026-09-17`
  (independent worktree `worktrees/zcode_tenant_bootstrap_r1r5_utf8_2026-09-17`)
- **Candidate:** `9da7454fe78274afd83e46b758bdf96050715502`
- **Verification tier:** V3_TARGETED_VERIFICATION_TOOL_CLOSURE
- **Claim ceiling:** TEST_TOOL_REPAIR_AND_CANDIDATE_PREPARATION_ONLY

## The defect (CTO-confirmed, reproduced here)

`_candidate_source()` in `backend/tests/test_tenant_bootstrap_db_authority.py`
used `subprocess.run(text=True)` with no encoding.  On Windows the process
default codec is cp936/GBK (system codepage 936 on this machine), so `git
show`'s UTF-8 output containing non-ASCII bytes raised `UnicodeDecodeError`,
and the broad `except` then silently fell back to reading the **working tree**
— breaking the boundary that the checked source IS the committed candidate and
failing the static mutation-acceptance node.  A test-tool defect, not a
product behavior.

The R1-R3/R1-R4 source scripts already contain non-ASCII bytes (em dashes;
grants 36, harness 45, test file 66 non-ASCII bytes), so this defect is live
on any Windows-default-codec machine, not just on the fixture.

## The repair (test tooling only)

- `git show` output is captured as raw bytes and decoded **strictly as UTF-8**
  (no `text=`, no default codec).
- Every failure refuses explicitly with `RuntimeError`: subprocess spawn
  error, non-zero rc, empty output, invalid UTF-8.  No ignoring, no byte
  replacement, no `None`, and **no working-tree fallback** — a git
  candidate-read failure must not continue acceptance on anything but the
  committed candidate.
- A structural sentinel test proves the helper body has no `open()` and no
  broad `except`, and decodes strictly as UTF-8.

**No product logic changed, no authority framework rebuilt, no mutation
declarations touched.**

## Evidence in this pack

| File | Content |
| --- | --- |
| `environment.txt` | system codepage (936/GBK), Python 3.12.10, inherited vs test-run codec env; tests ran with `PYTHONUTF8=0` (true Windows default), the fix does NOT rely on `PYTHONUTF8=1` |
| `impact_analysis.txt` | GitNexus impact/context (real tool run, repo indexed fresh) + direct-call grep: exactly one caller, `test_static_every_mutation_is_parseable_and_fully_declared` |
| `pytest_focused_acceptance.txt` | FINAL frozen run, single invocation: **15/15 PASSED** under `PYTHONUTF8=0` — exact RED-set validator (5), validator self-check (1), formal-gate statics (1), mutation parseability (1), declaration integrity (1), R1-R5 helper tests (6) |
| `pytest_counterexample_red.txt` | bounded counterexample: old defect restored → **6/6 named assertions FAILED** with the exact CTO signature `UnicodeDecodeError: 'gbk' codec … illegal multibyte sequence` |
| `pytest_post_restore_green.txt` | post-restore: 6/6 GREEN |
| `counterexample_summary.txt` | the defect→fix diff, the applied patch, and the byte-identical restore proof (`sha256 == 685cf270…`) |
| `failed_attempts.txt` | transparent preparation-phase failures (pre-commit fixture-not-in-HEAD; two safe aborts of the counterexample harness; the `chcp` GBK capture issue) — none deleted |

## Node-by-node result of the focused group (frozen acceptance)

Exact RED-set validator: `test_mutation_validator_rejects_two_expected_one_hit`,
`..._rejects_extra_and_undeclared_reds`, `..._rejects_empty_declaration`,
`..._rejects_named_red_that_never_fired`, `..._accepts_exact_and_tolerated_sets`
— 5/5 PASS.

Validator self-check / formal gate:
`test_formal_gate_declares_its_own_negative_cases_and_they_fail_closed`,
`test_static_formal_gate_uses_the_exact_set_validator` — 2/2 PASS.

Declaration integrity + parseability:
`test_static_every_mutation_is_parseable_and_fully_declared`,
`test_mutation_apply_gate_refuses_unparseable_mutation` — 2/2 PASS.

R1-R5 helper tests: `test_candidate_source_reads_non_ascii_utf8_from_committed_candidate`,
`test_candidate_source_refuses_invalid_utf8`,
`test_candidate_source_refuses_git_failure`,
`test_candidate_source_refuses_empty_output`,
`test_candidate_source_refuses_subprocess_exception`,
`test_static_candidate_source_has_no_working_tree_fallback` — 6/6 PASS.

## NOT executed this round (by the authorization, explicitly)

No PostgreSQL scenarios, no second cluster, no `alembic upgrade head`, no
104-node BASE-vs-candidate regression, and none of the nine runtime mutations
(MM1–MM8, MM5a/MM5b) were re-run.  **The R1-R4 evidence pack is preserved
as-is and is explicitly marked as NOT re-run in this round; it is NOT
inherited as an independent R1-R5 PASS.**  This round closes one targeted
verification-tool defect only.

## Pre-commit self-check (see the journal for the full record)

Scope limited to the helper + its tests + one pure-test fixture; `git diff
--check` clean; detect-secrets pre-commit hook green; R1–R4 commits, evidence
and failure records untouched (verified empty diffs against their manifest
tips); product scripts (bootstrap/grants) byte-identical to BASE; the helper's
checked bytes are the committed blob (LF) — the EOL relationship is recorded
in the journal.  Commits made with normal hooks, no `--no-verify`.
