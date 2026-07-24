"""Retailer credential setup/reset token models (public schema).

DC-12R1-S1: retailer-owned credential lifecycle. These tokens are bound to the
public identity (retailer_id) — never inferred from email, schema name, or
tenant-user strings. Setup tokens additionally bind to the binding that
triggered them; reset tokens are retailer-scoped (no wholesaler_id/binding_id).

Mirrors the single-use, hash-only, partial-unique-active pattern of
OwnerCredentialSetupToken (models/tenant_onboarding.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import PublicBaseModel


RETAILER_CREDENTIAL_SETUP_TOKEN_PURPOSE = "retailer_credential_setup"
RETAILER_PASSWORD_RESET_TOKEN_PURPOSE = "retailer_password_reset"  # pragma: allowlist secret


class RetailerCredentialSetupToken(PublicBaseModel):
    """Single-use retailer credential setup token metadata without raw token storage.

    Bound to the public identity: retailer_id plus the binding_id that triggered
    provisioning. One active (unused, unrevoked) token per retailer at a time.
    """

    __tablename__ = "retailer_credential_setup_tokens"
    __table_args__ = (
        CheckConstraint(
            f"purpose = '{RETAILER_CREDENTIAL_SETUP_TOKEN_PURPOSE}'",
            name="ck_retailer_credential_setup_tokens_purpose",
        ),
        CheckConstraint(
            "used_at IS NULL OR revoked_at IS NULL",
            name="ck_retailer_credential_setup_tokens_not_used_and_revoked",
        ),
        UniqueConstraint(
            "token_hash",
            name="uq_retailer_credential_setup_tokens_token_hash",
        ),
        Index(
            "ux_retailer_credential_setup_tokens_token_hash",
            "token_hash",
            unique=True,
        ),
        Index(
            "ix_retailer_credential_setup_tokens_retailer_id",
            "retailer_id",
        ),
        Index(
            "ix_retailer_credential_setup_tokens_binding_id",
            "binding_id",
        ),
        Index(
            "ix_retailer_credential_setup_tokens_expires_at",
            "expires_at",
        ),
        Index(
            "ux_retailer_credential_setup_tokens_retailer_active",
            "retailer_id",
            unique=True,
            postgresql_where=text(
                "used_at IS NULL AND revoked_at IS NULL AND is_deleted = false"
            ),
        ),
        {"schema": "public"},
    )

    retailer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.retailers.id", ondelete="CASCADE"),
        nullable=False,
        comment="Canonical retailer identity this token provisions credentials for.",
    )
    binding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.wholesaler_retailer_bindings.id", ondelete="CASCADE"),
        nullable=False,
        comment="The wholesaler relationship (binding) that triggered this setup.",
    )
    issued_by_wholesaler_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Wholesaler that issued/reissued this token (audit only).",
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=RETAILER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
        server_default=text(f"'{RETAILER_CREDENTIAL_SETUP_TOKEN_PURPOSE}'"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RetailerPasswordResetToken(PublicBaseModel):
    """Single-use retailer password reset token metadata without raw token storage.

    Retailer-scoped (no wholesaler_id/binding_id): a reset applies to the unified
    credential across all of the retailer's wholesalers. One active token per
    retailer at a time.
    """

    __tablename__ = "retailer_password_reset_tokens"
    __table_args__ = (
        CheckConstraint(
            f"purpose = '{RETAILER_PASSWORD_RESET_TOKEN_PURPOSE}'",
            name="ck_retailer_password_reset_tokens_purpose",
        ),
        CheckConstraint(
            "used_at IS NULL OR revoked_at IS NULL",
            name="ck_retailer_password_reset_tokens_not_used_and_revoked",
        ),
        UniqueConstraint(
            "token_hash",
            name="uq_retailer_password_reset_tokens_token_hash",
        ),
        Index(
            "ux_retailer_password_reset_tokens_token_hash",
            "token_hash",
            unique=True,
        ),
        Index(
            "ix_retailer_password_reset_tokens_retailer_id",
            "retailer_id",
        ),
        Index(
            "ix_retailer_password_reset_tokens_expires_at",
            "expires_at",
        ),
        Index(
            "ux_retailer_password_reset_tokens_retailer_active",
            "retailer_id",
            unique=True,
            postgresql_where=text(
                "used_at IS NULL AND revoked_at IS NULL AND is_deleted = false"
            ),
        ),
        {"schema": "public"},
    )

    retailer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.retailers.id", ondelete="CASCADE"),
        nullable=False,
        comment="Canonical retailer identity this token resets credentials for.",
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=RETAILER_PASSWORD_RESET_TOKEN_PURPOSE,
        server_default=text(f"'{RETAILER_PASSWORD_RESET_TOKEN_PURPOSE}'"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
