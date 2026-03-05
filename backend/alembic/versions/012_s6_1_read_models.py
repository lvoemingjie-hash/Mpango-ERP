"""S6-1: Financial Read Models (SQL Views)

Revision ID: 012_s6_1_read_models
Revises: 011_s6_p_reporting_role
Create Date: 2026-02-07

Philosophy: "Build the eyes of the ERP."

S6-P Compliance:
- ✅ All views prefixed with rpt_
- ✅ Created in tenant schemas (same as source tables)
- ✅ Include 'USD'::CHAR(3) AS reporting_currency_code
- ✅ Use transaction_date as time axis (never created_at)
- ✅ Monetary columns cast to NUMERIC(20, 4)
- ✅ Shallow Join Rule: Depth 0 (single table, no JOINs)

Views:
1. rpt_sales_daily        — Daily revenue aggregation
2. rpt_receivables_summary — Outstanding AR by customer
3. rpt_cash_flow_daily     — Daily cash movement with running balance
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '012_s6_1_read_models'
down_revision = '011_s6_p_reporting_role'
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# View SQL Definitions
# ---------------------------------------------------------------------------
# All views operate on ledger_entries with account_type filters.
# Join Depth: 0 (single table with WHERE clause — no JOINs).
# ---------------------------------------------------------------------------

RPT_SALES_DAILY = """
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

DROP_VIEWS = """
DROP VIEW IF EXISTS rpt_cash_flow_daily;
DROP VIEW IF EXISTS rpt_receivables_summary;
DROP VIEW IF EXISTS rpt_sales_daily;
"""


def upgrade() -> None:
    """
    Create rpt_* views in all tenant schemas.

    Views are tenant-scoped because ledger_entries lives in tenant schemas.
    The search_path determines which schema's ledger_entries is queried.
    """
    connection = op.get_bind()

    # Discover tenant schemas that have ledger_entries (required by rpt_* views)
    result = connection.execute(sa.text("""
        SELECT DISTINCT table_schema
        FROM information_schema.tables
        WHERE table_schema LIKE 't_%'
          AND table_name = 'ledger_entries'
        ORDER BY table_schema
    """))
    tenant_schemas = [row[0] for row in result]

    for schema in tenant_schemas:
        # Set search_path to this tenant schema
        connection.execute(sa.text(
            f'SET LOCAL search_path TO "{schema}", public'
        ))

        # Create all three views
        connection.execute(sa.text(RPT_SALES_DAILY))
        connection.execute(sa.text(RPT_RECEIVABLES_SUMMARY))
        connection.execute(sa.text(RPT_CASH_FLOW_DAILY))

        # Grant SELECT to reporting_role
        connection.execute(sa.text(
            f'GRANT SELECT ON "{schema}".rpt_sales_daily TO reporting_role'
        ))
        connection.execute(sa.text(
            f'GRANT SELECT ON "{schema}".rpt_receivables_summary TO reporting_role'
        ))
        connection.execute(sa.text(
            f'GRANT SELECT ON "{schema}".rpt_cash_flow_daily TO reporting_role'
        ))

        print(f"  ✅ Created 3 rpt_* views in schema: {schema}")

    print(f"\n✅ Read Models created in {len(tenant_schemas)} tenant schema(s)")
    print(f"   Views: rpt_sales_daily, rpt_receivables_summary, rpt_cash_flow_daily")
    print(f"   S6-P Compliance: ✅ Prefix, Currency, Time, Precision, Shallow Join")


def downgrade() -> None:
    """
    Drop rpt_* views from all tenant schemas.
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
        connection.execute(sa.text(DROP_VIEWS))
        print(f"  ⚠️  Dropped rpt_* views from schema: {schema}")

    print(f"\n⚠️  Read Models removed from {len(tenant_schemas)} tenant schema(s)")
