"""
S2-5: Rate Limiting System

Implements Redis-backed rate limiting with:
- Fixed window strategy
- IP-based limiting for anonymous requests
- Tenant+User-based limiting for authenticated requests
"""
import time
from typing import Optional, Tuple
from redis.asyncio import Redis
from fastapi import Request

from core.config import get_settings
from core.structured_logging import get_logger
from core.error_codes import ErrorCode, MpangoAPIException

logger = get_logger(__name__)

# Rate limit configurations
DEFAULT_IP_LIMIT = 100  # requests per minute for anonymous users
DEFAULT_TENANT_LIMIT = 1000  # requests per minute per tenant
WINDOW_SIZE = 60  # seconds (1 minute)


class RateLimiter:
    """
    S2-5: Redis-backed rate limiter using Fixed Window algorithm.
    
    Strategy:
    - Anonymous requests: Limited by IP address (100 req/min)
    - Authenticated requests: Limited by tenant_id + user_id (1000 req/min)
    
    Redis Keys:
    - rate_limit:ip:{ip_address}:{window} -> count
    - rate_limit:tenant:{tenant_id}:{user_id}:{window} -> count
    """
    
    def __init__(self, redis_client: Optional[Redis] = None):
        """
        Initialize rate limiter.
        
        Args:
            redis_client: Optional Redis client. If None, creates new client from config.
        """
        self.settings = get_settings()
        self._redis: Optional[Redis] = redis_client
        self._redis_url = self.settings.REDIS_URL
    
    async def _get_redis(self) -> Redis:
        """Get or create Redis client."""
        if self._redis is None:
            self._redis = Redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        return self._redis
    
    async def check_rate_limit(self, request: Request) -> Tuple[bool, int, int]:
        """
        Check if request is within rate limit.
        
        Args:
            request: FastAPI request object
            
        Returns:
            Tuple of (is_allowed, current_count, limit)
            
        Raises:
            MpangoAPIException: If rate limit exceeded
        """
        # Determine rate limit key and limit
        key, limit = await self._get_rate_limit_key(request)
        
        # Get current window
        current_window = int(time.time() / WINDOW_SIZE)
        redis_key = f"{key}:{current_window}"
        
        try:
            redis = await self._get_redis()
            
            # Increment counter
            count = await redis.incr(redis_key)
            
            # Set expiry on first request in window
            if count == 1:
                await redis.expire(redis_key, WINDOW_SIZE)
            
            # Check if limit exceeded
            if count > limit:
                logger.warning(
                    f"Rate limit exceeded",
                    extra={
                        "rate_limit_key": key,
                        "count": count,
                        "limit": limit,
                        "window": current_window
                    }
                )
                
                # Record metric
                from core.prometheus_metrics import http_requests_total
                tenant = getattr(request.state, 'tenant_id', 'unknown')
                http_requests_total.labels(
                    method=request.method,
                    route=request.url.path,
                    status_code=429,
                    tenant=tenant
                ).inc()
                
                raise MpangoAPIException(
                    error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
                    message=f"Rate limit exceeded. Maximum {limit} requests per minute.",
                    status_code=429,
                    details={
                        "limit": limit,
                        "window_size": WINDOW_SIZE,
                        "retry_after": WINDOW_SIZE - (int(time.time()) % WINDOW_SIZE)
                    }
                )
            
            return True, count, limit
            
        except MpangoAPIException:
            # Re-raise rate limit exception
            raise
        except Exception as e:
            # Log error but don't block request if Redis fails
            logger.error(
                f"Rate limiter error: {type(e).__name__}",
                exc_info=e,
                extra={"redis_key": redis_key}
            )
            # Fail open - allow request if rate limiter fails
            return True, 0, limit
    
    async def _get_rate_limit_key(self, request: Request) -> Tuple[str, int]:
        """
        PW1-R3: determine the rate limit key from the VERIFIED server-side
        JWT context only.

        `request.state.tenant_id` / `request.state.user_id` are attached
        exclusively by AuthenticationMiddleware, derived from the token that
        JwtAuthStrategy verified server-side (never from client headers or
        self-declared claims). A contextual JWT therefore maps to
        ``rate_limit:tenant:{tenant_id}:{user_id}`` (limit 1000); everything
        else — anonymous, identity-only, malformed or invalid Authorization —
        maps to the per-IP bucket (limit 100). Invalid auth can never widen
        the limit: rejection-path requests carry no tenant state, and the
        AuthenticationMiddleware rejection hook applies this same IP bucket.

        Returns:
            Tuple of (redis_key_prefix, limit)
        """
        # Verified contextual context (set ONLY by AuthenticationMiddleware)
        tenant_id = getattr(request.state, 'tenant_id', None)
        user_id = getattr(request.state, 'user_id', None)
        if tenant_id is not None and user_id is None:
            # Defensive: a tenant_id without a verified user_id must never
            # downgrade into an unclassified bucket ambiguity — treat as
            # anonymous (IP bucket) rather than trusting a partial context.
            tenant_id = None
        
        if tenant_id and user_id:
            # Authenticated: Use tenant + user
            key = f"rate_limit:tenant:{tenant_id}:{user_id}"
            limit = DEFAULT_TENANT_LIMIT
            
            logger.debug(
                "Rate limit check (authenticated)",
                extra={
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "limit": limit
                }
            )
        else:
            # Anonymous: Use IP address
            client_ip = self._get_client_ip(request)
            key = f"rate_limit:ip:{client_ip}"
            limit = DEFAULT_IP_LIMIT
            
            logger.debug(
                "Rate limit check (anonymous)",
                extra={
                    "client_ip": client_ip,
                    "limit": limit
                }
            )
        
        return key, limit
    
    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request.
        
        Checks X-Forwarded-For header first (for proxies), then falls back to client.host.
        """
        # Check X-Forwarded-For header (for proxies/load balancers)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take first IP in chain
            return forwarded_for.split(",")[0].strip()
        
        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        # Fall back to direct client IP
        if request.client:
            return request.client.host
        
        return "unknown"
    
    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


async def close_rate_limiter():
    """Close global rate limiter."""
    global _rate_limiter
    if _rate_limiter:
        await _rate_limiter.close()
        _rate_limiter = None
