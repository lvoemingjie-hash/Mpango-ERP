"""Client Product API — Retailer-facing PRODUCT-LEVEL catalog browsing.

DC-12R1-MVP-L1-SKU-R0-M1-R1-R1 product-level multipackaging contract:

- List/count/page by ``catalog_products.id`` — ONE customer-visible product
  object per CatalogProduct (never one row per SKU).
- Each product carries its ACTIVE sellable units (packaging choices), each
  with its own retailer-specific price, stock enum and can_order flag.
- Tenant, retailer, stock and visibility isolation preserved (dual-key client
  identity; retailer_prices joined per bound retailer; inactive units/products
  never listed).
- Deterministic ordering: products by (name ASC, id ASC); units by
  (package_quantity ASC, sku_code ASC, sellable_unit_id ASC).
- No N+1: the list runs exactly three awaited queries (count, page of product
  ids, all unit rows for that page); detail runs exactly two (product row,
  unit rows).
- ``GET /client/products/{product_id}`` queries ``catalog_products.id`` ONLY.
  The old ambiguity (where the path id was actually matched against
  ``skus.id``) is removed — a sellable-unit UUID is a 404, never a product.

Legacy (per-SKU) response semantics are documented in
``schemas/client.py`` and the closure report.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from math import ceil
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from api.v1.client.dependencies import ClientIdentity, resolve_client_identity
from core.security import TokenPayload
from schemas.client import (
    ClientProductDetail,
    ClientProductSummary,
    ClientSellableUnitOption,
    StockLevel,
    compute_stock_level,
    product_stock_level,
)
from schemas.common import DataResponse, Pagination


router = APIRouter()


def _unit_option(row) -> ClientSellableUnitOption:
    qty = Decimal(str(row.quantity_on_hand))
    in_stock = qty > 0
    sell_price = Decimal(str(row.sell_price)) if row.sell_price is not None else None
    has_price = sell_price is not None
    return ClientSellableUnitOption(
        sellable_unit_id=str(row.unit_id),
        sku_code=row.sku_code,
        unit=row.unit,
        package_quantity=row.package_quantity,
        price=sell_price,
        in_stock=in_stock,
        stock_level=compute_stock_level(qty),
        can_order=in_stock and has_price,
    )


def _product_summary(rows, *, with_description: bool) -> ClientProductSummary | ClientProductDetail:
    """Group one product's unit rows into a single product container."""
    first = rows[0]
    units = [_unit_option(row) for row in rows]
    unit_levels = [unit.stock_level for unit in units]
    kwargs = dict(
        id=str(first.product_id),
        name=first.name,
        category=first.category,
        in_stock=any(unit.in_stock for unit in units),
        stock_level=product_stock_level(unit_levels),
        can_order=any(unit.can_order for unit in units),
        unit_count=len(units),
        units=units,
    )
    if with_description:
        return ClientProductDetail(description=first.description, **kwargs)
    return ClientProductSummary(**kwargs)


_UNIT_SELECT = """
    SELECT
        p.id AS product_id,
        p.name,
        p.description,
        p.category,
        s.id AS unit_id,
        s.sku_code,
        s.unit,
        s.package_quantity,
        COALESCE(i.quantity_on_hand, 0) AS quantity_on_hand,
        rp.price AS sell_price
    FROM catalog_products p
    JOIN skus s
        ON s.catalog_product_id = p.id
        AND s.is_active = true
        AND s.is_deleted IS NOT TRUE
    LEFT JOIN inventory_stocks i
        ON i.sku_id = s.id AND i.is_deleted IS NOT TRUE
    LEFT JOIN retailer_prices rp
        ON rp.sku_id = s.id
        AND rp.retailer_id = :retailer_id
        AND rp.is_deleted IS NOT TRUE
"""

# Deterministic unit order inside each product container.
_UNIT_ORDER = " ORDER BY s.package_quantity ASC, s.sku_code ASC, s.id ASC"

# Only products with at least one active unit are visible (the old per-SKU
# inner join implied the same visibility contract).
_VISIBLE_PRODUCT = (
    "p.is_active = true AND p.is_deleted IS NOT TRUE "
    "AND EXISTS (SELECT 1 FROM skus su WHERE su.catalog_product_id = p.id "
    "AND su.is_active = true AND su.is_deleted IS NOT TRUE)"
)


