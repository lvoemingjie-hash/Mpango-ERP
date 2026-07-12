"""
Authentication API endpoints.

H-Fix-01: Decoupled Identity from Tenant Context.
- POST /auth/login  -> email + password only -> Identity JWT + available_tenants
- POST /auth/select-tenant -> tenant_id -> Contextual JWT
- POST /auth/refresh -> works for both Identity and Contextual refresh tokens
"""
from datetime import datetime
from typing import Union
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.dependencies import get_db_session, get_current_user_context
from core.cache import cache
from core.security import (
    create_contextual_token,
    create_identity_token,
    decode_token,
    TokenPayload,
    InvalidTokenError,
    ExpiredTokenError
)
from crud.wholesaler import get_wholesaler_by_id
from crud.user import find_user_across_tenants, get_user_with_permissions
from database.session import get_tenant_db
from models.user import User, Role
from schemas.auth_signup import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ForgotPasswordResponseData,
    OnboardingStatusRequest,
    OnboardingStatusResponse,
    OnboardingStatusResponseData,
    OwnerCredentialSetupRequest,
    OwnerCredentialSetupResponse,
    OwnerCredentialSetupResponseData,
    ResetPasswordRequest,
    ResetPasswordResponse,
    ResetPasswordResponseData,
    SignupRequest,
    SignupResponse,
    SignupResponseData,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from schemas.auth import (
    LoginRequest,
    LoginResponse,
    IdentityLoginResponse,
    IdentityTokenData,
    SelectTenantRequest,
    TenantInfo,
    RefreshTokenRequest,
    CurrentUserResponse,
    TokenData,
    CurrentUserData
)
from schemas.common import MessageResponse
from services.email_delivery import EmailDeliveryNotConfiguredError
from services.onboarding_service import (
    IdempotencyConflictError,
    INVALID_OR_EXPIRED_ONBOARDING_STATUS_TOKEN,
    INVALID_OR_EXPIRED_VERIFICATION_TOKEN,
    NEUTRAL_ONBOARDING_STATUS_MESSAGE,
    NEUTRAL_SIGNUP_MESSAGE,
    NEUTRAL_VERIFY_EMAIL_MESSAGE,
    OnboardingOrchestrationError,
    OnboardingStatusTokenInvalidError,
    VerificationTokenInvalidError,
    create_signup_registration,
    get_onboarding_status,
    verify_email_token,
)
from services.owner_credential_service import (
    INVALID_OR_EXPIRED_OWNER_CREDENTIAL_SETUP_TOKEN,
    OwnerCredentialSetupAdminCreationError,
    OwnerCredentialSetupService,
    OwnerCredentialSetupTokenInvalidError,
)
from services.password_reset_service import (
    INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN,
    NEUTRAL_PASSWORD_RESET_MESSAGE,
    PasswordResetService,
    PasswordResetTokenInvalidError,
)

router = APIRouter()
PUBLIC_SIGNUP_STATUS = "pending_email_verification"
NEUTRAL_OWNER_CREDENTIAL_SETUP_MESSAGE = "Credential setup result is not disclosed through this endpoint."


# ---------------------------------------------------------------------------
# POST /auth/signup  (U6-C tenant registration skeleton)
# ---------------------------------------------------------------------------

