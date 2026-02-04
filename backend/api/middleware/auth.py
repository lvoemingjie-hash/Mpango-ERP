"""Authentication middleware for Mpango ERP."""
import uuid
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api.context.auth import AuthContext, attach_auth_context, clear_auth_context
from auth.strategy import AuthStrategy
from core.logging_config import get_request_logger
from db.tenant_filter import reset_current_tenant, set_current_tenant

__all__ = ["AuthenticationMiddleware"]


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Decode JWT tokens and attach auth/tenant context to request.state."""

    def __init__(self, app, *, strategy: AuthStrategy):
        super().__init__(app)
        self._strategy = strategy

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        # Generate unique request ID for tracing
        request_id = str(uuid.uuid4())
        tenant_id = 'N/A'  # Default value

        # Set up logging context for this request
        logger = get_request_logger(request_id, tenant_id)

        auth_ctx: Optional[AuthContext] = None
        tenant_ctx = None
        tenant_tokens = None

        try:
            auth_ctx = await self._strategy.authenticate(request)
            if auth_ctx is not None:
                attach_auth_context(request, auth_ctx)

                from api.context.tenant import (
                    attach_tenant_context,
                    clear_tenant_context,
                    finalize_tenant_context,
                )

                tenant_ctx = await self._strategy.resolve_tenant_context(auth_ctx)
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
                from api.context.tenant import finalize_tenant_context
                await finalize_tenant_context(tenant_ctx, success=response.status_code < 400)

            return response

        except HTTPException as exc:
            if tenant_ctx:
                from api.context.tenant import finalize_tenant_context
                await finalize_tenant_context(tenant_ctx, success=False)

            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail,
                headers=exc.headers,
            )

        except Exception:
            if tenant_ctx:
                from api.context.tenant import finalize_tenant_context
                await finalize_tenant_context(tenant_ctx, success=False)
            raise

        finally:
            if tenant_ctx:
                from api.context.tenant import clear_tenant_context

                clear_tenant_context(request)
            if auth_ctx:
                clear_auth_context(request)

            if tenant_tokens:
                reset_current_tenant(*tenant_tokens)
