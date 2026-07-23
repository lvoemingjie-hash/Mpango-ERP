# Mpango AI-Native Operating Layer Roadmap

## Status

Recorded strategic direction as of 2026-07-23.

This document is a post-MVP roadmap, not an implementation commitment or a
current release claim. It is informed by the separate Procurement Workspace
blueprint, but it does not import that project's code, database, deployment, or
security model into Mpango ERP.

The current customer-delivery priorities remain operational stability,
clickable credential emails over HTTPS, verified tenant onboarding,
supplier-scoped retailer access, user guidance, and production runbooks.

## Strategic Decision

Mpango should become AI-native by adding a governed operating layer above the
existing ERP, not by replacing the ERP with a chatbot or an autonomous agent.

The intended interaction is:

1. A user states a business goal in natural language.
2. Mpango identifies the intent and converts it into a typed business contract.
3. The contract is normalized and validated against tenant, permission, and
   business rules.
4. Mpango presents the proposed action and its material effects.
5. A human confirms when the action creates business, financial, security, or
   external communication consequences.
6. Existing Mpango APIs and services execute the approved action.
7. The full request, decision, action, result, and actor are audited.

AI may help a user decide and prepare work. It must not become an alternate
authorization, tenancy, accounting, or data-access system.

## Product Fit

The AI operating layer supports Mpango's wholesaler-centric private-channel
positioning:

- the wholesaler remains the primary customer and controls its workspace;
- a retailer interacts within one wholesaler relationship at a time;
- AI may improve ordering, procurement, inventory, finance, and support inside
  the current workspace;
- AI must not aggregate supplier relationships, expose competing prices, or
  turn Mpango into a retailer price-comparison service;
- recommendations derived from one wholesaler's data must not be used in
  another wholesaler's context without a separate approved product and legal
  decision.

Unified identity remains a security and continuity capability. It is not a
license for unified commercial memory or cross-wholesaler inference.

## Reference Architecture

The target control flow is:

```text
User
  -> Mpango AI entry
  -> Intent Router
  -> Typed Business Contract
  -> Normalize and Validate
  -> Policy and Human Confirmation
  -> Governed Tool Registry
  -> Existing Mpango API and Service Layer
  -> PostgreSQL and External Services
  -> Immutable Audit Evidence
```

The AI entry may eventually be presented through `ai.mpango.xyz`, but the
current AI workspace remains an isolated pilot. It must not receive production
ERP authority merely because it shares the Mpango name or VPS.

The customer ERP application remains a separate trusted surface. Any future
connection between the two surfaces requires explicit authentication,
authorization, tenant-context, network, audit, and rollback contracts.

## Workspace Primitives

Future AI-enabled workspaces should share a small set of governed primitives:

| Primitive | Meaning in Mpango |
| --- | --- |
| Object | A tenant-scoped business entity such as an SKU, order, payment, supplier, or retailer relationship. |
| Event | An immutable business occurrence or state transition. |
| Memo | Human or AI-authored context that is non-authoritative until accepted. |
| Decision | A recorded choice with actor, evidence, reason, and approval state. |
| Action | A typed tool invocation against an existing Mpango capability. |
| Agent | A constrained assistant with an explicit purpose, tool allowlist, and tenant scope. |
| Audit | Tamper-evident evidence linking request, decision, execution, and outcome. |

These primitives are coordination concepts. Existing ERP tables and services
remain the system of record unless a separately reviewed migration changes that
contract.

## Non-Negotiable Safety Boundaries

Every AI-assisted capability must satisfy all of the following:

- authenticate through Mpango-controlled identity;
- resolve exactly one authorized tenant context before business-data access;
- enforce the same or stronger RBAC rules as the non-AI API;
- call allowlisted, typed tools rather than generate and execute arbitrary SQL;
- validate tool inputs with deterministic schemas and business rules;
- use idempotency and replay protection for write operations;
- require human confirmation for financial, destructive, external-message, or
  permission-changing actions;
- require maker-checker approval where the underlying business risk warrants it;
- preserve existing ledger, payment, receivable, inventory, and order
  invariants;
- fail closed when context, authorization, contract, or evidence is incomplete;
- record actor, tenant, tool, normalized inputs, approval, result, and error
  classification without logging secrets;
- keep credentials, API keys, raw tokens, and database URLs outside prompts,
  memories, model outputs, and client-visible traces;
- support cancellation, retry, reconciliation, and rollback according to the
  underlying business operation;
- make AI-generated content visibly distinguishable from authoritative
  committed records.

No model output is trusted merely because it is syntactically valid.

## Memory and Data Governance

Enterprise memory is a later phase and must be treated as a data product, not a
chat-history feature.

Required controls include:

- tenant-partitioned storage and retrieval;
- supplier-scoped retailer context;
- purpose and retention classification;
- source attribution and freshness;
- explicit distinction between facts, user statements, drafts, and inferences;
- deletion, legal hold, export, and audit policies;
- prevention of cross-tenant embeddings, caches, retrieval, and model context;
- model-provider and data-residency review before production use;
- no training or reuse of customer data without explicit contractual approval.

A retailer's activity with wholesaler A must not influence recommendations,
pricing, or disclosure inside wholesaler B's workspace.

