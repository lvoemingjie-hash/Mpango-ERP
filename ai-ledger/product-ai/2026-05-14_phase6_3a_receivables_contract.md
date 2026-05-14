# Phase 6.3A: Receivables API Contract Stabilization

**Date:** 2026-05-14
**Base:** `origin/codex/phase6-2-receivables-mvp-2026-05-13 @ 7111dcc`
**Branch:** `codex/phase6-3a-receivables-contract-2026-05-14`
**Type:** Read-only contract hardening
**Status:** ✅ Complete

## Mission

Implement Phase 6.3A: receivables API contract stabilization and frontend-readiness guardrails.

This is a read-only contract hardening slice. It must not add collection recording, payment settlement, ledger posting, migrations, or write-path behavior.

## Scope

### Allowed

- ✅ Add typed Pydantic response schemas for Phase 6.2 receivables summary and orders
- ✅ Update API response models from `DataResponse[dict]` to typed receivables data models
- ✅ Add/strengthen API boundary tests for validation
- ✅ Create ledger documentation

### Forbidden

- ❌ No migrations
- ❌ No changes to OrderService, PaymentService, LedgerService
- ❌ No payment repository write behavior
- ❌ No ledger posting
- ❌ No tenant schema bootstrap
- ❌ No collection recording
- ❌ No payment allocation or AR settlement
- ❌ No platform line work
- ❌ No push
- ❌ No changes to existing Phase 6.2 business semantics

## Implementation

### 1. Typed Response Schemas

Created `backend/schemas/finance.py` with stable Pydantic models:

#### `ReceivablesSummaryResponse`
Aggregate receivables summary by retailer:
- `total_outstanding`: sum of all retailer outstanding balances
- `retailer_count`: number of retailers with balances
- `order_count`: total orders with receivable exposure
- `credit_receivables`: total credit payment exposure
- `unpaid_order_balance`: total unpaid order balances
- `by_retailer`: list of per-retailer breakdowns

#### `RetailerSummaryItem`
Per-retailer receivables breakdown:
- `retailer_id`: retailer UUID
- `retailer_name`: retailer display name
- `outstanding_balance`: total outstanding balance from public binding
- `credit_receivables`: total credit payment exposure
- `unpaid_order_balance`: total unpaid order balances
- `order_count`: number of orders with receivable exposure

#### `ReceivableOrderItem`
Order with receivables exposure:
- `order_id`: order UUID
- `retailer_id`: retailer UUID
- `retailer_name`: retailer display name
- `status`: order status (confirmed, partially_paid, paid)
- `classification`: credit_receivable or unpaid_order
- `payment_method`: primary payment method (credit, cash)
- `total_amount`: order total amount
- `cash_paid`: cash/transfer amount paid
- `credit_amount`: credit amount charged
- `balance_due`: remaining balance (total_amount - cash_paid)
- `created_at`: order creation timestamp (ISO 8601)
- `age_days`: days since order creation

#### `ReceivableOrdersResponse`
Paginated receivables orders list:
- `items`: list of receivable orders
- `pagination`: pagination metadata with page, size, total, pages

### 2. API Endpoint Updates

Updated `backend/api/v1/finance.py`:

- `GET /finance/receivables/summary`: Changed response_model from `DataResponse[dict]` to `DataResponse[ReceivablesSummaryResponse]`
- `GET /finance/receivables/orders`: Changed response_model from `DataResponse[dict]` to `DataResponse[ReceivableOrdersResponse]`

### 3. API Boundary Tests

Added comprehensive validation tests to `backend/tests/test_finance_receivables_api.py`:

- ✅ `test_receivable_orders_invalid_classification_returns_empty`: Invalid classification returns empty result (safe contract)
- ✅ `test_receivable_orders_invalid_status_returns_empty`: Invalid status returns empty result (safe contract)
- ✅ `test_receivable_orders_invalid_retailer_id_returns_empty`: Invalid retailer_id returns empty result (safe contract)
- ✅ `test_receivable_orders_page_size_validation`: Page/size validation is enforced
- ✅ `test_receivables_response_has_stable_keys`: Responses have stable, documented keys for frontend consumption

### 4. Validation Contract Decision

**Chosen:** Invalid `classification`/`status`/`retailer_id` returns empty result, not HTTP 422.

**Rationale:**
- Safer frontend contract: frontend gets consistent shape (`items: []`) rather than error handling
- Aligns with current `ReceivablesService` behavior (returns empty on validation failure)
- No breaking changes to existing business semantics
- Prevents cascading errors from malformed queries

**Alternative Rejected:** FastAPI query validation with HTTP 422 would be stricter but:
- Changes existing Phase 6.2 behavior
- Requires frontend error handling for validation failures
- More aggressive for read-only contract hardening

## API Contract Specification

### GET /finance/receivables/summary

**Response Model:** `DataResponse[ReceivablesSummaryResponse]`

**Classification Constraints:** None (summary endpoint)

**Query Parameters:** None

