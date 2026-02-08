# S6-1: Read Models Implementation — Ops Ledger

**Track**: S6-1 (Read Models Implementation)
**Date**: 2026-02-07
**Status**: ✅ COMPLETE
**Author**: Backend AI
**Depends On**: S6-P (BI Foundation & Constraints) — 🔒 FROZEN

---

## 1. Objective

Implement the first layer of Financial Read Models (SQL Views) following the
strict constraints defined in S6-P. These views serve as the data "API" for
Dashboards.

---

## 2. S6-P Addendum Recorded

Appended the **"Shallow Join" Rule** to `ai-ledger/backend/s6-p_bi_foundation.md` §7:

> **Rule**: BI Views (`rpt_*`) MUST NOT directly JOIN non-reporting tables
> with a depth greater than **1 level**.
>
> - Depth 0: Single table with filters → ✅ Allowed
> - Depth 1: Source table + 1 dimension table → ✅ Allowed
> - Depth 2+: Multi-hop joins → ❌ Forbidden (use Materialized Views)

---

## 3. Views Implemented

### A. `rpt_sales_daily` — Revenue Trends

| Property | Value |
|----------|-------|
| Source | `ledger_entries` |
| Filter | `account_type = 'revenue' AND is_deleted = false` |
| Grain | One row per calendar day |
| Join Depth | 0 |

**Columns**:

| Column | Type | Description |
|--------|------|-------------|
| `transaction_date` | `DATE` | Accounting date (S6-P time axis) |
| `reporting_currency_code` | `CHAR(3)` | Hardcoded `'USD'` |
| `daily_revenue` | `NUMERIC(20,4)` | `ABS(SUM(amount))` — Revenue stored negative, displayed positive |
| `transaction_count` | `INTEGER` | Number of revenue entries |

**SQL**:
```sql
SELECT
    transaction_date::DATE AS transaction_date,
    'USD'::CHAR(3) AS reporting_currency_code,
    ABS(SUM(amount))::NUMERIC(20, 4) AS daily_revenue,
    COUNT(*) AS transaction_count
FROM ledger_entries
WHERE account_type = 'revenue' AND is_deleted = false
GROUP BY transaction_date::DATE
ORDER BY transaction_date::DATE;
```

---

### B. `rpt_receivables_summary` — AR Snapshot

| Property | Value |
|----------|-------|
| Source | `ledger_entries` |
| Filter | `account_type = 'receivable' AND is_deleted = false` |
| Grain | One row per (entity_id, entity_type) |
| Join Depth | 0 |

**Columns**:

| Column | Type | Description |
|--------|------|-------------|
| `entity_id` | `UUID` | Reference ID (customer/order UUID) |
| `entity_type` | `VARCHAR(50)` | Reference type (`'order'`, `'payment'`) |
| `reporting_currency_code` | `CHAR(3)` | Hardcoded `'USD'` |
| `outstanding_balance` | `NUMERIC(20,4)` | `SUM(amount)` — positive = customer owes us |
| `entry_count` | `INTEGER` | Number of receivable entries |
| `earliest_transaction` | `TIMESTAMPTZ` | First transaction date |
| `latest_transaction` | `TIMESTAMPTZ` | Most recent transaction date |

**SQL**:
```sql
SELECT
    reference_id AS entity_id,
    reference_type AS entity_type,
    'USD'::CHAR(3) AS reporting_currency_code,
    SUM(amount)::NUMERIC(20, 4) AS outstanding_balance,
    COUNT(*) AS entry_count,
    MIN(transaction_date) AS earliest_transaction,
    MAX(transaction_date) AS latest_transaction
FROM ledger_entries
WHERE account_type = 'receivable' AND is_deleted = false
GROUP BY reference_id, reference_type
ORDER BY outstanding_balance DESC;
```

---

### C. `rpt_cash_flow_daily` — Cash Position

| Property | Value |
|----------|-------|
| Source | `ledger_entries` |
| Filter | `account_type = 'cash' AND is_deleted = false` |
| Grain | One row per calendar day |
| Join Depth | 0 |

**Columns**:

| Column | Type | Description |
|--------|------|-------------|
| `transaction_date` | `DATE` | Accounting date (S6-P time axis) |
| `reporting_currency_code` | `CHAR(3)` | Hardcoded `'USD'` |
| `net_change` | `NUMERIC(20,4)` | `SUM(amount)` — positive = inflow, negative = outflow |
| `transaction_count` | `INTEGER` | Number of cash entries |
| `running_balance` | `NUMERIC(20,4)` | `SUM(SUM(amount)) OVER (ORDER BY date)` — cumulative |

