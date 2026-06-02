# P5-D Harness Index Consistency Check

**Date**: 2026-05-31
**Agent**: claude
**Branch**: codex/platform-p5bcd-platform-infra-batch-2026-05-31
**Base**: codex/platform-p5a-ledger-gap-audit-2026-05-31

---

## Modified Files

- `scripts/platform_harness_index.py` (modified — added `--check` mode and `check_consistency` function)
- `scripts/test_platform_harness_index.py` (modified — added 6 new tests)
- `ai-ledger/platform/2026-05-31_p5d_harness_index_check.md` (new)

## Tests

- `python scripts/test_platform_harness_index.py` — 46/46 PASS (34 existing + 6 new stale-index + 6 prior check-mode)

## Report Path

- `python scripts/platform_harness_index.py --repo . --check`

## Risk

Low. Additive change only — added `--check` flag, `check_consistency()`, `find_existing_indices()`, and `check_index_staleness()` functions. Existing `--output` generate behavior is unchanged and backward-compatible.

## Implementation Summary

Added `--check` CLI flag that:
1. Scans for script/test pairing and file existence issues.
2. Detects stale index artifacts by comparing current scripts/tests/ledgers against any existing `*harness_index*.md` in `ai-ledger/platform/`. Reports new scripts, tests, or ledgers that exist on disk but are not listed in the index.

Exits 0 when consistent, nonzero with diagnostics when issues found. Existing generate mode unchanged.

## Known Limitations

- Stale index detection checks whether current scripts/tests/ledgers are mentioned in the existing index; it does not detect entries in the index that reference files removed from disk (reverse direction).
- Does not validate index content beyond structural presence checks.
