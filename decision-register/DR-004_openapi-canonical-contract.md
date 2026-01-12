# DR-004: OpenAPI as Canonical Frontend-Backend Contract

## Status
**Accepted** (2026-01-12)

## Context

Mpango ERP follows multi-AI collaboration rules (钢钉1) which mandate:
> "OpenAPI is the ONLY interface truth between frontend and backend"

The Architect AI must define the canonical OpenAPI specification BEFORE Backend AI implements endpoints. This ensures:
1. Frontend and Backend AI work from identical interface definitions
2. No implicit API decisions made during implementation
3. Contract changes require explicit Architect approval

## Decision

1. **Single Source of Truth**: `docs/contracts/openapi.yaml` is the canonical API contract
2. **Architect Authority**: Only Architect AI may modify the OpenAPI spec
3. **Implementation Compliance**: Backend AI must implement endpoints exactly as specified
4. **Frontend Compliance**: Frontend AI must consume APIs exactly as specified
5. **Version Control**: OpenAPI version in `info.version` must be incremented for any change

## Specification Structure

```
docs/contracts/openapi.yaml
├── info (version, description)
├── servers (dev, prod URLs)
├── tags (endpoint grouping)
├── security (BearerAuth default)
├── paths (all endpoints)
└── components
    ├── securitySchemes
    ├── parameters (reusable)
    ├── responses (reusable)
    └── schemas (all DTOs)
```

## Response Envelope Standard

All responses follow this envelope:

```yaml
# Success
{ success: true, data: {...}, message?: string, timestamp: ISO8601 }

# Error
{ success: false, error: { code, message, details? }, timestamp: ISO8601 }
```

## Consequences

### Positive
- Clear contract prevents frontend-backend misalignment
- Enables parallel development by Frontend and Backend AI
- Swagger UI auto-generated at `/docs`
- Type generation possible for frontend (openapi-typescript)

### Negative
- Requires Architect involvement for any API change
- May slow down rapid prototyping

### Risks
- OpenAPI spec drift from implementation (mitigated by contract tests)

## Compliance

This decision implements **钢钉1** from `Mpango AI workrules.md`.

## References
- `Read before building/Mpango AI workrules.md` - Steel Nail 1
- `Read before building/#11 kiro_api_contract (v1.1).md` - API standards
- `docs/contracts/openapi.yaml` - The canonical spec
