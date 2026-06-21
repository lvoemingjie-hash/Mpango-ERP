# P16-C Mission - Real Worktree Smoke

- **Phase:** P16-C
- **Branch (worker):** codex/platform-p16c-smoke-worker-2026-06-21
- **Base ref:** HEAD (codex/platform-p16c-real-worktree-smoke-2026-06-21 foundation commit, rooted at origin/platform-dev @ 31b2fc7)
- **Agent:** claude
- **Mode:** execute (a real worker runs in a real isolated worktree)

## Goal

Prove the newly merged platform_worktree_executor can run a real governed worker
mission in an isolated git worktree, catch committed/staged/unstaged/untracked
changes, and produce auditable completion evidence. This is the first slice that
exercises `--execute` end to end with a non-trivial worker that commits its output.

## Worker

scripts/platform_worktree_smoke_worker.py - a minimal, safe worker that:

- writes exactly ONE caller-supplied, allowlisted output path;
- rejects absolute, traversal, unsafe-part, forbidden, and non-allowlisted paths
  (reusing platform_diff_auditor's canonical rules);
- with `--commit` commits the output in the worktree so the executor's
  committed-change audit (diff base_sha..HEAD) is exercised.

## Deliverables (expected_files)

- scripts/platform_worktree_smoke_worker.py
- scripts/test_platform_worktree_smoke_worker.py
- ai-ledger/platform/2026-06-21_p16c_real_worktree_smoke_mission.json
- ai-ledger/platform/2026-06-21_p16c_real_worktree_smoke_mission.md

## Mission contract (machine)

- expected_files: exactly the worker output (scripts/p16c_smoke_worker_output.json).
- The worker output is ephemeral: it lives only inside the temporary worktree,
  which the executor removes in its `finally` block. The durable evidence is the
  completion report written under ai-ledger/platform/.

## Scope guards

- Forbidden prefixes (reused from platform_diff_auditor): backend/, frontend/,
  product-dev-recovered/, .github/, .claude/, docs/ai/.
- Forbidden keywords: auth, rbac, tenancy, migration, payment, session.
- Worker output confined to allowlisted prefixes (scripts/, ai-ledger/platform/).
- Completion report path confined to ai-ledger/platform/ and must end in .json.
- Worker command failure is never swallowed.

## Validation gates

- python scripts/test_platform_worktree_executor.py
- python scripts/test_platform_worktree_smoke_worker.py
- python scripts/test_platform_diff_auditor.py
- python scripts/test_platform_agent_mission_gate.py
- platform_worktree_executor --execute against this mission (verdict == passed)
- adversarial smoke case: committed forbidden file still fails (P16-A/B-R1 test)
- git diff --check origin/platform-dev..HEAD
- npx gitnexus analyze
- GitNexus detect_changes compare vs origin/platform-dev
- forbidden path audit over origin/platform-dev..HEAD

## Stop conditions

- any runtime/product/backend/frontend/auth/migration/payment path appears
- the executor passes with unexpected or forbidden files
- worker failure is swallowed
- the completion report escapes ai-ledger/platform/
- GitNexus reports HIGH/CRITICAL product/runtime impact (harness-only is fine)
