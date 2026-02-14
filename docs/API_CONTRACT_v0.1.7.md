# API_CONTRACT_v0.1.7 (Frozen)

**Status**: API Freeze — Track C complete
**Date**: 2026-02-13

---

## Section 1: Authentication Protocol (Frozen)

### Token Lifecycle
- **Access Token TTL**: **30 minutes** (`ACCESS_TOKEN_EXPIRE_MINUTES=30`) — @backend/core/config.py#57-60
- **Refresh Token TTL**: **7 days** (`REFRESH_TOKEN_EXPIRE_DAYS=7`) — @backend/core/config.py#61-64

### Security
- **Algorithm**: **HS256** — @backend/core/config.py#53-56
- **Header Format**: `Authorization: Bearer <token>`
- **JWT Claims**: `user_id`, `tenant_id`, `tenant_schema`, `exp`, `type` — @backend/core/security.py#74-79

### Endpoints (Exact Schemas)

#### `POST /auth/login`
**Request** — `LoginRequest` (@backend/schemas/auth.py#10-28)
```json
{
  "tenant_code": "ACME01",
  "email": "admin@example.com",
  "password": "string (min 8)"
}
```

**Response** — `LoginResponse` (@backend/schemas/auth.py#49-61)
```json
{
  "success": true,
  "data": {
    "access_token": "...",
    "refresh_token": "...",
    "token_type": "bearer",
    "user_id": "uuid",
    "tenant_id": "uuid",
    "tenant_schema": "t_<uuid_without_dashes>"
  },
  "timestamp": "2026-02-13T00:00:00Z"
}
```

#### `POST /auth/refresh`
**Request** — `RefreshTokenRequest` (@backend/schemas/auth.py#64-71)
```json
{
  "refresh_token": "..."
}
```

**Response** — `LoginResponse` (same as `/auth/login`)

#### `POST /auth/logout`
**Request**
- Requires valid Authorization header.

**Response** — `MessageResponse` (@backend/schemas/common.py#56-66)
```json
{
  "success": true,
  "message": "Logged out successfully",
  "timestamp": "2026-02-13T00:00:00Z"
}
```

#### `GET /auth/me`
**Request**
- Requires valid Authorization header.

**Response** — `CurrentUserResponse` (@backend/schemas/auth.py#93-104)
```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "email": "admin@example.com",
    "full_name": "Admin User",
    "tenant_id": "uuid",
    "tenant_schema": "t_<uuid_without_dashes>",
    "roles": ["admin"],
    "permissions": ["users:read", "wholesalers:write", "..."]
  },
  "timestamp": "2026-02-13T00:00:00Z"
}
```

---

## Section 2: Error Agreement (The "Adapter" Standard)

### 422 — Validation
FastAPI default validation error shape:
```json
{
  "detail": [
    {
      "loc": ["body", "field"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 409 — Conflict
Example from `/wholesalers` create:
```json
{
  "detail": {
    "code": "WHOLESALER_CODE_EXISTS",
    "message": "Wholesaler code 'ACME01' already exists"
  }
}
```

### 403 — Forbidden
RBAC enforcement via `RequirePermission`:
```json
{
  "detail": {
    "code": "PERMISSION_DENIED",
    "message": "Permission 'wholesalers:write' required"
  }
}
```

---

## Section 3: RBAC Nomenclature (Frozen)

### Active Permission Codes (seeded)
From `create_wholesaler.py` permission seed list:
- **users**: `users:read`, `users:create`, `users:update`, `users:deactivate`
- **wholesalers**: `wholesalers:read`, `wholesalers:write`
- **roles**: `roles:read`, `roles:create`, `roles:update`, `roles:delete`, `roles:assign`
- **orders**: `orders:read`, `orders:create`, `orders:update`, `orders:confirm`, `orders:ship`, `orders:cancel`

### Role Mapping
- **admin** role is assigned **all permissions** during tenant bootstrap (see `assign_all_permissions_to_admin`).
- No `SuperAdmin` role is defined in the current codebase.

---

## Section 4: Domain Entities (Wholesaler MVP)

### Wholesaler Schema
**Model**: `public.wholesalers` — @backend/models/wholesaler.py#13-56

| Field | Type | Constraints | Nullability |
|------|------|-------------|------------|
| `id` | UUID | primary key | NOT NULL |
| `code` | varchar(32) | unique, regex `^[A-Z0-9]+$`, immutable | NOT NULL |
| `name` | varchar(255) | — | NOT NULL |
| `address` | text | — | NULL |
| `contact` | text | — | NULL |
| `plan_type` | varchar(50) | — | NULL |
| `created_at` | datetime | auto | NOT NULL |
| `updated_at` | datetime | auto | NOT NULL |

### CRUD Endpoints (Wholesaler)
- `GET /wholesalers` — list with pagination (`skip`, `limit`, or `page`, `size`)
- `POST /wholesalers` — create
- `GET /wholesalers/{id}` — read by UUID
- `PUT /wholesalers/{id}` — update
- `DELETE /wholesalers/{id}` — soft delete

**Permissions**
- `wholesalers:read` → list/read
- `wholesalers:write` → create/update/delete

---

**Freeze Version**: v0.1.7
**Authority**: CTO
