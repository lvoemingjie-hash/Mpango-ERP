# Phase P1-I: Agent Artifact Allowlist Collector

**Date:** 2026-05-26
**Branch:** `codex/platform-p1i-agent-artifact-allowlist-collector-2026-05-26`
**Base commit:** `d5c9c678d3b8bebe1d228f63305e29b4d5be79ef` (`origin/platform-dev`)
**Status:** COMPLETE for isolated task; not merged to `platform-dev`

## Scope

Add a platform-only artifact collector that records the actual git changed files after an agent task and compares them with an expected allowlist. It emits a JSON or markdown manifest that can be consumed by later batch review packets.

## Files Changed

| File | Operation |
|------|-----------|
| `scripts/platform_agent_artifact_collector.py` | new |
| `scripts/test_platform_agent_artifact_collector.py` | new |
| `ai-ledger/platform/2026-05-26_p1i_agent_artifact_allowlist_collector.md` | new |

## Implementation

CLI:

```bash
python scripts/platform_agent_artifact_collector.py \
  --repo . \
  --output ai-ledger/platform/artifact-manifest.json \
  --phase P1-I \
  --risk MEDIUM \
  --expected-file scripts/example.py
```

Behavior:

- Collects current git status with `git status --porcelain=v1 -uall`.
- Normalizes paths to `/`.
- Validates expected files are safe relative paths.
- Rejects expected files in forbidden platform/product/runtime paths.
- Compares actual changed files against expected files.
- Reports unexpected, missing, and forbidden changed files.
- Writes JSON or markdown output under `ai-ledger/platform/`.
- Exits 0 only when actual changed files exactly match expected files and no forbidden path is present.

## Test Evidence

```
python scripts/test_platform_agent_artifact_collector.py
............
----------------------------------------------------------------------
Ran 12 tests in 6.201s

OK

git diff --check
PASS
```

Coverage:

- Exact allowlist PASS and JSON manifest output.
- Markdown manifest output.
- Unexpected changed file FAIL.
- Missing expected file FAIL.
- Forbidden expected file FAIL before writing manifest.
- Expected file list from committed JSON array PASS.
- Invalid expected file list shape FAIL.
- Absolute/traversal/outside-ledger/bad-extension output paths FAIL.
- Traversal expected path FAIL.

## Forbidden Path Audit

Changed files are limited to:

- `scripts/platform_agent_artifact_collector.py`
- `scripts/test_platform_agent_artifact_collector.py`
- `ai-ledger/platform/2026-05-26_p1i_agent_artifact_allowlist_collector.md`

No product/runtime paths were touched. Forbidden path strings appear only as policy constants and negative test fixtures.

## GitNexus

```
npx gitnexus analyze
Repository indexed successfully
4,656 nodes | 13,551 edges | 317 clusters | 244 flows

GitNexus detect_changes(scope=staged)
changed_files: 3
risk_level: medium
affected_processes:
- Main -> Normalize_path (validate_output_path path-safety flow)
- Main -> Run_git (git status artifact collection flow)
```

Risk is MEDIUM because this task adds a new platform harness audit flow.

## Risk Classification

**Risk:** MEDIUM

This is additive platform harness code. It does not modify runtime product code, backend/frontend code, auth/RBAC/tenancy/migration/payment code, `.github`, or `.claude`.

## Report Fields

- **Branch:** `codex/platform-p1i-agent-artifact-allowlist-collector-2026-05-26`
- **Commit:** pending final commit
- **Modified files:** `scripts/platform_agent_artifact_collector.py`, `scripts/test_platform_agent_artifact_collector.py`, `ai-ledger/platform/2026-05-26_p1i_agent_artifact_allowlist_collector.md`
- **Tests:** `python scripts/test_platform_agent_artifact_collector.py`, `git diff --check`
- **Report path:** `ai-ledger/platform/2026-05-26_p1i_agent_artifact_allowlist_collector.md`
- **Risk:** MEDIUM
