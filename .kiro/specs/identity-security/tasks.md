# Implementation Tasks: Identity & Security Layer

## Task 1: Implement JWT Utilities
- [x] Create `backend/core/security.py` with:
  - Custom exceptions: `InvalidTokenError`, `ExpiredTokenError`
  - `create_access_token(user_id, tenant_id, tenant_schema, expires_delta)` → JWT string
  - `create_refresh_token(user_id, tenant_id, tenant_schema, expires_delta)` → JWT string
  - `decode_token(token)` → TokenPayload (raises on invalid/expired)
  - Use `python-jose` for JWT encoding/decoding
  - Use HS256 algorithm with `settings.SECRET_KEY`
  - Access token expires in `settings.ACCESS_TOKEN_EXPIRE_MINUTES` (default 30)
  - Refresh token expires in `settings.REFRESH_TOKEN_EXPIRE_DAYS` (default 7)
- [ ] Requirements: REQ-1, REQ-2, REQ-3
- [ ] Properties: P1, P2, P7

## Task 2: Implement Password Utilities
- [x] Add to `backend/core/security.py`:
  - `hash_password(password)` → hashed string
  - `verify_password(plain_password, hashed_password)` → bool
  - Use `passlib` with bcrypt scheme
- [ ] Requirements: REQ-7
- [ ] Properties: P6

## Task 3: Create Auth Middleware
- [x] Create `backend/api/middleware/__init__.py`
- [x] Create `backend/api/middleware/auth.py` with:
  - `JWTBearer` class extending `HTTPBearer`
  - Validates Bearer token scheme
  - Decodes token and returns `TokenPayload`
  - Returns 401 with appropriate error codes:
    - `MISSING_TOKEN` - no Authorization header
    - `INVALID_TOKEN` - signature invalid
    - `TOKEN_EXPIRED` - token expired
    - `INVALID_TOKEN_TYPE` - wrong token type
- [ ] Requirements: REQ-2
- [ ] Properties: P2, P7

## Task 4: Update Dependencies with Tenant Resolver
- [x] Update `backend/api/dependencies.py`:
  - Add `get_current_user_context(token: TokenPayload = Depends(JWTBearer()))` → TokenPayload
  - Add `get_tenant_db_session(token: TokenPayload = Depends(get_current_user_context))` → AsyncSession
  - Tenant schema ONLY from JWT claims (never headers/params)
  - Sets search_path to `"<tenant_schema>", public`
- [ ] Requirements: REQ-4
- [ ] Properties: P3

## Task 5: Create RBAC Middleware
- [x] Create `backend/api/middleware/rbac.py` with:
  - `RequirePermission` class (callable dependency)
  - Constructor takes `permission: str` (e.g., "users:read")
  - Loads user with roles and permissions from DB
  - Admin role bypasses all permission checks
  - Returns 403 `PERMISSION_DENIED` if user lacks permission
- [ ] Requirements: REQ-5, REQ-8
- [ ] Properties: P4, P5

## Task 6: Create CRUD Functions
- [x] Create `backend/crud/__init__.py`
- [x] Create `backend/crud/wholesaler.py`:
  - `get_wholesaler_by_code(db, code)` → Wholesaler | None
- [x] Create `backend/crud/user.py`:
  - `get_user_by_email(db, email)` → User | None
  - `get_user_with_permissions(db, user_id)` → User with roles/permissions loaded
- [ ] Requirements: REQ-1, REQ-5, REQ-6, REQ-7

## Task 7: Implement Login Endpoint
- [x] Update `backend/api/v1/auth.py` login():
  - Lookup wholesaler by tenant_code in public schema
  - Return 404 `TENANT_NOT_FOUND` if not found
  - Derive tenant_schema from wholesaler.id
  - Switch to tenant schema, find user by email
  - Return 401 `INVALID_CREDENTIALS` if user not found
  - Return 400 `USER_INACTIVE` if user.is_active = false
  - Verify password with bcrypt
  - Return 401 `INVALID_CREDENTIALS` if password wrong
  - Generate access_token and refresh_token
  - Return LoginResponse with tokens and tenant info
- [ ] Requirements: REQ-1, REQ-7

