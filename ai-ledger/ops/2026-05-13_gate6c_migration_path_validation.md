# Gate 6C — Migration Path Validation

| Field | Value |
|---|---|
| **Date** | 2026-05-13 |
| **Gate** | 6C — Migration Path Validation |
| **Operator** | Claude (automated) |
| **Predecessors** | Gate 6 (`BLOCKED_BY_ENVIRONMENT`), Gate 6B (`READY_FOR_FINAL_PROMOTION_COMMIT`) |

---

## 1. Branch & Commit Identifiers

| Item | Value |
|---|---|
| Source branch | `origin/ops/integration-rehearsal-clean-2026-05-08` |
| Candidate commit | `803634b` — `fix(tenant): reconcile retailer prices in bootstrapped schemas` |
| Target branch | `origin/product-dev-recovered` (HEAD: `6a92a29`) |
| Worktree branch | `ops/promotion-exec-6b-2026-05-13` (reused from Gate 6B) |
| Worktree path | `C:\Users\Jeff0\MPANGO ERP\promotion-exec-6b-2026-05-13` |

## 2. Methodology

Created a **clean PostgreSQL database** (`mpango_gate6c`) in the existing Docker container and ran the full migration chain from empty → head, with **no `alembic stamp`** used at any point.

### Database preparation

```sql
CREATE DATABASE mpango_gate6c OWNER mpango;
-- Then applied prerequisites from database/init.sql:
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE TABLE IF NOT EXISTS public.alembic_version (
    version_num VARCHAR(128) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
CREATE SCHEMA IF NOT EXISTS "t_dev";
```

### Migration execution

```
DATABASE_URL=postgresql://mpango:MpangoDBV0.1.4@localhost:5432/mpango_gate6c
REPORTING_USER_PASSWORD=ReportingPass_staging_2026
PYTHONIOENCODING=utf-8
alembic upgrade head
```

## 3. Migration Chain Result

### Full chain: 001 → 021 (all 21 migrations)

| Migration | Description | Status |
|---|---|---|
| 001_initial_schema | Public.wholesalers + tenant tables | PASS |
| 002_phase_b2_invitation_binding | Invitations, retailers, bindings | PASS |
| 003_phase_b3_orders_minimal_closed_loop | Orders minimal closed loop | PASS |
| 004_phase_b4_sku_inventory_mvp | Inventory MVP | PASS |
| 005_phase_b5_payments_minimal_loop | Payments minimal loop | PASS |
| 006_phase_b6_payments_idempotency_key | Payments idempotency key | PASS |
| 007_s3_b_index_hygiene | Index hygiene | PASS |
| 008_s4_b_job_persistence | sys_jobs table | PASS |
| 009_s5_b_financial_ledger | Financial ledger | PASS |
| 010_s5_5_ledger_hardening | Ledger immutability | PASS |
| 011_s6_p_reporting_role | Reporting role & isolation | PASS |
| 012_s6_1_read_models | Financial read models (views) | PASS |
| 013_s6_2_materialize_sales | Materialized sales view | PASS |
| 014_s7_3_audit_trail | BI access audit trail | PASS |
| 015_s7_4_sys_reports | sys_reports table | PASS |
| 016_add_returned_status | Add 'returned' to order_status | PASS |
| 017_retailer_prices | Retailer-specific pricing table | PASS |
| 018_platform_p0_lifecycle | Tenant lifecycle + platform_tenants | PASS |
| 019_platform_audit_logs | Platform audit logs | PASS |
| 020_sys_jobs_audit_columns | sys_jobs audit columns | PASS |
| 021_tenant_payments_retailer_id_transaction_id | Tenant payments schema alignment | PASS |

### Alembic verification

```
$ alembic heads
021_tenant_payments_retailer_id_transaction_id (head)

$ alembic current
021_tenant_payments_retailer_id_transaction_id (head)
```

Single linear head confirmed.

## 4. Pre-requisites Discovered

The migration chain requires these prerequisites before `alembic upgrade head`:

| # | Prerequisite | Source | Why |
|---|---|---|---|
| 1 | `init.sql` must run first | `database/init.sql` | Pre-creates `alembic_version` with `VARCHAR(128)` (default is 32, revision IDs exceed 32 chars starting at migration 003) |
| 2 | `PYTHONIOENCODING=utf-8` | Required on Windows | Migration 010 uses Unicode emoji in `print()` which fails with GBK codec |
| 3 | `REPORTING_USER_PASSWORD` env var | Migration 011 raises RuntimeError if unset | Creates reporting_user with this password |

### Impact assessment

These are **pre-existing deployment prerequisites**, not introduced by the promotion candidate (803634b). They apply to the full migration chain from scratch:
- **Docker deployments**: `init.sql` runs automatically via `docker-entrypoint-initdb.d/`. PYTHONIOENCODING and REPORTING_USER_PASSWORD are set in `docker-compose.yml`. No issue.
- **Non-Docker / manual deployments**: `init.sql` must be run manually, and env vars must be set.

## 5. Bootstrap Verification

After migrations completed, ran `bootstrap_tenant_schema.py t_dev` to create the tenant schema:

```
[reconcile] t_dev.payments: ensured ix_payments_order_id
[reconcile] t_dev.payments: ensured uq_payments_transaction_id
[reconcile] t_dev.retailer_prices: contract validated, indexes ensured
[reconcile] t_dev: granted schema USAGE to reporting_role
[reconcile] t_dev: created mv_sales_daily
[reconcile] t_dev: ensured idx_mv_sales_daily_u1
[reconcile] t_dev: ensured reporting_role table privileges
[bootstrap] Tenant schema 't_dev' ready (13 tables, reconciled).
```

## 6. Targeted Tests on Clean DB

### Group 1 — Payments Schema Contract

| Result | Count |
|---|---|
| Passed | 40 |
| Failed | 0 |
| Skipped | 0 |

### Group 2 — Phase 3 + Phase 4 Pricing

| Result | Count |
|---|---|
| Passed | 34 |
| Failed | 0 |
| Skipped | 0 |

### Group 3 — Payments API + Atomicity + Phase 5 Order Payment

| Result | Count |
|---|---|
| Passed | 53 |
| Failed | 0 |
| Xfailed | 1 |

### Total: **127 passed, 1 xfailed, 0 failed**

## 7. Summary

| Check | Result |
|---|---|
| Clean DB created | Yes (`mpango_gate6c`) |
| `alembic stamp` used | **No** |
| All 21 migrations applied from scratch | Yes |
| Alembic head = `021_tenant_payments_retailer_id_transaction_id` | Confirmed (single linear head) |
| Bootstrap reconciliation | Successful |
| Group 1 (schema contract) | 40 passed |
| Group 2 (pricing) | 34 passed |
| Group 3 (payments/order) | 53 passed, 1 xfailed |
| Merge commit created | **No** |
| Push performed | **No** |

## 8. Verdict

```
READY_FOR_FINAL_PROMOTION_COMMIT
```

### Rationale

- **Full migration chain 001→021 runs successfully from scratch** on a clean database.
- **No `alembic stamp` used** — every migration applied via its actual upgrade function.
- **127 of 128 targeted tests pass** against the freshly-migrated database.
- Three pre-existing deployment prerequisites documented (init.sql, PYTHONIOENCODING, REPORTING_USER_PASSWORD) — all satisfied in Docker deployments, none introduced by the promotion candidate.
