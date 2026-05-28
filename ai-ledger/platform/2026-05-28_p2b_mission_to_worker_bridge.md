# Phase P2-B: Mission-to-Worker Bridge

**Date:** 2026-05-28
**Branch:** `codex/platform-p2b-mission-to-worker-bridge-2026-05-28`
**Base commit:** `ffb5f95f808be371253073d4cd9312c251ff883c` (`origin/platform-dev`)
**Status:** COMPLETE for isolated branch; not merged to `platform-dev`

## Scope

Add a platform bridge that reads a validated mission JSON contract, invokes the
opencode worker gate, and independently audits the real post-command git diff.

The bridge is intentionally separate from P2-A mission validation and P1-K
worker execution. P2-B ties them together and repeats the final changed-file
allowlist check so a worker cannot pass the mission input contract and then
leave extra artifacts behind.

## Files Changed

| File | Operation |
|------|-----------|
| `scripts/platform_mission_worker_bridge.py` | new |
| `scripts/test_platform_mission_worker_bridge.py` | new |
| `ai-ledger/platform/2026-05-28_p2b_mission_to_worker_bridge.md` | new |

## Implementation

CLI:

```bash
python scripts/platform_mission_worker_bridge.py --repo . --mission <mission.json>
```

Behavior:

- Loads and validates mission JSON through P2-A `validate_mission()`.
- Supports `opencode` missions only for execution.
- Builds the `platform_opencode_worker_gate.py` invocation from mission fields.
- Supports `--dry-run` to print the worker command without execution.
- Runs the worker command when not dry-run.
- Always collects real git changed files after worker execution.
- Allows only `expected_files` plus mission `result` and `events` outputs.
- Fails when actual changed files include anything outside that allowlist.
- Fails when actual changed files include forbidden paths.
- If the worker exits nonzero, still prints changed-file diagnostics and fails.

## Test Evidence

```
python scripts/test_platform_mission_worker_bridge.py -v
Ran 7 tests
OK
```

Coverage:

- Dry-run prints worker command and does not execute worker.
- Invalid mission contract fails before worker execution.
- Non-opencode mission fails as unsupported for bridge execution.
- Expected file plus result/events changes pass.
- Extra actual file fails even when worker exits 0.
- Forbidden actual path fails.
- Worker nonzero still prints changed-file diagnostics and exits nonzero.

## GitNexus Impact

Pre-change impact checks:

```
impact(target="validate_mission", direction="upstream")
risk: CRITICAL
direct callers: 44 test/main references
decision: do not modify validate_mission; call it from the new bridge only

impact(target="changed_paths", direction="upstream")
risk: LOW
direct callers: platform_opencode_worker_gate.main
decision: reuse changed_paths behavior without modifying it
```

## Forbidden Path Audit

Changed files are limited to `scripts/` and `ai-ledger/platform/`.
No product/runtime paths were touched. The bridge checks forbidden actual paths
at runtime, and forbidden path strings appear only as policy/test fixtures.

## Risk Classification

**Risk:** MEDIUM

This is additive platform harness code that creates a new mission-to-worker
execution flow. It does not modify runtime product code, backend/frontend code,
auth/RBAC/tenancy/migration/payment code, `.github`, `.claude`, or `docs/ai`.

## CTO Instruction Compliance Check

| CTO instruction | Implementation evidence | Test evidence | Status |
|----------------|-------------------------|---------------|--------|
| Continue P2 in isolated branches. | Branch is `codex/platform-p2b-mission-to-worker-bridge-2026-05-28`, based on `origin/platform-dev`. | Git branch/status evidence before commit. | PASS |
| Do not touch product/runtime paths. | Changed files are only bridge script, bridge tests, and this platform ledger. | Forbidden path audit checks changed file paths. | PASS |
| Bridge mission to worker execution. | `build_worker_command()` converts mission fields into worker gate CLI args. | `test_dry_run_prints_worker_command_and_does_not_execute`. | PASS |
| `expected_files` must be enforced after execution. | `audit_actual_changes()` compares real git changed files against expected + result/events allowlist. | `test_extra_file_fails_even_when_worker_exit_zero`. | PASS |
| Forbidden actual path must fail. | Post-command audit calls worker gate forbidden path policy on actual changed files. | `test_forbidden_actual_file_fails_even_if_expected_were_impossible`. | PASS |
| Worker nonzero still reports diagnostics. | Bridge always prints actual changed files after worker execution before final verdict. | `test_worker_nonzero_still_prints_changed_file_diagnostics`. | PASS |

## Counterexample Check

| Counterexample | Expected behavior | Test coverage |
|----------------|-------------------|---------------|
| Mission validates, worker exits 0, but creates `scripts/extra.py` not listed in `expected_files`. | Bridge fails after post-command git diff audit. | `test_extra_file_fails_even_when_worker_exit_zero` |
| Worker creates `backend/bad.py` after a valid mission, bypassing the mission input allowlist. | Bridge fails and reports forbidden actual path. | `test_forbidden_actual_file_fails_even_if_expected_were_impossible` |
| Worker exits nonzero after partial changes. | Bridge prints actual changed-file diagnostics and returns worker failure. | `test_worker_nonzero_still_prints_changed_file_diagnostics` |

## Completion Claim

COMPLETE for isolated branch. Do not merge to `platform-dev` without CTO merge
gate approval.

## Report Fields

- **Branch:** `codex/platform-p2b-mission-to-worker-bridge-2026-05-28`
- **Commit:** pending final commit
- **Modified files:** `scripts/platform_mission_worker_bridge.py`, `scripts/test_platform_mission_worker_bridge.py`, `ai-ledger/platform/2026-05-28_p2b_mission_to_worker_bridge.md`
- **Tests:** `python scripts/test_platform_mission_worker_bridge.py -v`
- **Report path:** `ai-ledger/platform/2026-05-28_p2b_mission_to_worker_bridge.md`
- **Risk:** MEDIUM
