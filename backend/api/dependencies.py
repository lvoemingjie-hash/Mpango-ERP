"""
FastAPI dependencies for Mpango ERP.
Provides dependency injection for database sessions and authentication.

Per multi_tenancy_spec.md section 4.2:
- Tenant schema is ONLY derived from JWT claims
- Never from headers or request parameters
- This ensures tenant isolation cannot be bypassed
"""
from typing import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.context import get_auth_context, get_tenant_context as fetch_tenant_context
from core.security import TokenPayload
from database.session import get_db


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


def get_current_user_context(request: Request) -> TokenPayload:
    """Return the decoded JWT payload from request state."""
    return get_auth_context(request).token


def get_tenant_context(request: Request):
    """Expose tenant context stored on request.state."""
    return fetch_tenant_context(request)


def get_tenant_db_session(request: Request) -> AsyncSession:
    """Return tenant-scoped session attached to the request."""
    return fetch_tenant_context(request).session
