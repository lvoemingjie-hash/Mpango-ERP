# S1-2: Auth Strategy Refactor

## Objective
Refactor authentication into a Strategy Pattern so authentication behavior is selected by environment wiring (DI) rather than inlined environment conditionals.

Key requirements:
- Authentication middleware must be environment-agnostic.
- All `MPANGO_TEST_MODE` bypass conditionals must be removed.
- Strategy selection must be based strictly on `MPANGO_ENV`.
- No business logic / API shape changes.

## Design Summary
### Strategy interface
A single interface (`backend/auth/strategy.py`) defines the contract used by middleware:
- `authenticate(request) -> Optional[AuthContext]`
- `resolve_tenant_context(auth_ctx) -> TenantContext`

This isolates:
- token parsing and validation
- tenant/user resolution

from the middleware.

### Strategy implementations
- **`backend/auth/strategies/jwt.py`**
  - Production strategy.
  - Extracts bearer token and validates/decodes it into `AuthContext`.
  - Resolves tenant context from the JWT claims.
  - Note: tenant resolution import is lazy inside `resolve_tenant_context` to keep module import lightweight.

- **`backend/auth/strategies/mock.py`**
  - Test strategy.
  - Injects deterministic mock identity and permissions.
  - Uses `_LazyTenantSession` so DB connections are only established if an endpoint actually executes DB operations.

### Strategy selection (single env switch)
`backend/auth/factory.py` is the only location allowed to branch on environment:
- `MPANGO_ENV=test` -> `MockAuthStrategy`
- otherwise -> `JwtAuthStrategy`

This enforces the invariant that the middleware does not contain environment checks.

### Middleware wiring (DI)
`backend/api/app.py` wires the selected strategy into middleware during app configuration:
- `app.add_middleware(AuthenticationMiddleware, strategy=get_auth_strategy())`

`backend/api/middleware/auth.py`:
- delegates authentication and tenant resolution to the injected strategy
- attaches contexts to `request.state`
- does not branch on environment

## Removal of `MPANGO_TEST_MODE`
All test-mode bypass logic was removed from:
- authentication middleware
- request dependencies
- test/config environments
- docker-compose env wiring

`MPANGO_ENV` is now the single control for strategy selection.

## Tests
Tests were updated to validate both behaviors:
- `MPANGO_ENV=test` allows requests through without a JWT, while preserving permission checks.
- `MPANGO_ENV=production` rejects unauthenticated requests with `401` and rejects invalid auth schemes.

Additionally, tenant context helper imports were made lazy so unit/integration tests can be collected/run in environments that don’t have a PostgreSQL async driver installed.

## Invariants / Guardrails
- **Single env branch**: Only `auth.factory.get_auth_strategy()` may inspect `MPANGO_ENV`.
- **Middleware is environment-agnostic**: No environment checks in middleware.
- **No API shape changes**: endpoints and response formats remain unchanged.
- **Tenant isolation rules preserved**: tenant context resolution remains derived from JWT claims in production.

## Files Changed / Added
- Added:
  - `backend/auth/strategy.py`
  - `backend/auth/factory.py`
  - `backend/auth/strategies/jwt.py`
  - `backend/auth/strategies/mock.py`
  - `backend/auth/__init__.py`
  - `backend/auth/strategies/__init__.py`
- Updated:
  - `backend/api/middleware/auth.py`
  - `backend/api/app.py`
  - `backend/api/dependencies.py`
  - `backend/tests/test_auth_bypass.py`
  - `backend/tests/test_test_mode_auth_bypass.py`
  - `backend/tests/conftest.py`
  - `docker-compose.yml`
  - `docker-compose.override.yml`
  - `b6_test_mode_verification.py`

## Notes
The changes are intentionally structural: responsibilities were reallocated into strategy modules and wired via DI. Core security/token semantics and business behavior are unchanged.
