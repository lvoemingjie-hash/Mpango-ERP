# S7-2: BI Access Enforcement Layer — The Police

**Track**: S7-2 (Enforcement Layer)
**Date**: 2026-02-09
**Status**: ✅ COMPLETE
**Author**: Backend AI (Chief Backend Architect)
**Phase**: 7 — Governance & Operations
**Depends On**: S7-1 (BI Policy Engine — The Law)
**Tests**: 31/31 passed (1.05s)

---

## 1. Objective

Bridge the pure-logic policy engine (S7-1) with FastAPI's HTTP layer.
The enforcement layer performs exactly ONE job: **translate policy decisions
into HTTP responses** (200 pass-through / 403 deny).

**Before S7-2**: "We have laws, but no police."
**After S7-2**: "Every BI endpoint can declare or invoke access control
that delegates to `evaluate_policy()` and returns 403 on denial."

---

## 2. CTO Mandates (Frozen Constraints)

### 🔒 Constraint S7-1-A — Trusted Role Source

> `get_policy_subject()` loads roles from `TenantContext.user.roles` (DB),
> NEVER from JWT token claims directly.

### 🔒 Constraint S7-1-C — Two Legal Entry Points

> ALL BI permission checks MUST use one of:
> 1. `RequireBIPermission` — Declarative (Depends) for static URNs
> 2. `enforce_bi_access` — Imperative (function call) for dynamic URNs
>
> It is STRICTLY FORBIDDEN to call `evaluate_policy()` directly from
> business code.

---

## 3. Architecture

### 3.1 File Structure

```
backend/api/middleware/
├── rbac.py              # Existing: RequirePermission (CRUD permissions)
└── bi_access.py         # NEW (S7-2): RequireBIPermission + enforce_bi_access
```

### 3.2 Component Diagram

```
HTTP Request
    │
    ▼
┌─────────────────────────────────┐
│  Auth Middleware (existing)      │  → AuthContext on request.state
│  Tenant Middleware (existing)    │  → TenantContext on request.state
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│  get_policy_subject()           │  ← Trust Boundary (🔒 S7-1-A)
│  Reads: auth_ctx.token          │     user_id, tenant_id from JWT
│  Reads: tenant_ctx.user.roles   │     role names from DB
│  Output: PolicySubject          │
└─────────────────────────────────┘
    │
    ├── Pattern A: Static URN ──────────────────────────────┐
    │   RequireBIPermission(action, urn)                    │
    │   Used as: Depends() in route definition              │
    │                                                       │
    ├── Pattern B: Dynamic URN ─────────────────────────────┤
    │   enforce_bi_access(subject, action, urn)             │
    │   Used as: explicit call after body parsing           │
    │                                                       │
    ▼                                                       ▼
┌─────────────────────────────────┐
│  evaluate_policy()  (S7-1)      │  ← Pure logic, no HTTP
│  Returns: PolicyResult          │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│  _audit_hook(result)            │  ← TODO: P7-3 audit trail
│  Current: no-op                 │
└─────────────────────────────────┘
    │
    ├── allowed=True  → return PolicyResult (200)
    └── allowed=False → raise HTTPException(403)
```

---

## 4. API Surface

### 4.1 `get_policy_subject(request: Request) → PolicySubject`

The **single Trust Boundary** for constructing PolicySubject in the HTTP layer.

```python
from api.middleware.bi_access import get_policy_subject

subject: PolicySubject = Depends(get_policy_subject)
```

- Reads `AuthContext.token` for `user_id`, `tenant_id`
- Reads `TenantContext.user.roles` for role names (🔒 S7-1-A: from DB)
- Raises 401 if auth or tenant context is missing

### 4.2 `RequireBIPermission(action, urn)` — Declarative

For routes where the asset URN is **known at definition time**.

```python
from api.middleware.bi_access import RequireBIPermission
from core.governance.models import BIAction

# As parameter dependency (captures PolicyResult)
@router.get("/kpi/summary")
async def kpi_summary(
    _policy = Depends(RequireBIPermission(
        BIAction.VIEW,
        "urn:bi:dashboard:executive:executive_summary",
    )),
):
    ...

# As route-level dependency
@router.get(
    "/charts/sales-trend",
    dependencies=[Depends(RequireBIPermission(
        BIAction.VIEW,
        "urn:bi:dashboard:sales:sales_trend",
    ))],
)
async def sales_trend():
    ...
```

