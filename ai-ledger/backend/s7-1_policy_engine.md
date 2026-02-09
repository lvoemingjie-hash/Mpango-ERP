# S7-1: BI Policy Engine — The Law

**Track**: S7-1 (BI Policy Engine)
**Date**: 2026-02-09
**Status**: ✅ COMPLETE
**Author**: Backend AI (Chief Security Architect)
**Phase**: 7 — Governance & Operations
**Depends On**: P7-0 (Governance Baseline — BIAsset, URN, Registry)
**Tests**: 55/55 passed (0.65s)

---

## 1. Objective

Build a pure-logic policy engine that answers one question:

> *"Given a Subject, an Action, and an Asset in a Tenant Context, is this allowed?"*

This module is **The Law** — it defines policy logic only. No enforcement code
(middleware, decorators, API hooks) exists here. The engine is framework-agnostic
and serves HTTP API handlers, background job workers (S6-4), and CLI tools.

---

## 2. CTO Mandates (Frozen Constraints)

### 🔒 Constraint S7-1-A — Trusted Role Source

> PolicySubject.roles MUST originate from a backend-trusted authority
> (Database / Directory / IAM). It is STRICTLY FORBIDDEN to directly
> trust roles or scopes from JWT tokens, request payloads, or any
> client-supplied source.

**Rationale**: Prevents token mis-issuance, client forgery, and SSO config drift
from granting unauthorized BI access.

### 🔒 Constraint S7-1-B — Baseline Matrix Scope

> The Default Permission Matrix is the GLOBAL DEFAULT BASELINE.
> It does NOT express any Asset-Specific or Override Policy.

**Rationale**: Future phases will layer per-asset, per-domain, and per-tenant
overrides on top of this baseline. The baseline is the fallback.

---

## 3. Architecture

### 3.1 File Structure

```
backend/core/governance/
├── __init__.py          # Package exports (P7-0 + S7-1)
├── models.py            # BIAction, ResourceType, BIDomain, BiUrn, BIAsset (P7-0)
├── registry.py          # GOVERNANCE_REGISTRY — 18 assets (P7-0)
├── roles.py             # DEFAULT_BI_PERMISSIONS matrix (S7-1)
└── policy.py            # PolicySubject, PolicyResult, evaluate_policy() (S7-1)
```

### 3.2 Dependency Graph

```
policy.py
    ├── models.py    (BIAction, BIAsset, BiUrn)
    ├── roles.py     (ADMIN_ROLE_NAME, DEFAULT_BI_PERMISSIONS)
    └── registry.py  (get_asset — for URN string resolution)

roles.py
    └── models.py    (BIAction)

registry.py
    └── models.py    (all model types)
```

No imports from `api.*`, `middleware`, `dependencies`, or `FastAPI`.

---

## 4. Core Signature

```python
def evaluate_policy(
    subject: PolicySubject,    # Who: user_id, tenant_id, roles (from DB)
    action: BIAction,          # What: VIEW, INTERACT, EXPORT, MANAGE
    asset: Union[BIAsset, str] # On: BIAsset object or URN string
) -> PolicyResult:             # Verdict: allowed, reason, policy_name, audit fields
```

---

## 5. Evaluation Order (Frozen — Must Not Be Reordered)

```
┌─────────────────────────────────────────────────────┐
│  Step 1: TENANT ISOLATION                           │
│  subject.tenant_id ≠ asset.tenant_id? → DENY        │
│  (system-wide assets with tenant_id=None pass)      │
│                                                     │
│  ⚠️ ALWAYS before admin bypass.                     │
│  admin ≠ god. Admin of Tenant A ≠ access Tenant B.  │
├─────────────────────────────────────────────────────┤
│  Step 2: ADMIN BYPASS                               │
│  "admin" ∈ subject.roles? → ALLOW                   │
│  (only within tenant scope, per Step 1)             │
├─────────────────────────────────────────────────────┤
│  Step 3: ROLE-ACTION MATRIX (Baseline)              │
│  Any role in subject.roles grants action? → ALLOW   │
│  (most permissive role wins)                        │
│  🔒 S7-1-B: Global Default Baseline only.           │
├─────────────────────────────────────────────────────┤
│  Step 4: DEFAULT DENY                               │
│  No matching policy → DENY                          │
│  (reason includes role list for debugging)          │
└─────────────────────────────────────────────────────┘
```

