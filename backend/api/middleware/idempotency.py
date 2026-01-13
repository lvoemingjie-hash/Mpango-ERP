"""
Idempotency middleware for safe request retries.

Implements generic idempotency key handling:
- Client sends X-Idempotency-Key header
- Server caches response for duplicate requests
- Prevents duplicate order creation, payments, etc.

Uses in-memory cache for MVP (Redis in production).
"""
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
from functools import wraps

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


# In-memory cache for MVP (replace with Redis in production)
_idempotency_cache: Dict[str, Dict[str, Any]] = {}

# Cache TTL (24 hours)
IDEMPOTENCY_TTL = timedelta(hours=24)

# Methods that support idempotency
IDEMPOTENT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle idempotency keys for safe request retries.
    
    Usage:
        Client sends: X-Idempotency-Key: <unique-key>
        Server returns cached response for duplicate keys.
    
    Behavior:
        - GET requests: ignored (naturally idempotent)
        - POST/PUT/PATCH/DELETE: checked for idempotency key
        - Missing key on mutating requests: proceeds without caching
        - Duplicate key: returns cached response with 200 OK
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with idempotency handling."""
        
        # Skip non-mutating methods
        if request.method not in IDEMPOTENT_METHODS:
            return await call_next(request)
        
        # Get idempotency key from header
        idempotency_key = request.headers.get("X-Idempotency-Key")
        
        # No key provided - proceed without caching
        if not idempotency_key:
            return await call_next(request)
        
        # Create cache key (includes path and method for uniqueness)
        cache_key = self._make_cache_key(
            idempotency_key,
            request.method,
            str(request.url.path)
        )
        
        # Check for cached response
        cached = self._get_cached_response(cache_key)
        if cached:
            return JSONResponse(
                content=cached["body"],
                status_code=cached["status_code"],
                headers={
                    "X-Idempotency-Replayed": "true",
                    "X-Idempotency-Key": idempotency_key
                }
            )
        
        # Mark as in-progress to prevent race conditions
        self._mark_in_progress(cache_key)
        
        try:
            # Execute the actual request
            response = await call_next(request)
            
            # Cache successful responses (2xx status codes)
            if 200 <= response.status_code < 300:
                # Read response body
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk
                
                # Parse JSON body
                try:
                    body_json = json.loads(body.decode())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    body_json = {"raw": body.decode()}
                
                # Cache the response
                self._cache_response(
                    cache_key,
                    body_json,
                    response.status_code
                )
                
                # Return new response with body
                return JSONResponse(
                    content=body_json,
                    status_code=response.status_code,
                    headers={
                        "X-Idempotency-Key": idempotency_key
                    }
                )
            
            return response
            
        except Exception as e:
            # Remove in-progress marker on error
            self._remove_cache(cache_key)
            raise
    
    def _make_cache_key(self, key: str, method: str, path: str) -> str:
        """Create unique cache key from idempotency key, method, and path."""
        combined = f"{key}:{method}:{path}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def _get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached response if exists and not expired."""
        cached = _idempotency_cache.get(cache_key)
        
        if not cached:
            return None
        
        # Check if in-progress (concurrent request)
        if cached.get("in_progress"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "IDEMPOTENCY_CONFLICT",
                    "message": "A request with this idempotency key is already in progress"
                }
            )
        
        # Check expiration
        if datetime.utcnow() > cached["expires_at"]:
            del _idempotency_cache[cache_key]
            return None
        
        return cached
    
    def _mark_in_progress(self, cache_key: str) -> None:
        """Mark a request as in-progress."""
        _idempotency_cache[cache_key] = {
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
        _idempotency_cache[cache_key] = {
            "body": body,
            "status_code": status_code,
            "expires_at": datetime.utcnow() + IDEMPOTENCY_TTL,
            "in_progress": False
        }
    
    def _remove_cache(self, cache_key: str) -> None:
        """Remove cache entry."""
        _idempotency_cache.pop(cache_key, None)


def clear_idempotency_cache() -> int:
    """
    Clear all idempotency cache entries.
    Returns number of entries cleared.
    
    Useful for testing and maintenance.
    """
    count = len(_idempotency_cache)
    _idempotency_cache.clear()
    return count


def cleanup_expired_entries() -> int:
    """
    Remove expired entries from cache.
    Returns number of entries removed.
    
    Should be called periodically in production.
    """
    now = datetime.utcnow()
    expired_keys = [
        key for key, value in _idempotency_cache.items()
        if value.get("expires_at") and now > value["expires_at"]
    ]
    
    for key in expired_keys:
        del _idempotency_cache[key]
    
    return len(expired_keys)
