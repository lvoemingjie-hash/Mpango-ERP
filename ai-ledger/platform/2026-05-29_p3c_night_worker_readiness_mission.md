# P3-C Night Run: Worker Reliability & Batch Readiness Packet

## Scope

You are opencode working under the Mpango platform CTO harness.

Create a CTO-facing batch readiness packet for the stacked P3-A/P3-B platform work. This is a platform governance/evidence task only.

Do not edit backend, frontend, product runtime, auth, RBAC, tenancy, session, migration, payment, `.github`, `.claude`, or `docs/ai`.

## Required Work

Modify only:

- `ai-ledger/platform/2026-05-29_p3c_night_worker_readiness_packet.md`

The packet must summarize:

1. Stack under review:
   - P3-A: `codex/platform-p3a-governed-harness-index-2026-05-28`
   - P3-B: `codex/platform-p3b-opencode-timeout-evidence-2026-05-29`
   - Current P3-C branch: `codex/platform-p3c-night-worker-readiness-2026-05-29`
2. Base:
   - `origin/platform-dev`
3. The actual changed files from `origin/platform-dev..HEAD`.
4. The actual changed files from `origin/codex/platform-p3b-opencode-timeout-evidence-2026-05-29..HEAD`.
5. Worker reliability findings:
   - P3-A opencode timed out after 900s and produced partial files.
   - P3-B opencode was invoked twice; it did not produce result JSON/code changes, so CTO completed the hardening.
   - P3-B now sanitizes opencode event output and writes partial timeout result JSON.
6. Test plan for tomorrow:
   - P3-A/B/P3-C focused tests
   - P1/P2 critical regression tests
   - `git diff --check`
   - forbidden path audit
   - `npx gitnexus analyze`
   - GitNexus compare vs `origin/platform-dev`
   - runner smoke only after CTO approves merge
7. CTO Instruction Compliance Check.
8. Counterexample Check.
9. Completion Claim as `COMPLETE` only if the packet is written and the task stays docs-only.

## Suggested Commands

Use read-only git commands to gather evidence:

```powershell
git branch --show-current
git rev-parse HEAD
git diff --name-status origin/platform-dev..HEAD
git diff --name-status origin/codex/platform-p3b-opencode-timeout-evidence-2026-05-29..HEAD
```

You may also use:

```powershell
python scripts/platform_batch_review_packet.py --repo . --base-ref origin/platform-dev --output ai-ledger/platform/2026-05-29_p3c_night_worker_readiness_packet.md --risk HIGH --phase "P3-A Governed Harness Index" --phase "P3-B Opencode Timeout Evidence Hygiene" --phase "P3-C Night Worker Readiness Packet"
```

If you use the script, revise the generated packet so the title and evidence accurately say P3-C, not P1-G.

## Validation Commands

Run:

```powershell
git diff --check
git status --short
```

## Required Result JSON

Write `ai-ledger/platform/2026-05-29_p3c_opencode_result.json`:

```json
{
  "status": "done",
  "files_changed": [
    "ai-ledger/platform/2026-05-29_p3c_night_worker_readiness_packet.md"
  ],
  "test_result": "git diff --check: PASS; git status --short: only expected P3-C packet/result/events"
}
```
