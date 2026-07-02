# Platform Product P22-E0 -- Runtime Governed Action Adapter Seam Contract

**Status:** Docs-only architecture revision contract (P22-E0). No runtime code, no backend,
no frontend, no migration, no alembic change, no table, no column, no test code, and no
dependency change. No `backend/`, no `frontend/`, no `migrations/`, no `alembic/env.py`, no
`scripts/platform_worktree_executor.py` or any other P16 code, no `product-dev-recovered/`,
and no product / payment / billing / order / invoice / customer / inventory / ledger path is
touched. P22-E0 performs NO execution, dispatches NO worker, drains NO queue, invokes NO
harness, and runs NO shell / SQL / script / subprocess. It revises exactly one gate (G5) of
the P22-D real-execution design lock to correct a semantic error, defines the runtime governed
action adapter seam that future real execution must use, and gates a later P22-E1 backend-only
non-executing skeleton. P22-E0 ships no execution power and unlocks nothing at runtime.
**Phase:** P22-E0 Runtime Governed Action Adapter Seam Contract
**Date:** 2026-07-02
**Base:** `f48e9fe` (`origin/platform-dev` -- "merge: P22-D controlled execution readiness
lock"; P22-A contract, P22-B non-executing backend skeleton, P22-C non-executing frontend
console, and P22-D readiness closeout + real-execution design lock all merged)
**Depends on:** P10 (identity-only super_admin guard, PlatformAuditEvent, source-status
vocabulary, redact_metadata allowlist), P16 (Worktree Execution Harness -- development-time /
agent-worker file-change audit harness; see section 3), P17 (Registry and Tenant Lifecycle
Contract), P18 (Controlled Platform Actions Contract), P19 (Approval Workflow Contract), P20
(Durable Approval Governance Contract), P21 (Durable Approval Store Contract), P22-A
(Controlled Execution v0 Contract), P22-B (non-executing backend skeleton), P22-C
(non-executing frontend console), P22-D (readiness closeout + real-execution design lock).
**Revises:** P22-D section 3 gate G5 only. Every other P22-A / P22-D term -- the seven-action
allowlist, the exclusion list, G1-G4 and G6-G7, the dry-run / request / result models, the
audit contract, the idempotency rules, the safety rules, the operator-separation policy, the
permanent hard stops, and the API shapes -- is unchanged by P22-E0.
**Author:** Codex (Claude worker)

---

## 1. Goal and Scope

