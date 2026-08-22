from __future__ import annotations

from datetime import datetime
from math import ceil
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
from schemas.retailer_credentials import (
    RetailerCredentialResponse,
    RetailerCredentialResponseData,
    RetailerSetupCredentialRequest,
)
from services.retailer_provisioning_service import (
    CREDENTIAL_ALREADY_ESTABLISHED,
    RETAILER_CREDENTIAL_NEUTRAL,
    SETUP_TOKEN_INVALID,
    RetailerCredentialTokenInvalidError,
    RetailerProvisioningError,
    RetailerProvisioningService,
)
from repositories.binding_repository import BindingRepository
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
async def register_retailer_dual_entry(
    request: Request,
    payload: RetailerRegisterRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Dual-entry retailer registration (DC-12R1-MVP-L1-J1-H2-A-R1).

    Entry A: invitation_code (wholesaler-shared one-time invite).
    Entry B: join_intent (server-signed, short-lived, bound to exactly one
    wholesaler by a public supplier-code lookup). Exactly one of the two is
    accepted — the schema rejects both/neither. The bound wholesaler is
    resolved exclusively server-side; a client-submitted wholesaler_id is
    never read. Endpoint-scoped rate limit applies on top of the global
    middleware bucket.
    """
    from core.rate_limiter import get_rate_limiter

    await get_rate_limiter().check_endpoint_rate_limit(
        request, namespace="public_register", limit=10
    )

    service = RetailerService()
    wholesaler = None
    if payload.join_intent is not None:
        from core.join_intent import JoinIntentError, verify_join_intent

        try:
            intent = verify_join_intent(payload.join_intent)
        except JoinIntentError:
            # Neutral: no disclosure of which check failed.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "JOIN_INTENT_INVALID", "message": "Registration failed"},
            )
        _inv, retailer, binding, error_code, wholesaler = (
            await service.register_with_join_intent(
                db,
                join_intent_wholesaler_id=intent.wholesaler_id,
                phone=payload.phone,
                email=payload.email,
                name=payload.name,
                address=payload.address,
            )
        )
    else:
        invitation, retailer, binding, error_code = await service.register_with_invitation(
            db,
            invitation_code=payload.invitation_code,
            phone=payload.phone,
            name=payload.name,
            email=payload.email,
            address=payload.address,
        )

    if error_code:
        status_code = (
            status.HTTP_422_UNPROCESSABLE_ENTITY
            if error_code == "EMAIL_REQUIRED"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail={"code": error_code, "message": "Registration failed"},
        )

    # Server-verified portal code for the login handoff: prefer the
    # provisioning-resolved wholesaler; fall back to loading it by the
    # binding's wholesaler id (still server-side truth, never client input).
    if wholesaler is None:
        from services.invitation_service import InvitationService

        wholesaler = await InvitationService().get_wholesaler(
            db, wholesaler_id=binding.wholesaler_id
        )
    wholesaler_code = wholesaler.code if wholesaler is not None else ""

    data = RetailerRegisterResponseData(
        retailer=_retailer_to_data(retailer),
        binding=_binding_to_data(binding),
        wholesaler_code=wholesaler_code,
    )

    return DataResponse(success=True, data=data, timestamp=datetime.utcnow())


# ---------------------------------------------------------------------------
# POST /retailers/setup-credential  (DC-12R1-S1 retailer credential setup)
# ---------------------------------------------------------------------------

NEUTRAL_RETAILER_SETUP_MESSAGE = (
    "Retailer setup result is not disclosed through this endpoint."
)


@router.post(
    "/retailers/setup-credential",
    response_model=RetailerCredentialResponse,
    status_code=status.HTTP_200_OK,
)
async def retailer_setup_credential(
    request: RetailerSetupCredentialRequest,
    db: AsyncSession = Depends(get_db_session),
    http_request: Request = None,
):
    """Consume a retailer setup token and establish the credential.

    Token arrives ONLY in the body; query-string token/password params are
    rejected. On success the new password is written to every tenant user
    mapped to the same retailer_id, the user is activated, and the canonical
    email is marked verified. retailer_id is resolved from the token row,
    never from email. Invalid/expired/used/revoked tokens return neutral 401.
    """
    if http_request is not None and any(
        k in http_request.query_params
        for k in ("setup_token", "setupToken", "password", "new_password")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": SETUP_TOKEN_INVALID,
                "message": NEUTRAL_RETAILER_SETUP_MESSAGE,
            },
        )
    service = RetailerProvisioningService(db)
    try:
        await service.consume_setup_token(request.setup_token, request.new_password)
        await db.commit()
    except RetailerCredentialTokenInvalidError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": SETUP_TOKEN_INVALID,
                "message": NEUTRAL_RETAILER_SETUP_MESSAGE,
            },
        )
    except ValueError:
        # Password policy violation — neutral 401 (no leak).
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": SETUP_TOKEN_INVALID,
                "message": NEUTRAL_RETAILER_SETUP_MESSAGE,
            },
        )
    return RetailerCredentialResponse(
        data=RetailerCredentialResponseData(),
        message=NEUTRAL_RETAILER_SETUP_MESSAGE,
        timestamp=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# POST /retailers/{retailer_id}/reissue-setup  (DC-12R1-S1 restricted reissue)
# ---------------------------------------------------------------------------


@router.post(
    "/retailers/{retailer_id}/reissue-setup",
    response_model=RetailerCredentialResponse,
    status_code=status.HTTP_200_OK,
)
async def retailer_reissue_setup(
    retailer_id: str,
    token: TokenPayload = Depends(RequirePermission("retailers:reissue_credential")),
    db: AsyncSession = Depends(get_db_session),
):
    """Reissue a retailer setup token (restricted).

    Tenant-scoped: the current token's tenant must own a binding for this
    retailer (verified in the service). Allowed ONLY while the retailer has no
    established password; otherwise returns 409 CREDENTIAL_ALREADY_ESTABLISHED.
    Cross-tenant access returns a neutral 404 (no relationship disclosure).
    """
    try:
        wholesaler_id = uuid.UUID(token.tenant_id)
        retailer_uuid = uuid.UUID(retailer_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RETAILER_NOT_FOUND", "message": RETAILER_CREDENTIAL_NEUTRAL},
        )
    service = RetailerProvisioningService(db)
    try:
        await service.reissue_setup_token(
            wholesaler_id=wholesaler_id,
            retailer_id=retailer_uuid,
            issued_by_user_id=uuid.UUID(token.user_id) if token.user_id else wholesaler_id,
        )
        await db.commit()
    except RetailerProvisioningError as exc:
        await db.rollback()
        if exc.code == CREDENTIAL_ALREADY_ESTABLISHED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": exc.code, "message": RETAILER_CREDENTIAL_NEUTRAL},
            )
        # RETAILER_NOT_FOUND (cross-tenant) and others -> neutral 404.
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "message": RETAILER_CREDENTIAL_NEUTRAL},
        )
    return RetailerCredentialResponse(
        data=RetailerCredentialResponseData(),
        message=NEUTRAL_RETAILER_SETUP_MESSAGE,
        timestamp=datetime.utcnow(),
    )


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

    # R1 dual-entry: derive each relationship's join source from the
    # used-invitation linkage (server-side truth; no client input). A used
    # invitation from THIS wholesaler for THIS retailer => 'invite', else
    # the relationship started through the supplier-code entry => 'code'.
    retailer_ids = [retailer.id for retailer, _binding in results]
    invited_ids: set = set()
    if retailer_ids:
        from sqlalchemy import text as _text

        rows = await db.execute(
            _text(
                "SELECT used_retailer_id FROM public.invitations "
                "WHERE wholesaler_id = :ws AND used_retailer_id = ANY(:rids) "
                "AND used_at IS NOT NULL AND is_deleted = false"
            ),
            {"ws": wholesaler_id, "rids": [str(r) for r in retailer_ids]},
        )
        invited_ids = {row[0] for row in rows.fetchall()}

    pages = ceil(total / size) if total > 0 else 0
    items = [
        RetailerWithBinding(
            retailer=_retailer_to_data(retailer),
            binding_status=binding.status,
            bound_at=binding.created_at,
            join_source="invite" if retailer.id in invited_ids else "code",
        )
        for retailer, binding in results
    ]

    data = RetailerListData(
        items=items,
        pagination=Pagination(page=page, size=size, total=total, pages=pages).model_dump(),
    )
    return DataResponse(success=True, data=data, timestamp=datetime.utcnow())


@router.post(
    "/retailers/{retailer_id}/deactivate",
    response_model=DataResponse[BindingData],
    status_code=status.HTTP_200_OK,
)
async def deactivate_retailer_binding(
    retailer_id: str,
    token: TokenPayload = Depends(RequirePermission("retailers:deactivate")),
    db: AsyncSession = Depends(get_db_session),
):
    """Deactivate a retailer relationship (dual-entry post-hoc control).

    Tenant-scoped: only the wholesaler who owns the binding may deactivate
    it; cross-tenant ids get a neutral 404. Idempotent for an already
    inactive binding. The retailer can no longer operate against this
    supplier while inactive.
    """
    try:
        retailer_uuid = uuid.UUID(retailer_id)
        wholesaler_id = uuid.UUID(token.tenant_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RETAILER_NOT_FOUND", "message": "Retailer not found"},
        )

    from db.tenant_filter import run_as_system

    binding = await BindingRepository().get_binding(
        db, wholesaler_id=wholesaler_id, retailer_id=retailer_uuid
    )
    if binding is None or binding.is_deleted:
        # Neutral 404 — no cross-tenant existence disclosure.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RETAILER_NOT_FOUND", "message": "Retailer not found"},
        )
    with run_as_system(reason="retailer_binding_deactivate"):
        if binding.status != "inactive":
            binding.status = "inactive"
            await db.flush()
        await db.commit()
        await db.refresh(binding)

    return DataResponse(
        success=True,
        data=_binding_to_data(binding),
        timestamp=datetime.utcnow(),
    )


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