## Task 8: Implement Refresh Endpoint
- [x] Update `backend/api/v1/auth.py` refresh_token():
  - Decode refresh_token
  - Return 401 `INVALID_REFRESH_TOKEN` if invalid
  - Return 401 `REFRESH_TOKEN_EXPIRED` if expired
  - Return 401 `INVALID_TOKEN_TYPE` if not refresh type
  - Generate new access_token and refresh_token
  - Preserve tenant_id and tenant_schema from original
  - Return LoginResponse with new tokens
- [ ] Requirements: REQ-3
- [ ] Properties: P7, P8

## Task 9: Implement /auth/me Endpoint
- [x] Update `backend/api/v1/auth.py` get_current_user():
  - Use `get_current_user_context` dependency for auth
  - Use `get_tenant_db_session` for tenant-scoped DB
  - Load user with permissions
  - Return 401 `USER_NOT_FOUND` if user not in DB
  - Return CurrentUserResponse with:
    - id, email, full_name
    - tenant_id, tenant_schema from token
    - roles (list of role names)
    - permissions (list of permission codes)
- [ ] Requirements: REQ-6

## Task 10: Implement Logout Endpoint
- [x] Update `backend/api/v1/auth.py` logout():
  - Require authentication (JWTBearer)
  - Return success message (client discards tokens)
  - No server-side token invalidation for MVP
- [ ] Requirements: (implicit from openapi.yaml)

## Task 11: Update Route Handlers with RBAC
- [x] Update `backend/api/v1/users.py`:
  - GET /users → RequirePermission("users:read")
  - POST /users → RequirePermission("users:create")
  - GET /users/{id} → RequirePermission("users:read")
  - PUT /users/{id} → RequirePermission("users:update")
  - DELETE /users/{id} → RequirePermission("users:deactivate")
  - PUT /users/{id}/roles → RequirePermission("roles:assign")
- [x] Update `backend/api/v1/roles.py`:
  - GET /roles → RequirePermission("roles:read")
- [x] Update `backend/api/v1/orders.py`:
  - GET /orders → RequirePermission("orders:read")
  - POST /orders → RequirePermission("orders:create")
  - GET /orders/{id} → RequirePermission("orders:read")
  - POST /orders/{id}/confirm → RequirePermission("orders:confirm")
  - POST /orders/{id}/ship → RequirePermission("orders:ship")
  - POST /orders/{id}/cancel → RequirePermission("orders:cancel")
- [ ] Requirements: REQ-8

## Task 12: Add Dependencies to requirements.txt
- [x] Add to `backend/requirements.txt`:
  - `python-jose[cryptography]` - JWT encoding/decoding
  - `passlib[bcrypt]` - Password hashing
- [ ] Verify existing dependencies are compatible

## Task 13: Write Unit Tests for JWT Utilities
- [x] Create `backend/tests/test_jwt_utils.py`:
  - Test create_access_token returns valid JWT
  - Test create_refresh_token returns valid JWT
  - Test decode_token with valid token
  - Test decode_token raises ExpiredTokenError for expired token
  - Test decode_token raises InvalidTokenError for bad signature
  - Test token type validation (access vs refresh)
- [ ] Properties: P1, P2, P7

## Task 14: Write Unit Tests for Password Utilities
- [x] Create `backend/tests/test_password_utils.py`:
  - Test hash_password produces different hash each call (salt)
  - Test verify_password returns True for correct password
  - Test verify_password returns False for wrong password
- [ ] Properties: P6

## Task 15: Write Property-Based Tests
- [x] Create `backend/tests/test_token_properties.py`:
  - P1: Token roundtrip integrity (Hypothesis)
  - P6: Password hash/verify roundtrip (Hypothesis)
  - P8: Refresh preserves claims (Hypothesis)
- [ ] Use Hypothesis for property-based testing

## Task 16: Write RBAC Enforcement Tests
- [x] Create `backend/tests/test_rbac_enforcement.py`:
  - Test user with permission gets 200
  - Test user without permission gets 403
  - Test admin user bypasses permission check
  - Test permission loaded from role_permissions
- [x] Properties: P4, P5

## Task 17: Update AI Ledger
- [x] Create `ai-ledger/backend/2026-01-12_identity_security_implementation.md`:
  - Context: Problem solved
  - Decisions Made: Key implementation choices
  - Contract Compliance: Alignment with openapi.yaml, rbac_matrix.md, multi_tenancy_spec.md
  - Artifacts Created: Files/modules added
  - Blockers/Risks: Deviations or technical debt
  - Next Steps: Dependencies for next phase
