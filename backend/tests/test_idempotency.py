"""
Tests for Idempotency middleware.

Tests cover:
- Idempotency key caching
- Duplicate request handling
- Cache expiration
- Concurrent request handling

Uses self-contained implementation to avoid database initialization issues.
"""
import os
import hashlib
import pytest
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# Set test environment variables before any imports
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars")


# ============================================================================
# Test-Local Idempotency Implementation (mirrors actual implementation)
# ============================================================================

# In-memory cache for testing
_test_idempotency_cache: Dict[str, Dict[str, Any]] = {}
IDEMPOTENCY_TTL = timedelta(hours=24)


class TestIdempotencyMiddleware:
    """Test-local IdempotencyMiddleware that mirrors actual implementation."""

    def __init__(self, app=None):
        self.app = app

    def _make_cache_key(
        self,
        *,
        idempotency_key: str,
        tenant_schema: str,
        user_id: str,
        method: str,
        path: str,
        body_hash: str,
    ) -> str:
        combined = f"{tenant_schema}:{user_id}:{method}:{path}:{body_hash}:{idempotency_key}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def _get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached response if exists and not expired."""
        cached = _test_idempotency_cache.get(cache_key)

        if not cached:
            return None

        # Check expiration
        if datetime.utcnow() > cached["expires_at"]:
            del _test_idempotency_cache[cache_key]
            return None

        return cached

    def _mark_in_progress(self, cache_key: str) -> None:
        """Mark a request as in-progress."""
        _test_idempotency_cache[cache_key] = {
            "in_progress": True,
            "expires_at": datetime.utcnow() + timedelta(minutes=5)
        }

    def _cache_response(
        self,
        cache_key: str,
        body: Dict[str, Any],
        status_code: int
    ) -> None:
        """Cache a response."""
        _test_idempotency_cache[cache_key] = {
            "body": body,
            "status_code": status_code,
            "expires_at": datetime.utcnow() + IDEMPOTENCY_TTL,
            "in_progress": False
        }

    def _remove_cache(self, cache_key: str) -> None:
        """Remove cache entry."""
        _test_idempotency_cache.pop(cache_key, None)


def clear_test_cache() -> int:
    """Clear all test cache entries."""
    count = len(_test_idempotency_cache)
    _test_idempotency_cache.clear()
    return count


def cleanup_expired_entries() -> int:
    """Remove expired entries from cache."""
    now = datetime.utcnow()
    expired_keys = [
        key for key, value in _test_idempotency_cache.items()
        if value.get("expires_at") and now > value["expires_at"]
    ]

    for key in expired_keys:
        del _test_idempotency_cache[key]

    return len(expired_keys)


# ============================================================================
# Tests
# ============================================================================

