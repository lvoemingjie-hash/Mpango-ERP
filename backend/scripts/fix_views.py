#!/usr/bin/env python3
"""
Hotfix: Recreate reporting views and materialized views in tenant schemas.

Root Cause:
  Migrations 012 (rpt_* views) and 013 (mv_sales_daily) only create views in
  tenant schemas that exist at migration time. After a `docker compose down -v`
  + `alembic upgrade head`, the DB has zero tenant schemas, so the views are
  never created. The seed script creates the tenant schema AFTER migrations,
  leaving the schema without reporting views.

This script discovers all tenant schemas and creates the missing views.

Usage:
    PYTHONPATH=/app python /app/scripts/fix_views.py
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from pathlib import Path


def _add_backend_to_path() -> None:
    backend_dir = Path(__file__).resolve().parent.parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))


# ---------------------------------------------------------------------------
# SQL Definitions (from migrations 012 + 013)
# ---------------------------------------------------------------------------

RPT_RECEIVABLES_SUMMARY = """
CREATE OR REPLACE VIEW rpt_receivables_summary AS
SELECT
    reference_id                                    AS entity_id,
    reference_type                                  AS entity_type,
    'USD'::CHAR(3)                                  AS reporting_currency_code,
    SUM(amount)::NUMERIC(20, 4)                     AS outstanding_balance,
    COUNT(*)                                        AS entry_count,
    MIN(transaction_date)                           AS earliest_transaction,
    MAX(transaction_date)                           AS latest_transaction
FROM ledger_entries
WHERE account_type = 'receivable'
  AND is_deleted = false
GROUP BY reference_id, reference_type
ORDER BY outstanding_balance DESC;
"""

RPT_CASH_FLOW_DAILY = """
CREATE OR REPLACE VIEW rpt_cash_flow_daily AS
SELECT
    transaction_date::DATE                          AS transaction_date,
    'USD'::CHAR(3)                                  AS reporting_currency_code,
    SUM(amount)::NUMERIC(20, 4)                     AS net_change,
    COUNT(*)                                        AS transaction_count,
    SUM(SUM(amount)) OVER (
        ORDER BY transaction_date::DATE
    )::NUMERIC(20, 4)                               AS running_balance
FROM ledger_entries
WHERE account_type = 'cash'
  AND is_deleted = false
GROUP BY transaction_date::DATE
ORDER BY transaction_date::DATE;
"""

MV_SALES_DAILY = """
CREATE MATERIALIZED VIEW mv_sales_daily AS
SELECT
    transaction_date::DATE                          AS transaction_date,
    'USD'::CHAR(3)                                  AS reporting_currency_code,
    ABS(SUM(amount))::NUMERIC(20, 4)                AS daily_revenue,
    COUNT(*)::INTEGER                               AS transaction_count
FROM ledger_entries
WHERE account_type = 'revenue'
  AND is_deleted = false
GROUP BY transaction_date::DATE
ORDER BY transaction_date::DATE
WITH DATA;
"""

MV_UNIQUE_INDEX = """
CREATE UNIQUE INDEX idx_mv_sales_daily_u1
ON mv_sales_daily (transaction_date, reporting_currency_code);
"""


async def fix_views() -> None:
    _add_backend_to_path()

    os.environ.setdefault("MPANGO_ENV", "staging")
    _fallback_key = hashlib.sha256(b"mpango-staging-seed-key").hexdigest()
    os.environ.setdefault("SECRET_KEY", _fallback_key)
    os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")

    from sqlalchemy import text
    from database.session import AsyncSessionLocal

    print("\n=== Mpango ERP: Fix Reporting Views ===\n")

    async with AsyncSessionLocal() as db:
        # Discover tenant schemas with ledger_entries
        result = await db.execute(text("""
            SELECT DISTINCT table_schema
            FROM information_schema.tables
            WHERE table_schema LIKE 't_%'
              AND table_name = 'ledger_entries'
            ORDER BY table_schema
        """))
        tenant_schemas = [row[0] for row in result]

        if not tenant_schemas:
            print("  No tenant schemas with ledger_entries found. Nothing to do.")
            return

        print(f"  Found {len(tenant_schemas)} tenant schema(s): {tenant_schemas}\n")

        for schema in tenant_schemas:
            print(f"  Processing schema: {schema}")

            # Set search_path
            await db.execute(text(f'SET LOCAL search_path TO "{schema}", public'))

            # --- Step 1: rpt_receivables_summary (regular view) ---
            await db.execute(text(RPT_RECEIVABLES_SUMMARY))
            print(f"    + rpt_receivables_summary (view)")

            # --- Step 2: rpt_cash_flow_daily (regular view) ---
            await db.execute(text(RPT_CASH_FLOW_DAILY))
            print(f"    + rpt_cash_flow_daily (view)")

            # --- Step 3: mv_sales_daily (materialized view) ---
            # Drop if exists (idempotent)
            await db.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_sales_daily"))
            # Also drop the regular view if it was somehow left behind
            await db.execute(text("DROP VIEW IF EXISTS rpt_sales_daily"))

            await db.execute(text(MV_SALES_DAILY))
            await db.execute(text(MV_UNIQUE_INDEX))
            print(f"    + mv_sales_daily (materialized view + unique index)")

            # --- Step 4: Grant to reporting_role ---
            try:
                await db.execute(text(
                    f'GRANT SELECT ON "{schema}".rpt_receivables_summary TO reporting_role'
                ))
                await db.execute(text(
                    f'GRANT SELECT ON "{schema}".rpt_cash_flow_daily TO reporting_role'
                ))
                await db.execute(text(
                    f'GRANT SELECT ON "{schema}".mv_sales_daily TO reporting_role'
                ))
                print(f"    + GRANT SELECT to reporting_role")
            except Exception as e:
                print(f"    ! GRANT failed (reporting_role may not exist): {e}")

            await db.commit()
            print(f"  Done: {schema}\n")

    print("=== Fix Complete ===")
    print("  Views created: rpt_receivables_summary, rpt_cash_flow_daily")
    print("  Materialized:  mv_sales_daily (WITH DATA)")
    print()


if __name__ == "__main__":
    asyncio.run(fix_views())
