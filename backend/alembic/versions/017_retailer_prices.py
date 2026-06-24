"""017: Add retailer_prices table for MVP retailer-specific pricing

Revision ID: 017_retailer_prices
Revises: 016_add_returned_status
Create Date: 2026-03-31

Phase 3 P0: Without pricing, retailer orders are financially meaningless.
This migration adds a simple retailer_id + sku_id → price lookup table
in the tenant schema.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '017_retailer_prices'
down_revision = '016_add_returned_status'
branch_labels = None
depends_on = None


REQUIRED_COLUMNS = {
    "id": {"data_type": "uuid", "nullable": "NO"},
    "retailer_id": {"data_type": "uuid", "nullable": "NO"},
    "sku_id": {"data_type": "uuid", "nullable": "NO"},
    "price": {
        "data_type": "numeric",
        "nullable": "NO",
        "numeric_precision": 12,
        "numeric_scale": 2,
    },
    "created_at": {"nullable": "NO"},
    "updated_at": {"nullable": "NO"},
    "is_deleted": {"data_type": "boolean", "nullable": "NO"},
    "deleted_at": {},
    "created_by": {"data_type": "uuid"},
    "updated_by": {"data_type": "uuid"},
}


def _current_schema(bind) -> str:
    return bind.execute(sa.text("SELECT current_schema()")).scalar_one()


def _table_exists(bind, schema: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_name = 'retailer_prices'"
            ),
            {"schema": schema},
        ).first()
    )


def _columns(bind, schema: str) -> dict[str, dict]:
    rows = bind.execute(
        sa.text(
            "SELECT column_name, data_type, is_nullable AS nullable, "
            "numeric_precision, numeric_scale "
            "FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = 'retailer_prices'"
        ),
        {"schema": schema},
    ).mappings()
    return {row["column_name"]: dict(row) for row in rows}


def _validate_existing_table(bind, schema: str) -> None:
    columns = _columns(bind, schema)
    violations: list[str] = []

    for column_name, expected in REQUIRED_COLUMNS.items():
        column = columns.get(column_name)
        if column is None:
            violations.append(f"missing column '{column_name}'")
            continue

        for key, expected_value in expected.items():
            if column.get(key) != expected_value:
                violations.append(
                    f"column '{column_name}' has {key}={column.get(key)!r}, "
                    f"expected {expected_value!r}"
                )

    if violations:
        violation_list = "; ".join(violations)
        raise RuntimeError(
            f"retailer_prices exists in schema '{schema}' but does not match "
            f"migration 017 contract: {violation_list}"
        )


def _constraint_exists(bind, schema: str, constraint_name: str, constraint_type: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM pg_constraint c "
                "JOIN pg_namespace n ON n.oid = c.connamespace "
                "WHERE n.nspname = :schema "
                "AND c.conrelid = to_regclass(:qualified_table) "
                "AND c.conname = :constraint_name "
                "AND c.contype = :constraint_type"
            ),
            {
                "schema": schema,
                "qualified_table": f'"{schema}".retailer_prices',
                "constraint_name": constraint_name,
                "constraint_type": constraint_type,
            },
        ).first()
    )


def _index_exists(bind, schema: str, index_name: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM pg_indexes "
                "WHERE schemaname = :schema AND indexname = :index_name"
            ),
            {"schema": schema, "index_name": index_name},
        ).first()
    )


def _ensure_existing_table_contract(bind, schema: str) -> None:
    _validate_existing_table(bind, schema)

    if not _constraint_exists(bind, schema, "uq_retailer_prices_retailer_sku", "u"):
        op.create_unique_constraint(
            "uq_retailer_prices_retailer_sku",
            "retailer_prices",
            ["retailer_id", "sku_id"],
        )

    if not _constraint_exists(bind, schema, "ck_retailer_prices_positive_price", "c"):
        op.create_check_constraint(
            "ck_retailer_prices_positive_price",
            "retailer_prices",
            "price > 0",
        )

    if not _index_exists(bind, schema, "ix_retailer_prices_retailer_id"):
        op.create_index("ix_retailer_prices_retailer_id", "retailer_prices", ["retailer_id"])

    if not _index_exists(bind, schema, "ix_retailer_prices_sku_id"):
        op.create_index("ix_retailer_prices_sku_id", "retailer_prices", ["sku_id"])


def upgrade() -> None:
    bind = op.get_bind()
    schema = _current_schema(bind)

    if _table_exists(bind, schema):
        _ensure_existing_table_contract(bind, schema)
        return

    op.create_table(
        'retailer_prices',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('retailer_id', postgresql.UUID(as_uuid=True), nullable=False, comment='FK to public.retailers.id'),
        sa.Column('sku_id', postgresql.UUID(as_uuid=True), nullable=False, comment='FK to skus.id'),
        sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False, comment='Sell price'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('retailer_id', 'sku_id', name='uq_retailer_prices_retailer_sku'),
        sa.CheckConstraint('price > 0', name='ck_retailer_prices_positive_price'),
    )
    op.create_index('ix_retailer_prices_retailer_id', 'retailer_prices', ['retailer_id'])
    op.create_index('ix_retailer_prices_sku_id', 'retailer_prices', ['sku_id'])


def downgrade() -> None:
    op.drop_index('ix_retailer_prices_sku_id', table_name='retailer_prices')
    op.drop_index('ix_retailer_prices_retailer_id', table_name='retailer_prices')
    op.drop_table('retailer_prices')
