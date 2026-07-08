# Phase P1-F: Agent Task Execution Bridge

**Date:** 2026-05-26
**Branch:** `codex/platform-p1f-agent-task-execution-bridge-2026-05-26`
**Base commit:** `9f4c274306b53c0cd0258eb6845d78cc325b5e3a` (P1-E)
**Stack:** Stacked on P1-D and P1-E. Do not merge before those branches unless CTO approves a stack merge.
**Agent:** Opencode implementation attempt, completed and verified by Codex Platform CTO
**Status:** COMPLETE for implementation draft; not merged to `platform-dev`

## Scope

P1-F adds a platform-only bridge that lets CTO provide one run packet for longer opencode/goose work. The bridge validates the P1-E packet, emits a P1-C directive, then invokes `platform_directive_gate.py` so post-command changed-file allowlist enforcement remains active.

## Files Changed

| File | Operation |
|------|-----------|
| `scripts/platform_task_execution_bridge.py` | new |
| `scripts/test_platform_task_execution_bridge.py` | new |
| `ai-ledger/platform/2026-05-26_p1f_agent_task_execution_bridge.md` | new |

No backend/frontend/runtime/product files were modified.

## Implementation

`scripts/platform_task_execution_bridge.py` is a standard-library-only CLI:

```bash
python scripts/platform_task_execution_bridge.py \
  --packet PATH \
  --repo PATH \
  [--dry-run] \
  [--keep-directive PATH] \
  [--allow-unknown-agent] \
  [--skip-agent-tool-check]
```

Behavior:

- Runs `platform_run_packet_gate.py --emit-directive` against the packet.
- Runs `--agent-tool-check` by default.
- Passes `--allow-unknown-agent` through when requested.
- Emits the directive into a temporary directory outside the repo.
- Runs `platform_directive_gate.py` with the emitted directive.
- Adds `--dry-run` to the directive gate when requested, so the packet command is not executed.
- Supports `--keep-directive PATH` with safe relative path validation. This is intended for dry-run or explicit review workflows because it creates a repo file before directive execution.
- Preserves failure boundaries: packet gate failure skips directive gate; directive gate failure fails the bridge.

## Test Evidence

Initial opencode run timed out after creating the core bridge/test files but before ledger and full self-verification. Codex Platform CTO stopped the stale opencode process, fixed the test fixture to keep the repo clean before postflight, and completed verification.

```
python scripts/test_platform_task_execution_bridge.py
.............
----------------------------------------------------------------------
Ran 13 tests in 15.494s

OK
```

Full regression evidence:

```
python scripts/test_platform_run_packet_gate.py
..............................................
----------------------------------------------------------------------
Ran 46 tests in 25.818s

OK

python scripts/test_platform_toolchain_gate.py
.............
----------------------------------------------------------------------
Ran 13 tests in 1.392s

OK

python scripts/test_platform_directive_gate.py
.......................
----------------------------------------------------------------------
Ran 23 tests in 17.074s

OK

python scripts/test_platform_runner_gate.py
......
----------------------------------------------------------------------
Ran 6 tests in 5.761s

OK

python scripts/test_platform_agent_preflight.py
....................................
----------------------------------------------------------------------
Ran 36 tests in 6.197s

OK
```

Diff and graph evidence:

```
git diff --check
PASS

npx gitnexus analyze
Repository indexed successfully
4,570 nodes | 13,255 edges | 313 clusters | 239 flows

GitNexus detect_changes(scope=staged)
risk_level: medium
changed_files: 3
affected_processes: Main -> Normalize_path (new bridge internal flow)
```

## Counterexamples Covered

| Counterexample | Expected behavior | Coverage |
|----------------|-------------------|----------|
| Dry-run packet command would create a file | Bridge exits 0 and no file is created | `test_dry_run_validates_both_gates_no_file_created` |
| Command creates only an expected file | Bridge exits 0 | `test_successful_execution_creates_expected_file` |
| Command creates an extra file | Directive postflight fails bridge | `test_unexpected_file_fails_via_directive_postflight` |
| Packet is invalid JSON or missing required fields | Packet gate fails and directive gate is skipped | invalid packet tests |
| Tests should not depend on real opencode | `--skip-agent-tool-check` allows hermetic tests | skip-agent-tool-check test |
| Keep directive path is safe | Directive is written in dry-run | keep-directive safe path test |
| Keep directive path is absolute/traversal/forbidden | Bridge fails before packet gate | keep-directive failure tests |
| Unknown agent is unapproved | Fails by default | unknown agent default test |
| Unknown agent explicitly allowed for hermetic testing | Passes with `--allow-unknown-agent --skip-agent-tool-check` | unknown agent allow test |

## Forbidden Path Audit

Allowed files are limited to `scripts/` platform harness files and `ai-ledger/platform/`. The only occurrences of forbidden path strings are policy constants and negative tests. No files under these scopes were modified:

- `backend/`
- `frontend/`
- `.github/workflows/`
- `.claude/`
- `docs/ai/PHASE4_FRONTEND_CONTRACT.md`
- product branch/runtime paths
- auth/RBAC/tenancy/session/migration/payment paths

## Risk Classification

**Risk:** MEDIUM

The change is platform harness only and additive, but it introduces an execution bridge that orchestrates existing gates. The risk is contained by the directive postflight contract and regression tests.

## Report Fields

- **Branch:** `codex/platform-p1f-agent-task-execution-bridge-2026-05-26`
- **Commit:** `09e2095` before ledger hash update; final amended commit recorded in CTO report
- **Modified files:** `scripts/platform_task_execution_bridge.py`, `scripts/test_platform_task_execution_bridge.py`, `ai-ledger/platform/2026-05-26_p1f_agent_task_execution_bridge.md`
- **Tests:** listed above
- **Report path:** `ai-ledger/platform/2026-05-26_p1f_agent_task_execution_bridge.md`
- **Risk:** MEDIUM
