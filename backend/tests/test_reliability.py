"""
S2-7: Reliability Tests

Tests for rate limiting, graceful shutdown, and system reliability.
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from core.rate_limiter import RateLimiter, DEFAULT_IP_LIMIT, DEFAULT_TENANT_LIMIT
from core.error_codes import ErrorCode, MpangoAPIException, register_exception_handlers


class TestRateLimiter:
    """Test rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_rate_limiter_anonymous_within_limit(self):
        """Test that anonymous requests within limit are allowed."""
        # Mock Redis
        mock_redis = AsyncMock(spec=Redis)
        mock_redis.incr = AsyncMock(return_value=50)  # Within limit
        mock_redis.expire = AsyncMock(return_value=True)

        rate_limiter = RateLimiter(redis_client=mock_redis)

        # Mock request
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.tenant_id = None
        request.state.user_id = None
        request.client = Mock()
        request.client.host = "192.168.1.100"
        request.headers = {}
        request.method = "GET"
        request.url = Mock()
        request.url.path = "/api/v1/test"

        # Check rate limit
        is_allowed, count, limit = await rate_limiter.check_rate_limit(request)

        assert is_allowed is True
        assert count == 50
        assert limit == DEFAULT_IP_LIMIT

    @pytest.mark.asyncio
    async def test_rate_limiter_anonymous_exceeds_limit(self):
        """Test that anonymous requests exceeding limit are blocked."""
        # Mock Redis
        mock_redis = AsyncMock(spec=Redis)
        mock_redis.incr = AsyncMock(return_value=101)  # Exceeds limit
        mock_redis.expire = AsyncMock(return_value=True)

        rate_limiter = RateLimiter(redis_client=mock_redis)

        # Mock request
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.tenant_id = None
        request.state.user_id = None
        request.client = Mock()
        request.client.host = "192.168.1.100"
        request.headers = {}
        request.method = "GET"
        request.url = Mock()
        request.url.path = "/api/v1/test"

        # Check rate limit - should raise exception
        with pytest.raises(MpangoAPIException) as exc_info:
            await rate_limiter.check_rate_limit(request)

        assert exc_info.value.error_code == ErrorCode.RATE_LIMIT_EXCEEDED
        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in exc_info.value.message
        assert exc_info.value.details["limit"] == DEFAULT_IP_LIMIT

    @pytest.mark.asyncio
    async def test_rate_limiter_authenticated_within_limit(self):
        """Test that authenticated requests within limit are allowed."""
        # Mock Redis
        mock_redis = AsyncMock(spec=Redis)
        mock_redis.incr = AsyncMock(return_value=500)  # Within tenant limit
        mock_redis.expire = AsyncMock(return_value=True)

        rate_limiter = RateLimiter(redis_client=mock_redis)

        # Mock request with authentication
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.tenant_id = "t_acme"
        request.state.user_id = "user-123"
        request.client = Mock()
        request.client.host = "192.168.1.100"
        request.headers = {}
        request.method = "POST"
        request.url = Mock()
        request.url.path = "/api/v1/orders"

        # Check rate limit
        is_allowed, count, limit = await rate_limiter.check_rate_limit(request)

        assert is_allowed is True
        assert count == 500
        assert limit == DEFAULT_TENANT_LIMIT

    @pytest.mark.asyncio
    async def test_rate_limiter_authenticated_exceeds_limit(self):
        """Test that authenticated requests exceeding limit are blocked."""
        # Mock Redis
        mock_redis = AsyncMock(spec=Redis)
        mock_redis.incr = AsyncMock(return_value=1001)  # Exceeds tenant limit
        mock_redis.expire = AsyncMock(return_value=True)

        rate_limiter = RateLimiter(redis_client=mock_redis)

        # Mock request with authentication
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.tenant_id = "t_acme"
        request.state.user_id = "user-123"
        request.client = Mock()
        request.client.host = "192.168.1.100"
        request.headers = {}
        request.method = "POST"
        request.url = Mock()
        request.url.path = "/api/v1/orders"

        # Check rate limit - should raise exception
        with pytest.raises(MpangoAPIException) as exc_info:
            await rate_limiter.check_rate_limit(request)

        assert exc_info.value.error_code == ErrorCode.RATE_LIMIT_EXCEEDED
        assert exc_info.value.status_code == 429
        assert exc_info.value.details["limit"] == DEFAULT_TENANT_LIMIT

    @pytest.mark.asyncio
    async def test_rate_limiter_uses_x_forwarded_for(self):
        """Test that rate limiter uses X-Forwarded-For header when present."""
        # Mock Redis
        mock_redis = AsyncMock(spec=Redis)
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)

        rate_limiter = RateLimiter(redis_client=mock_redis)

        # Mock request with X-Forwarded-For header
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.tenant_id = None
        request.state.user_id = None
        request.client = Mock()
        request.client.host = "10.0.0.1"  # Internal IP
        request.headers = {"X-Forwarded-For": "203.0.113.1, 198.51.100.1"}  # External IPs
        request.method = "GET"
        request.url = Mock()
        request.url.path = "/api/v1/test"

        # Check rate limit
        await rate_limiter.check_rate_limit(request)

        # Verify Redis key uses first IP from X-Forwarded-For
        call_args = mock_redis.incr.call_args[0][0]
        assert "203.0.113.1" in call_args

    @pytest.mark.asyncio
    async def test_rate_limiter_fails_open_on_redis_error(self):
        """Test that rate limiter allows requests if Redis fails."""
        # Mock Redis to raise exception
        mock_redis = AsyncMock(spec=Redis)
        mock_redis.incr.side_effect = Exception("Redis connection failed")

        rate_limiter = RateLimiter(redis_client=mock_redis)

        # Mock request
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.tenant_id = None
        request.state.user_id = None
        request.client = Mock()
        request.client.host = "192.168.1.100"
        request.headers = {}
        request.method = "GET"
        request.url = Mock()
        request.url.path = "/api/v1/test"

        # Check rate limit - should allow request despite Redis error
        is_allowed, count, limit = await rate_limiter.check_rate_limit(request)

        assert is_allowed is True
        assert count == 0  # No count available

    @pytest.mark.asyncio
    async def test_rate_limit_response_format(self):
        """Test that rate limit exception has correct response format."""
        # Mock Redis
        mock_redis = AsyncMock(spec=Redis)
        mock_redis.incr = AsyncMock(return_value=101)  # Exceeds limit

        rate_limiter = RateLimiter(redis_client=mock_redis)

        # Mock request
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.tenant_id = None
        request.state.user_id = None
        request.client = Mock()
        request.client.host = "192.168.1.100"
        request.headers = {}
        request.method = "GET"
        request.url = Mock()
        request.url.path = "/api/v1/test"

        # Check rate limit
        with pytest.raises(MpangoAPIException) as exc_info:
            await rate_limiter.check_rate_limit(request)

        exc = exc_info.value

        # Verify exception structure
        assert exc.error_code == ErrorCode.RATE_LIMIT_EXCEEDED
        assert exc.status_code == 429
        assert isinstance(exc.message, str)
        assert isinstance(exc.details, dict)
        assert "limit" in exc.details
        assert "window_size" in exc.details
        assert "retry_after" in exc.details


