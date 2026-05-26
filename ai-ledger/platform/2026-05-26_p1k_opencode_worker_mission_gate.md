# Phase P1-K: Opencode Worker Mission Gate

**Date:** 2026-05-26
**Branch:** `codex/platform-p1k-opencode-worker-mission-gate-2026-05-26`
**Base commit:** `d5c9c678d3b8bebe1d228f63305e29b4d5be79ef` (`origin/platform-dev`)
**Status:** COMPLETE for isolated task; not merged to `platform-dev`

## Scope

Add a platform-only gate that formalizes reliable `opencode` worker invocation. The gate uses the real opencode executable, clean `--pure` context, JSON event output, explicit worktree `--dir`, optional edit permission, event capture, result JSON schema validation, and artifact allowlist checks.

## Files Changed

| File | Operation |
|------|-----------|
| `scripts/platform_opencode_worker_gate.py` | new |
| `scripts/test_platform_opencode_worker_gate.py` | new |
| `ai-ledger/platform/2026-05-26_p1k_opencode_worker_mission_gate.md` | new |

## Implementation

CLI:

```bash
python scripts/platform_opencode_worker_gate.py \
  --repo . \
  --mission scripts/mission.md \
  --result ai-ledger/platform/worker-result.json \
  --events ai-ledger/platform/worker-events.jsonl \
  --expected-file scripts/example.py \
  --allow-edits
```

Behavior:

- Resolves `opencode.exe` from explicit `--opencode`, known Windows npm location, or PATH.
- Runs `opencode run --pure --format json --dir <repo>`.
- Adds `--dangerously-skip-permissions` only when `--allow-edits` is supplied.
- Writes raw JSON events to `ai-ledger/platform/*.jsonl` or `.json`.
- Requires worker result JSON under `ai-ledger/platform/*.json`.
- Validates result schema:
  - `status`: `done`, `failed`, or `partial`
  - `files_changed`: array of strings
  - `test_result`: string
  - optional `blocker`: string
- Validates `files_changed` is within `--expected-file`.
- Validates actual git changed files are within expected files plus result/events outputs.
- Returns `124` on timeout.
- Exits 0 only when opencode exits 0, result status is `done`, and artifact checks pass.

## Opencode Execution Evidence

This P1-K task was attempted through real `opencode.exe` with:

```text
opencode.exe run --pure --format json --dangerously-skip-permissions --dir <P1-K worktree> <mission>
```

Result:

- opencode process exited 0 after about 459 seconds.
- It produced JSON events but no task files.
- Final event ended with `reason: length`.
- The temporary events file was removed from final task scope.

Codex Platform CTO completed the implementation and verification after the worker produced no artifacts.

## Test Evidence

```
python scripts/test_platform_opencode_worker_gate.py
........
----------------------------------------------------------------------
Ran 8 tests in 8.810s

OK

git diff --check
PASS
```

Coverage:

- Dry-run validates and creates no files.
- Fake opencode success writes result/events and passes.
- Fake opencode nonzero result fails.
- Fake opencode timeout returns `124`.
- Missing result JSON fails.
- Partial status fails.
- Extra actual changed file fails artifact audit.
- Unsafe expected path fails.

## Forbidden Path Audit

Changed files are limited to:

- `scripts/platform_opencode_worker_gate.py`
- `scripts/test_platform_opencode_worker_gate.py`
- `ai-ledger/platform/2026-05-26_p1k_opencode_worker_mission_gate.md`

No product/runtime paths were touched. Forbidden path strings appear only as policy constants, documentation, and negative test fixtures.

## GitNexus

```
npx gitnexus analyze
Repository indexed successfully
4,645 nodes | 13,544 edges | 313 clusters | 245 flows

GitNexus detect_changes(scope=staged, repo=<P1-K worktree path>)
changed_files: 3
changed_count: 42
affected_count: 3
risk_level: medium
affected_processes:
- Main -> Normalize_path (ledger/result/events path validation flow)
- Main -> Get (opencode executable resolution flow)
- Main -> Run (test helper execution flow)
```

Risk is MEDIUM because this task adds a new platform worker invocation and artifact verification flow.

## Risk Classification

**Risk:** MEDIUM

This is additive platform harness code. It does not modify runtime product code, backend/frontend code, auth/RBAC/tenancy/migration/payment code, `.github`, or `.claude`.

## Report Fields

- **Branch:** `codex/platform-p1k-opencode-worker-mission-gate-2026-05-26`
- **Implementation commit:** `f2dc9adcbe8487cb955a34ea2987c9786a533eca`
- **Branch head:** reported in the final CTO handoff after commit creation
- **Modified files:** `scripts/platform_opencode_worker_gate.py`, `scripts/test_platform_opencode_worker_gate.py`, `ai-ledger/platform/2026-05-26_p1k_opencode_worker_mission_gate.md`
- **Tests:** `python scripts/test_platform_opencode_worker_gate.py`, `git diff --check`
- **Report path:** `ai-ledger/platform/2026-05-26_p1k_opencode_worker_mission_gate.md`
- **Risk:** MEDIUM
