# Contract Library Index

This index keeps the original Mpango contracts reachable from the current
navigation layer. A contract disappearing from a new summary does not retire or
supersede it.

## How authority works

`CURRENT_CONTRACT_ENTRY` means this is the canonical document to consult for
that topic. It does not mean every sentence is automatically synchronized with
the merged implementation.

For every implementation task:

1. read the relevant contract entry;
2. verify it against the exact merged source, migrations and executable tests;
3. treat any mismatch as contract drift requiring an explicit decision;
4. update this index and all affected navigation documents when authority moves;
5. supersede historical documents in place before considering archival.

No document in this directory may be deleted merely because a newer summary
does not link to it.

## Constitution and security boundaries

| Topic | Canonical entry | Classification |
|---|---|---|
| AI engineering workflow | [AI workrules](AI%20workrules.md) | `CURRENT_CONTRACT_ENTRY` |
| Runtime/startup constitution | [Boot contract](Boot%20contract.md) | `CURRENT_CONTRACT_ENTRY` |
| System architecture | [Architecture contract](architecture_contract.md) | `CURRENT_CONTRACT_ENTRY_REQUIRES_BASELINE_CHECK` |
| Multi-tenancy | [Multi-tenancy spec](multi_tenancy_spec.md) | `CURRENT_CONTRACT_ENTRY` |
| Tenant onboarding/provisioning | [Tenant onboarding contract](tenant_onboarding_provisioning_contract.md) | `CURRENT_CONTRACT_ENTRY` |
| RBAC vocabulary and roles | [RBAC matrix](rbac_matrix.md) | `CURRENT_CONTRACT_ENTRY`; executable registry is `backend/core/permission_registry.py` |

## Interface, data and workflow contracts

| Topic | Canonical entry | Classification |
|---|---|---|
| API conventions | [API contract](api_contract.md) | `CURRENT_CONTRACT_ENTRY_REQUIRES_ROUTE_CHECK` |
| OpenAPI artifact | [openapi.yaml](openapi.yaml) | `DERIVED_ARTIFACT_REQUIRES_REGENERATION_CHECK` |
| Database shape | [Database contract](database_contract.md) | `CURRENT_CONTRACT_ENTRY_REQUIRES_MIGRATION_CHECK` |
| Domain workflows | [Domain workflows](domain_workflows.md) | `CURRENT_CONTRACT_ENTRY_REQUIRES_SERVICE_CHECK` |
| UI/API integration | [UI integration contract](ui_integration_contract.md) | `CURRENT_CONTRACT_ENTRY_REQUIRES_FRONTEND_CHECK` |
| Spec-kit data model | [speckit_data_model.yaml](speckit_data_model.yaml) | `DESIGN_INPUT` |

## Implementation and delivery contracts

| Topic | Canonical entry | Classification |
|---|---|---|
| Backend implementation | [Backend contract](backend_contract.md) | `CURRENT_CONTRACT_ENTRY` |
| Frontend implementation | [Frontend contract](frontend_contract.md) | `CURRENT_CONTRACT_ENTRY` |
| Test minimums | [Test contract](test_contract.md) | `CURRENT_CONTRACT_ENTRY`; acceptance evidence also follows [EVIDENCE.md](../governance/EVIDENCE.md) |
| Coding and Git style | [Coding style](coding_style_contract.md) | `CURRENT_CONTRACT_ENTRY` |
| Container packaging | [Docker contract](docker_contract.md) | `CURRENT_CONTRACT_ENTRY_REQUIRES_COMPOSE_CHECK` |
| CI/CD | [CI/CD contract](ci_cd_contract.md) | `CURRENT_CONTRACT_ENTRY_REQUIRES_WORKFLOW_CHECK` |
| Non-functional operations | [Non-functional ops spec](nonfunctional_ops_spec.md) | `CURRENT_CONTRACT_ENTRY`; targets are not runtime evidence |
| Operational procedures | [Ops runbooks](ops_runbooks.md) | `CONTRACT_REFERENCE`; current response entry is [RUNBOOK.md](../operations/RUNBOOK.md) |

## Supporting and historical inputs

| Document | Classification |
|---|---|
| [Spec-kit project guide](speckit_project_guide.md) | `DESIGN_INPUT` |
| [Product backlog and future roadmap](Product%20Backlog%20%26%20Future%20Roadmap.md) | `PLANNING_NOT_CURRENT_PRODUCT_TRUTH` |
| [Boot contract prompt](Boot%20contract.prompt.md) | `AUTHORING_COMPANION_NOT_AUTHORITY` |
| [2026-01-27 accepted clarifications](contract-patches/2026-01-27_perplexity-clarifications.md) | `HISTORICAL_ACCEPTED_PATCH`; verify incorporation in current entries |
| [RBAC matrix v0.2.0](../RBAC_MATRIX_v0.2.0.md) | `HISTORICAL_SUPERSEDED_SNAPSHOT`; retained for traceability |

## RBAC authority resolution

- Contract entry: [rbac_matrix.md](rbac_matrix.md).
- Executable permission sets: `backend/core/permission_registry.py`.
- Runtime enforcement: `backend/api/middleware/rbac.py` and route-level
  `RequirePermission(...)` declarations.
- Bootstrap parity: `backend/scripts/onboard_tenant.py`,
  `backend/scripts/create_wholesaler.py`, and bootstrap parity tests.
- Historical mapping: [RBAC_MATRIX_v0.2.0.md](../RBAC_MATRIX_v0.2.0.md).

If these surfaces disagree, do not silently choose the newest timestamp. Record
the drift, determine intended policy, update code/tests/contracts together, and
run the required security tier.
