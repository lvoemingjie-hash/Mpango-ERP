"""Retailer model - Global customer registry in public schema."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Index, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from models.base import PublicBaseModel


class Retailer(PublicBaseModel):
    """Retailer model stored in public schema."""

    __tablename__ = "retailers"
    __table_args__ = (
        Index("ix_retailers_phone", "phone", unique=True),
        {"schema": "public"},
    )

    phone: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        index=True,
        comment="Retailer phone number (global unique)",
    )
    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Retailer display name",
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Retailer canonical email (retailer-owned credential-delivery address)",
    )
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment=(
            "DC-12R1-S1: timestamp the canonical email was verified (set when the "
            "retailer consumes a credential setup token). NULL until verified. "
            "Wholesalers cannot change this after verification."
        ),
    )
    address: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Retailer address",
    )
