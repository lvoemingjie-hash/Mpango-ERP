# P22-E4 Backup / Status Console Visibility

**Phase:** P22-E4 -- backup.check source visibility in the controlled execution console
**Date:** 2026-07-04
**Branch:** `codex/platform-p22e4-backup-check-console-2026-07-03`
**Base:** `bfbd780` (`origin/platform-dev` -- includes the merged P22-E3 read-only route)
**Author:** Codex (Claude worker)
**Status:** Complete. Frontend-only, read-only console addition. E4 gates pass; P22-F closeout completed (sibling ledger). R1 = ledger-evidence-accuracy fix only (changed-files wording = 5 frontend impl/test files + 2 ledgers = 7; detect_changes `changed_count=47/affected_count=0/changed_files=7/risk low`; frontend targeted 34 / full 312 / backend 113; act-warning characterization corrected). No runtime/test/code change in R1. Never executes; ready for CTO review.

---

## 1. Summary

P22-E4 makes the P22-E3 read-only `backup.check` source status visible and usable from
the existing P22 controlled execution console (P22-C). It adds frontend API/type support
for `GET /api/v1/platform/p22/backup-check/source` and a read-only "backup.check source
status" section to `PlatformControlledExecutionConsolePage`. The backend is UNTOUCHED.

The section surfaces the honest P22-E3 verdict -- `known` | `degraded` | `unknown` --
with `unavailable` (fail-closed) shown as unknown, never healthy. It renders only the
allowlisted fields (`last_backup_status`, `last_backup_at`, `restore_test_status`,
`last_restore_test_at`, `failure_reason_redacted`, `export_available`,
`retention_policy`, `p17_backup_source_status`, `reason`, `checked_at`) when present,
plus the non-executing flags (all `false`, `result_state=blocked`). It never displays
raw logs, DSNs, host/port/path, command lines, secrets, or raw failure text
(`failure_reason_redacted` is the closed allowlisted code only).

The section's ONLY control is a "Refresh source status" button (a READ). There is no
execute button, no queue drain, no worker, no shell, no SQL/script. Unknown / unavailable
never implies healthy / success. A defensive guard renders an explicit violation notice
if a source read ever carried an execution flag (it never should).

> **Read-only.** This is a status probe, not an execution. Approval is not execution; a
> read is not execution. The static `backup.check` adapter stays `not_implemented`.

---

## 2. Base / Branch / Commit Chain

- **Base SHA:** `bfbd780` (`origin/platform-dev`; the P22-E3 merge).
- **Worktree:** `MPANGO ERP/codex-platform-p22e4-backup-check-console-2026-07-03`, created
  via `git worktree add --no-track -b <branch> <path> origin/platform-dev`. Upstream unset;
  published with the explicit refspec `git push -u origin <branch>:<branch>`.
- **Commit chain (base..tip):** `bfbd780` (base) -> `7ea894d` (R0: frontend type + API
  client + console section + tests) -> `131ea4e` (R0 ledger + P22-F closeout) -> R1
  (this evidence-accuracy fix to the R0 ledger). The final tip SHA is reported in the chat
  report.

`platform-dev` is NOT merged and NOT the push target. Only the isolated E4 branch is
published.

---

## 3. Changed Files (5 frontend implementation/test files + 2 ledgers = 7 total; backend untouched)

The five files below are the E4 frontend implementation/test files:

| File | Status | Scope |
|---|---|---|
| `frontend/src/types/platformControlledExecution.ts` | Modified | Added `BackupCheckSummary` + `BackupCheckSourceRead` (echo-safe; only allowlisted fields; `failure_reason_redacted` is the closed code only; every execution flag typed `false`). |
| `frontend/src/services/platformApi.ts` | Modified | Added `getBackupCheckSource(tenantId?)` -> `GET /platform/p22/backup-check/source` (blank tenant_id normalized to platform-wide). |
| `frontend/src/pages/platform/PlatformControlledExecutionConsolePage.tsx` | Modified | Added a read-only "backup.check source status" `section` + a `BackupSourceField` helper + state and a `refreshBackupCheckSource` handler. The only control is the refresh button; non-executing flags are surfaced; an execution-flag violation would render an explicit notice. |
| `frontend/src/services/__tests__/platformControlledExecutionApi.test.ts` | Modified | +3 API tests (URL, tenant_id forwarding, non-executing model). |
| `frontend/src/pages/platform/__tests__/PlatformControlledExecutionConsolePage.test.tsx` | Modified | +7 page tests (known / degraded / unknown / unavailable / transport-failure / no-execute-control-no-raw-text / tenant_id forwarding). |

