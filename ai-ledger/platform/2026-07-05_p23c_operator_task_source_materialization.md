# P23-C - Operator Task Source Materialization Bridge

- Status: LANDED on branch, NOT merged (push-ready on request).
- Date: 2026-07-05.
- Branch: `codex/platform-p23c-operator-task-source-materialization-2026-07-05`
- Base: `origin/platform-dev` @ `58f48884` (merge: P23-B operator task notification queue backend skeleton). P23-B IS merged at this base.
- Worktree: `_p23c_2026-07-05`.
- Commits: `e646b671` (code), `9391bfbe` (ledger R0), + an R1 ledger-only revision (see Revision history).

## Objective

Make P23-B's operator task queue begin to receive REAL platform follow-up items
from existing platform surfaces, without executing actions, sending
notifications, scheduling workers, or mutating product/tenant business data.

## What it does

A new module `backend/api/v1/platform/p23/sources.py` is a non-executing,
non-sending PULL bridge. It reads two AST-allowed, already-audited, READ-ONLY
source surfaces, maps them to typed `OperatorTaskIntakeEvent` objects, and feeds
them - and only them - through the P23 service layer's `upsert_task_from_event`.

Source mapping (P23-A section 3.1):
- P19 in-memory approval workflow (`p19.services.list_approvals`) -> one
  `approval_pending` task per open approval (state `requested` / `pending_review`);
  an open approval past its `expires_at` -> `approval_decision_required` (an
  honest "decide now" signal). P19 is in-memory; no DB session.
- P22-E3 read-only `backup.check` source probe
  (`p22.source_probe.read_backup_check_source`) -> `backup_check_warning` for a
  degraded backup (stale / failed / partial / in_progress) or `source_unknown`
  for an unknown / unavailable source. A fresh success is the only healthy read
  and produces NO task. This reuses the proven P22-E3 / P17-D-C read-only path
  verbatim and degrades fail-closed to `source_unknown` on any read failure.

New guarded route `POST /api/v1/platform/p23/operator-tasks/internal/materialize`
behind the reused P10 `require_platform_operator` guard. It is a manual
read/materialize operation, NOT a scheduler and NOT a worker. `db` is typed
`Any` so the P23 source tree stays free of a direct sqlalchemy import (a static
AST guard requires that).

## What it does NOT (explicit)

- No execution: calls no P22 action; approves no P19/P20/P21 approval; restores
  no backup; runs no shell / subprocess / SQL-script / pg_dump; dispatches no
  worker / scheduler / drain loop.
- No delivery: sends no notification on any channel. `channel` is None on every
  materialized event; no smtp / socket / requests / httpx / push module is
  imported (AST-enforced).
- No product/tenant mutation: reads only P19 in-memory approvals and the
  read-only `backup.check` probe; mutates no product / payment / billing /
  inventory / invoice / customer / ledger / tenant-business record.
- No fabrication: `source_unknown` is never healthy; `backup_check_warning` is
  never success; a fresh success produces no task; an unknown/unavailable source
  never becomes healthy.
- Execution task types (`action_request_created`, `execution_ready`,
  `execution_completed`, `execution_failed`) are deliberately NOT pulled - the
  P22 execution surface is AST-forbidden to P23 (`p22.services` /
  `p22.adapters` / `p22.governed_execution`). Those follow-ups arrive via the
  P23 intake PUSH endpoint. Omitting them here is the honest, safe choice; it is
  not a fabrication and never claims success from unknown data.

## Files

`origin/platform-dev..HEAD` = 5 files = 4 code/test files + this ledger:

- `backend/api/v1/platform/p23/sources.py` (NEW, 360 lines): materialization
  module - readers, pure source->event mappers (the honesty rules), and
  `materialize_all` orchestration. Imports only `p19.services` and
  `p22.source_probe` (both AST-allowed) plus `p23.schemas` / `p23.services`;
  NO `p22.services` / `p22.adapters` / `p22.governed_execution`, NO
  sqlalchemy / alembic / psycopg.
- `backend/api/v1/platform/p23/routes.py` (+36 lines): `Any` + `get_db` +
  `sources` imports, the docstring endpoint line, and the async
  `materialize_route` behind the reused P10 guard.
- `backend/tests/test_platform_p23_source_materialization.py` (NEW, 776 lines):
  42 tests.
- `backend/tests/test_platform_p23_operator_task_queue.py` (+3 lines): added
  `sources.py` to `_p23_source_files()` so the merged P23-B AST guards cover it.
- `ai-ledger/platform/2026-07-05_p23c_operator_task_source_materialization.md`
  (this ledger).

Diff scope: the 4 code/test files are within `backend/api/v1/platform/p23/*` and
`backend/tests/test_platform_p23_*.py`; the 5th file is this ledger. Zero
`app.py`, migration, `alembic/env`, product, frontend, package, or docs changes.
The P23 router was already included by P23-B; this branch only ADDS a route and
a module.

## Tests

- 42 new P23-C tests pass: P19 approval mapping (pending / overdue /
  non-pending / scope / source-status), backup-check mapping (degraded /
  unknown / unavailable / fresh-success / defensive honesty), `materialize_*`
  integration with dedup, `materialize_all` orchestration, honesty + redaction
  (warning never success; unknown never healthy; DSN scrubbed; no notification
  event recorded), the guarded materialize route (401 / 403 / 200 / shape /
  idempotent), and static AST guards for `sources.py` + `routes.py`.
