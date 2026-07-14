"""DC-11P1: platform operator identity schema foundation.

Revision ID: 034_platform_operators
Revises: 033_order_status_enum_reconciliation
Create Date: 2026-07-14

Creates four additive public-schema tables for platform operator identity
and credential lifecycle. No existing tables are modified.

R1 corrections:
- Every create_table / create_index / drop uses schema="public".
- FKs reference public.platform_operators.id.
- Email normalization CHECK replaces the redundant lower(trim(email)) index.
- No runtime model/service imports (self-contained migration).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "034_platform_operators"
down_revision = "033_order_status_enum_reconciliation"
branch_labels = None
depends_on = None

SCHEMA = "public"

TABLE_OPERATORS = f"{SCHEMA}.platform_operators"
TABLE_SETUP = f"{SCHEMA}.platform_operator_setup_tokens"
TABLE_RESET = f"{SCHEMA}.platform_operator_reset_tokens"
TABLE_RECOVERY = f"{SCHEMA}.platform_operator_recovery_credentials"


def upgrade() -> None:
    # 1. platform_operators
    op.create_table(
        "platform_operators",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default=sa.text("'pending_setup'")),
        sa.Column("role", sa.String(20), nullable=False,
                  server_default=sa.text("'platform_operator'")),
        sa.Column("failed_login_attempts", sa.Integer, nullable=False,
                  server_default=sa.text("0")),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auth_version", sa.BigInteger, nullable=False,
                  server_default=sa.text("1")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by", UUID(as_uuid=True),
                  sa.ForeignKey(f"{TABLE_OPERATORS}.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "email = lower(btrim(email)) AND length(btrim(email)) > 0",
            name="ck_platform_operators_email_normalized",
        ),
        sa.CheckConstraint(
            "status IN ('pending_setup', 'active', 'disabled')",
            name="ck_platform_operators_status",
        ),
        sa.CheckConstraint(
            "role IN ('platform_admin', 'platform_operator')",
            name="ck_platform_operators_role",
        ),
        sa.CheckConstraint(
            "failed_login_attempts >= 0",
            name="ck_platform_operators_failed_attempts_nonneg",
        ),
        sa.CheckConstraint(
            "auth_version >= 1",
            name="ck_platform_operators_auth_version_min",
        ),
        sa.CheckConstraint(
            "status != 'active' OR password_hash IS NOT NULL",
            name="ck_platform_operators_active_requires_password",
        ),
        sa.CheckConstraint(
            "status != 'active' OR revoked_at IS NULL",
            name="ck_platform_operators_active_not_revoked",
        ),
        sa.UniqueConstraint("email", name="uq_platform_operators_email"),
        schema=SCHEMA,
    )

    # 2. platform_operator_setup_tokens
    op.create_table(
        "platform_operator_setup_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("operator_id", UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False,
                  server_default=sa.text("'setup'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["operator_id"], [f"{TABLE_OPERATORS}.id"],
            ondelete="CASCADE",
            name="fk_setup_tokens_operator",
        ),
        sa.CheckConstraint(
            "purpose = 'setup'",
            name="ck_setup_tokens_purpose",
        ),
        sa.CheckConstraint(
            "used_at IS NULL OR revoked_at IS NULL",
            name="ck_setup_tokens_not_used_and_revoked",
        ),
        sa.UniqueConstraint("token_hash", name="uq_setup_tokens_token_hash"),
        schema=SCHEMA,
    )

    op.create_index(
        "ux_setup_tokens_operator_active",
        "platform_operator_setup_tokens",
        ["operator_id"],
        unique=True,
        postgresql_where=sa.text(
            "used_at IS NULL AND revoked_at IS NULL AND is_deleted = false"
        ),
        schema=SCHEMA,
    )

    # 3. platform_operator_reset_tokens
    op.create_table(
        "platform_operator_reset_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("operator_id", UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False,
                  server_default=sa.text("'reset'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["operator_id"], [f"{TABLE_OPERATORS}.id"],
            ondelete="CASCADE",
            name="fk_reset_tokens_operator",
        ),
        sa.CheckConstraint(
            "purpose = 'reset'",
            name="ck_reset_tokens_purpose",
        ),
        sa.CheckConstraint(
            "used_at IS NULL OR revoked_at IS NULL",
            name="ck_reset_tokens_not_used_and_revoked",
        ),
        sa.UniqueConstraint("token_hash", name="uq_reset_tokens_token_hash"),
        schema=SCHEMA,
    )

    op.create_index(
        "ux_reset_tokens_operator_active",
        "platform_operator_reset_tokens",
        ["operator_id"],
        unique=True,
        postgresql_where=sa.text(
            "used_at IS NULL AND revoked_at IS NULL AND is_deleted = false"
        ),
        schema=SCHEMA,
    )

    # 4. platform_operator_recovery_credentials
    op.create_table(
        "platform_operator_recovery_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("operator_id", UUID(as_uuid=True), nullable=False),
        sa.Column("credential_hash", sa.String(128), nullable=False),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default=sa.text("'active'")),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["operator_id"], [f"{TABLE_OPERATORS}.id"],
            ondelete="CASCADE",
            name="fk_recovery_credentials_operator",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'used', 'revoked')",
            name="ck_recovery_credentials_status",
        ),
        sa.CheckConstraint(
            "(status = 'active' AND used_at IS NULL AND revoked_at IS NULL) OR "
            "(status = 'used' AND used_at IS NOT NULL AND revoked_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL AND used_at IS NULL)",
            name="ck_recovery_credentials_state_consistency",
        ),
        sa.UniqueConstraint(
            "credential_hash", name="uq_recovery_credentials_hash"
        ),
        schema=SCHEMA,
    )

    op.create_index(
        "ux_recovery_credentials_operator_active",
        "platform_operator_recovery_credentials",
        ["operator_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'active' AND is_deleted = false"
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ux_recovery_credentials_operator_active", schema=SCHEMA,
                  table_name="platform_operator_recovery_credentials")
    op.drop_table("platform_operator_recovery_credentials", schema=SCHEMA)
    op.drop_index("ux_reset_tokens_operator_active", schema=SCHEMA,
                  table_name="platform_operator_reset_tokens")
    op.drop_table("platform_operator_reset_tokens", schema=SCHEMA)
    op.drop_index("ux_setup_tokens_operator_active", schema=SCHEMA,
                  table_name="platform_operator_setup_tokens")
    op.drop_table("platform_operator_setup_tokens", schema=SCHEMA)
    op.drop_table("platform_operators", schema=SCHEMA)
