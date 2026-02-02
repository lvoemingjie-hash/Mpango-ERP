# B6 Hardening Tests

## What this folder is

This folder contains the **B6 Hardening Patch Sprint** test suite only.

- All tests in this folder follow the naming convention: `test_b6_*`.
- These tests are intended to be runnable independently of the legacy test suite.

## P1: Global Tenant Context Enforcement

**Goal:** Prevent accidental cross-tenant ORM access by requiring an explicit tenant context for ORM operations.

Key behaviors:

- ORM SELECT/UPDATE/DELETE operations require tenant context (via `session.info["tenant_schema"]` or request-scoped contextvars).
- Missing tenant context raises `RuntimeError("Tenant context required")`.
- Escape hatch: `execution_options(ignore_tenant=True)` bypasses enforcement for intentionally global/public operations.

Related implementation:

- `backend/db/tenant_filter.py`
- Test coverage: `test_b6_global_tenant_filter.py`

## P3: Payment Idempotency via `payments.idempotency_key`

**Goal:** Make transfer payment creation idempotent with an explicit idempotency key, unique per tenant schema.

Key behaviors:

- `POST /api/v1/payments` with `method=transfer` requires the header `X-Idempotency-Key`.
- The idempotency key is persisted in `payments.idempotency_key` (unique index per tenant schema).
- Same key + same payload: returns the existing payment record.
- Same key + different payload: returns `409` with code `IDEMPOTENCY_CONFLICT`.

Related implementation:

- Migration: `backend/alembic/versions/006_phase_b6_payments_idempotency_key.py`
- Repo/service: `backend/repositories/payment_repository.py`, `backend/services/payment_service.py`
- Endpoint: `backend/api/v1/payments.py`
- Test coverage: `test_b6_payments_api.py`

## How to run only B6 tests

From host (runs inside the backend container):

```bash
docker compose exec backend poetry run pytest -q backend/tests/b6_hardening
```

Or run only the B6 tests by name pattern:

```bash
docker compose exec backend poetry run pytest -q -k "test_b6_"
```

## Alembic invocation (tenant schema)

Alembic must be invoked via Poetry:

```bash
docker compose exec backend poetry run alembic -x tenant_schema=t_b6_verify upgrade head
```
