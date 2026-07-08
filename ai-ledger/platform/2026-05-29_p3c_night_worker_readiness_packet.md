# P3-C Night Run: Worker Reliability & Batch Readiness Packet

## Summary

- **Branch:** `codex/platform-p3c-night-worker-readiness-2026-05-29`
- **HEAD:** `bdccd03b05bd72a1430ea1502ddbcbcf9ff53dc9`
- **Base:** `origin/platform-dev`
- **Risk:** HIGH (stacked P3-A + P3-B + P3-C merge)
- **Scope:** Platform governance/evidence only; no backend, frontend, product runtime, auth, RBAC, tenancy, session, migration, payment, `.github`, `.claude`, or `docs/ai` edits.

## Stack Under Review

| Phase | Branch | Status |
|-------|--------|--------|
| P3-A | `codex/platform-p3a-governed-harness-index-2026-05-28` | COMPLETE (CTO-finished after opencode timeout) |
| P3-B | `codex/platform-p3b-opencode-timeout-evidence-2026-05-29` | COMPLETE (CTO-finished after opencode no-output) |
| P3-C | `codex/platform-p3c-night-worker-readiness-2026-05-29` | This packet |

## Changed Files vs `origin/platform-dev..HEAD`

```
A   ai-ledger/platform/2026-05-28_p3a_governed_harness_index_mission.json
A   ai-ledger/platform/2026-05-28_p3a_governed_harness_index_mission.md
A   ai-ledger/platform/2026-05-28_p3a_opencode_result.json
A   ai-ledger/platform/2026-05-28_p3a_platform_harness_index.md
A   ai-ledger/platform/2026-05-29_p3b_opencode_result.json
A   ai-ledger/platform/2026-05-29_p3b_opencode_timeout_evidence.md
A   ai-ledger/platform/2026-05-29_p3b_opencode_timeout_evidence_mission.json
A   ai-ledger/platform/2026-05-29_p3b_opencode_timeout_evidence_mission.md
A   ai-ledger/platform/2026-05-29_p3c_night_worker_readiness_mission.json
A   ai-ledger/platform/2026-05-29_p3c_night_worker_readiness_mission.md
M   scripts/platform_agent_mission_gate.py
A   scripts/platform_harness_index.py
M   scripts/platform_opencode_worker_gate.py
M   scripts/test_platform_agent_mission_gate.py
A   scripts/test_platform_harness_index.py
M   scripts/test_platform_opencode_worker_gate.py
```

All changes are in `ai-ledger/platform/` and `scripts/`, within the platform harness allowlist.

## Changed Files vs `origin/codex/platform-p3b-opencode-timeout-evidence-2026-05-29..HEAD`

```
A   ai-ledger/platform/2026-05-29_p3c_night_worker_readiness_mission.json
A   ai-ledger/platform/2026-05-29_p3c_night_worker_readiness_mission.md
A   ai-ledger/platform/2026-05-29_p3c_night_worker_readiness_packet.md
A   ai-ledger/platform/2026-05-29_p3c_opencode_events.jsonl
A   ai-ledger/platform/2026-05-29_p3c_opencode_result.json
```

P3-C adds only mission contract files, this readiness packet, and sanitized worker result/events on top of P3-B.

## Commits Since `origin/platform-dev`

```
bdccd03 docs: add p3c night readiness mission
4e01424 docs: finalize p3b evidence ledger
61d4454 feat: sanitize opencode timeout evidence
05f885b docs: allow p3b opencode mission edits
c9b71f2 docs: add p3b opencode timeout evidence mission
9dbad1b feat: add governed platform harness index
34cee19 feat: allow p3 platform mission contracts
620a227 docs: add p3a governed opencode mission
```

## Worker Reliability Findings

### P3-A: Opencode Timeout After 900s

- Opencode was invoked via `scripts/platform_mission_worker_bridge.py` with `--allow-edits`.
- `platform_opencode_worker_gate.py` timed out at 900 seconds with exit code 124.
- Partial files were generated (`scripts/platform_harness_index.py`, `scripts/test_platform_harness_index.py`) but no result JSON was written.
- Raw event stream (`ai-ledger/platform/2026-05-28_p3a_opencode_events.jsonl`) was not committed because `detect-secrets` flagged high-entropy opencode session/snapshot identifiers.
- CTO reviewed generated files, normalized output, and wrote the harness index ledger and partial-result JSON.

### P3-B: Opencode No Output on Two Invocations

- First invocation: `allow_edits` was omitted from the mission JSON; the bridge correctly withheld `--allow-edits`. Opencode exited 0 but produced no result JSON or code changes.
- Mission JSON was corrected to include `allow_edits: true`.
- Second invocation: opencode exited 0 internally but again produced no result JSON or code changes.
- CTO completed the P3-B implementation manually: sanitized event output in `platform_opencode_worker_gate.py`, added partial timeout result JSON writing, and wrote all ledger files.

### P3-B Hardening Improvements (Now in Stack)

- `scripts/platform_opencode_worker_gate.py` now writes sanitized JSONL event summaries instead of raw opencode stdout/stderr.
- On timeout with missing result JSON, the gate writes a valid partial result JSON with `files_changed` limited to actual changed files in `expected_files`.
- Actual changed-file audit still runs after command execution and reports unexpected files.

### Pattern Summary

