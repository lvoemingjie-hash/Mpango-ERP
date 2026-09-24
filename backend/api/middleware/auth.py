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
from api.middleware.rate_limiting import enforce_rate_limit_on_auth_rejection

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

                    # PW1-R3: verified identity principal for downstream
                    # consumers (S2-5 rate limiter). Derived EXCLUSIVELY from
                    # the server-side verified JWT (auth_ctx.token) — never
                    # from client-supplied headers or claims. Identity-only
                    # tokens never reach this branch (tenant_ctx is None), so
                    # they stay on the anonymous IP bucket by design.
                    request.state.user_id = str(auth_ctx.token.user_id)

            response = await call_next(request)

            if tenant_ctx:
                from api.context.tenant import finalize_tenant_context
                await finalize_tenant_context(tenant_ctx, success=response.status_code < 400)
                # R1: notification intents are request-private and dispatched
                # ONLY after the business transaction committed successfully.
                # Rollback or commit failure leaves request.state without
                # intents (the request dies with them): zero sends.
                if response.status_code < 400:
                    await _dispatch_notification_intents(request)

            return response

        except HTTPException as exc:
            if tenant_ctx:
                from api.context.tenant import finalize_tenant_context
                await finalize_tenant_context(tenant_ctx, success=False)

            # PW1-R3: rejected-auth requests (invalid/expired/malformed token,
            # unknown tenant user) return here WITHOUT reaching the inner
            # rate-limiting middleware. Rate-limit the rejection path with the
            # same anonymous IP bucket so a flood of garbage Authorization
            # headers can never bypass rate limiting (fail-open on limiter
            # errors, consistent with the S2-5 design). Exempt paths keep the
            # exact same exclusions as RateLimitingMiddleware.
            limited = await enforce_rate_limit_on_auth_rejection(request)
            if limited is not None:
                return limited

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


async def _dispatch_notification_intents(request: Request) -> None:
    """Best-effort post-commit notification dispatch (R1).

    Intents are request-private objects placed on ``request.state`` by the
    order endpoints. Recipients are resolved from REAL retailer contact
    data at dispatch time; when a retailer has no contact channel the
    intent is skipped with a log line (no placeholder addresses or phone
    numbers exist anywhere). A send failure is logged as a post-commit
    delivery failure and never rolls back the already committed business
    transaction. No job framework: one in-request best-effort pass.
    """
    intents = getattr(request.state, "osd1_notification_intents", None)
    if not intents:
        return
    request.state.osd1_notification_intents = None
    try:
        from sqlalchemy import text as _text

        from database.session import AsyncSessionLocal
        from services.notification_service import notification_service

        async with AsyncSessionLocal() as session:
            for intent in intents:
                try:
                    row = (await session.execute(
                        _text(
                            "SELECT email, phone FROM public.retailers "
                            "WHERE id = :rid AND is_deleted IS FALSE"
                        ),
                        {"rid": str(intent.retailer_id)},
                    )).fetchone()
                    if row is None:
                        logger.warning(
                            "post_commit_notification_skipped_no_retailer",
                            extra={"event": intent.event,
                                   "order_id": str(intent.order_id)},
                        )
                        continue
                    if intent.event == "order_confirmed" and row.email:
                        await notification_service.send_email(
                            to=row.email,
                            subject=f"Order #{str(intent.order_id)[:8]} Confirmed",
                            body=(
                                f"Your order #{str(intent.order_id)[:8]} has "
                                "been confirmed. Thank you for your business!"
                            ),
                        )
                    elif intent.event == "order_fulfilled" and row.phone:
                        await notification_service.send_sms(
                            phone=row.phone,
                            message=(
                                f"Order #{str(intent.order_id)[:8]} is on "
                                "the way!"
                            ),
                        )
                    else:
                        logger.warning(
                            "post_commit_notification_skipped_no_contact",
                            extra={"event": intent.event,
                                   "order_id": str(intent.order_id)},
                        )
                except Exception as send_exc:  # noqa: BLE001
                    logger.warning(
                        "post_commit_delivery_failed",
                        extra={"event": intent.event,
                               "order_id": str(intent.order_id),
                               "error": str(send_exc)},
                    )
    except Exception as dispatch_exc:  # noqa: BLE001
        logger.warning(
            "post_commit_delivery_failed",
            extra={"error": str(dispatch_exc)},
        )
