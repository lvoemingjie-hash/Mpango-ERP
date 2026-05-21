# Phase P1-B: Runner Preflight Wiring

**Date:** 2026-05-21
**Branch:** `codex/platform-p1b-runner-preflight-wiring-2026-05-21` based on `origin/platform-dev`
**Base commit:** `7b0229622791ba2f6a16ca352f1e8df8e94be612`
**Agent:** Opencode execution, reviewed by Codex Platform CTO
**Status:** COMPLETE for implementation draft; new files only, not merged to `platform-dev`

## Scope

Add a local platform runner gate that future platform agents / Lubuntu runner commands can invoke before executing a task. It runs the existing platform preflight first and only then runs the requested command.

Deliverables:

1. `scripts/platform_runner_gate.py` - runner gate CLI
2. `scripts/test_platform_runner_gate.py` - unit tests
3. `ai-ledger/platform/2026-05-21_p1b_runner_preflight_wiring.md` - this ledger

## Files Changed

| File | Operation |
|------|-----------|
| `scripts/platform_runner_gate.py` | new |
| `scripts/test_platform_runner_gate.py` | new |
| `ai-ledger/platform/2026-05-21_p1b_runner_preflight_wiring.md` | new |

No existing files or indexed symbols were modified.

## Impact Note

All changes are new files only. No existing symbols were modified:

- `scripts/platform_runner_gate.py` invokes the existing `platform_agent_preflight.py` as a subprocess. It does not import or modify the preflight module.
- `scripts/test_platform_runner_gate.py` tests the runner gate via subprocess only, with no direct import of any existing module.
- The ledger file is additive documentation.

## Implementation

### `scripts/platform_runner_gate.py`

Python 3 script using only standard library modules: `argparse`, `os`, `subprocess`, `sys`, `pathlib`.

CLI interface:

```bash
python scripts/platform_runner_gate.py \
  --repo PATH \
  --report PATH \
  [--allow-platform-dev] \
  [-- <command>...]
```

**Required flags:**

- `--repo PATH` - path to the git repository root (required)
- `--report PATH` - path to the report file (runner-grade, mandatory)

**Optional flags:**

- `--allow-platform-dev` - passes through to `platform_agent_preflight.py` to allow the `platform-dev` branch
- `<command>...` after `--` - executed only if preflight succeeds

**Report fields validated (delegated to preflight):**

- branch
- commit
- modified files
- tests
- report path
- risk

**Behavior:**

1. Resolves the preflight script path relative to its own location
2. Resolves the report path relative to the repo if not absolute
3. Runs the preflight as a subprocess with `--require-report`
4. If preflight fails: exits nonzero, command is blocked
5. If preflight passes and a command was supplied: runs the command from the repo root and exits with its exit code
6. If preflight passes and no command was supplied: exits 0 (gate-only mode)

**Output sections:**
- `PREFLIGHT CHECK` - shows the preflight command being run
- `RUNNER VERDICT` - shows preflight pass/fail and whether command will run
- `RUNNER COMMAND EXECUTION` - runs the command only if preflight passed

### `scripts/test_platform_runner_gate.py`

Unit tests use only `unittest`, `tempfile`, and other standard-library modules. Tests invoke the runner gate as a subprocess.

Test coverage includes:

- Gate-only success on `codex/platform-*` branch with valid report
- Command executes after preflight passes
- Command runs from the `--repo` root, regardless of the caller shell's current directory
- Command is blocked when preflight fails (`platform-dev` without `--allow-platform-dev`)
- `platform-dev` passes only with `--allow-platform-dev`
- Missing report fails before command execution

## Test Evidence

```text
python scripts/test_platform_runner_gate.py
......
----------------------------------------------------------------------
Ran 6 tests in 5.377s
OK
```

Real-repo self-check (with command):

```text
python scripts/platform_runner_gate.py --repo . --report ai-ledger/platform/2026-05-21_p1b_runner_preflight_wiring.md -- python -c "print('runner-ok')"
VERDICT: PASS - All preflight checks passed
  Branch:  codex/platform-p1b-runner-preflight-wiring-2026-05-21
  Commit:  7b0229622791ba2f6a16ca352f1e8df8e94be612
runner-ok
PREFLIGHT: PASS
COMMAND: PASS (exit 0)
```

Real-repo self-check (gate-only mode):

```text
python scripts/platform_runner_gate.py --repo . --report ai-ledger/platform/2026-05-21_p1b_runner_preflight_wiring.md
VERDICT: PASS - All preflight checks passed
PREFLIGHT: PASS
COMMAND: (none - gate-only mode)
Verdict: PASS - gate-only mode, no command to execute
```

