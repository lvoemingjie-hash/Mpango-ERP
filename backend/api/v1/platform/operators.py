"""Platform operator lifecycle routes (DC-11P2 only).

Login/JWT/guard strict-mode behavior remains unchanged for DC-11P3.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_platform_db
from api.v1.platform.p10.guard import require_platform_operator
from schemas.common import DataResponse
from schemas.platform_operator import (
    PlatformOperatorActionResponseData,
    PlatformOperatorData,
    PlatformOperatorForgotPasswordRequest,
    PlatformOperatorInviteRequest,
    PlatformOperatorResetPasswordRequest,
    PlatformOperatorSetupCredentialRequest,
)
from services.platform_operator_service import (
    EmailDeliveryNotConfiguredError,
    INVALID_OR_EXPIRED_PLATFORM_OPERATOR_TOKEN,
    NEUTRAL_PLATFORM_OPERATOR_RESET_MESSAGE,
    NEUTRAL_PLATFORM_OPERATOR_SETUP_MESSAGE,
    PlatformOperatorExistsError,
    PlatformOperatorInvalidStateError,
    PlatformOperatorNotFoundError,
    PlatformOperatorService,
    PlatformOperatorTokenInvalidError,
)


router = APIRouter(prefix="/api/v1/platform/operators", tags=["platform-operators"])


def _operator_to_data(operator) -> PlatformOperatorData:
    return PlatformOperatorData(
        id=str(operator.id),
        email=operator.email,
        status=operator.status,
        role=operator.role,
        failed_login_attempts=int(operator.failed_login_attempts or 0),
        locked_until=operator.locked_until,
        auth_version=int(operator.auth_version),
        last_login_at=operator.last_login_at,
        revoked_at=operator.revoked_at,
        invited_by=str(operator.invited_by) if operator.invited_by else None,
        created_at=operator.created_at,
        updated_at=operator.updated_at,
    )


def _reject_query_tokens(request: Request, names: set[str]) -> None:
    if any(name in request.query_params for name in names):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": INVALID_OR_EXPIRED_PLATFORM_OPERATOR_TOKEN,
                "message": NEUTRAL_PLATFORM_OPERATOR_SETUP_MESSAGE,
            },
        )


@router.post("/setup-credential", response_model=DataResponse[PlatformOperatorActionResponseData])
async def setup_platform_operator_credential(
    payload: PlatformOperatorSetupCredentialRequest,
    request: Request,
    db: AsyncSession = Depends(get_platform_db),
):
    _reject_query_tokens(request, {"setup_token", "setupToken", "password", "token"})
    service = PlatformOperatorService(db)
    try:
        result = await service.setup_credential(
            setup_token=payload.setup_token,
            password=payload.password,
        )
    except (PlatformOperatorTokenInvalidError, ValueError):
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": INVALID_OR_EXPIRED_PLATFORM_OPERATOR_TOKEN,
                "message": NEUTRAL_PLATFORM_OPERATOR_SETUP_MESSAGE,
            },
        )
    return DataResponse(
        data=PlatformOperatorActionResponseData(
            operator_id=str(result.operator_id),
            status=result.status,
        ),
        message=NEUTRAL_PLATFORM_OPERATOR_SETUP_MESSAGE,
        timestamp=datetime.utcnow(),
    )


@router.post("/forgot-password", response_model=DataResponse[PlatformOperatorActionResponseData])
async def forgot_platform_operator_password(
    payload: PlatformOperatorForgotPasswordRequest,
    db: AsyncSession = Depends(get_platform_db),
):
    service = PlatformOperatorService(db)
    try:
        await service.request_password_reset(email=payload.email)
    except EmailDeliveryNotConfiguredError:
        await db.rollback()
    except Exception:
        await db.rollback()
    return DataResponse(
        data=PlatformOperatorActionResponseData(),
        message=NEUTRAL_PLATFORM_OPERATOR_RESET_MESSAGE,
        timestamp=datetime.utcnow(),
    )


@router.post("/reset-password", response_model=DataResponse[PlatformOperatorActionResponseData])
async def reset_platform_operator_password(
    payload: PlatformOperatorResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_platform_db),
):
    _reject_query_tokens(request, {"reset_token", "resetToken", "new_password", "newPassword", "token"})
    service = PlatformOperatorService(db)
    try:
        result = await service.reset_password(
            reset_token=payload.reset_token,
            new_password=payload.new_password,
        )
    except (PlatformOperatorTokenInvalidError, ValueError):
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": INVALID_OR_EXPIRED_PLATFORM_OPERATOR_TOKEN,
                "message": NEUTRAL_PLATFORM_OPERATOR_RESET_MESSAGE,
            },
        )
    return DataResponse(
        data=PlatformOperatorActionResponseData(
            operator_id=str(result.operator_id),
            status=result.status,
        ),
        message=NEUTRAL_PLATFORM_OPERATOR_RESET_MESSAGE,
        timestamp=datetime.utcnow(),
    )


@router.get("", response_model=DataResponse[list[PlatformOperatorData]])
async def list_platform_operators(
    db: AsyncSession = Depends(get_platform_db),
    _platform_auth: None = Depends(require_platform_operator),
):
    service = PlatformOperatorService(db)
    operators = await service.list_operators()
    return DataResponse(data=[_operator_to_data(operator) for operator in operators])


@router.post("/invite", response_model=DataResponse[PlatformOperatorActionResponseData])
async def invite_platform_operator(
    payload: PlatformOperatorInviteRequest,
    db: AsyncSession = Depends(get_platform_db),
    _platform_auth: None = Depends(require_platform_operator),
):
    service = PlatformOperatorService(db)
    try:
        result = await service.invite_operator(email=payload.email, role=payload.role)
    except PlatformOperatorExistsError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "PLATFORM_OPERATOR_EXISTS", "message": "Platform operator already exists"},
        )
    except PlatformOperatorInvalidStateError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_PLATFORM_OPERATOR_STATE", "message": "Invalid platform operator request"},
        )
    except EmailDeliveryNotConfiguredError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "EMAIL_DELIVERY_NOT_CONFIGURED", "message": "Platform operator email delivery is unavailable"},
        )
    return DataResponse(
        data=PlatformOperatorActionResponseData(operator_id=str(result.operator_id), status=result.status),
        timestamp=datetime.utcnow(),
    )


@router.get("/{operator_id}", response_model=DataResponse[PlatformOperatorData])
async def get_platform_operator(
    operator_id: UUID,
    db: AsyncSession = Depends(get_platform_db),
    _platform_auth: None = Depends(require_platform_operator),
):
    service = PlatformOperatorService(db)
    try:
        operator = await service.get_operator(operator_id)
    except PlatformOperatorNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PLATFORM_OPERATOR_NOT_FOUND", "message": "Platform operator not found"},
        )
    return DataResponse(data=_operator_to_data(operator), timestamp=datetime.utcnow())


@router.post("/{operator_id}/disable", response_model=DataResponse[PlatformOperatorActionResponseData])
async def disable_platform_operator(
    operator_id: UUID,
    db: AsyncSession = Depends(get_platform_db),
    _platform_auth: None = Depends(require_platform_operator),
):
    return await _operator_action(db, operator_id, "disable")


@router.post("/{operator_id}/enable", response_model=DataResponse[PlatformOperatorActionResponseData])
async def enable_platform_operator(
    operator_id: UUID,
    db: AsyncSession = Depends(get_platform_db),
    _platform_auth: None = Depends(require_platform_operator),
):
    return await _operator_action(db, operator_id, "enable")


@router.post("/{operator_id}/revoke", response_model=DataResponse[PlatformOperatorActionResponseData])
async def revoke_platform_operator(
    operator_id: UUID,
    db: AsyncSession = Depends(get_platform_db),
    _platform_auth: None = Depends(require_platform_operator),
):
    return await _operator_action(db, operator_id, "revoke")


async def _operator_action(db: AsyncSession, operator_id: UUID, action: str):
    service = PlatformOperatorService(db)
    try:
        if action == "disable":
            result = await service.disable_operator(operator_id)
        elif action == "enable":
            result = await service.enable_operator(operator_id)
        elif action == "revoke":
            result = await service.revoke_operator(operator_id)
        else:
            raise PlatformOperatorInvalidStateError("INVALID_PLATFORM_OPERATOR_ACTION")
    except PlatformOperatorNotFoundError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PLATFORM_OPERATOR_NOT_FOUND", "message": "Platform operator not found"},
        )
    except PlatformOperatorInvalidStateError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_PLATFORM_OPERATOR_STATE", "message": "Invalid platform operator state"},
        )
    return DataResponse(
        data=PlatformOperatorActionResponseData(operator_id=str(result.operator_id), status=result.status),
        timestamp=datetime.utcnow(),
    )
