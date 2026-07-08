# P5-C Worker Reliability Summary

**Date**: 2026-05-31
**Agent**: claude
**Branch**: codex/platform-p5bcd-platform-infra-batch-2026-05-31
**Base**: codex/platform-p5a-ledger-gap-audit-2026-05-31

---

## Modified Files

- `scripts/platform_worker_reliability_summary.py` (new)
- `scripts/test_platform_worker_reliability_summary.py` (new)
- `ai-ledger/platform/2026-05-31_p5c_worker_reliability_summary.md` (new)

## Tests

- `python scripts/test_platform_worker_reliability_summary.py` — 11/11 PASS

## Report Path

- `python scripts/platform_worker_reliability_summary.py --repo . [--json]`

## Risk

Low. Read-only diagnostic scanning result JSONs and events JSONLs. Never commits raw worker stdout/stderr.

## Implementation Summary

Reads all mission JSONs to find result/events references. Summarizes status breakdown (done/partial/failed/unknown), timeout counts, nonzero exit codes, elapsed seconds stats, malformed/missing artifact counts, and sanitized event status. Supports `--json`. Stdlib only.

## Known Limitations

- Relies on mission JSONs referencing correct result/events paths.
- Elapsed seconds only available when events JSONL contains `elapsed_seconds` fields.
- Does not validate the full result JSON schema beyond parsing.
