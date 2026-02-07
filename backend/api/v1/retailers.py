from __future__ import annotations

from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_context, get_db_session
from api.middleware.rbac import RequirePermission  # S2.5: Added RBAC import
from core.security import TokenPayload
from schemas.common import DataResponse
from schemas.retailer import (
    RetailerRegisterRequest,
    RetailerRegisterResponseData,
    RetailerData,
    BindingData,
    BindingListData,
    BindingListItem,
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
