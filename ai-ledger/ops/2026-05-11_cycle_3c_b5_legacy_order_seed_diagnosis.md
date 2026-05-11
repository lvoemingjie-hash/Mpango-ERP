# Cycle 3C — B5 Legacy Real-DB ORDER_NOT_FOUND Diagnosis

**Date:** 2026-05-11
**Author:** CodeBuddy (Product AI)
**Branch:** `ops/integration-rehearsal-clean-2026-05-08`
**Status:** COMPLETE — diagnosis only, awaiting CTO decision

---

## 1. Environment

```
HEAD: 2666386a fix(payments): align bootstrapped tenant schema contract
Branch: ops/integration-rehearsal-clean-2026-05-08
Alembic head: 021_tenant_payments_retailer_id_transaction_id (head)
git status --short: ?? resolve_conflict.py
```

No uncommitted code changes. Working tree clean except `resolve_conflict.py` (untracked, per constraint).

---

## 2. B5 Test File Analysis

**File:** `backend/tests/test_b5_real_db.py`

### 2.1 Hardcoded IDs

| ID | Value | Purpose |
|----|-------|---------|
| `ORDER_ID` | `550e8400-e29b-41d4-a716-446655440002` | Payment target order |
| `BINDING_ID` | `550e8400-e29b-41d4-a716-446655440004` | Wholesaler-retailer binding for balance check |

Both are module-level constants, never dynamically created.

### 2.2 Real Dependencies

| Dependency | Type | Present? |
|------------|------|----------|
| Docker CLI | `shutil.which("docker")` — skip guard | YES |
| Docker Compose postgres | `docker compose exec postgres psql ...` for balance/count queries | YES |
| `t_dev.orders` row with `ORDER_ID` | DB data | **NO** |
| `public.wholesaler_retailer_bindings` row with `BINDING_ID` | DB data | **NO** |
| `t_dev.payments` table (with correct schema) | Schema (Cycle 3B fixed) | YES |
| FastAPI TestClient | Runtime dependency | YES |
| `MPANGO_ENV=test` | Env var for MockAuthStrategy | YES |

### 2.3 Test Architecture

- Uses `unittest.TestCase` (not pytest)
- `setUpClass` creates `TestClient(app)` and runs `DELETE FROM t_dev.payments` + resets binding balance via `docker compose exec postgres psql`
- Each test calls `/api/v1/payments` with hardcoded `ORDER_ID`
- Balance verification via `docker compose exec postgres psql` (subprocess)
- Payment count verification via `docker compose exec postgres psql` (subprocess)
- Tests are **sequential by design**: test_transfer → test_replay → test_violation depend on prior state

---

## 3. B5 Four Tests — Individual Results

### 3.1 `test_cash_payment`

| Field | Value |
|-------|-------|
| **Status** | FAILED |
| **HTTP** | `404` |
| **Error** | `AssertionError: 404 != 201` |
| **API Response** | `ORDER_NOT_FOUND: Order with ID '550e8400-e29b-41d4-a716-446655440002' not found` |
| **Balance before** | `None` (BINDING_ID not in DB) |
| **Payments count before** | `None` (docker query returned no result) |
| **Classification** | **Hardcoded seed missing** |

### 3.2 `test_transfer_payment_first`

| Field | Value |
|-------|-------|
| **Status** | FAILED |
| **HTTP** | `404` |
| **Error** | `AssertionError: 404 != 201` |
| **API Response** | `ORDER_NOT_FOUND: Order with ID '550e8400-e29b-41d4-a716-446655440002' not found` |
| **Classification** | **Hardcoded seed missing** |

### 3.3 `test_idempotent_replay`

| Field | Value |
|-------|-------|
| **Status** | FAILED |
| **HTTP** | `404` |
| **Error** | `AssertionError: 404 != 201` |
| **API Response** | `ORDER_NOT_FOUND: Order with ID '550e8400-e29b-41d4-a716-446655440002' not found` |
| **Classification** | **Hardcoded seed missing** |

### 3.4 `test_idempotency_violation`

| Field | Value |
|-------|-------|
| **Status** | FAILED |
| **HTTP** | `404` |
| **Error** | `AssertionError: 404 != 409` |
| **API Response** | `ORDER_NOT_FOUND: Order with ID '550e8400-e29b-41d4-a716-446655440002' not found` |
| **Classification** | **Hardcoded seed missing** |

