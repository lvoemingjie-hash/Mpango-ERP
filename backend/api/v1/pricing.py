"""
Admin Pricing API — Wholesaler-facing retailer price management.
Phase 4: Thin API layer over existing pricing_repository.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from repositories.pricing_repository import set_price
from schemas.common import DataResponse

router = APIRouter()


# -- Schemas --

class RetailerPriceView(BaseModel):
    sku_id: str
    sku_code: str
    sku_name: str
    retailer_id: str
    price: Decimal
    updated_at: datetime | None = None
    model_config = {"from_attributes": True}


class RetailerPriceListData(BaseModel):
    items: List[RetailerPriceView]
    total: int


class SetPriceRequest(BaseModel):
    retailer_id: str = Field(..., min_length=36, max_length=36)
    sku_id: str = Field(..., min_length=36, max_length=36)
    price: Decimal = Field(..., gt=0, le=Decimal("999999.99"))

    @field_validator("price")
    @classmethod
    def validate_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Price must be > 0")
        return v
    model_config = {"from_attributes": True}


class SetPriceResponse(BaseModel):
    sku_id: str
    retailer_id: str
    price: Decimal
    action: str


# -- Endpoints --

@router.get("/prices", response_model=DataResponse[RetailerPriceListData])
async def list_retailer_prices(
    retailer_id: str = Query(..., min_length=36, max_length=36),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    token: TokenPayload = Depends(RequirePermission("pricing:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """List retailer-specific prices for a given retailer within this tenant."""
    await _assert_binding(db, token.tenant_id, retailer_id)

    count_result = await db.execute(
        text(
            "SELECT COUNT(*) FROM retailer_prices rp "
            "JOIN skus s ON s.id = rp.sku_id AND s.is_deleted IS NOT TRUE "
            "WHERE rp.retailer_id = :rid AND rp.is_deleted IS NOT TRUE"
        ),
        {"rid": retailer_id},
    )
    total = count_result.scalar_one()

    offset = (page - 1) * size
    rows = await db.execute(
        text(
            "SELECT rp.sku_id, s.sku_code, s.name AS sku_name, "
            "  rp.retailer_id, rp.price, rp.updated_at "
            "FROM retailer_prices rp "
            "JOIN skus s ON s.id = rp.sku_id AND s.is_deleted IS NOT TRUE "
            "WHERE rp.retailer_id = :rid AND rp.is_deleted IS NOT TRUE "
            "ORDER BY s.name ASC OFFSET :off LIMIT :lim"
        ),
        {"rid": retailer_id, "off": offset, "lim": size},
    )
    items = [
        RetailerPriceView(
            sku_id=str(r.sku_id), sku_code=r.sku_code, sku_name=r.sku_name,
            retailer_id=str(r.retailer_id), price=r.price, updated_at=r.updated_at,
        )
        for r in rows.fetchall()
    ]

    return DataResponse(
        success=True,
        data=RetailerPriceListData(items=items, total=total),
        timestamp=datetime.utcnow(),
    )


@router.put("/prices", response_model=DataResponse[SetPriceResponse])
async def set_retailer_price(
    request: SetPriceRequest,
    token: TokenPayload = Depends(RequirePermission("pricing:write")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """Set or update a retailer-specific price for a SKU."""
    await _assert_binding(db, token.tenant_id, request.retailer_id)

    # Verify SKU exists
    sku_check = await db.execute(
        text("SELECT id FROM skus WHERE id = :sid AND is_deleted IS NOT TRUE LIMIT 1"),
        {"sid": request.sku_id},
    )
    if sku_check.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SKU_NOT_FOUND", "message": f"SKU '{request.sku_id}' not found"},
        )

    # Check if price already exists to determine action label
    existing = await db.execute(
        text(
            "SELECT id FROM retailer_prices "
            "WHERE retailer_id = :rid AND sku_id = :sid AND is_deleted IS NOT TRUE LIMIT 1"
        ),
        {"rid": request.retailer_id, "sid": request.sku_id},
    )
    action = "updated" if existing.fetchone() is not None else "created"

    await set_price(
        db=db,
        retailer_id=UUID(request.retailer_id),
        sku_id=UUID(request.sku_id),
        price=request.price,
        updated_by=UUID(token.user_id),
    )

    return DataResponse(
        success=True,
        data=SetPriceResponse(
            sku_id=request.sku_id,
            retailer_id=request.retailer_id,
            price=request.price,
            action=action,
        ),
        message=f"Price {action} successfully",
        timestamp=datetime.utcnow(),
    )


async def _assert_binding(db: AsyncSession, tenant_id: str, retailer_id: str) -> None:
    """Verify retailer is actively bound to this tenant. Raises 400 if not."""
    result = await db.execute(
        text(
            "SELECT id FROM public.wholesaler_retailer_bindings "
            "WHERE wholesaler_id = :tid AND retailer_id = :rid AND status = 'active' LIMIT 1"
        ),
        {"tid": tenant_id, "rid": retailer_id},
    )
    if result.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "RETAILER_NOT_BOUND", "message": "Retailer not bound to this wholesaler"},
        )
