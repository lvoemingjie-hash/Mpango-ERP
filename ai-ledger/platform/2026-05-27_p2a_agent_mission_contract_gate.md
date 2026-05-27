# Phase P2-A: Agent Mission Contract Gate

**Date:** 2026-05-27
**Branch:** `codex/platform-p2a-agent-mission-contract-gate-2026-05-27`
**Base commit:** `bd52094a475570ad97ce1eaf1ad79d91e1dc75df`
**Status:** COMPLETE for isolated branch; not merged to `platform-dev`

## Scope

Add a stdlib-only mission contract validator for future long agent runs. Validates a mission JSON file containing phase, agent, mission path, expected files, result/events output paths, and timeout. Optionally prints the `platform_opencode_worker_gate.py` runner command for opencode agents.

## Files Changed

| File | Operation |
|------|-----------|
| `scripts/platform_agent_mission_gate.py` | new |
| `scripts/test_platform_agent_mission_gate.py` | new |
| `ai-ledger/platform/2026-05-27_p2a_agent_mission_contract_gate.md` | new |

## Implementation

CLI:

```bash
python scripts/platform_agent_mission_gate.py --repo . --mission mission.json [--print-runner-command]
```

Mission JSON contract:

- `phase`: non-empty string beginning with `P2-` or `P1-`
- `agent`: one of `opencode`, `claude`, `goose`
- `mission`: safe relative path ending `.md`; no forbidden/traversal/absolute paths
- `expected_files`: non-empty array of safe relative paths
- `result`: safe relative path under `ai-ledger/platform/` ending `.json`
- `events`: safe relative path under `ai-ledger/platform/` ending `.jsonl`
- `timeout_seconds`: integer in range 1..43200
- optional `allow_edits`: boolean
- optional `notes`: string

Behavior:

- Rejects malformed JSON with exit 1 and clear FAIL messages
- Passes valid mission with exit 0 and PASS messages
- `--print-runner-command` prints `platform_opencode_worker_gate.py` invocation for agent `opencode` only
- For non-opencode agents, `--print-runner-command` prints unsupported message and fails

## Opencode Worker Attempted Implementation

This task was attempted through opencode worker. The opencode worker produced the initial implementation and test suite. Codex Platform CTO then reviewed the result and added stricter path safety checks for drive-qualified paths, `.` path parts, and empty path parts.

## Test Evidence

```
python scripts/test_platform_agent_mission_gate.py -v
Ran 53 tests in 0.967s
OK
```

Coverage:

- Valid mission passes (unit + CLI)
- Missing required key fails (all 7 keys)
- Malformed JSON fails
- Unsafe mission path fails (absolute, drive-qualified, traversal, `.`, empty path part, forbidden, non-.md)
- Forbidden expected file fails (forbidden, absolute, drive-qualified, traversal, `.`, empty path part)
- Empty expected_files fails (empty array, non-array)
- Invalid result/events output paths fail, including drive-qualified and empty path part cases
- Timeout out of range fails (0, negative, too large, float)
- Print runner command for opencode includes platform_opencode_worker_gate.py and expected files
- Print runner command for claude fails as unsupported
- Optional fields (allow_edits, notes) validated
- Phase prefix validation
- Agent validation (all three valid + invalid)
- Non-object JSON fails
- Nonexistent mission file fails

## Forbidden Path Audit

Changed files are limited to:

- `scripts/platform_agent_mission_gate.py`
- `scripts/test_platform_agent_mission_gate.py`
- `ai-ledger/platform/2026-05-27_p2a_agent_mission_contract_gate.md`

No product/runtime paths were touched. Forbidden path strings appear only as policy constants and negative test fixtures.

## Risk Classification

**Risk:** MEDIUM

This is additive platform harness code. GitNexus marks the staged change MEDIUM because it introduces a new mission-gate CLI flow. It does not modify runtime product code, backend/frontend code, auth/RBAC/tenancy/migration/payment code, `.github`, or `.claude`.

## GitNexus Evidence

```
npx gitnexus analyze
Repository already up to date

GitNexus detect_changes(scope=staged)
changed_files: 3
changed_count: 43
affected_count: 1
risk_level: medium
affected_processes:
- Main -> Normalize_path (mission contract validation flow)
```

## CTO Instruction Compliance Check

- [x] Stdlib-only implementation (no third-party imports)
- [x] Mission JSON contract with all required keys validated
- [x] Phase prefix validation (P2- or P1-)
- [x] Agent allowlist (opencode, claude, goose)
- [x] Safe relative path enforcement (no absolute, drive-qualified, traversal, `.`, empty path part, or forbidden paths)
- [x] Result path under `ai-ledger/platform/` ending `.json`
- [x] Events path under `ai-ledger/platform/` ending `.jsonl`
- [x] Timeout range 1..43200
- [x] `--print-runner-command` for opencode only
- [x] Non-opencode agents rejected for runner command
- [x] All 10 specified test cases covered
- [x] Exit 1 on failure, exit 0 on pass
- [x] No forbidden files touched

## Counterexample Check

| Counterexample | Expected behavior | Test coverage |
|----------------|-------------------|---------------|
| A mission claims `expected_files: ["C:/tmp/out.py"]`, escaping repo-relative allowlists while looking like a file contract. | Reject as drive-qualified / not safe relative. | `test_drive_qualified_expected_file` |
| A mission uses `scripts//out.py` or `scripts/./out.py`, which could normalize into an allowed path after bypassing string checks. | Reject unsafe empty or `.` path parts before any runner command is printed. | `test_empty_expected_file_path_part`, `test_dot_expected_file_path_part` |
| A mission writes `events` to `ai-ledger/platform//events.jsonl`, visually under the ledger but containing an empty path part. | Reject as unsafe path part. | `test_events_empty_path_part_fails` |

## Report Fields

- **Branch:** `codex/platform-p2a-agent-mission-contract-gate-2026-05-27`
- **Commit:** pending final commit
- **Modified files:** `scripts/platform_agent_mission_gate.py`, `scripts/test_platform_agent_mission_gate.py`, `ai-ledger/platform/2026-05-27_p2a_agent_mission_contract_gate.md`
- **Tests:** `python scripts/test_platform_agent_mission_gate.py -v` (53 passed)
- **Report path:** `ai-ledger/platform/2026-05-27_p2a_agent_mission_contract_gate.md`
- **Risk:** MEDIUM
