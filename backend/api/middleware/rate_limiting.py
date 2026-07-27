"""
S2-5: Rate Limiting Middleware

Applies rate limiting to all requests before business logic.
"""
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from core.error_codes import ErrorCode, MpangoAPIException, mpango_exception_handler
from core.rate_limiter import WINDOW_SIZE, get_rate_limiter
from core.structured_logging import get_logger

logger = get_logger(__name__)


def _ensure_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    return request_id


def _apply_rate_limit_headers(response, *, limit: int, remaining: int, reset: int):
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
    response.headers["X-RateLimit-Reset"] = str(max(0, reset))
    if response.status_code == 429:
        response.headers["Retry-After"] = str(max(0, reset))

    request_id = getattr(response, "_mpango_request_id", None)
    if request_id:
        response.headers.setdefault("X-Request-ID", request_id)
    return response


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """
    S2-5: Middleware to enforce rate limiting.

    Should be placed:
    - After RequestLoggingMiddleware (needs request_id)
    - After AuthenticationMiddleware (needs tenant/user info)
    - Before business logic
    """

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health and metrics endpoints
        if request.url.path in ["/health", "/healthz", "/health/live", "/health/ready", "/readyz", "/metrics"]:
            return await call_next(request)

        # Check rate limit
        rate_limiter = get_rate_limiter()

        try:
            _, count, limit = await rate_limiter.check_rate_limit(request)
        except MpangoAPIException as exc:
            if exc.error_code != ErrorCode.RATE_LIMIT_EXCEEDED or exc.status_code != 429:
                raise
            request_id = _ensure_request_id(request)
            response = await mpango_exception_handler(request, exc)
            response._mpango_request_id = request_id
            limit = int(exc.details.get("limit", 0))
            reset = int(exc.details.get("retry_after", exc.details.get("window_size", WINDOW_SIZE)))
            response = _apply_rate_limit_headers(
                response,
                limit=limit,
                remaining=0,
                reset=reset,
            )
            return response

        # Add rate limit headers to response
        response = await call_next(request)
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            response._mpango_request_id = request_id
        response = _apply_rate_limit_headers(
            response,
            limit=limit,
            remaining=limit - count,
            reset=WINDOW_SIZE,
        )

        return response
