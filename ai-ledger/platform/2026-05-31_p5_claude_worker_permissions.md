# P5 Claude Worker Permission Policy

Date: 2026-05-31
Lane: platform-dev / automation / runner / platform infra
Branch: codex/platform-p5-claude-worker-permissions-2026-05-31
Status: proposed worker invocation policy; isolated branch only, not merged to platform-dev

## Required Report Fields

| Field | Value |
|-------|-------|
| branch | `codex/platform-p5-claude-worker-permissions-2026-05-31` |
| commit | Pending before final commit; final commit is recorded in CTO report |
| modified files | `ai-ledger/platform/2026-05-31_p5_claude_worker_permissions.md` |
| tests | `git diff --check`; forbidden path audit; GitNexus detect_changes |
| report path | `ai-ledger/platform/2026-05-31_p5_claude_worker_permissions.md` |
| risk | LOW, docs-only permission policy for external worker invocation |

## Decision

Claude Code may be given non-interactive worker permissions for P5 platform
infra tasks, but only inside an isolated worktree/branch and only within the
P5 allowed platform surfaces.

This policy does not grant merge authority. Claude may implement, test, commit,
and optionally push an isolated branch. Codex Platform CTO still reviews before
any merge to `platform-dev`.

## Recommended Claude Invocation

Use this mode for P5-B/C/D long tasks when Jeff wants Claude to avoid repeated
confirmation prompts:

```bash
claude --bare -p "$(cat .missions/features/P5X_<name>.md)" \
  --append-system-prompt "$(cat .missions/knowledge_base.md)" \
  --allowedTools "Read,Write,Edit,MultiEdit,Bash" \
  --permission-mode bypassPermissions \
  --output-format json \
  --json-schema '{
    "type": "object",
    "required": [
      "status",
      "branch",
      "commit",
      "files_changed",
      "test_result",
      "report_path",
      "risk",
      "forbidden_path_audit",
      "gitnexus"
    ],
    "properties": {
      "status": {"type": "string", "enum": ["done", "failed", "partial"]},
      "branch": {"type": "string"},
      "commit": {"type": "string"},
      "files_changed": {"type": "array", "items": {"type": "string"}},
      "test_result": {"type": "string"},
      "report_path": {"type": "string"},
      "risk": {"type": "string"},
      "forbidden_path_audit": {"type": "string"},
      "gitnexus": {"type": "string"},
      "blocker": {"type": "string"}
    }
  }' > .missions/features/P5X_<name>_result.json
```

If the installed Claude Code build rejects `bypassPermissions`, use the fallback:

```bash
--permission-mode acceptEdits
```

Do not remove `--bare`. Clean context is part of the governance contract.

## Worker Scope

Claude may work on P5 platform infra / automation / runner / harness tooling
only.

Allowed by default:

- `scripts/platform_*.py`
- `scripts/test_platform_*.py`
- `ai-ledger/platform/*.md`
- `ai-ledger/platform/*.json`
- `ai-ledger/platform/*.jsonl`

Forbidden by default:

- `backend/`
- `frontend/`
- `product-dev-recovered/`
- `.github/`
- `.claude/`
- `docs/ai/`
- any path containing auth, RBAC, tenancy, tenant, migration, payment, or session concerns
- product business code

## Required Worker Gates

Every Claude P5 slice must:

1. Start from a clean isolated branch/worktree.
2. Run `git fetch --all --prune` before implementation.
3. Run GitNexus impact before editing any existing function, class, or method.
4. Keep changed files inside the allowed list for that mission.
5. Run focused tests for the new feature.
6. Run relevant platform harness regression tests.
7. Run `git diff --check`.
8. Run a forbidden path audit.
9. Run `npx gitnexus analyze`.
10. Run GitNexus `detect_changes`.
11. Write a ledger with `branch`, `commit`, `modified files`, `tests`, `report path`, and `risk`.
12. Commit on the isolated branch only.

## P5 Batch Permission Boundary

Claude may be asked to complete P5-B, P5-C, and P5-D as a long batch task if
P5-A passes CTO review.

The batch permission is limited:

- One isolated branch or a clearly documented stack of isolated branches.
- One ledger per slice.
- One result artifact per slice.
- One final batch readiness packet.
- No `platform-dev` merge.
- No product/runtime/backend/frontend/auth/RBAC/tenancy/migration/payment edits.

## Stop Conditions

Claude must stop and report if any of these occur:

- GitNexus HIGH or CRITICAL risk.
- Any forbidden path appears in `git diff --name-only`.
- Any focused or regression test fails.
- The mission requires product/backend/frontend/runtime work.
- The branch is not clean before starting.
- The worker cannot produce a structured JSON result.

## CTO Review Requirement

This permission policy reduces interactive prompts for Claude. It does not
reduce CTO review.

Codex Platform CTO must still review:

- branch and commit alignment
- diff scope
- tests
- report path
- GitNexus evidence
- forbidden path audit
- ledger quality
- risk classification
