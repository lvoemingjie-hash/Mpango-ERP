# Platform Real Worktree Smoke (P16-C)

- **Branch:** codex/platform-p16c-real-worktree-smoke-2026-06-21
- **Final feature branch HEAD:** see R1 section (pushed to origin)
- **Foundation commit:** e3d31e2 (smoke worker + tests + mission)
- **Ledger commit:** 116007d (P16-C ledger); R1 commit adds the sanitized evidence + this update
- **Base:** origin/platform-dev @ 31b2fc7 (not merged, not pushed)
- **Worker branch:** codex/platform-p16c-smoke-worker-2026-06-21 @ 1eb44d6 (parent e3d31e2)
- **Completion evidence:** ai-ledger/platform/2026-06-21_p16c_real_worktree_smoke_evidence.json (committed sanitized report; the raw executor JSON is intentionally NOT committed — see R1)
- **Agent:** claude
- **Mode:** execute (a real worker ran in a real isolated worktree)

## Goal

Prove the newly merged platform_worktree_executor can run a real governed worker
mission in an isolated git worktree, catch committed/staged/unstaged/untracked
changes, and produce auditable completion evidence. This is the first slice that
exercises `--execute` end to end with a non-trivial worker that commits its output.

## Real execution summary

`platform_worktree_executor --execute` against this mission produced a `passed`
completion report. What the executor actually did, end to end:

1. Resolved `base_ref` HEAD to the immutable commit SHA e3d31e2 in the parent
   repo (the foundation commit that contains the smoke worker), closing the
   committed-change bypass from P16-A/B-R1.
2. Created a sibling worktree at `../platform-p16c-smoke-worker-2026-06-21`
   (branch `codex/platform-p16c-smoke-worker-2026-06-21`) checked out at e3d31e2.
3. Ran the smoke worker inside the worktree. The worker wrote exactly one
   allowlisted file (`scripts/p16c_smoke_worker_output.json`) and, because
   `--commit` was passed, committed it on the worker branch.
4. Audited ALL change categories (committed base_sha..HEAD, staged, unstaged,
   untracked) against `expected_files`. Exactly one file changed, zero
   violations/forbidden/unexpected/missing. The committed change WAS caught by
   `diff base_sha..HEAD`, proving the committed-change audit works on a real run.
5. Removed the worktree in its `finally` block, then wrote the completion report.

The worker's commit (1eb44d6 "P16-C smoke worker output") is retained on the
worker branch as durable git evidence that the worker genuinely executed and
committed. The worker output itself is ephemeral (it lived only inside the
temporary worktree, which the executor removed).

## Deliverables (in branch vs base 31b2fc7)

- scripts/platform_worktree_smoke_worker.py - minimal safe smoke worker.
- scripts/test_platform_worktree_smoke_worker.py - 24 unit tests for the worker.
- ai-ledger/platform/2026-06-21_p16c_real_worktree_smoke_mission.json - machine mission contract.
- ai-ledger/platform/2026-06-21_p16c_real_worktree_smoke_mission.md - human mission.
- ai-ledger/platform/2026-06-21_p16c_real_worktree_smoke.md - this report.

## Smoke worker contract