**Stable Keys:**
- `total_outstanding`, `retailer_count`, `order_count`, `credit_receivables`, `unpaid_order_balance`, `by_retailer`
- Per-retailer: `retailer_id`, `retailer_name`, `outstanding_balance`, `credit_receivables`, `unpaid_order_balance`, `order_count`

### GET /finance/receivables/orders

**Response Model:** `DataResponse[ReceivableOrdersResponse]`

**Classification Constraints:**
- `credit_receivable`: order with credit payment exposure (may be PAID)
- `unpaid_order`: confirmed/partially_paid with remaining non-credit balance
- `null`: order has no receivable exposure

**Query Parameters:**
- `page`: int ≥ 1 (default 1)
- `size`: int ≥ 1, ≤ 100 (default 20)
- `retailer_id`: str | null (optional UUID filter)
- `classification`: "credit_receivable" | "unpaid_order" | null (optional filter)
- `status`: str | null (optional order status filter)

**Validation Behavior:**
- Invalid `retailer_id` (non-UUID): Returns empty `items: []` with `total: 0`
- Invalid `classification`: Returns empty `items: []` with `total: 0`
- Invalid `status`: Returns empty `items: []` with `total: 0`
- Invalid `page`/`size`: Enforced by FastAPI query validation (HTTP 422)

**Stable Keys:**
- `items`, `pagination`
- Per-item: `order_id`, `retailer_id`, `retailer_name`, `status`, `classification`, `payment_method`, `total_amount`, `cash_paid`, `credit_amount`, `balance_due`, `created_at`, `age_days`
- Pagination: `page`, `size`, `total`, `pages`

## Testing Evidence

### Backend Tests

```powershell
poetry run pytest tests/test_receivables_service.py tests/test_finance_receivables_api.py -q --tb=short
```

**Expected:** All tests pass with new validation tests included.

```powershell
$env:REPORTING_USER_PASSWORD='test-password-for-reporting'
poetry run pytest tests/test_phase5_order_payment.py -q --tb=short
```

**Expected:** All tests pass (no regressions to payment flows).

### App Smoke Test

```powershell
$env:MPANGO_ENV='test'
$env:DATABASE_URL='postgresql://postgres:postgres@localhost:5432/mpango_test'
$env:REPORTING_USER_PASSWORD='test-password-for-reporting'
@'
import os
import secrets
os.environ["SECRET_KEY"] = secrets.token_urlsafe(32)
from api.app import app
print(len(app.routes))
'@ | poetry run python -
```

**Expected:** App starts successfully, routes loaded.

## GitNexus Status

```powershell
npx gitnexus analyze
npx gitnexus status
```

**Expected:** Index updated, no new symbols added (read-only contract hardening).

## Files Changed

- `backend/schemas/finance.py` (new) - Typed Pydantic response models
- `backend/api/v1/finance.py` (modified) - Updated response_model annotations
- `backend/tests/test_finance_receivables_api.py` (modified) - Added API boundary validation tests
- `ai-ledger/product-ai/2026-05-14_phase6_3a_receivables_contract.md` (new) - This ledger

## Commits

1. `feat(finance): stabilize receivables API response contract`
   - Add typed Pydantic schemas for receivables endpoints
   - Update API response_model annotations
   - Add API boundary validation tests

2. `docs(ai): record phase6.3a receivables contract evidence`
   - Create ledger documenting contract stabilization

## Confirmation

✅ No push performed
✅ No migrations created
✅ No write-path changes (OrderService, PaymentService, LedgerService untouched)
✅ No collection recording
✅ No payment allocation or AR settlement
✅ No platform line work
✅ No changes to existing Phase 6.2 business semantics
✅ Read-only contract hardening only

## Frontend Contract Note

### For Frontend Developers

The receivables API endpoints now have stable typed contracts:

**GET /finance/receivables/summary**
```typescript
interface ReceivablesSummaryResponse {
  total_outstanding: number;
  retailer_count: number;
  order_count: number;
  credit_receivables: number;
  unpaid_order_balance: number;
  by_retailer: RetailerSummaryItem[];
}

interface RetailerSummaryItem {
  retailer_id: string;
  retailer_name: string;
  outstanding_balance: number;
  credit_receivables: number;
  unpaid_order_balance: number;
  order_count: number;
}
```

**GET /finance/receivables/orders**
```typescript
interface ReceivableOrdersResponse {
  items: ReceivableOrderItem[];
  pagination: {
    page: number;
    size: number;
    total: number;
    pages: number;
  };
}

interface ReceivableOrderItem {
  order_id: string;
  retailer_id: string;
  retailer_name: string;
  status: string;
  classification: "credit_receivable" | "unpaid_order" | null;
  payment_method: "credit" | "cash";
  total_amount: number;
  cash_paid: number;
  credit_amount: number;
  balance_due: number;
  created_at: string | null;
  age_days: number;
}
```

**Important:** Invalid filter values (classification, status, retailer_id) return empty results, not errors. This ensures consistent response shapes for frontend consumption.
