# Dual Machine Development Protocol

This protocol governs parallel development across two machines for Mpango ERP.

## Scope

- Two machines (a Windows machine and a Lubuntu machine) are available; the
  protocol's governance rules bind all of them equally
- Work is assigned to named executors by written CTO directive, not by
  machine: the historical static mapping of "Windows = product line,
  Lubuntu = platform line" is SUPERSEDED (2026-10-13) and must not be used to
  infer authority in a new task
- Every executor, on either machine, follows the same repository memory and
  governance rules

## Current CTO Decision (2026-10-15)

Two parallel preparation lines are active under paired directives, and
neither line owns a machine:

- ZCode-L (executing on Lubuntu): RC1 docs-only freeze of the five
  governance/release docs from the product acceptance baseline `88c7d815`
  (`CTO-AUTH-MVP-RC1-DOCS-FREEZE-AND-CI-ADMISSION-L-R1-20261015`), plus the
  one-pass current-CI admission design; writes only the five named docs
  paths; no product, test, or CI bytes, no services, no push
- ZCode-W (executing on Windows): minimal pilot manual and go-live rehearsal
  preparation; writes only its own output directory; candidate source
  read-only; no repo, runtime, or VPS actions
- CTO: final technical ruling on scope, candidates, the one finite CI
  correction scope and budget, integration, promotion, and release

Closed lines (2026-10-15): Codex-L's S2 "reorder from own history"
implementation is closed by the CTO's final acceptance at `88c7d815`
(`PASS__88c7d815__FROZEN_FUNCTIONAL_SCOPE`); the proposed Kilo-L independent
S2 acceptance was closed by the CTO's own native-result review. The earlier
2026-10-13 dual-track assignment block (Codex-L S2 implementation, ZCode-W
governance-doc candidates, Kilo-L independent acceptance) is HISTORY.

Standing constraints for both lines: product work must not create
architectural drift from the current ERP core; push, remote CI, protected
merge, and deployment are NOT AUTHORIZED unless a specific directive grants
them. A CI admission design is a plan for one CTO decision, not a green gate
and not a dispatch authorization.

## Strategic Rule

Product line and platform line are parallel only in execution, not in authority.

When conflict appears:

1. Wholesaler ERP operational readiness wins
2. Tenant isolation and contract integrity win over speed
3. Platform abstractions must serve the product, not force product rewrites

## Repository Truth

Both machines must treat the repository as the shared memory system.

The following are not reliable shared memory:

- Local chat history
- Local desktop app state
- Personal notes outside the repo
- Verbal recollection of old Web conversations

The following are the approved shared memory surfaces:

- `docs/ai/CTO_COCKPIT.md`
- `docs/ai/CTO_CONTEXT.md`
- `docs/ai/PROJECT.md`
- `docs/ai/PROJECT_MEMORY.md`
- `docs/ai/AGENT_DELEGATION_PROTOCOL.md`
- `decision-register/`
- `ai-ledger/`
- `docs/contracts/`

## Executor Roles

Current roles (2026-10-15). A role travels with the named executor and its
directive, not with a machine.

### Product implementation (no active line; last: Codex-L, S2 reorder)

- CLOSED 2026-10-15: the S2 reorder slice was implemented by Codex-L within
  its directive scope with real PG/HTTP/browser evidence and accepted at
  `88c7d815`. Any new product implementation line requires a fresh CTO
  directive, and under it the executor must not edit the four `docs/ai/`
  governance documents, migrations 001-040, DB provisioner,
  bootstrap/readiness, auth/cache core, CI, dependency locks, or baseline,
  and must not implement S3 negotiation, refunds, partial fulfillment,
  credit limits, or a shared stock pool without a new authorization.

### Documentation, release preparation, and CI admission (currently ZCode-L)

Primary responsibility (2026-10-15 line, executing on Lubuntu):

- RC1 docs-only freeze: bring the accepted S1/S2 state into PROJECT.md,
  PROJECT_MEMORY.md, CTO_CURRENT_OPS.md,
  DUAL_MACHINE_DEVELOPMENT_PROTOCOL.md, and
  `docs/releases/mvp-20261031/RC1-PLAN.zh-CN.md` as one normal docs-only
  successor of BASE `88c7d815`
- the one-pass current-CI admission design (read-only; a plan for one CTO
  decision, not a green gate)

Must not:

- write product code, CI workflows, or test tooling
- start services, run test suites/collect, or merge anything
- push, or touch any path outside the five named docs paths

### Pilot manual and ops rehearsal preparation (currently ZCode-W)

Primary responsibility (2026-10-15 line, executing on Windows):

- minimal trial manual and go-live rehearsal material in its own output
  directory; candidate source read-only; no repo edits, no runtime, no VPS
  actions

### Independent acceptance (no active line; last proposed: Kilo-L, S2)

- CLOSED 2026-10-15: the CTO closed the S2 acceptance question by directly
  reviewing the native results (V3 + browser supplement), so the proposed
  Kilo-L acceptance was not dispatched. Future independent acceptance lines
  are dispatched only by a new directive and must not inherit an author's
  PASS.

### Final ruling (CTO)

- scope, risk, contracts, integration/merge decisions, acceptance verdicts

### Historical machine-role text (superseded 2026-10-13)

