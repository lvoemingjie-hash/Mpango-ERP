# P22-B Controlled Execution v0 -- Non-Executing Backend Skeleton

**Phase:** P22-B Controlled Execution v0 (non-executing backend skeleton)
**Date:** 2026-07-01
**Branch:** `codex/platform-p22b-controlled-execution-backend-skeleton-2026-07-01`
**Base:** `b788a55` (`origin/platform-dev` -- "merge: P22-A controlled execution v0 contract")
**Contract:** `docs/ai/PLATFORM_PRODUCT_P22_CONTROLLED_EXECUTION_V0_CONTRACT.md` (P22-A)
**Author:** Codex (Claude worker)
**Status:** R1 applied (precondition binding fix); ready for CTO re-review

---

## 1. Summary

P22-B implements the **non-executing** execution skeleton permitted by the P22-A
entry gate (section 16): catalog read, a no-mutation dry-run validator,
execution-request recording (digest-only idempotency, redacted reason/metadata),
and execution-result read. It is wired to the P21 durable-approval read path and
the P10 identity-only guard.

It NEVER executes any action. There is no execute function, no worker, no queue
drain, no scheduler, no call to the P16 governed harness, and no shell / SQL /
script. `result_state` is only ever `dry_run_passed | blocked`;
`execution_allowed`, `executed`, and `execution_started` are always `false`.
Storage is in-memory, process-local (`storage == "memory"`); there is no
migration, no alembic change, and no new table.

> **Approval is not execution. Durability is not execution.** A durable,
> quorum-met approval at `approved_execution_blocked` is a PRECONDITION for a
> passed dry-run and a recorded request; it is not execution itself.

## 2. Base / Branch / Commit Chain

- **Base SHA:** `b788a55` (`origin/platform-dev`)
- **Worktree:** `MPANGO ERP/_p22b_skeleton` (created from `origin/platform-dev`;
  upstream unset so `platform-dev` cannot be pushed by a bare `git push`)
- **Commit chain (base..HEAD):**
  - `b788a55` -- base (origin/platform-dev)
  - `2ddffe7` -- `platform(p22b): controlled execution v0 non-executing backend skeleton` (code + tests + app.py route include)
  - `ae09698` -- `platform(p22b): controlled execution backend skeleton ledger` (initial ledger)
  - `3d67220` -- `platform(p22b-r1): precondition binding fix` (CTO R1: target binding + required reason/execution_mode; +8 tests)

`platform-dev` was NOT merged and NOT pushed. Only the isolated branch carries
these changes.

## 3. Modified / Added Files

| File | Status | Scope |
|---|---|---|
| `backend/api/app.py` | Modified | Route include only (P22 router registration; 5 added lines) |
| `backend/api/v1/platform/p22/__init__.py` | New | Package marker + non-execution markers |
| `backend/api/v1/platform/p22/schemas.py` | New | Closed 7-action allowlist, exclusion list, 9-state result enum (2 realized), 9 audit events, request/response shapes, digest/redaction fields |
| `backend/api/v1/platform/p22/services.py` | New | In-memory store, durable-approval resolver seam (default P20 memory read), dry-run validator, request recording (replay/conflict), read/list, redacted in-memory audit |
| `backend/api/v1/platform/p22/routes.py` | New | 5 endpoints behind the reused P10 identity-only guard; actor from token |
| `backend/tests/test_platform_p22_controlled_execution.py` | New | 48 contract-backed tests |
| `ai-ledger/platform/2026-07-01_p22b_controlled_execution_backend_skeleton.md` | New | This ledger |

No other paths were touched. No file under `product-dev-recovered/`, no
migration / alembic / env.py, no package / lockfile, no secret baseline, no
frontend, and no CI / deploy infra was modified.

## 4. Endpoint List

All behind the reused P10 identity-only `require_platform_operator` guard; prefix
`/api/v1/platform/p22/execution`.

