"""
S3-C: Redis Read-Through Cache

Implements read-through caching for static or slowly changing data.

Philosophy: "Cache for Reads, Benchmark for Truth."

Features:
- Automatic serialization/deserialization of Pydantic models
- TTL-based expiration (no complex invalidation)
- Cache key builder support
- Prometheus metrics for cache hits/misses
"""
import json
import functools
from typing import Optional, Callable, Any, TypeVar, ParamSpec
from datetime import timedelta

import redis.asyncio as redis
from pydantic import BaseModel
from prometheus_client import Counter, Histogram

from core.config import get_settings
from core.structured_logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Type variables for generic decorator
P = ParamSpec('P')
T = TypeVar('T')

# Redis client (lazy initialization)
_redis_client: Optional[redis.Redis] = None


# S3-C: Prometheus metrics for cache performance
cache_hits_total = Counter(
    'cache_hits_total',
    'Total cache hits',
    ['cache_key_prefix']
)

cache_misses_total = Counter(
    'cache_misses_total',
    'Total cache misses',
    ['cache_key_prefix']
)

cache_operation_duration_seconds = Histogram(
    'cache_operation_duration_seconds',
    'Cache operation duration in seconds',
    ['operation', 'cache_key_prefix'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
)


async def get_redis_client() -> redis.Redis:
    """
    Get Redis client (lazy initialization).

    Returns:
        Redis client instance
    """
    global _redis_client

    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        logger.info("Redis client initialized")

    return _redis_client


async def close_redis_client() -> None:
    """Close Redis client connection."""
    global _redis_client

    client = _redis_client
    _redis_client = None
    if client is None:
        return

    try:
        await client.aclose()
    except RuntimeError as exc:
        if str(exc) != "Event loop is closed":
            raise
        logger.warning("Redis client event loop was already closed")
    else:
        logger.info("Redis client closed")


def default_key_builder(*args, **kwargs) -> str:
    """
    Default cache key builder.

    Builds key from function arguments.

    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Cache key string
    """
    # Convert args to strings
    arg_strs = [str(arg) for arg in args]

    # Convert kwargs to sorted key=value strings
    kwarg_strs = [f"{k}={v}" for k, v in sorted(kwargs.items())]

    # Combine all parts
    all_parts = arg_strs + kwarg_strs

    return ":".join(all_parts) if all_parts else "default"


def serialize_value(value: Any) -> str:
    """
    Serialize value for Redis storage.

    Handles Pydantic models, dicts, lists, and primitives.

    Args:
        value: Value to serialize

    Returns:
        JSON string
    """
    if isinstance(value, BaseModel):
        # Pydantic model - use model_dump_json()
        return value.model_dump_json()
    elif isinstance(value, (dict, list)):
        # Dict or list - use json.dumps()
        return json.dumps(value)
    else:
        # Primitive - convert to JSON
        return json.dumps(value)


def deserialize_value(data: str, return_type: type) -> Any:
    """
    Deserialize value from Redis.

    Handles Pydantic models, dicts, lists, and primitives.

    Args:
        data: JSON string from Redis
        return_type: Expected return type

    Returns:
        Deserialized value
    """
    # Check if return type is a Pydantic model
    if isinstance(return_type, type) and issubclass(return_type, BaseModel):
        # Pydantic model - use model_validate_json()
        return return_type.model_validate_json(data)
    else:
        # Other types - use json.loads()
        return json.loads(data)


def cache(
    ttl_seconds: int = 300,
    key_prefix: Optional[str] = None,
    key_builder: Optional[Callable[..., str]] = None
):
    """
    S3-C: Redis read-through cache decorator.

    Caches function results in Redis with TTL-based expiration.

    Args:
        ttl_seconds: Time-to-live in seconds (default: 300 = 5 minutes)
        key_prefix: Optional prefix for cache keys (default: function name)
        key_builder: Optional custom key builder function (default: default_key_builder)

    Usage:
        @cache(ttl_seconds=60, key_prefix="user")
        async def get_user(user_id: str) -> User:
            # Expensive operation
            return user

    Cache Key Format:
        {key_prefix}:{key_builder_result}

    Example:
        user:123e4567-e89b-12d3-a456-426614174000
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        # Determine key prefix
        prefix = key_prefix or func.__name__

        # Determine key builder
        builder = key_builder or default_key_builder

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Build cache key
            key_suffix = builder(*args, **kwargs)
            cache_key = f"{prefix}:{key_suffix}"

            # Get Redis client
            redis_client = await get_redis_client()

            # Try to get from cache
            try:
                import time
                start_time = time.time()

                cached_data = await redis_client.get(cache_key)

                duration = time.time() - start_time
                cache_operation_duration_seconds.labels(
                    operation="get",
                    cache_key_prefix=prefix
                ).observe(duration)

                if cached_data is not None:
                    # Cache hit
                    cache_hits_total.labels(cache_key_prefix=prefix).inc()

                    logger.debug(
                        f"Cache hit: {cache_key}",
                        extra={
                            "cache_key": cache_key,
                            "ttl_seconds": ttl_seconds,
                            "duration_ms": duration * 1000
                        }
                    )

                    # Deserialize and return
                    return_type = func.__annotations__.get('return', dict)
                    return deserialize_value(cached_data, return_type)

                # Cache miss
                cache_misses_total.labels(cache_key_prefix=prefix).inc()

                logger.debug(
                    f"Cache miss: {cache_key}",
                    extra={
                        "cache_key": cache_key,
                        "ttl_seconds": ttl_seconds
                    }
                )

            except Exception as e:
                # Cache error - log and continue without cache
                logger.warning(
                    f"Cache get error: {str(e)}",
                    extra={
                        "cache_key": cache_key,
                        "error": str(e)
                    }
                )

            # Execute function
            result = await func(*args, **kwargs)

            # Store in cache
            try:
                start_time = time.time()

                serialized = serialize_value(result)
                await redis_client.setex(
                    cache_key,
                    timedelta(seconds=ttl_seconds),
                    serialized
                )

                duration = time.time() - start_time
                cache_operation_duration_seconds.labels(
                    operation="set",
                    cache_key_prefix=prefix
                ).observe(duration)

                logger.debug(
                    f"Cache set: {cache_key}",
                    extra={
                        "cache_key": cache_key,
                        "ttl_seconds": ttl_seconds,
                        "duration_ms": duration * 1000
                    }
                )

            except Exception as e:
                # Cache error - log and continue
                logger.warning(
                    f"Cache set error: {str(e)}",
                    extra={
                        "cache_key": cache_key,
                        "error": str(e)
                    }
                )

            return result

        return wrapper

    return decorator


async def invalidate_cache(key_pattern: str) -> int:
    """
    Invalidate cache keys matching pattern.

    Args:
        key_pattern: Redis key pattern (e.g., "user:*")

    Returns:
        Number of keys deleted
    """
    redis_client = await get_redis_client()

    try:
        # Find matching keys
        keys = []
        async for key in redis_client.scan_iter(match=key_pattern):
            keys.append(key)

        # Delete keys
        if keys:
            deleted = await redis_client.delete(*keys)
            logger.info(
                f"Cache invalidated: {deleted} keys",
                extra={
                    "pattern": key_pattern,
                    "deleted_count": deleted
                }
            )
            return deleted

        return 0

    except Exception as e:
        logger.error(
            f"Cache invalidation error: {str(e)}",
            extra={
                "pattern": key_pattern,
                "error": str(e)
            }
        )
        return 0


async def get_cache_stats() -> dict:
    """
    Get cache statistics.

    Returns:
        Dict with cache stats (keys, memory, etc.)
    """
    redis_client = await get_redis_client()

    try:
        info = await redis_client.info()

        return {
            "connected_clients": info.get("connected_clients", 0),
            "used_memory_human": info.get("used_memory_human", "0B"),
            "total_keys": await redis_client.dbsize(),
            "uptime_seconds": info.get("uptime_in_seconds", 0)
        }

    except Exception as e:
        logger.error(f"Failed to get cache stats: {str(e)}")
        return {}