@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_202_ACCEPTED)
async def signup(
    signup_request: SignupRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Create a pending tenant registration and verification token hash."""
    try:
        result = await create_signup_registration(
            db=db,
            request=signup_request,
            idempotency_key=request.headers.get("Idempotency-Key"),
        )
    except IdempotencyConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "IDEMPOTENCY_CONFLICT",
                "message": "Idempotency key was reused with a different signup payload",
            },
        )
    except EmailDeliveryNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "EMAIL_DELIVERY_NOT_CONFIGURED",
                "message": "Signup verification email delivery is not configured",
            },
        )

    return SignupResponse(
        data=SignupResponseData(
            registration_id=None,
            status=PUBLIC_SIGNUP_STATUS,
            email_verification_required=result.email_verification_required,
            resend_available_at=result.resend_available_at,
        ),
        message=NEUTRAL_SIGNUP_MESSAGE,
        timestamp=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# POST /auth/verify-email  (U6-D email verification skeleton)
# ---------------------------------------------------------------------------

@router.post("/verify-email", response_model=VerifyEmailResponse, status_code=status.HTTP_200_OK)
async def verify_email(
    verify_request: VerifyEmailRequest = Body(default_factory=VerifyEmailRequest),
    db: AsyncSession = Depends(get_db_session),
):
    """Verify signup email and complete backend onboarding orchestration."""
    try:
        await verify_email_token(db=db, token=verify_request.token)
    except VerificationTokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": INVALID_OR_EXPIRED_VERIFICATION_TOKEN,
                "message": "Verification link is invalid or expired",
            },
        )
    except EmailDeliveryNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "EMAIL_DELIVERY_NOT_CONFIGURED",
                "message": NEUTRAL_VERIFY_EMAIL_MESSAGE,
            },
        )
    except OnboardingOrchestrationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ONBOARDING_ORCHESTRATION_FAILED",
                "message": NEUTRAL_VERIFY_EMAIL_MESSAGE,
            },
        )

    return VerifyEmailResponse(
        message=NEUTRAL_VERIFY_EMAIL_MESSAGE,
        timestamp=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# POST /auth/onboarding/status  (U6-E onboarding status endpoint)
# ---------------------------------------------------------------------------

@router.post(
    "/onboarding/status",
    response_model=OnboardingStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def onboarding_status(
    status_request: OnboardingStatusRequest = Body(default_factory=OnboardingStatusRequest),
    status_token_header: str | None = Header(None, alias="X-Onboarding-Status-Token"),
    db: AsyncSession = Depends(get_db_session),
):
    """Return coarse onboarding status for a valid opaque status token."""
    body_token = status_request.status_token
    header_token = status_token_header.strip() if status_token_header else None
    if body_token and header_token and body_token != header_token:
        raise _invalid_onboarding_status_token()

    try:
        result = await get_onboarding_status(db=db, token=body_token or header_token)
    except OnboardingStatusTokenInvalidError:
        raise _invalid_onboarding_status_token()

    return OnboardingStatusResponse(
        data=OnboardingStatusResponseData(status=result.status),
        message=NEUTRAL_ONBOARDING_STATUS_MESSAGE,
        timestamp=datetime.utcnow(),
    )


def _invalid_onboarding_status_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": INVALID_OR_EXPIRED_ONBOARDING_STATUS_TOKEN,
            "message": "Onboarding status token is invalid or expired",
        },
    )


# ---------------------------------------------------------------------------
# POST /auth/login  (Identity phase)
# ---------------------------------------------------------------------------

@router.post("/login", response_model=IdentityLoginResponse, status_code=status.HTTP_200_OK)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Identity login endpoint (H-Fix-01).

    Flow:
    1. Accept email + password (no tenant_code).
    2. Scan all active tenant schemas for the email.
    3. Verify password.
    4. Return Identity JWT + list of available tenants.

    The Identity JWT contains NO tenant context.  Frontend should call
    POST /auth/select-tenant to obtain a Contextual JWT.

    Returns:
        IdentityLoginResponse with identity tokens and available_tenants.

    Raises:
        HTTPException 401: Invalid credentials.
    """
    verified_user_id, matches = await find_user_across_tenants(
        db, request.email, request.password
    )

    if verified_user_id is None or len(matches) == 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Invalid credentials"}
        )

    # Aggregate unique roles across all VERIFIED tenants only (DC-3B-R1: matches
    # now contains only copies whose own password_hash verified at login).
    all_roles = sorted({r for m in matches for r in m.roles})

    # Build available tenants list (only verified tenants are listed/selectable).
    available_tenants = [
        TenantInfo(
            id=str(m.wholesaler.id),
            code=m.wholesaler.code,
            name=m.wholesaler.name,
        )
        for m in matches
    ]

    # DC-3B-R1: signed tenant_id -> tenant-local user_id map for verified
    # matches. Carried in the identity JWT so /select-tenant resolves the
    # correct per-tenant user_id when the same email has different user IDs
    # across tenants. Never exposed in the public response body.
    tenant_user_map = {str(m.wholesaler.id): str(m.user.id) for m in matches}

    # Create identity tokens (no tenant context) carrying the signed map.
    access_token = create_identity_token(
        user_id=verified_user_id,
        roles=all_roles,
        token_type="access",
        tenant_user_map=tenant_user_map,
    )
    refresh_token = create_identity_token(
        user_id=verified_user_id,
        roles=all_roles,
        token_type="refresh",
        tenant_user_map=tenant_user_map,
    )

    return IdentityLoginResponse(
        success=True,
        data=IdentityTokenData(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user_id=verified_user_id,
            roles=all_roles,
            available_tenants=available_tenants,
        ),
        timestamp=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# POST /auth/select-tenant  (Context phase)
# ---------------------------------------------------------------------------

@router.post("/select-tenant", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def select_tenant(
    request: SelectTenantRequest,
    token: TokenPayload = Depends(get_current_user_context),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Upgrade an Identity JWT to a Contextual JWT.

    Flow:
    1. Validate the caller holds a valid Identity (or Contextual) JWT.
    2. Verify the requested tenant exists and user has access.
    3. Return a Contextual JWT scoped to the selected tenant.

    Args:
        request: SelectTenantRequest with tenant_id
        token: Current JWT payload (identity or contextual)
        db: Public schema database session

    Returns:
        LoginResponse with contextual access + refresh tokens.

    Raises:
        HTTPException 404: Tenant not found.
        HTTPException 403: User has no access to this tenant.
    """
    # 1. Find the wholesaler
    wholesaler = await get_wholesaler_by_id(db, request.tenant_id)
    if not wholesaler:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TENANT_NOT_FOUND", "message": "Tenant not found"}
        )

    tenant_schema = wholesaler.get_tenant_schema()

    # DC-3B-R1: resolve the tenant-local user_id. For identity-only tokens that
    # carry the signed tenant_id->user_id map (tmap), use the map entry for the
    # requested tenant so the correct per-tenant user is selected even when the
    # same email has different user IDs across tenants. For contextual tokens or
    # legacy/mock identity tokens without tmap, fall back to token.user_id.
    # getattr() tolerates mock tokens (test mode) that don't expose the field.
    token_tmap = getattr(token, "tmap", None)
    if token.is_identity_only and token_tmap:
        local_user_id_str = token_tmap.get(str(wholesaler.id))
        if not local_user_id_str:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "TENANT_ACCESS_DENIED",
                    "message": "You do not have access to this tenant"
                },
            )
        effective_user_id = UUID(local_user_id_str)
    else:
        effective_user_id = UUID(token.user_id)

    # 2. Verify user exists and is active in this tenant schema.
    user_query = text(f'SELECT id, is_active FROM "{tenant_schema}".users WHERE id = :user_id')
    user_result = await db.execute(user_query, {"user_id": effective_user_id})
    user = user_result.fetchone()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TENANT_ACCESS_DENIED",
                "message": "You do not have access to this tenant"
            }
        )

    # Fetch roles for the user in the target tenant
    roles_query = text(
        f'SELECT r.name FROM "{tenant_schema}".roles r '
        f'JOIN "{tenant_schema}".user_roles ur ON r.id = ur.role_id '
        f'WHERE ur.user_id = :user_id'
    )

    roles_result = await db.execute(roles_query, {"user_id": effective_user_id})
    roles = [row[0] for row in roles_result.fetchall()]

    # 3. Issue contextual tokens
    access_token = create_contextual_token(
        user_id=str(user.id),
        roles=roles,
        tenant_id=str(wholesaler.id),
        tenant_schema=tenant_schema,
        token_type="access",
    )
    refresh_token = create_contextual_token(
        user_id=str(user.id),
        roles=roles,
        tenant_id=str(wholesaler.id),
        tenant_schema=tenant_schema,
        token_type="refresh",
    )

    return LoginResponse(
        success=True,
        data=TokenData(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user_id=str(user.id),
            tenant_id=str(wholesaler.id),
            tenant_schema=tenant_schema,
            roles=roles,
        ),
        timestamp=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------

@router.post("/refresh", response_model=Union[LoginResponse, IdentityLoginResponse], status_code=status.HTTP_200_OK)
async def refresh_token(request: RefreshTokenRequest):
    """
    Refresh access token endpoint.

    Works for both Identity and Contextual refresh tokens.
    - Identity refresh -> new Identity tokens
    - Contextual refresh -> new Contextual tokens (preserves tenant claims)

    Returns:
        LoginResponse with new access_token and refresh_token.

    Raises:
        HTTPException 401: If refresh token invalid, expired, or wrong type.
    """
    try:
        payload = decode_token(request.refresh_token)

        if payload.type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_TOKEN_TYPE", "message": "Refresh token required"}
            )

        if payload.is_identity_only:
            # Identity refresh - re-issue identity tokens (preserve the signed
            # tenant_id->user_id map so tenant selection still works after
            # refresh; DC-3B-R1).
            access_token = create_identity_token(
                user_id=payload.user_id,
                roles=payload.roles,
                token_type="access",
                tenant_user_map=payload.tmap,
            )
            new_refresh = create_identity_token(
                user_id=payload.user_id,
                roles=payload.roles,
                token_type="refresh",
                tenant_user_map=payload.tmap,
            )
            # For identity-only refresh we still return LoginResponse
            # but with placeholder tenant fields - the frontend should
            # call select-tenant to get a full contextual token.
            # We return the identity tokens wrapped in the contextual schema
            # by using sentinel values.
            return IdentityLoginResponse(
                success=True,
                data=IdentityTokenData(
                    access_token=access_token,
                    refresh_token=new_refresh,
                    token_type="bearer",
                    user_id=payload.user_id,
                    roles=payload.roles,
                    available_tenants=[],
                ),
                timestamp=datetime.utcnow(),
            )
        else:
            # Contextual refresh - preserve tenant claims
            access_token = create_contextual_token(
                user_id=payload.user_id,
                roles=payload.roles,
                tenant_id=payload.tenant_id,
                tenant_schema=payload.tenant_schema,
                token_type="access",
            )
            new_refresh = create_contextual_token(
                user_id=payload.user_id,
                roles=payload.roles,
                tenant_id=payload.tenant_id,
                tenant_schema=payload.tenant_schema,
                token_type="refresh",
            )

            return LoginResponse(
                success=True,
                data=TokenData(
                    access_token=access_token,
                    refresh_token=new_refresh,
                    token_type="bearer",
                    user_id=payload.user_id,
                    tenant_id=payload.tenant_id,
                    tenant_schema=payload.tenant_schema,
                    roles=payload.roles,
                ),
                timestamp=datetime.utcnow(),
            )

    except ExpiredTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "REFRESH_TOKEN_EXPIRED", "message": "Refresh token has expired"}
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_REFRESH_TOKEN", "message": "Invalid refresh token"}
        )


@router.post("/logout", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def logout(token: TokenPayload = Depends(get_current_user_context)):
    """
    Logout endpoint.

    Implements openapi.yaml POST /auth/logout

    Client should discard tokens on logout.
    No server-side token invalidation for MVP (stateless JWT).

    Args:
        token: JWT payload (validates authentication)

    Returns:
        MessageResponse with success message
    """
    return MessageResponse(
        success=True,
        message="Logged out successfully",
        timestamp=datetime.utcnow()
    )


@cache(ttl_seconds=30, key_prefix="auth_me", key_builder=lambda user_id, db: user_id)
async def _get_user_with_permissions_cached(user_id: str, db: AsyncSession):
    """
    S3-C: Cached helper for getting user with permissions.

    Cache Key: auth_me:{user_id}
    TTL: 30 seconds

    Rationale: User profile data changes infrequently, but /auth/me is called
    frequently for permission checks. Caching reduces DB load by 90%.
    """
    user = await get_user_with_permissions(db, user_id)

    if not user:
        return None

    # Extract role names
    roles = [role.name for role in user.roles]

    # Extract permission codes from all roles
    permissions = set()
    for role in user.roles:
        for perm in role.permissions:
            permissions.add(perm.code)

    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "roles": roles,
        "permissions": list(permissions)
    }


@router.get("/me", response_model=CurrentUserResponse, status_code=status.HTTP_200_OK)
async def get_current_user(
    request: Request,
    token: TokenPayload = Depends(get_current_user_context),
):
    """
    Get current authenticated user info.

    H-Fix-01: Works for both identity-only and contextual JWTs.
    - Identity JWT: returns user_id and roles from JWT claims (no DB query).
    - Contextual JWT: queries tenant DB for full user data with permissions.

    S3-C: Cached with 30s TTL for contextual tokens.
    """
    if token.is_identity_only:
        # Identity-only JWT: return minimal info from JWT claims.
        return CurrentUserResponse(
            success=True,
            data=CurrentUserData(
                id=token.user_id,
                email=None,
                full_name=None,
                tenant_id=None,
                tenant_schema=None,
                roles=token.roles,
                permissions=[],
            ),
            timestamp=datetime.utcnow(),
        )


    # Contextual JWT: get tenant session from request state (set by middleware).
    from api.context.tenant import get_tenant_context as _get_tc
    tenant_ctx = _get_tc(request)
    db: AsyncSession = tenant_ctx.session

    user_data = await _get_user_with_permissions_cached(token.user_id, db)

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_NOT_FOUND", "message": "User not found"}
        )

    return CurrentUserResponse(
        success=True,
        data=CurrentUserData(
            id=user_data["id"],
            email=user_data["email"],
            full_name=user_data["full_name"],
            tenant_id=token.tenant_id,
            tenant_schema=token.tenant_schema,
            roles=user_data["roles"],
            permissions=user_data["permissions"]
        ),
        timestamp=datetime.utcnow()
    )


# ---------------------------------------------------------------------------
# POST /auth/onboarding/setup-credential  (U6-I5 owner credential setup)
# ---------------------------------------------------------------------------

@router.post(
    "/onboarding/setup-credential",
    response_model=OwnerCredentialSetupResponse,
    status_code=status.HTTP_200_OK,
)
async def setup_credential(
    request: OwnerCredentialSetupRequest,
    db: AsyncSession = Depends(get_db_session),
    http_request: Request = None,
):
    if http_request is not None and any(
        k in http_request.query_params for k in ("setup_token", "setupToken", "password")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": INVALID_OR_EXPIRED_OWNER_CREDENTIAL_SETUP_TOKEN,
                "message": NEUTRAL_OWNER_CREDENTIAL_SETUP_MESSAGE,
            },
        )
    try:
        service = OwnerCredentialSetupService(db)
        consume_result = await service.consume_setup_token(
            request.setup_token, request.password
        )
        admin_result = await service.create_first_admin_rbac(consume_result)
    except OwnerCredentialSetupTokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": INVALID_OR_EXPIRED_OWNER_CREDENTIAL_SETUP_TOKEN,
                "message": NEUTRAL_OWNER_CREDENTIAL_SETUP_MESSAGE,
            },
        )
    except OwnerCredentialSetupAdminCreationError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "OWNER_ADMIN_RBAC_CREATION_FAILED",
                "message": NEUTRAL_OWNER_CREDENTIAL_SETUP_MESSAGE,
            },
        )

    return OwnerCredentialSetupResponse(
        data=OwnerCredentialSetupResponseData(),
        message=NEUTRAL_OWNER_CREDENTIAL_SETUP_MESSAGE,
        timestamp=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# POST /auth/forgot-password  (DC-3B credential recovery)
# ---------------------------------------------------------------------------
@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    status_code=status.HTTP_200_OK,
)
async def forgot_password(
    request: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Request a password reset link.

    Always returns a neutral 200 regardless of whether the email exists, to
    avoid account-existence disclosure. If active tenant users exist for the
    email, a single canonical reset token is issued and the reset email is
    sent. Production fails closed: if email delivery is unavailable, no token
    is committed and the endpoint still responds neutrally.
    """
    service = PasswordResetService(db)
    try:
        await service.request_reset(request.email)
    except EmailDeliveryNotConfiguredError:
        # Fail-closed: do not commit a token without a delivered email.
        await db.rollback()
    except Exception:
        # Any unexpected error must not leak account existence; respond neutral.
        await db.rollback()
    return ForgotPasswordResponse(
        data=ForgotPasswordResponseData(),
        message=NEUTRAL_PASSWORD_RESET_MESSAGE,
        timestamp=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# POST /auth/reset-password  (DC-3B credential recovery)
# ---------------------------------------------------------------------------
@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
    status_code=status.HTTP_200_OK,
)
async def reset_password(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db_session),
    http_request: Request = None,
):
    """Consume a reset token and set a new password.

    Token must arrive in the body only; query-string token/password params are
    rejected. On success the new password is applied to every active tenant
    user copy for the email (canonical multi-tenant rule) and the token is
    marked used. Invalid/expired/used/revoked tokens return a neutral error.
    """
    # Reject query-string token/password (anti-leakage, mirrors setup-credential).
    if http_request is not None and any(
        k in http_request.query_params
        for k in ("reset_token", "resetToken", "new_password", "newPassword", "token")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN,
                "message": NEUTRAL_PASSWORD_RESET_MESSAGE,
            },
        )

    if not request.reset_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN,
                "message": NEUTRAL_PASSWORD_RESET_MESSAGE,
            },
        )

    service = PasswordResetService(db)
    try:
        await service.consume_reset(request.reset_token, request.new_password)
        await db.commit()
    except PasswordResetTokenInvalidError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN,
                "message": NEUTRAL_PASSWORD_RESET_MESSAGE,
            },
        )
    except ValueError:
        # Password policy violation (e.g. blank / < 8). Surface as neutral 401
        # so the reset-consume surface does not leak which validation failed.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN,
                "message": NEUTRAL_PASSWORD_RESET_MESSAGE,
            },
        )

    return ResetPasswordResponse(
        data=ResetPasswordResponseData(),
        message=NEUTRAL_PASSWORD_RESET_MESSAGE,
        timestamp=datetime.utcnow(),
    )