**SQL**:
```sql
SELECT
    transaction_date::DATE AS transaction_date,
    'USD'::CHAR(3) AS reporting_currency_code,
    SUM(amount)::NUMERIC(20, 4) AS net_change,
    COUNT(*) AS transaction_count,
    SUM(SUM(amount)) OVER (
        ORDER BY transaction_date::DATE
    )::NUMERIC(20, 4) AS running_balance
FROM ledger_entries
WHERE account_type = 'cash' AND is_deleted = false
GROUP BY transaction_date::DATE
ORDER BY transaction_date::DATE;
```

---

## 4. S6-P Compliance Matrix

| Constraint | rpt_sales_daily | rpt_receivables_summary | rpt_cash_flow_daily |
|------------|:-:|:-:|:-:|
| `rpt_` prefix | ✅ | ✅ | ✅ |
| Tenant schema | ✅ | ✅ | ✅ |
| `reporting_currency_code` | ✅ `'USD'` | ✅ `'USD'` | ✅ `'USD'` |
| `transaction_date` time axis | ✅ | ✅ (via min/max) | ✅ |
| No `created_at` | ✅ | ✅ | ✅ |
| `NUMERIC(20,4)` money | ✅ | ✅ | ✅ |
| Shallow Join ≤ 1 | ✅ Depth 0 | ✅ Depth 0 | ✅ Depth 0 |
| `reporting_role` SELECT | ✅ Granted | ✅ Granted | ✅ Granted |

---

## 5. Migration Details

| Field | Value |
|-------|-------|
| Migration ID | `012_s6_1_read_models` |
| Revises | `011_s6_p_reporting_role` |
| Schemas affected | 6 tenant schemas |
| Objects created | 3 views × 6 schemas = **18 views** |
| Grants issued | `SELECT` on all views to `reporting_role` |

### Schemas Migrated

```
✅ t_550e8400e29b41d4a716446655440000
✅ t_7465a81cc3f94fb3b0e6674cbc22c829
✅ t_b6_verify
✅ t_dev
✅ t_f32148fea3b74353b1c9bb095a1a0e58
✅ t_test
```

---

## 6. Verification Results

### View Existence

```
✅ t_test.rpt_sales_daily         — EXISTS
✅ t_test.rpt_receivables_summary — EXISTS
✅ t_test.rpt_cash_flow_daily     — EXISTS
```

### Reporting User Access

```
✅ rpt_sales_daily:         SELECT OK (rows=0)
✅ rpt_receivables_summary: SELECT OK (rows=4)
✅ rpt_cash_flow_daily:     SELECT OK (rows=0)
```

### Live Data Sample (rpt_receivables_summary)

```
entity_id=183391f5-..., entity_type=order, outstanding_balance=100.0000, currency=USD
entity_id=363c19fc-..., entity_type=order, outstanding_balance=100.0000, currency=USD
entity_id=67eb9360-..., entity_type=order, outstanding_balance=100.0000, currency=USD
```

---

## 7. Files Changed

| File | Change |
|------|--------|
| `backend/alembic/versions/012_s6_1_read_models.py` | Migration: 3 SQL views in all tenant schemas |
| `backend/models/reporting.py` | SQLAlchemy read-only ORM mappings for views |
| `backend/models/__init__.py` | Added reporting model exports |
| `ai-ledger/backend/s6-p_bi_foundation.md` | Appended §7 Shallow Join Rule + §8 Read Models Registry |
| `backend/scripts/s6_1_verify_views.py` | Verification script |
| `ai-ledger/backend/s6-1_read_models.md` | This ledger |

---

## 8. Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   REPORTING LAYER (S6-1)                  │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ledger_entries (source, immutable)                       │
│       │                                                  │
│       ├── WHERE account_type = 'revenue'                 │
│       │   └── rpt_sales_daily                            │
│       │       └── ABS(SUM(amount)) by date               │
│       │                                                  │
│       ├── WHERE account_type = 'receivable'              │
│       │   └── rpt_receivables_summary                    │
│       │       └── SUM(amount) by entity                  │
│       │                                                  │
│       └── WHERE account_type = 'cash'                    │
│           └── rpt_cash_flow_daily                        │
│               └── SUM(amount) by date + running balance  │
│                                                          │
│  Access: reporting_user (SELECT only, 30s timeout)       │
│  Currency: 'USD'::CHAR(3) on every view                  │
│  Time Axis: transaction_date (never created_at)          │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

**Document Author**: Backend AI
**Track**: S6-1 — Read Models Implementation
**Status**: ✅ COMPLETE
**Last Updated**: 2026-02-07
