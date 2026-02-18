# Mpango ERP: Exception & Edge-Case Strategy

> **Authority**: This document defines the canonical error-handling policies for the
> Mpango ERP backend and frontend.  Every new module MUST follow these rules.

---

## 1. Error Code Taxonomy

All business‐logic failures return a structured error body:

```json
{
  "code": "SCREAMING_SNAKE_CASE",
  "message": "Human-readable description"
}
```

| HTTP Status | When to use | Example codes |
|---|---|---|
| `400 Bad Request` | Malformed input, missing required field | `INVALID_ORDER_ID`, `MISSING_IDEMPOTENCY_KEY` |
| `404 Not Found` | Entity does not exist (or soft-deleted) | `ORDER_NOT_FOUND`, `SKU_NOT_FOUND` |
| `409 Conflict` | Optimistic lock failure, stock shortage, idempotency collision | `INVENTORY_SHORTAGE`, `IDEMPOTENCY_CONFLICT`, `STALE_VERSION` |
| `403 Forbidden` | RBAC denial or tenant isolation violation | `PERMISSION_DENIED`, `TENANT_MISMATCH` |
| `422 Unprocessable` | Valid JSON but fails domain rules | `INVALID_STATE_TRANSITION` |
| `500 Internal Server Error` | Unexpected bugs only — **never** for business logic | — |

**Rule**: Generic 500s for business logic are a **bug**, not a feature.

---

## 2. Payment Timeout Policy (M‑Pesa Specific)

| Scenario | Backend behaviour | Frontend behaviour |
|---|---|---|
| M-Pesa STK push times out (>30s) | Mark payment as `pending`, return `202 Accepted` with `code: PAYMENT_PENDING` | Show spinner + "Waiting for M-Pesa confirmation…" toast |
| M-Pesa callback arrives (success) | Idempotently complete the payment (match by `transaction_id`); post ledger entries | N/A (server-side only) |
| M-Pesa callback arrives (failure) | Mark payment as `failed`; do NOT create ledger entries | N/A |
| Callback never arrives (>5 min) | Background job marks payment `timed_out`; operator manually reconciles | Dashboard shows "Unresolved payments" amber badge |
| Duplicate callback | Idempotency key prevents double-ledgering — return cached original response | No change |

### Idempotency Enforcement

1. **All mutating endpoints** pass through `IdempotencyMiddleware` (header: `X-Idempotency-Key`).
2. **Payment service** has a secondary check at the repository level using `idempotency_key` column with `UNIQUE` constraint.
3. If key matches existing payload → return cached result (200).
4. If key matches different payload → return `409 IDEMPOTENCY_CONFLICT`.

---

## 3. Inventory Concurrency Policy

### Problem
Two concurrent requests attempt to deduct stock for the same SKU.  Without locking,
both may "see" sufficient stock and both succeed, over-selling inventory.

### Solution: Pessimistic Locking (`SELECT FOR UPDATE`)

```sql
-- Inside inventory deduction transaction:
SELECT quantity_on_hand, quantity_reserved
  FROM inventory_stock
 WHERE sku_id = :sku_id AND is_deleted = FALSE
   FOR UPDATE;          -- Row-level lock, blocks other transactions

-- Check: available = on_hand - reserved
-- If available < requested_qty → ROLLBACK, return 409 INVENTORY_SHORTAGE
-- Else: UPDATE inventory_stock SET quantity_reserved = quantity_reserved + :qty
```

### Error Response (409):

```json
{
  "code": "INVENTORY_SHORTAGE",
  "message": "Insufficient stock for SKU 'UNGA-2KG'. Available: 5, requested: 10."
}
```

### Frontend handling:
The `api.ts` response interceptor already handles **409** status with a warning toast:
```
Title: "Action Not Allowed"
Message: (server-provided message)
```

---

## 4. Network Disconnect Policy (Frontend)

| Scenario | Behaviour |
|---|---|
| Request timeout (>15s) | Axios `timeout: 15_000` fires. Show error toast "Request timed out" |
| Server unreachable | Axios network error. Show error toast "Unable to reach server" |
| Token expired mid-session | Interceptor auto-refreshes token via `/auth/refresh`. Queues failed requests |
| Refresh also fails | Logout user, redirect to `/login` |
| Offline → Online | No auto-retry. User must manually re-trigger actions |

### Optimistic UI forbidden
State changes (order transitions, payments) are **never** applied optimistically.
The UI always waits for confirmation from the server before updating displayed state.

---

## 5. Tenant Isolation Invariants

1. **JWT-only derivation**: Tenant schema is derived exclusively from the JWT `tenant_schema` claim.  Never from URL, headers, or query params.
2. **Session-level guardrail**: Every tenant-scoped DB session sets `search_path` to the tenant schema.  Cross-tenant reads are structurally impossible.
3. **Financial data**: Ledger entries, orders, invoices are all in the tenant schema. The finance endpoints enforce isolation via the same `get_tenant_db_session` dependency as every other endpoint.

---

## 6. Summary of Error Codes (Registry)

| Code | HTTP | Module | Description |
|---|---|---|---|
| `INVALID_ORDER_ID` | 400 | Orders, Payments | UUID parse failure |
| `MISSING_IDEMPOTENCY_KEY` | 400 | Payments | Transfer payment without key |
| `ORDER_NOT_FOUND` | 404 | Orders, Finance | Order ID does not exist |
| `SKU_NOT_FOUND` | 404 | Inventory | SKU code does not exist |
| `INVENTORY_SHORTAGE` | 409 | Inventory | Insufficient available stock |
| `IDEMPOTENCY_CONFLICT` | 409 | Payments, Middleware | Key reused with different payload |
| `STALE_VERSION` | 409 | Inventory | Optimistic lock version mismatch |
| `INVALID_STATE_TRANSITION` | 422 | Orders | State machine rejects transition |
| `BINDINGNOTFOUND` | 403 | Payments | Retailer not bound to wholesaler |
| `TENANT_CONTEXT_MISSING` | 500 | Auth middleware | JWT tenant claim missing (security bug) |
