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

Recommended:

- `product-dev` for active ERP work
- `platform-dev` for platform line work
- short-lived feature branches off the relevant long-lived branch

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
