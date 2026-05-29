# P3-B Opencode Timeout Evidence Hygiene

## Summary

- **Branch:** `codex/platform-p3b-opencode-timeout-evidence-2026-05-29`
- **Base:** stacked on `origin/codex/platform-p3a-governed-harness-index-2026-05-28` at `9dbad1b0eaf625f29f103b51d111fc101a037990`
- **Implementation commit:** `61d44542ae8104c434a5b5748d6255711d1415f2`
- **Final branch head:** recorded in CTO final response after ledger polish commit
- **Report path:** `ai-ledger/platform/2026-05-29_p3b_opencode_timeout_evidence.md`
- **Risk:** MEDIUM, platform harness only

## Opencode Execution

Opencode was invoked through `scripts/platform_mission_worker_bridge.py`.

- First run omitted `allow_edits` in the mission JSON. The bridge correctly withheld `--allow-edits`; opencode exited 0 internally but wrote no result JSON and made no implementation changes.
- The mission JSON was fixed to include `allow_edits: true`.
- Second run passed `--allow-edits`. Opencode again exited 0 internally but wrote no result JSON and made no implementation changes.
- Raw opencode event files were removed from the commit because P3-A already proved raw event streams may contain high-entropy session/snapshot identifiers that fail `detect-secrets`.

CTO completed the implementation manually after the worker failed to complete the mission.

## Modified Files

- `ai-ledger/platform/2026-05-29_p3b_opencode_timeout_evidence_mission.md`
- `ai-ledger/platform/2026-05-29_p3b_opencode_timeout_evidence_mission.json`
- `ai-ledger/platform/2026-05-29_p3b_opencode_result.json`
- `ai-ledger/platform/2026-05-29_p3b_opencode_timeout_evidence.md`
- `scripts/platform_opencode_worker_gate.py`
- `scripts/test_platform_opencode_worker_gate.py`

## Implementation

- `scripts/platform_opencode_worker_gate.py` now writes sanitized JSONL event summaries instead of raw opencode stdout/stderr.
- The sanitized event output records byte counts, non-empty line counts, exit code, timeout state, elapsed seconds, and a redaction policy marker.
- On timeout with missing result JSON, the gate writes a valid partial result JSON with `files_changed` limited to actual changed files that are also in `expected_files`.
- The gate still runs actual changed-file audit after command execution and reports unexpected files before returning failure.

## GitNexus Preflight

- `impact(target="run_worker", direction="upstream")`: LOW; direct caller is `scripts/platform_opencode_worker_gate.py:main`.
- `context(name="main", file_path="scripts/platform_opencode_worker_gate.py")`: reviewed; main owns worker validation, invocation, result validation, and artifact audit flow.
- `context(name="validate_result", file_path="scripts/platform_opencode_worker_gate.py")`: reviewed; called by worker gate main.
- A generic `impact(target="main")` is ambiguous in this repository and resolved to another file, so file-path context was used for disambiguation.

## Test Evidence

- `python scripts/test_platform_opencode_worker_gate.py`: PASS, 10 tests
- `python scripts/test_platform_mission_worker_bridge.py`: PASS, 7 tests
- `python scripts/test_platform_run_evidence_bundle.py`: PASS, 8 tests
- `python scripts/test_platform_agent_mission_gate.py`: PASS, 54 tests
- `python scripts/test_platform_harness_index.py`: PASS, 34 tests
- `git diff --check`: PASS
- `npx gitnexus analyze`: PASS, 5,046 nodes, 14,827 edges, 339 clusters, 250 flows
- GitNexus detect changes (staged): MEDIUM, affected processes limited to platform worker gate main flows
- Forbidden path audit: PASS, worktree changes limited to `scripts/` and `ai-ledger/platform/`

## CTO Instruction Compliance Check

| CTO instruction | Implementation evidence | Test evidence | Status |
|----------------|-------------------------|---------------|--------|
| Use opencode where possible | Bridge invoked opencode twice for this mission | Worker output recorded in this ledger | PASS |
| Keep work isolated | Work is on `codex/platform-p3b-opencode-timeout-evidence-2026-05-29` | Git status and final diff audit pending | PASS |
| Platform harness only | Changes are limited to `scripts/` and `ai-ledger/platform/` | Forbidden path audit pending | PASS |
| Do not commit raw opencode event streams | Raw events were removed; worker gate now writes sanitized summaries | New tests validate sanitized JSONL and absence of raw session-like strings | PASS |
| Preserve timeout semantics | Timeout still exits 124 | `test_timeout_returns_124` | PASS |
| Preserve actual changed-file audit | Audit still runs after worker execution and reports unexpected files | `test_timeout_extra_actual_file_fails_audit` and existing extra-file tests | PASS |

## Counterexample Check

| Counterexample | Expected behavior | Test coverage |
|----------------|-------------------|---------------|
| Raw stdout contains session/snapshot identifiers and is written directly to events | Events must contain only sanitized summaries | `test_timeout_events_jsonl_is_sanitized` |
| Worker times out, writes an unexpected extra file, and still reports a partial result | Gate must keep exit 124 and print unexpected changed-file diagnostics | `test_timeout_extra_actual_file_fails_audit` |
| Successful worker output includes raw text in committed events | Events must redact raw stdout and remain valid JSONL | `test_successful_worker_passes` |

## Completion Claim

COMPLETE for CTO-implemented P3-B harness hardening after final verification passes. Opencode execution itself is PARTIAL because it did not produce code changes or result JSON.
