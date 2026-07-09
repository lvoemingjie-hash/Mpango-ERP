# P22-F Controlled Execution v0 Closeout

**Phase:** P22-F -- controlled execution v0 closeout (docs-only)
**Date:** 2026-07-04
**Branch:** `codex/platform-p22e4-backup-check-console-2026-07-03` (carried with P22-E4)
**Base:** `bfbd780` (`origin/platform-dev`)
**Author:** Codex (Claude worker)
**Status:** Complete. Docs-only closeout. Records the P22-A..P22-E4 lineage, fixes the v0
boundary, and enumerates the P23+ gates. P23+ is NOT started.

---

## 1. Purpose

This is the closeout for the Controlled Execution v0 program (P22). It states, in one
place, what v0 IS, what it is NOT, and what the next (separately approved) phase must
settle before any real execution may exist. It changes no code.

---

## 2. The v0 boundary (one paragraph)

**Controlled execution v0 is read / record / non-executing.** An operator can view the
closed action catalog, run a no-mutation dry-run (a precondition validator), record a
non-executing execution request (recorded only, behind durable approval + quorum + ack),
and list/read recorded requests. The `backup.check` action is source-visible only: it reads
the proven P17-D-C backup / status source and reports an honest `known | unknown | degraded`
verdict (P22-E3 backend probe + P22-E4 console surface). **No real execution engine
exists** in any P22 phase: there is no worker, no queue drain, no governed-harness run, no
shell / SQL / script / subprocess, and no backup / restore / dump. Every response carries
`executed === false`, `execution_allowed === false`, `execution_started === false`, and a
`result_state` of only `dry_run_passed | blocked`. Approval is not execution; durability is
not execution; a passed dry-run is not execution; a recorded request is not execution; a
read is not execution.

---

## 3. Phase lineage (P22-A .. P22-E4)

| Phase | Deliverable | Status |
|---|---|---|
| **P22-A** | The v0 contract: the seven-action allowlist; executor = identity-only super_admin; operator separation; the dry-run / record / read shape; the closed block-reason vocabulary; the read/record/non-executing invariant; the full nine-state execution-record enum (only the two non-executing entry states realized in v0). | Contract (docs) |
| **P22-B** | Backend non-executing skeleton: catalog, no-mutation dry-run, request recording (digest-only, redacted), request list/read. In-memory store; every response non-executing. | Landed |
| **P22-C** | Operator console (frontend): `PlatformControlledExecutionConsolePage` -- catalog, dry-run form, record section (gated on passed dry-run + ack), queue/read. Non-executing banner; raw idempotency key never echoed (only its digest). | Landed |
| **P22-D** | Readiness lock: the precondition/lock semantics that gate a recorded request (state / quorum / source / target / operator separation / idempotency). | Landed |
| **P22-E0** | Runtime governed action adapter contract: revised G5 -- any future real execution must run through a per-action, no-shell/SQL/script/subprocess, preflight-gated, before/after/failure-audited, digest-idempotency-guarded, source-honest, no-tenant-mutation, fail-closed seam (not the P16 dev/agent worktree harness). | Merged (`317c407`) |
| **P22-E1** | Non-executing seam skeleton: `adapters.py` (allowlist-only NON-EXECUTING registry; every adapter `not_implemented`; `backup.check` = `source_unknown` slot) + `seam.py` (`evaluate_preflight_gate` reuses the P22-B precondition evaluator; audit shape templates; digest-only idempotency; `realized_execution`/`executed` always false). Import-tested only; no route. | Merged (`e87323f`) |
| **P22-E2** | Backup source discovery gate (docs-only). Verdict SOURCE_UNKNOWN at the time: no real backup / status source existed. Fixed the P22-E3 entry gate (read-only probe only, never execution, behind the seam). | Docs (merged) |
| **P22-E3** | Read-only `backup.check` source probe bound to the PROVEN P17-D-C backup / status source (migration 021 durable read path). `source_probe.py` reuses P17 verbatim; honest P17->P22 map (`fresh_success`->known; stale/failed/partial/in_progress->degraded; no-outcome/read-failure->unknown fail-closed). R1 wired it into a guarded read-only `GET /backup-check/source` route. Static adapter stays `not_implemented` (G15). | Merged (`bfbd780`) |
| **P22-E4** | Console visibility: frontend type + API client + a read-only console section surfacing the P22-E3 verdict honestly (known/degraded/unknown; unavailable never healthy; only allowlisted fields; no execute control). Backend untouched. | This branch |

---

## 4. What v0 proved (and what it deliberately did NOT)

**Proved:**
- A closed, allowlisted, identity-only-super_admin execution surface with operator
  separation and digest-only idempotency can be built and tested end-to-end (backend +
  console) while executing nothing.
- A read-only source binding (`backup.check` -> P17-D-C) can be added behind the governed
  seam, surfaced to operators, and kept source-honest and fail-closed -- still without
  executing anything.
- The non-execution invariant is testable and enforceable: AST scans forbid execution
  primitives across the P22 backend modules, and every response shape pins the execution
  flags false.

**Deliberately NOT proved (out of v0 scope):**
- That any action actually runs. No adapter is realized; `result_state` never reaches
  `executed`; no `execution_succeeded` audit event is ever written.
- That a real backup / restore / migration / lifecycle side effect can be produced. Real
  restore and schema migration are excluded from v0 forever; `backup.check` reads status
  only.

---

## 5. P23+ gates (NOT started; each requires separate CTO approval)

Before any real execution may exist, P23+ must settle -- at minimum -- the following. P22
does not design or build these; it only names them.

1. **Real execution policy.** A CTO-approved policy for which v0 action may actually execute
   first, under what boundary (the revised G5 seam from P22-E0), and with what
   side-effect contract. The seam shape exists; no adapter body does.
2. **Rollback / recovery.** Compensation semantics for a real side-effecting action that
   fails partway: the `execution_failed` / `compensation_required` /
   `compensation_completed` states are typed in v0 but never assigned; P23+ must realize
   them (or bind the action to a system with its own atomicity).
3. **Notification.** Operator / stakeholder notification on execution start / success /
   failure / denial. v0 records audit-shape templates and redacted events in memory only;
   there is no durable notification fan-out.
4. **Audit retention / export.** A durable, retained, exportable execution audit (today the
   P22 audit is in-memory / ephemeral; the P17-D-C source and the platform audit log exist,
   but the execution-record audit is not durably retained to a table with retention/export).
5. **AI operator copilot boundary.** If an AI operator / copilot may ever propose or drive a
   controlled action, the boundary (what it may draft, what still requires the human
   identity-only-super_admin executor + maker-checker + quorum + ack) must be fixed before
   that path exists. v0's identity-only-super_admin executor and operator-separation rules
   are the foundation; the copilot policy itself is a P23+ decision.

A non-goal of this closeout: scheduling or sequencing P23+. The order and the first real
action are CTO decisions.

---

## 6. Explicit Statements

- **v0 is read / record / non-executing.** No real execution engine exists in any P22 phase.
- **`backup.check` is source-visible only.** It reads the P17-D-C source and reports status;
  it does not back up, restore, or dump.
- **This closeout changes no code.** Docs-only (this ledger + the sibling P22-E4 report).
- **P23+ is NOT started.** The gates in section 5 are enumerated, not begun.
- **platform-dev untouched by P22-E4.** Only the isolated E4 branch is published; merge is a
  separate CTO decision.
