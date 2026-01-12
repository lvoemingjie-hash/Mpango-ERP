# DR-005: Constitution Sync Policy

## Status
**Accepted** (2026-01-12)

## Context

The Mpango ERP project has authoritative L0/L1/L2 documents that define system contracts. These documents were originally stored in `Read before building/` folder outside the main documentation structure.

Per AI Engineering Work Rules, no AI is allowed to rely on off-repo memory. All living truth must exist within the repository in a consistent location.

## Decision

1. **Single Source Location**: All authoritative contracts must exist in `docs/contracts/`
2. **Constitution Sync Loop**: Architect AI must periodically verify all L0/L1/L2 documents are synced
3. **Binary Files Exception**: Binary files (.docx, .png, .pdf) remain in `Read before building/` as reference-only
4. **Naming Convention**: All contract files use `snake_case.md` format
5. **No Modification**: Imported contracts preserve original content verbatim

## Imported Documents

| Document | Classification | Target |
|----------|---------------|--------|
| Coding Style Contract | L1 | `coding_style_contract.md` |
| CI/CD Contract | L1 | `ci_cd_contract.md` |
| Test Contract | L1 | `test_contract.md` |
| API Contract v1.1 | L0 | `api_contract.md` |
| Docker Contract | L1 | `docker_contract.md` |
| UI Integration Contract | L1 | `ui_integration_contract.md` |
| Domain Workflows | L1 | `domain_workflows.md` |
| Ops Runbooks | L2 | `ops_runbooks.md` |
| Non-functional Spec | L1 | `nonfunctional_ops_spec.yaml` |
| SpecKit Guide | L1 | `speckit_project_guide.md` |
| SpecKit Data Model | L0 | `speckit_data_model.yaml` |

## Reference-Only Documents (Not Imported)

| Document | Reason |
|----------|--------|
| `#0 init_mpango_erp_project.sh` | Script, not contract |
| `#1 Mpango_ERP_PRD_v1.0.docx` | Binary file |
| `#2 Mpango_ERP_ERD.png` | Binary file |
| `standard_ai_communication_protocol.pdf` | Binary file |

## Consequences

### Positive
- All AIs reference single authoritative location
- No reliance on off-repo memory
- Consistent naming and organization
- Version control for all contracts

### Negative
- Binary files (PRD, ERD) not directly accessible to AI
- Requires manual sync if source documents change

### Risks
- Source documents in `Read before building/` may diverge from `docs/contracts/`
- Mitigation: Architect AI performs periodic sync verification

## Compliance

This decision implements the "Living Truth" principle from `AI workrules.md`.

## References
- `docs/contracts/AI workrules.md` - Work rules requiring in-repo truth
- `ai-ledger/architect/2026-01-12_architecture_constitution_sync.md` - Sync ledger
