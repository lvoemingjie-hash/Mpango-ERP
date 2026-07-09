# Phase P1-H: Agent Timeout Watchdog

**Date:** 2026-05-26
**Branch:** `codex/platform-p1h-agent-timeout-watchdog-2026-05-26`
**Base commit:** `d5c9c678d3b8bebe1d228f63305e29b4d5be79ef` (`origin/platform-dev`)
**Status:** COMPLETE for isolated task; not merged to `platform-dev`

## Scope

Add a platform-only watchdog for supervising long-running agent commands such as `opencode run` or `goose`. The watchdog applies an explicit timeout, preserves command exit code, returns `124` on timeout, captures stdout/stderr into a platform ledger report, and records changed files seen after command execution.

This responds to repeated `opencode run` behavior where the CLI did not return a completion event before the external shell timeout.

## Files Changed

| File | Operation |
|------|-----------|
| `scripts/platform_agent_timeout_watchdog.py` | new |
| `scripts/test_platform_agent_timeout_watchdog.py` | new |
| `ai-ledger/platform/2026-05-26_p1h_agent_timeout_watchdog.md` | new |

## Implementation

CLI:

```bash
python scripts/platform_agent_timeout_watchdog.py \
  --repo . \
  --report ai-ledger/platform/watchdog-report.md \
  --phase P1-H \
  --agent opencode \
  --timeout-seconds 600 \
  --risk MEDIUM \
  -- opencode run "task"
```

Behavior:

- Validates report path is safe, relative, under `ai-ledger/platform/`, and ends in `.md`.
- Rejects forbidden report paths using the same platform forbidden path policy.
- Runs the command in the target repo.
- Returns the command exit code on normal completion.
- Returns `124` on timeout.
- Writes a markdown report with branch, commit, command, timeout, elapsed time, outcome, exit code, modified files, tests, report path, risk, stdout, and stderr.

## Test Evidence

```
python scripts/test_platform_agent_timeout_watchdog.py
.........
----------------------------------------------------------------------
Ran 9 tests in 5.200s

OK

git diff --check
PASS
```

Coverage:

- Successful command exits zero and writes PASS report.
- Failing command preserves nonzero exit code.
- Timeout returns `124` and writes TIMEOUT report.
- Changed files are recorded in the report.
- Absolute, traversal, and outside-ledger report paths fail before command execution.
- Non-positive timeout fails.
- Missing command fails.

## Forbidden Path Audit

No product/runtime paths were touched. Changed files are limited to:

- `scripts/platform_agent_timeout_watchdog.py`
- `scripts/test_platform_agent_timeout_watchdog.py`
- `ai-ledger/platform/2026-05-26_p1h_agent_timeout_watchdog.md`

Forbidden path strings appear only as policy constants and negative-test inputs.

## GitNexus

```
npx gitnexus analyze
Repository indexed successfully
4,650 nodes | 13,506 edges | 318 clusters | 244 flows

GitNexus detect_changes(scope=staged)
changed_files: 3
risk_level: medium
affected_processes:
- Main -> Normalize_path (validate_report_path path-safety flow)
- Main -> Run_git (branch/commit collection flow)
```

Risk is MEDIUM because this task adds a new platform harness execution flow.

## Risk Classification

**Risk:** MEDIUM

This is an additive platform harness utility. It does not modify runtime product code, backend/frontend code, auth/RBAC/tenancy/migration/payment code, `.github`, or `.claude`.

## Report Fields

- **Branch:** `codex/platform-p1h-agent-timeout-watchdog-2026-05-26`
- **Commit:** pending final commit
- **Modified files:** `scripts/platform_agent_timeout_watchdog.py`, `scripts/test_platform_agent_timeout_watchdog.py`, `ai-ledger/platform/2026-05-26_p1h_agent_timeout_watchdog.md`
- **Tests:** `python scripts/test_platform_agent_timeout_watchdog.py`, `git diff --check`
- **Report path:** `ai-ledger/platform/2026-05-26_p1h_agent_timeout_watchdog.md`
- **Risk:** MEDIUM
