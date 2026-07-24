from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_context, get_db_session
from api.middleware.rbac import RequirePermission  # S2.5: Added RBAC import
from core.security import TokenPayload
from db.tenant_filter import run_as_system
from models.invitation import Invitation
from repositories.invitation_repository import InvitationRepository
from schemas.common import DataResponse
from schemas.invitation import InvitationCreateRequest, InvitationData, InvitationLookupData
from schemas.retailer_credentials import (
    InvitationLookupRequest,
    InvitationRevokeRequest,
)
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
    token: TokenPayload = Depends(RequirePermission("invitations:create")),  # S2.5: Added RBAC
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


@router.post(
    "/invitations/lookup",
    response_model=DataResponse[InvitationLookupData],
    status_code=status.HTTP_200_OK,
)
async def lookup_invitation(
    request: InvitationLookupRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """JSON-body invitation preflight (DC-12R1-S1, replaces path-token lookup).

    The code arrives in the request body only — no token in the URL path/query.
    Returns the same neutral shape as the legacy GET lookup.
    """
    service = InvitationService()
    invitation, usable, reason = await service.get_invitation_status(db, code=request.code)
    if not invitation:
        data = InvitationLookupData(code=request.code, usable=False, reason=reason)
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


@router.get("/invitations/{code}", response_model=DataResponse[InvitationLookupData], status_code=status.HTTP_200_OK, deprecated=True)
async def get_invitation_by_code(
    code: str,
    db: AsyncSession = Depends(get_db_session),
):
    """DEPRECATED (DC-12R1-S1): path-token preflight. Prefer POST /invitations/lookup.

    Retained for the existing InvitePage consumer; no new frontend/email should
    use it. The token travels in the URL path (server log exposure) which is why
    the JSON-body lookup endpoint is preferred.
    """
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


# ---------------------------------------------------------------------------
# POST /invitations/{invitation_id}/revoke  (DC-12R1-S1 tenant-scoped revoke)
# ---------------------------------------------------------------------------


@router.post(
    "/invitations/{invitation_id}/revoke",
    response_model=DataResponse[InvitationData],
    status_code=status.HTTP_200_OK,
)
async def revoke_invitation(
    invitation_id: str,
    request: InvitationRevokeRequest,
    token: TokenPayload = Depends(RequirePermission("invitations:revoke")),
    db: AsyncSession = Depends(get_db_session),
):
    """Revoke an outstanding invitation (DC-12R1-S1 F-04).

    Tenant-scoped: only the inviting wholesaler
    (invitation.wholesaler_id == token.tenant_id) may revoke. Cross-tenant
    access returns a neutral 404. Idempotent for an already-used/revoked
    invitation.
    """
    try:
        invitation_uuid = uuid.UUID(invitation_id)
        wholesaler_id = uuid.UUID(token.tenant_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "INVITATION_NOT_FOUND", "message": "Invitation not found"},
        )

    repo = InvitationRepository()
    with run_as_system(reason="invitation_revoke"):
        invitation = await repo.get_by_id(db, invitation_id=invitation_uuid)
        if invitation is None or invitation.wholesaler_id != wholesaler_id:
            # Neutral 404 — do not disclose the invitation exists for another tenant.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "INVITATION_NOT_FOUND",
                    "message": "Invitation not found",
                },
            )
        await repo.revoke(
            db,
            invitation_id=invitation_uuid,
            revoked_by=uuid.UUID(token.user_id) if token.user_id else wholesaler_id,
            revoked_at=datetime.now(timezone.utc),
        )
        await db.commit()
        await db.refresh(invitation)

    return DataResponse(
        success=True,
        data=_invitation_to_data(invitation),
        timestamp=datetime.utcnow(),
    )