---

## 6. Default Permission Matrix (Baseline)

```
┌───────────┬──────┬──────────┬────────┬────────┐
│ Role      │ VIEW │ INTERACT │ EXPORT │ MANAGE │
├───────────┼──────┼──────────┼────────┼────────┤
│ admin     │  ✅  │    ✅    │   ✅   │   ✅   │  ← engine bypass (Step 2)
│ finance   │  ✅  │    ✅    │   ✅   │   ❌   │
│ sales     │  ✅  │    ✅    │   ❌   │   ❌   │
│ warehouse │  ✅  │    ❌    │   ❌   │   ❌   │
│ viewer    │  ✅  │    ❌    │   ❌   │   ❌   │
└───────────┴──────┴──────────┴────────┴────────┘
```

- `admin` is NOT in the matrix dict — handled by engine Step 2.
- Unknown roles get empty frozenset → default deny.
- Multiple roles: most permissive wins (union of allowed actions).

---

## 7. Data Models

### PolicySubject

```python
class PolicySubject(BaseModel):
    user_id: str          # Authenticated user UUID
    tenant_id: str        # Tenant UUID from verified JWT
    roles: frozenset[str] # Role names from backend DB (🔒 S7-1-A)
```

- Frozen (immutable)
- Accepts `list`, `set`, `tuple` for roles (coerced to `frozenset`)
- `.is_admin` property for convenience

### PolicyResult

```python
class PolicyResult(BaseModel):
    allowed: bool         # The verdict
    reason: str           # Human-readable explanation
    policy_name: str      # Which rule decided (audit trail)
    subject_id: str       # Who asked (audit trail)
    asset_urn: str        # What was accessed (audit trail)
    action: str           # What was attempted (audit trail)
```

- Frozen (immutable)
- All fields designed for compliance logging (P7-3 future)
- `policy_name` values: `tenant_isolation`, `admin_bypass`, `role_matrix_baseline`, `default_deny`

---

## 8. Test Coverage (55 tests)

| Category | Count | Description |
|----------|-------|-------------|
| Tenant Isolation | 4 | Cross-tenant deny, system-wide allow, same-tenant pass |
| Admin Bypass | 6 | All actions allowed, cross-tenant still denied |
| Role-Action Matrix | 12 | Finance (4), Sales (4), Warehouse (4), Viewer (3) |
| Default Deny | 3 | No roles, unknown role, reason includes roles |
| Multiple Roles | 3 | Most permissive wins, admin in set triggers bypass |
| URN String Input | 3 | Resolution, invalid URN, invalid type |
| PolicySubject Validation | 6 | Empty fields, coercion, is_admin, frozen |
| PolicyResult Structure | 2 | Audit fields present, frozen |
| Roles Helpers | 7 | Matrix lookups, admin absent, action queries |
| Full Scenarios | 6 | End-to-end business scenarios |

---

## 9. Future Phases

| Phase | What It Adds | Relationship to S7-1 |
|-------|-------------|---------------------|
| P7-2 | Enforcement middleware: `@require_bi_access(urn, action)` | Calls `evaluate_policy()` |
| P7-3 | Audit trail: log every PolicyResult to audit table | Consumes PolicyResult fields |
| P7-4 | Asset-specific overrides: per-domain, per-tenant policies | Layers on top of baseline matrix |
| P7-5 | "Explain Why" UX: show denial reason to users | Uses `result.reason` and `result.policy_name` |

---

**Document Status**: ✅ COMPLETE
**Last Updated**: 2026-02-09
