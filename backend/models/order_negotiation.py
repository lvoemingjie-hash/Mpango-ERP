"""Tenant-local immutable commercial proposal and durable customer decision."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class OrderNegotiationProposal(Base):
    __tablename__ = 'order_negotiation_proposals'
    __table_args__ = (
        UniqueConstraint('source_order_id', 'version', name='uq_negotiation_source_version'),
        UniqueConstraint('accepted_order_id', name='uq_negotiation_accepted_order'),
        CheckConstraint('version > 0', name='ck_negotiation_version'),
        CheckConstraint("status IN ('pending','accepted','rejected','withdrawn')", name='ck_negotiation_status'),
        CheckConstraint(
            "(status='pending' AND decided_by IS NULL AND decided_at IS NULL "
            "AND accepted_order_id IS NULL AND accept_key_digest IS NULL AND accepted_intent_digest IS NULL) OR "
            "(status IN ('rejected','withdrawn') AND decided_by IS NOT NULL AND decided_at IS NOT NULL "
            "AND accepted_order_id IS NULL AND accept_key_digest IS NULL AND accepted_intent_digest IS NULL) OR "
            "(status='accepted' AND decided_by IS NOT NULL AND decided_at IS NOT NULL "
            "AND accepted_order_id IS NOT NULL AND accept_key_digest IS NOT NULL AND accepted_intent_digest IS NOT NULL)",
            name='ck_negotiation_decision_shape'),
        Index('ux_negotiation_pending_source', 'source_order_id', unique=True,
              postgresql_where=text("status='pending'")),
        Index('ux_negotiation_accept_key', 'wholesaler_id', 'retailer_id', 'decided_by',
              'accept_key_digest', unique=True, postgresql_where=text('accept_key_digest IS NOT NULL')),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_order_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('orders.id', ondelete='RESTRICT'), nullable=False)
    wholesaler_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    retailer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='pending')
    decided_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_order_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey('orders.id', ondelete='RESTRICT'), nullable=True)
    accept_key_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    accepted_intent_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