## Phased Roadmap

### Phase 0 - Evidence and Read-Only Evaluation

- Keep Procurement Workspace and other AI experiments isolated.
- Build an inventory of candidate Mpango tools and their risk classes.
- Establish representative, sanitized evaluation cases.
- Measure intent accuracy, contract accuracy, correction rate, and operator time.
- Permit no autonomous production writes.

Exit gate: stable evaluation results, zero tenant-boundary failures, approved
threat model, and named owners for operations and incident response.

### Phase 1 - AI Draft Assistant

- Draft purchase requests, retailer messages, SKU intake mappings, summaries,
  and support guidance.
- Retrieve user-manual and policy content with source attribution.
- Keep every result as a draft until a human accepts it.
- Do not allow direct financial, inventory, permission, or credential writes.

Exit gate: measured reduction in user effort with acceptable correction and
abandonment rates.

### Phase 2 - Governed Tool Harness

- Introduce the Intent Router, typed Business Contract, normalization,
  validation, confirmation, and Tool Registry.
- Start with read-only tools and low-risk draft creation.
- Add controlled writes one workflow at a time.
- Enforce tenant context, RBAC, idempotency, audit, and deterministic errors at
  the tool boundary.

Exit gate: workflow-specific runtime evidence, rollback proof, adversarial
authorization tests, and no bypass of existing APIs or services.

### Phase 3 - Tenant-Partitioned Enterprise Memory

- Add governed memory only for approved workflows.
- Preserve provenance, freshness, classification, retention, and deletion.
- Keep relationship and commercial data partitioned by tenant and purpose.

Exit gate: privacy review, retrieval-isolation proof, customer terms, and
operational deletion/export procedures.

### Phase 4 - Proactive AI Operator

- Detect anomalies, missing tasks, reconciliation issues, and operational risk.
- Recommend actions with evidence and expected effects.
- Allow scheduled or event-driven analysis.
- Keep material actions human-approved; do not permit autonomous accounting or
  payment decisions.

Exit gate: low false-positive burden, explainable recommendations, incident
controls, and demonstrated operator trust.

### Phase 5 - Multi-Workspace Engine

- Reuse the governed primitives across procurement, logistics, sales, finance,
  and platform operations.
- Keep each workspace's authority and tool allowlist explicit.
- Finance enters controlled automation last because accounting correctness is
  more important than convenience.

Exit gate: each workspace independently satisfies its domain invariants and
cross-workspace orchestration preserves transaction and audit integrity.

## Recommended Pilot Order

1. Procurement drafts and policy assistance.
2. Inventory and logistics exception analysis.
3. Sales and retailer-service drafts within one wholesaler context.
4. Finance explanation and reconciliation assistance.
5. Financial execution only after separate CTO, accounting, security, and
   runtime approval.

This order reflects risk, not product importance.

## Measurement Gates

Each phase must publish evidence for:

- task completion rate;
- time saved compared with the current workflow;
- user acceptance, correction, abandonment, and override rates;
- intent and contract classification accuracy;
- unauthorized-action count;
- tenant-boundary and commercial-privacy violations;
- duplicate, replay, and reconciliation outcomes;
- audit completeness;
- model and infrastructure cost per completed business task;
- incident, rollback, and recovery performance.

Human scoring is required before claiming that an AI workflow creates customer
value. Offline model quality alone is insufficient.

## Explicit Non-Goals

The following are not approved by this roadmap:

- replacing PostgreSQL or Mpango services with an AI-owned system of record;
- letting a model generate and execute arbitrary SQL;
- placing a generic agent gateway around internal endpoints without Mpango
  authentication and authorization;
- sharing global memory across tenants;
- exposing or inferring cross-wholesaler relationships or prices;
- allowing agents to own reusable production credentials;
- autonomous payment, ledger, credit, receivable, user, role, or destructive
  administration actions;
- moving the Procurement Workspace SQLite data model into ERP as an authority;
- marketing the isolated AI demo as a production ERP capability.

## Preconditions Before Product Integration

AI integration work should not begin until the relevant scope has:

- stable HTTPS customer and operator entry points;
- completed credential and tenant onboarding runtime gates;
- supplier-scoped retailer identity and branding contracts;
- production monitoring, backup, restore, and incident runbooks;
- current user manuals and operator procedures;
- a reviewed tool inventory with risk classes and owners;
- a tenant-isolated evaluation corpus without production secrets;
- approved model-provider, privacy, retention, and cost policies.

## Governance and Ownership

Every AI workflow requires:

- a business owner;
- a product contract;
- a security and tenant-isolation review;
- a named tool allowlist;
- a human-approval policy;
- test and runtime evidence;
- monitoring and incident ownership;
- a rollback or disable path.

The CTO approves movement between phases. A successful demo, model benchmark,
or isolated workspace does not itself authorize production integration.

## Planning Verdict

`RECORDED_AS_POST_MVP_STRATEGIC_DIRECTION`

The Procurement Workspace blueprint provides a useful proof of the operating
pattern:

`Intent Router -> Business Contract -> Normalize -> Human Confirm -> Audit`

Mpango should retain that pattern while adding the stricter tenancy, commercial
privacy, financial integrity, credential, and operational controls required by
a managed multi-tenant ERP.
