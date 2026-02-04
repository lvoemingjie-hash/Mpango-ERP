"""
CRUD operations for Wholesaler model.
Operates on public schema.
"""
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.wholesaler import Wholesaler


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
