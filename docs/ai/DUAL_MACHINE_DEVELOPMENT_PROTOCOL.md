# Dual Machine Development Protocol

This protocol governs parallel development across two machines for Mpango ERP.

## Scope

- Machine A: product line development on Windows
- Machine B: platform line exploration and implementation on Lubuntu
- Codex may operate on both machines, but both must follow the same repository memory and governance rules

## Current CTO Decision

At this moment, the product line is active and the platform line is not yet implementation-active.

Therefore:

- Machine A remains the delivery-critical track
- Machine B starts in architecture-and-foundation mode, not feature expansion mode
- Platform work must not create architectural drift from the current ERP core

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

## Machine Roles

### Machine A - Product Track

Primary responsibility:

- retailer workflows
- wholesaler workflows
- order, inventory, payment, reporting usability
- frontend integration
- product-side bug fixing and hardening

May change:

- product frontend
- product backend
- product-side scenarios and tests
- product documentation

Should avoid:

- speculative platform abstractions
- platform-first schema changes

### Machine B - Platform Track

Current responsibility:

- validate platform architecture against existing product contracts
- prepare platform documentation, module boundaries, and migration governance
- prototype only low-risk platform slices after explicit approval

Allowed initial focus:

- tenant registry design
- admin console information model
- audit log design
- billing model design
- branch and migration governance

Must avoid before explicit approval:

- rewriting the product tenancy model
- changing core auth assumptions
- changing frozen product modules
- introducing infra complexity that current scale does not need

## Start Condition For Platform Coding

Machine B should not begin broad platform implementation until these are true:

1. The tenancy model is explicitly aligned with repository decisions
2. Shared docs are pulled and readable locally
3. Platform scope for the next slice is bounded and approved
4. Write ownership is clear
5. Migration impact is reviewed

Until then, Machine B should stay in design-review and scaffolding mode.

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

Machine B should assume these are read-only unless a written approval exists in repo memory.

## Branch Protocol

- `main` is release-candidate only
- Machine A uses a product branch
- Machine B uses a platform branch
- Cross-cutting work requires explicit coordination before merge
- A local-only branch state is not sufficient shared truth when another machine or CTO must review it

Recommended:

- `product-dev` for active ERP work
- `platform-dev` for platform line work
- short-lived feature branches off the relevant long-lived branch

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

There are two distinct push states:

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

For Machine B, the safest order is:

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
