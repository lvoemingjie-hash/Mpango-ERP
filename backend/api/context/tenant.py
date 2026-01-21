"""Tenant context helpers."""
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import TokenPayload
from crud.user import get_user_with_permissions
from database.session import AsyncSessionLocal

_TENANT_CONTEXT_ATTR = "tenant_context"


def _http_exc(detail_code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": detail_code, "message": message},
    )


@dataclass
class TenantContext:
    """Container for tenant-scoped request data."""

    tenant_id: str
    tenant_schema: str
    session: AsyncSession
    user: object


async def create_tenant_session(tenant_schema: str) -> AsyncSession:
    """Create tenant-scoped async session with search_path set."""
    session: AsyncSession = AsyncSessionLocal()
    try:
        await session.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))
    except Exception:
        await session.close()
        raise
    return session


async def resolve_tenant_context(token: TokenPayload) -> TenantContext:
    """Build tenant context from JWT claims."""
    if not token.tenant_schema:
        raise _http_exc("MISSING_TENANT", "Tenant schema missing from token")

    session = await create_tenant_session(token.tenant_schema)
    try:
        user = await get_user_with_permissions(session, token.user_id)
        if not user:
            raise _http_exc("USER_NOT_FOUND", "User not found in tenant scope")
        if not getattr(user, "is_active", True):
            raise _http_exc("USER_INACTIVE", "User account is inactive")

        return TenantContext(
            tenant_id=token.tenant_id,
            tenant_schema=token.tenant_schema,
            session=session,
            user=user,
        )
    except Exception:
        await session.close()
        raise


def attach_tenant_context(request: Request, context: TenantContext) -> None:
    """Attach tenant context to request state."""
    setattr(request.state, _TENANT_CONTEXT_ATTR, context)


def clear_tenant_context(request: Request) -> None:
    """Remove tenant context from request state."""
    if hasattr(request.state, _TENANT_CONTEXT_ATTR):
        delattr(request.state, _TENANT_CONTEXT_ATTR)


def get_tenant_context(request: Request) -> TenantContext:
    """Retrieve tenant context from request state."""
    context: Optional[TenantContext] = getattr(request.state, _TENANT_CONTEXT_ATTR, None)
    if context is None:
        raise _http_exc("TENANT_CONTEXT_MISSING", "Tenant context unavailable for request")
    return context


async def finalize_tenant_context(context: TenantContext, success: bool) -> None:
    """Finalize tenant session lifecycle."""
    session = context.session
    try:
        if success:
            await session.commit()
        else:
            await session.rollback()
    finally:
        await session.close()
