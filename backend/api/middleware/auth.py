"""Authentication middleware for Mpango ERP."""
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api.context.auth import AuthContext, attach_auth_context, clear_auth_context
from api.middleware.request_logging import update_request_context_with_auth
from auth.strategy import AuthStrategy
from core.structured_logging import get_logger
from core.error_codes import ErrorCode, MpangoAPIException
from db.tenant_filter import reset_current_tenant, set_current_tenant

__all__ = ["AuthenticationMiddleware"]

logger = get_logger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Decode JWT tokens and attach auth/tenant context to request.state.

    S2-2: Updates logging context with tenant and user information.
    """

    def __init__(self, app, *, strategy: AuthStrategy):
        super().__init__(app)
        self._strategy = strategy

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
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

                # H-Fix-01: resolve_tenant_context returns None for
                # identity-only JWTs (no tenant_id/tenant_schema).
                tenant_ctx = await self._strategy.resolve_tenant_context(auth_ctx)

                if tenant_ctx is not None:
                    attach_tenant_context(request, tenant_ctx)

                    tenant_tokens = set_current_tenant(
                        tenant_id=str(tenant_ctx.tenant_id),
                        tenant_schema=tenant_ctx.tenant_schema,
                    )

                    # S2.5 Batch B: Enforce tenant isolation - fail-safe check
                    if not tenant_ctx.tenant_schema:
                        logger.critical(
                            "Tenant isolation violation: tenant_schema is missing for authenticated request",
                            extra={
                                "tenant_id": str(tenant_ctx.tenant_id),
                                "auth_context": str(auth_ctx)
                            }
                        )
                        raise MpangoAPIException(
                            error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                            message="Tenant isolation check failed",
                            status_code=500
                        )

                    # S2-2: Update logging context with tenant and user
                    update_request_context_with_auth(
                        tenant_schema=tenant_ctx.tenant_schema,
                        user_id=str(tenant_ctx.tenant_id)
                    )

                    # Also update request.state for metrics
                    request.state.tenant_id = str(tenant_ctx.tenant_id)
                    request.state.tenant_schema = tenant_ctx.tenant_schema

            response = await call_next(request)

            if tenant_ctx:
                from api.context.tenant import finalize_tenant_context
                await finalize_tenant_context(tenant_ctx, success=response.status_code < 400)

            return response

        except HTTPException as exc:
            if tenant_ctx:
                from api.context.tenant import finalize_tenant_context
                await finalize_tenant_context(tenant_ctx, success=False)

            # BaseHTTPMiddleware cannot propagate HTTPException to FastAPI's
            # exception handlers — re-raising would produce an unhandled 500.
            # Return a JSONResponse directly with the correct status code.
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            return JSONResponse(
                status_code=exc.status_code,
                content=detail,
                headers=getattr(exc, "headers", None),
            )

        except Exception as e:
            if tenant_ctx:
                from api.context.tenant import finalize_tenant_context
                await finalize_tenant_context(tenant_ctx, success=False)

            logger.error(f"Authentication middleware error: {type(e).__name__}", exc_info=e)
            raise

        finally:
            if tenant_ctx:
                from api.context.tenant import clear_tenant_context

                clear_tenant_context(request)
            if auth_ctx:
                clear_auth_context(request)

            if tenant_tokens:
                reset_current_tenant(*tenant_tokens)
