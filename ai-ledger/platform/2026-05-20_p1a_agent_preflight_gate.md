# Phase P1-A: Agent Preflight Gate

**Date:** 2026-05-20
**Branch:** `codex/platform-p1-agent-preflight-2026-05-20` based on `origin/platform-dev`
**Head commit:** `cad9a9f4e7a6b23ffe68cd6b6b006c03a982adc1` (pushed; not merged to `platform-dev`)
**Agent:** Opencode execution, reviewed by Codex Platform CTO
**Status:** COMPLETE for implementation draft; branch is pushed to remote only, not merged to `platform-dev`. Phase P1-A.1 below supersedes the original branch-policy behavior.

## Scope

Create a standard-library Python preflight checker that validates a platform-track agent's operating environment before implementation.

Deliverables:

1. `scripts/platform_agent_preflight.py` - preflight checker
2. `scripts/test_platform_agent_preflight.py` - unit tests
3. `ai-ledger/platform/2026-05-20_p1a_agent_preflight_gate.md` - this ledger

The checker verifies:

- Branch is `platform-dev` or starts with `codex/platform-`.
- Required shared-memory docs exist.
- Staged, unstaged, and untracked changed files avoid forbidden paths and fragments.
- Optional report field validation works via `--report PATH`.
- `--require-report` fails when no report path is provided.

## Files Changed

| File | Operation |
|------|-----------|
| `scripts/platform_agent_preflight.py` | new |
| `scripts/test_platform_agent_preflight.py` | new |
| `ai-ledger/platform/2026-05-20_p1a_agent_preflight_gate.md` | new |

No existing files or indexed symbols were modified.

## Implementation Evidence

### `scripts/platform_agent_preflight.py`

Python 3 script using only standard library modules: `argparse`, `os`, `subprocess`, `sys`, and `pathlib`.

Key functions:

| Function | Purpose |
|----------|---------|
| `run_git()` | Runs git commands via subprocess with timeout |
| `get_current_branch()` | Returns active branch name |
| `get_current_commit()` | Returns HEAD commit hash |
| `get_changed_files()` | Returns staged, unstaged, and untracked files |
| `is_forbidden_path()` | Checks forbidden prefixes, specific paths, and path/name fragments |
| `check_branch()` | Validates platform branch naming |
| `check_required_docs()` | Validates the six shared-memory docs exist |
| `check_changed_files()` | Validates changed paths do not cross forbidden boundaries |
| `validate_report()` | Validates required report fields |

Command-line interface:

```bash
python scripts/platform_agent_preflight.py [--repo PATH] [--report PATH] [--require-report]
```

Forbidden path checks:

- Prefixes: `backend/`, `frontend/`, `.github/workflows/`, `.claude/`
- Specific path: `docs/ai/PHASE4_FRONTEND_CONTRACT.md`
- Path/name fragments: `auth`, `rbac`, `tenancy`, `session`, `migration`, `payment`

Report fields validated:

- branch
- commit
- modified files
- tests
- report path
- risk

### `scripts/test_platform_agent_preflight.py`

Unit tests use only `unittest`, `tempfile`, and other standard-library modules. They require no network, database, backend, frontend, or pytest dependency.

Test coverage includes:

- valid platform branch with required docs passes
- invalid branch fails
- missing required doc fails
- forbidden changed path fails
- forbidden fragments and prefixes are detected
- Windows and Unix path normalization
- report field validation passes and fails
- `--require-report` without `--report` fails
- relative report paths resolve from `--repo`

## Test Evidence

```text
python scripts/test_platform_agent_preflight.py
Ran 31 tests in 2.970s
OK
```

Real-repo self-check:

```text
python scripts/platform_agent_preflight.py --repo . --report ai-ledger/platform/2026-05-20_p1a_agent_preflight_gate.md
VERDICT: PASS - All preflight checks passed
Branch: codex/platform-p1-agent-preflight-2026-05-20
Commit: cad9a9f4e7a6b23ffe68cd6b6b006c03a982adc1
```

Diff/check evidence:

```text
git diff --name-status
A       ai-ledger/platform/2026-05-20_p1a_agent_preflight_gate.md
A       scripts/platform_agent_preflight.py
A       scripts/test_platform_agent_preflight.py

git diff --check
PASS
```

Forbidden path audit:

```text
PASS: changed paths avoid forbidden runtime paths
```

GitNexus staged detect_changes:

```text
changed_files: 3
changed_count: 49
affected_count: 4
risk_level: medium
affected_processes:
- Main -> Add_pass
- Main -> Add_fail
- Main -> Run_git
- Main -> Normalize_path
```

Interpretation: the affected processes are the new preflight CLI's own execution flows. No product, backend, frontend, auth/RBAC/tenancy, migration, payment, GitHub workflow, or docs/ai shared-memory runtime path is affected.

## GitNexus Note

All changes are new files only. No existing functions, classes, or methods were modified. GitNexus impact analysis against an existing symbol was therefore not applicable before editing. GitNexus `detect_changes` must still run before commit.

## CTO Instruction Compliance Check

