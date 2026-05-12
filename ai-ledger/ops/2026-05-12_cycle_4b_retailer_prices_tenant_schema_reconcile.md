# Cycle 4B — Retailer Prices Tenant Schema Reconcile

**Date:** 2026-05-12
**Branch:** `ops/integration-rehearsal-clean-2026-05-08`
**Worktree:** `product-dev-recovered-review`
**Status:** FIX_READY_FOR_CTO_REVIEW
**Author:** AI (Cycle 4B Final Polish)
**Promotion:** Paused — pending commit + push + Lubuntu Stage 4D

---

## 1. Problem Statement

Migration `017_retailer_prices` creates the `retailer_prices` table in tenant schemas.
Tenants bootstrapped **after** migration 017 ran (e.g. `t_dev` via `bootstrap_tenant_schema.py`)
miss this table entirely. Bootstrap had no `retailer_prices` in its `tables` list and no
reconcile function — unlike `payments` (Cycle 4A) and `reporting` views/matviews (Cycle 4A).

**Confirmed:** `t_dev` has **zero** `retailer_prices` table.

---

## 2. Root Cause Analysis

Same architectural gap as Cycle 4A:

1. Alembic migration 017 runs once, discovers tenant schemas dynamically at runtime.
2. Tenants created by `bootstrap_tenant_schema.py` **after** 017 executed miss the table.
3. `CREATE TABLE IF NOT EXISTS` in bootstrap is a no-op for existing tables with different columns,
   but for **missing** tables it creates them correctly.
4. Indexes (`ix_retailer_prices_retailer_id`, `ix_retailer_prices_sku_id`) are created by
   `op.create_index()` in the migration — not part of `CREATE TABLE` — so bootstrap needs
   explicit index reconciliation.

---

## 3. Audit Nullability Drift Diagnosis

| Field | `AuditMixin` (ORM) | Migration 017 | Bootstrap legacy tables |
|-------|--------------------|---------------|------------------------|
| `created_at` | `nullable=False` | `nullable=False` | nullable (no `NOT NULL`) |
| `updated_at` | `nullable=False` | `nullable=False` | nullable (no `NOT NULL`) |
| `is_deleted` | `nullable=False` | `nullable=False` | nullable (no `NOT NULL`) |

**Finding:** ORM and migration 017 are aligned — audit fields are `NOT NULL`.
Bootstrap's legacy tables (users, skus, orders, etc.) have nullable audit fields,
which is a pre-existing inconsistency predating Cycle 4B.

**Decision:** The new `retailer_prices` DDL matches migration 017 contract (`NOT NULL` on
`created_at`, `updated_at`, `is_deleted`). Fixing existing tables' nullable audit fields
is a separate concern requiring `ALTER TABLE` + data validation — out of scope for Cycle 4B.

---

## 4. Code Changes

### 4.1 `backend/scripts/bootstrap_tenant_schema.py`

#### Added to `tables` list (new tenants):
```python
f'CREATE TABLE IF NOT EXISTS "{ts}".retailer_prices ('
"id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
"retailer_id UUID NOT NULL,"
"sku_id UUID NOT NULL,"
"price NUMERIC(12,2) NOT NULL,"
"created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
"updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
"is_deleted BOOLEAN NOT NULL DEFAULT false,"
"deleted_at TIMESTAMPTZ,"
"created_by UUID, updated_by UUID,"
"CONSTRAINT uq_retailer_prices_retailer_sku UNIQUE (retailer_id, sku_id),"
"CONSTRAINT ck_retailer_prices_positive_price CHECK (price > 0))",
```

#### Rewritten function `_reconcile_retailer_prices(db, ts)` (Cycle 4B Revision):
Two-phase approach:

**Phase 1** — if table does not exist: return (CREATE TABLE IF NOT EXISTS handles it).

