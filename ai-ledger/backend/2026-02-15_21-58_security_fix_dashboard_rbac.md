# Security Fix: RBAC Coverage for Dashboard Endpoints

**Date**: 2026-02-15 21:58 UTC+08:00  
**Type**: Critical Security Fix  
**Status**: ✅ Completed

---

## Problem Statement

Security audit (2026-02-15_21-46_security_audit_v0.2.0.md) identified **5 unprotected endpoints** in `backend/api/v1/dashboards.py` that were accessible to any authenticated user without explicit permission checks.

### Vulnerable Endpoints

| Endpoint | Method | Risk |
|----------|--------|------|
| `/dashboards/kpi/summary` | GET | Financial KPIs exposed (Revenue, AR, Cash) |
| `/dashboards/charts/sales-trend` | GET | Sales data exposed |
| `/dashboards/charts/cash-flow` | GET | Cash flow data exposed |
| `/reports/analyze` | POST | Ad-hoc query execution |
| `/reports/schema/{view_scope}` | GET | Schema discovery |

---

## Solution Implemented

### 1. Added RBAC Imports to dashboards.py

```python
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
```

### 2. Added RequirePermission Decorators

| Endpoint | Permission Assigned |
|----------|---------------------|
| `GET /dashboards/kpi/summary` | `dashboards:read` |
| `GET /dashboards/charts/sales-trend` | `dashboards:read` |
| `GET /dashboards/charts/cash-flow` | `dashboards:read` |
| `POST /reports/analyze` | `reports:analyze` |
| `GET /reports/schema/{view_scope}` | `reports:read` |

### Code Change Pattern

```python
# Before (VULNERABLE)
async def get_kpi_summary(request: Request) -> JSONResponse:

# After (SECURED)
async def get_kpi_summary(
    request: Request,
    token: TokenPayload = Depends(RequirePermission("dashboards:read")),
) -> JSONResponse:
```

### 3. Added Permissions to Seed Script

Updated `scripts/seed_demo_data.py` PERMISSION_CODES:

```python
PERMISSION_CODES = [
    # ... existing permissions ...
    ("dashboards:read", "Read dashboard KPIs and charts"),
    ("reports:analyze", "Execute ad-hoc semantic analysis queries"),
]
```

---

## Files Modified

1. `backend/api/v1/dashboards.py`
   - Added imports: `RequirePermission`, `TokenPayload`
   - Added `Depends(RequirePermission(...))` to 5 endpoints

2. `scripts/seed_demo_data.py`
   - Added `dashboards:read` permission
   - Added `reports:analyze` permission

---

## Verification Steps

1. **Static Analysis**: Confirmed all 5 endpoints now have `RequirePermission` decorator
2. **Permission Registry**: Verified new permissions are in seed script
3. **Import Check**: Verified `RequirePermission` import path matches other secured endpoints

---

## Post-Fix RBAC Matrix

| Endpoint | Method | Permission | Status |
|----------|--------|------------|--------|
| `/dashboards/kpi/summary` | GET | `dashboards:read` | ✅ PASS |
| `/dashboards/charts/sales-trend` | GET | `dashboards:read` | ✅ PASS |
| `/dashboards/charts/cash-flow` | GET | `dashboards:read` | ✅ PASS |
| `/reports/analyze` | POST | `reports:analyze` | ✅ PASS |
| `/reports/schema/{view_scope}` | GET | `reports:read` | ✅ PASS |

**Critical Issues**: 0 (down from 5)

---

## Deployment Notes

- **Backward Compatibility**: Breaking change — clients without the new permissions will receive 403
- **Migration**: Run `scripts/seed_demo_data.py` or manually assign `dashboards:read` and `reports:analyze` to Admin role
- **Affected Roles**: All roles need permission review; Admin role gets all permissions by default
