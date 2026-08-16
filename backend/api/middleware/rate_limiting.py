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


# PW1-R3: single source of truth for rate-limit exclusions. Shared by
# RateLimitingMiddleware and the auth-middleware rejection path so both apply
# EXACTLY the same exemptions (health/metrics must never be limited).
RATE_LIMIT_EXEMPT_PATHS = frozenset(
    {"/health", "/healthz", "/health/live", "/health/ready", "/readyz", "/metrics"}
)


async def _rate_limit_rejection_response(request: Request, exc: MpangoAPIException):
    """Build the 429 response with the exact S2-5 rate-limit headers.

    Non-rate-limit exceptions are re-raised unchanged.
    """
    if exc.error_code != ErrorCode.RATE_LIMIT_EXCEEDED or exc.status_code != 429:
        raise exc
    request_id = _ensure_request_id(request)
    response = await mpango_exception_handler(request, exc)
    response._mpango_request_id = request_id
    limit = int(exc.details.get("limit", 0))
    reset = int(exc.details.get("retry_after", exc.details.get("window_size", WINDOW_SIZE)))
    return _apply_rate_limit_headers(
        response,
        limit=limit,
        remaining=0,
        reset=reset,
    )


async def enforce_rate_limit_on_auth_rejection(request: Request):
    """PW1-R3: rate-limit the authentication middleware's rejection path.

    Requests whose Authorization is malformed/invalid/expired — or whose tenant
    context fails to resolve — are answered directly by AuthenticationMiddleware
    and never reach the inner RateLimitingMiddleware. Without this hook a flood
    of garbage Authorization headers would bypass rate limiting entirely. The
    rejection path uses the SAME anonymous IP bucket (limit 100) and the SAME
    exempt-path list; limiter failures fail open (request proceeds to the
    original 401), consistent with the S2-5 design.

    Returns a 429 Response when the IP bucket is exhausted, else None.
    """
    if request.url.path in RATE_LIMIT_EXEMPT_PATHS:
        return None

    rate_limiter = get_rate_limiter()
    try:
        await rate_limiter.check_rate_limit(request)
    except MpangoAPIException as exc:
        return await _rate_limit_rejection_response(request, exc)
    return None


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
    - INSIDE AuthenticationMiddleware (needs the verified tenant/user context
      that PW1-R3 attaches to request.state) — i.e. registered BEFORE
      AuthenticationMiddleware in configure_app, because Starlette makes the
      last-registered middleware the outermost.
    - Before business logic
    """

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health and metrics endpoints
        if request.url.path in RATE_LIMIT_EXEMPT_PATHS:
            return await call_next(request)

        # Check rate limit
        rate_limiter = get_rate_limiter()

        try:
            _, count, limit = await rate_limiter.check_rate_limit(request)
        except MpangoAPIException as exc:
            return await _rate_limit_rejection_response(request, exc)

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
