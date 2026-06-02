# P5-B Platform Batch Mission Check

**Date**: 2026-05-31
**Agent**: claude
**Branch**: codex/platform-p5bcd-platform-infra-batch-2026-05-31
**Base**: codex/platform-p5a-ledger-gap-audit-2026-05-31

---

## Modified Files

- `scripts/platform_batch_mission_check.py` (new)
- `scripts/test_platform_batch_mission_check.py` (new)
- `ai-ledger/platform/2026-05-31_p5b_batch_mission_check.md` (new)

## Tests

- `python scripts/test_platform_batch_mission_check.py` — 12/12 PASS

## Report Path

- `python scripts/platform_batch_mission_check.py --repo . [--json]`

## Risk

Low. Read-only diagnostic that reuses existing `platform_agent_mission_gate.validate_mission`. No existing code modified.

## Implementation Summary

Batch validates all `ai-ledger/platform/*_mission.json` files using the mission gate contract logic. Reports pass/fail per mission with total summary. Supports `--json` output. Stdlib only.

## Known Limitations

- Validates contract schema only; does not check whether referenced files exist on disk (that is the gap audit's job).
- Phase validation only allows P1-/P2-/P3- prefixes (per `platform_agent_mission_gate.validate_mission`). P4/P5 missions will be flagged as invalid until the mission gate phase rules are updated to include P4-/P5- prefixes. This update depends on a phase-unlock change covered by a separate work item and must not be broadened without dedicated test coverage.
