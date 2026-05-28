# Phase P2-C: Run Evidence Bundle

**Date:** 2026-05-28
**Branch:** `codex/platform-p2c-run-evidence-bundle-2026-05-28`
**Base commit:** `ffb5f95f808be371253073d4cd9312c251ff883c`
**Status:** COMPLETE for isolated branch; not merged to `platform-dev`

## Scope

Add a stdlib-only evidence bundle generator for completed long agent runs. The bundle turns a mission JSON, worker result JSON, worker events JSONL, test command list, and actual `git status` changed files into a CTO-readable markdown report.

## Files Changed

| File | Operation |
|------|-----------|
| `scripts/platform_run_evidence_bundle.py` | new |
| `scripts/test_platform_run_evidence_bundle.py` | new |
| `ai-ledger/platform/2026-05-28_p2c_run_evidence_bundle.md` | new |

## Implementation

CLI:

```bash
python scripts/platform_run_evidence_bundle.py --repo . --mission mission.json --result ai-ledger/platform/result.json --events ai-ledger/platform/events.jsonl --output ai-ledger/platform/bundle.md
```

Behavior:

- Validates the mission JSON with `platform_agent_mission_gate.validate_mission()`.
- Validates result JSON schema: `status`, `files_changed`, `test_result`, optional `blocker`.
- Reads events JSONL, counts non-empty event lines, and records malformed JSONL diagnostics without crashing.
- Validates all paths as safe relative paths with no absolute path, Windows drive prefix, traversal, `.`, empty segment, or forbidden product/runtime path.
- Requires output bundles under `ai-ledger/platform/` ending `.md`.
- Collects staged, unstaged, and untracked files via `git status --porcelain=v1 -uall`.
- Fails when actual changed files exceed `expected_files + result + events + output`.
- Fails when actual changed files touch forbidden paths, even if they appear in an allowlist.
- Allows the output bundle itself so report generation does not self-fail.

## Opencode Worker Attempted Implementation

This task was delegated to opencode first. The opencode run read project context but ended with `reason:length` before producing file changes. Codex Platform CTO completed the bounded implementation manually in the same isolated branch.

## Test Evidence

```text
python scripts/test_platform_run_evidence_bundle.py
Ran 8 tests in 4.075s
OK

python scripts/test_platform_agent_mission_gate.py
Ran 53 tests in 0.952s
OK

python scripts/test_platform_opencode_worker_gate.py
Ran 8 tests in 9.718s
OK

python scripts/test_platform_runner_gate.py
Ran 6 tests in 5.520s
OK

git diff --cached --check
PASS

Forbidden path audit
PASS
```

Coverage:

- Valid bundle writes markdown and passes.
- Output path outside `ai-ledger/platform/` fails.
- Missing result JSON fails and still writes a FAIL bundle when output is safe.
- Malformed events JSONL records diagnostics and fails without crashing.
- Unexpected actual changed files fail and are reported.
- Forbidden actual changed files fail and are reported.
- Output file is allowlisted and does not cause self-failure.
- Mission validation failure fails.

## Forbidden Path Audit

Changed files are limited to platform harness and platform ledger paths:

- `scripts/platform_run_evidence_bundle.py`
- `scripts/test_platform_run_evidence_bundle.py`
- `ai-ledger/platform/2026-05-28_p2c_run_evidence_bundle.md`

No product/runtime paths are touched. Forbidden path strings appear only as policy constants and negative test fixtures.

## Risk Classification

**Risk:** MEDIUM

This is additive platform harness code. It does not modify product runtime, backend/frontend code, `.github`, `.claude`, docs/ai, auth/RBAC/tenancy/migration/payment logic, or deployment paths.

GitNexus classifies the staged change as MEDIUM because it adds a new harness CLI flow (`Build_evidence -> Normalize_path`). The risk is platform-harness internal, not product/runtime.

## GitNexus Evidence

```text
npx gitnexus analyze
Repository indexed successfully
4,900 nodes | 14,390 edges | 327 clusters | 251 flows

GitNexus detect_changes(scope=staged)
changed_files: 3
changed_count: 50
affected_count: 1
risk_level: medium
affected_processes:
- Build_evidence -> Normalize_path
```

## CTO Instruction Compliance Check

- [x] Isolated branch only.
- [x] Stdlib-only implementation.
- [x] No dependency on unmerged P2-B code.
- [x] Evidence bundle validates P2-A mission contracts.
- [x] Actual changed files are checked against a post-run allowlist.
- [x] Output bundle is included in the allowlist.
- [x] Forbidden actual changed files fail even when otherwise listed.
- [x] Malformed events JSONL is diagnostic rather than a crash.
- [x] No forbidden files touched by implementation.

## Counterexample Check

| Counterexample | Expected behavior | Test coverage |
|----------------|-------------------|---------------|
| A worker leaves `scripts/extra.py` outside `expected_files` while still reporting `status: done`. | Bundle verdict FAIL with `scripts/extra.py` listed as unexpected. | `test_unexpected_actual_changed_file_fails_and_is_reported` |
| A worker changes `backend/evil.py`, a forbidden runtime path. | Bundle verdict FAIL with forbidden path diagnostics. | `test_forbidden_actual_changed_file_fails_and_is_reported` |
| Events JSONL contains a malformed line after valid events. | Bundle verdict FAIL and report includes the malformed line number, without crashing. | `test_malformed_events_jsonl_is_diagnostic_fail_not_crash` |

## Report Fields

- **Branch:** `codex/platform-p2c-run-evidence-bundle-2026-05-28`
- **Final branch head:** reported after final commit
- **Modified files:** `scripts/platform_run_evidence_bundle.py`, `scripts/test_platform_run_evidence_bundle.py`, `ai-ledger/platform/2026-05-28_p2c_run_evidence_bundle.md`
- **Tests:** `test_platform_run_evidence_bundle.py` (8), `test_platform_agent_mission_gate.py` (53), `test_platform_opencode_worker_gate.py` (8), `test_platform_runner_gate.py` (6)
- **Report path:** `ai-ledger/platform/2026-05-28_p2c_run_evidence_bundle.md`
- **Risk:** MEDIUM
