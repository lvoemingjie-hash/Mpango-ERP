"""
S3-C: Integration tests for cached endpoints

Tests that caching is properly applied to API endpoints.

R1 SKU-cache tenant isolation: every mock session used with
`_list_skus_cached` explicitly carries a tenant schema in `session.info`
(the new cache-key contract — the tenant dimension comes from the actual
tenant-scoped DB session, and a session without a valid tenant schema is
rejected BEFORE any Redis access).
"""
import json

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.auth import _get_user_with_permissions_cached
from api.v1.skus import SkuListCacheTenantContextError, _list_skus_cached

# Explicit tenant schema carried by every mock sku-list session (the new
# key contract: skus_list:{tenant_schema}:{page}:{size}:{is_active}:{q}).
S3C_TENANT_SCHEMA = "t_s3c_cache_probe"
OTHER_TENANT_SCHEMA = "t_s3c_other_tenant"


def _tenant_mock_db(tenant_schema: str = S3C_TENANT_SCHEMA):
    """AsyncSession mock that EXPLICITLY carries a tenant schema."""
    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.info = {"tenant_schema": tenant_schema}
    return mock_db


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
    # Mock database session (explicit tenant schema — new key contract)
    mock_db = _tenant_mock_db()

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
    """Test that skus_list cache key format is the exact tenant-scoped key."""
    with patch('api.v1.skus.SKUService') as mock_service_class:
        mock_service = MagicMock()
        mock_service.list_skus = AsyncMock(return_value=([], 0))
        mock_service_class.return_value = mock_service

        with patch('core.cache.get_redis_client') as mock_get_client:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            mock_redis.setex = AsyncMock()
            mock_get_client.return_value = mock_redis

            mock_db = _tenant_mock_db()
            await _list_skus_cached(mock_db, page=1, size=10, is_active=True, q=None)

            # Verify the EXACT tenant-scoped cache key format
            call_args = mock_redis.get.call_args[0][0]
            assert call_args == (
                f"skus_list:{S3C_TENANT_SCHEMA}:1:10:True:None"
            )
            assert mock_redis.setex.call_args[0][0] == call_args


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

            mock_db = _tenant_mock_db()
            await _list_skus_cached(mock_db, page=1, size=10, is_active=True, q=None)

            # Verify TTL is 60 seconds
            call_args = mock_redis.setex.call_args[0]
            ttl = call_args[1].total_seconds()
            assert ttl == 60


@pytest.mark.asyncio
async def test_skus_list_cache_key_differs_per_tenant_same_params():
    """Identical listing parameters under two tenant schemas address two
    DIFFERENT cache keys; the same tenant/schema builds a stable identical
    key (R1 SKU-cache tenant isolation)."""
    with patch('api.v1.skus.SKUService') as mock_service_class:
        mock_service = MagicMock()
        mock_service.list_skus = AsyncMock(return_value=([], 0))
        mock_service_class.return_value = mock_service

        with patch('core.cache.get_redis_client') as mock_get_client:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            mock_redis.setex = AsyncMock()
            mock_get_client.return_value = mock_redis

            db_a = _tenant_mock_db(S3C_TENANT_SCHEMA)
            db_b = _tenant_mock_db(OTHER_TENANT_SCHEMA)

            await _list_skus_cached(db_a, page=1, size=10, is_active=True, q=None)
            key_a_first = mock_redis.get.call_args[0][0]

            await _list_skus_cached(db_b, page=1, size=10, is_active=True, q=None)
            key_b = mock_redis.get.call_args[0][0]

            await _list_skus_cached(db_a, page=1, size=10, is_active=True, q=None)
            key_a_second = mock_redis.get.call_args[0][0]

            assert key_a_first == key_a_second == (
                f"skus_list:{S3C_TENANT_SCHEMA}:1:10:True:None"
            ), "same tenant + same parameters must build one stable key"
            assert key_b == (
                f"skus_list:{OTHER_TENANT_SCHEMA}:1:10:True:None"
            ), "the other tenant's key must be its own tenant-scoped key"
            assert key_a_first != key_b, (
                "identical parameters under different tenant schemas must "
                "not share a cache key"
            )


