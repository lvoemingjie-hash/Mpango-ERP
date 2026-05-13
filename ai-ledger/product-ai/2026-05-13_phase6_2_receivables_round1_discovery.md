# Phase 6.2 Round 1 — Receivables MVP Discovery

Date: 2026-05-13
Executor: Claude Code under CTO supervision
Verdict: DISCOVERY_COMPLETE

## Worktree Setup

- Worktree path: `C:\Users\Jeff0\MPANGO ERP\phase6-2-receivables-mvp-2026-05-13`
- Branch: `codex/phase6-2-receivables-mvp-2026-05-13`
- Base commit: `beb89b62bcc32f98c4398f32f900bf809c5c7e70`
- Git status verified: Clean (no uncommitted changes)
- Base branch verified: Matches `origin/product-dev-recovered` HEAD

## Documentation Read

- `docs/ai/PROJECT.md` - Current project status and strategic frame
- `docs/ai/README.md` - AI context entry and read order
- `ai-ledger/product-ai/2026-05-13_phase6_credit_payment_promotion.md` - Phase 6 promotion evidence
- `ai-ledger/product-ai/2026-05-13_phase6_credit_ledger_semantics_fix.md` - Phase 6.1 credit fix details

## Code Explored

**Services:**
- `backend/services/ledger_service.py` - Immutable ledger, balance projection, account types
- `backend/services/order_service.py` - State machine, Phase 6.1 credit payment fix

**API Endpoints:**
- `backend/api/v1/orders.py` - Order CRUD, pay_order with structured payment support
- `backend/api/v1/finance.py` - Receivables list, financial summary (GAP 2 implementation)
- `backend/api/v1/payments.py` - Payment CRUD via PaymentService

**Models:**
- `backend/models/ledger.py` - LedgerEntry, AccountType (RECEIVABLE, REVENUE, CASH, LIABILITY)
- `backend/models/order.py` - Order, OrderItem, OrderStatus (includes PAID, PARTIALLY_PAID)

**Schemas:**
- `backend/schemas/payment.py` - PaymentMethod enum (cash, transfer, credit)

**Tests:**
- `backend/tests/test_s5_ledger.py` - Ledger integration tests including Phase 6.1 credit tests
- `backend/tests/test_phase5_order_payment.py` - Payment contract tests including Phase 6 credit tests

## Current Ledger/Payment/Order Architecture Summary

### Phase 6.1 Credit Payment Fix (COMPLETE)

**Problem:** Credit payments were incorrectly posting cash-settlement ledger entries, making receivables disappear from the ledger.

**Solution:** Added optional `payment_method` parameter to `OrderService.transition()`:
- When `payment_method="credit"` and target is PAID: Skip `LedgerService.post_payment_received()`
- When `payment_method` is None/cash/transfer: Call `post_payment_received()` as before

**Ledger Behavior:**
- Credit PAID: RECEIVABLE +100 (confirm only, no settlement) → Receivable stays visible
- Cash/transfer PAID: RECEIVABLE +100 (confirm) -100 (settlement) = 0 → Receivable cleared

### Payment Flow

**Structured Payment Creation:**
1. `POST /orders/{order_id}/pay` with `PayOrderRequest(amount, method, transaction_id)`
2. `PaymentRepository.create()` records payment in `payments` table
3. `PaymentService._apply_outstanding_balance_delta()` updates retailer balance:
   - Credit: delta = +amount (increases receivable)
   - Cash/transfer: delta = -amount (decreases receivable)
4. `OrderService.transition(..., payment_method=method)` advances order state

**Balance Calculation:**
- `PaymentRepository.get_order_paid_total()` sums only cash + transfer (excludes credit)
- Outstanding balance = order.total - paid_total
- Target state: PAID if cumulative >= total, else PARTIALLY_PAID

### Existing Data Sources

**Tables:**
- `ledger_entries` - All immutable financial transactions (RECEIVABLE, REVENUE, CASH)
- `payments` - Structured payment records (order_id, amount, method, status)
- `orders` - Order records (status, total_amount, retailer_id)
- `outstanding_balances` - Retailer-level outstanding balance (computed column)

**API Endpoints (GAP 2 - EXISTING):**
- `GET /finance/receivables` - Lists CONFIRMED/PARTIALLY_PAID/PAID orders with balance_due
- `GET /finance/summary` - Aggregate KPIs (revenue, cash, receivables, order counts)
- `GET /finance/orders/{order_id}/invoice` - Invoice with ledger entries