### 4.3 `enforce_bi_access(subject, action, urn)` — Imperative

For routes where the URN is **dynamic** (resolved from request body/path).

```python
from api.middleware.bi_access import get_policy_subject, enforce_bi_access
from core.governance.models import BIAction

@router.post("/reports/analyze")
async def analyze(
    request: Request,
    body: SemanticQueryRequest,
    subject: PolicySubject = Depends(get_policy_subject),
):
    urn = f"urn:bi:report:sales:adhoc_{body.view.value}_analysis"
    enforce_bi_access(subject, BIAction.INTERACT, urn)
    # ... proceed with analysis ...
```

---

## 5. Security: Error Detail Sanitization

| Policy | HTTP Detail | Rationale |
|--------|-------------|-----------|
| `tenant_isolation` | "resource not available in your scope" | Generic — don't confirm cross-tenant asset existence |
| `default_deny` | "insufficient permissions for '{action}' action" | Shows action, hides role names |
| `role_matrix_baseline` | "insufficient permissions for '{action}' action" | Same sanitized format |

Internal `PolicyResult.reason` (with full details) is available to the
audit hook but NEVER exposed to the HTTP client.

---

## 6. Fail-Safe Behavior

| Scenario | Result |
|----------|--------|
| Missing AuthContext | HTTP 401 |
| Missing TenantContext | HTTP 401 |
| User has no roles | HTTP 403 (default deny) |
| Unknown role name | HTTP 403 (default deny) |
| Invalid/unregistered URN | HTTP 403 (fail-safe) |
| Cross-tenant access | HTTP 403 (tenant isolation) |

**Principle**: When in doubt, DENY. Never fail open.

---

## 7. Audit Hook (P7-3 Placeholder)

```python
def _audit_hook(result: PolicyResult) -> None:
    """
    Called on EVERY policy evaluation (allow AND deny).
    PolicyResult contains: allowed, reason, policy_name,
    subject_id, asset_urn, action.

    P7-3 will: generate decision_id, emit audit event, persist async.
    Current: no-op.
    """
    pass
```

The hook is called **before** the HTTP response is sent, ensuring that
even denied requests are auditable.

---

## 8. Test Coverage (31 tests)

| Category | Count | Description |
|----------|-------|-------------|
| Trust Boundary | 6 | Subject building, roles from DB, missing context → 401 |
| Declarative Enforcement | 7 | Admin allow, viewer deny, finance export, cross-tenant, result capture |
| Imperative Enforcement | 6 | Allow/deny, BIAsset object, invalid URN fail-safe, dynamic URN |
| Fail-Safe | 2 | No roles, unknown role |
| Error Detail Security | 3 | Tenant isolation generic msg, no role leak, code field |
| Audit Hook | 2 | Called on allow, called on deny |
| Full Request Flow | 5 | End-to-end admin/viewer/finance/sales/multi-role scenarios |

---

## 9. Relationship to Existing RBAC

| Component | Scope | Location |
|-----------|-------|----------|
| `RequirePermission` | CRUD permissions (`users:read`, `orders:create`) | `api/middleware/rbac.py` |
| `RequireBIPermission` | BI governance (`BIAction` × `BIAsset URN`) | `api/middleware/bi_access.py` |

These are **complementary, not competing**. A route can use both:
```python
@router.get("/reports/analyze")
async def analyze(
    token = Depends(RequirePermission("reports:read")),  # CRUD gate
    _bi = Depends(RequireBIPermission(BIAction.INTERACT, urn)),  # BI gate
):
    ...
```

---

## 10. Future Phases

| Phase | What It Adds | Relationship to S7-2 |
|-------|-------------|---------------------|
| P7-3 | Audit trail: `_audit_hook()` persists PolicyResult | Fills the placeholder |
| P7-4 | Asset-specific overrides | No change to S7-2 (handled in S7-1 matrix) |
| P7-5 | "Explain Why" UX | Uses PolicyResult from enforce_bi_access return value |

---

**Document Status**: ✅ COMPLETE
**Last Updated**: 2026-02-09
