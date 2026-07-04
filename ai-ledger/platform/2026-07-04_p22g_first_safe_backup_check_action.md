# P22-G First Safe Governed backup.check Action

**Phase:** P22-G -- first SAFE governed action completion (backup.check)
**Date:** 2026-07-04
**Branch:** `codex/platform-p22g-first-safe-backup-check-action-2026-07-04`
**Base:** `33ad74e` (`origin/platform-dev` -- includes merged P22-E3 + P22-E4)
**Author:** Codex (Claude worker)
**Status:** Complete. Additive governed read-completion for backup.check behind the P22-E1 seam.
The first action in P22 v0 that actually COMPLETES something after approval. The action
content is a READ. Never mutates. Ready for CTO review.

---

## 1. Summary

P22-G fills the key gap in the original P22 plan: controlled execution v0 does not stop at
dry-run / request / approval / source visibility -- after approval it can COMPLETE one safe,
low-risk, allowlisted, auditable action. This slice realizes exactly ONE action:
**`backup.check`**, and the action content is a governed READ of the proven P17-D-C backup /
status source.

The governed execution runs ONLY after the P22-E1 seam preflight passes (identity-only
super_admin; durable approval at `approved_execution_blocked` with quorum; a bound passed
dry-run; the typed acknowledgement; the allowlist; the digest-only idempotency not a
conflict). It then reads the P17-D-C source via the P22-E3 probe (`read_backup_check_source`),
maps the honest source verdict to a governed result, and records a redacted execution audit
event. It performs NO backup, NO restore, NO dump, NO shell / child process / SQL script, NO
queue drain, NO worker, and NO tenant mutation. Approval is not execution; what runs after
approval here is a read.

This is ADDITIVE and preserves every existing invariant:
- the static `backup.check` adapter descriptor in `adapters.py` STAYS `not_implemented` /
  `source_unknown` (the G15 invariant, `test_p22_backup_check_still_not_implemented`,
  unchanged) -- that descriptor is the closed GENERIC adapter name-table; this module is the
  separately-gated REALIZED adapter body anticipated by P22-E0 section 9.6;
- the seam (`seam.py`) STAYS a NON-EXECUTING preflight boundary
  (`SEAM_REALIZES_EXECUTION` still False; `evaluate_preflight_gate` reused UNCHANGED);
- the P22-B dry-run / request shapes STAY `executed=False` (a NEW governed-execution result
  shape carries the completed read).

> **The first safe action is a read.** `executed=True` means the governed READ completed; it
> is never a tenant mutation. `no_tenant_mutated` is ALWAYS True. `execution_allowed` is
> ALWAYS False (approval is not execution; this flag is never a trigger).

---

## 2. Base / Branch / Commit Chain

- **Base SHA:** `33ad74e` (`origin/platform-dev`; the P22-E4 merge).
- **Worktree:** `MPANGO ERP/codex-platform-p22g-first-safe-backup-check-action-2026-07-04`,
  created via `git worktree add --no-track -b <branch> <path> origin/platform-dev`. Upstream
  unset; published with the explicit refspec `git push -u origin <branch>:<branch>`.
- **Commit chain (base..tip):** `33ad74e` (base) -> `57b42c3` (R0: governed module + route +
  tests) -> R0 ledger (this report). The final tip SHA is reported in the chat report.

`platform-dev` is NOT merged and NOT the push target. Only the isolated P22-G branch is
published.

---

## 3. E0 Self-Check

Read the P22-A/B/C/D/E/F contracts + ledgers, the P22-E1 seam, the P22-E3 source probe, and
the P17-D-C source runtime.

**Current P22 capabilities before P22-G:** read-only catalog; no-mutation dry-run
(preflight); non-executing request recording; read-only queue/read; the P22-E1 non-executing
seam preflight; the P22-E3 read-only source probe + route; the P22-E4 console visibility.

**The gap:** nothing in P22 COMPLETES an action after approval -- every response carries
`executed=False`. P22-G fills this for backup.check only.

