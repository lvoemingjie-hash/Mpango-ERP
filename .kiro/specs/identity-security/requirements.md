# Requirements Document: Identity & Security Layer

## Introduction

This specification defines the requirements for the Mpango ERP Identity & Security Layer. This layer implements JWT authentication, tenant resolution from tokens, and RBAC enforcement. It builds on the backend skeleton to provide secure, multi-tenant access control.

## Glossary

- **JWT**: JSON Web Token used for authentication, containing user_id, tenant_id, tenant_schema claims
- **Access_Token**: Short-lived JWT (30 minutes) for API authentication
- **Refresh_Token**: Long-lived JWT (7 days) for obtaining new access tokens
- **Tenant_Resolution**: Process of extracting tenant_id and tenant_schema from JWT claims
- **RBAC**: Role-Based Access Control using Permission.code format `<resource>:<action>`
- **Permission_Code**: String in format `<resource>:<action>` (e.g., `users:read`, `orders:create`)
- **Current_User**: Authenticated user context including user_id, tenant_id, roles, and permissions

## Requirements

### Requirement 1: JWT Token Generation

**User Story:** As a user, I want to receive JWT tokens upon successful login, so that I can authenticate subsequent API requests.

#### Acceptance Criteria

1. WHEN a user provides valid tenant_code, email, and password, THE Auth_Service SHALL generate an access_token and refresh_token
2. THE Access_Token SHALL contain claims: user_id (UUID), tenant_id (UUID), tenant_schema (string), exp (expiration)
3. THE Access_Token SHALL expire after 30 minutes (configurable via ACCESS_TOKEN_EXPIRE_MINUTES)
4. THE Refresh_Token SHALL expire after 7 days (configurable via REFRESH_TOKEN_EXPIRE_DAYS)
5. THE Auth_Service SHALL use HS256 algorithm with SECRET_KEY for token signing
6. IF tenant_code is not found in public.wholesalers, THEN THE Auth_Service SHALL return HTTP 404

### Requirement 2: JWT Token Validation

**User Story:** As a backend service, I want to validate JWT tokens on every request, so that only authenticated users can access protected endpoints.

#### Acceptance Criteria

1. WHEN a request includes a valid Bearer token, THE Auth_Middleware SHALL extract and validate the token
2. IF the token signature is invalid, THEN THE Auth_Middleware SHALL return HTTP 401 with error code INVALID_TOKEN
3. IF the token is expired, THEN THE Auth_Middleware SHALL return HTTP 401 with error code TOKEN_EXPIRED
4. IF the Authorization header is missing, THEN THE Auth_Middleware SHALL return HTTP 401 with error code MISSING_TOKEN
5. THE Auth_Middleware SHALL decode token claims and make them available to route handlers

### Requirement 3: Token Refresh

**User Story:** As a user, I want to refresh my access token using a refresh token, so that I can maintain my session without re-entering credentials.

#### Acceptance Criteria

1. WHEN a valid refresh_token is provided, THE Auth_Service SHALL generate new access_token and refresh_token
2. IF the refresh_token is expired, THEN THE Auth_Service SHALL return HTTP 401 with error code REFRESH_TOKEN_EXPIRED
3. IF the refresh_token is invalid, THEN THE Auth_Service SHALL return HTTP 401 with error code INVALID_REFRESH_TOKEN
4. THE new tokens SHALL contain the same tenant_id and tenant_schema as the original

### Requirement 4: Tenant Resolution from JWT

**User Story:** As a backend service, I want to resolve tenant context from JWT claims, so that database queries are isolated to the correct tenant schema.

#### Acceptance Criteria

1. WHEN processing an authenticated request, THE Tenant_Resolver SHALL extract tenant_id and tenant_schema from JWT claims
2. THE Tenant_Resolver SHALL set database search_path to `"<tenant_schema>", public` for each request
3. THE Tenant_Resolver SHALL NOT allow tenant_schema to be overridden by request headers or parameters
4. IF tenant_schema claim is missing from token, THEN THE Tenant_Resolver SHALL return HTTP 401

### Requirement 5: RBAC Permission Enforcement

**User Story:** As a system administrator, I want endpoints protected by RBAC permissions, so that users can only access resources they are authorized for.

#### Acceptance Criteria

1. THE RBAC_Middleware SHALL check user permissions against required Permission.code for each endpoint
2. WHEN a user lacks the required permission, THE RBAC_Middleware SHALL return HTTP 403 with error code PERMISSION_DENIED
3. THE RBAC_Middleware SHALL load user permissions from roles via role_permissions table
4. THE Permission.code format SHALL be `<resource>:<action>` per rbac_matrix.md
5. THE admin role SHALL have ALL permissions (bypass permission checks)

### Requirement 6: Current User Endpoint

**User Story:** As a user, I want to retrieve my current user information from the token, so that I can display my profile and permissions in the UI.

#### Acceptance Criteria

1. WHEN GET /auth/me is called with valid token, THE Auth_Service SHALL return CurrentUserResponse
2. THE CurrentUserResponse SHALL include: id, email, full_name, tenant_id, tenant_schema, roles, permissions
3. THE roles field SHALL contain role names (strings), not role objects
4. THE permissions field SHALL contain all Permission.code values the user has via their roles
5. IF token is invalid, THEN THE Auth_Service SHALL return HTTP 401

### Requirement 7: Password Verification

**User Story:** As a backend service, I want to securely verify user passwords, so that only users with correct credentials can authenticate.

#### Acceptance Criteria

1. THE Auth_Service SHALL use bcrypt for password hashing and verification
2. THE Auth_Service SHALL compare provided password against stored password_hash
3. IF password is incorrect, THEN THE Auth_Service SHALL return HTTP 401 with error code INVALID_CREDENTIALS
4. IF user is_active is false, THEN THE Auth_Service SHALL return HTTP 400 with error code USER_INACTIVE
5. THE Auth_Service SHALL NOT reveal whether email or password was incorrect (generic error message)

### Requirement 8: Endpoint Permission Mapping

**User Story:** As a developer, I want clear mapping between endpoints and required permissions, so that RBAC is consistently enforced.

#### Acceptance Criteria

1. THE following endpoints SHALL require the specified permissions per openapi.yaml:
   - GET /users → users:read
   - POST /users → users:create
   - PUT /users/{id} → users:update
   - DELETE /users/{id} → users:deactivate
   - PUT /users/{id}/roles → roles:assign
   - GET /roles → roles:read
   - GET /orders → orders:read
   - POST /orders → orders:create
   - GET /orders/{id} → orders:read
   - POST /orders/{id}/confirm → orders:confirm
   - POST /orders/{id}/ship → orders:ship
   - POST /orders/{id}/cancel → orders:cancel
2. THE /auth/* endpoints (login, refresh, logout, me) SHALL NOT require RBAC permissions (only authentication)
