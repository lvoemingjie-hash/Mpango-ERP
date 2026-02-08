# S6-P: BI Foundation & Constraints — Semantic Freeze

**Track**: S6-P (Preflight)
**Date**: 2026-02-07
**Status**: 🔒 FROZEN
**Author**: Backend AI

---

## 1. Reporting Currency Convention (S6-P1)

### Rule

ALL Read Models (views, materialized views, query results) MUST expose a
`reporting_currency_code CHAR(3) NOT NULL DEFAULT 'USD'` column.

### Rationale

Mpango ERP is single-currency today, but the schema must be forward-compatible
with multi-currency. By embedding the column now, every downstream dashboard,
export, and API response carries an explicit currency tag. When multi-currency
lands, the column becomes dynamic instead of hard-coded.

### Implementation

```sql
-- Every rpt_* view must include:
'USD'::CHAR(3) AS reporting_currency_code
```

### System Default

| Parameter | Value |
|-----------|-------|
| `REPORTING_CURRENCY_CODE` | `USD` |
| Column type | `CHAR(3)` |
| Nullable | `NO` |

> **Migration path**: When multi-currency is introduced, replace the hard-coded
> `'USD'` with a join to a `tenant_settings.default_currency` column.

---

## 2. Ledger Semantics (S6-P1)

### 2.1 Natural Sign Convention

The ledger stores amounts using **signed values**:

| Account Type | Storage Sign | Natural Sign (Display) | Example |
|-------------|-------------|----------------------|---------|
| `RECEIVABLE` | **Positive** (+) = Debit | Positive = "Customer owes" | +100.00 |
| `RECEIVABLE` | **Negative** (−) = Credit | Negative = "Customer paid" | −100.00 |
| `REVENUE` | **Negative** (−) = Credit | **Flip sign for display** → Positive = "Revenue earned" | Stored: −100.00 → Display: 100.00 |
| `CASH` | **Positive** (+) = Debit | Positive = "Cash received" | +100.00 |
| `LIABILITY` | **Negative** (−) = Credit | **Flip sign for display** → Positive = "Amount owed" | Stored: −50.00 → Display: 50.00 |

### Display Rule

```
For REVENUE and LIABILITY accounts:
    display_amount = ABS(stored_amount)

For RECEIVABLE and CASH accounts:
    display_amount = stored_amount
```

### Report Mapping

| Report | Source Account | Display Rule |
|--------|--------------|-------------|
| **Sales Report** | `REVENUE` | `ABS(SUM(amount))` → always positive |
| **Receivables Aging** | `RECEIVABLE` | `SUM(amount)` → positive = outstanding |
| **Cash Position** | `CASH` | `SUM(amount)` → positive = available |
| **Liabilities** | `LIABILITY` | `ABS(SUM(amount))` → always positive |

### 2.2 Time Basis

| Field | Purpose | Use In Reports? |
|-------|---------|----------------|
| `transaction_date` | **Accounting date** — when the economic event occurred | ✅ YES — primary time axis |
| `created_at` | **System timestamp** — when the row was inserted | ❌ NO — audit trail only |

**Rule**: All `rpt_*` views and time-series aggregations MUST use
`transaction_date` as the time dimension. `created_at` is for audit/debugging
only and MUST NOT appear in any reporting query's `WHERE` or `GROUP BY` clause.

### 2.3 Double-Entry Invariant

Every transaction MUST satisfy:

```
SUM(amount) = 0  -- across all entries in the same transaction
```

This is enforced at:
- **Application layer**: `LedgerService.post_transaction()` raises `LedgerIntegrityError`
- **Database layer**: `prevent_ledger_modification_trigger` blocks UPDATE/DELETE (S5.5)

---

## 3. Naming Conventions (S6-P3)

### Read Model Naming

| Prefix | Type | Example |
|--------|------|---------|
| `rpt_` | Reporting view / materialized view | `rpt_sales_daily` |
| `rpt_` | Reporting summary | `rpt_receivables_aging` |
| `rpt_` | Dashboard data source | `rpt_cash_position` |

### Rules

1. **All reporting views MUST start with `rpt_`**
2. Views live in the **tenant schema** (same as source tables)
3. Views are **read-only** — no INSERT/UPDATE/DELETE
4. Views MUST include `reporting_currency_code`
5. Views MUST use `transaction_date` as the time axis
6. Column names use `snake_case`
7. Monetary columns use `NUMERIC(20, 4)`

### Forbidden Patterns

