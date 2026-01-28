# Phase B5 — Payments Minimal Loop (Completion)

## Scope (MVP / Phase B5)

- Implement `POST /api/v1/payments` to record payments against an existing order.
- Enforce idempotency for transfer payments via:
  - Required `Idempotency-Key` header (contract requirement).
  - `transaction_id` uniqueness (DB constraint) and deterministic conflict behavior.
- Maintain a cached `outstanding_balance` per wholesaler–retailer pair.

## Non-Goals (explicit)

- No real payment gateway integration (M-Pesa API, callbacks, webhooks) — transfer is treated as synchronous.
- No refunds, reversals, chargebacks.
- No payment confirmation workflow beyond `status` field.
- No order state-machine expansion (orders remain `draft|confirmed|cancelled` as per current repo/OpenAPI).

## Contract Alignment

- **API Contract**: `Read before building/#11 kiro_api_contract (v1.1).md` and `docs/contracts/api_contract.md`
  - `POST /api/v1/payments` exists.
  - Payment methods: `cash | transfer | credit`.
  - Transfer payments require `Idempotency-Key`.
  - `transaction_id` stores external reference (e.g. M-Pesa code) and must be unique per-tenant.
  - Duplicate transaction_id returns 409 with business code `DUPLICATE_TRANSACTION_ID`.

- **RBAC**:
  - Permission used: `payments:create`.

## API: `POST /api/v1/payments`

- **Path**: `/api/v1/payments`
- **Auth**: Bearer JWT + RBAC `payments:create`
- **Headers**:
  - `Idempotency-Key`: REQUIRED when `method=transfer`
- **Body**:
  - `order_id` (uuid)
  - `amount` (> 0)
  - `method` in `cash|transfer|credit`
  - `transaction_id` (string, REQUIRED for `transfer`)

### Behavior Rules

- `method=transfer`
  - Requires `Idempotency-Key`.
  - Requires `transaction_id`.
  - Payment created with `status=completed`.
  - Updates `outstanding_balance += (-amount)`.

- `method=credit`
  - Payment created with `status=pending`.
  - Updates `outstanding_balance += (+amount)` (exposure increases).

- `method=cash`
  - Payment created with `status=pending`.
  - Does **not** update `outstanding_balance` in B5 minimal loop.

## Idempotency & Uniqueness Design

### Transfer idempotency inputs

- `Idempotency-Key` header is required for transfer (network retry safety).
- `transaction_id` is enforced unique at DB level (tenant schema).

### Implementation details

- Primary guard: **unique index** on `payments.transaction_id` (where not null).
- Logic:
  1) If `transaction_id` exists already:
     - If payload matches (`order_id`, `amount`, `method`), return the existing record (idempotent success).
     - Otherwise return 409 with `DUPLICATE_TRANSACTION_ID`.
  2) On concurrent insertion race:
     - Insert may raise `IntegrityError` due to uniqueness constraint.
     - Service catches it, re-queries by `transaction_id`, and applies the same payload-match vs conflict decision.

This ensures correctness under concurrency and retries.

## Data Model / Migrations

### Tenant schema

- New table: `payments`
  - `id` uuid pk
  - `order_id` uuid fk -> `orders.id`
  - `retailer_id` uuid
  - `transaction_id` nullable string
  - `amount` numeric(12,2)
  - `method` string
  - `status` string
  - audit columns (created_at/updated_at/is_deleted/deleted_at/created_by/updated_by)
- Unique index:
  - `uq_payments_transaction_id` on `transaction_id` where not null

### Public schema

- New column: `public.wholesaler_retailer_bindings.outstanding_balance numeric(12,2) NOT NULL default 0`

### Migration

- `backend/alembic/versions/005_phase_b5_payments_minimal_loop.py`
  - Runs as tenant migration when `search_path` indicates tenant schema.
  - Runs as public migration otherwise.

## Transactional Consistency

- `outstanding_balance` update is executed using the tenant session (`tenant_db`) directly against the `public.*` table. This avoids a “two-session” partial-update risk.

## Code Changes (Files)

- Backend API:
  - `backend/api/v1/payments.py` (new)
  - `backend/api/app.py` (register payments router)

- Service / Repo:
  - `backend/services/payment_service.py` (new)
  - `backend/repositories/payment_repository.py` (new)

- Schemas:
  - `backend/schemas/payment.py` (new)

- DB Migration:
  - `backend/alembic/versions/005_phase_b5_payments_minimal_loop.py` (new)

- Tests:
  - `backend/tests/test_payments_api.py` (new)

- OpenAPI:
  - `docs/contracts/openapi.yaml` updated to include:
    - `payments` tag
    - `/payments` POST
    - Payment schemas

## Tests Added

- `transfer` missing idempotency key -> 400 `MISSING_IDEMPOTENCY_KEY`
- `transaction_id` same payload -> idempotent success
- `transaction_id` different payload -> 409 `DUPLICATE_TRANSACTION_ID`
- `cash` does not update outstanding balance

## Known Gaps / Follow-ups

- No `GET /payments` listing endpoint yet.
- No credit limit enforcement in `orders:confirm` in current repo (contract mentions it but implementation is not part of B5 minimal loop).
- `cash` handling vs COD semantics may be refined in later phases (B5 currently treats `cash` as a recorded payment without balance impact).
