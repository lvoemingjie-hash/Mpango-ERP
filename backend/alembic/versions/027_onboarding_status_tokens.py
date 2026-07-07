"""027: Onboarding status token schema contract

Revision ID: 027_onboarding_status_tokens
Revises: 026_tenant_onboarding_auth_contract
Create Date: 2026-07-07

U6-E0: add public hash-only onboarding status token storage. This migration is
schema-only and does not add runtime onboarding status routes or tenant
provisioning behavior.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "027_onboarding_status_tokens"
down_revision = "026_tenant_onboarding_auth_contract"
branch_labels = None
depends_on = None


ONBOARDING_STATUS_TOKEN_PURPOSE = "onboarding_status"


def upgrade() -> None:
    conn = op.get_bind()
    if _is_tenant_schema(conn):
        return

    op.create_table(
        "onboarding_status_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("registration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "purpose",
            sa.String(length=64),
            server_default=sa.text(f"'{ONBOARDING_STATUS_TOKEN_PURPOSE}'"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["registration_id"], ["public.tenant_registrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            f"purpose = '{ONBOARDING_STATUS_TOKEN_PURPOSE}'",
            name="ck_onboarding_status_tokens_purpose",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_onboarding_status_tokens_expires_after_created",
        ),
        schema="public",
    )

    op.create_index(
        "ux_onboarding_status_tokens_token_hash",
        "onboarding_status_tokens",
        ["token_hash"],
        unique=True,
        schema="public",
    )
    op.create_index(
        "ix_onboarding_status_tokens_registration_id",
        "onboarding_status_tokens",
        ["registration_id"],
        schema="public",
    )
    op.create_index(
        "ix_onboarding_status_tokens_registration_active",
        "onboarding_status_tokens",
        ["registration_id"],
        schema="public",
        postgresql_where=sa.text("revoked_at IS NULL AND is_deleted = false"),
    )


def downgrade() -> None:
    conn = op.get_bind()
    if _is_tenant_schema(conn):
        return

    op.drop_table("onboarding_status_tokens", schema="public")


def _is_tenant_schema(conn) -> bool:
    search_path = conn.execute(sa.text("SHOW search_path")).scalar() or ""
    return any(part.strip().startswith("t_") for part in search_path.split(","))