The full branch diff (`git diff --name-only origin/platform-dev..HEAD`) is **7 paths**:
the 5 frontend implementation/test files above plus the 2 ledger files
(`ai-ledger/platform/2026-07-03_p22e4_backup_check_console.md` and
`ai-ledger/platform/2026-07-03_p22f_controlled_execution_closeout.md`). No
`backend/` change (E4 is frontend-only), no `migrations/`, no `alembic/env.py`, no
`scripts/` / P16, no `product-dev-recovered/` or product / payment / billing / order /
invoice / customer / inventory path, no auth / RBAC / session rewrite, no `package.json`
or lockfile, no CI / `.github` / `.claude` file, no configured secrets baseline file. (A
`frontend/node_modules` junction to the main repo's node_modules was created for the
worktree test-env reuse; it is gitignored and is NOT a tracked change.)

---

## 4. Design

- **Why a route-driven section, not catalog/dry-run fields:** the P22-E3 probe is `async`
  and needs a DB session; the console's catalog/dry-run are sync. The new section fetches
  on demand via a "Refresh source status" button (a READ), carrying the authed Bearer token
  through the existing Axios singleton -- identical to every other P22 call.
- **Honest rendering:** `source_status` badge reuses the existing `SOURCE_TONE` map
  (known=green, degraded=yellow, unknown=red); `source_summary` is shown as text. For the
  fail-closed `unavailable` summary, `source_status` is `unknown` (red) -- never healthy.
- **Echo-safety:** only the allowlisted `BackupCheckSourceRead` fields are rendered via the
  explicit `BackupSourceField` list; the object is never dumped wholesale, so a future raw
  field could not leak. `failure_reason_redacted` is the closed allowlisted code only
  (asserted: a raw `Traceback` never appears).
- **No-execution preserved:** the section adds NO execute/run/dispatch/restore/dump control
  (asserted: the only button is "Refresh source status"); it surfaces `realizes_execution /
  executed / execution_started / execution_allowed = false` and `result_state = blocked`;
  and it would render an explicit `p22-backup-check-exec-violation` notice if a read ever
  carried an execution flag.
- **Guard unchanged:** the page remains under the existing `PlatformRoute` guard
  (identity-only super_admin); the new section inherits that protection. No routing or
  guard code changed.

---

## 5. Tests

10 new tests (3 API + 7 page), all passing:

| Case | Test |
|---|---|
| API: URL + no params (platform-wide) | `P22-E4-001` |
| API: tenant_id forwarding (blank -> platform-wide) | `P22-E4-002` |
| API: response modelled non-executing + echo-safe | `P22-E4-003` |
| Page: fresh success visible as known, non-executing | `P22-E4-P01` |
| Page: stale -> degraded, never success | `P22-E4-P02` |
| Page: no outcome -> unknown, never healthy | `P22-E4-P03` |
| Page: unavailable (fail-closed) -> unknown, never healthy | `P22-E4-P04` |
| Page: transport failure -> operator error, no crash | `P22-E4-P05` |
| Page: NO execute/run/dispatch control; no raw failure text | `P22-E4-P06` |
| Page: tenant_id reaches the query param | `P22-E4-P07` |

Guard coverage is the existing `PlatformControlledExecutionNav.test.tsx` (P22-N04 admits
identity-only super_admin; P22-N05 redirects tenant-contextual away) -- unchanged, passing.

---

## 6. Validation Gates

| Gate | Result |
|---|---|
| `git diff --check origin/platform-dev..HEAD` | clean (exit 0) |
| Changed files | 7 paths total: 5 frontend implementation/test files + 2 ledgers (section 3) |
| Non-ASCII byte scan on changed files | 0 non-ASCII bytes across all 7 files (Python byte scan) |
| detect-secrets (configured baseline) | clean (exit 0); baseline unmodified; pre-commit detect-secrets passed at every commit |
| Forbidden path audit | clean (section 8) |
| Frontend E4 new tests | 10 new pass (3 API + 7 page) |
| Frontend targeted suite (P22-E4 console + API) | **34 passed** |
| Full frontend suite | **312 passed** across 33 files (pre-existing React Router future-flag warnings and multiple pre-existing act warnings in `src/pages/platform/ops/` pages, e.g. `OpsSlowRoutesPage`, `OpsResourcesPage`, and siblings; no P22-E4 targeted test produces an act warning and no new blocking failure is observed) |
| Backend P22-E3 / P22 / P22-E1 regression | **113 passed** (backend untouched) |
| `npx gitnexus analyze .` | 8,690 nodes / 26,519 edges / 542 clusters / 300 flows at `131ea4e` |
| `npx gitnexus status` | up-to-date at `131ea4e` (indexed == current == tip) |
| GitNexus `detect_changes` vs `origin/platform-dev` | `changed_count=47, affected_count=0, changed_files=7, risk_level=low`; **0 affected flows, 0 product-business hit** (correct for a frontend-only read-only UI addition) |

### Tooling notes (pre-existing, not introduced by E4)
- `tsc --noEmit` reports ~20 errors, ALL in other pre-existing files (e.g.
  `OpsSlowRoutesPage`, `PlatformApprovalsPage`, `PlatformAuditEventsPage`); the five E4
  frontend files are type-clean (zero errors).
