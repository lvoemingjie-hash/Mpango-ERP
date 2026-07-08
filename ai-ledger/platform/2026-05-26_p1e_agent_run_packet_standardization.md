# Phase P1-E: Agent Run Packet Standardization

**Date:** 2026-05-26
**Branch:** `codex/platform-p1e-agent-run-packet-standardization-2026-05-26`
**Base commit:** `c2efc87` (HEAD of P1-D)
**Stack:** Stacked on P1-D (`codex/platform-p1d-agent-toolchain-gate-2026-05-26`). Should not be merged before P1-D unless CTO approves stack merge.
**Agent:** Opencode execution, reviewed by Codex Platform CTO
**Status:** COMPLETE for implementation draft; new files only, not merged to `platform-dev`

## Scope

Create a standard-library-only CLI gate that validates a JSON run packet given by CTO to opencode/goose before long platform work. The gate validates packet structure, path safety, branch policies, and can emit a `platform_directive_gate`-compatible directive JSON.

Deliverables:

1. `scripts/platform_run_packet_gate.py` - run packet gate CLI
2. `scripts/test_platform_run_packet_gate.py` - unit tests
3. `ai-ledger/platform/2026-05-26_p1e_agent_run_packet_standardization.md` - this ledger

## Files Changed

| File | Operation |
|------|-----------|
| `scripts/platform_run_packet_gate.py` | new |
| `scripts/test_platform_run_packet_gate.py` | new |
| `ai-ledger/platform/2026-05-26_p1e_agent_run_packet_standardization.md` | new |

No existing files or indexed symbols were modified.

## Impact Note

All changes are new files only. No existing symbols were modified:

- `scripts/platform_run_packet_gate.py` is a standalone CLI. It imports only standard-library modules and invokes `platform_toolchain_gate.py` as a subprocess when `--agent-tool-check` is passed.
- `scripts/test_platform_run_packet_gate.py` tests the gate via subprocess only (no direct module import).
- The ledger file is additive documentation.

## Implementation

### `scripts/platform_run_packet_gate.py`

Python 3 script using only standard library modules: `argparse`, `json`, `os`, `subprocess`, `sys`, `pathlib.Path`.

CLI interface:

```bash
python scripts/platform_run_packet_gate.py \
  --packet PATH \
  [--repo PATH] \
  [--print-template] \
  [--emit-directive PATH] \
  [--agent-tool-check] \
  [--allow-unknown-agent]
```

**Options:**

| Flag | Description |
|------|-------------|
| `--packet PATH` | Path to JSON run packet (required unless `--print-template`) |
| `--repo PATH` | Git repository root (default: `.`) |
| `--print-template` | Print a valid JSON run packet template and exit 0 |
| `--emit-directive PATH` | Write normalized directive JSON after validation |
| `--agent-tool-check` | Run `platform_toolchain_gate.py` for the packet's agent |
| `--allow-unknown-agent` | Allow agents not in the known list (`opencode`, `goose`, `codex`) |

**Required packet fields:**