| CTO instruction | Implementation evidence | Test evidence | Status |
|----------------|-------------------------|---------------|--------|
| Name the phase | Ledger and final report use `Phase P1-A: Agent Preflight Gate` | Phase name appears in this ledger | PASS |
| Use opencode to begin execution | Opencode created the implementation draft | Opencode final report captured files and checks | PASS |
| Create `scripts/platform_agent_preflight.py` | File created | self-check runs the script successfully | PASS |
| Create `scripts/test_platform_agent_preflight.py` | File created | 31 unittest tests pass | PASS |
| Create a platform ledger | This file created under `ai-ledger/platform/` | report validation checks required fields | PASS |
| Accept `--repo PATH` | CLI supports `--repo` | temp repo tests and real-repo self-check pass | PASS |
| Validate allowed branch names | `check_branch()` enforces `codex/platform-*` by default; `platform-dev` only with `--allow-platform-dev` | valid and invalid branch tests pass; platform-dev default-fail + flag-pass tests added | PASS |
| Validate six shared-memory docs | `check_required_docs()` enforces required docs | valid and missing-doc tests pass | PASS |
| Reject forbidden changed paths | `is_forbidden_path()` and `check_changed_files()` enforce forbidden prefixes/fragments | forbidden path tests pass | PASS |
| Validate report fields | `validate_report()` checks all six required fields | report validation tests pass | PASS |
| Support `--require-report` | CLI fails early when required report is missing | CLI test passes | PASS |
| Use standard library only | Script and tests import only standard-library modules | tests run without external dependencies | PASS |
| Do not modify existing symbols before impact | Only new files were added | `git diff --name-status` shows only added files | PASS |
| Do not touch runtime/product paths | No backend/frontend/.github/.claude/docs/ai runtime paths changed | forbidden path audit passes | PASS |
| Do not commit or push during opencode execution | Opencode stopped before commit for Phase P1-A and Phase P1-A.1; commits and pushes are performed by CTO after gates pass | Branch is pushed only, not merged to `platform-dev` | PASS |

## Counterexample Check

| Counterexample | Expected behavior | Test coverage |
|----------------|-------------------|---------------|
| Agent starts on `feature/foo` | Preflight fails because branch is not platform-approved | invalid branch test |
| A report omits `commit` or `risk` | Preflight fails report validation | missing report fields test |
| A platform branch modifies `backend/` | Preflight fails even though branch is allowed | forbidden changed path test |
| A path contains `auth`, `rbac`, `tenancy`, `session`, `migration`, or `payment` | Preflight fails on fragment detection | fragment tests |
| Shared-memory docs are missing | Preflight fails before implementation | missing doc test |
| `--require-report` is set without `--report` | CLI exits nonzero | require-report CLI test |

## Phase P1-A.1 Revision (Branch Policy Tightening)

**Date:** 2026-05-20
**Starting commit:** `cad9a9f4e7a6b23ffe68cd6b6b006c03a982adc1`
**Final branch head:** Recorded in the CTO handoff report after commit/push, because the commit hash cannot be embedded in the content before the commit exists.
**Status:** Completed on the same isolated branch; branch pushed only, not merged to `platform-dev`.

### Changes

1. **`check_branch()` now defaults to `codex/platform-*` only.** The `platform-dev` branch is no longer accepted by default. A new `--allow-platform-dev` CLI flag explicitly enables it, with a clear failure message otherwise.
2. **New tests added:**
   - `TestPlatformDevBranchPolicy.test_platform_dev_fails_by_default`: verifies `platform-dev` without flag fails
   - `TestPlatformDevBranchPolicy.test_platform_dev_passes_with_allow_flag`: verifies `platform-dev` with `allow_platform_dev=True` passes
   - `TestPlatformDevBranchPolicy.test_codex_platform_branch_still_passes_by_default`: verifies `codex/platform-*` still passes without flag
   - `TestCliReportBehavior.test_platform_dev_without_flag_fails_cli`: CLI-level check
   - `TestCliReportBehavior.test_platform_dev_with_flag_passes_cli`: CLI-level check
3. **Ledger corrected:** Previous stale base/head wording was replaced with the pushed P1-A starting commit `cad9a9f`. Branch is noted as pushed only, not merged to `platform-dev`.

### Impact Evidence

`check_branch` was the only modified symbol. Its callers are:
- `main()` in `platform_agent_preflight.py`: updated to pass `allow_platform_dev`
- Two unit test methods: updated/extended via new test classes

**Impact assessment:** LOW. All changes are self-contained within the three allowed files. No product code, auth/RBAC/tenancy/session/migration/payment paths, or CI/CD workflows are affected.

### P1-A.1 Validation Evidence

```text
python scripts/test_platform_agent_preflight.py
Ran 36 tests in 5.556s
OK

python scripts/platform_agent_preflight.py --repo . --report ai-ledger/platform/2026-05-20_p1a_agent_preflight_gate.md
VERDICT: PASS - All preflight checks passed

git diff --cached --check
PASS

GitNexus detect_changes(scope=staged)
changed_files: 3
changed_count: 49
affected_count: 4
risk_level: medium
affected_processes:
- Main -> Add_pass
- Main -> Add_fail
- Main -> Run_git
- Main -> Normalize_path
```

Interpretation: staged GitNexus risk remains MEDIUM because the preflight CLI's own execution flows are modified. No product, backend, frontend, auth/RBAC/tenancy, migration, payment, GitHub workflow, `.claude`, or `docs/ai` path is affected.

### P1-A.1 Counterexamples

| Counterexample | Expected behavior | Test coverage |
|----------------|-------------------|---------------|
| Agent on `platform-dev` without flag | Preflight fails: "not allowed by default" | `test_platform_dev_fails_by_default` |
| Agent on `platform-dev` with `--allow-platform-dev` | Preflight passes | `test_platform_dev_passes_with_allow_flag` |
| Agent on `codex/platform-*` | Preflight passes as before | `test_codex_platform_branch_still_passes_by_default` |

## Completion Claim

**COMPLETE for Phase P1-A implementation draft (revised P1-A.1).** The preflight checker, unit tests, and ledger are present and validated locally. Branch policy tightened: `platform-dev` requires `--allow-platform-dev`. No existing symbols outside the three allowed files were modified. No product/runtime paths were touched. The branch is pushed only and not merged to `platform-dev`.
