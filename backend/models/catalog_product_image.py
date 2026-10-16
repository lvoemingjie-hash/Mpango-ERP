"""Tenant-local current media pointer and durable deletion revision."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, UserTrackingMixin


class CatalogProductImage(Base, UserTrackingMixin):
    __tablename__ = 'catalog_product_images'
    __table_args__ = (
        CheckConstraint('image_revision >= 1', name='ck_product_image_revision'),
        CheckConstraint('(current_version IS NULL) = (variants IS NULL)', name='ck_product_image_shape'),
    )

    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('catalog_products.id', name='fk_product_image_product', ondelete='RESTRICT'), primary_key=True)
    image_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    current_version: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    variants: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    product = relationship('CatalogProduct', back_populates='image_record', lazy='raise')
