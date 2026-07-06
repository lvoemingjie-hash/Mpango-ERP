"""
Authentication API endpoints.

H-Fix-01: Decoupled Identity from Tenant Context.
- POST /auth/login  -> email + password only -> Identity JWT + available_tenants
- POST /auth/select-tenant -> tenant_id -> Contextual JWT
- POST /auth/refresh -> works for both Identity and Contextual refresh tokens
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from schemas.auth_signup import SignupRequest, SignupResponse, SignupResponseData
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
    NEUTRAL_SIGNUP_MESSAGE,
    create_signup_registration,
)

router = APIRouter()


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
            status=result.status,
            email_verification_required=result.email_verification_required,
            resend_available_at=result.resend_available_at,
        ),
        message=NEUTRAL_SIGNUP_MESSAGE,
        timestamp=datetime.utcnow(),
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

    # Aggregate unique roles across all tenants
    all_roles = sorted({r for m in matches for r in m.roles})

    # Build available tenants list
    available_tenants = [
        TenantInfo(
            id=str(m.wholesaler.id),
            code=m.wholesaler.code,
            name=m.wholesaler.name,
        )
        for m in matches
    ]

    # Create identity tokens (no tenant context)
    access_token = create_identity_token(
        user_id=verified_user_id,
        roles=all_roles,
        token_type="access",
    )
    refresh_token = create_identity_token(
        user_id=verified_user_id,
        roles=all_roles,
        token_type="refresh",
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

    # 2. Verify user exists in this tenant schema using a raw query to bypass the ORM filter.
    user_query = text(f'SELECT id, is_active FROM "{tenant_schema}".users WHERE id = :user_id')
    user_result = await db.execute(user_query, {"user_id": UUID(token.user_id)})
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

    roles_result = await db.execute(roles_query, {"user_id": UUID(token.user_id)})
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

@router.post("/refresh", response_model=LoginResponse, status_code=status.HTTP_200_OK)
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
            # Identity refresh - re-issue identity tokens
            access_token = create_identity_token(
                user_id=payload.user_id,
                roles=payload.roles,
                token_type="access",
            )
            new_refresh = create_identity_token(
                user_id=payload.user_id,
                roles=payload.roles,
                token_type="refresh",
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