Existing preflight tests still pass:

```text
python scripts/test_platform_agent_preflight.py
Ran 36 tests in 5.915s
OK
```

Diff/check evidence before CTO staging:

```text
git status --short
?? ai-ledger/platform/2026-05-21_p1b_runner_preflight_wiring.md
?? scripts/platform_runner_gate.py
?? scripts/test_platform_runner_gate.py

git diff --check
PASS after CTO staging

GitNexus detect_changes(scope=staged)
changed_files: 3
changed_count: 0
affected_count: 0
risk_level: low
affected_processes: none
```

## CTO Instruction Compliance Check

| CTO instruction | Implementation evidence | Test evidence | Status |
|----------------|-------------------------|---------------|--------|
| Name the phase | Ledger and gate use `Phase P1-B: Runner Preflight Wiring` | Phase name appears in this ledger | PASS |
| Use opencode to begin execution | Opencode created the implementation | Opencode report captures files and checks | PASS |
| Create `scripts/platform_runner_gate.py` | File created | self-check runs the script successfully | PASS |
| Create `scripts/test_platform_runner_gate.py` | File created | unittest tests pass | PASS |
| Create a platform ledger | This file created under `ai-ledger/platform/` | report validation checks required fields | PASS |
| Require `--repo PATH` | `--repo` is `required=True` | gate-only test uses `--repo tmpdir` | PASS |
| Require `--report PATH` (runner-grade, mandatory) | `--report` is `required=True` | missing report test fails | PASS |
| `--allow-platform-dev` passes through | Flag appended to preflight subprocess cmd | `--allow-platform-dev` test passes | PASS |
| Optional command after `--` executes only on preflight success | `subprocess.run(args.command, cwd=repo_path)` gated on `result.returncode == 0` | command-executes test passes; command-blocked test passes | PASS |
| Runner command executes from repo root | Command subprocess uses `cwd=repo_path` | repo-root cwd test passes | PASS |
| Gate-only mode exits 0 after preflight success | No command branch reached after preflight pass | gate-only test exits 0 | PASS |
| Preflight failure exits nonzero, blocks command | `sys.exit(result.returncode)` before command execution | command-blocked test exits nonzero | PASS |
| Resolve paths cross-platform | `Path(__file__).resolve()` for script; `os.path.normpath(os.path.join())` for report | relative paths resolved in tests | PASS |
| Print clear sections | `print_section()` with `PREFLIGHT CHECK`, `RUNNER VERDICT`, `RUNNER COMMAND EXECUTION` | sections appear in test stdout | PASS |
| Use standard library only | Script and tests import only standard-library modules | tests run without external dependencies | PASS |
| Do not modify existing symbols | Only new files added; preflight invoked as subprocess | `git diff --name-status` shows only added files | PASS |
| Do not touch runtime/product paths | New files under `scripts/` and `ai-ledger/platform/` only | forbidden path audit passes | PASS |
| Do not commit or push during opencode execution | Opencode stops before commit | Branch is pushed only, not merged to `platform-dev` | PASS |

## Counterexample Check

| Counterexample | Expected behavior | Test coverage |
|----------------|-------------------|---------------|
| Agent on `platform-dev` without `--allow-platform-dev` | Preflight fails, command blocked | `test_command_blocked_when_preflight_fails` |
| Agent on `platform-dev` with `--allow-platform-dev` | Preflight passes, command runs | `test_platform_dev_passes_with_allow_flag` |
| Gate invoked without `--report` | CLI parser rejects before any execution | `argparse` `required=True`; `test_missing_report_fails` |
| Gate invoked with nonexistent report | Preflight fails, command blocked | `test_missing_report_fails` |
| Gate in gate-only mode | Preflight passes, exits 0 without command | `test_gate_only_success_on_codex_branch` |
| Gate with valid command | Preflight passes, command output visible | `test_command_executes_after_preflight_passes` |
| Caller shell starts outside repo | Command still runs from `--repo` root | `test_command_runs_from_repo_root` |

## Risk Classification

**Risk:** LOW

All changes are new files only. No existing code, symbols, or execution flows are modified. The runner gate wraps the existing preflight as a subprocess. It does not import, monkey-patch, or alter any existing module. GitNexus staged detect_changes reports LOW risk and no affected processes.

## Completion Claim

**COMPLETE for Phase P1-B implementation draft.** The runner gate, unit tests, and ledger are present and validated locally. No existing symbols were modified. No product/runtime paths were touched. The branch is not merged to `platform-dev`.