| Method | Path | Behavior |
|---|---|---|
| GET | `/catalog` | Return the closed v0 allowlist (exactly 7 actions) + explicit exclusion list. Read-only. |
| POST | `/dry-run` | No-mutation precondition validation; returns `executable`, `verdict`, `block_reasons`, `expected_audit_shape`, `source_status`, `reversible`. Records dry-run audit events in memory. |
| POST | `/requests` | Record an execution request after a passed dry-run + acknowledgement. Digest-only idempotency (replay vs conflict). `result_state` is `dry_run_passed` or `blocked` only. Never executes. |
| GET | `/requests` | List recorded requests (filters: `result_state`, `action_type`, `durable_approval_id`). Read-only. |
| GET | `/requests/{execution_request_id}` | Read one redacted request record. 404 when missing. |

## 5. Storage Mode

`storage == "memory"` everywhere. The execution-request store, the dry-run
binding store, and the execution audit log are in-memory, process-local module
globals (`reset_store()` clears them). There is no database table, no migration,
no alembic revision, and no persistence. Durable approval is READ only, through
the P20 in-memory read path (default resolver) or an injected test resolver; P22
holds no durable-approval state of its own.

## 6. Exact Non-Execution Statement

P22-B performs **no real execution**. Specifically and verifiably:

- There is no function that executes, dispatches, drains, schedules, or invokes
  an action. (`services` exposes no `execute` / `run_action` / `dispatch` /
  `drain` / `invoke` / `start_worker` symbol; `P22_EXECUTES` is `False`.)
- There is no import of `subprocess` and no `os.system` / `os.popen` / `eval` /
  `exec` / `shell=True` / harness call in any p22 source file (proven by an AST
  scan test and a grep audit).
- The P16 governed harness is never imported or invoked.
- `result_state` is only ever `dry_run_passed | blocked`
  (`REALIZED_RESULT_STATES == {"dry_run_passed", "blocked"}`); the executing /
  executed / failed / compensation / cancelled states are never assigned.
- `execution_allowed`, `executed`, and `execution_started` are `False` on every
  response and audit event.
- No tenant business data, P17 registry, operational flag, provisioning, backup,
  payment / billing, or product record is read-for-write or mutated.

## 7. v0 Allowlist (exactly 7) and Exclusions

Allowlist (closed): `support_mode.on`, `support_mode.off`, `incident.flag_set`,
`incident.flag_clear`, `provisioning.recheck`, `backup.check`,
`backup.restore_test_request`.

Explicitly denied forever in v0 (return `action_excluded` / `action_not_allowlisted`
and never execute regardless of approval state): `tenant.pause`, `tenant.resume`,
`lifecycle.transition`, real restore, schema migration, data deletion,
payment / billing, tenant business records, and arbitrary shell / SQL / script.

## 8. Security Invariants (enforced + tested)

1. **Executor is identity-only super_admin.** Derived from the authenticated
   token via the reused P10 guard (never the request body -- no identity spoof,
   mirroring P20-B-R1). `support_operator`, `engineering_operator`,
   tenant-contextual super_admin, tenant admin, tenant-scoped token, and the
   operator-secret/no-actor path are denied and audited.
2. **Dry-run first.** No request is recorded without a passed dry-run bound by
   `dry_run_ref` matching the same approval / action / target / executor.
3. **Operator separation.** The executor is distinct from the maker and every
   checker (`self_execution_forbidden`, `checker_execution_forbidden`).
4. **Approval is a precondition, not execution.** State must be exactly
   `approved_execution_blocked` with `quorum_met == true`; re-validated at
   request time (a state change between dry-run and request blocks the request).
5. **Unknown is never healthy.** A write / write-request against a non-`known`
   source is blocked (`source_unknown_for_write`). A read MAY proceed against a
   `degraded` source and surface `source_status == degraded` (the only degraded
   allowance); writes never take a degraded / silent-fallback path.
6. **Digest-only idempotency.** The raw idempotency key is hashed at the boundary
   and discarded; only `idempotency_key_digest` and a canonical `payload_digest`
   are stored / returned / audited. Same key + same payload is a replay (original
   result, no new success audit); same key + different payload is a conflict
   (blocked, audited as `execution_denied`, no second state change).
7. **Total redaction.** reason / metadata / correlation pass through the P18
   allowlist (`_redact_reason`, `redact_metadata`, `_sanitize_text`) before any
   record, response, or audit field. No raw secret / DSN / host:port / token /
   password / cookie / auth header / raw body / shell / SQL / script appears.