@pytest.mark.asyncio
async def test_skus_list_cache_hit_same_tenant_serves_cached_page():
    """Same tenant, same parameters: a cache hit serves the cached page and
    the database service is NOT invoked again (normal caching still works
    under the tenant-scoped key)."""
    cached_page = {
        "items": [
            {
                "id": "sku-123",
                "catalog_product_id": "cat-1",
                "sku_code": "SKU001",
                "name": "Test Product",
                "description": None,
                "unit": "pcs",
                "package_quantity": "1",
                "category": None,
                "is_active": True,
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00",
            }
        ],
        "total": 1,
    }
    with patch('api.v1.skus.SKUService') as mock_service_class:
        mock_service = MagicMock()
        mock_service.list_skus = AsyncMock(return_value=([], 0))
        mock_service_class.return_value = mock_service

        with patch('core.cache.get_redis_client') as mock_get_client:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = json.dumps(cached_page)
            mock_redis.setex = AsyncMock()
            mock_get_client.return_value = mock_redis

            result = await _list_skus_cached(
                _tenant_mock_db(), page=1, size=10, is_active=True, q=None
            )

            assert result == cached_page, (
                "the cache hit must return the cached page for this tenant"
            )
            assert mock_redis.get.await_count == 1
            assert mock_service.list_skus.await_count == 0, (
                "a cache hit must not re-query the database"
            )
            assert mock_redis.setex.await_count == 0, (
                "a cache hit must not re-write the cache entry"
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mock_session, case",
    [
        (object(), "no-info-attribute"),
        (AsyncMock(spec=AsyncSession), "info-without-tenant-schema"),
    ],
)
async def test_skus_list_cache_refuses_session_without_tenant_before_redis(
    mock_session, case
):
    """A session carrying no usable tenant_schema is rejected by a NAMED
    error BEFORE any Redis access (and before any database work)."""
    if case == "info-without-tenant-schema":
        mock_session.info = {}
    with patch('api.v1.skus.SKUService') as mock_service_class:
        mock_service = MagicMock()
        mock_service.list_skus = AsyncMock(return_value=([], 0))
        mock_service_class.return_value = mock_service

        with patch('core.cache.get_redis_client') as mock_get_client:
            mock_get_client.return_value = AsyncMock()

            with pytest.raises(SkuListCacheTenantContextError) as raised:
                await _list_skus_cached(
                    mock_session, page=1, size=10, is_active=True, q=None
                )

            assert "INVARIANT_R1_SKU_LIST_CACHE_NOT_TENANT_SCOPED" in str(raised.value)
            assert mock_get_client.await_count == 0, (
                f"[{case}] the rejection must happen BEFORE any Redis access"
            )
            assert mock_service.list_skus.await_count == 0, (
                f"[{case}] the rejection must happen before database work"
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_schema, case",
    [
        ("", "empty"),
        (None, "none"),
        (123, "non-string"),
        ("t_evil:drop", "colon-injection"),
        ("t-evil", "dash-invalid"),
    ],
)
async def test_skus_list_cache_refuses_invalid_tenant_schema_before_redis(
    bad_schema, case
):
    """A session whose tenant_schema is empty/invalid is rejected by a NAMED
    error BEFORE any Redis access (never a global or None-namespaced key)."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.info = {"tenant_schema": bad_schema}
    with patch('api.v1.skus.SKUService') as mock_service_class:
        mock_service = MagicMock()
        mock_service.list_skus = AsyncMock(return_value=([], 0))
        mock_service_class.return_value = mock_service

        with patch('core.cache.get_redis_client') as mock_get_client:
            mock_get_client.return_value = AsyncMock()

            with pytest.raises(SkuListCacheTenantContextError) as raised:
                await _list_skus_cached(
                    mock_session, page=1, size=10, is_active=True, q=None
                )

            assert "INVARIANT_R1_SKU_LIST_CACHE_NOT_TENANT_SCOPED" in str(raised.value)
            assert mock_get_client.await_count == 0, (
                f"[{case}] the rejection must happen BEFORE any Redis access"
            )
            mock_service.list_skus.assert_not_awaited()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
