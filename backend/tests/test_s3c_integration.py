"""
S3-C: Integration tests for cached endpoints

Tests that caching is properly applied to API endpoints.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.auth import _get_user_with_permissions_cached
from api.v1.skus import _list_skus_cached


@pytest.mark.asyncio
async def test_auth_me_caching():
    """Test that GET /auth/me uses caching."""
    # Mock database session
    mock_db = AsyncMock(spec=AsyncSession)
    
    # Mock user data
    mock_user = MagicMock()
    mock_user.id = "123e4567-e89b-12d3-a456-426614174000"
    mock_user.email = "test@example.com"
    mock_user.full_name = "Test User"
    
    # Mock roles
    mock_role = MagicMock()
    mock_role.name = "admin"
    
    # Mock permissions
    mock_perm = MagicMock()
    mock_perm.code = "users:read"
    mock_role.permissions = [mock_perm]
    mock_user.roles = [mock_role]
    
    # Mock get_user_with_permissions
    with patch('api.v1.auth.get_user_with_permissions', return_value=mock_user):
        # Mock Redis to simulate cache miss
        with patch('core.cache.get_redis_client') as mock_get_client:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None  # Cache miss
            mock_redis.setex = AsyncMock()
            mock_get_client.return_value = mock_redis
            
            # Call cached function
            result = await _get_user_with_permissions_cached("123e4567-e89b-12d3-a456-426614174000", mock_db)
            
            # Verify result
            assert result is not None
            assert result["id"] == "123e4567-e89b-12d3-a456-426614174000"
            assert result["email"] == "test@example.com"
            assert result["full_name"] == "Test User"
            assert "admin" in result["roles"]
            assert "users:read" in result["permissions"]
            
            # Verify Redis was called
            mock_redis.get.assert_called_once()
            mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_skus_list_caching():
    """Test that GET /skus uses caching."""
    # Mock database session
    mock_db = AsyncMock(spec=AsyncSession)
    
    # Mock SKU data
    mock_sku = MagicMock()
    mock_sku.id = "sku-123"
    mock_sku.sku_code = "SKU001"
    mock_sku.name = "Test Product"
    mock_sku.description = "Test Description"
    mock_sku.unit = "pcs"
    mock_sku.category = "Electronics"
    mock_sku.is_active = True
    mock_sku.created_at = "2024-01-01T00:00:00"
    mock_sku.updated_at = "2024-01-01T00:00:00"
    
    # Mock SKUService
    with patch('api.v1.skus.SKUService') as mock_service_class:
        mock_service = MagicMock()
        mock_service.list_skus = AsyncMock(return_value=([mock_sku], 1))
        mock_service_class.return_value = mock_service
        
        # Mock Redis to simulate cache miss
        with patch('core.cache.get_redis_client') as mock_get_client:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None  # Cache miss
            mock_redis.setex = AsyncMock()
            mock_get_client.return_value = mock_redis
            
            # Call cached function
            result = await _list_skus_cached(mock_db, page=1, size=10, is_active=True, q=None)
            
            # Verify result
            assert result is not None
            assert "items" in result
            assert "total" in result
            assert result["total"] == 1
            assert len(result["items"]) == 1
            
            # Verify Redis was called
            mock_redis.get.assert_called_once()
            mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_cache_key_format_auth_me():
    """Test that auth_me cache key format is correct."""
    user_id = "123e4567-e89b-12d3-a456-426614174000"
    
    with patch('api.v1.auth.get_user_with_permissions', return_value=None):
        with patch('core.cache.get_redis_client') as mock_get_client:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            mock_redis.setex = AsyncMock()
            mock_get_client.return_value = mock_redis
            
            mock_db = AsyncMock(spec=AsyncSession)
            await _get_user_with_permissions_cached(user_id, mock_db)
            
            # Verify cache key format
            call_args = mock_redis.get.call_args[0][0]
            assert call_args == f"auth_me:{user_id}"


@pytest.mark.asyncio
async def test_cache_key_format_skus_list():
    """Test that skus_list cache key format is correct."""
    with patch('api.v1.skus.SKUService') as mock_service_class:
        mock_service = MagicMock()
        mock_service.list_skus = AsyncMock(return_value=([], 0))
        mock_service_class.return_value = mock_service
        
        with patch('core.cache.get_redis_client') as mock_get_client:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            mock_redis.setex = AsyncMock()
            mock_get_client.return_value = mock_redis
            
            mock_db = AsyncMock(spec=AsyncSession)
            await _list_skus_cached(mock_db, page=1, size=10, is_active=True, q=None)
            
            # Verify cache key format
            call_args = mock_redis.get.call_args[0][0]
            assert call_args.startswith("skus_list:")
            assert "1" in call_args  # page
            assert "10" in call_args  # size
            assert "True" in call_args  # is_active


@pytest.mark.asyncio
async def test_cache_ttl_auth_me():
    """Test that auth_me cache TTL is 30 seconds."""
    mock_user = MagicMock()
    mock_user.id = "123"
    mock_user.email = "test@example.com"
    mock_user.full_name = "Test"
    mock_user.roles = []
    
    with patch('api.v1.auth.get_user_with_permissions', return_value=mock_user):
        with patch('core.cache.get_redis_client') as mock_get_client:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            mock_redis.setex = AsyncMock()
            mock_get_client.return_value = mock_redis
            
            mock_db = AsyncMock(spec=AsyncSession)
            await _get_user_with_permissions_cached("123", mock_db)
            
            # Verify TTL is 30 seconds
            call_args = mock_redis.setex.call_args[0]
            ttl = call_args[1].total_seconds()
            assert ttl == 30


@pytest.mark.asyncio
async def test_cache_ttl_skus_list():
    """Test that skus_list cache TTL is 60 seconds."""
    with patch('api.v1.skus.SKUService') as mock_service_class:
        mock_service = MagicMock()
        mock_service.list_skus = AsyncMock(return_value=([], 0))
        mock_service_class.return_value = mock_service
        
        with patch('core.cache.get_redis_client') as mock_get_client:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            mock_redis.setex = AsyncMock()
            mock_get_client.return_value = mock_redis
            
            mock_db = AsyncMock(spec=AsyncSession)
            await _list_skus_cached(mock_db, page=1, size=10, is_active=True, q=None)
            
            # Verify TTL is 60 seconds
            call_args = mock_redis.setex.call_args[0]
            ttl = call_args[1].total_seconds()
            assert ttl == 60


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
