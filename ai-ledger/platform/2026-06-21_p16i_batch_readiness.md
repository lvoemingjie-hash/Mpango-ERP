# P16-I Batch Readiness Packet

Branch: codex/platform-p16efghi-worktree-harness-closeout-2026-06-21
Base: origin/platform-dev (short f98e637)
Date: 2026-06-21
Merge target: none (isolated branch; not merged to platform-dev)

## Commit chain (oldest first)

1. P16-E artifact lifecycle report sanitization
2. P16-F queue resume retry contract
3. P16-G CTO review packet generator
4. P16-H end to end harness trial

The machine-readable CTO review packet is 2026-06-21_p16i_review_packet.json
(branch, commit subjects, modified files, forbidden audit, risk).

## Slice summary

- P16-E: executor reports are sanitized so no 40-char hex run reaches disk;
  batch runner gains a keep_reports option and a sanitize_report_file helper.
- P16-F: queue resume and retry contract; statuses pending, passed, retried,
  failed, skipped; max_retries and resume_from; aggregate stays failed when any
  required mission fails.
- P16-G: new platform_worktree_review_packet.py builds a CTO review packet.
- P16-H: end-to-end trial proves success, controlled failure, retry-then-pass,
  resume, sanitized evidence, and automatic cleanup; executor switched to
  git worktree add -B so retries are idempotent.

## Tests

- test_platform_worktree_executor.py: 42 passed
- test_platform_worktree_batch_runner.py: 47 passed
- test_platform_worktree_review_packet.py: 5 passed
- test_platform_worktree_smoke_worker.py: unchanged from base
- test_platform_diff_auditor.py: unchanged from base
- test_platform_agent_mission_gate.py: unchanged from base

## Forbidden path audit

All changes are under scripts/ and ai-ledger/platform/. No backend, frontend,
migrations, product-dev-recovered, .github, or .claude paths touched. The review
packet forbidden audit returns PASS.

## detect-secrets

pre-commit detect-secrets (baseline) passes on every committed file. Committed
evidence uses symbolic refs, integer counts, and commit subjects instead of
object ids; the one mandatory test fixture is marked pragma allowlist secret.

## Risks and open limitations

- The retry feature retries the whole mission (fresh worktree each attempt).
  Workers that need cross-attempt state must persist it outside the worktree,
  as the trial retry worker does via a marker file.
- The risk assessor in the review packet treats any non-passed batch aggregate
  as high risk; a batch that intentionally includes a controlled failure (like
  the P16-H trial) should be read with that in mind.
- Per-mission executor reports are sanitized to a 12-char short id; a 12-char
  hex run can still be flagged by detect-secrets, so per-mission reports are not
  committed (only the clean batch report is committed).
- GitNexus analyze and detect_changes are run in the final validation step.

## Not merged

This branch is pushed isolated only. platform-dev is not merged and no product
branch is pushed.
