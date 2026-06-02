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

- `python scripts/test_platform_harness_index.py` — 58/58 PASS (34 existing + 4 pairing/existence + 12 stale-index + 8 path validation)

## Report Path

- `python scripts/platform_harness_index.py --repo . --check`

## Risk

Low. Additive change only — added `--check` flag, `check_consistency()`, `find_existing_indices()`, and `check_index_staleness()` functions. Existing `--output` generate behavior is unchanged and backward-compatible.

## Implementation Summary

Added `--check` CLI flag that:
1. Scans for script/test pairing and file existence issues (default mode).
2. With optional `--check-index <path>`, detects stale index artifacts by comparing current scripts/tests/ledgers against a specific generated index file. Not every `*harness_index*.md` in `ai-ledger/platform/` is a canonical generated index; stale detection requires an explicit artifact path.

Exits 0 when consistent, nonzero with diagnostics when issues found. Existing generate mode unchanged.

## Known Limitations

- Default `--check` is pairing/existence only. Stale detection requires explicit `--check-index <path>`.
- Stale detection checks whether current scripts/tests/ledgers are mentioned in the specified index; does not detect entries in the index that reference files removed from disk (reverse direction).
- Does not validate index content beyond structural presence checks.
