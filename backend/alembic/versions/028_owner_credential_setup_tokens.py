"""028: Owner credential setup token schema foundation

Revision ID: 028_owner_credential_setup_tokens
Revises: 027_onboarding_status_tokens
Create Date: 2026-07-08

U6-I1: add public hash-only owner credential setup token storage. This migration
is schema-only and does not add endpoints, credential delivery, or tenant admin
creation behavior.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "028_owner_credential_setup_tokens"
down_revision = "027_onboarding_status_tokens"
branch_labels = None
depends_on = None


OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE = "owner_credential_setup"


def upgrade() -> None:
    conn = op.get_bind()
    if _is_tenant_schema(conn):
        return

    op.create_table(
        "owner_credential_setup_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("registration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "purpose",
            sa.String(length=64),
            server_default=sa.text(f"'{OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE}'"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["registration_id"],
            ["public.tenant_registrations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_owner_credential_setup_tokens_token_hash"),
        sa.CheckConstraint(
            f"purpose = '{OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE}'",
            name="ck_owner_credential_setup_tokens_purpose",
        ),
        sa.CheckConstraint(
            "used_at IS NULL OR revoked_at IS NULL",
            name="ck_owner_credential_setup_tokens_not_used_and_revoked",
        ),
        schema="public",
    )

    op.create_index(
        "ux_owner_credential_setup_tokens_token_hash",
        "owner_credential_setup_tokens",
        ["token_hash"],
        unique=True,
        schema="public",
    )
    op.create_index(
        "ux_owner_credential_setup_tokens_registration_active",
        "owner_credential_setup_tokens",
        ["registration_id"],
        unique=True,
        schema="public",
        postgresql_where=sa.text(
            "used_at IS NULL AND revoked_at IS NULL AND is_deleted = false"
        ),
    )
    op.create_index(
        "ix_owner_credential_setup_tokens_registration_id",
        "owner_credential_setup_tokens",
        ["registration_id"],
        schema="public",
    )
    op.create_index(
        "ix_owner_credential_setup_tokens_expires_at",
        "owner_credential_setup_tokens",
        ["expires_at"],
        schema="public",
    )


def downgrade() -> None:
    conn = op.get_bind()
    if _is_tenant_schema(conn):
        return

    op.drop_table("owner_credential_setup_tokens", schema="public")


def _is_tenant_schema(conn) -> bool:
    search_path = conn.execute(sa.text("SHOW search_path")).scalar() or ""
    return any(part.strip().startswith("t_") for part in search_path.split(","))
