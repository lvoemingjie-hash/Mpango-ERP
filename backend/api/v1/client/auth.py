"""Client Auth API — Retailer self-service credential recovery (DC-12R1-S1).

Public endpoints (no auth dependency) for retailer forgot-password /
reset-password. Both are strictly neutral: no-account / unverified-email /
wrong-wholesaler-code / SMTP-failure all return the identical response.
Tokens arrive ONLY in the JSON body; query-string token/password params are
rejected before any service work.

NOTE: the supplier-scoped retailer LOGIN endpoint is S2 and is intentionally
NOT implemented here.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session
from schemas.retailer_credentials import (
    RetailerCredentialResponse,
    RetailerCredentialResponseData,
    RetailerForgotPasswordRequest,
    RetailerResetPasswordRequest,
)
from services.email_delivery import EmailDeliveryNotConfiguredError
from services.retailer_provisioning_service import (
    RESET_TOKEN_INVALID,
    RetailerCredentialTokenInvalidError,
    RetailerProvisioningService,
)

router = APIRouter()

NEUTRAL_RETAILER_CREDENTIAL_MESSAGE = (
    "Retailer credential result is not disclosed through this endpoint."
)


def _reject_query_token(http_request: Request, keys: tuple[str, ...]) -> None:
    """Reject any sensitive value in the query string (anti-leakage)."""
    if http_request is not None and any(k in http_request.query_params for k in keys):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": RESET_TOKEN_INVALID,
                "message": NEUTRAL_RETAILER_CREDENTIAL_MESSAGE,
            },
        )


@router.post(
    "/forgot-password",
    response_model=RetailerCredentialResponse,
    status_code=status.HTTP_200_OK,
)
async def retailer_forgot_password(
    request: RetailerForgotPasswordRequest,
    db: AsyncSession = Depends(get_db_session),
    http_request: Request = None,
):
    """Request a retailer password-reset link.

    Always returns a neutral 200. A reset token is issued only when a verified
    retailer with an established password exists for the (email, wholesaler_code)
    pair. Production fails closed: SMTP failure rolls back the token and the
    response stays identical to the no-match case. No raw email/token/link is
    logged.
    """
    _reject_query_token(http_request, ("email", "wholesaler_code", "token"))
    service = RetailerProvisioningService(db)
    try:
        await service.request_password_reset(
            email=request.email, wholesaler_code=request.wholesaler_code
        )
    except EmailDeliveryNotConfiguredError:
        await db.rollback()
    except Exception:
        # Never leak account existence; respond neutral.
        await db.rollback()
    return RetailerCredentialResponse(
        data=RetailerCredentialResponseData(),
        message=NEUTRAL_RETAILER_CREDENTIAL_MESSAGE,
        timestamp=datetime.utcnow(),
    )


@router.post(
    "/reset-password",
    response_model=RetailerCredentialResponse,
    status_code=status.HTTP_200_OK,
)
async def retailer_reset_password(
    request: RetailerResetPasswordRequest,
    db: AsyncSession = Depends(get_db_session),
    http_request: Request = None,
):
    """Consume a retailer reset token and set a new password.

    Token must arrive in the body only; query-string token/password params are
    rejected. On success the new password is applied to every tenant user
    mapped to the same retailer_id (unified credential), never to unrelated
    same-email users. Invalid/expired/used/revoked tokens return a neutral 401.
    """
    _reject_query_token(
        http_request,
        ("reset_token", "resetToken", "new_password", "newPassword", "token"),
    )
    if not request.reset_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": RESET_TOKEN_INVALID,
                "message": NEUTRAL_RETAILER_CREDENTIAL_MESSAGE,
            },
        )
    service = RetailerProvisioningService(db)
    try:
        await service.consume_password_reset(request.reset_token, request.new_password)
        await db.commit()
    except RetailerCredentialTokenInvalidError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": RESET_TOKEN_INVALID,
                "message": NEUTRAL_RETAILER_CREDENTIAL_MESSAGE,
            },
        )
    except ValueError:
        # Password policy violation — surface as neutral 401 (no leak).
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": RESET_TOKEN_INVALID,
                "message": NEUTRAL_RETAILER_CREDENTIAL_MESSAGE,
            },
        )
    return RetailerCredentialResponse(
        data=RetailerCredentialResponseData(),
        message=NEUTRAL_RETAILER_CREDENTIAL_MESSAGE,
        timestamp=datetime.utcnow(),
    )