**Phase 2** — if table exists: full structural contract validation against migration 017.
Checks all of the following; any violation triggers `RuntimeError` with precise details:
- `retailer_id` exists and NOT NULL
- `sku_id` exists and NOT NULL
- `price` exists and NOT NULL
- `created_at` exists and NOT NULL
- `updated_at` exists and NOT NULL
- `is_deleted` exists and NOT NULL
- `uq_retailer_prices_retailer_sku` unique constraint (or equivalent unique index) exists
- `ck_retailer_prices_positive_price` check constraint exists
- `ix_retailer_prices_retailer_id` index created/validated via `_ensure_index()`
- `ix_retailer_prices_sku_id` index created/validated via `_ensure_index()`

#### Called from `bootstrap()`:
```python
# --- retailer_prices: structural validation + index reconcile (mirrors 017) ---
await _reconcile_retailer_prices(db, ts)
```

### 4.2 `backend/tests/test_payments_schema_contract.py`

Added 13 static DDL test methods in `TestRetailerPricesDDLContract` (unchanged from Cycle 4B).

Added 13 live DB contract guard tests in `TestLiveRetailerPricesContract` (new in Cycle 4B Revision):

| Test | What it verifies |
|------|-----------------|
| `test_live_has_retailer_id` | Column exists in t_dev |
| `test_live_retailer_id_not_null` | `NOT NULL` on t_dev |
| `test_live_has_sku_id` | Column exists in t_dev |
| `test_live_sku_id_not_null` | `NOT NULL` on t_dev |
| `test_live_has_price` | Column exists in t_dev |
| `test_live_price_not_null` | `NOT NULL` on t_dev |
| `test_live_created_at_not_null` | Audit NOT NULL on t_dev |
| `test_live_updated_at_not_null` | Audit NOT NULL on t_dev |
| `test_live_is_deleted_not_null` | Audit NOT NULL on t_dev |
| `test_live_has_unique_constraint` | `uq_retailer_prices_retailer_sku` on t_dev |
| `test_live_has_check_constraint` | `ck_retailer_prices_positive_price` on t_dev |
| `test_live_has_retailer_id_index` | `ix_retailer_prices_retailer_id` on t_dev |
| `test_live_has_sku_id_index` | `ix_retailer_prices_sku_id` on t_dev |

Live tests are skipped only when the database server is completely unreachable.
If the DB is reachable but `t_dev.retailer_prices` is missing, tests FAIL rather than skip —
the missing table is exactly the schema drift they are designed to catch.

**Skip-condition bug fix (Cycle 4B Final Correction):**
The previous version used `_can_connect_t_dev_retailer_prices()` which returned `False`
(skip) when the database was reachable but the `retailer_prices` table did not exist.
This defeated the purpose of the live guard — it skipped precisely when it should have failed.
Replaced with `_can_connect_db()` that checks only DB server reachability via `SELECT 1`.
Now, when DB is reachable but the table is missing, fixtures return empty dicts and
assertions like `assert "retailer_id" in rp_columns` will fail with a clear error.

**`_table_exists()` helper (Cycle 4B Final Correction):**
Added a proper `_table_exists(db, schema, table_name)` helper that queries
`information_schema.tables` directly, instead of using `_column_exists(id)` as a
proxy for table existence. The `_reconcile_retailer_prices()` function now uses
this helper for its Phase 1 table-existence check.

**`rp_constraints` fixture fix (Cycle 4B Final Polish):**
The `rp_constraints` fixture used `'t_dev.retailer_prices'::regclass` which throws
`UndefinedTableError` when the table does not exist, causing 2 setup ERRORs instead
of clean assertion failures. Replaced with `to_regclass('t_dev.retailer_prices')`
which returns NULL on missing tables, so the query returns an empty result set and
the fixture returns `{}`. Now constraint tests fail via assertion (`"uq_retailer_prices_retailer_sku" not in {}`) rather than unhandled error.

---

## 5. Test Results (Current State)

**Context:** The Windows Docker DB is reachable and `t_dev` schema exists, but
`t_dev.retailer_prices` has not yet been created (the updated `bootstrap_tenant_schema.py`
has not been committed, pushed, or deployed). Live guard tests correctly detect this drift.

