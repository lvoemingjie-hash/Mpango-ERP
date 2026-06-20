# Platform Worktree Execution Harness (P16-A/B + R1)

- **Branch:** codex/platform-p16a-worktree-harness-2026-06-20
- **Foundation commit:** e2b559e
- **R1 commit:** 06fed2d
- **Final HEAD:** 049ccce
- **Base:** codex/platform-p15bcd-incident-triage-batch-2026-06-14 @ 2211512
- **Generated output path:** ai-ledger/platform/2026-06-20_p16_worktree_execution_harness.md

## Goal

First platform worktree execution harness: run CTO-defined missions in isolated git worktrees with machine-readable scope, forbidden paths, validation gates, stop conditions, and completion reports. Default mode is dry-run; this slice executes no risky worker.

## R1 - Immutable Base SHA Audit (committed-change bypass fix)

Review found that execute() created the worktree and audited against the symbolic base_ref (HEAD). A worker that COMMITTED a forbidden file (e.g. backend/evil.txt) advanced the worktree HEAD, so the audit diff HEAD..HEAD was empty and the committed forbidden file bypassed detection. R1 closes this:

- execute() resolves base_ref to an immutable commit SHA (base_sha) via git rev-parse --verify base_ref^{commit} in the parent repo BEFORE worktree creation. Unresolved base_ref fails the executor.
- git worktree add and the post-run audit both use base_sha (diff base_sha..HEAD), so committed changes are always surfaced.
- collect_changed_files now covers committed (base_sha..HEAD), staged, unstaged, and untracked files.
- Completion report records base_ref, base_sha, audit_command, changed_files, verdict.

## Files in branch vs base 2211512

- scripts/platform_worktree_executor.py - harness (P16) + R1 immutable base_sha.
- scripts/test_platform_worktree_executor.py - 38 unittest cases (34 P16 + 4 R1).
- ai-ledger/platform/2026-06-20_p16_worktree_execution_harness_mission.json - machine mission contract.
- ai-ledger/platform/2026-06-20_p16_worktree_execution_harness_mission.md - human mission.
- ai-ledger/platform/2026-06-20_p16_worktree_execution_harness.md - this report.

## Design invariants (stop conditions)

- Forbidden prefixes/keywords reused verbatim from platform_diff_auditor (backend/, frontend/, product-dev-recovered/, .github/, .claude/, docs/ai/; auth, rbac, tenancy, migration, payment, session). No runtime product/backend/frontend path is touched.
- Post-run audit: any changed file that is forbidden OR outside expected_files forces FAIL. Committed, staged, unstaged, and untracked files are all checked.
- Worker failure is never swallowed: non-zero exit -> verdict failed + non-zero process exit.
- Completion report path validated relative, traversal-free, under ai-ledger/platform/, ending .json. Cannot escape the ledger.

## Verification (R1)

- python scripts/test_platform_worktree_executor.py: PASS, 38 tests
- python scripts/test_platform_diff_auditor.py: PASS, 37 tests (regression)
- python scripts/test_platform_agent_mission_gate.py: PASS, 62 tests (regression)
- platform_diff_auditor.audit_files on the 5 branch files: PASS, 0 violations
- git diff --check 2211512..HEAD: PASS (rc 0, no whitespace errors)
- npx gitnexus analyze: PASS, 6645 nodes / 19993 edges / 436 clusters / 300 flows (re-indexed after R1 commit)
- committed-change bypass test: a worker that commits backend/evil.txt (leaving allowlisted allowed.txt uncommitted) now correctly FAILs.

## Report Fields

- **Branch:** codex/platform-p16a-worktree-harness-2026-06-20
- **Commit:** e2b559e (foundation) + 06fed2d (R1 immutable base SHA) + 049ccce (final HEAD)
- **Modified files:** scripts/platform_worktree_executor.py, scripts/test_platform_worktree_executor.py, ai-ledger/platform/2026-06-20_p16_worktree_execution_harness_mission.json, ai-ledger/platform/2026-06-20_p16_worktree_execution_harness_mission.md, ai-ledger/platform/2026-06-20_p16_worktree_execution_harness.md (5 files added vs base 2211512)
- **Tests:** 38 / 38 new; 99 / 99 regression (diff_auditor 37 + mission_gate 62)
- **Report path:** ai-ledger/platform/2026-06-20_p16_worktree_execution_harness.md
- **Risk:** MEDIUM (harness-only). MEDIUM because this is the load-bearing control plane that turns human relay into automated execution, so its audit gates must hold under adversarial worker behavior. R1 specifically fixes the committed-change bypass; the remaining surface (worktree creation is the only git mutation, default dry-run) is bounded and tested. No product/backend/frontend/auth/migration/payment code touched.

## Notes

- git worktree add / git status cannot be invoked directly by the agent this session (dontAsk allowlist); the executor runs git internally via subprocess, and changed-file scope was verified via git diff --name-only and git show --stat against the immutable base.
- detect_changes compare is an MCP-only GitNexus tool not exposed in this headless session; scope was verified equivalently via git diff --name-only 2211512..HEAD plus the forbidden-path audit (5 files, all under scripts/ and ai-ledger/platform/).
- Worktree branch created from the p15bcd worktree HEAD; the p15bcd branch itself is untouched. platform-dev NOT merged (per instruction).