**Verdict: backup.check CAN be realized safely.** The action content is a READ of the P17-D-C
source (reuses the P22-E3 probe, which reuses P17's read-only loader). It violates NO
forbidden item: no subprocess / shell / SQL script / pg_dump / restore / queue / worker / tenant
mutation / migration / auth rewrite / frontend / dependency change. The read is read-only.

**G15 / first-execution decision:** honest realization does NOT require changing G15 -- the
realized adapter body lives in a NEW module layered behind the seam, while the static GENERIC
adapter name-table (G15) is preserved as the catalog/preflight registry. So no STOP condition
fires (the G15 invariant is kept; the execution is real, not fake -- it actually reads the
source and records honest results; no forbidden item is needed).

---

## 4. Changed Files (3 implementation + this ledger; backend-only; P17 untouched)

| File | Status | Scope |
|---|---|---|
| `backend/api/v1/platform/p22/governed_execution.py` | New | The realized adapter body for backup.check ONLY: `complete_governed_backup_check(request, db)` reuses the seam preflight (`evaluate_preflight_gate`) + the P22-E3 probe (`read_backup_check_source`) + the P22-B audit (`_emit_audit`); honest source->result mapping; new `GovernedBackupCheckRequest` / `GovernedBackupCheckResult` schemas. Read-only action content. |
| `backend/api/v1/platform/p22/routes.py` | Modified (additive) | Added one import + one route handler `POST /governed-execution/backup-check` behind the existing `require_platform_operator_with_p22_audit` guard. No existing route changed. |
| `backend/tests/test_platform_p22g_governed_backup_check.py` | New | 22 unit tests (section 6). |
| `ai-ledger/platform/2026-07-04_p22g_first_safe_backup_check_action.md` | New | This ledger. |

`git diff --name-only origin/platform-dev..HEAD` returns the three implementation/test paths
above (+ this ledger). No `p17/` change, no other `backend/` file modified (in particular no
`seam.py` / `adapters.py` / `services.py` / `schemas.py` / `source_probe.py` edit), no
`migrations/`, no `alembic/env.py`, no `scripts/` / P16, no `frontend/`, no
`product-dev-recovered/` or product / payment / billing / order / invoice / customer /
inventory path, no auth / RBAC / session rewrite, no `package.json` / lockfile, no CI /
`.github` / `.claude` / configured-secrets-baseline file.

---

## 5. Exact Behavior Delivered

`complete_governed_backup_check(request, db)`:

1. **Preflight (reused UNCHANGED from P22-E1).** Build a `SeamAdapterRequest` and call
   `evaluate_preflight_gate`. This re-validates: executor is identity-only super_admin;
   idempotency digest present; explicit acknowledgement present; action is the closed
   `backup.check` allowlist slot; the bound dry-run is still valid; the durable approval is at
   `approved_execution_blocked` with quorum, matching action / target (tenant) / honest source,
   with operator separation; the digest-only idempotency is not a conflict.
2. **Fail-closed.** If the preflight blocks, record an `execution_denied` audit and return a
   `blocked` result (`executed=False`). The read is never reached.
3. **Governed READ (the action content).** On a passed preflight, `await read_backup_check_source(db, tenant_id)`
   -- the P22-E3 probe of the P17-D-C source. Read-only; no session mutation.
4. **Honest result mapping** (unknown is never healthy):

   | source read | `result_state` | `executed` | audit event |
   |---|---|---|---|
   | fresh success (known) | `succeeded` | True | `execution_succeeded` |
   | stale / failed / partial / in_progress (degraded) | `completed_with_warning` | True | `execution_succeeded` |
   | no outcome (unknown) | `completed_with_warning` | True | `execution_succeeded` |
   | read failure (unavailable) | `failed` | False | `execution_failed` |
   | preflight blocked | `blocked` | False | `execution_denied` |

   `executed=True` means the governed READ completed; the warning / `failure_reason_redacted`
   carry the (allowlisted, redacted) source detail. A read failure is fail-closed (`failed`,
   `executed=False`); no fabricated healthy status.
5. **Audit.** Every completion appends a redacted `ExecutionAuditEvent` (via the P22-B
   `_emit_audit`) carrying action_type, durable_approval_id, dry_run_ref, actor identity,
   tenant_id, source_status, result_state (mapped to the P22-A coarse state), the redacted
   reason (which explicitly states no tenant mutation occurred), correlation_id, and the
   one-way idempotency digest. The audit `result_state` uses the P22-A execution-record
   vocabulary (`executed` / `execution_failed` / `blocked`); the governed result's
   `result_state` uses the more nuanced governed vocabulary above.

The static `backup.check` adapter descriptor stays `not_implemented` / `source_unknown` (G15);
the seam stays non-executing; the P22-B dry-run/request shapes stay `executed=False`. The
governed-execution layer is the separately-gated REALIZED adapter body (P22-E0 9.6).

---

## 6. Tests (22 new; all pass)

`test_platform_p22g_governed_backup_check.py`:

| Case | Test |
|---|---|
| dry-run does not execute (regression) | `TestNonExecutingInvariants.test_dry_run_does_not_execute` |
| module realizes ONLY backup.check (non-allowlisted rejected) | `test_module_realizes_only_backup_check` |
| unapproved request -> blocked, read never reached | `TestPreflightBlocking.test_unapproved_request_is_blocked_not_executed` |
| missing dry-run ref -> blocked | `test_missing_dry_run_ref_is_blocked` |
| missing ack -> blocked | `test_missing_ack_is_blocked` |
| fresh success -> succeeded / executed=True | `TestSourceMapping.test_fresh_success_succeeds` |
| stale -> completed_with_warning | `test_stale_completes_with_warning` |
| partial -> completed_with_warning + redacted reason | `test_partial_completes_with_redacted_reason` |
| failed backup -> completed_with_warning + redacted reason | `test_failed_backup_completes_with_warning` |
| in_progress -> completed_with_warning | `test_in_progress_completes_with_warning` |
| no source -> unknown, never healthy | `test_no_source_unknown_never_healthy` |
| read failure -> failed, fail-closed, no fake healthy | `test_read_failure_fail_closed_no_fake_healthy` |
| tenant_id propagation + binding | `TestTenantScope.test_tenant_id_propagates_and_binds` |
| tenant mismatch -> blocked | `test_tenant_mismatch_blocks` |
| audit records completion fields + no-tenant-mutation | `TestAudit.test_audit_records_completion_fields` |
| audit records denial for blocked preflight | `test_audit_records_denial_for_blocked_preflight` |
| audit records failure for read error | `test_audit_records_failure_for_read_error` |
| G15 static descriptor unchanged | `TestInvariantsPreserved.test_g15_static_descriptor_unchanged` |
| E3 source read still honest (unavailable on read error) | `test_e3_source_read_still_honest` |
| no subprocess/shell/execution call tokens (AST) | `TestNoExecutionPrimitives.*` |
| no forbidden imports (AST) | `TestNoExecutionPrimitives.*` |
| no invocation token in text (pg_dump/SELECT/etc.) | `TestNoExecutionPrimitives.*` |

---

## 7. Validation Gates

| Gate | Result |
|---|---|
| `git diff --check origin/platform-dev..HEAD` | clean |
| Changed files | 3 backend paths (2 new + 1 modified) + this ledger |
| Non-ASCII byte scan | 0 non-ASCII bytes across all 3 implementation/test files |
| detect-secrets (configured baseline) | clean (exit 0); baseline unmodified; pre-commit detect-secrets passed at commit |
| Forbidden path audit | clean (section 8) |
| AST/text scan for subprocess / shell / pg_dump / restore / raw SQL | clean (`TestNoExecutionPrimitives` + the P22-E1 scans now also walk `governed_execution.py` and the modified `routes.py`) |
| P22-G targeted tests | 22 passed |
| P22-E3 / P22-E1 / P22 controlled execution regression | pass (part of the 921) |
| P17-D-C read tests | 25 passed, 1 deselected -- see section 9 (pre-existing date-roll flake) |
| Platform regression subset (P0..P22) | **921 passed, 37 skipped, 1 deselected, 0 failed** |
| `npx gitnexus analyze .` | 8,764 nodes / 26,819 edges / 560 clusters / 300 flows at `57b42c3` |
| `npx gitnexus status` | up-to-date at `57b42c3` |
| GitNexus `detect_changes` vs `origin/platform-dev` | `changed_count=58, affected_count=9, changed_files=3, risk_level=high` -- ALL 9 affected processes are platform-P22-internal; **0 product-business hit** (section 10) |

---

## 8. Forbidden Path Audit

The change set is 3 backend paths under `backend/api/v1/platform/p22/` + `backend/tests/`,
plus this ledger. None matches any forbidden prefix or fragment:

- No `p17/` change (P17-D-C source runtime untouched; the probe reuses it read-only); no
  `migrations/`; no `alembic/env.py`.
- No `scripts/` / P16; no `product-dev-recovered/` or product / payment / billing / order /
  invoice / customer / inventory path.
- No auth / RBAC / session rewrite (the route reuses the existing P22 guard + actor helper).
- No `frontend/`; no `package.json` / lockfile / dependency change.
- No `.github/`, no `.claude/`, no configured secrets baseline file, no CI / deploy file.
- No real execution / worker / harness / shell / SQL script / pg_dump / restore / queue drain.

The new module's imports are AST-scanned clean (it imports only from `.seam`, `.services`,
`.source_probe`, `.schemas`, `pydantic`, `datetime`, `typing`). The P22-E1 forbidden-call /
forbidden-import scans now walk `governed_execution.py` and the modified `routes.py` and pass.

