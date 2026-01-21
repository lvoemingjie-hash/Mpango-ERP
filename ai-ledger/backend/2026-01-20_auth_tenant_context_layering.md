# Auth & Tenant Context Layering Refactor

**Date**: 2026-01-20  
**Status**: COMPLETED  
**Owner**: Backend AI

---

## Objective
Fully eliminate the residual circular imports between `api.dependencies` and `api.middleware` by enforcing the new layering contract:

```
api.context → api.middleware → request.state
request.state → api.dependencies → routers
```

## Key Changes
1. **Introduced tenant context module**
   - Added `api/context/tenant.py` with `TenantContext` dataclass, session lifecycle helpers, and request.state accessors.
   - Updated `api/context/__init__.py` to export both auth and tenant context utilities only (no middleware coupling).

2. **Rebuilt authentication middleware**
   - `api/middleware/auth.py` now implements `AuthenticationMiddleware` which:
     - Extracts the bearer token from incoming requests.
     - Decodes JWT and attaches `AuthContext` to `request.state`.
     - Resolves tenant session/user via `TenantContext`, commits/rolls back, and ensures cleanup.
   - `api/middleware/__init__.py` exports the new middleware for application wiring.

3. **Simplified RBAC enforcement**
   - `api/middleware/rbac.py` reads `AuthContext` and `TenantContext` directly from `request.state` and no longer touches FastAPI dependencies or the database layer.

4. **Dependency layer cleanup**
   - `api/dependencies.py` now only reads context from `request.state` and re-exposes the token, tenant context, and tenant-scoped session without performing JWT decoding or database lookups.

5. **Application wiring**
   - `main.py` registers `AuthenticationMiddleware` before idempotency middleware to ensure context is available for downstream routes and dependencies.

## Files Touched
- `backend/api/context/tenant.py` *(new)*
- `backend/api/context/__init__.py`
- `backend/api/middleware/auth.py`
- `backend/api/middleware/__init__.py`
- `backend/api/middleware/rbac.py`
- `backend/api/dependencies.py`
- `backend/main.py`

## Verification Steps
Pending manual run (execute from repo root):
```bash
cd backend
poetry run uvicorn main:app --reload
curl -f http://localhost:8000/health
```
Expect clean startup without circular import errors and HTTP 200 from `/health`.

---

*Entry recorded to document the completion of the backend context layering refactor.*
