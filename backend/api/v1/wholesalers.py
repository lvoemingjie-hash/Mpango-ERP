"""
Wholesaler (Tenant registry) API endpoints.
Operates on public schema.
"""
from __future__ import annotations

from datetime import datetime
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from crud.crud_wholesaler import wholesaler as wholesaler_crud
from crud.wholesaler import get_wholesaler_by_id, get_wholesalers_paginated
from models.wholesaler import Wholesaler
from schemas.common import MessageResponse, Pagination
from schemas.wholesaler import (
    WholesalerCreate,
    WholesalerUpdate,
    WholesalerRead,
    WholesalerResponse,
    WholesalerListResponse,
)

router = APIRouter()


def wholesaler_to_read(obj: Wholesaler) -> WholesalerRead:
    return WholesalerRead(
        id=str(obj.id),
        code=obj.code,
        name=obj.name,
        address=obj.address,
        contact=obj.contact,
        plan_type=obj.plan_type,
        schema_name=obj.get_tenant_schema(),
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


@router.get("", response_model=WholesalerListResponse, status_code=status.HTTP_200_OK)
async def list_wholesalers(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=100, description="Max records to return"),
    page: int | None = Query(None, ge=1, description="Page number (1-based)"),
    size: int | None = Query(None, ge=1, le=100, description="Items per page"),
    token: TokenPayload = Depends(RequirePermission("wholesalers:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """
    List wholesalers with pagination.

    Returns WholesalerListResponse with items and pagination.
    """
    effective_limit = size or limit
    effective_skip = (page - 1) * effective_limit if page else skip

    wholesalers, total = await get_wholesalers_paginated(
        db,
        skip=effective_skip,
        limit=effective_limit,
    )
    computed_page = (effective_skip // effective_limit) + 1 if effective_limit > 0 else 1
    pages = ceil(total / effective_limit) if total > 0 else 0

    return WholesalerListResponse(
        success=True,
        data={
            "items": [wholesaler_to_read(w) for w in wholesalers],
            "pagination": Pagination(
                page=computed_page,
                size=effective_limit,
                total=total,
                pages=pages,
            ).model_dump(),
        },
        timestamp=datetime.utcnow(),
    )


@router.post("", response_model=WholesalerResponse, status_code=status.HTTP_201_CREATED)
async def create_wholesaler(
    request: WholesalerCreate,
    token: TokenPayload = Depends(RequirePermission("wholesalers:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Create a public-schema wholesaler registry record only.

    This does not provision tenant schema, login, admin user, RBAC, inventory,
    orders, or finance workspace. Full tenant onboarding remains a separate
    operator-controlled bootstrap flow.
    """
    existing = await db.execute(
        Wholesaler.__table__.select().where(
            (Wholesaler.code == request.code) & (Wholesaler.is_deleted == False)
        )
    )
    if existing.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "WHOLESALER_CODE_EXISTS",
                "message": f"Wholesaler code '{request.code}' already exists",
            },
        )

    created = await wholesaler_crud.create(db, obj_in=request)

    return WholesalerResponse(
        success=True,
        data=wholesaler_to_read(created),
        message=(
            "Registry record created only; tenant schema, login, admin user, "
            "RBAC, inventory, orders, and finance workspace were not provisioned."
        ),
        timestamp=datetime.utcnow(),
    )


@router.get("/{wholesaler_id}", response_model=WholesalerResponse, status_code=status.HTTP_200_OK)
async def get_wholesaler(
    wholesaler_id: str,
    token: TokenPayload = Depends(RequirePermission("wholesalers:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get wholesaler by ID.
    """
    wholesaler = await get_wholesaler_by_id(db, wholesaler_id)
    if not wholesaler:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "WHOLESALER_NOT_FOUND", "message": "Wholesaler not found"},
        )

    return WholesalerResponse(
        success=True,
        data=wholesaler_to_read(wholesaler),
        timestamp=datetime.utcnow(),
    )


@router.put("/{wholesaler_id}", response_model=WholesalerResponse, status_code=status.HTTP_200_OK)
async def update_wholesaler(
    wholesaler_id: str,
    request: WholesalerUpdate,
    token: TokenPayload = Depends(RequirePermission("wholesalers:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Update wholesaler by ID.
    """
    db_obj = await get_wholesaler_by_id(db, wholesaler_id)
    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "WHOLESALER_NOT_FOUND", "message": "Wholesaler not found"},
        )

    updated = await wholesaler_crud.update(db, db_obj=db_obj, obj_in=request)

    return WholesalerResponse(
        success=True,
        data=wholesaler_to_read(updated),
        timestamp=datetime.utcnow(),
    )


@router.delete("/{wholesaler_id}", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def delete_wholesaler(
    wholesaler_id: str,
    token: TokenPayload = Depends(RequirePermission("wholesalers:write")),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Soft-delete wholesaler by ID.
    """
    db_obj = await get_wholesaler_by_id(db, wholesaler_id)
    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "WHOLESALER_NOT_FOUND", "message": "Wholesaler not found"},
        )

    try:
        wholesaler_uuid = UUID(wholesaler_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_ID", "message": "Invalid wholesaler id"},
        )

    removed = await wholesaler_crud.remove(db, id=wholesaler_uuid)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "WHOLESALER_NOT_FOUND", "message": "Wholesaler not found"},
        )

    return MessageResponse(message="Wholesaler deleted", timestamp=datetime.utcnow())