- 42 existing P23-B tests still pass (84 P23 total).
- Platform regression subset (P0, P10-P23, excluding the two postgres-migration
  files): 934 passed, 46 skipped, 3 failed.
  - The 3 failures are PRE-EXISTING date-roll flakes (today 2026-07-05 is past
    their fixed-now cutoff 2026-07-04 02:00):
    `test_platform_p17dc_backup_registry_read.py::test_fresh_success_attached_to_registry`,
    `::test_tenant_specific_wins_over_platform_at_registry`, and
    `test_platform_p22e3_backup_check_source_probe.py::test_fresh_success_visible_as_known`.
    They reproduce on `origin/platform-dev` base; the P23-C diff does not touch
    p17dc / p22e3 source. Not a regression (documented in prior phase ledgers).

Recipe: `MPANGO_ENV=test`, a strong generated `SECRET_KEY`, run
`python -m pytest` from `backend/` with `PYTHONPATH=<worktree>/backend` and the
shared `.venv`.

## Validation gates

- pytest P23 (new + existing): 84 green.
- pytest platform regression: 934 green (3 documented pre-existing flakes above).
- `git diff --check`: clean (only LF -> CRLF Windows-normalization warnings).
- Added-line ASCII scan on the 4 code/test files: clean (0 non-ASCII lines).
  This ledger is also ASCII-clean.
- detect-secrets: 0 new findings on the 4 code/test files and on this ledger;
  the configured baseline is UNTOUCHED. The pre-commit `Detect secrets` hook
  Passed on every commit (it scans all 5 staged files). (One initial
  Basic-Auth-Credentials false-positive on a redaction-test fixture was
  eliminated by assembling the hostile string at runtime from fragments - the
  documented repo workaround for fake-secret fixtures.)
- Forbidden path/keyword audit: my path segments (`backend/api/v1/platform/p23/`
  `sources.py`, `routes.py`, `test_platform_p23_source_materialization.py`,
  `test_platform_p23_operator_task_queue.py`) contain NONE of the forbidden
  keywords (auth / rbac / tenancy / migration / payment / session). The AST
  forbidden-primitive guards (no subprocess / shell / pg_dump / restore / worker
  / scheduler / drain / channel-delivery / persistence / product /
  p22-execution imports; no executing call tokens) PASS for `sources.py` +
  `routes.py` (`sources.py` was added to `_p23_source_files()`).

## GitNexus

- `gitnexus analyze --force` (re-run at the branch code tip `9391bfbe`):
  9,111 nodes / 27,871 edges / 569 clusters / 300 flows. Analyzer variance vs.
  the earlier run on the same code (9,101 / 27,859 / 571 / 300): nodes +10,
  edges +12, clusters -2, flows 0 - the documented node/cluster wobble; same
  order of magnitude, NOT the base index passed off as the tip index.
- `gitnexus status`: indexed at branch tip `9391bfbe` (= current commit),
  up-to-date. NOT the base `58f4888`.
- `gitnexus impact` CLI (`--repo _p23c_2026-07-05`):
  - `materialize_route`: impactedCount 0, risk LOW, 0 processes, 0 modules.
  - `materialize_all`: impactedCount 0, risk LOW, 0 processes, 0 modules.
  - `upsert_task_from_event` (the reused seam): risk LOW, 0 processes_affected,
    affected_modules = Tests + P23 only (0 product).
- `detect_changes` (MCP): attempted; the stdio MCP did not respond to the
  standard initialize / tools/list handshake in this environment - the
  documented flakiness for large repos. The impact CLI is the reliable
  corroborator (per the repo validation playbook) and, together with the git
  diff scope above, establishes platform-only risk with ZERO product-business
  flows.

## Risk

LOW. Platform-only blast radius. Zero product-business flows. Zero `app.py` /
migration / shared-symbol changes. No new auth / RBAC / session surface (reuses
the P10 identity-only platform-operator guard). No DB writes - the only DB use
is the read-only `backup.check` probe, already proven read-only by P22-E3. The
stop gate (GitNexus shows product-business affected flows) is NOT triggered.

## Blockers

None.

## Explicit statements

- No execution: the bridge calls no P22 action, approves nothing, restores
  nothing, runs no shell / SQL / script / subprocess / pg_dump. AST guards
  enforce it.
- No delivery: no notification is sent on any channel; `channel` is None on
  every materialized event; no smtp / socket / requests / httpx / push module
  is imported (AST-enforced).
- No product/tenant mutation: the bridge reads only P19 in-memory approvals and
  the read-only `backup.check` probe; it mutates no product / payment / billing
  / inventory / invoice / customer / ledger / tenant-business record.

## Revision history

- R0 (`9391bfbe`): initial P23-C ledger (code commit `e646b671`).
- R1 (ledger-only, this revision): corrected the GitNexus `status` to the branch
  code tip `9391bfbe` (= current commit, up-to-date) - it had wrongly read
  "indexed at base commit 58f4888"; refreshed `gitnexus analyze --force` counts
  at the tip (9,111 / 27,871 / 569 / 300, with the documented node/cluster
  wobble); and aligned the file counts to the actual
  `origin/platform-dev..HEAD` diff (4 code/test files + this ledger = 5 files).
  No runtime / test / migration change; the index code graph is unchanged, so
  the impact evidence (LOW / 0 product for `materialize_route`,
  `materialize_all`, `upsert_task_from_event`) stands.
