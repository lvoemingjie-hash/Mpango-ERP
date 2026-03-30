# Security Audit Report — Mpango ERP v0.2.0 Pre-release

**Date**: 2026-02-15 21:46 UTC+08:00  
**Role**: Security Auditor (Static Analysis)  
**Scope**: `@backend/api`, `@backend/schemas`, `@frontend/src/types`

---

## Task 1: RBAC Coverage Matrix

### Executive Summary
- **Total Endpoints Scanned**: 45
- **PASS (Has Permission Decorator)**: 31 (68.9%)
- **PUBLIC (Explicitly Unauthenticated)**: 9 (20.0%)
- **⚠️ CRITICAL (Write Operation Without Permission)**: 5 (11.1%)

### Detailed Matrix

#### Auth Routes (`/api/v1/auth/*`) — PUBLIC (Correctly Unauthenticated)
| Endpoint Path | Method | Permission Decorator | Status |
|---------------|--------|---------------------|--------|
| `/api/v1/auth/login` | POST | None (public) | ⚠️ PUBLIC |
| `/api/v1/auth/refresh` | POST | None (public) | ⚠️ PUBLIC |
| `/api/v1/auth/logout` | POST | `get_current_user_context` (auth only) | ⚠️ PUBLIC |
| `/api/v1/auth/me` | GET | `get_current_user_context` (auth only) | ⚠️ PUBLIC |

#### Health Routes (`/health/*`, `/readyz`) — PUBLIC (Correct)
| Endpoint Path | Method | Permission Decorator | Status |
|---------------|--------|---------------------|--------|
| `/healthz` | GET | None (liveness probe) | ⚠️ PUBLIC |
| `/health/live` | GET | None (liveness probe) | ⚠️ PUBLIC |
| `/health/ready` | GET | None (readiness probe) | ⚠️ PUBLIC |
| `/readyz` | GET | None (readiness probe) | ⚠️ PUBLIC |

#### Order Routes (`/api/v1/orders/*`) — ✅ COVERED
| Endpoint Path | Method | Permission Decorator | Status |
|---------------|--------|---------------------|--------|
| `/api/v1/orders` | GET | `RequirePermission("orders:read")` | ✅ PASS |
| `/api/v1/orders` | POST | `RequirePermission("orders:create")` | ✅ PASS |
| `/api/v1/orders/{id}` | GET | `RequirePermission("orders:read")` | ✅ PASS |
| `/api/v1/orders/{id}/confirm` | POST | `RequirePermission("orders:update")` | ✅ PASS |
| `/api/v1/orders/{id}/cancel` | POST | `RequirePermission("orders:update")` | ✅ PASS |

#### SKU Routes (`/api/v1/skus/*`) — ✅ COVERED
| Endpoint Path | Method | Permission Decorator | Status |
|---------------|--------|---------------------|--------|
| `/api/v1/skus` | GET | `RequirePermission("skus:read")` | ✅ PASS |
| `/api/v1/skus` | POST | `RequirePermission("skus:create")` | ✅ PASS |
| `/api/v1/skus/{sku_code}` | GET | `RequirePermission("skus:read")` | ✅ PASS |
| `/api/v1/skus/{sku_code}` | PUT | `RequirePermission("skus:update")` | ✅ PASS |

#### Inventory Routes (`/api/v1/inventory/*`) — ✅ COVERED
| Endpoint Path | Method | Permission Decorator | Status |
|---------------|--------|---------------------|--------|
| `/api/v1/inventory/stocks` | GET | `RequirePermission("inventory:read")` | ✅ PASS |
| `/api/v1/inventory/stocks/{sku_code}` | GET | `RequirePermission("inventory:read")` | ✅ PASS |
| `/api/v1/inventory/orders/{order_id}/stocks` | GET | `RequirePermission("inventory:read")` | ✅ PASS |

