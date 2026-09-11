"""
Pricing repository — tenant-scoped retailer price lookups.

Phase 3 MVP: simple retailer_id + sku_id → price resolution.
All functions operate within the tenant session's search_path.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.retailer_price import RetailerPrice
from services.package_identity import lock_sku_row


async def get_price(
    db: AsyncSession,
    retailer_id: UUID,
    sku_id: UUID,
) -> Optional[Decimal]:
    """Get the sell price for a single retailer+SKU combination."""
    result = await db.execute(
        select(RetailerPrice.price)
        .where(
            and_(
                RetailerPrice.retailer_id == retailer_id,
                RetailerPrice.sku_id == sku_id,
                RetailerPrice.is_deleted == False,
            )
        )
    )
    row = result.scalar_one_or_none()
    return row


async def get_prices_bulk(
    db: AsyncSession,
    retailer_id: UUID,
    sku_ids: List[UUID],
) -> Dict[UUID, Decimal]:
    """
    Bulk-fetch sell prices for a retailer across multiple SKUs.

    Returns:
        Dict mapping sku_id → price. Missing SKUs are absent from the dict.
    """
    if not sku_ids:
        return {}

    result = await db.execute(
        select(RetailerPrice.sku_id, RetailerPrice.price)
        .where(
            and_(
                RetailerPrice.retailer_id == retailer_id,
                RetailerPrice.sku_id.in_(sku_ids),
                RetailerPrice.is_deleted == False,
            )
        )
    )
    return {row.sku_id: row.price for row in result.fetchall()}


async def set_price(
    db: AsyncSession,
    retailer_id: UUID,
    sku_id: UUID,
    price: Decimal,
    updated_by: Optional[UUID] = None,
) -> RetailerPrice:
    """
    Set or update the sell price for a retailer+SKU combination.

    Uses upsert semantics: creates if not exists, updates if exists.
    """
    # BC06-R1/R2-R1: take the SAME skus row lock as the package_quantity
    # modification entries, creating one deterministic serialization order:
    # a price committed before a repackaging attempt makes that attempt
    # return SKU_PACKAGE_QUANTITY_REPRICE_REQUIRED / 409; a repackaging
    # committed first means this price simply applies to the new package
    # definition. No price rows are ever deleted or retired here.
    # R2-R1: the lock's return is load-bearing — a SKU that is missing or
    # concurrently soft-deleted as of lock acquisition fails closed with the
    # structured Not Found semantics and ZERO price writes; this backstop
    # holds even when callers skip their own prechecks.
    locked = await lock_sku_row(db, sku_id=sku_id)
    if locked is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SKU_NOT_FOUND", "message": f"SKU '{sku_id}' not found"},
        )

    result = await db.execute(
        select(RetailerPrice)
        .where(
            and_(
                RetailerPrice.retailer_id == retailer_id,
                RetailerPrice.sku_id == sku_id,
                RetailerPrice.is_deleted == False,
            )
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.price = price
        if updated_by:
            existing.updated_by = updated_by
        await db.flush()
        return existing

    record = RetailerPrice(
        retailer_id=retailer_id,
        sku_id=sku_id,
        price=price,
        created_by=updated_by,
    )
    db.add(record)
    await db.flush()
    return record