| Pattern | Reason |
|---------|--------|
| `v_*` or `vw_*` prefix | Non-standard; use `rpt_` |
| `created_at` in GROUP BY | Use `transaction_date` |
| Missing `reporting_currency_code` | Forward-compatibility requirement |
| `FLOAT` for money | Precision loss; use `NUMERIC(20,4)` |

---

## 4. Database Isolation (S6-P2)

### Reporting Role

```sql
CREATE ROLE reporting_role NOLOGIN;
GRANT CONNECT ON DATABASE mpango_erp TO reporting_role;
GRANT USAGE ON SCHEMA public TO reporting_role;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO reporting_role;
-- + per-tenant: GRANT USAGE/SELECT on each t_* schema
ALTER ROLE reporting_role SET statement_timeout = '30000';  -- 30s
```

### Reporting User

```sql
CREATE USER reporting_user WITH PASSWORD '***' IN ROLE reporting_role;
```

### Connection Separation

The reporting system uses a **dedicated SQLAlchemy engine** (`reporting_session.py`)
that connects as `reporting_user`. This ensures:

- **Read-only**: INSERT/UPDATE/DELETE will fail with permission error
- **Timeout**: Queries exceeding 30s are automatically cancelled
- **Pool isolation**: Reporting queries cannot starve transactional connections

---

## 5. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    MPANGO ERP BACKEND                        │
├──────────────────────┬──────────────────────────────────────┤
│  Transactional Path  │  Reporting Path                      │
│                      │                                      │
│  database/session.py │  database/reporting_session.py       │
│  ├── async_engine    │  ├── reporting_engine                │
│  ├── mpango user     │  ├── reporting_user (read-only)      │
│  ├── full CRUD       │  ├── SELECT only                     │
│  └── no timeout      │  └── 30s statement_timeout           │
│                      │                                      │
│  Models:             │  Views:                              │
│  ├── orders          │  ├── rpt_sales_daily                 │
│  ├── ledger_entries  │  ├── rpt_receivables_aging           │
│  ├── users           │  ├── rpt_cash_position               │
│  └── ...             │  └── rpt_*                           │
│                      │                                      │
│  Currency:           │  Currency:                           │
│  (implicit)          │  reporting_currency_code = 'USD'     │
│                      │                                      │
│  Time:               │  Time:                               │
│  created_at (audit)  │  transaction_date (accounting)       │
└──────────────────────┴──────────────────────────────────────┘
```

---

## 6. Checklist for Future Read Models

Before creating any `rpt_*` view, verify:

- [ ] Name starts with `rpt_`
- [ ] Includes `reporting_currency_code` column (hardcoded `'USD'` for now)
- [ ] Uses `transaction_date` as time axis (NOT `created_at`)
- [ ] Monetary values are `NUMERIC(20,4)`
- [ ] Revenue/Liability amounts use `ABS()` for display
- [ ] Query runs under 30s on expected data volume
- [ ] Accessible via `reporting_role` (SELECT only)

---

## 7. Addendum: The "Shallow Join" Rule (S6-1)

**Added**: 2026-02-07 — S6-1 Read Models Implementation

> **📌 S6-P Constraint Addendum: The "Shallow Join" Rule**
>
> - **Rule**: BI Views (`rpt_*`) MUST NOT directly JOIN non-reporting tables
>   (source tables) with a depth greater than **1 level**.
> - **Allowed**: `rpt_view` → `ledger` JOIN `accounts` (Depth 1)
> - **Forbidden**: `rpt_view` → `ledger` JOIN `orders` JOIN `users` JOIN `regions` (Depth 3+)
> - **Reason**: Prevents "Hidden Complexity" and "Optimizer Collapse". Complex
>   data stitching must happen in the ETL layer (Materialized Views) or
>   Application layer, not inside a basic View.

### Depth Classification

| Depth | Example | Allowed? |
|-------|---------|----------|
| 0 | Single table with filters | ✅ Yes |
| 1 | Source table + 1 dimension table | ✅ Yes |
| 2+ | Multi-hop joins across domains | ❌ No — use Materialized Views |

---

## 8. S6-1 Read Models Registry

| View | Source | Filter | Join Depth | Status |
|------|--------|--------|-----------|--------|
| `rpt_sales_daily` | `ledger_entries` | `account_type = 'revenue'` | 0 | ✅ Implemented |
| `rpt_receivables_summary` | `ledger_entries` | `account_type = 'receivable'` | 0 | ✅ Implemented |
| `rpt_cash_flow_daily` | `ledger_entries` | `account_type = 'cash'` | 0 | ✅ Implemented |

---

**Document Status**: 🔒 FROZEN — Do not modify without CTO approval.