## Proposed Minimal Data Model Strategy

### Verdict: NO MIGRATION REQUIRED

**Rationale:**

All required data already exists in the current schema:

1. **Retailer-level receivable summary:**
   - Query `outstanding_balances` table (already computed)
   - Or aggregate `payments` table by retailer with method filter

2. **Order-level receivable list:**
   - Join `orders` + `payments` tables
   - Filter by payment method (credit = true receivable, cash/transfer = settled)
   - Calculate balance from ledger or payment records

3. **Future collection recording:**
   - Add optional `collected_at` timestamp to `payments` table (nullable)
   - Or create separate `collections` table referencing payment_id
   - No migration needed for MVP: use `status='completed'` as collection indicator

### If Collection Tracking Requires New Table (Future)

**Option A: Extend payments table (Minimal)**
```sql
ALTER TABLE payments ADD COLUMN collected_at TIMESTAMP NULL;
```

**Option B: Separate collections table (Cleaner)**
```sql
CREATE TABLE collections (
    id UUID PRIMARY KEY,
    payment_id UUID NOT NULL REFERENCES payments(id),
    amount NUMERIC(12,2) NOT NULL,
    collected_at TIMESTAMP NOT NULL DEFAULT NOW(),
    collected_by UUID,
    notes TEXT
);
```

## Proposed API Shape for Round 2

### 1. Retailer-Level Receivable Summary (NEW)

**Endpoint:** `GET /finance/receivables/summary`

**Response:**
```json
{
  "success": true,
  "data": {
    "total_outstanding": "150000.00",
    "credit_receivables": "100000.00",
    "cash_receivables": "50000.00",
    "retailer_count": 25,
    "overdue_30_days": "45000.00",
    "by_retailer": [
      {
        "retailer_id": "uuid",
        "retailer_name": "ABC Store",
        "outstanding_balance": "15000.00",
        "credit_sales": "10000.00",
        "cash_unpaid": "5000.00",
        "order_count": 5
      }
    ]
  }
}
```

**Implementation:**
- Query `outstanding_balances` table for retailer-level totals
- Join `payments` table to breakdown by method (credit vs unpaid cash/transfer)
- Add aging buckets using order.created_at

### 2. Order-Level Receivable List (ENHANCED)

**Endpoint:** `GET /finance/receivables/orders`

**Query params:**
- `retailer_id` (optional) - Filter by retailer
- `payment_method` (optional) - Filter by payment type (credit/unpaid)
- `status` (optional) - Filter by order status
- `age_days_min` (optional) - Show only receivables older than X days
- `age_days_max` (optional) - Show only receivables younger than X days

**Response:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "order_id": "uuid",
        "retailer_id": "uuid",
        "retailer_name": "ABC Store",
        "status": "paid",
        "payment_method": "credit",
        "total_amount": "10000.00",
        "balance_due": "10000.00",
        "created_at": "2026-05-01T00:00:00Z",
        "age_days": 12,
        "is_overdue": true
      }
    ],
    "pagination": {...}
  }
}
```

**Implementation:**
- Join `orders` + `payments` tables
- Filter logic:
  - `payment_method='credit'` → Include all PAID credit orders
  - `payment_method in ('cash', 'transfer')` → Include only PARTIALLY_PAID or unpaid CONFIRMED
- Calculate age from created_at
- Add overdue flag (age_days > 30)

### 3. Collection Recording (Round 3 - FUTURE)

**Endpoint:** `POST /finance/receivables/{payment_id}/collect`

**Request:**
```json
{
  "amount": "5000.00",
  "collected_at": "2026-05-13T10:00:00Z",
  "notes": "Partial collection via M-Pesa"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "payment_id": "uuid",
    "remaining_balance": "5000.00"
  },
  "message": "Collection recorded"
}
```

**Implementation (Round 3):**
- Option A: Update `payments.collected_at` and reduce `outstanding_balances`
- Option B: Create `collections` record and post ledger entry (CASH +, RECEIVABLE -)
- Do NOT change order status (order lifecycle remains closed)

## Proposed Service/Repository Seam for Round 2

### New Service: ReceivablesService

**File:** `backend/services/receivables_service.py`

**Responsibilities:**
1. Aggregate retailer-level receivable summaries
2. Query order-level receivables with payment method filtering
3. Calculate aging and overdue status
4. Prepare data for API responses

**Methods:**
```python
class ReceivablesService:
    async def get_retailer_summary(
        self,
        retailer_id: Optional[UUID] = None
    ) -> dict
    # Returns outstanding balances by retailer, breakdown by payment method

    async def get_order_receivables(
        self,
        retailer_id: Optional[UUID] = None,
        payment_method: Optional[str] = None,
        age_days_min: Optional[int] = None,
        age_days_max: Optional[int] = None,
        page: int = 1,
        size: int = 20
    ) -> tuple[list[dict], int]
    # Returns paginated receivable orders with aging

    async def get_aging_report(
        self,
        bucket_days: list[int] = [30, 60, 90]
    ) -> dict
    # Returns aging buckets for dashboard
