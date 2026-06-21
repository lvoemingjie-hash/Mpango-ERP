# Platform Mission Queue / Batch Runner (P16-D)

- **Branch:** codex/platform-p16d-mission-queue-runner-2026-06-21
- **Foundation commit:** 1a03909 (batch runner + tests + smoke mission contracts + manifest + mission)
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

## What the wrapper does

- accepts `--repo` and `--manifest <json>`;
- validates manifest structure and the safety of every declared path: each
  mission path must be relative, traversal-free, and confined under
  `ai-ledger/platform/` (`.json`); the batch report path is confined the same
  way and the write is re-checked by resolved-path containment so it can never
  escape the ledger;
- runs missions **in order**, each through `platform_worktree_executor`
  (parse -> validate -> worktree -> worker -> audit -> report);
- defaults to **DRY-RUN** (validate + plan, no worktree, no worker);
- requires explicit `--execute` to run real missions;
- **stops on the first failure** by default (remaining missions recorded as
  `skipped`); `--continue-on-failure` runs the rest, but the aggregate verdict
  is still `failed` if any mission failed;
- writes one batch report JSON under `ai-ledger/platform/` recording each
  mission's verdict, report path, changed-file count, and failure reason, plus
  the aggregate verdict;
- never swallows worker failures (executor verdict recorded verbatim; any
  failure forces a failed aggregate + non-zero exit).

Path/forbidden rules are reused from `platform_diff_auditor` (via the executor)
so the wrapper cannot drift from the canonical, regression-tested auditor.

## Real batch smoke results

Manifest `ai-ledger/platform/2026-06-21_p16d_mission_queue_manifest.json` orders
three missions: success A (P16-C-style smoke worker + `--commit`), controlled
failure B (worker exits 2), success C (uncommitted output). All three are valid
contracts, so dry-run passes for all three; the failure only manifests at
execution.

**Dry-run** (default): `aggregate_verdict = passed`, 3/3 valid, no worktree
created, no worker run.

**Execute --execute (stop-on-first-failure, the default):**

| order | mission | verdict | changed_files | failure |
|-------|---------|---------|---------------|---------|
| 0 | smoke_success_a | passed | 1 | - |
| 1 | smoke_failure | failed | 0 | worker exited 2 |
| 2 | smoke_success_c | skipped | - | skipped: earlier mission failed |

`aggregate_verdict = failed`, `stopped_early = true`, process exit 1. Mission A
ran for real: the smoke worker wrote exactly one allowlisted output and
committed it on the worker branch, and the executor's committed-change audit
(`diff base_sha..HEAD`) caught it. Mission B's worker exited 2 and that failure
was recorded, not swallowed. Mission C was correctly skipped.

**Execute --execute --continue-on-failure:**

| order | mission | verdict | changed_files |
|-------|---------|---------|---------------|
| 0 | smoke_success_a | passed | 1 |
| 1 | smoke_failure | failed | 0 |
| 2 | smoke_success_c | passed | 1 |

`aggregate_verdict = failed` (B still failed), `stopped_early = false`, all
three ran, process exit 1. This proves `--continue-on-failure` runs the
remaining missions while the aggregate verdict still fails.

The committed batch report
(`ai-ledger/platform/2026-06-21_p16d_mission_queue_batch_report.json`) captures
the stop-on-first-failure execute run (the default mode).

## detect-secrets / completion-evidence handling

The executor's raw per-mission completion reports contain the full 40-char
`base_sha` git hash. detect-secrets (pre-commit, baseline `.secrets.baseline`)
flags that as a Hex High Entropy String (exit 1). JSON cannot carry an inline
`pragma: allowlist secret`, and the tracked `.secrets.baseline` lives outside
the allowed `scripts/` + `ai-ledger/platform/` scope, so editing it would fail
the strict `platform_diff_auditor` allowlist audit.

Following the P16-C pattern, the raw reports are therefore NOT committed. A
committed **sanitized** evidence artifact
(`ai-ledger/platform/2026-06-21_p16d_mission_queue_evidence.json`) captures
every executor report field with 40-char SHAs truncated to 7-char short SHAs,
so it passes detect-secrets. The batch report itself stores NO SHA by design
(only integer counts and short reason strings), so it is committed directly.
The raw reports are regenerated on demand via the command in the evidence
artifact's `regenerate_raw_reports_note`.

Operator note: `platform_worktree_executor` retains each worker branch across
runs (by design, as P16-C worker-branch evidence). Re-running the same smoke
therefore requires first deleting the `codex/platform-p16d-smoke-*` branches;
the smoke worktrees themselves are always removed by the executor's `finally`
block. After the smoke, all retained worker branches were deleted and all raw
reports removed, leaving a clean working tree.