| Field | Type | Description |
|-------|------|-------------|
| `phase` | string | Phase identifier |
| `branch` | string | Target git branch |
| `agent` | string | Agent name (`opencode`, `goose`, `codex` or custom with `--allow-unknown-agent`) |
| `report` | string | Relative path under `ai-ledger/platform/` ending in `.md` |
| `risk` | string | One of `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `allowed_files` | list of strings | All files the agent is permitted to touch |
| `expected_files` | list of strings | Subset of `allowed_files` expected to change |
| `command` | list of strings | Command to execute |
| `tests` | list of strings | Test commands (non-empty list of non-empty strings) |
| `gate_only` | boolean | If true, no command is executed |

**Optional fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `allow_platform_dev` | boolean | `false` | Only valid when `branch` is `platform-dev` |
| `notes` | string or list | omitted | Free-form notes |

**Validation rules:**

1. Agent must be one of `opencode`, `goose`, `codex` unless `--allow-unknown-agent` is provided.
2. Report path validation (same policy as `platform_directive_gate`):
   - Must be relative and safe (no absolute paths, no traversal)
   - Must be under `ai-ledger/platform/`
   - Must end in `.md`
   - Must be forbidden-path-free (same `FORBIDDEN_PREFIXES`, `FORBIDDEN_SPECIFIC`, `FORBIDDEN_FRAGMENTS`)
3. `allowed_files` and `expected_files` validation:
   - Both must be lists of safe relative paths
   - Same forbidden-path policy as `platform_directive_gate`
   - `expected_files` must be a subset of `allowed_files`
   - Report path must be included in both `allowed_files` and `expected_files`
4. `tests` must be a non-empty list of non-empty strings
5. Branch policy:
   - If `branch` is `platform-dev`: `allow_platform_dev` must be `true`
   - If `branch` is not `platform-dev`: `allow_platform_dev` must not be `true`
6. Branch must match current git branch

**Emitted directive:**
When `--emit-directive` is provided, a JSON file is written with fields compatible with `platform_directive_gate`:
- `phase`, `branch`, `report`, `risk`, `command`, `gate_only`, `expected_files`, `allow_platform_dev`
- Notably excludes: `allowed_files`, `tests`, `agent`

**Output sections:**
- `RUN PACKET VALIDATION` - per-field validation results
- `NORMALIZED RUN PACKET` - full packet JSON
- `EMITTED DIRECTIVE` - directive JSON
- `TOOLCHAIN CHECK` - (when `--agent-tool-check`) agent tool availability results
- `RUN PACKET VERDICT` - PASS/FAIL

### `scripts/test_platform_run_packet_gate.py`

Unit tests use only `unittest`, `tempfile`, and other standard-library modules. Tests create fake executables (`.bat` on Windows, plain scripts on POSIX) in temporary directories on PATH for toolchain check tests. All tests invoke the gate via subprocess.

Test coverage includes:

- `--print-template` outputs valid JSON with all required fields and exits 0
- Valid packet passes with all sections present
- Valid packet with gate_only=true and empty command passes
- Valid packet with optional notes (string and list) passes
- `--emit-directive` writes correct subset without `allowed_files`, `tests`, `agent`
- `--emit-directive` normalizes Windows-style paths to `/`
- Emitted directive is accepted by `platform_directive_gate` `--dry-run` in a temp git repo
- `expected_files` not subset of `allowed_files` fails with clear message
- Report missing from `allowed_files` fails
- Report missing from `expected_files` fails
- Report in both lists passes
- Forbidden `allowed_files` (backend/ prefix, auth fragment) fails
- Forbidden `expected_files` (frontend/ prefix) fails
- Absolute `allowed_files` (/tmp/...) fails
- Windows drive `allowed_files` (C:/...) fails
- Traversal `allowed_files` (../) fails
- Absolute report fails
- `platform-dev` branch without `allow_platform_dev` fails
- `platform-dev` branch with `allow_platform_dev` passes
- `allow_platform_dev` on non-platform-dev fails
- Unknown agent fails by default with message referencing `--allow-unknown-agent`
- Unknown agent passes with `--allow-unknown-agent`
- All known agents (opencode, goose, codex) pass
- Empty tests list fails
- Tests with empty string fails
- Tests not a list fails
- Empty command with `gate_only: false` fails
- Notes must be string or list of strings
- Missing required fields fails
- Multiple validation errors collected before failing
- Report not ending in .md fails
- Report not under ai-ledger/platform fails
- Command not a list fails
- gate_only not boolean fails
- allowed_files not list fails
- Branch mismatch fails
- No packet and no template fails with usage message
- Invalid JSON file fails
- `--agent-tool-check` with fake agent on PATH passes and shows TOOLCHAIN CHECK section
- `--agent-tool-check` with missing tool fails

## Test Evidence

```
python scripts/test_platform_run_packet_gate.py
```

```
..............................................
----------------------------------------------------------------------
Ran 46 tests in 23.058s
OK
```

Existing tests still pass:

```
python scripts/test_platform_toolchain_gate.py
.............
----------------------------------------------------------------------
Ran 13 tests in 1.325s
OK

python scripts/test_platform_runner_gate.py
......
----------------------------------------------------------------------
Ran 6 tests in 5.092s
OK

python scripts/test_platform_directive_gate.py
.......................
----------------------------------------------------------------------
Ran 23 tests in 15.834s
OK

