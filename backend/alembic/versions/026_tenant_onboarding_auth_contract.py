"""026: Tenant onboarding and email auth schema contract

Revision ID: 026_tenant_onboarding_auth_contract
Revises: 025_intake_apply_audit
Create Date: 2026-07-05

U6-B: add public registration and token tables only. This migration is a
no-op for tenant-schema migrations and does not add runtime auth routes.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "026_tenant_onboarding_auth_contract"
down_revision = "025_intake_apply_audit"
branch_labels = None
depends_on = None


TENANT_REGISTRATION_STATUSES = (
    "pending_email_verification",
    "email_verified",
    "provisioning",
    "active",
    "failed",
    "cancelled",
    "expired",
)
LIVE_REGISTRATION_STATUSES = (
    "pending_email_verification",
    "email_verified",
    "provisioning",
    "active",
    "failed",
)
EMAIL_VERIFICATION_TOKEN_PURPOSE = "signup_email_verification"
PASSWORD_RESET_TOKEN_PURPOSE = "password_reset"  # pragma: allowlist secret


def upgrade() -> None:
    conn = op.get_bind()
    if _is_tenant_schema(conn):
        return

    op.create_table(
        "tenant_registrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("tenant_code", sa.String(length=32), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("business_type", sa.String(length=64), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("owner_email", sa.String(length=255), nullable=False),
        sa.Column("owner_full_name", sa.Text(), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("password_hash_cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_hash_cleanup_reason", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=40),
            server_default=sa.text("'pending_email_verification'"),
            nullable=False,
        ),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provisioning_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provisioning_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("retry_allowed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("wholesaler_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_schema", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key_hash", sa.String(length=128), nullable=True),
        sa.Column("request_fingerprint_hash", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["wholesaler_id"], ["public.wholesalers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            f"status IN ({_quoted(TENANT_REGISTRATION_STATUSES)})",
            name="ck_tenant_registrations_status",
        ),
        sa.CheckConstraint(
            "owner_email = lower(btrim(owner_email)) AND owner_email NOT LIKE '% %'",
            name="ck_tenant_registrations_owner_email_normalized",
        ),
        sa.CheckConstraint(
            "status NOT IN ('active', 'cancelled', 'expired') "
            "OR (password_hash IS NULL AND password_hash_cleared_at IS NOT NULL)",
            name="ck_tenant_registrations_terminal_password_hash_cleared",
        ),
        sa.CheckConstraint(
            "status <> 'failed' OR retry_allowed_until IS NOT NULL OR "
            "(password_hash IS NULL AND password_hash_cleared_at IS NOT NULL)",
            name="ck_tenant_registrations_failed_password_hash_retry_bound",
        ),
        schema="public",
    )

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("registration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "purpose",
            sa.String(length=32),
            server_default=sa.text(f"'{EMAIL_VERIFICATION_TOKEN_PURPOSE}'"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_to_email", sa.String(length=255), nullable=False),
        sa.Column("send_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("request_fingerprint_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["registration_id"], ["public.tenant_registrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            f"purpose = '{EMAIL_VERIFICATION_TOKEN_PURPOSE}'",
            name="ck_email_verification_tokens_purpose",
        ),
        sa.CheckConstraint(
            "used_at IS NULL OR revoked_at IS NULL",
            name="ck_email_verification_tokens_not_used_and_revoked",
        ),
        sa.CheckConstraint(
            "sent_to_email = lower(btrim(sent_to_email)) AND sent_to_email NOT LIKE '% %'",
            name="ck_email_verification_tokens_sent_to_email_normalized",
        ),
        sa.CheckConstraint("send_count >= 1", name="ck_email_verification_tokens_send_count_positive"),
        schema="public",
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_email_hash", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_schema", sa.String(length=64), nullable=True),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "purpose",
            sa.String(length=32),
            server_default=sa.text(f"'{PASSWORD_RESET_TOKEN_PURPOSE}'"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_fingerprint_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["public.wholesalers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            f"purpose = '{PASSWORD_RESET_TOKEN_PURPOSE}'",
            name="ck_password_reset_tokens_purpose",
        ),
        sa.CheckConstraint(
            "used_at IS NULL OR revoked_at IS NULL",
            name="ck_password_reset_tokens_not_used_and_revoked",
        ),
        schema="public",
    )

    _create_indexes()


def downgrade() -> None:
    conn = op.get_bind()
    if _is_tenant_schema(conn):
        return

    op.drop_table("password_reset_tokens", schema="public")
    op.drop_table("email_verification_tokens", schema="public")
    op.drop_table("tenant_registrations", schema="public")


def _create_indexes() -> None:
    op.create_index(
        "ux_tenant_registrations_owner_email_live",
        "tenant_registrations",
        ["owner_email"],
        unique=True,
        schema="public",
        postgresql_where=sa.text(f"status IN ({_quoted(LIVE_REGISTRATION_STATUSES)})"),
    )
    op.create_index(
        "ux_tenant_registrations_tenant_code_reserved",
        "tenant_registrations",
        ["tenant_code"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("tenant_code IS NOT NULL"),
    )
    op.create_index(
        "ux_tenant_registrations_wholesaler_id",
        "tenant_registrations",
        ["wholesaler_id"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("wholesaler_id IS NOT NULL"),
    )
    op.create_index(
        "ux_tenant_registrations_tenant_schema",
        "tenant_registrations",
        ["tenant_schema"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("tenant_schema IS NOT NULL"),
    )
    op.create_index(
        "ux_tenant_registrations_idempotency_key_hash",
        "tenant_registrations",
        ["idempotency_key_hash"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("idempotency_key_hash IS NOT NULL"),
    )
    op.create_index("ix_tenant_registrations_status", "tenant_registrations", ["status"], schema="public")
    op.create_index("ix_tenant_registrations_expires_at", "tenant_registrations", ["expires_at"], schema="public")
    op.create_index(
        "ix_tenant_registrations_request_fingerprint_hash",
        "tenant_registrations",
        ["request_fingerprint_hash"],
        schema="public",
    )
    op.create_index(
        "ux_email_verification_tokens_token_hash",
        "email_verification_tokens",
        ["token_hash"],
        unique=True,
        schema="public",
    )
    op.create_index(
        "ux_email_verification_tokens_registration_active",
        "email_verification_tokens",
        ["registration_id"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("used_at IS NULL AND revoked_at IS NULL"),
    )
    op.create_index(
        "ix_email_verification_tokens_registration_id",
        "email_verification_tokens",
        ["registration_id"],
        schema="public",
    )
    op.create_index("ix_email_verification_tokens_expires_at", "email_verification_tokens", ["expires_at"], schema="public")
    op.create_index(
        "ix_email_verification_tokens_request_fingerprint_hash",
        "email_verification_tokens",
        ["request_fingerprint_hash"],
        schema="public",
    )
    op.create_index(
        "ux_password_reset_tokens_token_hash",
        "password_reset_tokens",
        ["token_hash"],
        unique=True,
        schema="public",
    )
    op.create_index(
        "ux_password_reset_tokens_email_active_global",
        "password_reset_tokens",
        ["user_email_hash"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("tenant_id IS NULL AND used_at IS NULL AND revoked_at IS NULL"),
    )
    op.create_index(
        "ux_password_reset_tokens_email_tenant_active",
        "password_reset_tokens",
        ["user_email_hash", "tenant_id"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("tenant_id IS NOT NULL AND used_at IS NULL AND revoked_at IS NULL"),
    )
    op.create_index("ix_password_reset_tokens_user_email_hash", "password_reset_tokens", ["user_email_hash"], schema="public")
    op.create_index("ix_password_reset_tokens_tenant_id", "password_reset_tokens", ["tenant_id"], schema="public")
    op.create_index("ix_password_reset_tokens_expires_at", "password_reset_tokens", ["expires_at"], schema="public")
    op.create_index(
        "ix_password_reset_tokens_request_fingerprint_hash",
        "password_reset_tokens",
        ["request_fingerprint_hash"],
        schema="public",
    )


def _is_tenant_schema(conn) -> bool:
    search_path = conn.execute(sa.text("SHOW search_path")).scalar() or ""
    return any(part.strip().startswith("t_") for part in search_path.split(","))


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)