| Phase | Worker Invoked | Worker Completed | CTO Finished | Root Cause |
|-------|---------------|-----------------|--------------|------------|
| P3-A | Yes | No (timeout 900s) | Yes | Opencode exceeded timeout; partial files saved |
| P3-B | Yes (x2) | No (no output) | Yes | Opencode exited 0 but produced no artifacts |
| P3-C | Yes | Yes | No | Docs-only packet task completed through worker gate |

## Test Plan for Tomorrow

Before merging P3-A/P3-B/P3-C into `platform-dev`:

1. **P3-A focused tests:**
   - `python scripts/test_platform_harness_index.py` - expect 34 PASS
   - Verify harness index output matches current `scripts/` contents

2. **P3-B focused tests:**
   - `python scripts/test_platform_opencode_worker_gate.py` - expect 10 PASS
   - Verify sanitized JSONL output contains no raw session identifiers
   - Verify partial timeout result JSON is written correctly

3. **P3-C focused tests:**
   - `git diff --check` - no whitespace errors
   - `git status --short` - only expected P3-C packet, result JSON, events, and mission files
   - Forbidden path audit - no edits outside `ai-ledger/platform/` and `scripts/`

4. **P1/P2 critical regression tests:**
   - `python scripts/test_platform_agent_mission_gate.py` - expect 54 PASS
   - `python scripts/test_platform_mission_worker_bridge.py` - expect 7 PASS
   - `python scripts/test_platform_run_evidence_bundle.py` - expect 8 PASS

5. **Full harness regression:**
   - Run all `scripts/test_platform_*.py` files
   - `npx gitnexus analyze` - verify index freshness
   - GitNexus compare vs `origin/platform-dev` - confirm expected scope

6. **Runner smoke:**
   - Only after CTO approves merge to `platform-dev`
   - Verify no runtime regressions in platform harness

## Night Run Verification

- `python scripts/test_platform_*.py`: PASS, 16 files
- `python scripts/test_platform_agent_artifact_collector.py`: PASS, 12 tests
- `python scripts/test_platform_agent_mission_gate.py`: PASS, 54 tests
- `python scripts/test_platform_agent_preflight.py`: PASS, 36 tests
- `python scripts/test_platform_agent_run_bundle_gate.py`: PASS, 8 tests
- `python scripts/test_platform_agent_timeout_watchdog.py`: PASS, 9 tests
- `python scripts/test_platform_batch_review_packet.py`: PASS, 8 tests
- `python scripts/test_platform_directive_gate.py`: PASS, 23 tests
- `python scripts/test_platform_harness_index.py`: PASS, 34 tests
- `python scripts/test_platform_mission_worker_bridge.py`: PASS, 7 tests
- `python scripts/test_platform_opencode_worker_gate.py`: PASS, 10 tests
- `python scripts/test_platform_remote_runner_packet.py`: PASS, 9 tests
- `python scripts/test_platform_run_evidence_bundle.py`: PASS, 8 tests
- `python scripts/test_platform_run_packet_gate.py`: PASS, 46 tests
- `python scripts/test_platform_runner_gate.py`: PASS, 6 tests
- `python scripts/test_platform_task_execution_bridge.py`: PASS, 13 tests
- `python scripts/test_platform_toolchain_gate.py`: PASS, 13 tests
- `git diff --check`: PASS
- Worktree forbidden path audit: PASS, P3-C uncommitted delta only under `ai-ledger/platform/`
- Sanitized P3-C opencode events JSONL audit: PASS, no raw session/snapshot/message/call identifiers found
- `npx gitnexus analyze`: PASS, 5,037 nodes, 14,823 edges, 334 clusters, 250 flows
- GitNexus detect changes (staged P3-C packet/result/events): LOW, affected processes none

## CTO Instruction Compliance Check

| CTO Instruction | Evidence | Status |
|----------------|----------|--------|
| Modify only expected P3-C evidence files | P3-C adds mission files, packet, sanitized events, and result JSON under `ai-ledger/platform/` | PASS |
| No edits to backend, frontend, product runtime, auth, RBAC, tenancy, session, migration, payment, `.github`, `.claude`, or `docs/ai` | All changes limited to `ai-ledger/platform/` and `scripts/` | PASS |
| Summarize P3-A/P3-B/P3-C stack | Sections above document all three phases | PASS |
| Worker reliability findings documented | P3-A timeout, P3-B no-output, P3-B hardening all recorded | PASS |
| Test plan for tomorrow provided | Six-point test plan above | PASS |
| Counterexample check included | See below | PASS |
| Completion claim as COMPLETE only if docs-only | This is a docs-only task; claim below | PASS |

## Counterexample Check

| Counterexample | Expected Behavior | Mitigation |
|----------------|-------------------|------------|
| P3-C packet edits runtime code | Packet must be docs-only | P3-C delta contains only `ai-ledger/platform/` files; no runtime code changed |
| Stacked merge introduces P3-A timeout artifacts into `platform-dev` | Raw event files must not be committed | P3-A raw events were excluded; P3-B gate now sanitizes all event output |
| P3-B sanitization misses a raw session identifier | Sanitized JSONL must contain only summary fields | Test `test_timeout_events_jsonl_is_sanitized` validates absence of raw session-like strings |
| P3-A partial files are incorrect or incomplete | Harness index must reflect actual `scripts/` contents | Test `test_platform_harness_index.py` (34 tests) validates index generation |
| Forbidden paths edited in stacked merge | Only `ai-ledger/platform/` and `scripts/` allowed | `git diff --name-status origin/platform-dev..HEAD` audit confirms no forbidden paths |

## Completion Claim

COMPLETE. This packet is written, the worker completed successfully, the task is docs-only, and no runtime code was edited by P3-C.
