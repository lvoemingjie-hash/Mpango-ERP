"""
S2-2: Request Logging Middleware

Logs all HTTP requests with structured context.
Automatically injects request_id, tenant, user, route, method, status, latency.
"""
import time
import uuid
from typing import Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from core.structured_logging import get_logger, set_request_context, clear_request_context

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    S2-2: Middleware for structured request logging.
    
    Responsibilities:
    1. Generate request_id if not present
    2. Set request context for structured logging
    3. Log request start
    4. Log request completion with status and latency
    5. Clear request context
    
    This middleware should be FIRST in the stack to ensure:
    - request_id is available for all other middleware
    - All logs include request context
    """
    
    async def dispatch(self, request: Request, call_next):
        # Generate request ID
        request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
        
        # Store in request state for other middleware
        request.state.request_id = request_id
        
        # Extract route and method
        route = request.url.path
        method = request.method
        
        # Set initial context (tenant and user will be added by auth middleware)
        set_request_context(
            request_id=request_id,
            route=route,
            method=method
        )
        
        # Log request start
        logger.info(
            "Request started",
            extra={
                "event": "request_start",
                "client_host": request.client.host if request.client else "unknown",
                "user_agent": request.headers.get("user-agent", "unknown")
            }
        )
        
        # Start timer
        start_time = time.time()
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate latency
            latency_ms = round((time.time() - start_time) * 1000, 2)
            
            # Log request completion
            logger.info(
                "Request completed",
                extra={
                    "event": "request_complete",
                    "status_code": response.status_code,
                    "latency_ms": latency_ms
                }
            )
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            # Calculate latency
            latency_ms = round((time.time() - start_time) * 1000, 2)
            
            # Log request error
            logger.error(
                f"Request failed: {type(e).__name__}",
                exc_info=e,
                extra={
                    "event": "request_error",
                    "exception_type": type(e).__name__,
                    "latency_ms": latency_ms
                }
            )
            
            raise
            
        finally:
            # Clear request context
            clear_request_context()


def update_request_context_with_auth(
    tenant_schema: Optional[str] = None,
    user_id: Optional[str] = None
) -> None:
    """
    Helper function for auth middleware to update context.
    
    Called after authentication to add tenant and user to log context.
    """
    set_request_context(
        tenant_schema=tenant_schema,
        user_id=user_id
    )
