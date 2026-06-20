# P16-A/B Mission - Worktree Execution Harness Foundation

- **Phase:** P16-A/B
- **Branch:** codex/platform-p16a-worktree-harness-2026-06-20
- **Base ref:** HEAD (codex/platform-p15bcd-incident-triage-batch-2026-06-14 @ 2211512)
- **Agent:** claude
- **Mode:** dry-run (no risky worker executed in this slice)

## Goal

Create the first platform worktree execution harness so CTO-defined missions can run in isolated git worktrees with machine-readable scope, forbidden paths, validation gates, stop conditions, and completion reports.

## Deliverables (expected_files)

- scripts/platform_worktree_executor.py
- scripts/test_platform_worktree_executor.py
- ai-ledger/platform/2026-06-20_p16_worktree_execution_harness_mission.json
- ai-ledger/platform/2026-06-20_p16_worktree_execution_harness_mission.md

## Scope guards

- Forbidden prefixes (reused from platform_diff_auditor): backend/, frontend/, product-dev-recovered/, .github/, .claude/, docs/ai/.
- Forbidden keywords: auth, rbac, tenancy, migration, payment, session.
- Completion report path confined to ai-ledger/platform/ and must end in .json.
- Worker command failure is never swallowed; default mode is dry-run.

## Validation gates

- unit tests for the executor (parsing, command construction, post-run audit, forbidden blocking, dry-run, failure reporting, report writing)
- existing platform harness regression tests as appropriate
- git diff --check
- forbidden path audit
- npx gitnexus analyze
- GitNexus detect_changes compare

## Stop conditions

- any runtime product/backend/frontend path is touched
- executor can write outside expected_files
- worker command failure is swallowed
- report path can escape ai-ledger/platform/
- GitNexus reports unexpected product/runtime impact