8. **Every operation is audited** in the in-memory append-only execution audit
   log (dry-run requested/passed/blocked, execution_requested, execution_denied);
   `redaction_applied == true` on every event; denials audited with the same
   shape as successes.

## 9. Tests and Counts

- **P22 suite: 56 passed, 0 failed, 0 skipped** (48 base + 8 R1; see section 17)
  (`backend/tests/test_platform_p22_controlled_execution.py`).
  Coverage: catalog exactness (7 allowlist + named exclusions + storage/auth),
  dry-run passed variants (write/read/audit-shape/reversible),
  dry-run blocked variants (approval missing / wrong state / no quorum / unknown
  source for write / excluded action x3 / not-allowlisted / self-execution /
  checker-execution / action mismatch / missing idempotency key),
  degraded read (executable, source degraded; write degraded still blocked),
  executor denials (support / engineering / tenant-contextual / tenant admin /
  operator-secret-no-actor / no-auth 401), execution request (recorded /
  requires dry_run_ref / requires ack / requires key / blocked on re-validation /
  result_state never executing), idempotency (replay no double record / no double
  success audit / conflict audited), raw-key secrecy (never stored / returned /
  audited; digest present), redaction (sensitive reason -> [redacted]; metadata
  redacted), read/list (filters / 404 / redacted read), audit shape (dry-run
  events / redacted / no raw key), and no-execution source invariants (AST scan:
  no subprocess/shell/harness call tokens; no tenant/payment/product imports; no
  execute function; realized result_state values; default resolver reads P20
  memory store).
- **Regression: 361 passed, 0 failed**
  (P10 contracts, P18 controlled actions + real registry, P20 durable-approval
  governance, P21 adapter implementation/skeleton/models, P21-E runtime closeout).

## 10. Validation Gates

Final state at HEAD `3d67220` (post-R1; the R1 re-run delta is in section 16.4).

| Gate | Result |
|---|---|
| `git diff --check origin/platform-dev..HEAD` | clean (exit 0; no whitespace errors) |
| Backend P22 tests | 56 passed (48 base + 8 R1) |
| P10 / P18 / P20 / P21 regression | 361 passed |
| Non-ASCII scan on changed files | clean (all 7 files ASCII-only) |
| detect-secrets (configured baseline) | clean (exit 0; deliberate redaction-test fixtures marked `pragma: allowlist secret`) |
| Forbidden path audit | clean (app.py diff is route-include only; no subprocess/shell/harness/tenant/payment/product/alembic in p22 source) |
| `npx gitnexus analyze` | indexed at commit `3d67220`, status up-to-date; ~8.3k nodes / 25,521 edges / ~530 clusters / 300 flows (node & cluster counts fluctuate slightly across re-indexes; the 300-flow count is stable) |
| `gitnexus detect_changes` (compare vs `origin/platform-dev`) | 7 changed files, 99 changed symbols (all in `app.py` + `p22/*` + this ledger), 4 affected, **risk: medium** |
| Worktree clean (post-commit) | tracked tree clean (only gitignored `__pycache__` / `.gitnexus` / `CLAUDE.md` / `AGENTS.md` artifacts present, none committed) |

