from __future__ import annotations

from datetime import datetime
from math import ceil
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_context, get_db_session
from api.middleware.rbac import RequirePermission  # S2.5: Added RBAC import
from core.security import TokenPayload
from schemas.common import DataResponse, Pagination
from schemas.retailer import (
    RetailerRegisterRequest,
    RetailerRegisterResponseData,
    RetailerData,
    BindingData,
    BindingListData,
    BindingListItem,
    RetailerWithBinding,
    RetailerListData,
)
from services.retailer_service import RetailerService


router = APIRouter()


def _retailer_to_data(retailer) -> RetailerData:
    return RetailerData(
        id=str(retailer.id),
        phone=retailer.phone,
        name=retailer.name,
        email=retailer.email,
        address=retailer.address,
    )


def _binding_to_data(binding) -> BindingData:
    return BindingData(
        id=str(binding.id),
        wholesaler_id=str(binding.wholesaler_id),
        retailer_id=str(binding.retailer_id),
        status=binding.status,
        created_at=binding.created_at,
    )


@router.post(
    "/retailers/register",
    response_model=DataResponse[RetailerRegisterResponseData],
    status_code=status.HTTP_201_CREATED,
)
async def register_retailer_with_invitation(
    request: RetailerRegisterRequest,
    db: AsyncSession = Depends(get_db_session),
):
    service = RetailerService()
    invitation, retailer, binding, error_code = await service.register_with_invitation(
        db,
        invitation_code=request.invitation_code,
        phone=request.phone,
        name=request.name,
        email=request.email,
        address=request.address,
    )

    if error_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": error_code, "message": "Invitation registration failed"},
        )

    data = RetailerRegisterResponseData(
        retailer=_retailer_to_data(retailer),
        binding=_binding_to_data(binding),
    )

    return DataResponse(success=True, data=data, timestamp=datetime.utcnow())


@router.get(
    "/retailers/bindings",
    response_model=DataResponse[BindingListData],
    status_code=status.HTTP_200_OK,
)
async def list_bindings_for_current_wholesaler(
    token: TokenPayload = Depends(RequirePermission("retailers:read")),  # S2.5: Added RBAC
    db: AsyncSession = Depends(get_db_session),
):
    try:
        wholesaler_id = uuid.UUID(token.tenant_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TENANT", "message": "Invalid tenant_id in token"},
        )

    service = RetailerService()
    bindings_with_retailers = await service.list_bindings_with_retailers(db, wholesaler_id=wholesaler_id)

    items: list[BindingListItem] = []
    for binding, retailer in bindings_with_retailers:
        items.append(
            BindingListItem(
                binding=_binding_to_data(binding),
                retailer=_retailer_to_data(retailer) if retailer else None,
            )
        )

    return DataResponse(success=True, data=BindingListData(items=items), timestamp=datetime.utcnow())


@router.get(
    "/retailers",
    response_model=DataResponse[RetailerListData],
    status_code=status.HTTP_200_OK,
)
async def list_retailers(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    token: TokenPayload = Depends(RequirePermission("retailers:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """
    List retailers bound to the current wholesaler (CRM list).

    Returns paginated retailer records with binding metadata.
    """
    try:
        wholesaler_id = uuid.UUID(token.tenant_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TENANT", "message": "Invalid tenant_id in token"},
        )

    service = RetailerService()
    results, total = await service.list_retailers_for_wholesaler(
        db, wholesaler_id=wholesaler_id, page=page, size=size
    )

    pages = ceil(total / size) if total > 0 else 0
    items = [
        RetailerWithBinding(
            retailer=_retailer_to_data(retailer),
            binding_status=binding.status,
            bound_at=binding.created_at,
        )
        for retailer, binding in results
    ]

    data = RetailerListData(
        items=items,
        pagination=Pagination(page=page, size=size, total=total, pages=pages).model_dump(),
    )
    return DataResponse(success=True, data=data, timestamp=datetime.utcnow())


@router.get(
    "/retailers/{retailer_id}",
    response_model=DataResponse[RetailerWithBinding],
    status_code=status.HTTP_200_OK,
)
async def get_retailer(
    retailer_id: str,
    token: TokenPayload = Depends(RequirePermission("retailers:read")),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get a single retailer's detail (must be bound to current wholesaler).
    """
    try:
        wholesaler_id = uuid.UUID(token.tenant_id)
        retailer_uuid = uuid.UUID(retailer_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_ID", "message": "Invalid UUID format"},
        )

    service = RetailerService()
    result = await service.get_retailer_for_wholesaler(
        db, wholesaler_id=wholesaler_id, retailer_id=retailer_uuid
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RETAILER_NOT_FOUND",
                "message": f"Retailer '{retailer_id}' not found or not bound to your business",
            },
        )

    retailer, binding = result
    data = RetailerWithBinding(
        retailer=_retailer_to_data(retailer),
        binding_status=binding.status,
        bound_at=binding.created_at,
    )
    return DataResponse(success=True, data=data, timestamp=datetime.utcnow())
