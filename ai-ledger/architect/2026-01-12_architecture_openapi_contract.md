# AI Ledger: OpenAPI Contract Definition

## Metadata
- **AI Role:** Architect AI
- **Date:** 2026-01-12
- **Session Type:** Contract Definition (钢钉1 Compliance)
- **Status:** ✅ Complete

---

## Scope

Define the canonical OpenAPI 3.1 specification for Mpango ERP MVP, establishing the single source of truth for frontend-backend interface contract per 钢钉1 (Steel Nail 1) requirements.

---

## Inputs

### L0 Documents (Immutable)
- `Read before building/Mpango AI workrules.md` - Multi-AI collaboration rules
- `Read before building/#11 kiro_api_contract (v1.1).md` - API design standards
- `docs/contracts/database_contract.md` - Schema definitions
- `docs/contracts/rbac_matrix.md` - Permission codes

### L1 Documents (Frozen for MVP)
- `scenarios/SC-001_wholesaler_login.md` - Login flow requirements
- `scenarios/SC-002_create_user.md` - User management requirements
- `scenarios/SC-003_retailer_place_order.md` - Order creation requirements

### L2 Documents (Reference)
- `decision-register/DR-001_schema-per-tenant.md` - Multi-tenancy decision
- `decision-register/DR-002_crud-base-class.md` - CRUD patterns

---

## Outputs

### Created Files
1. `docs/contracts/openapi.yaml` - Complete OpenAPI 3.1 specification

### Specification Coverage

#### Auth Endpoints (4)
- `POST /auth/login` - Multi-tenant login
- `POST /auth/refresh` - Token refresh
- `POST /auth/logout` - Logout
- `GET /auth/me` - Current user info

#### User Endpoints (6)
- `GET /users` - List users (paginated)
- `POST /users` - Create user
- `GET /users/{user_id}` - Get user
- `PUT /users/{user_id}` - Update user
- `DELETE /users/{user_id}` - Soft delete user
- `PUT /users/{user_id}/roles` - Assign roles

#### Role Endpoints (1)
- `GET /roles` - List roles

#### Order Endpoints (6)
- `GET /orders` - List orders (paginated)
- `POST /orders` - Create order
- `GET /orders/{order_id}` - Get order
- `POST /orders/{order_id}/confirm` - Confirm order
- `POST /orders/{order_id}/ship` - Ship order
- `POST /orders/{order_id}/cancel` - Cancel order

### Component Schemas (25+)
- Common: Pagination, ErrorResponse, ErrorDetail, MessageResponse
- Auth: LoginRequest, LoginResponse, RefreshTokenRequest, CurrentUserResponse
- User: UserCreateRequest, UserUpdateRequest, User, UserResponse, UserListResponse, AssignRolesRequest
- Role: Role, RoleListResponse
- Order: OrderStatus, OrderItemCreate, OrderCreateRequest, OrderItem, Order, OrderResponse, OrderListResponse, OrderActionResponse

---

## Decisions Made

### D1: Response Envelope Pattern
All responses follow unified envelope structure:
```json
{
  "success": true/false,
  "data": {...},
  "message": "optional",
  "timestamp": "ISO8601"
}
```
**Rationale:** Consistent with `kiro_api_contract (v1.1).md` Section 4.

### D2: Error Code Format
Error codes use UPPERCASE_SNAKE_CASE (e.g., `VALIDATION_ERROR`, `INVALID_STATE`).
**Rationale:** Matches API contract specification.

### D3: Pagination Parameters
Standard pagination via query params: `page` (1-based), `size` (max 100).
**Rationale:** Consistent with API contract Section 3.2.

### D4: JWT Claims Structure
Access token contains: `user_id`, `tenant_id`, `tenant_schema`, `exp`.
**Rationale:** Required for multi-tenant request routing per DR-001.

### D5: Permission Codes in OpenAPI
Each endpoint documents required permission code in description.
**Rationale:** Enables Frontend AI to implement proper UI guards.

---

## Known Risks / TODO

1. **Procurement & Finance endpoints not included** - MVP scope limited to Auth, Users, Orders
2. **Product/Retailer/Inventory endpoints pending** - Will be added in next iteration
3. **Idempotency-Key header** - Documented in API contract but not yet added to OpenAPI (applies to receive/transfer operations)

---

## Validation

- [x] OpenAPI 3.1 syntax valid
- [x] All MVP scenarios (SC-001, SC-002, SC-003) have corresponding endpoints
- [x] Response schemas match database contract types
- [x] Permission codes match RBAC matrix
- [x] Error response format matches API contract

---

## Steel Nail Compliance

| Steel Nail | Status | Evidence |
|------------|--------|----------|
| 钢钉1: OpenAPI is ONLY interface truth | ✅ | `docs/contracts/openapi.yaml` created |
| 钢钉2: DB Schema is ONLY data shape truth | ✅ | Schemas derived from `database_contract.md` |
| 钢钉3: Executable Scenarios exist | ✅ | Endpoints map to `/scenarios/SC-*` |

---

**Next AI:** Backend AI should implement endpoints exactly as specified in `openapi.yaml`.