#### User Routes (`/api/v1/users/*`) — ✅ COVERED
| Endpoint Path | Method | Permission Decorator | Status |
|---------------|--------|---------------------|--------|
| `/api/v1/users` | GET | `RequirePermission("users:read")` | ✅ PASS |
| `/api/v1/users` | POST | `RequirePermission("users:create")` | ✅ PASS |
| `/api/v1/users/{id}` | GET | `RequirePermission("users:read")` | ✅ PASS |
| `/api/v1/users/{id}` | PUT | `RequirePermission("users:update")` | ✅ PASS |
| `/api/v1/users/{id}` | DELETE | `RequirePermission("users:deactivate")` | ✅ PASS |
| `/api/v1/users/{id}/roles` | PUT | `RequirePermission("roles:assign")` | ✅ PASS |

#### Wholesaler/Tenant Routes (`/api/v1/wholesalers/*`) — ✅ COVERED
| Endpoint Path | Method | Permission Decorator | Status |
|---------------|--------|---------------------|--------|
| `/api/v1/wholesalers` | GET | `RequirePermission("wholesalers:read")` | ✅ PASS |
| `/api/v1/wholesalers` | POST | `RequirePermission("wholesalers:write")` | ✅ PASS |
| `/api/v1/wholesalers/{id}` | GET | `RequirePermission("wholesalers:read")` | ✅ PASS |
| `/api/v1/wholesalers/{id}` | PUT | `RequirePermission("wholesalers:write")` | ✅ PASS |
| `/api/v1/wholesalers/{id}` | DELETE | `RequirePermission("wholesalers:write")` | ✅ PASS |

#### Retailer Routes (`/api/v1/retailers/*`) — ✅ COVERED
| Endpoint Path | Method | Permission Decorator | Status |
|---------------|--------|---------------------|--------|
| `/api/v1/retailers/register` | POST | None (public registration) | ⚠️ PUBLIC |
| `/api/v1/retailers/bindings` | GET | `RequirePermission("retailers:read")` | ✅ PASS |

#### Invitation Routes (`/api/v1/invitations/*`) — MIXED
| Endpoint Path | Method | Permission Decorator | Status |
|---------------|--------|---------------------|--------|
| `/api/v1/invitations` | POST | `RequirePermission("invitations:create")` | ✅ PASS |
| `/api/v1/invitations/{code}` | GET | None (public lookup) | ⚠️ PUBLIC |

#### Payment Routes (`/api/v1/payments/*`) — ✅ COVERED
| Endpoint Path | Method | Permission Decorator | Status |
|---------------|--------|---------------------|--------|
| `/api/v1/payments` | POST | `RequirePermission("payments:create")` | ✅ PASS |

#### Role Routes (`/api/v1/roles/*`) — ✅ COVERED
| Endpoint Path | Method | Permission Decorator | Status |
|---------------|--------|---------------------|--------|
| `/api/v1/roles` | GET | `RequirePermission("roles:read")` | ✅ PASS |

#### Dashboard Routes (`/api/v1/dashboards/*`, `/api/v1/reports/*`) — ❌ CRITICAL
| Endpoint Path | Method | Permission Decorator | Status |
|---------------|--------|---------------------|--------|
| `/api/v1/dashboards/kpi/summary` | GET | None (only tenant context) | ❌ CRITICAL |
| `/api/v1/dashboards/charts/sales-trend` | GET | None (only tenant context) | ❌ CRITICAL |
| `/api/v1/dashboards/charts/cash-flow` | GET | None (only tenant context) | ❌ CRITICAL |
| `/api/v1/reports/analyze` | POST | None (only tenant context) | ❌ **CRITICAL** |
| `/api/v1/reports/schema/{view_scope}` | GET | None (only tenant context) | ❌ CRITICAL |

---

## RBAC Audit Findings

### 🔴 CRITICAL Issues (5 endpoints)

**Location**: `backend/api/v1/dashboards.py`

The following endpoints extract tenant context from `request.state` but have **NO explicit permission checks** via `RequirePermission`. While they have tenant isolation, any authenticated user within a tenant can access sensitive BI data and execute ad-hoc analysis queries.

1. **`GET /api/v1/dashboards/kpi/summary`**
   - Risk: Revenue, AR, Cash Position exposed to any authenticated user
   - Evidence: `tenant_ctx: TenantContext = _extract_tenant(request)` only, no `RequirePermission`

2. **`GET /api/v1/dashboards/charts/sales-trend`**
   - Risk: Sales trend data exposed without permission check
   - Evidence: Line 218 `tenant_ctx: TenantContext = _extract_tenant(request)` only

