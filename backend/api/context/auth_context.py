"""
Auth context helpers for Mpango ERP.

Provides JWT decoding and user/tenant resolution utilities
used by dependencies and middleware.
"""
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import (
    decode_token as _decode_token,
    TokenPayload,
    InvalidTokenError,
    ExpiredTokenError,
)
from database.session import get_tenant_db


def decode_jwt_token(token: str) -> TokenPayload:
    """
    Decode and validate a JWT token.
    """
    return _decode_token(token)


class JWTBearer(HTTPBearer):
    """
    JWT Bearer token authentication dependency.

    Usage:
        @router.get("/protected")
        async def protected_route(token: TokenPayload = Depends(JWTBearer())):
            # token contains user_id, tenant_id, tenant_schema
    """

    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)

    async def __call__(self, request: Request) -> TokenPayload:
        """
        Validate JWT token from Authorization header.

        Args:
            request: FastAPI request object

        Returns:
            TokenPayload with decoded claims

        Raises:
            HTTPException 401: For missing, invalid, or expired tokens
        """
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)

        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "MISSING_TOKEN", "message": "Authorization header required"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        if credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_SCHEME", "message": "Bearer scheme required"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            payload = decode_jwt_token(credentials.credentials)

            # Validate token type is access (not refresh)
            if payload.type != "access":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"code": "INVALID_TOKEN_TYPE", "message": "Access token required"},
                    headers={"WWW-Authenticate": "Bearer"},
                )

            return payload

        except ExpiredTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "TOKEN_EXPIRED", "message": "Token has expired"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        except InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_TOKEN", "message": "Invalid token"},
                headers={"WWW-Authenticate": "Bearer"},
            )


# Singleton instance for convenience
jwt_bearer = JWTBearer()


async def get_current_user_context(
    token: TokenPayload = Depends(jwt_bearer),
) -> TokenPayload:
    """
    Get current user context from JWT token.

    Extracts and validates JWT from Authorization header.
    Returns TokenPayload with user_id, tenant_id, tenant_schema.

    Args:
        token: Decoded JWT payload from JWTBearer

    Returns:
        TokenPayload with user context
    """
    return token


def resolve_tenant_schema(token: TokenPayload) -> str:
    """
    Resolve tenant schema from JWT payload.

    Raises:
        HTTPException 401: If tenant_schema claim is missing
    """
    if not token.tenant_schema:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "MISSING_TENANT", "message": "Tenant schema missing from token"},
        )
    return token.tenant_schema


async def get_tenant_db_session(
    token: TokenPayload = Depends(get_current_user_context),
) -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session with tenant search_path set from JWT claims.

    CRITICAL: Tenant schema is ONLY derived from JWT claims.
    This ensures tenant isolation cannot be bypassed by headers or params.

    Per multi_tenancy_spec.md section 4.2:
    - Sets search_path to "<tenant_schema>", public
    - ORM models automatically resolve to correct tenant schema

    Args:
        token: JWT payload containing tenant_schema

    Yields:
        AsyncSession with tenant search_path set
    """
    tenant_schema = resolve_tenant_schema(token)
    async for session in get_tenant_db(tenant_schema):
        yield session
