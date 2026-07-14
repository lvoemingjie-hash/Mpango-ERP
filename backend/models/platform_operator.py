"""Platform operator identity and credential lifecycle models (DC-11P1).

Four public-schema tables for platform operator authentication, independent
of tenant-local RBAC. No raw tokens or plaintext passwords are stored; only
hashes.

R1 corrections:
- Every model table includes {"schema": "public"}.
- Every FK references public.platform_operators.id.
- Email normalization CHECK constraint.
- ORM Index definitions match DDL partial unique indexes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID as UUIDType

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey,
    Index, Integer, String, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import PublicBaseModel


class PlatformOperator(PublicBaseModel):
    """A platform operator with independent authentication."""

    __tablename__ = "platform_operators"
    __table_args__ = (
        CheckConstraint(
            "email = lower(btrim(email)) AND length(btrim(email)) > 0",
            name="ck_platform_operators_email_normalized",
        ),
        CheckConstraint(
            "status IN ('pending_setup', 'active', 'disabled')",
            name="ck_platform_operators_status",
        ),
        CheckConstraint(
            "role IN ('platform_admin', 'platform_operator')",
            name="ck_platform_operators_role",
        ),
        CheckConstraint(
            "failed_login_attempts >= 0",
            name="ck_platform_operators_failed_attempts_nonneg",
        ),
        CheckConstraint(
            "auth_version >= 1",
            name="ck_platform_operators_auth_version_min",
        ),
        CheckConstraint(
            "status != 'active' OR password_hash IS NOT NULL",
            name="ck_platform_operators_active_requires_password",
        ),
        CheckConstraint(
            "status != 'active' OR revoked_at IS NULL",
            name="ck_platform_operators_active_not_revoked",
        ),
        {"schema": "public"},
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending_setup'")
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'platform_operator'")
    )
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    auth_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    invited_by: Mapped[Optional[UUIDType]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.platform_operators.id", ondelete="SET NULL"),
        nullable=True,
    )


class PlatformOperatorSetupToken(PublicBaseModel):
    """Single-use setup token for a platform operator (hash only)."""

    __tablename__ = "platform_operator_setup_tokens"
    __table_args__ = (
        CheckConstraint("purpose = 'setup'", name="ck_setup_tokens_purpose"),
        CheckConstraint(
            "used_at IS NULL OR revoked_at IS NULL",
            name="ck_setup_tokens_not_used_and_revoked",
        ),
        Index(
            "ux_setup_tokens_operator_active",
            "operator_id",
            unique=True,
            postgresql_where=text(
                "used_at IS NULL AND revoked_at IS NULL AND is_deleted = false"
            ),
        ),
        {"schema": "public"},
    )

    operator_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.platform_operators.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    purpose: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'setup'")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PlatformOperatorResetToken(PublicBaseModel):
    """Single-use password reset token for a platform operator (hash only)."""

    __tablename__ = "platform_operator_reset_tokens"
    __table_args__ = (
        CheckConstraint("purpose = 'reset'", name="ck_reset_tokens_purpose"),
        CheckConstraint(
            "used_at IS NULL OR revoked_at IS NULL",
            name="ck_reset_tokens_not_used_and_revoked",
        ),
        Index(
            "ux_reset_tokens_operator_active",
            "operator_id",
            unique=True,
            postgresql_where=text(
                "used_at IS NULL AND revoked_at IS NULL AND is_deleted = false"
            ),
        ),
        {"schema": "public"},
    )

    operator_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.platform_operators.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    purpose: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'reset'")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PlatformOperatorRecoveryCredential(PublicBaseModel):
    """Pre-provisioned break-glass recovery credential (hash only)."""

    __tablename__ = "platform_operator_recovery_credentials"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'used', 'revoked')",
            name="ck_recovery_credentials_status",
        ),
        CheckConstraint(
            "(status = 'active' AND used_at IS NULL AND revoked_at IS NULL) OR "
            "(status = 'used' AND used_at IS NOT NULL AND revoked_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL AND used_at IS NULL)",
            name="ck_recovery_credentials_state_consistency",
        ),
        Index(
            "ux_recovery_credentials_operator_active",
            "operator_id",
            unique=True,
            postgresql_where=text(
                "status = 'active' AND is_deleted = false"
            ),
        ),
        {"schema": "public"},
    )

    operator_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.platform_operators.id", ondelete="CASCADE"),
        nullable=False,
    )
    credential_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'active'")
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
