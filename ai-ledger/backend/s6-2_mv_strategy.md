# S6-2: Materialized Views & Refresh Policy

**Track**: S6-2 (Materialized Views & Refresh Policy)
**Date**: 2026-02-07
**Status**: ✅ COMPLETE
**Author**: Backend AI
**Depends On**: S6-1 (Read Models) — ✅ COMPLETE

---

## 1. Core Philosophy

> **"Staleness is acceptable; Locking is not."**

We trade real-time accuracy (seconds) for query speed (milliseconds), but we
strictly avoid locking the database during report generation.

---

## 2. Tiering Strategy

| Tier | Staleness | Implementation | Refresh Trigger | Example |
|------|-----------|---------------|----------------|---------|
| **Real-Time** | 0s (Live) | Standard SQL View | N/A — always current | `rpt_receivables_summary`, `rpt_cash_flow_daily` |
| **Near-Real-Time** | 5–15 min | Materialized View + `CONCURRENTLY` | S4 Job Queue (periodic) | `mv_sales_daily` |
| **End-of-Day** | 24 hours | Materialized View (heavy) | S4 Job Queue (scheduled) | `mv_inventory_valuation` (planned) |

### Tier Assignment Rationale

| View | Tier | Why |
|------|------|-----|
| `rpt_receivables_summary` | Real-Time | AR must be accurate for dunning and payment collection |
| `rpt_cash_flow_daily` | Real-Time | Cash position must reflect latest payments |
| `mv_sales_daily` | Near-Real-Time | Revenue trends don't change second-by-second; dashboard can tolerate 5–15 min lag |

---

## 3. Technical Constraints

### 3.1 CONCURRENTLY Requirement

All Materialized Views **MUST** include a `UNIQUE INDEX` to allow:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_sales_daily;
```

Without the unique index, `REFRESH` takes an `ACCESS EXCLUSIVE` lock, blocking
all reads for the duration of the refresh. With `CONCURRENTLY`, the old data
remains readable while the new data is computed.

### 3.2 Advisory Lock

The refresh job uses a PostgreSQL **advisory lock** to prevent double-refresh:

```sql
SELECT pg_try_advisory_lock(hashtext('mv_refresh_<schema>'));
```

If another refresh is already running for the same tenant, the job skips
gracefully instead of queuing up.

### 3.3 Naming Convention

| Type | Prefix | Example |
|------|--------|---------|
| Standard View (Real-Time) | `rpt_` | `rpt_receivables_summary` |
| Materialized View (Near-RT / EOD) | `mv_` | `mv_sales_daily` |

---

## 4. Refresh Policy

### `mv_sales_daily`

| Parameter | Value |
|-----------|-------|
| Refresh interval | Every 15 minutes |
| Refresh method | `CONCURRENTLY` |
| Lock strategy | Advisory lock per tenant |
| Job name | `refresh_materialized_views` |
| Job system | S4 LocalJobQueue |
| Max retries | 3 |
| Timeout | 30s (reporting_role limit) |

### Refresh Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│ S4 Job Queue│────▶│ refresh_mv   │────▶│ For each tenant: │
│ (periodic)  │     │ handler      │     │                  │
└─────────────┘     └──────────────┘     │ 1. Advisory lock │
                                          │ 2. REFRESH CONC. │
                                          │ 3. Log timestamp │
                                          │ 4. Release lock  │
                                          └─────────────────┘
```

---

## 5. Materialized View Registry

| View | Source | Unique Index | Refresh | Status |
|------|--------|-------------|---------|--------|
| `mv_sales_daily` | `ledger_entries` WHERE `revenue` | `(transaction_date, reporting_currency_code)` | 15 min | ✅ Implemented |

---

## 6. Migration Details

| Field | Value |
|-------|-------|
| Migration ID | `013_s6_2_materialize_sales` |
| Revises | `012_s6_1_read_models` |
| Actions | Drop `rpt_sales_daily` view → Create `mv_sales_daily` MATERIALIZED VIEW → Add unique index |

---

## 7. Files

| File | Purpose |
|------|---------|
| `backend/alembic/versions/013_s6_2_materialize_sales.py` | Migration |
| `backend/jobs/reporting_jobs.py` | Refresh job handler |
| `backend/models/reporting.py` | Updated `RptSalesDaily` → `MvSalesDaily` |
| `backend/tests/test_s6_2_materialized_views.py` | Staleness + refresh test |
| `ai-ledger/backend/s6-2_mv_strategy.md` | This document |

---

**Document Status**: ✅ COMPLETE
