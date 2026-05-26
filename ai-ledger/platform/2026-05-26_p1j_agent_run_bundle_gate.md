# Phase P1-J: Agent Run Bundle Gate

**Date:** 2026-05-26
**Branch:** `codex/platform-p1j-agent-run-bundle-gate-2026-05-26`
**Base commit:** `d5c9c678d3b8bebe1d228f63305e29b4d5be79ef` (`origin/platform-dev`)
**Stack dependencies:** P1-H watchdog and P1-I artifact collector are included in this isolated branch stack.
**Status:** COMPLETE for isolated task; not merged to `platform-dev`

## Scope

Add a platform-only bundle gate that executes one platform agent run from a JSON bundle. The bundle gate validates task contract fields, invokes the P1-H timeout watchdog, then invokes the P1-I artifact collector even when the watched command fails or times out.

## Files Changed

P1-J task files:

| File | Operation |
|------|-----------|
| `scripts/platform_agent_run_bundle_gate.py` | new |
| `scripts/test_platform_agent_run_bundle_gate.py` | new |
| `ai-ledger/platform/2026-05-26_p1j_agent_run_bundle_gate.md` | new |

This branch also carries P1-H and P1-I stack dependencies because those tasks are not yet merged to `platform-dev`.

## Implementation

CLI:

```bash
python scripts/platform_agent_run_bundle_gate.py \
  --repo . \
  --bundle ai-ledger/platform/example-bundle.json
```

Bundle fields:

- `phase`
- `agent`
- `timeout_seconds`
- `risk`
- `command`
- `expected_files`
- `watchdog_report`
- `artifact_manifest`

Behavior:

- Validates bundle shape and path safety.
- Rejects forbidden expected/report/manifest paths.
- `--dry-run` prints watchdog and collector invocations without writing outputs.
- Non-dry-run invokes `platform_agent_timeout_watchdog.py`.
- Then invokes `platform_agent_artifact_collector.py` regardless of watchdog result.
- Final exit code is 0 only when watchdog and collector both pass.
- Timeout preserves exit code `124` when collector passes.
- Collector failure takes precedence over command failure because artifact scope is invalid.

## Opencode Execution Evidence

P1-J was intentionally attempted as an M-size task through P1-H watchdog:

```text
WATCHDOG OUTCOME: TIMEOUT
Exit code: 124
Timeout: 900 seconds
Modified Files: none
```

The temporary watchdog report was removed from the final task scope after its evidence was recorded here. Codex Platform CTO completed the implementation and verification.

## Test Evidence

```
python scripts/test_platform_agent_run_bundle_gate.py
........
----------------------------------------------------------------------
Ran 8 tests in 7.577s

OK

git diff --check
PASS
```

Coverage:

- Dry-run validates bundle and creates no files.
- Successful command creates expected artifact and exits 0.
- Nonzero command still runs collector and final exit is nonzero.
- Timeout preserves `124` while collector still runs.
- Unexpected artifact causes collector failure.
- Missing bundle field fails before execution.
- Unsafe expected path fails.
- Unsafe report path fails.

## Forbidden Path Audit

P1-J task files are limited to:

- `scripts/platform_agent_run_bundle_gate.py`
- `scripts/test_platform_agent_run_bundle_gate.py`
- `ai-ledger/platform/2026-05-26_p1j_agent_run_bundle_gate.md`

No product/runtime paths were touched. Forbidden path strings appear only as policy constants, documentation, and negative test fixtures.

## GitNexus

```
npx gitnexus analyze
Repository indexed successfully
4,725 nodes | 13,799 edges | 314 clusters | 247 flows

GitNexus detect_changes(scope=staged)
changed_files: 3
risk_level: medium
affected_processes:
- Main -> Normalize_path (bundle path validation flow)
- Main -> Script_path (watchdog invocation construction flow)
```

Risk is MEDIUM for P1-J itself because it adds a new platform harness orchestration flow. Batch compare may be HIGH when H/I/J are reviewed together because it includes multiple new harness flows.

## Risk Classification

**Risk:** MEDIUM

This is additive platform harness orchestration. It does not modify runtime product code, backend/frontend code, auth/RBAC/tenancy/migration/payment code, `.github`, or `.claude`.

## Report Fields

- **Branch:** `codex/platform-p1j-agent-run-bundle-gate-2026-05-26`
- **Commit:** pending final commit
- **Modified files:** `scripts/platform_agent_run_bundle_gate.py`, `scripts/test_platform_agent_run_bundle_gate.py`, `ai-ledger/platform/2026-05-26_p1j_agent_run_bundle_gate.md`
- **Tests:** `python scripts/test_platform_agent_run_bundle_gate.py`, `git diff --check`
- **Report path:** `ai-ledger/platform/2026-05-26_p1j_agent_run_bundle_gate.md`
- **Risk:** MEDIUM