```
test_payments_schema_contract.py
  Static DDL tests:  21 passed (8 payments + 13 retailer_prices)
  Live payments:      6 passed (t_dev.payments contract valid)
  Live retailer_prices: 13 FAILED (t_dev.retailer_prices missing - CORRECT)
  Total: 27 passed, 13 failed, 0 errors

test_phase3_pricing.py             16 passed
test_phase4_pricing_safe_orders.py 18 passed
test_payments_api.py                5 passed
test_payment_atomicity.py           2 passed
test_phase5_order_payment.py       53 passed, 1 xfailed
```

All 13 live retailer_prices failures are in `TestLiveRetailerPricesContract` and are
caused by `t_dev.retailer_prices` not existing. After commit + push + Docker rebuild +
Lubuntu Stage 4D (which runs updated `bootstrap_tenant_schema.py`), the table will be
created and all 40 contract tests will pass (27 static + 6 live payments + 13 live
retailer_prices = 40 total, 0 failures).

---

## 6. Schema Contract Alignment Matrix

| Object | Migration 017 | Bootstrap DDL | Reconcile validates | ORM Model |
|--------|:---:|:---:|:---:|:---:|
| `retailer_prices` table | ✅ | ✅ | — | ✅ |
| `retailer_id UUID NOT NULL` | ✅ | ✅ | ✅ | ✅ |
| `sku_id UUID NOT NULL` | ✅ | ✅ | ✅ | ✅ |
| `price NUMERIC(12,2) NOT NULL` | ✅ | ✅ | ✅ | ✅ |
| `uq_retailer_prices_retailer_sku` | ✅ | ✅ | ✅ | ✅ |
| `ck_retailer_prices_positive_price` | ✅ | ✅ | ✅ | ✅ |
| `ix_retailer_prices_retailer_id` | ✅ | — | ✅ (created) | ✅ |
| `ix_retailer_prices_sku_id` | ✅ | — | ✅ (created) | ✅ |
| `created_at NOT NULL` | ✅ | ✅ | ✅ | ✅ |
| `updated_at NOT NULL` | ✅ | ✅ | ✅ | ✅ |
| `is_deleted NOT NULL` | ✅ | ✅ | ✅ | ✅ |

---

## 7. Outstanding Issues

1. **Legacy audit nullable drift**: Existing tables (users, skus, orders, payments, etc.)
   have nullable `created_at`, `updated_at`, `is_deleted` while ORM expects `NOT NULL`.
   Requires dedicated cycle with `ALTER TABLE ... ALTER COLUMN ... SET NOT NULL` +
   data validation for any existing NULL rows.

2. **Blast radius**: `retailer_prices` is part of the order pricing main chain.
   Used by: pricing repository/API, orders, client products, client orders.
   Structural mismatch in any tenant schema would break order creation and pricing lookups.
   The reconcile function's fail-fast approach prevents silent data corruption.

3. **Docker container runs old bootstrap**: Container image doesn't have updated
   `bootstrap_tenant_schema.py`. Cannot verify reconcile against live `t_dev` DB from host.
   Requires commit + push + Docker rebuild + Lubuntu Stage 4D.

---

## 8. Files Modified

| File | Change |
|------|--------|
| `backend/scripts/bootstrap_tenant_schema.py` | +table DDL + `_table_exists()` helper + structural reconcile function + call |
| `backend/tests/test_payments_schema_contract.py` | +13 static DDL tests + 13 live DB contract guard tests, `_can_connect_db()`, `rp_constraints` via `to_regclass()` |
| `ai-ledger/ops/2026-05-12_cycle_4b_retailer_prices_tenant_schema_reconcile.md` | This ledger, updated through 4 iterations |

---

*Cycle 4B Final Polish complete. Static tests pass. Live retailer_prices contract correctly fails until updated bootstrap is deployed. Ready for CTO review.*