The earlier "Machine A - Product Track (Windows)" and "Machine B - Platform
Track (Lubuntu)" sections described the founding phase when the product line
ran on Windows and the platform line explored on Lubuntu. They are retained
in earlier versions of this file and no longer describe current authority.
The platform-track start conditions below remain useful governance for any
future platform slice, applied to whichever executor receives it.

## Start Condition For Platform Coding

A platform-line executor should not begin broad platform implementation until these are true:

1. The tenancy model is explicitly aligned with repository decisions
2. Shared docs are pulled and readable locally
3. Platform scope for the next slice is bounded and approved
4. Write ownership is clear
5. Migration impact is reviewed

Until then, a platform-line executor should stay in design-review and scaffolding mode.

## Tenancy Alignment Rule

Platform proposals must not silently override the active tenancy architecture.

If a proposal uses a different tenancy model from the repository:

- do not implement it directly
- write the discrepancy down
- escalate through `decision-register/`
- wait for CTO approval before coding against the new assumption

## Frozen Zone Rule

The following areas are frozen unless explicitly approved by CTO:

- `backend/core/`
- `backend/api/context/`
- `backend/api/middleware/`
- `backend/database/session.py`

Every executor should assume these are read-only unless a written approval exists in repo memory.

## Branch Protocol

- `main` is release-candidate only
- Active work uses the local branch named by its directive from the
  directive-named BASE (current freeze line: `codex/mvp-rc1-freeze-20261015`
  off acceptance baseline `88c7d815` in a `--no-hardlinks` clone without
  alternates; the S2 line's branch was `codex/s2-reorder-r1-20261013` off
  S1 BASE `41fd3adb`); long-lived branch names and remotes must not be
  silently equated with work in progress
- Cross-cutting work requires explicit coordination before merge
- A local-only branch state is not sufficient shared truth when another
  machine or CTO must review it — use an authorized visibility mechanism
  (push when authorized, otherwise a handoff package)

Recommended:

- short-lived, directive-named feature branches off the relevant baseline
- record branch name, BASE, and tip identity in the task handoff

## Start-Of-Task Sync Gate

Before a machine starts a new non-trivial task, it must:

1. Fetch the latest remote branch state
2. Read:
   - `docs/ai/README.md`
   - `docs/ai/PROJECT.md`
   - `docs/ai/PROJECT_MEMORY.md`
3. Confirm the active branch and current blocker list are still accurate
4. Refuse to proceed on stale assumptions if repo memory and local branch state disagree

## Visibility Push Rule

Current constraint (2026-10-15): push and remote CI are NOT AUTHORIZED unless
a specific CTO directive grants them. When push is not authorized, review
visibility is provided through CTO-addressed handoff packages and delivery
directories (for example `AI_REPORT_INBOX/.../delivery/`), which carry the
candidate content and diffs instead of a remote ref.

When a directive does authorize pushes, there are two distinct push states:

1. Visibility push
   - allowed when another machine / CTO cannot inspect a local-only commit
   - purpose is review visibility, not approval to continue or merge
2. Approval push / promotion push
   - happens only after CTO review says the slice is approved for continuation, closeout, or branch promotion

Agents must state which kind of push they are performing.
Do not treat "pushed so CTO can see it" as equivalent to "approved to merge/promote".

## PROJECT.md Update Gate

`docs/ai/PROJECT.md` must be updated whenever any of the following changes:

- active branch ownership
- accepted / not accepted status of a slice
- current blocker list
- next expected action
- recovered-vs-backup branch role

If another machine depends on this knowledge, the update must be pushed remotely or it is not reliable shared memory.

## Merge Gates

### Product Merge Gate

Before merge:

- relevant scenarios pass or move closer to passing
- Boot Contract evidence exists when startup is affected
- API contract changes are explicit
- ledger entry exists

### Platform Merge Gate

Before merge:

- no contradiction with active tenancy and auth model
- no business-table overreach
- migration impact reviewed
- product line is not blocked
- ledger entry exists

## Database Governance Across Two Machines

Only one machine should own a given migration slice.

Rules:

- do not create parallel migrations touching the same concern
- do not let product and platform edit the same migration chain blindly
- review `alembic heads` before merge
- record cross-track migration decisions in `decision-register/` if they are durable

## Weekly Sync Minimum

At least once per sync cycle, both tracks must reconcile:

- roadmap priority
- contract changes
- migration state
- tenancy assumptions
- branch state
- unresolved risks

Record meaningful outcomes in repo docs, not just chat.

## CTO Review Handshake

For dual-line work, the expected node sequence is:

1. Proposal or implementation slice completed locally
2. Self-check gate passes
3. Repo memory updated (`PROJECT.md` if needed, ledger always)
4. If CTO is on another machine, perform a visibility push
5. CTO reviews against the pushed state
6. CTO either:
   - approves continuation
   - requests correction
   - approves promotion / closeout

Skipping step 3 or 4 creates split-brain memory and stale-agent risk.

## Current Recommended Platform Sequence

For a platform-line executor, the safest order is:

1. Sync shared memory docs locally
2. Review tenancy alignment against current repo decisions
3. Write a platform scope note for the first approved slice
4. Implement only a narrow slice such as tenant registry documentation or scaffolding
5. Reconcile before any deeper data-model work

## Definition Of Success

Two-machine development is successful when both machines accelerate delivery without causing:

- architectural drift
- tenancy inconsistency
- migration collisions
- split-brain project memory
