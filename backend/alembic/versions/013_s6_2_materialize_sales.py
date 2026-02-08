"""S6-2: Materialize Sales Daily View

Revision ID: 013_s6_2_materialize_sales
Revises: 012_s6_1_read_models
Create Date: 2026-02-07

Philosophy: "Staleness is acceptable; Locking is not."

Changes:
1. Drop standard view rpt_sales_daily
2. Create MATERIALIZED VIEW mv_sales_daily (same aggregation logic)
3. Add UNIQUE INDEX for REFRESH CONCURRENTLY support
4. Grant SELECT to reporting_role
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '013_s6_2_materialize_sales'
down_revision = '012_s6_1_read_models'
branch_labels = None
depends_on = None


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

# Rollback: recreate the original standard view from S6-1
RPT_SALES_DAILY_VIEW = """
CREATE OR REPLACE VIEW rpt_sales_daily AS
SELECT
    transaction_date::DATE                          AS transaction_date,
    'USD'::CHAR(3)                                  AS reporting_currency_code,
    ABS(SUM(amount))::NUMERIC(20, 4)                AS daily_revenue,
    COUNT(*)                                        AS transaction_count
FROM ledger_entries
WHERE account_type = 'revenue'
  AND is_deleted = false
GROUP BY transaction_date::DATE
ORDER BY transaction_date::DATE;
"""


def upgrade() -> None:
    """
    Convert rpt_sales_daily (view) to mv_sales_daily (materialized view)
    in all tenant schemas.

    Steps per schema:
    1. DROP VIEW rpt_sales_daily
    2. CREATE MATERIALIZED VIEW mv_sales_daily WITH DATA
    3. CREATE UNIQUE INDEX (required for REFRESH CONCURRENTLY)
    4. GRANT SELECT to reporting_role
    """
    connection = op.get_bind()

    result = connection.execute(sa.text("""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name LIKE 't_%'
        ORDER BY schema_name
    """))
    tenant_schemas = [row[0] for row in result]

    for schema in tenant_schemas:
        connection.execute(sa.text(
            f'SET LOCAL search_path TO "{schema}", public'
        ))

        # Step 1: Drop the standard view
        connection.execute(sa.text("DROP VIEW IF EXISTS rpt_sales_daily"))

        # Step 2: Create materialized view
        connection.execute(sa.text(MV_SALES_DAILY))

        # Step 3: Create unique index for CONCURRENTLY support
        connection.execute(sa.text(MV_UNIQUE_INDEX))

        # Step 4: Grant SELECT to reporting_role
        connection.execute(sa.text(
            f'GRANT SELECT ON "{schema}".mv_sales_daily TO reporting_role'
        ))

        print(f"  ✅ {schema}: rpt_sales_daily → mv_sales_daily (materialized)")

    print(f"\n✅ Materialized {len(tenant_schemas)} tenant schema(s)")
    print(f"   Unique index: idx_mv_sales_daily_u1 (transaction_date, reporting_currency_code)")
    print(f"   REFRESH CONCURRENTLY: enabled")


def downgrade() -> None:
    """
    Revert mv_sales_daily back to rpt_sales_daily standard view.
    """
    connection = op.get_bind()

    result = connection.execute(sa.text("""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name LIKE 't_%'
        ORDER BY schema_name
    """))
    tenant_schemas = [row[0] for row in result]

    for schema in tenant_schemas:
        connection.execute(sa.text(
            f'SET LOCAL search_path TO "{schema}", public'
        ))

        # Drop materialized view (index drops automatically)
        connection.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS mv_sales_daily"))

        # Recreate standard view
        connection.execute(sa.text(RPT_SALES_DAILY_VIEW))

        # Re-grant
        connection.execute(sa.text(
            f'GRANT SELECT ON "{schema}".rpt_sales_daily TO reporting_role'
        ))

        print(f"  ⚠️  {schema}: mv_sales_daily → rpt_sales_daily (reverted to view)")
