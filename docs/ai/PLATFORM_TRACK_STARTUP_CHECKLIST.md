# Platform Track Startup Checklist

Use this checklist on the Lubuntu machine before platform-layer coding begins.

## Phase 0 - Local Setup

- Codex desktop client installed
- repository cloned locally
- correct branch checked out
- latest shared memory docs pulled
- local environment boot notes available

## Phase 1 - Required Reading

Read in this order:

1. `docs/ai/README.md`
2. `docs/ai/CTO_COCKPIT.md`
3. `docs/ai/CTO_CONTEXT.md`
4. `docs/ai/PROJECT_MEMORY.md`
5. `docs/ai/DUAL_MACHINE_DEVELOPMENT_PROTOCOL.md`
6. `docs/ai/SHARED_MEMORY_SYNC_PROTOCOL.md`
7. `decision-register/DR-001_schema-per-tenant.md`
8. `docs/contracts/multi_tenancy_spec.md`
9. `docs/arch/tenant-isolation.md`
10. `docs/ai/PLATFORM_PROPOSAL_CTO_REVIEW_2026-03-30.md`

Do not start coding before these are read.

## Phase 2 - Tenancy Alignment

Confirm these statements are understood and accepted:

- the active isolation architecture is `schema-per-tenant`
- JWT carries both `tenant_id` and `tenant_schema`
- search-path routing is authoritative for tenant DB access
- tenant-key filtering is guardrail logic, not the primary tenancy model
- no platform document may override this without a formal decision record

If any statement is disputed, stop and escalate before coding.

## Phase 3 - Platform Boundary Mapping

Before implementation, write down:

- which platform tables belong in `public`
- how platform records relate to `public.wholesalers`
- whether tenant provisioning changes are needed
- which APIs are platform-only versus product-facing
- which frozen zones remain untouched

This mapping should exist in repo docs before the first serious platform PR.

## Phase 4 - First Approved Slice

Choose only one of these to begin:

- tenant registry documentation and scaffolding
- platform admin information model
- audit log boundary and lifecycle design
- billing model documentation only

Do not start with:

- assume role
- broad auth rewrites
- tenancy rewrites
- cross-cutting migration changes

## Phase 5 - Engineering Gates

Before merging platform work:

- migration ownership is clear
- product tables are not modified casually
- bootability impact is known
- ledger entry is written
- shared memory docs are updated if a durable decision emerged

## Phase 6 - Sync Habit

Before every platform session:

- `git pull`
- review changed docs under `docs/ai/`, `decision-register/`, and `ai-ledger/`

After every meaningful session:

- update ledger
- commit shared-memory changes if they matter
- push so the other machine can see the same project state

## Stop Conditions

Stop immediately if platform work implies:

- changing tenancy architecture
- editing frozen product zones
- changing product auth model
- introducing migrations that collide with active product work
- implementing against assumptions that exist only in chat and not in repo memory
