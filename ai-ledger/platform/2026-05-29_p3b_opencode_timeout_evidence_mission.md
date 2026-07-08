# P3-B Opencode Timeout Evidence Hygiene

## Scope

You are opencode working under the Mpango platform CTO harness.

Implement a small platform harness hardening slice only. Do not edit backend, frontend, product runtime, auth, RBAC, tenancy, session, migration, payment, `.github`, `.claude`, or `docs/ai`.

## Problem

P3-A showed that `scripts/platform_opencode_worker_gate.py` writes raw opencode JSONL stdout to the events path. On long or timed-out runs, that raw stream can contain high-entropy session/snapshot identifiers and cannot be committed because `detect-secrets` blocks it. The worker also exits on missing result JSON before leaving a useful structured partial result.

## Required Implementation

Modify only:

- `scripts/platform_opencode_worker_gate.py`
- `scripts/test_platform_opencode_worker_gate.py`
- `ai-ledger/platform/2026-05-29_p3b_opencode_timeout_evidence.md`

Requirements:

1. Events output must be sanitized JSONL, not raw opencode stdout.
   - The events file must contain valid JSON object lines.
   - Include summary fields such as event count, stdout byte count, stderr byte count, exit code, timed_out, elapsed seconds, and redacted=true.
   - Do not include raw session IDs, snapshots, or arbitrary stdout text.
2. On timeout with missing result JSON, write a valid partial result JSON to the requested result path.
   - `status`: `partial`
   - `files_changed`: actual changed files limited to expected files only
   - `test_result`: explain timeout
   - `blocker`: explain missing worker result after timeout
   - If actual changed files include unexpected files, keep final exit as failure and diagnostics must still mention unexpected files.
3. Preserve the existing return-code semantics:
   - success + status done => exit 0
   - timeout => exit 124
   - non-timeout failures => nonzero
4. Keep post-command actual changed file audit.
5. Add tests for:
   - timeout without result writes partial result JSON and exits 124
   - timeout events JSONL is sanitized and valid JSON
   - raw high-entropy/session-like stdout is not written to events
   - unexpected changed file on timeout still fails audit/diagnostics
   - successful worker still passes with sanitized events

## Validation Commands

Run:

```powershell
python scripts/test_platform_opencode_worker_gate.py
python scripts/test_platform_mission_worker_bridge.py
python scripts/test_platform_run_evidence_bundle.py
git diff --check
```

## Required Result JSON

Write `ai-ledger/platform/2026-05-29_p3b_opencode_result.json` with:

```json
{
  "status": "done",
  "files_changed": [
    "scripts/platform_opencode_worker_gate.py",
    "scripts/test_platform_opencode_worker_gate.py",
    "ai-ledger/platform/2026-05-29_p3b_opencode_timeout_evidence.md"
  ],
  "test_result": "python scripts/test_platform_opencode_worker_gate.py: PASS; python scripts/test_platform_mission_worker_bridge.py: PASS; python scripts/test_platform_run_evidence_bundle.py: PASS; git diff --check: PASS"
}
```

## Ledger Requirements

The ledger must include:

- Branch
- Commit placeholder as `pending`
- Modified files
- Test evidence
- GitNexus impact summary from CTO preflight: `run_worker` LOW, `platform_opencode_worker_gate.py main` context reviewed, `validate_result` context reviewed
- Risk: MEDIUM, platform harness only
- CTO Instruction Compliance Check
- Counterexample Check
- Completion Claim
