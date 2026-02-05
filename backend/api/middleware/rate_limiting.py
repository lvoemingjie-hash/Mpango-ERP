"""
S2-5: Rate Limiting Middleware

Applies rate limiting to all requests before business logic.
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from core.rate_limiter import get_rate_limiter
from core.structured_logging import get_logger

logger = get_logger(__name__)


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
            is_allowed, count, limit = await rate_limiter.check_rate_limit(request)
            
            # Add rate limit headers to response
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
            response.headers["X-RateLimit-Reset"] = str(60)  # Window size in seconds
            
            return response
            
        except Exception as e:
            # Rate limit exception will be caught by global exception handler
            raise