### 3.5 Suite Run (all 4 together)

| Field | Value |
|-------|-------|
| **Total** | 4 failed, 0 passed |
| **Test 1** | `test_cash_payment`: `404 != 201` (ORDER_NOT_FOUND) |
| **Test 2** | `test_transfer_payment_first`: `404 != 201` (ORDER_NOT_FOUND) |
| **Test 3** | `test_idempotent_replay`: `404 != 201` (ORDER_NOT_FOUND) |
| **Test 4** | `test_idempotency_violation`: `404 != 409` (ORDER_NOT_FOUND) |

When run as suite, test 4 also shows idempotency middleware 409 in the batch run due to key `tx-001` leaking from test 2, but individually it's also `ORDER_NOT_FOUND` (404).

---

## 4. ORDER_ID / BINDING_ID Query Evidence

### 4.1 Hardcoded ORDER_ID

```sql
SELECT id, status, total_amount, retailer_id, wholesaler_id
FROM t_dev.orders WHERE id='550e8400-e29b-41d4-a716-446655440002';
```

**Result:** (empty) — ORDER_ID does NOT exist in `t_dev.orders`.

### 4.2 Hardcoded BINDING_ID

```sql
SELECT id, outstanding_balance
FROM public.wholesaler_retailer_bindings
WHERE id='550e8400-e29b-41d4-a716-446655440004';
```

**Result:** (empty) — BINDING_ID does NOT exist in `public.wholesaler_retailer_bindings`.

### 4.3 Available Data

```sql
SELECT COUNT(*) FROM t_dev.orders;
-- Result: 0

SELECT COUNT(*) FROM public.wholesaler_retailer_bindings;
-- Result: 8 (all with outstanding_balance = 0.00)

SELECT COUNT(*) FROM t_dev.payments;
-- Result: 0
```

**t_dev has zero orders, zero payments, and 8 bindings (all with 0 balance).** No data exists to support the B5 hardcoded IDs.

### 4.4 Sample Bindings Available

| Binding ID | Wholesaler ID | Retailer ID | Balance |
|------------|--------------|-------------|---------|
| `95768dc7-...` | `bd76c5a6-...` | `223dc9ce-...` | 0.00 |
| `e9b6eca5-...` | `e266bf91-...` | `38a9ecef-...` | 0.00 |
| `e24a07c6-...` | `f3a620ec-...` | `fd1c7250-...` | 0.00 |
| `9345c8c1-...` | `524a7737-...` | `6a5f6a7d-...` | 0.00 |
| `9e73048b-...` | `8d5bf28c-...` | `1665a6e4-...` | 0.00 |

These bindings exist but have no associated orders in `t_dev.orders`.

---

## 5. B5 vs. Current Payment Semantics

### 5.1 UndefinedColumnError Status

**ELIMINATED in Cycle 3B.** All 4 B5 tests now fail with `ORDER_NOT_FOUND` (404), not `UndefinedColumnError`. The schema-contract fix is confirmed effective.

### 5.2 Current Payment Flow (Phase 5/6)

The current payment API at `POST /api/v1/payments` expects:

1. **Order lookup** by `order_id` → must exist in tenant schema
2. **Binding lookup** (wholesaler-retailer relationship) → derived from order
3. **Payment creation** with `retailer_id`, `transaction_id`, etc.
4. **Idempotency** via `X-Idempotency-Key` header

The B5 test's payment semantics (cash/transfer payment, balance reduction, idempotency) **align with current API contract**. The test is not semantically obsolete — it just lacks seed data.

### 5.3 Conflicts

| Aspect | B5 Test | Current Product | Conflict? |
|--------|---------|------------------|-----------|
| Payment endpoint | `POST /api/v1/payments` | Same | NO |
| Order lookup | Required | Required | NO |
| `retailer_id` column | Now present (3B fix) | Expected | **RESOLVED** |
| `transaction_id` column | Now present (3B fix) | Expected | **RESOLVED** |
| Idempotency key | `X-Idempotency-Key` header | Same | NO |
| Binding balance | `public.wholesaler_retailer_bindings` | Same | NO |
| Seed data | Hardcoded UUIDs | Not present | **YES** |

