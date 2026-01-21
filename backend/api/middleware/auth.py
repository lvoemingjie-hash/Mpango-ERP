"""Authentication middleware for Mpango ERP."""
import uuid
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

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

__all__ = ["AuthenticationMiddleware"]


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

        try:
            raw_token = extract_bearer_token(request)

            if raw_token:
                auth_ctx = resolve_auth_context(raw_token)
                attach_auth_context(request, auth_ctx)

                tenant_ctx = await resolve_tenant_context(auth_ctx.token)
                attach_tenant_context(request, tenant_ctx)

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
