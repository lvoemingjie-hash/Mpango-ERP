# P16-F Queue Resume / Retry Contract

Branch: codex/platform-p16efghi-worktree-harness-closeout-2026-06-21
Base: origin/platform-dev (short f98e637)
Date: 2026-06-21

## Summary

The batch runner gains a retry and resume contract. Statuses are now pending,
passed, retried, failed, and skipped. A failing mission is retried up to
max_retries extra attempts; a pass after retry is recorded as retried. Resume
reads a prior batch report and carries forward missions that passed or retried,
re-running the rest. Worker failure is not swallowed and the aggregate stays
failed when any required mission ends failed.

## Files

- scripts/platform_worktree_batch_runner.py: STATUSES and SUCCESS_STATUSES; run_mission_with_retries; _resumed_result; load_resume_state; run_batch max_retries and resume_from params; build_batch_payload retried count, attempts, resumed, max_retries
- scripts/test_platform_worktree_batch_runner.py: 7 new tests (TestRetryResumeContract)

## Tests

- batch runner suite: 47 passed

## Scope

All paths under scripts/. No backend, frontend, migrations, or runtime paths touched.
