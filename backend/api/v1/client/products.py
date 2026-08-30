"""Client Product API — Retailer-facing product browsing.

CTO mandates:
- Return View Model, not DB Model
- Never expose cost_price or internal wholesaler fields
- Stock shown as level enum (LOW/MEDIUM/HIGH), not raw numbers
- can_order = is_active AND quantity_on_hand > 0
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from api.v1.client.dependencies import ClientIdentity, resolve_client_identity
from core.security import TokenPayload
from schemas.client import (
    ClientProductSummary,
    ClientProductDetail,
    StockLevel,
    compute_stock_level,
)
from schemas.common import DataResponse, Pagination


router = APIRouter()


# ---------------------------------------------------------------------------
# GET /client/products — paginated product list (active + in-stock first)
# ---------------------------------------------------------------------------

@router.get("", response_model=DataResponse[dict], status_code=status.HTTP_200_OK)
async def list_products(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search by name or SKU code"),
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:catalog:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Browse products available from this wholesaler.

    Returns UI-ready product cards with stock_level enum instead of raw
    inventory numbers. Only active products are shown.
    """
    # Build dynamic WHERE clauses
    conditions = [
        "s.is_active = true",
        "s.is_deleted IS NOT TRUE",
        "p.is_active = true",
        "p.is_deleted IS NOT TRUE",
    ]
    params: dict = {}

    if category:
        conditions.append("p.category = :category")
        params["category"] = category

    if search:
        conditions.append("(p.name ILIKE :search OR s.sku_code ILIKE :search)")
        params["search"] = f"%{search}%"

    where_clause = " AND ".join(conditions)

    # Count
    count_sql = f"SELECT COUNT(*) FROM skus s JOIN catalog_products p ON p.id = s.catalog_product_id WHERE {where_clause}"
    count_result = await db.execute(text(count_sql), params)
    total = count_result.scalar_one()

    # Paginated query — join inventory_stocks for stock, retailer_prices for price
    offset = (page - 1) * size
    data_sql = f"""
        SELECT
            s.id,
            p.id AS product_id,
            p.name,
            s.sku_code,
            p.category,
            s.unit,
            s.package_quantity,
            p.description,
            COALESCE(i.quantity_on_hand, 0) AS quantity_on_hand,
            rp.price AS sell_price
        FROM skus s
        JOIN catalog_products p ON p.id = s.catalog_product_id
        LEFT JOIN inventory_stocks i ON i.sku_id = s.id AND i.is_deleted IS NOT TRUE
        LEFT JOIN retailer_prices rp
            ON rp.sku_id = s.id
            AND rp.retailer_id = :retailer_id
            AND rp.is_deleted IS NOT TRUE
        WHERE {where_clause}
        ORDER BY COALESCE(i.quantity_on_hand, 0) DESC, p.name ASC, s.sku_code ASC
        OFFSET :offset LIMIT :limit
    """
    params["retailer_id"] = client.retailer_id
    params["offset"] = offset
    params["limit"] = size

    result = await db.execute(text(data_sql), params)
    rows = result.fetchall()

    items = []
    for row in rows:
        qty = Decimal(str(row.quantity_on_hand))
        stock_level = compute_stock_level(qty)
        in_stock = qty > 0
        sell_price = Decimal(str(row.sell_price)) if row.sell_price is not None else None
        has_price = sell_price is not None

        items.append(
            ClientProductSummary(
                id=str(row.id),
                product_id=str(row.product_id),
                catalog_product_id=str(row.product_id),
                sellable_unit_id=str(row.id),
                name=row.name,
                sku_code=row.sku_code,
                category=row.category,
                unit=row.unit,
                package_quantity=row.package_quantity,
                price=sell_price,
                in_stock=in_stock,
                stock_level=stock_level,
                can_order=in_stock and has_price,
            ).model_dump()
        )

    pages = ceil(total / size) if total > 0 else 0

    return DataResponse(
        success=True,
        data={
            "items": items,
            "pagination": Pagination(
                page=page, size=size, total=total, pages=pages
            ).model_dump(),
        },
        timestamp=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# GET /client/products/{product_id} — single product detail
# ---------------------------------------------------------------------------

@router.get(
    "/{product_id}",
    response_model=DataResponse[ClientProductDetail],
    status_code=status.HTTP_200_OK,
)
async def get_product(
    product_id: str,
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:catalog:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Get detailed product information.

    Returns description, stock level, and can_order flag.
    Never exposes cost price or raw inventory count.
    """
    sql = """
        SELECT
            s.id,
            p.id AS product_id,
            p.name,
            s.sku_code,
            p.description,
            p.category,
            s.unit,
            s.package_quantity,
            (s.is_active AND p.is_active) AS is_active,
            COALESCE(i.quantity_on_hand, 0) AS quantity_on_hand,
            rp.price AS sell_price
        FROM skus s
        JOIN catalog_products p ON p.id = s.catalog_product_id AND p.is_deleted IS NOT TRUE
        LEFT JOIN inventory_stocks i ON i.sku_id = s.id AND i.is_deleted IS NOT TRUE
        LEFT JOIN retailer_prices rp
            ON rp.sku_id = s.id
            AND rp.retailer_id = :retailer_id
            AND rp.is_deleted IS NOT TRUE
        WHERE s.id = :product_id
          AND s.is_deleted IS NOT TRUE
        LIMIT 1
    """
    result = await db.execute(text(sql), {"product_id": product_id, "retailer_id": client.retailer_id})
    row = result.fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "Product not found"},
        )

    if not row.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_INACTIVE", "message": "This product is no longer available"},
        )

    qty = Decimal(str(row.quantity_on_hand))
    stock_level = compute_stock_level(qty)
    in_stock = qty > 0
    sell_price = Decimal(str(row.sell_price)) if row.sell_price is not None else None
    has_price = sell_price is not None

    detail = ClientProductDetail(
        id=str(row.id),
        product_id=str(row.product_id),
        catalog_product_id=str(row.product_id),
        sellable_unit_id=str(row.id),
        name=row.name,
        sku_code=row.sku_code,
        description=row.description,
        category=row.category,
        unit=row.unit,
        package_quantity=row.package_quantity,
        price=sell_price,
        in_stock=in_stock,
        stock_level=stock_level,
        can_order=in_stock and has_price,
    )

    return DataResponse(
        success=True,
        data=detail,
        timestamp=datetime.utcnow(),
    )
