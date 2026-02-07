"""
S3-C: Cache functionality tests

Tests the Redis read-through cache implementation.
"""
import pytest
from unittest.mock import AsyncMock, patch
from core.cache import (
    cache,
    serialize_value,
    deserialize_value,
    default_key_builder,
    get_redis_client,
    close_redis_client
)
from pydantic import BaseModel


class TestUser(BaseModel):
    """Test Pydantic model for cache tests."""
    id: str
    name: str
    email: str


@pytest.mark.asyncio
async def test_serialize_deserialize_pydantic():
    """Test serialization/deserialization of Pydantic models."""
    user = TestUser(id="123", name="Test User", email="test@example.com")
    
    # Serialize
    serialized = serialize_value(user)
    assert isinstance(serialized, str)
    assert "123" in serialized
    assert "Test User" in serialized
    
    # Deserialize
    deserialized = deserialize_value(serialized, TestUser)
    assert isinstance(deserialized, TestUser)
    assert deserialized.id == "123"
    assert deserialized.name == "Test User"
    assert deserialized.email == "test@example.com"


@pytest.mark.asyncio
async def test_serialize_deserialize_dict():
    """Test serialization/deserialization of dicts."""
    data = {"key": "value", "number": 42}
    
    # Serialize
    serialized = serialize_value(data)
    assert isinstance(serialized, str)
    
    # Deserialize
    deserialized = deserialize_value(serialized, dict)
    assert isinstance(deserialized, dict)
    assert deserialized["key"] == "value"
    assert deserialized["number"] == 42


def test_default_key_builder():
    """Test default cache key builder."""
    # With args only
    key = default_key_builder("arg1", "arg2")
    assert key == "arg1:arg2"
    
    # With kwargs only
    key = default_key_builder(page=1, size=10)
    assert key == "page=1:size=10"
    
    # With both
    key = default_key_builder("user", page=1, size=10)
    assert key == "user:page=1:size=10"
    
    # Empty
    key = default_key_builder()
    assert key == "default"


@pytest.mark.asyncio
async def test_cache_decorator_cache_miss():
    """Test cache decorator on cache miss (first call)."""
    call_count = 0
    
    @cache(ttl_seconds=60, key_prefix="test")
    async def expensive_function(user_id: str) -> dict:
        nonlocal call_count
        call_count += 1
        return {"id": user_id, "name": "Test User"}
    
    # Mock Redis to simulate cache miss
    with patch('core.cache.get_redis_client') as mock_get_client:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Cache miss
        mock_redis.setex = AsyncMock()
        mock_get_client.return_value = mock_redis
        
        # First call - should execute function
        result = await expensive_function("123")
        
        assert result == {"id": "123", "name": "Test User"}
        assert call_count == 1
        
        # Verify Redis was called
        mock_redis.get.assert_called_once()
        mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_cache_decorator_cache_hit():
    """Test cache decorator on cache hit (cached data)."""
    call_count = 0
    
    @cache(ttl_seconds=60, key_prefix="test")
    async def expensive_function(user_id: str) -> dict:
        nonlocal call_count
        call_count += 1
        return {"id": user_id, "name": "Test User"}
    
    # Mock Redis to simulate cache hit
    cached_data = '{"id": "123", "name": "Cached User"}'
    
    with patch('core.cache.get_redis_client') as mock_get_client:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = cached_data  # Cache hit
        mock_get_client.return_value = mock_redis
        
        # Call should return cached data without executing function
        result = await expensive_function("123")
        
        assert result == {"id": "123", "name": "Cached User"}
        assert call_count == 0  # Function not called
        
        # Verify Redis was called
        mock_redis.get.assert_called_once()
        mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_cache_decorator_with_pydantic():
    """Test cache decorator with Pydantic models."""
    call_count = 0
    
    @cache(ttl_seconds=60, key_prefix="user")
    async def get_user(user_id: str) -> TestUser:
        nonlocal call_count
        call_count += 1
        return TestUser(id=user_id, name="Test User", email="test@example.com")
    
    # Mock Redis to simulate cache miss then hit
    with patch('core.cache.get_redis_client') as mock_get_client:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Cache miss
        mock_redis.setex = AsyncMock()
        mock_get_client.return_value = mock_redis
        
        # First call - cache miss
        result = await get_user("123")
        
        assert isinstance(result, TestUser)
        assert result.id == "123"
        assert call_count == 1


@pytest.mark.asyncio
async def test_cache_decorator_error_handling():
    """Test cache decorator handles Redis errors gracefully."""
    call_count = 0
    
    @cache(ttl_seconds=60, key_prefix="test")
    async def expensive_function(user_id: str) -> dict:
        nonlocal call_count
        call_count += 1
        return {"id": user_id, "name": "Test User"}
    
    # Mock Redis to raise error
    with patch('core.cache.get_redis_client') as mock_get_client:
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis connection error")
        mock_get_client.return_value = mock_redis
        
        # Should still execute function despite Redis error
        result = await expensive_function("123")
        
        assert result == {"id": "123", "name": "Test User"}
        assert call_count == 1


@pytest.mark.asyncio
async def test_cache_key_with_custom_builder():
    """Test cache decorator with custom key builder."""
    def custom_key_builder(user_id: str, **kwargs) -> str:
        return f"custom:{user_id}"
    
    @cache(ttl_seconds=60, key_prefix="test", key_builder=custom_key_builder)
    async def expensive_function(user_id: str) -> dict:
        return {"id": user_id}
    
    with patch('core.cache.get_redis_client') as mock_get_client:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.setex = AsyncMock()
        mock_get_client.return_value = mock_redis
        
        await expensive_function("123")
        
        # Verify custom key was used
        mock_redis.get.assert_called_once()
        call_args = mock_redis.get.call_args[0][0]
        assert call_args == "test:custom:123"


@pytest.mark.asyncio
async def test_redis_client_lifecycle():
    """Test Redis client initialization and cleanup."""
    # Get client
    client = await get_redis_client()
    assert client is not None
    
    # Get again - should return same instance
    client2 = await get_redis_client()
    assert client2 is client
    
    # Close client
    await close_redis_client()
    
    # Get after close - should create new instance
    client3 = await get_redis_client()
    assert client3 is not None
    
    # Cleanup
    await close_redis_client()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
