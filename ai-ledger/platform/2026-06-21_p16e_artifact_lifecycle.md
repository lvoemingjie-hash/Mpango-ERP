# P16-E Artifact Lifecycle

Branch: codex/platform-p16efghi-worktree-harness-closeout-2026-06-21
Base: origin/platform-dev (short f98e637)
Date: 2026-06-21

## Summary

Executor report payloads shorten any 40-char hex run to 12 chars before write.
The batch runner adds a keep_reports option and a sanitize_report_file helper,
plus a --remove-reports CLI flag.

## Files

- scripts/platform_worktree_executor.py: shorten_shas, sanitize_payload
- scripts/platform_worktree_batch_runner.py: sanitize_report_file, keep_reports
- scripts/test_platform_worktree_executor.py: 3 new tests
- scripts/test_platform_worktree_batch_runner.py: 2 new tests

## Tests

- executor suite: 41 passed
- batch runner suite: 40 passed

## Scope

All paths under scripts/. No backend, frontend, migrations, or runtime paths touched.
