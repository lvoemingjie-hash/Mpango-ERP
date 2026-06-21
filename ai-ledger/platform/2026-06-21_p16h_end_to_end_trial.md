# P16-H End-to-End Harness Trial

Branch: codex/platform-p16efghi-worktree-harness-closeout-2026-06-21
Base: origin/platform-dev (short f98e637)
Date: 2026-06-21

## Summary

A reproducible trial (scripts/platform_p16h_trial.py) runs three dummy
platform-only missions through the executor and batch runner in a throwaway repo:
one success, one controlled failure, and one retry-then-pass. A second pass
demonstrates resume. The trial proves the per-mission reports carry no long hex
run, worktrees are cleaned up automatically, and resume carries forward passed
missions.

The trial showed that retries reused the worker branch and hit a failure on the
second worktree add. The executor now uses git worktree add -B (create-or-reset),
which makes retries and re-runs idempotent. test_platform_worktree_executor.py
gains a rerun test and the command-shape assertion moved to -B.

## Trial results (see 2026-06-21_p16h_trial_proofs.json)

- run1 verdicts: passed, failed, retried
- run1 attempts: 1, 2, 2
- run1 counts: passed 1, retried 1, failed 1
- per-mission reports: no long hex run
- worktrees cleaned up: true
- run2 resume carried the passed mission forward: true

## Files

- scripts/platform_worktree_executor.py: worktree add -B (retry-safe)
- scripts/test_platform_worktree_executor.py: rerun test; command-shape -B
- scripts/platform_p16h_trial.py: new reproducible trial
- ai-ledger/platform/2026-06-21_p16h_trial_batch_report.json: trial batch report
- ai-ledger/platform/2026-06-21_p16h_trial_proofs.json: trial proofs

## Tests

- executor suite: 42 passed (includes rerun test)

## Scope

All paths under scripts/ and ai-ledger/platform/. No backend, frontend,
migrations, or runtime paths touched.
