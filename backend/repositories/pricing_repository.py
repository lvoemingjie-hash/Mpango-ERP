"""
Pricing repository — tenant-scoped retailer price lookups.

Phase 3 MVP: simple retailer_id + sku_id → price resolution.
All functions operate within the tenant session's search_path.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.retailer_price import RetailerPrice
from models.sku import SKU
from services.package_identity import lock_sku_row


def effective_price(base, override):
    """Shared price precedence. An override cannot complete a missing base."""
    if base is None:
        return None, None, 'BASE_PRICE_REQUIRED'
    if not Decimal(str(base)).is_finite() or Decimal(str(base)) <= 0:
        return None, None, 'PRICE_DATA_INTEGRITY_RED'
    value = override if override is not None else base
    if not Decimal(str(value)).is_finite() or Decimal(str(value)) <= 0:
        return None, None, 'PRICE_DATA_INTEGRITY_RED'
    return Decimal(str(value)), 'RETAILER_OVERRIDE' if override is not None else 'BASE_PRICE', None


async def get_price(
    db: AsyncSession,
    retailer_id: UUID,
    sku_id: UUID,
) -> Optional[Decimal]:
    """Get the sell price for a single retailer+SKU combination."""
    return (await get_prices_bulk(db, retailer_id, [sku_id])).get(sku_id)


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
        select(SKU.id, SKU.base_price, RetailerPrice.price)
        .outerjoin(RetailerPrice, and_(RetailerPrice.sku_id == SKU.id,
                    RetailerPrice.retailer_id == retailer_id, RetailerPrice.is_deleted.is_(False)))
        .where(SKU.id.in_(sku_ids), SKU.is_deleted.is_(False))
    )
    prices = {}
    for row in result.fetchall():
        value, _, reason = effective_price(row.base_price, row.price)
        if not reason:
            prices[row.id] = value
    return prices


async def set_price(
    db: AsyncSession,
    retailer_id: UUID,
    sku_id: UUID,
    price: Decimal,
    updated_by: Optional[UUID] = None,
    expected_revision: Optional[int] = None,
    retire: bool = False,
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
    # definition. Retirement changes state, never the retained price amount.
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

    from services.pricing_quote_service import money, resolve_currency, refuse
    source = await resolve_currency(db)
    if expected_revision is not None and locked.pricing_revision != expected_revision:
        refuse('PRICE_VERSION_CONFLICT', 'Reload the price before editing')
    result = await db.execute(
        select(RetailerPrice)
        .where(
            and_(
                RetailerPrice.retailer_id == retailer_id,
                RetailerPrice.sku_id == sku_id,
            )
        )
    )
    existing = result.scalar_one_or_none()

    if retire:
        if existing is None:
            refuse('PRICE_OVERRIDE_NOT_FOUND', 'There is no override to retire', status=404)
        if Decimal(str(price)) != existing.price:
            refuse('PRICE_RETIRE_AMOUNT_MISMATCH', 'Retirement must preserve the retained amount')
    else:
        price = money(price, source.currency)

    if existing:
        if not retire:
            existing.price = price
        existing.is_deleted = retire
        existing.deleted_at = datetime.now(timezone.utc) if retire else None
        if updated_by:
            existing.updated_by = updated_by
        locked.pricing_revision += 1
        await db.flush()
        return existing

    record = RetailerPrice(
        retailer_id=retailer_id,
        sku_id=sku_id,
        price=price,
        created_by=updated_by,
        is_deleted=retire,
    )
    db.add(record)
    locked.pricing_revision += 1
    await db.flush()
    return record


async def set_base_price(db, *, sku_id, price, expected_revision, actor_id):
    from services.pricing_quote_service import money, resolve_currency, refuse
    sku = await lock_sku_row(db, sku_id=sku_id)
    if sku is None:
        refuse('SKU_NOT_FOUND', 'Sellable unit not found', status=404)
    source = await resolve_currency(db)
    if sku.pricing_revision != expected_revision:
        refuse('PRICE_VERSION_CONFLICT', 'Reload the price before editing')
    sku.base_price = money(price, source.currency)
    sku.pricing_revision += 1
    sku.updated_by = actor_id
    await db.flush()
    return sku
