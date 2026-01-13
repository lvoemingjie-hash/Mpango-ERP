"""
Authentication API endpoints.
Implements openapi.yaml /auth/* endpoints.

Per multi_tenancy_spec.md section 4.1:
- Login validates tenant_code → tenant_id → tenant_schema
- JWT contains user_id, tenant_id, tenant_schema claims
- Tokens signed with HS256 algorithm
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db_session, get_tenant_db_session, get_current_user_context
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
    TokenPayload,
    InvalidTokenError,
    ExpiredTokenError
)
from crud.wholesaler import get_wholesaler_by_code
from crud.user import get_user_by_email, get_user_with_permissions
from database.session import get_tenant_db
from schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    CurrentUserResponse,
    TokenData,
    CurrentUserData
)
from schemas.common import MessageResponse

router = APIRouter()


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """
    Multi-tenant login endpoint.
    
    Implements openapi.yaml POST /auth/login
    
    Flow:
    1. Validate tenant_code against public.wholesalers
    2. Derive tenant_schema from wholesaler.id
    3. Authenticate user in tenant schema
    4. Return JWT with tenant claims
    
    Args:
        request: LoginRequest with tenant_code, email, password
        db: Public schema database session
        
    Returns:
        LoginResponse with access_token and refresh_token
        
    Raises:
        HTTPException 404: If tenant_code not found
        HTTPException 401: If credentials invalid
        HTTPException 400: If user inactive
    """
    # 1. Find wholesaler by tenant_code in public schema
    wholesaler = await get_wholesaler_by_code(db, request.tenant_code)
    if not wholesaler:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TENANT_NOT_FOUND", "message": "Tenant not found"}
        )
    
    tenant_schema = wholesaler.get_tenant_schema()
    
    # 2. Switch to tenant schema and find user
    async for tenant_db in get_tenant_db(tenant_schema):
        user = await get_user_by_email(tenant_db, request.email)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_CREDENTIALS", "message": "Invalid credentials"}
            )
        
        # 3. Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "USER_INACTIVE", "message": "User account is inactive"}
            )
        
        # 4. Verify password
        if not verify_password(request.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_CREDENTIALS", "message": "Invalid credentials"}
            )
        
        # 5. Generate tokens
        access_token = create_access_token(
            user_id=str(user.id),
            tenant_id=str(wholesaler.id),
            tenant_schema=tenant_schema
        )
        refresh_token = create_refresh_token(
            user_id=str(user.id),
            tenant_id=str(wholesaler.id),
            tenant_schema=tenant_schema
        )
        
        return LoginResponse(
            success=True,
            data=TokenData(
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer",
                user_id=str(user.id),
                tenant_id=str(wholesaler.id),
                tenant_schema=tenant_schema
            ),
            timestamp=datetime.utcnow()
        )


@router.post("/refresh", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def refresh_token(request: RefreshTokenRequest):
    """
    Refresh access token endpoint.
    
    Implements openapi.yaml POST /auth/refresh
    
    Validates refresh token and issues new access + refresh tokens.
    Preserves tenant_id and tenant_schema from original token.
    
    Args:
        request: RefreshTokenRequest with refresh_token
        
    Returns:
        LoginResponse with new access_token and refresh_token
        
    Raises:
        HTTPException 401: If refresh token invalid, expired, or wrong type
    """
    try:
        # Decode refresh token
        payload = decode_token(request.refresh_token)
        
        # Validate token type is refresh (not access)
        if payload.type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_TOKEN_TYPE", "message": "Refresh token required"}
            )
        
        # Generate new tokens with same claims
        access_token = create_access_token(
            user_id=payload.user_id,
            tenant_id=payload.tenant_id,
            tenant_schema=payload.tenant_schema
        )
        new_refresh_token = create_refresh_token(
            user_id=payload.user_id,
            tenant_id=payload.tenant_id,
            tenant_schema=payload.tenant_schema
        )
        
        return LoginResponse(
            success=True,
            data=TokenData(
                access_token=access_token,
                refresh_token=new_refresh_token,
                token_type="bearer",
                user_id=payload.user_id,
                tenant_id=payload.tenant_id,
                tenant_schema=payload.tenant_schema
            ),
            timestamp=datetime.utcnow()
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


@router.get("/me", response_model=CurrentUserResponse, status_code=status.HTTP_200_OK)
async def get_current_user(
    token: TokenPayload = Depends(get_current_user_context),
    db: AsyncSession = Depends(get_tenant_db_session)
):
    """
    Get current authenticated user info.
    
    Implements openapi.yaml GET /auth/me
    
    Returns user info from JWT claims with roles and permissions.
    
    Args:
        token: JWT payload from Authorization header
        db: Tenant-scoped database session
        
    Returns:
        CurrentUserResponse with user data, roles, and permissions
        
    Raises:
        HTTPException 401: If user not found in database
    """
    # Load user with roles and permissions
    user = await get_user_with_permissions(db, token.user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_NOT_FOUND", "message": "User not found"}
        )
    
    # Extract role names
    roles = [role.name for role in user.roles]
    
    # Extract permission codes from all roles
    permissions = set()
    for role in user.roles:
        for perm in role.permissions:
            permissions.add(perm.code)
    
    return CurrentUserResponse(
        success=True,
        data=CurrentUserData(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            tenant_id=token.tenant_id,
            tenant_schema=token.tenant_schema,
            roles=roles,
            permissions=list(permissions)
        ),
        timestamp=datetime.utcnow()
    )
