# P16-D Mission - Mission Queue / Batch Runner

- **Phase:** P16-D
- **Branch:** codex/platform-p16d-mission-queue-runner-2026-06-21
- **Base:** origin/platform-dev @ 75d0102 (not merged, not pushed)
- **Agent:** claude
- **Mode:** dry-run by default; `--execute` runs real worktrees + workers

## Goal

Upgrade the P16 worktree execution harness from single-mission execution to a
repeatable **batch / mission-queue** harness. `platform_worktree_batch_runner`
wraps `platform_worktree_executor` so the platform CTO can define an ordered
manifest of mission JSON files, run them sequentially inside isolated git
worktrees, stop safely on the first failure, and produce one auditable batch
report.

## Wrapper

scripts/platform_worktree_batch_runner.py - a governed batch runner that:

- accepts `--repo` and `--manifest <json>`;
- validates the manifest structure and the safety of every declared path
  (missions must be relative, traversal-free, and confined under
  `ai-ledger/platform/`; the batch report path is confined the same way and must
  end in `.json`, and the write is checked a second time by resolved-path
  containment so it can never escape the ledger);
- runs the missions **in order**, each through `platform_worktree_executor`
  (parse -> validate -> worktree -> worker -> audit -> report);
- defaults to **DRY-RUN** (validate + plan, no worktree, no worker);
- requires explicit `--execute` to run real missions;
- **stops on the first failure** by default (remaining missions recorded as
  `skipped`); `--continue-on-failure` runs the rest, but the aggregate verdict
  is still `failed` if any mission failed;
- writes one batch report JSON under `ai-ledger/platform/` recording each
  mission's verdict, report path, changed-file count, and failure reason, plus
  the aggregate verdict;
- never swallows worker failures (the executor's verdict is recorded verbatim
  and any failure forces a failed aggregate + non-zero exit).

Path/forbidden rules are reused from `platform_diff_auditor` (via the executor)
so the wrapper cannot drift from the canonical, regression-tested auditor.

## Deliverables (expected_files)

- scripts/platform_worktree_batch_runner.py
- scripts/test_platform_worktree_batch_runner.py
- ai-ledger/platform/2026-06-21_p16d_mission_queue_manifest.json
- ai-ledger/platform/2026-06-21_p16d_mission_queue_mission.md
- ai-ledger/platform/2026-06-21_p16d_mission_queue.md
- ai-ledger/platform/2026-06-21_p16d_smoke_success_a.json
- ai-ledger/platform/2026-06-21_p16d_smoke_failure.json
- ai-ledger/platform/2026-06-21_p16d_smoke_success_c.json
- ai-ledger/platform/2026-06-21_p16d_mission_queue_batch_report.json (generated)
- ai-ledger/platform/2026-06-21_p16d_mission_queue_evidence.json (sanitized)

## Batch report schema (machine)

- `aggregate_verdict`: `passed` only if every mission that ran passed.
- per mission: `order`, `mission` (path), `mode`, `verdict`
  (`passed`/`failed`/`skipped`), `report` (path), `changed_files` (int),
  `failure` (reason or null).
- The batch report stores NO 40-char git SHA (only integer counts and short
  reason strings) so it passes detect-secrets and is committed directly.

## Scope guards

- Forbidden prefixes (reused from platform_diff_auditor): backend/, frontend/,
  product-dev-recovered/, .github/, .claude/, docs/ai/.
- Forbidden keywords: auth, rbac, tenancy, migration, payment, session.
- Manifest mission paths and the batch report path confined to
  `ai-ledger/platform/`.
- Worker failure is never swallowed.
- The batch report path cannot escape `ai-ledger/platform/`.

## Validation gates

- python scripts/test_platform_worktree_batch_runner.py
- python scripts/test_platform_worktree_executor.py
- python scripts/test_platform_worktree_smoke_worker.py
- python scripts/test_platform_diff_auditor.py
- python scripts/test_platform_agent_mission_gate.py
- platform_worktree_batch_runner dry-run on the P16-D manifest
- platform_worktree_batch_runner --execute on the P16-D manifest (controlled)
- detect-secrets scan of committed JSON/ledger evidence
- git diff --check origin/platform-dev..HEAD
- npx gitnexus analyze
- GitNexus detect_changes compare vs origin/platform-dev
- forbidden path audit over origin/platform-dev..HEAD
- git status --short must be clean

## Stop conditions

- any runtime/product/backend/frontend/auth/migration/payment path appears
- the batch runner reports PASS while a mission failed
- unexpected or forbidden mission output is treated as success
- the batch report path escapes ai-ledger/platform/
- raw untracked report artifacts remain
- GitNexus HIGH/CRITICAL product/runtime impact (harness-only is fine)
