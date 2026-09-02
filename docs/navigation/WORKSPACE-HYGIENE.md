# Workspace Hygiene Policy

## Why this exists

The local Git registry currently contains hundreds of historical worktrees in
the Mpango parent directory and several under temporary or tool-managed paths.
This is a navigability and cleanup-risk problem, not permission to delete them.

The 2026-09-02 read-only snapshot found:

| Category | Registered worktrees |
|---|---:|
| Approved `MPANGO ERP/worktrees/` root | 60 |
| Codex-managed `.codex/worktrees/` | 7 |
| Legacy directories directly under `MPANGO ERP/` | 433 |
| Legacy temporary paths | 5 |
| Other | 2 |
| Total | 507 |

Counts are a snapshot. Run `scripts/project-context.ps1 -IncludeWorktrees` for
current local truth.

## Canonical roots for new work

Windows:

```text
C:\Users\Jeff0\MPANGO ERP\
  windsurf mpango erp\   # existing primary checkout; do not move in this task
  worktrees\             # all new Git worktrees
  evidence\              # task evidence not committed to Git
  handoffs\              # cross-agent handoff records
  scratch\               # disposable task-scoped files
  archive\               # CTO-approved retained legacy material
```

Lubuntu:

```text
/home/ivy/Documents/Codex/Mpango-ERP/
  repo/
  worktrees/
  evidence/
  handoffs/
  scratch/
  archive/
```

Codex-managed worktrees under `.codex/worktrees/` are allowed when created by
the desktop application, but they must still be tied to a task and cleaned by
the owning tool.

## Task directory contract

Every new worktree/evidence directory records:

```text
task_id
owner
base_sha
branch
created_at
claim_ceiling
expected_cleanup
retention_class
```

Temporary paths use the task ID. Names such as `test`, `new`, `final2`, or a bare
SHA are not acceptable long-term identifiers.

## Lifecycle

1. Create a task from a fetched exact base in a clean isolated worktree.
2. Keep runtime credentials and volatile artifacts in task-scoped scratch.
3. Publish only sanitized evidence required by the task contract.
4. Verify branch/report reachability and manifests.
5. Destroy task runtime, credentials, ports, containers, and scratch.
6. Remove the worktree registration and directory when the task closes unless
   an explicit review-retention period applies.
7. Record any retained path and its owner in the handoff/current-state system.

## Existing legacy material

Legacy cleanup is a separate controlled task. The safe order is:

```text
inventory -> classify -> hash/manifest -> reference check
-> retention decision -> move/quarantine -> verify -> delete only with approval
```

Do not use recursive deletion against computed paths. On Windows, resolve and
verify every absolute target remains inside the intended Mpango workspace before
moving or deleting it.

## Evidence retention classes

| Class | Example | Default action |
|---|---|---|
| Canonical committed evidence | merged reports and ledgers | Keep in Git |
| Active review evidence | current candidate runtime/review artifacts | Keep until CTO closeout |
| Reproducibility bundle | sanitized logs/manifests needed to rerun a gate | Archive with checksum and expiry |
| Scratch/runtime | venv, node_modules cache, raw logs, credentials, temp DB files | Destroy at task close |
| Unknown legacy | unclassified old directory | Quarantine; never delete directly |

## Enforcement target

Before customer delivery, require:

```text
UNREGISTERED_WORKTREES=0
UNCLASSIFIED_EXTERNAL_ARTIFACTS=0
ACTIVE_WORK_INDEX_CURRENT=true
SCRATCH_OUTSIDE_APPROVED_ROOTS=0
```

This document defines future placement and cleanup. It does not authorize moving
or deleting any path listed in the 2026-09-02 inventory.