python scripts/test_platform_agent_preflight.py
....................................
----------------------------------------------------------------------
Ran 36 tests in 5.346s
OK
```

Template smoke test:

```
python scripts/platform_run_packet_gate.py --print-template
PASS - template JSON printed with required fields
```

Diff/check evidence:

```
git diff --check
PASS

forbidden path audit
PASS
```

## CTO Instruction Compliance Check

| CTO instruction | Implementation evidence | Test evidence | Status |
|----------------|-------------------------|---------------|--------|
| Name the phase | Ledger and gate use `Phase P1-E: Agent Run Packet Standardization` | Phase name appears in this ledger | PASS |
| Create `scripts/platform_run_packet_gate.py` | File created with CLI gate | CLI runs and validates packets | PASS |
| Create `scripts/test_platform_run_packet_gate.py` | File created with unittest tests | unittest tests pass | PASS |
| Create a platform ledger | This file created under `ai-ledger/platform/` | Report validation checks required fields | PASS |
| Standard library only | Script and tests import only standard-library modules | Tests run without external dependencies | PASS |
| `--packet PATH` required unless `--print-template` | `argparse` requires packet unless --print-template | `test_no_packet_no_template_fails` passes | PASS |
| `--repo PATH` default `.` | `argparse` default `.` | Tests pass with `--repo tmpdir` | PASS |
| `--print-template` prints JSON template and exits 0 | `get_template()` returns valid packet | `test_print_template_outputs_valid_json` | PASS |
| `--emit-directive PATH` writes normalized directive | `build_directive()` extracts directive subset | `test_emit_directive_writes_correct_subset` | PASS |
| Emitted directive uses normalized `/` paths | `normalize_packet()` normalizes report and expected_files before directive emit | `test_emit_directive_normalizes_paths` | PASS |
| `--agent-tool-check` runs `platform_toolchain_gate.py` | `run_toolchain_check()` subprocesses the gate | `test_agent_tool_check_with_fake_agent_on_path` | PASS |
| Required packet fields validated | `validate_packet()` checks all `REQUIRED_PACKET_FIELDS` | `test_missing_required_field_fails` | PASS |
| Valid agents: opencode, goose, codex | `VALID_AGENTS` list used in validation | `test_known_agents_all_pass` | PASS |
| `--allow-unknown-agent` bypasses agent check | `allow_unknown_agent` flag skips known-agent check | `test_unknown_agent_passes_with_flag` | PASS |
| Report path validation under ai-ledger/platform/.md | Same logic as `platform_directive_gate` | Multiple report path tests | PASS |
| allowed_files/expected_files path safety | Reuses `validate_contract_path` and `is_forbidden_path` | Multiple path safety tests | PASS |
| Forbidden runtime/product paths rejected | Same `FORBIDDEN_PREFIXES/FRAGMENTS` policy | `test_forbidden_allowed_file_prefix_fails` | PASS |
| expected_files subset of allowed_files | `expected_set - allowed_set` check | `test_expected_files_not_subset_fails` | PASS |
| Report in both allowed_files and expected_files | Explicit membership checks | `test_report_missing_from_allowed_files_fails` | PASS |
| Tests non-empty list of non-empty strings | `validate_string_list()` with `allow_empty=False` | `test_empty_tests_list_fails` | PASS |
| Empty command rejected unless gate_only is true | `validate_packet()` checks empty command with `gate_only` false | `test_empty_command_without_gate_only_fails` | PASS |
| Notes must be string or list of strings | `validate_packet()` validates optional notes type | `test_notes_must_be_string_or_list` | PASS |
| platform-dev requires allow_platform_dev true | Branch policy check in validation | `test_platform_dev_without_allow_fails` | PASS |
| non-platform-dev rejects allow_platform_dev true | Inverse branch policy check | `test_allow_platform_dev_on_non_platform_dev_fails` | PASS |
| Emit directive subset without allowed_files/tests | `DIRECTIVE_FIELDS` explicitly excludes extra fields | `test_emit_directive_writes_correct_subset` | PASS |
| Directive accepted by platform_directive_gate dry-run | Temp git repo dry-run test | `test_emitted_directive_passes_directive_gate_dry_run` | PASS |
| Print clear sections | `print_section()` for each section | Section names appear in stdout | PASS |
| Exit 1 on validation errors | `sys.exit(1)` after printing all issues | All failure tests assert nonzero exit | PASS |
| Collect all errors before failing | Validation accumulates into `issues` list | `test_all_errors_collected_before_failing` | PASS |
| Path normalization to / | `normalize_path()` replaces `\` with `/` | Consistent with existing gates | PASS |

## Counterexample Check

| Counterexample | Expected behavior | Test coverage |
|----------------|-------------------|---------------|
| CTO provides run packet with `allowed_files` containing `backend/` paths | Gate rejects with forbidden path error | `test_forbidden_allowed_file_prefix_fails` |
| CTO provides run packet with `expected_files` not in `allowed_files` | Gate rejects with subset error | `test_expected_files_not_subset_fails` |
| CTO provides run packet with an unknown agent without `--allow-unknown-agent` | Gate rejects with unknown agent error | `test_unknown_agent_fails_by_default` |
| CTO provides run packet on `platform-dev` without `allow_platform_dev: true` | Gate rejects with branch policy error | `test_platform_dev_without_allow_fails` |
| CTO provides run packet with `allow_platform_dev: true` on a codex branch | Gate rejects: only valid on platform-dev | `test_allow_platform_dev_on_non_platform_dev_fails` |
| CTO provides run packet with `tests: []` (empty list) | Gate rejects: tests must be non-empty | `test_empty_tests_list_fails` |
| CTO provides run packet with `command: []` but `gate_only: false` | Gate rejects: empty command requires gate_only true | `test_empty_command_without_gate_only_fails` |
| CTO provides run packet with Windows-style path separators | Gate emits directive with normalized `/` paths | `test_emit_directive_normalizes_paths` |
| CTO provides run packet with invalid notes object | Gate rejects: notes must be string or list | `test_notes_must_be_string_or_list` |
| CTO provides run packet with absolute `allowed_files` path | Gate rejects: must be relative | `test_absolute_allowed_file_fails` |
| CTO provides run packet with report outside `ai-ledger/platform/` | Gate rejects: not under ledger | `test_report_not_under_ledger_fails` |
| CTO provides run packet with report missing from `expected_files` | Gate rejects: report must be in expected_files | `test_report_missing_from_expected_files_fails` |
| CTO runs `--emit-directive` and feeds result to `platform_directive_gate` | Directive gate accepts in dry-run mode | `test_emitted_directive_passes_directive_gate_dry_run` |
| CTO runs `--agent-tool-check` and agent tool is not on PATH | Gate exits 1 with FAIL verdict | `test_agent_tool_check_missing_tool_fails` |
| Packet has multiple validation errors | All errors printed, gate still fails | `test_all_errors_collected_before_failing` |
| Branch mismatch between packet and current branch | Gate rejects with mismatch error | `test_branch_mismatch_fails` |

## Risk Classification

**Risk:** MEDIUM

All changes are new files only. No existing product/runtime code is modified. The run packet gate is a standalone CLI that only validates JSON and invokes `platform_toolchain_gate.py` via subprocess. It reuses the same forbidden-path policy as `platform_directive_gate`. Risk is MEDIUM because the gate introduces new validation logic for packet structure, path safety, and branch policy.

## Report Fields

- **Branch:** `codex/platform-p1e-agent-run-packet-standardization-2026-05-26`
- **Base commit:** `c2efc87` (top of P1-D)
- **Modified files:** `scripts/platform_run_packet_gate.py`, `scripts/test_platform_run_packet_gate.py`, `ai-ledger/platform/2026-05-26_p1e_agent_run_packet_standardization.md`
- **Tests:** `scripts/test_platform_run_packet_gate.py`
- **Report path:** `ai-ledger/platform/2026-05-26_p1e_agent_run_packet_standardization.md`
- **Risk:** MEDIUM

## Completion Claim

**COMPLETE for Phase P1-E implementation draft.** The run packet gate, unit tests, and ledger are present. No existing symbols were modified. No product/runtime paths were touched. This branch is stacked on P1-D and should not be merged before P1-D without CTO approval.