P22-D froze a real-execution design lock whose gate G5 read: "real execution runs ONLY through
the P16 Worktree Execution Harness ... no direct in-process execution." P22-E was the earliest
phase permitted to attempt a minimal READ-FIRST real-execution slice (`backup.check`). When
P22-E reached its discovery step (P22-E0 discovery), it correctly STOPPED: the only artifact on
`origin/platform-dev` named a "P16 governed harness" is `scripts/platform_worktree_executor.py`,
which is a subprocess-based, file-change-auditing **worktree mission runner for agent workers**,
not an online runtime controlled-action executor. There is no in-process governed adapter seam
in the platform runtime, `backup.check` has no wired data source (P17 records "Backup system
source is not yet wired"), and the P22 source is AST-tested to forbid the very `execute` /
`subprocess` / `p16` symbols a real-execution path would need. G5, as written, conflated the
development-time agent worktree harness with a runtime controlled-action executor. P22-E0
corrects that error at the contract layer before any runtime code is written.

P22-E0 has three jobs and does nothing else:

1. **E0 STOP retrospective.** Record why the attempted P22-E READ-FIRST slice could not proceed
   inside the hard boundaries, with the as-built evidence (section 2).
2. **G5 revision.** Replace the P22-D G5 gate with a corrected gate: real execution must run
   through a runtime governed action adapter seam, NOT through the P16 worktree executor. P16
   keeps its real role: a development-time / agent-worker file-change audit harness (section 3).
3. **Runtime governed adapter seam definition + entry gate.** Define the seam a future
   real-execution phase must build and run actions through (section 4), fix the `backup.check`
   future path and its P17 data-source dependency (sections 5-6), and gate a later P22-E1
   backend-only NON-EXECUTING skeleton (section 9).

P22-E0 defines and revises; it implements nothing. **Real execution of any v0 action remains
reserved for a separately CTO-approved phase.** P22-E0 grants no execution power, changes no
runtime code, and starts no backend, frontend, migration, or P16 work.

The single most important invariant, carried forward from P22-A and P22-D and restated for this
revision:

> **Approval is not execution. A passed dry-run is not execution. A recorded request is not
> execution. A runtime governed adapter seam is the ONLY boundary a future real execution may
> run through -- and the seam, the adapter, the dry-run, the acknowledgement, and the durable
> approval are all PRECONDITIONS, not execution itself. Even a real-executed v0 action never
> mutates tenant business data, never runs arbitrary shell / SQL / script / subprocess, never
> touches payment / billing or product code, and is fully audited and fail-closed.**

### 1.1 In scope (docs / contract layer)

- The E0 STOP retrospective with as-built evidence (section 2).
- The G5 OLD -> NEW revision and the corrected role of P16 (section 3).
- The runtime governed action adapter seam definition (section 4).
- The `backup.check` future path (section 5) and the P17 data-source dependency (section 6).
- Acceptance criteria for the contract (section 7, >= 14).
- Counterexamples -- the misuse patterns the revised lock rejects (section 8, >= 14).
- The P22-E1 entry gate for a future backend-only non-executing skeleton (section 9).
- The relationship to P22-A / P22-D -- what changes and what does not (section 10).

### 1.2 Non-goals

- No runtime code, no backend handler, no adapter implementation, no frontend UI, no test code,
  and no dependency change.
- No migration, no alembic change, no table, no column.
- **No real execution.** No v0 action is executed, dispatched, queued, scheduled, or run in
  P22-E0. No worker, no queue drain, no scheduler, no adapter, and no shell / SQL / script /
  subprocess.
- No change to the P16 worktree executor or any P16 code (`scripts/platform_worktree_executor.py`
  and all other P16 assets are untouched).
- No change to the P22-A allowlist, exclusion list, preconditions, dry-run / request / result
  models, audit contract, idempotency rules, or safety rules; no change to G1-G4 or G6-G7.
- No auth / RBAC / session / tenancy rewrite.
- No merge or push of platform-dev and no push to any product branch.
- P22-E0 does not start P22-E1 and grants no execution power.

---

## 2. E0 STOP Retrospective -- Why P22-E Could Not Continue

The attempted P22-E READ-FIRST execution slice (`backup.check`) reached its discovery step and
correctly STOPPED under the task's stop conditions rather than improvise a write action or
violate a hard boundary. The stop was not a failure of effort; it exposed a genuine contract
error in P22-D G5. Four as-built facts on `origin/platform-dev` at base `f48e9fe` combine to
block any faithful implementation of G5 as written:

1. **The P16 harness is a development-time worktree mission runner, not a runtime executor.**
   The only artifact named a "P16 governed harness" is `scripts/platform_worktree_executor.py`.
   It `import subprocess`, runs `git worktree add`, spawns a worker process in an isolated
   worktree, and its entire verdict model is `audit_against_expected(changed_files,
   expected_files, ...)` -- i.e. **changed-files vs expected-files plus forbidden-path
   prefixes** (`backend/`, `frontend/`, `product-dev-recovered/`, `.github/`, `.claude/`,
   `docs/ai/`, and the auth / rbac / tenancy / session / migration / payment fragments). It is a
   file-change audit harness for agent code-change missions. It has no concept of hosting a
   bounded read adapter, no concept of a typed action request / response, and no concept of
   returning a backup-status result. (`ai-ledger/platform/2026-06-20_p16_worktree_execution_harness.md`;
   `scripts/platform_worktree_executor.py`.)

2. **There is no in-process governed adapter seam in the platform runtime.** A full search of
   `backend/` for governed / adapter-registry / execute-action / run-governed / invoke-harness
   symbols returns only unrelated names: Starlette middleware `dispatch` overrides, auth / mock
   `.execute()`, reporting `query_builder.execute()` (a SQL SELECT executor for governed BI
   assets), and `core/governance/*` (BI-asset URN / report governance, not controlled-action
   execution). `scripts/platform_harness_index.py` is a markdown index generator, not a runtime
   seam. No backend module exposes a bounded, named, per-action controlled-action adapter
   boundary.

3. **`backup.check` has no data source.** P17 records
   `_BACKUP_UNAVAILABLE_REASON = "Backup system source is not yet wired; backup status is
   unavailable."` and assembles every registry with `backup_status=None` plus the reason
   (`backend/api/v1/platform/p17/services.py`). P18 models `backup.check` as "Recorded only;
   not executed." A "real execution" of `backup.check` would therefore read nothing real; it
   could only return a fabricated or degraded result.

4. **The P22 source is AST-guarded against exactly the symbols a real-execution path needs.**
   `backend/tests/test_platform_p22_controlled_execution.py` asserts, across all p22 source:
   no call whose attribute name references `harness` / `execute_action` / `run_action` /
   `dispatch_action` / `drain_queue` / `start_worker` / `invoke_harness`; no `subprocess.*`,
   no `os.system` / `os.popen` / `os.execv` / `os.execve`, no `shell=True`; no import of `p16`,
   `subprocess`, or any product module; and no public function named `execute` / `run_action` /
   `dispatch` / `drain` / `invoke` / `invoke_harness` / `start_worker` / `run`. Even reaching
   for the P16 harness from P22 would require weakening a tested security invariant.

These four facts make every implementation path for a faithful `backup.check` real execution
violate at least one hard boundary:

| Attempted path | Hard boundary it violates |
|---|---|
| A direct in-process adapter that reads P17 backup status | P22-D G5 ("no direct in-process execution") and the P22 AST invariants (the needed `execute` / adapter symbols and the `p16` / `subprocess` imports are forbidden) |
| Invoke `scripts/platform_worktree_executor.py` at request time | The "no direct subprocess / shell" rule, the P22 AST invariants (`subprocess.*` and `p16` imports forbidden), and a semantic mismatch (the worktree executor audits file changes, not status reads) |
| Build a brand-new in-process governed seam as the "boundary" without a contract | Neither "the P16 governed harness" nor an "existing platform harness contract"; a new architectural execution surface that contradicts G5 as written and exceeds a minimal proof slice; also nothing real to read |

The conclusion is structural, not a matter of effort: **G5 as written in P22-D conflates the
development-time agent worktree harness with a runtime controlled-action executor.** The
correct resolution is a contract revision that (a) restores P16 to its real role and (b)
defines the runtime governed action adapter seam that future real execution must use. That is
what P22-E0 is. P22-E0 does not implement the seam; it defines it and gates a later skeleton.

---

## 3. G5 Revision -- OLD vs NEW, and the Corrected Role of P16

### 3.1 OLD G5 (P22-D section 3, verbatim)

> **G5 -- P16 governed harness only.** Real execution runs ONLY through the P16 Worktree
> Execution Harness. There is no direct in-process execution, no side channel, and no bypass.
> The harness is the single execution boundary.

### 3.2 NEW G5 (revised by P22-E0)

> **G5 -- Runtime governed action adapter seam only.** Real execution of a v0 action runs ONLY
> through the runtime governed action adapter seam defined in section 4 of this contract. The
> seam is a per-action, bounded, typed, preflight-gated, before / after / failure-audited,
> idempotency-guarded, source-honest, no-tenant-business-mutation, fail-closed adapter boundary
> inside the platform runtime. There is no direct in-process bypass of the seam, no side
> channel, and no generic shell / SQL / script / subprocess executor. The P16 Worktree Execution
> Harness is a development-time / agent-worker file-change audit harness; it is NOT a runtime
> controlled-action executor and is never invoked at request time.

### 3.3 The corrected role of P16

P16 (`scripts/platform_worktree_executor.py` and its index / mission / ledger assets) keeps its
real and valuable role unchanged: it runs CTO-defined **agent missions in isolated git
worktrees** with machine-readable scope, forbidden-path enforcement, validation gates, stop
conditions, and completion reports, and it audits worker file changes against an immutable base
SHA. It is the governed boundary for **development-time / agent-worker code-change work**. It is
not, and never becomes, the boundary that executes an online controlled platform action in
response to a runtime request. The two concerns are deliberately separate:

- **P16 worktree harness** -- governs an agent worker that changes files in a worktree (a
  development / automation activity). Audits file diffs. Default dry-run.
- **Runtime governed action adapter seam** (defined here, section 4) -- governs a bounded,
  named, typed platform action executed at request time behind G1-G4 + G7 (a runtime controlled
  -action activity). Audits action before / after / failure.

P22-E0 changes no P16 code, no P16 contract term, and no P16 asset. It only stops P22-D G5 from
mis-stating that the P16 harness is the runtime execution boundary.

### 3.4 What the revision does NOT change

- G1 (durable approval at `approved_execution_blocked`, quorum met, matching action / target),
  G2 (passed P22 dry-run bound by `dry_run_ref`), G3 (explicit execution acknowledgement), G4
  (allowlisted v0 action only), G6 (per-action adapter, no generic shell / SQL / script), and G7
  (audit before / after / failure) are all unchanged.
- The seven-action v0 allowlist, the exclusion list, the twelve preconditions, the dry-run /
  request / result models, the nine-state execution-record enum, the audit contract, the
  digest-only idempotency rules, the fifteen safety rules, and the operator-separation policy
  are all unchanged.
- The permanent hard stops (section 5 of P22-D) are unchanged: `tenant.pause`, `tenant.resume`,
  `lifecycle.transition`, real restore, schema migration, data deletion, payment / billing,
  tenant business records, arbitrary shell / SQL / script, and AI agent direct execution never
  enter v0 execution.
- The P22-A / P22-B / P22-C non-execution baseline is unchanged: on `origin/platform-dev` today
  no v0 action has ever executed; `executed`, `execution_allowed`, and `execution_started` are
  false everywhere; `result_state` is only ever `dry_run_passed | blocked`.

The revision is the smallest change that removes the error: it points the "only allowed
execution boundary" at the correct artifact (a runtime governed adapter seam) and returns P16 to
its real role.

---

## 4. Runtime Governed Action Adapter Seam Definition

This section freezes the shape of the runtime governed action adapter seam (the "seam") that a
future, separately CTO-approved real-execution phase must build and run v0 actions through. It
is a definition and a lock, not an implementation. P22-E0 ships none of it.

### 4.1 The seam is the single runtime execution boundary

The seam is the ONLY boundary through which a v0 action may really execute at request time.
Execution that bypasses the seam (direct in-process calls, side channels, the P16 worktree
executor, or any generic code-execution surface) is forbidden. The seam composes the unchanged
gates G1-G4 and G7 around a per-action adapter (G6), and adds the runtime disciplines below.

### 4.2 Seam properties (all required, conjunctive)

1. **Per-action adapter only.** Each allowlisted v0 action has exactly one named, bounded
   adapter. There is no generic dispatcher that takes an arbitrary action string and runs it;
   the seam resolves an allowlisted `action_type` to its one adapter and refuses everything
   else, including every excluded action.
2. **No generic shell / SQL / script / subprocess.** An adapter never accepts a free-form
   command, query, or script body and never spawns a process. It performs a bounded, named
   operation against an explicit platform source only. `subprocess`, `os.system`, `os.popen`,
   `shell=True`, `eval`, and `exec` are forbidden in the seam and in every adapter.
3. **Typed request / response.** The seam accepts a typed, echo-safe execution payload (approval
   id, action_type, scoped tenant_id, requested_state, digests) and returns a typed result. It
   never accepts or returns a raw secret, raw idempotency key, raw request / response body, DSN,
   host:port, auth header, shell / SQL, or tenant business payload.
4. **Preflight gate.** Immediately before the adapter runs, the seam re-validates the full
   precondition set at execution time (not only at dry-run time): executor is identity-only
   super_admin; the durable approval still resolves at `approved_execution_blocked` with
   `quorum_met`; the bound dry-run still matches approval / action / target / executor and is not
   expired; the acknowledgement is present; the action is allowlisted; operator separation holds;
   and the source status is honest for the action class. Any failed precondition blocks (fail
   closed) and emits `execution_denied`.
5. **Before / after / failure audit.** The seam emits exactly one `execution_started` event
   before the adapter runs, exactly one `execution_succeeded` (result_state `executed`) or
   `execution_failed` (result_state `execution_failed`, no state landed) event after, and --
   when applicable -- `execution_compensation_recorded`. No execution and no failure is
   unaudited. Audit fields stay redacted and digest-only per the P22-A never-logged list.
6. **Idempotency guard.** The seam enforces digest-only idempotency: same idempotency-key digest
   + matching payload digest is a replay (returns the original result, no new success audit, no
   second state change); same digest + different payload is a conflict (rejected, audited as
   `execution_denied`, never a second state change). The raw idempotency key is never stored.
7. **Source-status honesty.** The adapter reports the real source status (`known | unknown |
   degraded`) and never fabricates a healthy result. For writes / write-requests an `unknown`
   source blocks; for reads a `degraded` source may return a degraded result that changes no
   state. "Unknown is never healthy" and "null is never zero" hold absolutely.
8. **No tenant business mutation.** No adapter reads, writes, creates, updates, or deletes
   orders, payments, invoices, customers, inventory, or ledgers, and none enters a product /
   payment / billing code path or `product-dev-recovered`. `tenant_id` is a scoped identifier
   only and is never joinable to business tables.
9. **Fail closed.** Any precondition failure, unknown source (for a write / write-request),
   unknown approval state, resolver error, or validation error blocks execution and is audited.
   There is no silent fallback, no degraded write path, and no fabricated passing state.

### 4.3 Adapter contract shape (planning only; P22-E0 implements none of it)

A future real-execution phase realizes, for each allowlisted action, a named adapter that the
seam invokes. The planning shape (field names only, no values, no secrets):

```text
GovernedAdapterRequest {
  durable_approval_id   : uuid       -- required. Re-resolved and re-validated by the preflight gate.
  action_type           : enum       -- required. An allowlisted v0 action_type with one adapter.
  tenant_id             : uuid       -- nullable. Scoped id only; null for platform-wide.
  requested_state       : enum       -- nullable. Null for reads / no-target actions.
  dry_run_ref           : uuid       -- required. A still-valid passed dry-run for the same binding.
  execution_ack         : bool       -- required. The typed acknowledgement.
  idempotency_key_digest: char(64)   -- required. SHA-256 of the client key; raw key never stored.
  payload_digest        : char(64)   -- required. SHA-256 of the canonical execution payload.
  actor_id              : varchar    -- required. Identity-only super_admin executor (from the token).
  correlation_id        : varchar    -- nullable.
}

GovernedAdapterResponse {
  execution_request_id  : uuid            -- required. The recorded execution request.
  action_type           : enum            -- required.
  result_state          : enum            -- required. executed | execution_failed | blocked.
  source_status         : enum            -- required. known | unknown | degraded.
  degraded_reason       : string          -- nullable. Present only for a degraded read.
  executed              : bool            -- required. true only when result_state == executed.
  redaction_applied     : bool            -- required. DEFAULT true.
  failure_reason_redacted : string        -- nullable. Redacted; present only on execution_failed.
}
```

The adapter never returns a raw body, a secret, or a tenant business payload. The seam wraps the
adapter call with the preflight gate (4.2.4) and the audit triple (4.2.5); the adapter itself is
a bounded read or a reversible write against an explicit platform source.

### 4.4 Seam vs P16 -- the separation, restated

| Concern | Boundary | Activity | Audit unit | Invoked at request time? |
|---|---|---|---|---|
| Agent code-change mission | P16 worktree harness (`scripts/platform_worktree_executor.py`) | A worker changes files in an isolated git worktree | Changed files vs expected files + forbidden paths | No |
| Runtime controlled action | Runtime governed action adapter seam (defined here) | A bounded, named v0 action runs behind G1-G4 + G7 | `execution_started` / `execution_succeeded` / `execution_failed` | Yes (in a future approved phase) |

The seam does not call the P16 harness and the P16 harness does not call the seam. They are
different boundaries for different activities.

---

## 5. `backup.check` Future Path

`backup.check` remains the lowest-risk READ-FIRST action and the intended first real-execution
candidate, but P22-E0 fixes two preconditions that must hold before it can begin:

1. **The runtime governed adapter seam must be CTO-accepted and realized (at least as a
   non-executing skeleton).** `backup.check` may not begin until the seam exists, because G5 (as
   revised) forbids any other execution boundary. There is no grandfathered direct-read path.
2. **The `backup.check` data source must be explicitly identified before implementation.** The
   adapter must read a real, named platform backup / status source (or operate under an explicit
   degraded / unknown contract). It must not fabricate a healthy backup status.

When both hold, the `backup.check` adapter refreshes and reads backup STATUS only. It is
read-only, changes no state, performs NO real restore, mutates NOTHING, and runs NO shell / SQL /
script / subprocess. A degraded source may return a degraded result (changes no state); an
unknown source never fabricates health. Its audit shape is `execution_started` /
`execution_succeeded` (degraded reads still land as `executed` with a degraded result) /
`execution_failed`.

P22-E0 does not implement `backup.check` and does not choose its data source; it only fixes the
two preconditions above so a future phase can begin without repeating the E0 stop.

---

## 6. P17 Dependency -- Backup Source Honesty

`backup.check` reads backup status, and backup status is a P17 sub-contract. The as-built P17
state on `origin/platform-dev` is explicit and honest: the backup system source is not yet
wired, so every registry assembles `backup_status = None` with the reason "Backup system source
is not yet wired; backup status is unavailable." P22-E0 fixes the rules that govern how a future
`backup.check` adapter may treat that source:

1. **A real source, or an explicit degraded / unknown contract -- never a fabricated healthy
   status.** A future `backup.check` adapter reads either a real platform backup / status source
   (when one is wired) or operates under an explicit degraded / unknown contract that surfaces
   the unavailability honestly. It never synthesizes `last_backup_status = "success"` or a fresh
   `last_backup_at` to make an unavailable source look healthy.
2. **Unknown is never healthy; null is never zero.** These P10 / P17 / P22 invariants hold
   absolutely inside the adapter. An `unknown` source does not produce a passing read for a write
   semantics; a `null` count or timestamp is never reported as zero or fresh.
3. **Degraded is reads-only and changes no state.** The only degraded allowance is for a read
   (`backup.check`, `provisioning.recheck`): a degraded source may return a degraded result with
   a `degraded_reason` and changes no state. There is no degraded write path.
4. **Freshness still rules.** P17's "a `last_backup_status` of `success` is valid only when
   `last_backup_at` is fresh and the source is `available`" rule is inherited unchanged; the
   adapter never downgrades that discipline.

P22-E0 wires no source and changes no P17 code. It records the dependency so a future phase must
prove the source (or accept an explicit degraded contract) before `backup.check` can execute.

---

## 7. Acceptance Criteria (contract + revision)

P22-E0 is accepted only when ALL of the following hold (a future real-execution phase is accepted
only when it additionally satisfies revised G5 + G1-G4 + G6-G7 and section 9):

1. **P22-E0 is docs-only.** No runtime code, backend, frontend, migration, alembic change, table,
   test code, or dependency change ships in P22-E0.
2. **The E0 STOP retrospective is accurate.** Section 2 records the four as-built facts and the
   boundary-conflict table that blocked the attempted P22-E slice, with file-level evidence.
3. **G5 is revised, not relaxed.** Section 3 replaces OLD G5 with NEW G5 and returns P16 to its
   development-time / agent-worker role; no gate is waived and no hard stop is lifted.
4. **The seam is the only runtime execution boundary.** Section 4 fixes the runtime governed
   action adapter seam as the single boundary a future real execution may run through; direct
   in-process execution, side channels, and the P16 worktree executor are all rejected at request
   time.
5. **Per-action adapters only; no generic executor.** Section 4.2.1-4.2.2 fixes one named, bounded
   adapter per allowlisted action and forbids any generic shell / SQL / script / subprocess
   surface in the seam or any adapter.
6. **Preflight gate at execution time.** Section 4.2.4 requires re-validation of the full
   precondition set immediately before the adapter runs; any failure blocks and is audited.
7. **Audit before / after / failure.** Section 4.2.5 requires the full audit triple on every real
   execution; no execution or failure is unaudited.
8. **Idempotency is digest-only.** Section 4.2.6 requires replay vs conflict handling with no
   duplicate success and no stored raw key.
9. **Source-status honesty.** Section 4.2.7 and section 6 require honest known / unknown /
   degraded reporting; unknown is never healthy; degraded is reads-only and changes no state; no
   fabricated healthy backup status.
10. **No tenant business mutation.** Section 4.2.8 forbids any adapter from touching orders,
    payments, invoices, customers, inventory, ledgers, product code, or `product-dev-recovered`.
11. **Fail closed.** Section 4.2.9 requires every precondition failure, unknown source, resolver
    error, or validation error to block execution and be audited; no silent fallback.
12. **`backup.check` is gated twice.** Section 5 fixes that `backup.check` may not begin until
    (a) the seam is CTO-accepted and realized and (b) its data source is explicitly identified;
    it remains read-only and performs no real restore.
13. **P16 is untouched.** P22-E0 changes no P16 code, contract term, or asset; P16 remains the
    development-time / agent-worker file-change audit harness.
14. **No migration / auth / dependency change.** P22-E0 ships no migration, no alembic change, no
    table, no auth / RBAC / session / tenancy rewrite, and no package / lockfile change.
15. **platform-dev untouched.** `origin/platform-dev` is not merged and not pushed from P22-E0;
    only the isolated P22-E0 branch carries the changes.
16. **P22-E1 not started.** P22-E0 begins no backend runtime work; P22-E1 may begin only after
    CTO acceptance of E0 (section 9).
17. **Counterexamples covered.** Section 8 enumerates the misuse patterns the revised lock
    rejects, including P16-at-runtime, generic subprocess, shell / SQL / script wrapper, fake
    backup source, approval equals execution, and dry-run equals execution.
18. **No execution in P22-E0.** P22-E0 performs no execution, dispatches no worker, drains no
    queue, invokes no harness, and runs no shell / SQL / script / subprocess.

---

## 8. Counterexamples (the revised lock must reject these)

Each of the following is REJECTED by the revised lock. They are the high-value misuse patterns;
the P16-at-runtime error that caused the E0 stop, the generic executor family, the fake backup
source, and the "approval / dry-run equals execution" family are called out explicitly.

1. **P16 worktree executor invoked at runtime.** A real execution that calls
   `scripts/platform_worktree_executor.py` (or any P16 asset) at request time to run a v0 action
   -- rejected. (NEW G5; P16 is a development-time file-change audit harness, not a runtime
   executor.)
2. **Direct in-process execution.** A real execution that calls an adapter directly, bypassing
   the seam's preflight gate and audit -- rejected. (NEW G5; the seam is the only boundary.)
3. **Generic subprocess executor.** An adapter or seam that spawns a process (`subprocess`,
   `os.system`, `os.popen`, `shell=True`) to run an action -- rejected. (Section 4.2.2.)
4. **Generic shell wrapper.** An adapter that accepts a free-form shell command string and runs
   it -- rejected. (Section 4.2.2; G6.)
5. **Generic SQL executor.** An adapter that accepts a free-form SQL statement and runs it --
   rejected. (Section 4.2.2; G6.)
6. **Generic script runner.** An adapter that accepts a script body (Python / JS / other) and
   runs it via `eval` / `exec` or otherwise -- rejected. (Section 4.2.2; G6.)
7. **Fake backup source / fabricated health.** A `backup.check` adapter that synthesizes
   `last_backup_status = "success"` or a fresh `last_backup_at` for an unwired / unknown / stale
   source -- rejected. (Section 6; unknown is never healthy.)
8. **Approval equals execution.** A path that runs a v0 action because a durable, quorum-met
   approval exists at `approved_execution_blocked`, with no seam, no dry-run, no ack, no adapter,
   and no audit -- rejected. (G1 is a precondition, not execution.)
9. **Dry-run equals execution.** A path that runs a v0 action because a dry-run returned
   `executable == true`, with no seam, no real approval binding, no ack -- rejected. (G2 is a
   precondition, not execution.)
10. **Acknowledgement equals execution.** A path that runs a v0 action because the operator
    supplied `execution_ack` -- rejected. (G3 is a precondition, not execution.)
11. **Preflight skipped at execution time.** A seam that trusts the dry-run-time precondition
    check and does not re-validate state / quorum / source / separation immediately before the
    adapter runs -- rejected. (Section 4.2.4.)
12. **Unaudited execution or failure.** A real execution that lands with no `execution_started` /
    `execution_succeeded` (or `execution_failed`) audit triple, or a failure with no
    `execution_failed` event -- rejected. (Section 4.2.5; G7.)
13. **Duplicate success on replay.** An idempotent replay that emits a second `execution_succeeded`
    event or applies a second state change -- rejected. (Section 4.2.6.)
14. **Tenant business mutation.** A v0 execution that reads or writes an order, payment, invoice,
    customer, inventory, or ledger record, or enters product / payment / billing code --
    rejected. (Section 4.2.8; section 5 hard stops.)
15. **Excluded action executes.** A `tenant.pause` / `tenant.resume` / `lifecycle.transition` /
    real restore / schema migration / data deletion execution -- rejected forever. (P22-D section
    5; unchanged by P22-E0.)
16. **Non-super_admin or self / checker executor.** A `support_operator`, `engineering_operator`,
    tenant admin, tenant-contextual super_admin, or tenant-scoped token executing a v0 action, or
    an executor who is the maker or a checker on the approval -- rejected and audited. (G1 / G4 /
    operator separation; unchanged.)
17. **Silent-fallback / fabricated passing state.** A seam that takes a degraded / read-only
    fallback path and silently mutates, or that fabricates a passing state when a source is down
    or a resolver errors -- rejected. (Section 4.2.9; fail closed.)
18. **`backup.check` begins before the seam or the source.** A first real-execution slice that
    starts `backup.check` before the seam is CTO-accepted and realized, or before its data source
    is explicitly identified -- rejected by the P22-E1 entry gate. (Section 5; section 9.)
19. **P22-E0 ships runtime code.** Any backend, frontend, migration, adapter, test, or dependency
    change shipped inside P22-E0 itself -- rejected; P22-E0 is docs-only. (Section 1.2.)
20. **Relaxing the revised lock without a revision.** Treating any seam property (4.2.1-4.2.9) as
    waivable, or executing with fewer than revised-G5 + G1-G4 + G6-G7 -- rejected. (Section 3;
    section 4.)

---

## 9. P22-E1 Entry Gate (the earliest runtime-seam work)

P22-E1 is the earliest phase that MAY implement a backend-only, NON-EXECUTING runtime governed
adapter seam skeleton. It is NOT started by P22-E0. P22-E1 may begin ONLY after explicit CTO
acceptance of P22-E0, and only under these constraints:

1. **Backend-only, non-executing skeleton.** P22-E1 may add the seam shape only: a per-action
   adapter registry (names only, no real adapter bodies for any action that lacks a proven
   source), the preflight gate (reusing the P22-B precondition evaluator), the audit wiring
   (`execution_started` / `execution_succeeded` / `execution_failed` / `execution_denied`), and
   the idempotency guard. It dispatches NO worker, drains NO queue, and runs NO adapter that
   performs a real side effect.
2. **No real `backup.check` until the source is proven.** Even after the skeleton exists,
   `backup.check` does not really execute until its data source is explicitly identified and
   accepted (section 5 / section 6). The skeleton may carry a `backup.check` adapter slot that
   returns a non-executing / not-implemented result; it does not fabricate a read.
3. **No product / business mutation.** P22-E1 touches no orders, payments, invoices, customers,
   inventory, ledgers, product code, or `product-dev-recovered`, and enters no payment / billing
   path.
4. **No P16 change, no generic executor.** P22-E1 changes no P16 code and introduces no generic
   shell / SQL / script / subprocess surface. The AST invariants that today guard the P22 source
   are revised only to the minimum extent needed to permit the named seam symbols, and only after
   CTO acceptance -- never to permit a generic executor.
5. **No migration / auth / dependency change unless separately approved.** P22-E1 defaults to no
   migration, no alembic change, no auth / RBAC / session / tenancy rewrite, and no package /
   lockfile change; any exception is a separate explicit approval.
6. **Full gate compliance when execution arrives.** The first real adapter execution (earliest, a
   proven `backup.check`) satisfies revised G5 + G1-G4 + G6-G7 in full and runs only through the
   seam.

P22-E0 is the contract; P22-E1 is the gated skeleton. Until P22-E1 is CTO-approved and lands a
non-executing seam skeleton, the controlled execution v0 surface remains exactly the
non-executing P22-A / P22-B / P22-C baseline closed out in P22-D, with the corrected G5 on the
books.

---

## 10. Relationship to P22-A and P22-D

- **P22-A** (the controlled execution v0 contract) is unchanged. The allowlist, the exclusion
  list, the twelve preconditions, the dry-run / request / result models, the nine-state
  execution-record enum, the audit contract, the idempotency rules, the safety rules, and the
  operator-separation policy all stand as written.
- **P22-D** (the readiness closeout + real-execution design lock) is revised in exactly one
  place: section 3 gate G5. OLD G5 ("P16 governed harness only") is replaced by NEW G5 ("runtime
  governed action adapter seam only"), and P16 is returned to its development-time /
  agent-worker role (P22-D section 2 / section 3 G5 commentary is superseded by section 3 of this
  contract). Every other P22-D term -- G1-G4, G6-G7, the allowlist matrix, the permanent hard
  stops, the acceptance criteria, the counterexamples, and the P22-E entry gate -- is unchanged
  in substance; where P22-D referenced "the P16 governed harness" as the runtime boundary, this
  contract is the authoritative correction.
- **P22-B / P22-C** (the non-executing backend skeleton and frontend console) are unchanged and
  remain the as-built non-execution baseline. P22-E0 touches neither.

In one line: P22-E0 corrects the one gate (G5) that mis-stated the runtime execution boundary,
defines the seam that replaces it, and gates a later non-executing skeleton -- without shipping
runtime code, weakening any other gate, lifting any hard stop, or executing anything.

---

## 11. Docs-Only Statement

P22-E0 ships:

- `docs/ai/PLATFORM_PRODUCT_P22_RUNTIME_GOVERNED_ADAPTER_CONTRACT.md` -- this contract (the E0
  STOP retrospective, the G5 revision, the seam definition, the `backup.check` path, the P17
  dependency, the acceptance criteria, the counterexamples, and the P22-E1 entry gate).
- `docs/ai/README.md` -- one cumulative-state sentence appended to the P22 read-order paragraph
  (ASCII-only).
- `ai-ledger/platform/2026-07-02_p22e0_runtime_governed_adapter_contract.md` -- the ledger.

There is **no runtime code, no backend, no frontend, no migration, no alembic change, no table,
no test code, and no dependency change** in P22-E0. P22-E0 revises the G5 gate, defines the
runtime governed action adapter seam, and gates a future non-executing skeleton; it does not
execute, dispatch, queue, schedule, migrate, or implement any execution, adapter, approval,
action, storage, or P16 path. **Approval is not execution, a passed dry-run is not execution,
and the P16 worktree harness is not a runtime executor.** Real execution of any v0 action remains
reserved for a separately CTO-approved phase that must run through the runtime governed action
adapter seam behind revised G5 + G1-G4 + G6-G7. **P22-E1 is not started.**