The `detect_changes` "medium" risk is expected and acceptable: the only
non-additive touch is `app.py:configure_app` (the central router-registration
function), and the change is a single additive `include_router` call plus a log
line. Every other changed symbol is brand-new inside `p22/`. No symbol outside
`app.py` + `p22/` (plus this ledger's markdown headings) changed.

## 11. Self-Review (two rounds)

**Round 1 -- security.**
- Execution accidentally possible? No -- no execute/run/dispatch/drain function;
  no subprocess/shell/SQL/harness; `result_state` only `dry_run_passed | blocked`;
  constants `EXECUTION_ALLOWED/EXECUTED/EXECUTION_STARTED` all `False`.
- Raw key / reason leak? No -- idempotency key digest-only; reason redacted before
  any record/echo; metadata redacted; audit redacted; proven by content-scan tests.
- Identity spoofing? No -- actor derived from the authenticated token, never the
  request body.
- Source unknown treated healthy? No -- writes require `known`; reads may degrade;
  unknown never healthy.
- Excluded action passes? No -- `tenant.pause/resume`, `lifecycle.transition`, and
  all other non-allowlisted actions are blocked at dry-run and request time.
- Tenant / payment / product touched? No -- no imports/calls (AST + grep proven).

**Round 2 -- reproducibility.**
- Hidden DB dependency? No -- pure in-memory service; `get_db` used only for
  best-effort platform audit (mocked in tests; try/except never blocks).
- Test-order dependency? No -- autouse fixture resets the P22 store, resolver,
  auth context, and approvals dict per test.
- Environment leak? No -- env via `setdefault`; the one P20-default-resolver test
  sets memory mode and resets stores in a `finally`.
- Docker / real-Postgres assumptions? No -- all in-memory / mock; no container.
- Skipped tests counted as proof? No -- 48 run, 48 pass, 0 skipped.

## 12. Known Limitations

- **In-memory, non-durable.** The execution-request store, dry-run bindings, and
  audit log are process-local and reset on restart. A durable backend is a
  separately CTO-gated future slice (mirrors P20/P21).
- **Audit event actor vocabulary is widened for denials.** The P22-A contract
  lists `actor_role: super_admin | system` and `identity_context: identity_only |
  system` for the EXECUTOR. To keep every denial auditable with the real denied
  identity (P22-A 8.2, mirroring P20), `ExecutionAuditEvent` and denied
  `ExecutionRequestResponse` use the wider P20 vocabulary
  (`super_admin | support_operator | engineering_operator | system | unknown` and
  `identity_only | tenant_contextual | tenant_scoped_token | tenant_admin | system | unknown`).
  A recorded (non-denied) request always carries `super_admin` / `identity_only`.
- **Best-effort platform audit.** P22 records the authoritative execution audit
  in memory and writes a best-effort, redacted entry to the existing platform
  audit service on each outcome (never blocks; never a tenant/business mutation).
- **Dry-run is replayable.** A passed dry-run is reusable as an execution
  precondition within a short TTL; request-time re-validation of the approval
  guarantees a stale dry-run cannot mask a precondition change.
- **No execution.** By design, P22-B cannot execute; the executing / executed /
  failed / compensation / cancelled states are unreachable here.

## 13. Risk Classification

**Low.** The change is purely additive (a new `p22/` package + one router
include in `app.py`), non-executing, isolated to the platform layer, fully
covered by 48 dedicated tests plus 361 regression tests, and passes every
security / redaction / no-execution gate. The only `detect_changes` "medium"
signal is the unavoidable touch of `configure_app`, which is additive.

## 14. Blockers

None.

## 15. Explicit Statements

- No real execution.
- No tenant mutation.
- No migration (no alembic, no table, no column).
- No auth / RBAC / session rewrite (reuses the P10 identity-only guard).
- No frontend.
- No `product-dev-recovered` (and no product business path).
- No payment / billing.
- `platform-dev` not merged and not pushed (only the isolated branch is pushed).
- P22-C (real execution) not started.

## 16. P22-B-R1 Precondition Binding Fix (CTO review rework)

CTO review of the initial skeleton approved the scope and the non-execution main
line but blocked merge on two execution-gate precondition gaps. Both are fixed in
R1; the non-executing, shaped-response, total-redaction invariants are preserved.

### 16.1 CTO findings

1. **[P1] Approval target was not bound to the request target.**
   `_check_approval_preconditions()` validated approval state / quorum / action /
   source / maker-checker separation but NOT `approval.tenant_id ==
   request.tenant_id`. Reproduction: approval scoped to tenant-A, dry-run
   targeting tenant-B still returned `executable=true, block_reasons=[]`. This
   violates the P22-A "same approval / action / target / executor" binding: a
   recorded request would carry a wrong target that a future real-execution phase
   would inherit.

2. **[P1] Required confirmation fields could be missing/invalid and still pass.**
   `reason` and `execution_mode` are declared required in the schemas, but the
   service only enforced the idempotency key; an invalid `execution_mode` was
   silently coerced to `None` instead of blocking. Reproduction: empty `reason`
   + missing/invalid `execution_mode` still returned `passed=true`. An execution-
   gate skeleton must not return `passed` when a required confirmation field is
   absent.

### 16.2 R1 fix

- **Target binding.** `_check_approval_preconditions()` now takes `tenant_id` and
  appends `target_mismatch_approval` when `approval.tenant_id != request.tenant_id`
  (both null means platform-wide and matches; values are normalized so empty is
  never silently treated as a match). Both the dry-run and the request-creation
  paths pass `request.tenant_id`. This is layered on top of the existing dry-run
  binding check (which already compares the bound dry-run's tenant to the
  request's tenant), so a target change is caught at dry-run, at request binding,
  and at approval re-validation.
- **Required fields.** Added two closed-vocabulary block codes --
  `reason_required` and `execution_mode_required` -- and the dry-run and request-
  creation paths now block when `reason` is empty or when `execution_mode` is not
  exactly `sync | queued`. The response field stays request-lenient (Optional) so
  the failure is a SHAPED blocked response (`result_state=blocked`,
  `executable=false`), never a 422/500, and never an execution. The internal
  `safe_mode` coercion to `None` is retained ONLY to keep the bad value off the
  strict response Literal (defense against a 500); the block code records the
  failure.

### 16.3 R1 regression tests (8 new; 56 total)

- `test_dry_run_target_mismatch_tenant_blocked` -- approval tenant-A + request
  tenant-B -> `target_mismatch_approval`, non-executing.
- `test_dry_run_matching_tenant_passes` -- same tenant -> no target mismatch
  (regression guard for the happy path).
- `test_dry_run_missing_reason_blocked` -- empty reason -> `reason_required`.
- `test_dry_run_invalid_execution_mode_blocked` -- `execution_mode="realtime"` ->
  `execution_mode_required`.
- `test_dry_run_missing_execution_mode_blocked` -- `execution_mode=None` -> shaped
  blocked response (HTTP 200, not 422/500), `execution_mode_required`.
- `test_request_missing_reason_blocked` -- request empty reason -> blocked, not
  recorded.
- `test_request_invalid_execution_mode_blocked` -- request `execution_mode="async"`
  -> blocked, not recorded.
- `test_blocked_responses_non_executing_and_audit_redacted` -- a blocked request
  stays `executed=false / execution_allowed=false / execution_started=false` and
  the denial audit carries no raw reason value.

### 16.4 R1 validation gates (re-run)

| Gate | Result |
|---|---|
| P22 suite | 56 passed (48 base + 8 R1), 0 failed, 0 skipped |
| P10 / P18 / P20 / P21 regression | 361 passed |
| `git diff --check` | clean |
| non-ASCII scan (changed files) | clean |
| detect-secrets (configured baseline) | clean |
| forbidden-symbol re-audit (services.py re-touched) | clean |
| `npx gitnexus analyze` | up to date / exit 0 |

### 16.5 Risk classification (unchanged)

**Medium, runtime-skeleton mitigated.** R1 only TIGHTENS the execution gate (two
new precondition checks + a target binding); it adds no execution surface, no
new route, no migration, and no dependency change. The code scope is unchanged
(`app.py` + `p22/*` + the test); `app.py` is not re-touched in R1. Relative to
`origin/platform-dev`, `detect_changes` reports 7 changed files (the 6 code/test
files + this ledger) and risk MEDIUM. Risk remains MEDIUM for the same additive
reason (the `configure_app` router include), fully mitigated by the non-executing
invariants and the 56-test + 361-regression-test coverage.

## 17. Deliverables

- Code: `backend/api/v1/platform/p22/{__init__,schemas,services,routes}.py` +
  `backend/api/app.py` route include (initial `2ddffe7`; the R1 precondition fix
  to `schemas.py` / `services.py` at `3d67220`).
- Tests: `backend/tests/test_platform_p22_controlled_execution.py` -- 56 tests
  (48 at `2ddffe7` + 8 R1 at `3d67220`).
- Ledger: this file -- initial at `ae09698`; R1 update at `3d67220`; this R2
  accuracy fix at the branch tip (commit chain in section 2).
