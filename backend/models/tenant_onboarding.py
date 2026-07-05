"""Tenant onboarding and email auth public schema models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import PublicBaseModel


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
TERMINAL_PASSWORD_CLEANUP_STATES = ("active", "cancelled", "expired")
EMAIL_VERIFICATION_TOKEN_PURPOSE = "signup_email_verification"
PASSWORD_RESET_TOKEN_PURPOSE = "password_reset"  # pragma: allowlist secret


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class TenantRegistration(PublicBaseModel):
    """Durable customer-facing registration state before tenant activation."""

    __tablename__ = "tenant_registrations"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_quoted(TENANT_REGISTRATION_STATUSES)})",
            name="ck_tenant_registrations_status",
        ),
        CheckConstraint(
            "owner_email = lower(btrim(owner_email)) AND owner_email NOT LIKE '% %'",
            name="ck_tenant_registrations_owner_email_normalized",
        ),
        CheckConstraint(
            "status NOT IN ('active', 'cancelled', 'expired') "
            "OR (password_hash IS NULL AND password_hash_cleared_at IS NOT NULL)",
            name="ck_tenant_registrations_terminal_password_hash_cleared",
        ),
        CheckConstraint(
            "status <> 'failed' OR retry_allowed_until IS NOT NULL OR password_hash IS NULL",
            name="ck_tenant_registrations_failed_password_hash_retry_bound",
        ),
        Index(
            "ux_tenant_registrations_owner_email_live",
            "owner_email",
            unique=True,
            postgresql_where=text(f"status IN ({_quoted(LIVE_REGISTRATION_STATUSES)})"),
        ),
        Index(
            "ux_tenant_registrations_tenant_code_reserved",
            "tenant_code",
            unique=True,
            postgresql_where=text("tenant_code IS NOT NULL"),
        ),
        Index(
            "ux_tenant_registrations_wholesaler_id",
            "wholesaler_id",
            unique=True,
            postgresql_where=text("wholesaler_id IS NOT NULL"),
        ),
        Index(
            "ux_tenant_registrations_tenant_schema",
            "tenant_schema",
            unique=True,
            postgresql_where=text("tenant_schema IS NOT NULL"),
        ),
        Index(
            "ux_tenant_registrations_idempotency_key_hash",
            "idempotency_key_hash",
            unique=True,
            postgresql_where=text("idempotency_key_hash IS NOT NULL"),
        ),
        Index("ix_tenant_registrations_status", "status"),
        Index("ix_tenant_registrations_expires_at", "expires_at"),
        Index("ix_tenant_registrations_request_fingerprint_hash", "request_fingerprint_hash"),
        {"schema": "public"},
    )

    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    business_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    owner_email: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_full_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_hash_cleared_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_hash_cleanup_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="pending_email_verification",
        server_default=text("'pending_email_verification'"),
    )
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provisioning_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provisioning_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_allowed_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    wholesaler_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.wholesalers.id"),
        nullable=True,
    )
    tenant_schema: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    idempotency_key_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    request_fingerprint_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EmailVerificationToken(PublicBaseModel):
    """Single-use signup email verification token metadata."""

    __tablename__ = "email_verification_tokens"
    __table_args__ = (
        CheckConstraint(
            f"purpose = '{EMAIL_VERIFICATION_TOKEN_PURPOSE}'",
            name="ck_email_verification_tokens_purpose",
        ),
        CheckConstraint(
            "used_at IS NULL OR revoked_at IS NULL",
            name="ck_email_verification_tokens_not_used_and_revoked",
        ),
        CheckConstraint(
            "sent_to_email = lower(btrim(sent_to_email)) AND sent_to_email NOT LIKE '% %'",
            name="ck_email_verification_tokens_sent_to_email_normalized",
        ),
        CheckConstraint(
            "send_count >= 1", name="ck_email_verification_tokens_send_count_positive"
        ),
        Index("ux_email_verification_tokens_token_hash", "token_hash", unique=True),
        Index(
            "ux_email_verification_tokens_registration_active",
            "registration_id",
            unique=True,
            postgresql_where=text("used_at IS NULL AND revoked_at IS NULL"),
        ),
        Index("ix_email_verification_tokens_registration_id", "registration_id"),
        Index("ix_email_verification_tokens_expires_at", "expires_at"),
        Index("ix_email_verification_tokens_request_fingerprint_hash", "request_fingerprint_hash"),
        {"schema": "public"},
    )

    registration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.tenant_registrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=EMAIL_VERIFICATION_TOKEN_PURPOSE,
        server_default=text(f"'{EMAIL_VERIFICATION_TOKEN_PURPOSE}'"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    send_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    last_sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    request_fingerprint_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)


class PasswordResetToken(PublicBaseModel):
    """Single-use password reset token metadata without raw token storage."""

    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        CheckConstraint(
            f"purpose = '{PASSWORD_RESET_TOKEN_PURPOSE}'",
            name="ck_password_reset_tokens_purpose",
        ),
        CheckConstraint(
            "used_at IS NULL OR revoked_at IS NULL",
            name="ck_password_reset_tokens_not_used_and_revoked",
        ),
        Index("ux_password_reset_tokens_token_hash", "token_hash", unique=True),
        Index(
            "ux_password_reset_tokens_email_active_global",
            "user_email_hash",
            unique=True,
            postgresql_where=text("tenant_id IS NULL AND used_at IS NULL AND revoked_at IS NULL"),
        ),
        Index(
            "ux_password_reset_tokens_email_tenant_active",
            "user_email_hash",
            "tenant_id",
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL AND used_at IS NULL AND revoked_at IS NULL"),
        ),
        Index("ix_password_reset_tokens_user_email_hash", "user_email_hash"),
        Index("ix_password_reset_tokens_tenant_id", "tenant_id"),
        Index("ix_password_reset_tokens_expires_at", "expires_at"),
        Index("ix_password_reset_tokens_request_fingerprint_hash", "request_fingerprint_hash"),
        {"schema": "public"},
    )

    user_email_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.wholesalers.id"),
        nullable=True,
    )
    tenant_schema: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PASSWORD_RESET_TOKEN_PURPOSE,
        server_default=text(f"'{PASSWORD_RESET_TOKEN_PURPOSE}'"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    request_fingerprint_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