- Writes EXACTLY ONE caller-supplied, allowlisted output path.
- Rejects absolute, drive-qualified, traversal, empty/dot-segment, forbidden, and
  non-allowlisted paths (reuses platform_diff_auditor's canonical rules so it
  cannot drift from the auditor's boundary).
- `--commit` commits the output in the worktree to exercise the committed-change
  audit; uses a deterministic, attributable identity.
- Worker failure is never swallowed: any rejection or commit failure exits
  non-zero, which the executor records as a `failed` verdict.

## Design invariants (stop conditions)

- Forbidden prefixes/keywords reused verbatim from platform_diff_auditor
  (backend/, frontend/, product-dev-recovered/, .github/, .claude/, docs/ai/;
  auth, rbac, tenancy, migration, payment, session). No runtime
  product/backend/frontend/auth/migration/payment code is touched.
- The executor never treats a file outside `expected_files` as in-scope; any
  changed file that is forbidden OR outside expected_files forces FAIL.
- Committed, staged, unstaged, and untracked files are all checked.
- Worker failure is never swallowed.
- Completion report path is validated relative, traversal-free, confined under
  ai-ledger/platform/, ending in .json. Cannot escape the ledger.

## Verification

- python scripts/test_platform_worktree_executor.py: PASS, 38 tests (incl. the
  4 immutable-base-sha audit tests).
- python scripts/test_platform_worktree_smoke_worker.py: PASS, 24 tests.
- python scripts/test_platform_diff_auditor.py: PASS, 37 tests (regression).
- python scripts/test_platform_agent_mission_gate.py: PASS, 62 tests (regression).
- Total: 161 / 161 passing.
- platform_worktree_executor --execute on the P16-C mission: verdict **passed**,
  1 changed file, 0 violations/forbidden/unexpected/missing.
- Adversarial case: TestImmutableBaseShaAudit.test_committed_forbidden_file_fails
  confirms a worker that commits backend/evil.txt is correctly FAILED and listed
  under audit.forbidden (committed-change bypass closed).
- git diff --check origin/platform-dev..HEAD: PASS (no whitespace errors).
- npx gitnexus analyze: re-indexed (see GitNexus section).
- GitNexus detect_changes compare vs origin/platform-dev: scope confined to
  scripts/ + ai-ledger/platform/ (harness-only).
- forbidden path audit over origin/platform-dev..HEAD: PASS, 0 violations (all
  files under allowed prefixes).

## GitNexus

- The P16-C slice adds one new worker module + its tests + ledger/mission docs.
  No existing symbol is modified; impact analysis is N/A for net-new files.
- detect_changes compare vs origin/platform-dev shows only the 5 new files, all
  under scripts/ and ai-ledger/platform/. No product/backend/frontend/auth path.
- Risk: MEDIUM (harness-only). MEDIUM because the worktree executor is the
  load-bearing control plane that turns human relay into automated execution, so
  its audit gates must hold under adversarial worker behavior. The committed-
  change audit is exercised for real here and holds. No GitNexus HIGH/CRITICAL
  product/runtime impact.

## Report fields

- **Branch:** codex/platform-p16c-real-worktree-smoke-2026-06-21
- **Commit:** e3d31e2 (foundation) + 116007d (P16-C ledger) + R1 commit (sanitized evidence + this update; final HEAD)
- **Worker branch:** codex/platform-p16c-smoke-worker-2026-06-21 @ 1eb44d6 (retained)
- **Executor report:** RAW report (ai-ledger/platform/2026-06-21_p16c_real_worktree_smoke_report.json) intentionally NOT committed (detect-secrets); COMMITTED sanitized copy at ai-ledger/platform/2026-06-21_p16c_real_worktree_smoke_evidence.json (verdict passed, base_sha e3d31e2)
- **Modified files:** 6 added vs base 31b2fc7 (worker, worker tests, mission json, mission md, ledger, sanitized evidence) - all under scripts/ and ai-ledger/platform/
- **Tests:** 161 / 161 (38 executor + 24 smoke worker + 37 diff auditor + 62 mission gate)
- **gitnexus_risk:** MEDIUM (harness-only; no product/runtime impact)
- **forbidden_path_audit:** PASS, 0 violations
- **worktree_clean:** yes (git status --short clean; raw report removed)
- **push:** origin/codex/platform-p16c-real-worktree-smoke-2026-06-21
- **blockers:** none

## Temporary worker branch / worktree status

- Worktree `../platform-p16c-smoke-worker-2026-06-21`: removed by the executor's
  `finally` block (verified: not present, not registered in `git worktree list`).
- Worker branch `codex/platform-p16c-smoke-worker-2026-06-21`: retained @ 1eb44d6
  as durable evidence of the worker's real commit. It is a sibling of the feature
  branch (parent e3d31e2), not an ancestor of HEAD, so it does not appear in
  `git diff origin/platform-dev..HEAD` and does not affect the scope audit.

## R1 - Completion Evidence Cleanup + Push

P16-C-R1 closes the loose end from the initial slice: the executor's raw
completion report could not be committed (detect-secrets), leaving an untracked
file and a non-clean working tree. R1 resolves this with a committed sanitized
evidence artifact and pushes the branch.

- **Final feature branch HEAD:** the R1 commit (this update + the sanitized
  artifact). Resolved and stated exactly in the R1 commit / push output.
- **Is the executor JSON committed?** No. The RAW executor report
  (ai-ledger/platform/2026-06-21_p16c_real_worktree_smoke_report.json) is
  intentionally NOT committed. A COMMITTED sanitized copy lives at
  ai-ledger/platform/2026-06-21_p16c_real_worktree_smoke_evidence.json, which
  records every executor report field with 40-char SHAs truncated to 7-char
  short SHAs so it passes detect-secrets.
- **Exact command to regenerate the raw report:**
  `python scripts/platform_worktree_executor.py --repo . --mission ai-ledger/platform/2026-06-21_p16c_real_worktree_smoke_mission.json --execute`
  (deterministic for a given base_sha; recreates the report under
  ai-ledger/platform/). It is regenerated during validation but not committed.
- **detect-secrets reason (raw report not committed):** pre-commit detect-secrets
  (baseline .secrets.baseline) flags the raw report's full `base_sha` git-hash as
  a Hex High Entropy String (exit 1). JSON cannot carry an inline
  `pragma: allowlist secret`, and the tracked `.secrets.baseline` lives outside
  the allowed scripts/ + ai-ledger/platform/ scope, so editing it would fail the
  strict platform_diff_auditor allowlist audit. The sanitized artifact sidesteps
  this by truncating SHAs; it was verified detect-secrets-clean (0 findings) and
  contains no 40-char hex.
- **Worktree clean at finish:** yes. `git status --short` is clean (no untracked
  report; the raw report was removed after its fields were captured into the
  sanitized artifact). The temporary smoke worktree was already removed by the
  executor; the worker branch is retained as evidence (see below).
- **Push:** branch pushed to origin/codex/platform-p16c-real-worktree-smoke-2026-06-21.
  platform-dev is NOT merged and NOT pushed.

## Notes

- The raw executor completion report is intentionally NOT committed (detect-secrets
  Hex High Entropy false positive on the full base_sha git-hash; the only allowlist
  is the tracked .secrets.baseline, which is outside the allowed scope). A committed
  sanitized evidence artifact captures its fields with short SHAs; the raw report is
  regenerated on demand via the command in the R1 section. See [[R1]] above.
- base_ref is HEAD (the foundation commit e3d31e2), not origin/platform-dev, so
  the worktree contains the smoke worker and it runs genuinely in isolation.
  The feature branch is rooted at origin/platform-dev @ 31b2fc7.
- platform-dev is NOT merged and NOT pushed, per instruction.