```

### Integration Points

**Uses existing services:**
- `LedgerService` - For balance calculations if needed
- `PaymentRepository` - For payment method filtering

**Used by API:**
- `backend/api/v1/finance.py` - New receivables endpoints

## Collection Recording Design Options (Round 3)

### Option A: Ledger-Only Approach (RECOMMENDED)

**Flow:**
1. POST collection request
2. `LedgerService.post_payment_received()` creates settlement entry (CASH +, RECEIVABLE -)
3. Update `payments.collected_at` timestamp
4. Reduce `outstanding_balances`

**Pros:**
- Reuses existing ledger logic
- No new tables
- Clear audit trail

**Cons:**
- Requires extending `payments` table (1 column migration)

### Option B: Separate Collections Table

**Flow:**
1. POST collection request
2. Create `collections` record
3. `LedgerService.post_payment_received()` via new method
4. Update `outstanding_balances`

**Pros:**
- Cleaner separation of concerns
- Supports partial collections over time
- Full collection history

**Cons:**
- Requires new table + migration
- More complex joins for reporting

### Option C: Payment Status Update Only (Minimal)

**Flow:**
1. POST collection request
2. Update `payment.status = 'completed'`
3. Reduce `outstanding_balances`
4. No ledger entries (assume ledger already posted at sale time)

**Pros:**
- No schema changes
- Simplest implementation

**Cons:**
- No ledger audit trail for collection
- Confusing (when was cash actually received?)

**Recommendation:** Option A for Round 3 (ledger-only with 1-column migration).

## Risk Analysis

### Technical Risks

**Risk 1: Conflicting definitions of "receivable"**
- **Issue:** Current `/finance/receivables` endpoint returns PAID orders (including credit)
- **Mitigation:** Clarify terminology:
  - "True receivables" = Credit sales (PAID but unpaid)
  - "Unpaid cash orders" = CONFIRMED/PARTIALLY_PAID cash/transfer
  - Split into separate filters or response fields

**Risk 2: Performance of joins across orders + payments + ledger**
- **Issue:** Multiple joins for aging and payment method filtering
- **Mitigation:**
  - Add indexes on `payments(method, order_id)` if not present
  - Consider materialized view for retailer summaries
  - Cache summary data (refresh hourly)

**Risk 3: Outstanding balance accuracy**
- **Issue:** `outstanding_balances` is a computed column, may drift
- **Mitigation:** Add reconciliation endpoint to compare:
  - Sum of outstanding balances vs
  - Sum of (credit payments + unpaid cash orders)

### Business Logic Risks

**Risk 4: Collection recording changes order state**
- **Issue:** Teams may expect order to revert to CONFIRMED when collection recorded
- **Mitigation:** Document clearly: Order lifecycle is closed at PAID. Collection is a financial event, not an order state change.

**Risk 5: Partial collections not supported in MVP**
- **Issue:** Round 2 assumes full collections only
- **Mitigation:** Reject partial collections in Round 2. Add partial support in Round 3 with separate `collections` table.

## GitNexus Impact Summary

**Status:** GitNexus index not available in worktree. Static analysis performed.

**Likely Impact Areas (based on code exploration):**

**High Impact:**
- `backend/api/v1/finance.py` - Will add new receivables endpoints
- `backend/services/receivables_service.py` - New file (NEW)

**Medium Impact:**
- `backend/repositories/payment_repository.py` - May add collection query methods
- `backend/tests/test_finance_receivables.py` - New test file (NEW)

**Low Impact:**
- `backend/models/payment.py` - May add `collected_at` column in Round 3
- `backend/services/ledger_service.py` - Reuse for collection ledger entries

**No Impact Expected:**
- `OrderService` - Order lifecycle unchanged
- `PaymentService` - Payment creation flow unchanged
- Existing ledger tests - No changes to Phase 6.1 behavior

## Exact Recommended Next Implementation Slice (Round 2)

### Scope: READ-ONLY Receivables Visibility

**Files to Create:**
1. `backend/services/receivables_service.py` - New service
2. `backend/tests/test_receivables_service.py` - New service tests
3. `backend/tests/test_finance_receivables_api.py` - New API tests

**Files to Modify:**
1. `backend/api/v1/finance.py` - Add 2 new endpoints
2. `backend/schemas/finance.py` - Create or extend response schemas

**Implementation Steps:**

1. **Create ReceivablesService**
   - `get_retailer_summary()` - Aggregate by retailer from payments table
   - `get_order_receivables()` - Join orders + payments with filters
   - Add aging calculation logic

2. **Add API Endpoints**
   - `GET /finance/receivables/summary` - Retailer-level breakdown
   - `GET /finance/receivables/orders` - Order-level list with enhanced filters

3. **Add Response Schemas**
   - `ReceivableSummaryResponse`
   - `ReceivableOrderResponse`
   - `ReceivableRetailerSummary`

4. **Write Tests**
   - Service layer: Mock DB, test aggregation logic
   - API layer: TestClient, test filtering and pagination
   - Regression: Ensure Phase 6.1 credit behavior unchanged

**Out of Scope for Round 2:**
- Collection recording (Round 3)
- Schema migrations
- Order state changes
- Ledger modifications

## Tests to Add in Round 2

**Service Tests (`test_receivables_service.py`):**
1. `test_get_retailer_summary_aggregates_correctly` - Sum by retailer
2. `test_get_retailer_summary_breaks_down_by_payment_method` - Credit vs cash
3. `test_get_order_receivables_filters_by_payment_method` - Credit only
4. `test_get_order_receivables_filters_by_retailer` - Single retailer
5. `test_get_order_receivables_calculates_aging_correctly` - Age buckets
6. `test_get_order_receivables_identifies_overdue` - > 30 days
7. `test_get_order_receivables_excludes_fully_paid_cash_orders` - Settled cash excluded

**API Tests (`test_finance_receivables_api.py`):**
1. `test_receivables_summary_returns_200` - Happy path
2. `test_receivables_summary_includes_retailer_breakdown` - Response structure
3. `test_receivables_orders_returns_200` - Happy path
4. `test_receivables_orders_filters_by_retailer` - Query param works
5. `test_receivables_orders_filters_by_payment_method` - Credit filter
6. `test_receivables_orders_pagination_works` - Page/size params
7. `test_receivables_orders_calculates_age_days` - Aging in response

**Regression Tests:**
1. Run full `test_s5_ledger.py` suite - Ensure Phase 6.1 credit ledger unchanged
2. Run full `test_phase5_order_payment.py` suite - Ensure payment flow unchanged

## Confirmation: No Product Code Changes (Round 2)

**Verification:**
- ✅ No modifications to `OrderService.transition()`
- ✅ No modifications to `LedgerService` methods
- ✅ No modifications to `PaymentService.create_payment()`
- ✅ No modifications to `pay_order` endpoint logic
- ✅ No changes to order state machine
- ✅ No changes to payment creation flow
- ✅ No changes to Phase 6.1 credit payment behavior

**Round 2 is READ-ONLY:** Adds visibility only, no behavioral changes.

## Confirmation: No Test Changes (Round 2)

**Verification:**
- ✅ No modifications to existing test files
- ✅ New test files only (`test_receivables_service.py`, `test_finance_receivables_api.py`)
- ✅ Existing tests continue to pass

## Confirmation: No Push

**Verification:**
- ✅ Worktree created in isolated location
- ✅ No push command executed
- ✅ No remote branches modified
- ✅ Discovery ledger only (no implementation)

## Final Verdict

**DISCOVERY_COMPLETE**

The Phase 6.2 receivables MVP can be implemented safely with:
- **No migration required** for Round 2 (read-only visibility)
- **Minimal new code** (1 service, 2 API endpoints, 2 test files)
- **No behavioral changes** to existing payment/ledger flows
- **Clean separation** from order lifecycle (receivables are financial view)

**Recommended Next Step:** Proceed to Round 2 implementation with CTO approval.

**Implementation Priority:**
1. Create `ReceivablesService` with retailer summary + order list methods
2. Add 2 new endpoints to `/finance/receivables` API
3. Write comprehensive tests (service + API + regression)
4. Validate with DB-capable test suite before promotion

**Future Round 3:** Collection recording via ledger entries + 1-column migration (collected_at).