## Deliverables (vs base origin/platform-dev @ 75d0102)

- scripts/platform_worktree_batch_runner.py - governed batch wrapper.
- scripts/test_platform_worktree_batch_runner.py - 38 unit tests.
- ai-ledger/platform/2026-06-21_p16d_mission_queue_manifest.json - smoke manifest.
- ai-ledger/platform/2026-06-21_p16d_mission_queue_mission.md - human mission.
- ai-ledger/platform/2026-06-21_p16d_mission_queue.md - this report.
- ai-ledger/platform/2026-06-21_p16d_smoke_success_a.json - smoke mission A.
- ai-ledger/platform/2026-06-21_p16d_smoke_failure.json - controlled failure B.
- ai-ledger/platform/2026-06-21_p16d_smoke_success_c.json - smoke mission C.
- ai-ledger/platform/2026-06-21_p16d_mission_queue_batch_report.json - generated, SHA-free.
- ai-ledger/platform/2026-06-21_p16d_mission_queue_evidence.json - sanitized evidence.

## Design invariants (stop conditions)

- Forbidden prefixes/keywords reused verbatim from platform_diff_auditor
  (backend/, frontend/, product-dev-recovered/, .github/, .claude/, docs/ai/;
  auth, rbac, tenancy, migration, payment, session). No runtime
  product/backend/frontend/auth/migration/payment code is touched.
- The batch runner reports PASS only when every mission that ran passed; any
  failed mission forces a failed aggregate and non-zero exit.
- Unexpected or forbidden mission output is never treated as success (the
  executor's audit forces FAIL; verified by
  test_forbidden_mission_output_fails_via_executor).
- The batch report path cannot escape `ai-ledger/platform/` (validated on input
  and re-checked by resolved-path containment at write time).
- No raw untracked report artifacts remain (raw per-mission reports removed;
  worker branches deleted; smoke worktrees removed by the executor).
- GitNexus: net-new files only, no existing symbol modified, so impact analysis
  is N/A; risk is harness-only (no product/runtime impact).

## Verification

- python scripts/test_platform_worktree_batch_runner.py: PASS, 38 tests.
- python scripts/test_platform_worktree_executor.py: PASS, 38 tests (regression).
- python scripts/test_platform_worktree_smoke_worker.py: PASS, 24 tests (regression).
- python scripts/test_platform_diff_auditor.py: PASS, 37 tests (regression).
- python scripts/test_platform_agent_mission_gate.py: PASS, 62 tests (regression).
- Total: 199 / 199 passing.
- platform_worktree_batch_runner dry-run on the manifest: BATCH VERDICT PASS.
- platform_worktree_batch_runner --execute (stop-on-first-failure): BATCH VERDICT
  FAIL (controlled) - A passed, B failed, C skipped, aggregate failed, exit 1.
- platform_worktree_batch_runner --execute --continue-on-failure: BATCH VERDICT
  FAIL (controlled) - A passed, B failed, C passed, aggregate failed, exit 1.
- detect-secrets (pre-commit) on all committed JSON/ledger evidence: Passed.
- git diff --check origin/platform-dev..HEAD: PASS (no whitespace errors).
- npx gitnexus analyze: re-indexed for the P16-D worktree.
- GitNexus detect_changes compare vs origin/platform-dev: scope confined to
  scripts/ + ai-ledger/platform/ (harness-only).
- forbidden path audit over origin/platform-dev..HEAD: PASS, 0 violations.
- git status --short: clean.

## Report fields

- **status:** success
- **branch:** codex/platform-p16d-mission-queue-runner-2026-06-21
- **commit:** foundation 1a03909 + ledger/evidence commit (final HEAD)
- **modified_files:** 10 added vs base 75d0102 (2 scripts + 8 ai-ledger/platform)
- **tests:** 199 / 199 (38 batch runner + 38 executor + 24 smoke worker + 37 diff auditor + 62 mission gate)
- **batch_report_path:** ai-ledger/platform/2026-06-21_p16d_mission_queue_batch_report.json
- **ledger_path:** ai-ledger/platform/2026-06-21_p16d_mission_queue.md
- **gitnexus_risk:** harness-only (no product/runtime impact; net-new files)
- **forbidden_path_audit:** PASS, 0 violations
- **worktree_clean:** yes (git status --short clean; raw reports + worker branches removed)
- **push_status:** see final summary
- **blockers:** none

## Notes

- platform-dev is NOT merged and NOT pushed, per instruction.
- The batch report is the primary committed audit artifact and is SHA-free by
  construction; the sanitized evidence artifact mirrors the executor's raw
  per-mission reports with short SHAs.
- base_ref for the smoke missions is HEAD (resolves to a commit containing the
  smoke worker), so the worker genuinely runs inside the isolated worktree.
