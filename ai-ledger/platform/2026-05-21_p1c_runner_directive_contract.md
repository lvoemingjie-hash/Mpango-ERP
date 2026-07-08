# Phase P1-C: Runner Directive Contract

**Date:** 2026-05-21
**Branch:** `codex/platform-p1c-runner-directive-contract-2026-05-21` based on `origin/platform-dev`
**Base commit:** `99ec2ee2f130cff6e74622982016a27797b8ee0e`
**Agent:** Opencode execution for P1-C/R1; Codex Platform CTO direct fix for P1-C.2 after local opencode PATH became unavailable
**Status:** COMPLETE for implementation draft plus P1-C.2 postflight hardening; not merged to `platform-dev`

## Scope

Add a directive contract layer so a runner can receive a JSON directive, validate it, and invoke `platform_runner_gate` in a predictable way. This addresses report-delivery discipline without touching product code or GitHub workflows.

## P1-C.2 Postflight Contract

CTO paused P1-C before merge because `expected_files` only performed path safety validation and did not bind the command's actual post-command git diff. That left a gap where an agent could pass directive preflight and then create files outside the declared scope.

P1-C.2 upgrades `expected_files` into a real post-command changed-files allowlist:

- Collects staged, unstaged, and untracked git changed files after command execution.
- Normalizes all paths to `/` before comparison.
- If `expected_files` is non-empty, every actual changed file must appear in the allowlist.
- If `expected_files` is empty, actual changed files must be empty.
- If command exits 0 but unexpected files are present, directive gate exits 1.
- If command exits nonzero, directive gate still prints changed-file diagnostics and exits nonzero.
- Dry-run does not execute the command or post-command gate, but prints the expected_files allowlist.

Deliverables:

1. `scripts/platform_directive_gate.py` - directive gate CLI
2. `scripts/test_platform_directive_gate.py` - unit tests
3. `ai-ledger/platform/2026-05-21_p1c_runner_directive_contract.md` - this ledger

## Files Changed

| File | Operation |
|------|-----------|
| `scripts/platform_directive_gate.py` | new |
| `scripts/test_platform_directive_gate.py` | new |
| `ai-ledger/platform/2026-05-21_p1c_runner_directive_contract.md` | new |

No existing files or indexed symbols were modified.

## Impact Note

All changes are new files only. No existing symbols were modified:

- `scripts/platform_directive_gate.py` validates a JSON directive and invokes the existing `platform_runner_gate.py` as a subprocess. It does not import or modify any existing module.
- `scripts/test_platform_directive_gate.py` tests the directive gate via subprocess only, with no direct import of any existing module.
- The ledger file is additive documentation.

## Implementation

### `scripts/platform_directive_gate.py`

Python 3 script using only standard library modules: `argparse`, `json`, `os`, `subprocess`, `sys`, `pathlib`.

CLI interface:

```bash
python scripts/platform_directive_gate.py \
  --repo PATH \
  --directive PATH \
  [--dry-run]
```

**Required flags:**

- `--repo PATH` - path to the git repository root (required)
- `--directive PATH` - path to the JSON directive file (required)

**Optional flags:**

- `--dry-run` - print the runner command and exit 0 without executing

**Directive JSON format:**

Required top-level fields:

| Field | Type | Validation |
|-------|------|------------|
| `phase` | string | non-empty |
| `branch` | string | non-empty; must match current git branch |
| `report` | string | non-empty; must be under `ai-ledger/platform/` and end in `.md` |
| `risk` | string | one of `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `command` | list of strings | may be empty only when `gate_only` is true |
| `gate_only` | boolean | - |

Optional fields:

| Field | Type | Validation |
|-------|------|------------|
| `allow_platform_dev` | boolean | default false; only valid when branch is `platform-dev` |
| `expected_files` | list of strings | every path must be safe, avoid forbidden runtime/product paths, and match actual post-command changed files |

**Forbidden path policy** (same as platform agent preflight):

- Prefixes: `backend/`, `frontend/`, `.github/workflows/`, `.claude/`
- Specific: `docs/ai/PHASE4_FRONTEND_CONTRACT.md`
- Fragments: `auth`, `rbac`, `tenancy`, `session`, `migration`, `payment`

**Behavior:**

1. Loads and validates the JSON directive
2. Checks current git branch matches directive `branch`
3. Validates report path is under `ai-ledger/platform/` and ends in `.md`
4. Validates risk level, command/gate_only consistency, and expected_files
5. Builds runner invocation: `python scripts/platform_runner_gate.py --repo REPO --report REPORT [--allow-platform-dev] [-- command...]`
6. Prints the normalized expected_files allowlist
7. If `--dry-run`: prints the command and allowlist, then exits 0 without executing
8. Otherwise: executes the runner command
9. Collects staged, unstaged, and untracked changed files after command execution
10. Enforces the changed-files allowlist before returning the final status

**Output sections:**

- `DIRECTIVE VALIDATION` - shows validation pass/fail for the directive
- `RUNNER INVOCATION` - shows the runner command that would be executed
- `EXPECTED FILES ALLOWLIST` - shows the normalized expected_files allowlist
- `POST-COMMAND CHANGED FILES` - shows actual staged, unstaged, and untracked changed files after execution
- `VERDICT: PASS / FAIL / DRY-RUN PASS` - clear verdict at each stage

When not in dry-run mode, the runner gate's own sections and verdicts appear after the invocation line.

### `scripts/test_platform_directive_gate.py`

Unit tests use only `unittest`, `tempfile`, and other standard-library modules. Tests invoke the directive gate as a subprocess.

Test coverage includes:

- Valid dry-run on `codex/platform-*` prints runner command and exits 0
- UTF-8 BOM JSON directive passes, matching Windows PowerShell output behavior
- Valid execution invokes runner gate and runs a simple command
- Branch mismatch fails before runner command executes
- Missing required field fails
- Report outside `ai-ledger/platform/` fails
- Report path traversal with `..` fails
- Command elements must be non-empty strings
- Forbidden `expected_files` path fails
- P1-C.2 changed-files allowlist rejects empty allowlist with command-created files
- P1-C.2 changed-files allowlist accepts command-created files listed in `expected_files`
- P1-C.2 changed-files allowlist rejects extra unlisted command-created files
- P1-C.2 still rejects forbidden `expected_files` before command execution
- P1-C.2 prints changed-files diagnostics when the command exits nonzero
- P1-C.2 dry-run prints invocation and allowlist without executing the command
- `platform-dev` requires `allow_platform_dev` true and passes when true
- `allow_platform_dev` on non-`platform-dev` branches fails

## Test Evidence

```text
python scripts/test_platform_directive_gate.py
```

```
.................
----------------------------------------------------------------------
Ran 23 tests in 19.139s
OK
```

Real-repo self-check (dry-run):

```text
python scripts/platform_directive_gate.py --repo . --directive /tmp/.../directive.json --dry-run
VERDICT: PASS - directive is valid

============================================================
  RUNNER INVOCATION
============================================================
  python .../scripts/platform_runner_gate.py --repo ... --report ai-ledger/platform/2026-05-21_p1c_runner_directive_contract.md

============================================================
VERDICT: DRY-RUN PASS
```

Real-repo self-check (execution):

```text
python scripts/platform_directive_gate.py --repo . --directive <temp P1-C.2 directive>
VERDICT: PASS - directive is valid
VERDICT: PASS - All preflight checks passed
postflight-selfcheck-ok
COMMAND: PASS (exit 0)
POST-COMMAND CHANGED FILES
Actual changed files:
- ai-ledger/platform/2026-05-21_p1c_runner_directive_contract.md
- scripts/platform_directive_gate.py
- scripts/test_platform_directive_gate.py
PASS  changed files match expected_files contract
```

Existing tests still pass:

```text
python scripts/test_platform_runner_gate.py
......
----------------------------------------------------------------------
Ran 6 tests in 5.545s
OK

python scripts/test_platform_agent_preflight.py
....................................................................
----------------------------------------------------------------------
Ran 36 tests in 5.896s
OK
```

Diff/check evidence:

```text
git diff --name-status origin/platform-dev...HEAD
A       ai-ledger/platform/2026-05-21_p1c_runner_directive_contract.md
A       scripts/platform_directive_gate.py
A       scripts/test_platform_directive_gate.py

git diff --check HEAD~1..HEAD
(no output)