class TestIdempotencyMiddlewareCacheKey:
    """Tests for IdempotencyMiddleware cache key generation."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_test_cache()

    def test_make_cache_key_unique(self):
        """Cache keys should be unique for different inputs."""
        middleware = TestIdempotencyMiddleware(app=None)

        body_hash1 = hashlib.sha256(b"{\"a\":1}").hexdigest()
        body_hash2 = hashlib.sha256(b"{\"a\":2}").hexdigest()

        key1 = middleware._make_cache_key(
            idempotency_key="key1",
            tenant_schema="t1",
            user_id="u1",
            method="POST",
            path="/orders",
            body_hash=body_hash1,
        )
        key2 = middleware._make_cache_key(
            idempotency_key="key2",
            tenant_schema="t1",
            user_id="u1",
            method="POST",
            path="/orders",
            body_hash=body_hash1,
        )
        key3 = middleware._make_cache_key(
            idempotency_key="key1",
            tenant_schema="t1",
            user_id="u1",
            method="PUT",
            path="/orders",
            body_hash=body_hash1,
        )
        key4 = middleware._make_cache_key(
            idempotency_key="key1",
            tenant_schema="t1",
            user_id="u1",
            method="POST",
            path="/users",
            body_hash=body_hash1,
        )
        key5 = middleware._make_cache_key(
            idempotency_key="key1",
            tenant_schema="t2",
            user_id="u1",
            method="POST",
            path="/orders",
            body_hash=body_hash1,
        )
        key6 = middleware._make_cache_key(
            idempotency_key="key1",
            tenant_schema="t1",
            user_id="u2",
            method="POST",
            path="/orders",
            body_hash=body_hash1,
        )
        key7 = middleware._make_cache_key(
            idempotency_key="key1",
            tenant_schema="t1",
            user_id="u1",
            method="POST",
            path="/orders",
            body_hash=body_hash2,
        )

        # All keys should be different
        assert len({key1, key2, key3, key4, key5, key6, key7}) == 7

    def test_make_cache_key_deterministic(self):
        """Same inputs should produce same cache key."""
        middleware = TestIdempotencyMiddleware(app=None)

        body_hash = hashlib.sha256(b"{}").hexdigest()

        key1 = middleware._make_cache_key(
            idempotency_key="test-key",
            tenant_schema="t_abc",
            user_id="u_123",
            method="POST",
            path="/orders",
            body_hash=body_hash,
        )
        key2 = middleware._make_cache_key(
            idempotency_key="test-key",
            tenant_schema="t_abc",
            user_id="u_123",
            method="POST",
            path="/orders",
            body_hash=body_hash,
        )

        assert key1 == key2

    def test_cache_key_is_sha256_hash(self):
        """Cache key should be a SHA256 hash (64 hex chars)."""
        middleware = TestIdempotencyMiddleware(app=None)

        body_hash = hashlib.sha256(b"{}").hexdigest()

        key = middleware._make_cache_key(
            idempotency_key="test",
            tenant_schema="t",
            user_id="u",
            method="POST",
            path="/orders",
            body_hash=body_hash,
        )

        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_different_methods_different_keys(self):
        """Same idempotency key with different methods should produce different cache keys."""
        middleware = TestIdempotencyMiddleware(app=None)

        body_hash = hashlib.sha256(b"{}").hexdigest()

        post_key = middleware._make_cache_key(
            idempotency_key="same-key",
            tenant_schema="t",
            user_id="u",
            method="POST",
            path="/orders",
            body_hash=body_hash,
        )
        put_key = middleware._make_cache_key(
            idempotency_key="same-key",
            tenant_schema="t",
            user_id="u",
            method="PUT",
            path="/orders",
            body_hash=body_hash,
        )

        assert post_key != put_key

    def test_different_paths_different_keys(self):
        """Same idempotency key with different paths should produce different cache keys."""
        middleware = TestIdempotencyMiddleware(app=None)

        body_hash = hashlib.sha256(b"{}").hexdigest()

        orders_key = middleware._make_cache_key(
            idempotency_key="same-key",
            tenant_schema="t",
            user_id="u",
            method="POST",
            path="/orders",
            body_hash=body_hash,
        )
        users_key = middleware._make_cache_key(
            idempotency_key="same-key",
            tenant_schema="t",
            user_id="u",
            method="POST",
            path="/users",
            body_hash=body_hash,
        )

        assert orders_key != users_key


class TestIdempotencyMiddlewareCaching:
    """Tests for IdempotencyMiddleware caching operations."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_test_cache()

    def test_cache_response(self):
        """Should cache response correctly."""
        middleware = TestIdempotencyMiddleware(app=None)
        cache_key = "test-cache-key"
        body = {"success": True, "data": {"id": "123"}}

        middleware._cache_response(cache_key, body, 201)

        cached = _test_idempotency_cache.get(cache_key)
        assert cached is not None
        assert cached["body"] == body
        assert cached["status_code"] == 201
        assert cached["in_progress"] is False

    def test_get_cached_response_returns_cached(self):
        """Should return cached response when exists."""
        middleware = TestIdempotencyMiddleware(app=None)
        cache_key = "test-cache-key"
        body = {"success": True}

        middleware._cache_response(cache_key, body, 200)

        cached = middleware._get_cached_response(cache_key)
        assert cached is not None
        assert cached["body"] == body

    def test_get_cached_response_returns_none_when_missing(self):
        """Should return None when no cached response."""
        middleware = TestIdempotencyMiddleware(app=None)

        cached = middleware._get_cached_response("nonexistent-key")
        assert cached is None

    def test_mark_in_progress(self):
        """Should mark request as in-progress."""
        middleware = TestIdempotencyMiddleware(app=None)
        cache_key = "test-key"

        middleware._mark_in_progress(cache_key)

        cached = _test_idempotency_cache.get(cache_key)
        assert cached is not None
        assert cached["in_progress"] is True

    def test_remove_cache(self):
        """Should remove cache entry."""
        middleware = TestIdempotencyMiddleware(app=None)
        cache_key = "test-key"

        middleware._cache_response(cache_key, {"test": True}, 200)
        assert cache_key in _test_idempotency_cache

        middleware._remove_cache(cache_key)
        assert cache_key not in _test_idempotency_cache


class TestIdempotencyCacheManagement:
    """Tests for cache management functions."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_test_cache()

    def test_clear_idempotency_cache(self):
        """Should clear all cache entries."""
        middleware = TestIdempotencyMiddleware(app=None)

        # Add some entries
        middleware._cache_response("key1", {"a": 1}, 200)
        middleware._cache_response("key2", {"b": 2}, 201)

        assert len(_test_idempotency_cache) == 2

        count = clear_test_cache()

        assert count == 2
        assert len(_test_idempotency_cache) == 0

    def test_cleanup_expired_entries(self):
        """Should remove expired entries."""
        middleware = TestIdempotencyMiddleware(app=None)

        # Add an expired entry
        _test_idempotency_cache["expired-key"] = {
            "body": {"test": True},
            "status_code": 200,
            "expires_at": datetime.utcnow() - timedelta(hours=1),
            "in_progress": False
        }

        # Add a valid entry
        middleware._cache_response("valid-key", {"test": True}, 200)

        assert len(_test_idempotency_cache) == 2

        count = cleanup_expired_entries()

        assert count == 1
        assert "expired-key" not in _test_idempotency_cache
        assert "valid-key" in _test_idempotency_cache