# ---------------------------------------------------------------------------
# GET /client/products — paginated PRODUCT list (one item per CatalogProduct)
# ---------------------------------------------------------------------------

@router.get("", response_model=DataResponse[dict], status_code=status.HTTP_200_OK)
async def list_products(
    page: int = Query(1, ge=1, description="Page number (over products)"),
    size: int = Query(20, ge=1, le=100, description="Products per page"),
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search by product name or unit SKU code"),
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:catalog:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Browse PRODUCTS available from this wholesaler.

    One item per CatalogProduct with its active packaging choices nested under
    ``units``. Pagination counts PRODUCTS (not units). Stock is a business-safe
    level enum; raw inventory numbers are never exposed.
    """
    conditions: list[str] = [_VISIBLE_PRODUCT]
    params: dict = {"retailer_id": client.retailer_id}

    if category:
        conditions.append("p.category = :category")
        params["category"] = category

    if search:
        conditions.append(
            "(p.name ILIKE :search OR EXISTS ("
            "SELECT 1 FROM skus ss WHERE ss.catalog_product_id = p.id "
            "AND ss.is_active = true AND ss.is_deleted IS NOT TRUE "
            "AND ss.sku_code ILIKE :search))"
        )
        params["search"] = f"%{search}%"

    where_clause = " AND ".join(conditions)

    # 1/3 — count PRODUCTS.
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM catalog_products p WHERE {where_clause}"), params
    )
    total = count_result.scalar_one()

    # 2/3 — the page's product ids (deterministic product order).
    page_ids_result = await db.execute(
        text(
            f"SELECT p.id FROM catalog_products p WHERE {where_clause} "
            "ORDER BY p.name ASC, p.id ASC OFFSET :offset LIMIT :limit"
        ),
        {**params, "offset": (page - 1) * size, "limit": size},
    )
    product_ids = [str(row.id) for row in page_ids_result.fetchall()]

    items: list[dict] = []
    if product_ids:
        # 3/3 — every unit row for exactly these products, grouped in memory.
        rows_result = await db.execute(
            text(f"{_UNIT_SELECT} WHERE p.id = ANY(:product_ids){_UNIT_ORDER}"),
            {**params, "product_ids": product_ids},
        )
        grouped: dict[str, list] = {}
        for row in rows_result.fetchall():
            grouped.setdefault(str(row.product_id), []).append(row)
        # Re-emit in the deterministic product order of the page.
        for product_id in product_ids:
            rows = grouped.get(product_id)
            if rows:
                items.append(_product_summary(rows, with_description=False).model_dump())

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
# GET /client/products/{product_id} — single PRODUCT container detail
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
    Get one product container by **CatalogProduct.id** with its active
    packaging choices.

    Never exposes cost price or raw inventory counts. An inactive or unknown
    product is a neutral 404; a sellable-unit UUID is NOT a product id and
    returns 404 (the old SKU.id ambiguity is removed).
    """
    # Fail closed on malformed ids before any SQL (a non-UUID path id can
    # never match catalog_products.id).
    try:
        UUID(str(product_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "Product not found"},
        ) from exc

    # 1/2 — the product row itself (so an all-units-inactive product still
    # yields the correct PRODUCT_INACTIVE semantics instead of a false 404).
    product_row = (
        await db.execute(
            text(
                "SELECT id, name, description, category, is_active "
                "FROM catalog_products p "
                "WHERE p.id = :product_id AND p.is_deleted IS NOT TRUE"
            ),
            {"product_id": product_id},
        )
    ).fetchone()

    if product_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "Product not found"},
        )
    if not product_row.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_INACTIVE", "message": "This product is no longer available"},
        )

    # 2/2 — its active units with per-retailer price and stock.
    rows = (
        await db.execute(
            text(f"{_UNIT_SELECT} WHERE p.id = :product_id{_UNIT_ORDER}"),
            {"product_id": product_id, "retailer_id": client.retailer_id},
        )
    ).fetchall()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "Product not found"},
        )

    detail: ClientProductDetail = _product_summary(rows, with_description=True)  # type: ignore[assignment]

    return DataResponse(
        success=True,
        data=detail,
        timestamp=datetime.utcnow(),
    )
