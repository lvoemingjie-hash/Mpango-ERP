# Phase P1-A: Agent Preflight Gate

**Date:** 2026-05-20
**Branch:** `codex/platform-p1-agent-preflight-2026-05-20` based on `origin/platform-dev`
**Head commit:** `63dd3ed9db02514cbc35965b34ecbfbed81a6f8a`
**Agent:** Opencode execution, reviewed by Codex Platform CTO
**Status:** COMPLETE for implementation draft; commit/push remain under CTO control

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
Commit: 63dd3ed9db02514cbc35965b34ecbfbed81a6f8a
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
| Validate allowed branch names | `check_branch()` enforces `platform-dev` or `codex/platform-*` | valid and invalid branch tests pass | PASS |
| Validate six shared-memory docs | `check_required_docs()` enforces required docs | valid and missing-doc tests pass | PASS |
| Reject forbidden changed paths | `is_forbidden_path()` and `check_changed_files()` enforce forbidden prefixes/fragments | forbidden path tests pass | PASS |
| Validate report fields | `validate_report()` checks all six required fields | report validation tests pass | PASS |
| Support `--require-report` | CLI fails early when required report is missing | CLI test passes | PASS |
| Use standard library only | Script and tests import only standard-library modules | tests run without external dependencies | PASS |
| Do not modify existing symbols before impact | Only new files were added | `git diff --name-status` shows only added files | PASS |
| Do not touch runtime/product paths | No backend/frontend/.github/.claude/docs/ai runtime paths changed | forbidden path audit passes | PASS |
| Do not commit or push during opencode execution | Opencode stopped before commit/push | CTO retains commit/push control | PASS |

## Counterexample Check

| Counterexample | Expected behavior | Test coverage |
|----------------|-------------------|---------------|
| Agent starts on `feature/foo` | Preflight fails because branch is not platform-approved | invalid branch test |
| A report omits `commit` or `risk` | Preflight fails report validation | missing report fields test |
| A platform branch modifies `backend/` | Preflight fails even though branch is allowed | forbidden changed path test |
| A path contains `auth`, `rbac`, `tenancy`, `session`, `migration`, or `payment` | Preflight fails on fragment detection | fragment tests |
| Shared-memory docs are missing | Preflight fails before implementation | missing doc test |
| `--require-report` is set without `--report` | CLI exits nonzero | require-report CLI test |

## Completion Claim

**COMPLETE for Phase P1-A implementation draft.** The preflight checker, unit tests, and ledger are present and validated locally. No existing symbols were modified. No product/runtime paths were touched. No commit or push was performed by opencode.
