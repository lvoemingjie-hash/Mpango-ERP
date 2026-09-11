"""Wholesaler catalog-product API."""

from __future__ import annotations

from datetime import datetime
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from schemas.catalog import (
    CatalogProductCreate,
    CatalogProductRead,
    CatalogProductUpdate,
    SellableUnitCreate,
    SellableUnitRead,
    SellableUnitUpdate,
)
from schemas.common import DataResponse, Pagination
from services.catalog_product_service import CatalogProductService


router = APIRouter()


def _to_read(product) -> CatalogProductRead:
    units = [
        SellableUnitRead(
            id=str(unit.id),
            catalog_product_id=str(unit.catalog_product_id),
            sku_code=unit.sku_code,
            unit=unit.unit,
            package_quantity=unit.package_quantity,
            is_active=unit.is_active,
            created_at=unit.created_at,
            updated_at=unit.updated_at,
        )
        for unit in sorted(product.sellable_units, key=lambda item: (item.sku_code, str(item.id)))
        if not unit.is_deleted
    ]
    return CatalogProductRead(
        id=str(product.id),
        name=product.name,
        description=product.description,
        category=product.category,
        is_active=product.is_active,
        sellable_units=units,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.get("", response_model=DataResponse[dict])
async def list_catalog_products(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    q: Optional[str] = Query(None),
    token: TokenPayload = Depends(RequirePermission("skus:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    products, total = await CatalogProductService().list_products(
        db, page=page, size=size, is_active=is_active, q=q
    )
    return DataResponse(
        success=True,
        data={
            "items": [_to_read(product) for product in products],
            "pagination": Pagination(
                page=page, size=size, total=total, pages=ceil(total / size) if total else 0
            ).model_dump(),
        },
        timestamp=datetime.utcnow(),
    )


@router.post("", response_model=DataResponse[CatalogProductRead], status_code=status.HTTP_201_CREATED)
async def create_catalog_product(
    request: CatalogProductCreate,
    token: TokenPayload = Depends(RequirePermission("skus:create")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    product = await CatalogProductService().create_product(db, request=request, actor_id=token.user_id)
    return DataResponse(success=True, data=_to_read(product), timestamp=datetime.utcnow())


@router.get("/{product_id}", response_model=DataResponse[CatalogProductRead])
async def get_catalog_product(
    product_id: str,
    token: TokenPayload = Depends(RequirePermission("skus:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    product = await CatalogProductService().get_product(db, product_id=product_id)
    return DataResponse(success=True, data=_to_read(product), timestamp=datetime.utcnow())


@router.put("/{product_id}", response_model=DataResponse[CatalogProductRead])
async def update_catalog_product(
    product_id: str,
    request: CatalogProductUpdate,
    token: TokenPayload = Depends(RequirePermission("skus:update")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    product = await CatalogProductService().update_product(
        db, product_id=product_id, request=request, actor_id=token.user_id
    )
    return DataResponse(success=True, data=_to_read(product), timestamp=datetime.utcnow())


@router.post("/{product_id}/sellable-units", response_model=DataResponse[CatalogProductRead], status_code=status.HTTP_201_CREATED)
async def add_sellable_unit(
    product_id: str,
    request: SellableUnitCreate,
    token: TokenPayload = Depends(RequirePermission("skus:create")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    product = await CatalogProductService().add_sellable_unit(
        db, product_id=product_id, request=request, actor_id=token.user_id
    )
    return DataResponse(success=True, data=_to_read(product), timestamp=datetime.utcnow())


@router.put("/{product_id}/sellable-units/{sellable_unit_id}", response_model=DataResponse[CatalogProductRead])
async def update_sellable_unit(
    product_id: str,
    sellable_unit_id: str,
    request: SellableUnitUpdate,
    token: TokenPayload = Depends(RequirePermission("skus:update")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    product = await CatalogProductService().update_sellable_unit(
        db,
        product_id=product_id,
        sellable_unit_id=sellable_unit_id,
        request=request,
        actor_id=token.user_id,
    )
    return DataResponse(success=True, data=_to_read(product), timestamp=datetime.utcnow())