class _AuthenticatedContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.tenant_id = "00000000-0000-0000-0000-0000000000aa"
        request.state.user_id = "00000000-0000-0000-0000-0000000000bb"
        request.state.tenant_schema = "t_test"
        return await call_next(request)


class _SequencedRateLimiter:
    def __init__(self, limit: int, retry_after: int):
        self.limit = limit
        self.retry_after = retry_after
        self.count = 0

    async def check_rate_limit(self, request: Request):
        self.count += 1
        if self.count > self.limit:
            raise MpangoAPIException(
                error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
                message=f"Rate limit exceeded. Maximum {self.limit} requests per minute.",
                status_code=429,
                details={
                    "limit": self.limit,
                    "window_size": 60,
                    "retry_after": self.retry_after,
                },
            )
        return True, self.count, self.limit


def _build_rate_limit_boundary_app(*, authenticated: bool = False) -> FastAPI:
    from api.middleware.rate_limiting import RateLimitingMiddleware
    from api.middleware.request_logging import RequestLoggingMiddleware

    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(RateLimitingMiddleware)
    if authenticated:
        app.add_middleware(_AuthenticatedContextMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/probe")
    async def probe():
        return JSONResponse(status_code=200, content={"ok": True})

    return app


class TestRateLimitingMiddlewareBoundary:
    @pytest.mark.asyncio
    async def test_anonymous_limit_exceeded_returns_controlled_429(self):
        limiter = Mock()
        limiter.check_rate_limit = AsyncMock(
            side_effect=MpangoAPIException(
                error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
                message="Rate limit exceeded. Maximum 100 requests per minute.",
                status_code=429,
                details={"limit": 100, "window_size": 60, "retry_after": 37},
            )
        )

        app = _build_rate_limit_boundary_app()
        with patch("api.middleware.rate_limiting.get_rate_limiter", return_value=limiter):
            transport = ASGITransport(app=app, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get("/probe", headers={"X-Request-ID": "anon-429-red"})

        body = response.json()
        assert response.status_code == 429
        assert body["code"] == ErrorCode.RATE_LIMIT_EXCEEDED.value
        assert body["message"] == "Rate limit exceeded. Maximum 100 requests per minute."
        assert body["request_id"] == "anon-429-red"
        assert body["details"] == {"limit": 100, "window_size": 60, "retry_after": 37}
        assert response.headers["Retry-After"] == "37"
        assert response.headers["X-RateLimit-Limit"] == "100"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert response.headers["X-RateLimit-Reset"] == "37"
        assert response.headers["X-Request-ID"] == "anon-429-red"
        assert "INTERNAL_SERVER_ERROR" not in response.text
        assert "MpangoAPIException" not in response.text

    @pytest.mark.asyncio
    async def test_authenticated_limit_exceeded_returns_controlled_429(self):
        limiter = Mock()
        limiter.check_rate_limit = AsyncMock(
            side_effect=MpangoAPIException(
                error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
                message="Rate limit exceeded. Maximum 1000 requests per minute.",
                status_code=429,
                details={"limit": 1000, "window_size": 60, "retry_after": 11},
            )
        )

        app = _build_rate_limit_boundary_app(authenticated=True)
        with patch("api.middleware.rate_limiting.get_rate_limiter", return_value=limiter):
            transport = ASGITransport(app=app, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get("/probe", headers={"X-Request-ID": "auth-429"})

        body = response.json()
        assert response.status_code == 429
        assert body["code"] == ErrorCode.RATE_LIMIT_EXCEEDED.value
        assert body["message"] == "Rate limit exceeded. Maximum 1000 requests per minute."
        assert body["request_id"] == "auth-429"
        assert body["details"] == {"limit": 1000, "window_size": 60, "retry_after": 11}
        assert response.headers["Retry-After"] == "11"
        assert response.headers["X-RateLimit-Limit"] == "1000"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert response.headers["X-RateLimit-Reset"] == "11"
        assert response.headers["X-Request-ID"] == "auth-429"
        assert "INTERNAL_SERVER_ERROR" not in response.text
        assert "MpangoAPIException" not in response.text

    @pytest.mark.asyncio
    async def test_101st_anonymous_request_returns_429_never_500(self):
        limiter = _SequencedRateLimiter(limit=100, retry_after=9)
        app = _build_rate_limit_boundary_app()

        with patch("api.middleware.rate_limiting.get_rate_limiter", return_value=limiter):
            transport = ASGITransport(app=app, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                statuses = []
                final_response = None
                for request_num in range(101):
                    response = await client.get("/probe", headers={"X-Request-ID": f"anon-{request_num}"})
                    statuses.append(response.status_code)
                    final_response = response

        assert statuses[:100] == [200] * 100
        assert statuses[100] == 429
        assert 500 not in statuses
        assert final_response is not None
        assert final_response.json()["code"] == ErrorCode.RATE_LIMIT_EXCEEDED.value
        assert final_response.headers["Retry-After"] == "9"

    @pytest.mark.asyncio
    async def test_middleware_does_not_mask_unrelated_exception_types(self):
        limiter = Mock()
        limiter.check_rate_limit = AsyncMock(side_effect=RuntimeError("boom"))

        app = _build_rate_limit_boundary_app()
        with patch("api.middleware.rate_limiting.get_rate_limiter", return_value=limiter):
            transport = ASGITransport(app=app, raise_app_exceptions=False)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.get("/probe", headers={"X-Request-ID": "runtime-500"})

        body = response.json()
        assert response.status_code == 500
        assert body["code"] == ErrorCode.INTERNAL_SERVER_ERROR.value
        assert "RuntimeError" in response.text
        assert "RATE_LIMIT_EXCEEDED" not in response.text


class TestGracefulShutdown:
    """Test graceful shutdown functionality."""

    @pytest.mark.asyncio
    async def test_graceful_shutdown_closes_connections(self):
        """Test that graceful shutdown closes database and Redis connections."""
        from main import graceful_shutdown

        # Mock database engine
        with patch('database.session.async_engine') as mock_engine:
            mock_engine.dispose = AsyncMock()

            # Mock rate limiter
            with patch('core.rate_limiter.close_rate_limiter') as mock_close_limiter:
                mock_close_limiter.return_value = AsyncMock()

                # Run graceful shutdown (with short grace period for testing)
                with patch('main.SHUTDOWN_GRACE_PERIOD', 0.1):
                    await graceful_shutdown()

                # Verify connections were closed
                mock_engine.dispose.assert_called_once()
                mock_close_limiter.assert_called_once()


class TestMiddlewareUnderLoad:
    """Test that middleware works correctly under load."""

    @pytest.mark.asyncio
    async def test_logging_middleware_under_load(self):
        """Test that logging middleware works under concurrent requests."""
        from api.middleware.request_logging import RequestLoggingMiddleware

        # This is a placeholder test
        # In a real scenario, you would:
        # 1. Create multiple concurrent requests
        # 2. Verify each request gets unique request_id
        # 3. Verify logs are correctly structured
        # 4. Verify no race conditions

        assert True  # Placeholder

    @pytest.mark.asyncio
    async def test_metrics_middleware_under_load(self):
        """Test that metrics middleware works under concurrent requests."""
        from core.prometheus_metrics import PrometheusMetricsMiddleware

        # This is a placeholder test
        # In a real scenario, you would:
        # 1. Create multiple concurrent requests
        # 2. Verify metrics are correctly incremented
        # 3. Verify no race conditions in counter updates

        assert True  # Placeholder


class TestNoLegacyLogging:
    """Test that no print statements are used (enforce logger usage)."""

    def test_no_print_statements_in_core(self):
        """Test that core modules don't use print statements."""
        import os
        import re

        # Check core modules for print statements
        core_dir = os.path.join(os.path.dirname(__file__), '..', 'core')

        if not os.path.exists(core_dir):
            pytest.skip("Core directory not found")

        print_pattern = re.compile(r'^\s*print\s*\(', re.MULTILINE)

        violations = []
        for root, dirs, files in os.walk(core_dir):
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        matches = print_pattern.findall(content)
                        if matches:
                            violations.append(filepath)

        # Allow print statements in test files and config.py (runs before logging setup)
        violations = [v for v in violations if 'test_' not in v and 'config.py' not in v]

        assert len(violations) == 0, f"Found print statements in: {violations}"
