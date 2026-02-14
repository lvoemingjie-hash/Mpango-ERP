"""
CRUD operations for Wholesaler model.
Operates on public schema.
"""
from typing import Optional, List, Tuple
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.wholesaler import Wholesaler


async def get_wholesaler_by_id(
    db: AsyncSession,
    wholesaler_id: str
) -> Optional[Wholesaler]:
    """
    Get wholesaler by UUID string.

    Args:
        db: Database session (public schema)
        wholesaler_id: Wholesaler UUID string

    Returns:
        Wholesaler if found, None otherwise
    """
    try:
        wholesaler_uuid = UUID(wholesaler_id)
    except ValueError:
        return None

    result = await db.execute(
        select(Wholesaler)
        .where(Wholesaler.id == wholesaler_uuid)
        .where(Wholesaler.is_deleted == False)
    )
    return result.scalar_one_or_none()


async def get_wholesaler_by_code(
    db: AsyncSession,
    code: str
) -> Optional[Wholesaler]:
    """
    Get wholesaler by tenant_code.

    Queries public.wholesalers table.
    Used during login to resolve tenant_code → tenant_id → tenant_schema.

    Args:
        db: Database session (public schema)
        code: Wholesaler code (e.g., "ACME01")

    Returns:
        Wholesaler if found, None otherwise
    """
    result = await db.execute(
        select(Wholesaler).where(Wholesaler.code == code)
    )
    return result.scalar_one_or_none()


async def get_wholesalers_paginated(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 100
) -> Tuple[List[Wholesaler], int]:
    """
    Get paginated list of wholesalers.

    Args:
        db: Database session (public schema)
        skip: Number of records to skip
        limit: Max number of records to return

    Returns:
        Tuple of (wholesalers list, total count)
    """
    base_query = select(Wholesaler).where(Wholesaler.is_deleted == False)
    count_query = select(func.count(Wholesaler.id)).where(Wholesaler.is_deleted == False)

    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    result = await db.execute(
        base_query.order_by(Wholesaler.created_at.desc()).offset(skip).limit(limit)
    )
    wholesalers = list(result.scalars().all())

    return wholesalers, total