- ESLint cannot load its config in this worktree (`@typescript-eslint/recommended` not
  resolvable via the junction'd node_modules) -- a pre-existing tooling issue, not a code
  issue, and not fixable without a dependency change (forbidden).
- Act warnings: the full frontend suite passes with pre-existing React Router future-flag
  warnings and **multiple pre-existing act warnings in `src/pages/platform/ops/` pages**
  (e.g. `OpsSlowRoutesPage`, `OpsResourcesPage`, and sibling ops pages -- these pre-date
  E4 and are untouched by it; the warnings are timing-related and non-deterministic across
  runs). No P22-E4 targeted test produces an act warning, and no new blocking failure is
  observed.

---

## 7. GitNexus

- `analyze`: 8,690 nodes / 26,519 edges / 542 clusters / 300 flows at the final tip
  (`131ea4e`).
- `status`: up-to-date (indexed commit == current commit == `131ea4e`).
- `detect_changes` (MCP `scope=compare`, `base_ref=origin/platform-dev`,
  `repo=codex/platform-p22e4-...`): **`changed_count=47, affected_count=0,
  changed_files=7, risk_level=low`**. The 7 changed files are the 5 frontend paths + the 2
  ledger files. Affected-process count is **0** and product-business hit count is **0** --
  the expected result for a frontend-only read-only console addition (gitnexus
  affected_processes are backend execution flows; a read-only UI panel touches none). The
  stop condition "GitNexus shows product-business affected flow" does not fire.

---

## 8. Forbidden Path Audit

The implementation change set is five frontend paths; the full branch diff is seven
paths including the two platform ledger files. None matches any forbidden prefix or
fragment:

- No `backend/` change (frontend-only); no `migrations/`; no `alembic/env.py`.
- No `scripts/` / P16; no `product-dev-recovered/` or product / payment / billing / order /
  invoice / customer / inventory path.
- No auth / RBAC / session rewrite (the page reuses the existing `PlatformRoute` guard and
  the existing Axios Bearer-token transport; no `X-Platform-Operator` secret is sent).
- No `package.json`, no lockfile, no dependency change (the `node_modules` junction is
  gitignored).
- No `.github/`, no `.claude/`, no configured secrets baseline file, no CI / deploy file.
- No real execution / worker / harness / shell / SQL / script / dump / restore / queue drain.

---

## 9. Self-Review

- Did E4 add execution power or an execute button? No -- a read-only status section whose
  only control is a refresh READ; no execute/run/dispatch/restore/dump affordance (asserted).
- Did it display raw secrets / DSN / path / raw failure text? No -- only allowlisted fields;
  `failure_reason_redacted` is the closed code; a raw `Traceback` never appears (asserted).
- Did it imply healthy on unavailable/unknown? No -- `unavailable`/`unknown` render as
  `unknown` (red), never `known` (asserted).
- Did it touch the backend, a migration, P17/P21/P16, auth, or a product path? No --
  frontend-only; backend P22-E3/P22/P22-E1 regression 113 passed unchanged.
- Is it ASCII-clean and secrets-clean? Yes -- 0 non-ASCII bytes; detect-secrets (configured
  baseline) clean; only short SHAs are used.

---

## 10. Risk

**Low.** E4 is frontend-only (five files: one page, one API client, one types module, two
test files). It adds a read-only status panel and reuses the existing Axios transport and
`PlatformRoute` guard; it changes no backend, no migration, no schema, no auth, no
dependency, and no product / payment / tenant business path. It grants no execution power.
Blast radius is the P22 console page; GitNexus confirms 0 affected flows and 0
product-business hit.

---

## 11. Blockers / Forward Gates

- None for E4.
- P22-F closeout is completed (sibling ledger
  `ai-ledger/platform/2026-07-03_p22f_controlled_execution_closeout.md`); P23+ is NOT started.

---

## 12. Explicit Statements

- **No real execution.** E4 performs no execution, offers no execute button, dispatches no
  worker, drains no queue, invokes no P16 harness, runs no shell / SQL / script, and performs
  no backup / restore / dump.
- **Read-only / non-executing.** The section is a status read; every execution flag stays
  `false` and `result_state` stays `blocked`.
- **No migration / schema / storage change.** None.
- **No backend change.** None (E4 is frontend-only; backend regression green).
- **No auth / RBAC / session rewrite.** None (existing `PlatformRoute` guard + Axios Bearer
  transport reused).
- **No product / payment / tenant business path.** None.
- **No package / lockfile / dependency change.** None.
- **No frontend raw-secret display.** Only allowlisted fields; raw failure text never shown.
- **platform-dev untouched.** `origin/platform-dev` is not merged and not pushed from E4.
- **P22-F completed; P23+ not started.**
