# P3-A Governed Platform Task Trial: Harness Index

You are opencode acting as the platform worker for Mpango ERP.

## Scope

Implement a small platform harness index CLI. This is a platform-dev harness task only.

Modify only:

- `scripts/platform_harness_index.py`
- `scripts/test_platform_harness_index.py`
- `ai-ledger/platform/2026-05-28_p3a_platform_harness_index.md`
- `ai-ledger/platform/2026-05-28_p3a_opencode_result.json`

Do not modify product runtime, backend, frontend, auth, RBAC, tenancy, session, migration, payment, `.github`, `.claude`, or `docs/ai` files.

## Required Implementation

Create `scripts/platform_harness_index.py` using Python stdlib only.

CLI:

```bash
python scripts/platform_harness_index.py --repo . --output ai-ledger/platform/harness_index.md
```

Behavior:

- Validate `--output` as a safe relative path under `ai-ledger/platform/` ending `.md`.
- Reject absolute paths, Windows drive-qualified paths, empty path segments, `.`, and `..`.
- Reject forbidden output paths using the platform policy:
  - `backend/`
  - `frontend/`
  - `.github/`
  - `.claude/`
  - `docs/ai/PHASE4_FRONTEND_CONTRACT.md`
  - path fragments `auth`, `rbac`, `tenancy`, `session`, `migration`, `payment`
- Scan `scripts/` for platform harness scripts matching `platform_*.py`.
- Pair scripts with tests named `test_<script_name>.py` when present.
- Scan `ai-ledger/platform/` for `.md` ledgers.
- Write a markdown index including:
  - branch
  - commit
  - generated output path
  - harness script table with script path and test path or `MISSING`
  - platform ledger list
  - summary counts
  - report fields: branch, commit, modified files, tests, report path, risk

Create `scripts/test_platform_harness_index.py` using unittest and stdlib only.

Tests must cover at least:

- valid CLI writes an index and exits 0
- output outside `ai-ledger/platform/` fails
- absolute or drive-qualified output fails
- traversal or dot/empty path part fails
- forbidden output path fails
- script/test pairing identifies existing test file
- missing test is rendered as `MISSING`

Create ledger `ai-ledger/platform/2026-05-28_p3a_platform_harness_index.md` with:

- branch
- scope
- files changed
- opencode worker note
- test evidence placeholder or actual result
- forbidden path audit
- GitNexus placeholder
- risk MEDIUM until final CTO validation
- CTO Instruction Compliance Check
- at least two counterexamples
- report fields

After implementation, run:

```bash
python scripts/test_platform_harness_index.py
```

Finally write JSON result to `ai-ledger/platform/2026-05-28_p3a_opencode_result.json`:

```json
{
  "status": "done",
  "files_changed": [
    "scripts/platform_harness_index.py",
    "scripts/test_platform_harness_index.py",
    "ai-ledger/platform/2026-05-28_p3a_platform_harness_index.md"
  ],
  "test_result": "python scripts/test_platform_harness_index.py: PASS"
}
```

If blocked, set `status` to `failed` or `partial` and include `blocker`.
