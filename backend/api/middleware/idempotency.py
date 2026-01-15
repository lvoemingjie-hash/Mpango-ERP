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
from typing import Optional, Dict, Any, Callable, Protocol

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from core.security import decode_token


# Cache TTL (24 hours)
IDEMPOTENCY_TTL = timedelta(hours=24)

# Methods that support idempotency
IDEMPOTENT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class IdempotencyStore(Protocol):
    async def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        ...

    async def set(self, cache_key: str, value: Dict[str, Any]) -> None:
        ...

    async def delete(self, cache_key: str) -> None:
        ...


class InMemoryIdempotencyStore:
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    async def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        return self._cache.get(cache_key)

    async def set(self, cache_key: str, value: Dict[str, Any]) -> None:
        self._cache[cache_key] = value

    async def delete(self, cache_key: str) -> None:
        self._cache.pop(cache_key, None)


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

    def __init__(
        self,
        app,
        store: Optional[IdempotencyStore] = None,
        ttl: timedelta = IDEMPOTENCY_TTL,
    ):
        super().__init__(app)
        self._store: IdempotencyStore = store or InMemoryIdempotencyStore()
        self._ttl = ttl
    
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

        # Try to derive tenant/user context from Authorization header (best effort)
        tenant_schema = "anonymous"
        user_id = "anonymous"
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            raw_token = auth_header.split(" ", 1)[1].strip()
            try:
                payload = decode_token(raw_token)
                tenant_schema = payload.tenant_schema or tenant_schema
                user_id = payload.user_id or user_id
            except Exception:
                # Invalid/expired token should not break idempotency; auth layer will handle 401
                pass

        body_bytes = await request.body()

        async def _receive() -> dict:
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        request._receive = _receive  # type: ignore[attr-defined]
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        
        # Create cache key (tenant/user/method/path/body-hash to prevent cross-tenant/user collisions)
        cache_key = self._make_cache_key(
            idempotency_key=idempotency_key,
            tenant_schema=tenant_schema,
            user_id=user_id,
            method=request.method,
            path=str(request.url.path),
            body_hash=body_hash,
        )
        
        # Check for cached response
        cached = await self._get_cached_response(cache_key)
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
        await self._mark_in_progress(cache_key)
        
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
                await self._cache_response(cache_key, body_json, response.status_code)
                
                # Return new response with body
                return JSONResponse(
                    content=body_json,
                    status_code=response.status_code,
                    headers={
                        "X-Idempotency-Key": idempotency_key
                    }
                )
            
            return response
            
        except Exception:
            # Remove in-progress marker on error
            await self._remove_cache(cache_key)
            raise
    
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

    async def _get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached response if exists and not expired."""
        cached = await self._store.get(cache_key)
        
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
            await self._store.delete(cache_key)
            return None
        
        return cached
    
    async def _mark_in_progress(self, cache_key: str) -> None:
        """Mark a request as in-progress."""
        await self._store.set(cache_key, {
            "in_progress": True,
            "expires_at": datetime.utcnow() + timedelta(minutes=5)
        })
    
    async def _cache_response(
        self,
        cache_key: str,
        body: Dict[str, Any],
        status_code: int
    ) -> None:
        """Cache a response."""
        await self._store.set(cache_key, {
            "body": body,
            "status_code": status_code,
            "expires_at": datetime.utcnow() + self._ttl,
            "in_progress": False
        })

    async def _remove_cache(self, cache_key: str) -> None:
        """Remove cache entry."""
        await self._store.delete(cache_key)
