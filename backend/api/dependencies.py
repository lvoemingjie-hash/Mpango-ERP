"""
FastAPI dependencies for Mpango ERP.
Provides dependency injection for database sessions and authentication.

Per multi_tenancy_spec.md section 4.2:
- Tenant schema is ONLY derived from JWT claims
- Never from headers or request parameters
- This ensures tenant isolation cannot be bypassed
"""
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_db, get_tenant_db
from api.middleware.auth import JWTBearer
from core.security import TokenPayload


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for public schema database session.
    
    Usage:
        @app.get("/endpoint")
        async def endpoint(db: AsyncSession = Depends(get_db_session)):
            # Use db session
    """
    async for session in get_db():
        yield session


# JWT Bearer authentication instance
_jwt_bearer = JWTBearer()


async def get_current_user_context(
    token: TokenPayload = Depends(_jwt_bearer)
) -> TokenPayload:
    """
    Get current user context from JWT token.
    
    Extracts and validates JWT from Authorization header.
    Returns TokenPayload with user_id, tenant_id, tenant_schema.
    
    Args:
        token: Decoded JWT payload from JWTBearer
        
    Returns:
        TokenPayload with user context
        
    Raises:
        HTTPException 401: If token is missing, invalid, or expired
    """
    return token


async def get_tenant_db_session(
    token: TokenPayload = Depends(get_current_user_context)
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
        
    Raises:
        HTTPException 401: If tenant_schema claim is missing
    """
    if not token.tenant_schema:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "MISSING_TENANT", "message": "Tenant schema missing from token"}
        )
    
    async for session in get_tenant_db(token.tenant_schema):
        yield session