---

## 9. Pre-existing P17-D-C date-roll flake (NOT a P22-G regression)

One P17-D-C test fails: `test_platform_p17dc_backup_registry_read.py::TestRegistryAssembly::test_tenant_specific_wins_over_platform_at_registry`
(expected `last_backup_status == "success"`, got `"stale"`). This is a PRE-EXISTING date-roll
flake, not a P22-G regression:

- P22-G touches NO `p17/` file and NO P17-D-C test (`git diff` confirms; the 3 changed files
  are all under `p22/` + `tests/test_platform_p22*`).
- The test seeds a tenant backup row at a FIXED past time (test `NOW = 2026-07-03 12:00` minus
  10h = `2026-07-03 02:00`) and expects `success` (fresh). The P17 registry route computes
  freshness against the REAL `_utcnow()` (now `2026-07-04`), so the row is > 24h old -> `stale`.
- **Reproduced on a clean `origin/platform-dev` tree** (P22-G changes stashed): the test still
  fails. It passed in earlier sessions only because those ran on 2026-07-03 (real now ~= test
  NOW). It is inherently date-fragile and breaks from 2026-07-04 02:00 onward.
- The other 25 P17-D-C read tests pass (the 2h-old-row variant stays within the 24h window).

P22-G does NOT fix this (it is out of scope -- a P17-D-C test-hygiene issue, and P22-G must
not touch P17). Recommended: a separate P17-D-C hygiene task to inject a fixed `now` into the
registry route under test (or seed rows relative to real now).

