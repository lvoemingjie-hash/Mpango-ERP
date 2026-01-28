"""Invitation model - stored in public schema."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import PublicBaseModel


class Invitation(PublicBaseModel):
    """Invitation for a retailer to register and bind to a wholesaler."""

    __tablename__ = "invitations"
    __table_args__ = (
        Index("ix_invitations_code", "code", unique=True),
        Index("ix_invitations_wholesaler_id", "wholesaler_id"),
        Index("ix_invitations_retailer_phone", "retailer_phone"),
        {"schema": "public"},
    )

    code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="Invitation code/token",
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
        comment="active|used|expired|revoked",
    )

    wholesaler_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.wholesalers.id"),
        nullable=False,
        comment="Inviting wholesaler (tenant) id",
    )

    retailer_phone: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="Optional target retailer phone",
    )

    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Optional expiration timestamp",
    )

    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when invitation was used",
    )

    used_retailer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.retailers.id"),
        nullable=True,
        comment="Retailer id that used the invitation",
    )
