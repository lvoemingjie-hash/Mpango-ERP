# P7 Safety Automation Layer

**Date**: 2026-06-03
**Agent**: claude
**Branch**: codex/platform-p7-safety-automation-layer-2026-06-03
**Base**: platform-dev (0a5993e)
**Phase**: P7

---

## Objective

Build real platform-only safety automation tooling. Four scripts with paired tests, no product/runtime code.

## Scope

1. **P7-A Platform Diff Auditor** — Check changed files against allowed/forbidden path lists. Compare, staged, unstacked, untracked modes. Fail on forbidden prefix/keyword or files outside allowlist.
2. **P7-B Platform Function Registry** — Enumerate `scripts/platform_*.py`, pair with tests, identify related ledger artifacts.
3. **P7-C Platform Health Check** — Aggregate batch mission, harness index, worker reliability, diff auditor, detect-secrets, GitNexus into single pass/fail. Supports `--base-ref` for compare mode.
4. **P7-D Platform Merge Readiness Reporter** — Generate standard merge readiness report with all required fields. Short SHAs in JSON, full SHAs in markdown.

## Expected Artifacts

- `scripts/platform_diff_auditor.py` + `scripts/test_platform_diff_auditor.py`
- `scripts/platform_function_registry.py` + `scripts/test_platform_function_registry.py`
- `scripts/platform_health_check.py` + `scripts/test_platform_health_check.py`
- `scripts/platform_merge_readiness_reporter.py` + `scripts/test_platform_merge_readiness_reporter.py`
- `ai-ledger/platform/2026-06-03_p7_safety_automation_layer.md` (this file)
- `ai-ledger/platform/2026-06-03_p7_safety_automation_layer_mission.json`
- `ai-ledger/platform/2026-06-03_p7_safety_automation_layer_result.json`
- `ai-ledger/platform/2026-06-03_p7_safety_automation_layer_events.jsonl`

## Out of Scope

- No backend/frontend/product code changes.
- No `.github/`, `.claude/`, `docs/ai/`, auth/RBAC/tenancy/migration/payment/session paths.