GitNexus detect_changes(scope=compare, base_ref=origin/platform-dev)
changed_files: 3
changed_count: 43
affected_count: 3
risk_level: medium
affected_processes:
- Main -> Normalize_path
- Main -> Get_current_branch
- Main -> Get
```

## CTO Instruction Compliance Check

| CTO instruction | Implementation evidence | Test evidence | Status |
|----------------|-------------------------|---------------|--------|
| Name the phase | Ledger and gate use `Phase P1-C: Runner Directive Contract` | Phase name appears in this ledger | PASS |
| Create `scripts/platform_directive_gate.py` | File created | self-check runs the script successfully | PASS |
| Create `scripts/test_platform_directive_gate.py` | File created | unittest tests pass | PASS |
| Create a platform ledger | This file created under `ai-ledger/platform/` | report validation checks required fields | PASS |
| Use standard library only | Script and tests import only standard-library modules | tests run without external dependencies | PASS |
| Directive format is JSON | Script uses `json.load()` | JSON decode error handled | PASS |
| Accept Windows UTF-8 BOM JSON | Directive file opened with `utf-8-sig` | UTF-8 BOM directive dry-run test passes | PASS |
| Validate required fields | `REQUIRED_FIELDS` list checked in `validate_directive()` | missing required field test fails | PASS |
| Branch must match current git branch | `get_current_branch()` compared against directive `branch` | branch mismatch test fails before runner | PASS |
| Report under `ai-ledger/platform/` ending in `.md` | `report.startswith("ai-ledger/platform/")` and `endswith(".md")` | report outside ledger test fails | PASS |
| Risk one of LOW/MEDIUM/HIGH/CRITICAL | `directive["risk"] not in VALID_RISK_LEVELS` check | validated in validation logic | PASS |
| Command may be empty only when gate_only is true | `command` and `gate_only` consistency check | validation tests pass | PASS |
| Command elements must be strings | command list rejects non-string or empty entries | command element test fails | PASS |
| Report path must be safe | absolute, unsafe, forbidden, off-ledger report paths are rejected | report outside ledger and path traversal tests fail | PASS |
| Forbidden path policy on expected_files | `is_forbidden_path()` called for each expected_file | forbidden expected_files test fails | PASS |
| **P1-C-R1:** expected_files must have report-equivalent path safety (reject absolute, Windows drive, .., ., empty parts) | Validate non-empty, relative, safe parts per element before forbidden check | `test_expected_file_dotdot_fails`, `test_expected_file_posix_absolute_fails`, `test_expected_file_windows_drive_fails`, `test_expected_file_traversal_docs_fails`, `test_legal_expected_files_scripts_pass` | PASS |
| **P1-C.2:** expected_files must act as actual post-command changed-files allowlist | `get_changed_files()` collects staged, unstaged, untracked files; `validate_changed_files_allowlist()` compares actual vs expected | `test_empty_expected_files_with_command_change_fails`, `test_expected_file_with_command_change_passes`, `test_extra_unlisted_command_change_fails` | PASS |
| **P1-C.2:** command exit 0 with unexpected changed files must fail final gate | post-command allowlist failure exits 1 after runner command succeeds | `test_empty_expected_files_with_command_change_fails`, `test_extra_unlisted_command_change_fails` | PASS |
| **P1-C.2:** command exit nonzero still prints changed-file diagnostics and remains failed | post-command diagnostics run after runner command regardless of command status | `test_nonzero_command_outputs_changed_files_and_fails` | PASS |
| **P1-C.2:** dry-run must not execute command or post-command gate, but must show allowlist | dry-run prints `EXPECTED FILES ALLOWLIST` before `DRY-RUN PASS` | `test_dry_run_prints_allowlist_without_executing` | PASS |
| `--allow-platform-dev` optional flag | Flag passed through only when branch is `platform-dev` | platform-dev tests pass; codex branch with allow flag fails | PASS |
| Dry-run prints command and exits 0 | `--dry-run` flag bypasses subprocess execution | dry-run test exits 0 with runner command | PASS |
| Execute runner command and exit with its status | `subprocess.run(runner_cmd)` then `sys.exit(result.returncode)` | valid execution test passes | PASS |
| Print clear sections | `print_section()` with `DIRECTIVE VALIDATION`, `RUNNER INVOCATION` | sections appear in test stdout | PASS |
| Do not modify existing symbols | Only new files added; runner gate invoked as subprocess | `git diff --name-status` shows only added files | PASS |
| Do not touch runtime/product paths | New files under `scripts/` and `ai-ledger/platform/` only | forbidden path audit passes | PASS |
| Do not commit or push during opencode execution | Opencode stops before commit | Branch is not merged to `platform-dev` | PASS |

## Counterexample Check

| Counterexample | Expected behavior | Test coverage |
|----------------|-------------------|---------------|
| Agent provides directive with wrong branch | Directive validation fails, runner gate never invoked | `test_branch_mismatch_fails_before_runner` |
| Agent provides directive missing a required field | Directive validation fails | `test_missing_required_field_fails` |
| Agent provides directive with report outside `ai-ledger/platform/` | Directive validation fails | `test_report_outside_ledger_fails` |
| Agent provides directive with report path traversal | Directive validation fails | `test_report_path_traversal_fails` |
| Agent provides directive with non-string command element | Directive validation fails | `test_command_elements_must_be_strings` |
| Agent provides directive with forbidden `expected_files` | Directive validation fails | `test_forbidden_expected_files_fails` |
| Agent on `platform-dev` without `allow_platform_dev` | Directive validation fails | `test_platform_dev_no_allow_fails` |
| Agent on `platform-dev` with `allow_platform_dev` true | Directive validation passes | `test_platform_dev_with_allow_passes_dry_run` |
| Agent on `codex/platform-*` with `allow_platform_dev` true | Directive validation fails | `test_allow_platform_dev_on_codex_branch_fails` |
| Agent invokes in dry-run mode | Runner command printed, no execution | `test_valid_dry_run_on_codex_branch` |
| Agent provides UTF-8 BOM JSON generated by Windows tooling | Directive validation still passes | `test_utf8_bom_directive_passes_dry_run` |
| Agent invokes in execution mode | Runner gate invoked, command runs | `test_valid_execution_invokes_runner_gate` |
| **P1-C-R1:** Agent provides `expected_files` with `..` traversal (`../scripts/platform.py`) | Directive validation fails with unsafe path part | `test_expected_file_dotdot_fails` |
| **P1-C-R1:** Agent provides `expected_files` with POSIX absolute path (`/tmp/foo.py`) | Directive validation fails with must be relative | `test_expected_file_posix_absolute_fails` |
| **P1-C-R1:** Agent provides `expected_files` with Windows drive path (`C:/tmp/foo.py`) | Directive validation fails with must be relative | `test_expected_file_windows_drive_fails` |
| **P1-C-R1:** Agent provides `expected_files` with hidden traversal (`docs/ai/../ai/PROJECT.md`) | Directive validation fails with unsafe path part | `test_expected_file_traversal_docs_fails` |
| **P1-C-R1:** Agent provides `expected_files` with legal `scripts/` and `ai-ledger/platform/` paths | Directive validation passes | `test_legal_expected_files_scripts_pass` |
| **P1-C.2:** Agent declares no expected_files but command creates a file | Directive gate fails after command and prints changed-file diagnostics | `test_empty_expected_files_with_command_change_fails` |
| **P1-C.2:** Agent declares one file and command creates exactly that file | Directive gate passes post-command allowlist | `test_expected_file_with_command_change_passes` |
| **P1-C.2:** Agent declares one file but command also creates an extra file | Directive gate fails after command and names the unexpected file | `test_extra_unlisted_command_change_fails` |
| **P1-C.2:** Agent lists a forbidden path in expected_files | Directive validation fails before command execution | `test_forbidden_expected_file_fails_before_command` |
| **P1-C.2:** Command exits nonzero after changing a declared file | Directive gate prints post-command changed files and exits nonzero | `test_nonzero_command_outputs_changed_files_and_fails` |
| **P1-C.2:** Dry-run directive command would create a file | Directive gate prints runner invocation and allowlist, and the file is not created | `test_dry_run_prints_allowlist_without_executing` |

## Risk Classification

**Risk:** MEDIUM

GitNexus compare reports MEDIUM because the standalone directive gate introduces and extends its own internal execution flows (`main -> validate_directive -> normalize_path/get_current_branch` plus post-command changed-file checks). The platform/product blast radius remains bounded: no backend/frontend/GitHub workflow paths are touched, and the directive gate delegates to the existing runner gate as a subprocess.

## Report Fields

- **Branch:** `codex/platform-p1c-runner-directive-contract-2026-05-21`
- **Commit:** final branch commit after CTO amend/push; see `git rev-parse HEAD`
- **Modified files:** `scripts/platform_directive_gate.py`, `scripts/test_platform_directive_gate.py`, `ai-ledger/platform/2026-05-21_p1c_runner_directive_contract.md`
- **Tests:** `test_platform_directive_gate.py`, `test_platform_runner_gate.py`, `test_platform_agent_preflight.py`
- **Report path:** `ai-ledger/platform/2026-05-21_p1c_runner_directive_contract.md`
- **Risk:** MEDIUM

## Completion Claim

**COMPLETE for Phase P1-C.2 implementation draft.** The directive gate now validates directive fields and enforces actual post-command changed-files scope. Unit tests and ledger are updated. No product/runtime paths were touched. The branch is not merged to `platform-dev`.