**No semantic conflict.** B5 tests are architecturally sound but data-dependent.

---

## 6. Is There a Real Product Defect?

**NO.** The payment product code is working correctly:

- It correctly returns 404 for a non-existent order
- It correctly validates retailer_id/transaction_id (columns now present)
- Mainline tests (67 passed) confirm correct behavior with mocked data
- The B5 failure is purely a **test data** issue, not a product defect

---

## 7. Recommendation

### Primary Recommendation: **B — Mark B5 as legacy/xfail, promote on Phase 5/6 + schema-contract guard**

### 7.1 Rationale

| Factor | Assessment |
|--------|-----------|
| Product defect? | No — payment API works correctly |
| Schema defect? | No — Cycle 3B resolved `UndefinedColumnError` |
| Test data issue? | Yes — hardcoded ORDER_ID/BINDING_ID never seeded |
| Rewrite feasible? | Yes, but requires real-DB fixture infrastructure (orders API + bindings) |
| Rewrite risk | Medium — B5 uses `unittest.TestCase` + subprocess docker calls; rewrite to pytest + async fixtures is significant |
| Rewrite effort | ~1-2 days for proper dynamic fixture |
| Promotion gate? | Phase 5/6 (67 tests) + schema-contract guard (14 tests) = **81 tests** already cover payment behavior |

### 7.2 Why Not A (Rewrite B5)?

- B5 tests duplicate what Phase 5/6 already cover with mocked DB
- The only unique value of B5 is **real-DB end-to-end** verification
- Creating a real-DB fixture requires: (1) order creation via API, (2) binding setup, (3) balance seeding, (4) test isolation — significant infrastructure
- Current Docker DB has no orders table data at all — seed scripts would also need updating
- CTO preference: "不要为了旧硬编码 seed 修生产代码"

### 7.3 Why Not C (补 seed)?

- Hardcoded UUIDs (`550e8400-...`) are synthetic test IDs that must exist in both `t_dev.orders` AND `public.wholesaler_retailer_bindings`
- Requires adding seed SQL that creates an order, binding, wholesaler, and retailer — all cross-referenced
- Seed data is fragile: any schema change breaks it silently
- Violates "不允许为了让 B5 全绿而补历史硬编码 seed" (from Cycle 3B constraints)

### 7.4 Why Not D (产品代码修复)?

- No product defect exists
- All 67 mainline tests pass
- `ORDER_NOT_FOUND` is correct behavior for a non-existent order

### 7.5 Recommended Implementation (for CTO approval in a future cycle)

```python
# Add to test_b5_real_db.py class-level decorator or pytest.mark:
@pytest.mark.skip(reason="Legacy B5: requires real-DB seed data (ORDER_ID/BINDING_ID). "
                          "Superseded by Phase 5/6 tests + schema-contract guard. "
                          "See Cycle 3C ledger for full diagnosis.")
class TestB5RealDB(unittest.TestCase):
    ...
```

Or if finer control is desired, mark as `@pytest.mark.xfail(reason="...", strict=True)`.

### 7.6 Impact on Promotion

| Gate | Status | Tests |
|------|--------|-------|
| Phase 5/6 payment tests | **PASS** | 53 passed, 1 xfailed |
| Schema-contract guard | **PASS** | 14 passed |
| Payment API tests | **PASS** | 7 passed |
| **Total promotion gate** | **GREEN** | **74 passed** (67 mainline + 7 schema-contract static-only = 74 if live skipped; 81 total if live passes) |
| B5 real-DB tests | **xfail/skip** | 4 tests — not in promotion gate |

---

## 8. Summary

| Question | Answer |
|----------|--------|
| UndefinedColumnError still present? | **No** — eliminated in Cycle 3B |
| Real product defect? | **No** — ORDER_NOT_FOUND is correct for missing data |
| B5 semantically obsolete? | **No** — payment semantics align with current API |
| Root cause of all 4 failures? | **Hardcoded ORDER_ID/BINDING_ID not in DB** |
| Mainline tests green? | **Yes** — 67 passed, 1 xfailed |
| Recommendation | **B: legacy/xfail B5, promote on Phase 5/6 + schema-contract guard** |
