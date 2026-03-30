# Mpango ERP CTO Context

## Mission

Mpango ERP is a multi-tenant wholesale-retail ERP system for the African market. The immediate goal is to make the ERP genuinely usable for real wholesalers while preserving strict tenant isolation and preparing the path to SaaS platform expansion.

## North Star

Success for the current phase means:

- A real wholesaler can run daily operations in the ERP
- Retailer ordering works smoothly end to end
- Tenant isolation remains structurally enforced
- Platform expansion does not derail product delivery

## Current Strategic Frame

Based on `docs/mpango_erp_v0_3_development_master_plan.md`, development follows two tracks:

- Product line: ERP business modules, frontend UI, retailer portal, mobile web
- Platform line: tenant registry, platform admin console, billing, monitoring

This repository is currently strongest on the product line and must protect product usability first.

## Non-Negotiables

- Multi-tenancy is a first-order architectural rule, not an optional feature
- Schema and API changes must follow the documented contracts
- Database changes go through migrations, never ad hoc direct manipulation
- AI work must be auditable through repo docs, decision records, and ledger entries
- GitHub repository contents are the operational source of truth

## Canonical References

- Product overview: `README.md`
- Contracts: `docs/contracts/`
- Master roadmap: `docs/mpango_erp_v0_3_development_master_plan.md`
- Architectural decisions: `decision-register/`
- AI operating rules: `docs/contracts/AI workrules.md`
- Historical engineering knowledge: `docs/`, `docs/architecture/`, `docs/planning/`

## CTO Operating Stance For AI Agents

When acting as CTO or principal engineer, AI agents should optimize for:

1. Business usability before ornamental expansion
2. Correctness and isolation before speed
3. Contract alignment before local convenience
4. Recorded decisions before implicit decisions
5. Incremental, reviewable progress over large speculative rewrites

## Current Risk Areas

- Tenant isolation regressions
- Migration drift between environments
- Authentication and RBAC erosion
- Inventory consistency under concurrency
- Payment and ledger correctness

## Default Working Pattern

Before major work:

- Read this file
- Read `docs/ai/PROJECT_MEMORY.md`
- Read the applicable contracts
- Identify which roadmap phase the task belongs to

After major work:

- Update `ai-ledger/`
- If architecture or policy changed, update `decision-register/`
- If roadmap interpretation changed, update this file
