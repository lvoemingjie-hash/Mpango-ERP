from __future__ import annotations

from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_context, get_db_session
from core.security import TokenPayload
from schemas.common import DataResponse
from schemas.invitation import InvitationCreateRequest, InvitationData, InvitationLookupData
from services.invitation_service import InvitationService


router = APIRouter()


def _invitation_to_data(invitation) -> InvitationData:
    return InvitationData(
        code=invitation.code,
        status=invitation.status,
        wholesaler_id=str(invitation.wholesaler_id),
        retailer_phone=invitation.retailer_phone,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


@router.post("/invitations", response_model=DataResponse[InvitationData], status_code=status.HTTP_201_CREATED)
async def create_invitation(
    request: InvitationCreateRequest,
    token: TokenPayload = Depends(get_current_user_context),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        wholesaler_id = uuid.UUID(token.tenant_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TENANT", "message": "Invalid tenant_id in token"},
        )

    service = InvitationService()
    invitation = await service.create_invitation(
        db,
        wholesaler_id=wholesaler_id,
        retailer_phone=request.retailer_phone,
        expires_at=request.expires_at,
    )

    return DataResponse(
        success=True,
        data=_invitation_to_data(invitation),
        timestamp=datetime.utcnow(),
    )


@router.get("/invitations/{code}", response_model=DataResponse[InvitationLookupData], status_code=status.HTTP_200_OK)
async def get_invitation_by_code(
    code: str,
    db: AsyncSession = Depends(get_db_session),
):
    service = InvitationService()
    invitation, usable, reason = await service.get_invitation_status(db, code=code)

    if not invitation:
        data = InvitationLookupData(code=code, usable=False, reason=reason)
        return DataResponse(success=True, data=data, timestamp=datetime.utcnow())

    wholesaler = None
    try:
        wholesaler = await service.get_wholesaler(db, wholesaler_id=invitation.wholesaler_id)
    except Exception:
        wholesaler = None

    data = InvitationLookupData(
        code=invitation.code,
        usable=usable,
        reason=reason,
        status=invitation.status,
        wholesaler_id=str(invitation.wholesaler_id),
        wholesaler_name=getattr(wholesaler, "name", None) if wholesaler else None,
        expires_at=invitation.expires_at,
    )

    return DataResponse(success=True, data=data, timestamp=datetime.utcnow())
