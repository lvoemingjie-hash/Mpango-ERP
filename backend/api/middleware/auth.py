"""Authentication middleware for Mpango ERP."""
import os
import uuid
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text

from api.context import (
    AuthContext,
    TenantContext,
    attach_auth_context,
    attach_tenant_context,
    clear_auth_context,
    clear_tenant_context,
    extract_bearer_token,
    finalize_tenant_context,
    resolve_auth_context,
    resolve_tenant_context,
)
from core.logging_config import get_request_logger
from core.security import TokenPayload
from database.session import AsyncSessionLocal
from db.tenant_filter import reset_current_tenant, set_current_tenant

__all__ = ["AuthenticationMiddleware"]


class _TestModeSession:
    """
    Real async session for test mode that sets tenant search_path.
    Wraps SQLAlchemy AsyncSession to enable real DB operations.
    """
    def __init__(self, tenant_schema: str):
        self._tenant_schema = tenant_schema
        self._session = None

    async def _ensure_session(self):
        """Lazily initialize the session."""
        if self._session is None:
            self._session = AsyncSessionLocal()
            self._session.info["tenant_schema"] = self._tenant_schema
            # Set search_path for tenant isolation
            await self._session.execute(
                text(f'SET LOCAL search_path TO "{self._tenant_schema}", public')
            )

    async def execute(self, *args, **kwargs):
        await self._ensure_session()
        return await self._session.execute(*args, **kwargs)

    async def commit(self):
        await self._ensure_session()
        return await self._session.commit()

    async def rollback(self):
        await self._ensure_session()
        return await self._session.rollback()

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    def begin(self):
        """Return a transaction context manager."""
        return _TestModeTransaction(self)


class _TestModeTransaction:
    """Transaction context manager for test mode session."""
    def __init__(self, session: _TestModeSession):
        self._session = session

    async def __aenter__(self):
        await self._session._ensure_session()
        return self._session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self._session.rollback()
        else:
            await self._session.commit()
        return False


class _TestModePermission:
    def __init__(self, code: str):
        self.code = code


class _TestModeRole:
    def __init__(self, name: str, permission_codes: list[str]):
        self.name = name
        self.permissions = [_TestModePermission(code) for code in permission_codes]


class _TestModeUser:
    def __init__(self, roles: list[_TestModeRole]):
        self.roles = roles
        self.is_active = True


class _TestModeToken:
    def __init__(self, *, user_id: str, tenant_id: str, tenant_schema: str, permissions: list[str]):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.tenant_schema = tenant_schema
        self.type = "access"
        self.permissions = permissions


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Decode JWT tokens and attach auth/tenant context to request.state."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        # Generate unique request ID for tracing
        request_id = str(uuid.uuid4())
        tenant_id = 'N/A'  # Default value

        # Set up logging context for this request
        logger = get_request_logger(request_id, tenant_id)

        auth_ctx: Optional[AuthContext] = None
        tenant_ctx: Optional[TenantContext] = None
        tenant_tokens = None

        try:
            if os.getenv("MPANGO_TEST_MODE", "").lower() == "true":
                permission_codes = [
                    "payments:create",
                    "orders:read",
                    "orders:write",
                ]
                token = _TestModeToken(
                    user_id="00000000-0000-0000-0000-000000000001",
                    tenant_id="00000000-0000-0000-0000-000000000000",
                    tenant_schema="t_dev",
                    permissions=permission_codes,
                )

                tenant_id = str(token.tenant_id)
                logger = get_request_logger(request_id, tenant_id)
                auth_ctx = AuthContext(token=token, raw_token="")
                attach_auth_context(request, auth_ctx)

                user = _TestModeUser(
                    roles=[
                        _TestModeRole(
                            name="test",
                            permission_codes=permission_codes,
                        )
                    ]
                )
                tenant_ctx = TenantContext(
                    tenant_id=token.tenant_id,
                    tenant_schema=token.tenant_schema,
                    session=_TestModeSession(token.tenant_schema),
                    user=user,
                )
                attach_tenant_context(request, tenant_ctx)
                tenant_tokens = set_current_tenant(
                    tenant_id=str(token.tenant_id),
                    tenant_schema=token.tenant_schema,
                )
            else:
                raw_token = extract_bearer_token(request)

                if raw_token:
                    auth_ctx = resolve_auth_context(raw_token)
                    attach_auth_context(request, auth_ctx)

                    tenant_ctx = await resolve_tenant_context(auth_ctx.token)
                    attach_tenant_context(request, tenant_ctx)

                    tenant_tokens = set_current_tenant(
                        tenant_id=str(tenant_ctx.tenant_id),
                        tenant_schema=tenant_ctx.tenant_schema,
                    )

                    # Update tenant_id in logging context if available
                    if tenant_ctx and tenant_ctx.tenant_id:
                        tenant_id = str(tenant_ctx.tenant_id)
                        logger = get_request_logger(request_id, tenant_id)

            # Update request.state with logging context for potential use by other middleware/dependencies
            request.state.request_id = request_id
            request.state.tenant_id = tenant_id

            response = await call_next(request)

            if tenant_ctx:
                await finalize_tenant_context(tenant_ctx, success=response.status_code < 400)

            return response

        except HTTPException as exc:
            if tenant_ctx:
                await finalize_tenant_context(tenant_ctx, success=False)

            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail,
                headers=exc.headers,
            )

        except Exception:
            if tenant_ctx:
                await finalize_tenant_context(tenant_ctx, success=False)
            raise

        finally:
            if tenant_ctx:
                clear_tenant_context(request)
            if auth_ctx:
                clear_auth_context(request)

            if tenant_tokens:
                reset_current_tenant(*tenant_tokens)
