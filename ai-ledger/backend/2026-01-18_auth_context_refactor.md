# Auth Context Refactor - Circular Import Fix

**Date**: 2026-01-18
**Status**: COMPLETED
**Owner**: Backend AI

---

## Issue
- Runtime circular import between `api.dependencies` and `api.middleware` when booting `uvicorn main:app`.
- Stack trace showed `ImportError: cannot import name 'get_current_user_context'` due to `dependencies.py` importing middleware which in turn imported dependencies.

## Root Cause
- Authentication helpers (`JWTBearer`, `get_current_user_context`, tenant DB resolution) lived inside `api.dependencies`.
- Middleware modules required the same helpers, triggering reverse imports and creating a cycle.

## Solution
1. Introduced dedicated context layer `api/context/auth_context.py` to host all auth context helpers:
   - JWT bearer class and singleton
   - JWT decode wrapper
   - `get_current_user_context`
   - Tenant schema resolution and tenant DB session helper
2. `dependencies.py` now imports `get_current_user_context` / `get_tenant_db_session` from the new context module.
3. `middleware/auth.py` and `middleware/rbac.py` import solely from `api.context.auth_context`, eliminating middleware → dependencies coupling.
4. Added formal package entry point `api/context/__init__.py` for exports.

## Files Updated
- `backend/api/context/auth_context.py` *(new)*
- `backend/api/context/__init__.py` *(new)*
- `backend/api/dependencies.py`
- `backend/api/middleware/auth.py`
- `backend/api/middleware/rbac.py`

## Verification
- FastAPI import graph now satisfies: `context → dependencies → routes`, `context → middleware`.
- Next steps (to be run):
  ```bash
  cd backend
  poetry run uvicorn main:app --reload
  curl -f http://localhost:8000/health
  ```
  Expect HTTP 200 without circular import warnings.

---

*Log recorded to track backend auth context refactor work.*
