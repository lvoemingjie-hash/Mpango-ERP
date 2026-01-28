"""Phase B2 - invitations, retailers, and wholesaler-retailer bindings (public schema)

Revision ID: 002_phase_b2_invitation_binding
Revises: 001_initial_schema
Create Date: 2026-01-26

Creates public schema tables:
- public.retailers
- public.invitations
- public.wholesaler_retailer_bindings
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "002_phase_b2_invitation_binding"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Retailers (public)
    op.create_table(
        "retailers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone"),
        schema="public",
    )
    op.create_index("ix_retailers_phone", "retailers", ["phone"], unique=True, schema="public")

    # Invitations (public)
    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'active'"), nullable=False),
        sa.Column("wholesaler_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("retailer_phone", sa.String(length=32), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_retailer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["wholesaler_id"], ["public.wholesalers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["used_retailer_id"], ["public.retailers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        schema="public",
    )
    op.create_index("ix_invitations_code", "invitations", ["code"], unique=True, schema="public")
    op.create_index("ix_invitations_wholesaler_id", "invitations", ["wholesaler_id"], unique=False, schema="public")
    op.create_index("ix_invitations_retailer_phone", "invitations", ["retailer_phone"], unique=False, schema="public")

    # Wholesaler-Retailer bindings (public)
    op.create_table(
        "wholesaler_retailer_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("wholesaler_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("retailer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'active'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["wholesaler_id"], ["public.wholesalers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["retailer_id"], ["public.retailers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wholesaler_id", "retailer_id", name="uq_wholesaler_retailer"),
        schema="public",
    )
    op.create_index("ix_bindings_wholesaler_id", "wholesaler_retailer_bindings", ["wholesaler_id"], unique=False, schema="public")
    op.create_index("ix_bindings_retailer_id", "wholesaler_retailer_bindings", ["retailer_id"], unique=False, schema="public")


def downgrade() -> None:
    op.drop_index("ix_bindings_retailer_id", table_name="wholesaler_retailer_bindings", schema="public")
    op.drop_index("ix_bindings_wholesaler_id", table_name="wholesaler_retailer_bindings", schema="public")
    op.drop_table("wholesaler_retailer_bindings", schema="public")

    op.drop_index("ix_invitations_retailer_phone", table_name="invitations", schema="public")
    op.drop_index("ix_invitations_wholesaler_id", table_name="invitations", schema="public")
    op.drop_index("ix_invitations_code", table_name="invitations", schema="public")
    op.drop_table("invitations", schema="public")

    op.drop_index("ix_retailers_phone", table_name="retailers", schema="public")
    op.drop_table("retailers", schema="public")