---

## 10. GitNexus

- `analyze`: 8,764 nodes / 26,819 edges / 560 clusters / 300 flows at `57b42c3` (edges rose
  from ~26,519 at base -- the new `governed_backup_check_route` -> `complete_governed_backup_check`
  -> `evaluate_preflight_gate` / `read_backup_check_source` / `_emit_audit` call edges).
- `status`: up-to-date (indexed commit == current commit == `57b42c3`).
- `detect_changes` (MCP `scope=compare`, `base_ref=origin/platform-dev`):
  `changed_count=58, affected_count=9, changed_files=3, risk_level=high`. The 9 affected
  processes are ALL platform-P22-internal -- rooted at `Require_platform_operator_with_p22_audit`
  (the P22 guard) or `Governed_backup_check_route` (the new route), reaching only P22 internals
  (`PlatformAuditLog`, `_http_exc`, `Get`, `_is_test_env`, `_executor_block_reason`,
  `Resolve_adapter_descriptor`, `_classify_action`, `_dry_run_binding_block`). **Zero
  product / payment / order / invoice / customer / inventory business flow.** The HIGH risk
  level is gitnexus's count-based heuristic (9 affected processes, because the new route
  reaches into the P22 seam/preflight machinery); qualitatively the blast radius is
  platform-P22-only. The stop condition ("GitNexus shows product business affected flow") does
  NOT fire.

---

## 11. Risk

**GitNexus: HIGH (by affected-process count). Qualitative: MEDIUM.** P22-G adds the FIRST real
governed action (a meaningful capability), so it is more than a docs/UI change. But the action
content is a READ: it is bounded to backup.check, runs only behind the full seam preflight +
existing P22 guard, performs no backup / restore / dump / shell / SQL script / queue / worker,
mutates no tenant / payment / product state, and is fully redacted-audited. Blast radius is
platform-P22-only (`backend/api/v1/platform/p22/`); GitNexus confirms 0 product-business flow.
G15 / seam / P22-B shapes are preserved (additive).

---

## 12. Blockers

- None for P22-G.
- One pre-existing P17-D-C date-roll flake (section 9) is NOT a P22-G blocker -- it reproduces
  on `origin/platform-dev` and is a P17-D-C test-hygiene item.

---

## 13. Explicit Statements

- **Approval is not execution.** The governed read runs only after approval AND a passed seam
  preflight; `execution_allowed` is always False (never a trigger).
- **`backup.check` is the ONLY allowlisted action in this slice.** The governed request is
  pinned to `backup.check`; non-allowlisted actions cannot use this path (enforced + tested).
- **No tenant mutation.** The action content is a read; `no_tenant_mutated` is always True.
- **No backup / restore / pg_dump / dump / shell / subprocess / SQL script / queue / worker.**
  None.
- **No frontend.** None (backend-only).
- **No migration / alembic / env.py / schema change.** None.
- **No auth / RBAC / session rewrite.** None (existing P22 guard + actor helper reused).
- **No P17 source change.** None (the probe reuses the P17-D-C read path read-only).
- **No product / payment / billing / order / invoice / customer / inventory path.** None.
- **No package / lockfile / dependency change.** None.
- **platform-dev untouched.** `origin/platform-dev` is not merged and not pushed from P22-G.
- **P23 not started.** P22-G realizes one safe read-completion; it does not start the broader
  real-execution policy / rollback / notification / audit-retention / AI-copilot gates (those
  remain P23+, per the P22-F closeout).