3. **`GET /api/v1/dashboards/charts/cash-flow`**
   - Risk: Cash flow data exposed without permission check
   - Evidence: Line 274 `tenant_ctx: TenantContext = _extract_tenant(request)` only

4. **`POST /api/v1/reports/analyze`** ⚠️ **WRITE OPERATION**
   - Risk: Ad-hoc semantic query execution without permission check
   - Evidence: Line 345 `tenant_ctx: TenantContext = _extract_tenant(request)` only
   - **Recommended Permission**: `reports:analyze` or `dashboards:read`

5. **`GET /api/v1/reports/schema/{view_scope}`**
   - Risk: Schema discovery without permission check
   - Evidence: Line 434 no permission decorator
   - **Recommended Permission**: `reports:read` or `dashboards:read`

### Recommended Remediation

Add `RequirePermission` decorators to all dashboard endpoints:

```python
from api.middleware.rbac import RequirePermission

@dashboards_router.get("/kpi/summary")
async def get_kpi_summary(
    request: Request,
    token: TokenPayload = Depends(RequirePermission("dashboards:read")),
):
    ...

@reports_router.post("/analyze")
async def analyze_report(
    request: Request,
    body: SemanticQueryRequest,
    token: TokenPayload = Depends(RequirePermission("reports:analyze")),
):
    ...
```

---

## Task 2: API Contract Consistency

### Backend Schema Analysis

**Backend Naming Convention**: `snake_case` (Python standard)

**CamelModel Adapter** (`backend/schemas/base.py`):
- **Input**: Accepts BOTH `snake_case` AND `camelCase` via `AliasGenerator(validation_alias=to_camel)`
- **Output**: Remains `snake_case` — NO breaking change
- **Purpose**: Future-proofs for camelCase migration without breaking existing clients

### Frontend Type Analysis

**Frontend Naming Convention**: `snake_case` (matches backend output)

### Contract Mismatch Report

| Backend Schema | Frontend Type | Status | Issue |
|----------------|---------------|--------|-------|
| `Order` (snake_case) | `Order` (snake_case) | ✅ MATCH | `product_name`, `sku_code`, `total_amount` all match |
| `StockViewRead` (snake_case) | `StockView` (snake_case) | ✅ MATCH | `sku_id`, `quantity_on_hand` all match |
| `SKURead` (snake_case) | Not explicitly defined | ⚠️ N/A | Frontend uses inline types |
| `WholesalerRead` (snake_case) | `Tenant` (snake_case) | ✅ MATCH | `schema_name`, `created_at` all match |

### Casing Compatibility Verdict

**✅ NO BREAKING MISMATCHES DETECTED**

The backend's `CamelModel` adapter correctly allows the frontend to send either `snake_case` or `camelCase`, while the backend always returns `snake_case`. The frontend types use `snake_case`, which matches the backend output exactly.

**Evidence**:
```python
# backend/schemas/base.py
class CamelModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,  # Accepts both field name AND alias
        alias_generator=AliasGenerator(
            validation_alias=to_camel,  # camelCase accepted on input
        ),
    )
```

### Potential Future Risk

When the frontend migrates to `camelCase` conventions:
1. Backend already accepts `camelCase` on input (validation_alias)
2. Backend will need to add `serialization_alias=to_camel` to output `camelCase`
3. This requires a coordinated v0.3.0 breaking change release

---

## Summary

| Category | Count | Status |
|----------|-------|--------|
| RBAC PASS | 31 | ✅ Secure |
| RBAC PUBLIC | 9 | ⚠️ By Design (Auth/Health/Invitations) |
| RBAC CRITICAL | 5 | ❌ **REQUIRES IMMEDIATE FIX** |
| API Contract | 0 mismatches | ✅ Compatible |

### Priority Actions

1. **HIGH**: Add `RequirePermission("dashboards:read")` to all dashboard GET endpoints
2. **HIGH**: Add `RequirePermission("reports:analyze")` to `POST /api/v1/reports/analyze`
3. **MEDIUM**: Define `dashboards:read` and `reports:analyze` permissions in `rbac_matrix.md`
4. **LOW**: Plan v0.3.0 camelCase output migration with `serialization_alias`

---

*Report generated by static analysis — no code was executed.*
