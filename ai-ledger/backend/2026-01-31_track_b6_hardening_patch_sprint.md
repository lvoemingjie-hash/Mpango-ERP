# Track B6 Hardening Patch Sprint (Backend)

## Scope
This sprint applies **security and consistency hardening only** (no new business features, no API shape changes except tightening idempotency header requirements for transfer payments).

Changes covered:
- Tenant session marking and CRUD scoping enforcement.
- Global ORM tenant context enforcement (P1).
- Payment creation atomicity.
- Transfer payment idempotency header enforcement and DB-backed idempotency key persistence (P3).
- Authorization hardening: forbid admin-role/boolean bypass; permission-code checks only.

## Tenant isolation hardening
### Tenant-aware session marking
- Tenant-scoped sessions are explicitly marked via `session.info["tenant_schema"]`.
- This is used as a guardrail to prevent accidental ORM access with an unscoped session.

Files:
- `backend/database/session.py`

### Global ORM tenant enforcement (do_orm_execute)
- Implemented a global SQLAlchemy ORM enforcement hook using `SessionEvents.do_orm_execute`.
- For any ORM SELECT/UPDATE/DELETE, the hook requires tenant context to be present (derived from `session.info["tenant_schema"]` or a contextvar). If missing, it raises `RuntimeError("Tenant context required")`.
- Escape hatch supported via `execution_options(ignore_tenant=True)`.
- Future-proofing: if a mapped model has a `tenant_id` column, the hook applies `with_loader_criteria` to add an automatic `tenant_id == current_tenant_id` predicate.

Files:
- `backend/db/tenant_filter.py`
- `backend/api/middleware/auth.py` (sets/resets tenant contextvars per request)
- `backend/api/context/tenant.py` (marks sessions with tenant_schema)
- Tests:
  - `backend/tests/b6_hardening/test_b6_global_tenant_filter.py`

### CRUD scoped wrapper enforcement
- `CRUDBase.scoped(db)` returns a wrapper that enforces the provided session has `tenant_schema` set.
- If missing, a `RuntimeError("Tenant session required")` is raised.

Files:
- `backend/crud/base.py`
- Tests: `backend/tests/test_crud_scoped.py`

## Payments consistency hardening
### Atomic transaction boundary
- `PaymentService.create_payment(...)` now executes inside a single `async with tenant_db.begin():` transaction.
- This ensures that:
  - payment row creation
  - outstanding balance adjustments
  - any subsequent DB mutations
  either all commit or all roll back.

Files:
- `backend/services/payment_service.py`
- Tests:
  - `backend/tests/b6_hardening/test_b6_payment_atomicity.py` (forces a failure during balance update and asserts transaction context exits with exception).

### Transfer idempotency enforcement
#### Header requirement
- For `method == transfer`, requests must include `X-Idempotency-Key`.
- Legacy `Idempotency-Key` header is not accepted for transfer.

Files:
- `backend/api/v1/payments.py`
- Tests:
  - `backend/tests/b6_hardening/test_b6_payments_api.py`

#### Idempotency key persistence + uniqueness
- Added a dedicated `payments.idempotency_key` column.
- Added tenant-schema unique index `uq_payments_idempotency_key` on `idempotency_key` (partial index, `idempotency_key IS NOT NULL`).

Uniqueness alignment:
- With schema-per-tenant (`search_path`) isolation, uniqueness within the tenant schema is equivalent to `(tenant_id, idempotency_key)` uniqueness.

Files:
- Migration: `backend/alembic/versions/006_phase_b6_payments_idempotency_key.py`
- `backend/repositories/payment_repository.py`
- `backend/services/payment_service.py`

Runtime behavior:
- Same key + same payload: return existing record.
- Same key + different payload: return `409` with code `IDEMPOTENCY_CONFLICT`.

## Authorization hardening
### Forbid admin bypass
- Removed role-name-based bypass logic (`if "admin" in role_names: allow`) from `RequirePermission`.
- All access checks now depend solely on explicit permission codes.

Files:
- `backend/api/middleware/rbac.py`
- Updated tests:
  - `backend/tests/test_rbac_enforcement.py`
  - `backend/tests/test_users_roles_api.py`

## Verification
### B6-only test suite

Dedicated B6 test group:

- Folder: `backend/tests/b6_hardening/`
- Naming convention: all tests start with `test_b6_`
- README: `backend/tests/b6_hardening/README.md`

Executed in Docker container (test dependencies installed via `INSTALL_TEST_DEPS=true` build arg). Note that the backend container does not volume-mount source; after adding new B6-only tests, a rebuild is required.

- `docker compose build --build-arg INSTALL_TEST_DEPS=true backend`
- `docker compose up -d backend`
- `docker compose exec backend poetry run pytest -q tests/b6_hardening`
  - Result: **10 passed**
- `docker compose exec backend poetry run pytest -q tests/test_rbac_enforcement.py tests/test_users_roles_api.py`
  - Result: **46 passed**

### Alembic invocation (tenant schema)

Alembic must be invoked via Poetry:

- `docker compose exec backend poetry run alembic -x tenant_schema=t_b6_verify upgrade head`

## Architecture note

- `docs/architecture/b6-hardening.md`

## Risks / Notes
- Removing admin bypass means tenants must explicitly assign permission codes to privileged roles. This is intended: access control should be auditable and policy-driven.
- Backend container does not volume-mount backend source; changes require rebuild for container verification.
