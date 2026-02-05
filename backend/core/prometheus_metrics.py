"""
S2-3: Prometheus Metrics System

Provides Prometheus-compatible metrics for observability.
Tracks HTTP requests, response times, and business metrics.
"""
import time
from typing import Optional
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from core.structured_logging import get_logger

logger = get_logger(__name__)

# S2-3: HTTP Request Metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'route', 'status_code', 'tenant']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'route', 'tenant'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'HTTP requests currently in progress',
    ['method', 'route']
)

# S2-3: Business Metrics (placeholders)
db_transactions_total = Counter(
    'db_transactions_total',
    'Total database transactions',
    ['tenant', 'operation', 'status']
)

idempotency_conflicts_total = Counter(
    'idempotency_conflicts_total',
    'Total idempotency conflicts detected',
    ['tenant', 'endpoint']
)

payment_transactions_total = Counter(
    'payment_transactions_total',
    'Total payment transactions',
    ['tenant', 'status']
)

order_state_transitions_total = Counter(
    'order_state_transitions_total',
    'Total order state transitions',
    ['tenant', 'from_state', 'to_state']
)


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """
    S2-3: Middleware to collect Prometheus metrics.
    
    Tracks:
    - http_requests_total: Counter with labels (method, route, status_code, tenant)
    - http_request_duration_seconds: Histogram with labels (method, route, tenant)
    - http_requests_in_progress: Gauge with labels (method, route)
    """
    
    async def dispatch(self, request: Request, call_next):
        # Extract route and method
        route = self._normalize_route(request.url.path)
        method = request.method
        
        # Extract tenant from request state (set by auth middleware)
        tenant = getattr(request.state, 'tenant_id', 'unknown')
        
        # Track in-progress requests
        http_requests_in_progress.labels(method=method, route=route).inc()
        
        # Start timer
        start_time = time.time()
        
        try:
            # Process request
            response = await call_next(request)
            status_code = response.status_code
            
            # Record metrics
            duration = time.time() - start_time
            
            http_requests_total.labels(
                method=method,
                route=route,
                status_code=status_code,
                tenant=tenant
            ).inc()
            
            http_request_duration_seconds.labels(
                method=method,
                route=route,
                tenant=tenant
            ).observe(duration)
            
            return response
            
        except Exception as e:
            # Record error metrics
            duration = time.time() - start_time
            
            http_requests_total.labels(
                method=method,
                route=route,
                status_code=500,
                tenant=tenant
            ).inc()
            
            http_request_duration_seconds.labels(
                method=method,
                route=route,
                tenant=tenant
            ).observe(duration)
            
            raise
            
        finally:
            # Decrement in-progress counter
            http_requests_in_progress.labels(method=method, route=route).dec()
    
    def _normalize_route(self, path: str) -> str:
        """
        Normalize route path for metrics.
        
        Converts /api/v1/users/123 -> /api/v1/users/{id}
        """
        # Skip metrics endpoint itself
        if path == "/metrics":
            return "/metrics"
        
        # Skip health endpoints
        if path.startswith("/health"):
            return "/health"
        
        # Normalize API routes
        if path.startswith("/api/v1/"):
            parts = path.split("/")
            
            # /api/v1/resource/id -> /api/v1/resource/{id}
            if len(parts) >= 5:
                # Check if last part looks like an ID (UUID or number)
                last_part = parts[-1]
                if self._is_id(last_part):
                    parts[-1] = "{id}"
                    return "/".join(parts)
            
            # /api/v1/resource
            if len(parts) == 4:
                return path
        
        return path
    
    def _is_id(self, value: str) -> bool:
        """Check if value looks like an ID (UUID or number)."""
        # Check if it's a number
        if value.isdigit():
            return True
        
        # Check if it's a UUID (simple check)
        if len(value) == 36 and value.count('-') == 4:
            return True
        
        return False


def get_metrics() -> bytes:
    """
    S2-3: Get Prometheus metrics in text format.
    
    Returns metrics in Prometheus exposition format.
    """
    return generate_latest()


def get_metrics_content_type() -> str:
    """Get Prometheus metrics content type."""
    return CONTENT_TYPE_LATEST


# Business metrics helper functions
def record_db_transaction(tenant: str, operation: str, status: str) -> None:
    """Record a database transaction."""
    db_transactions_total.labels(tenant=tenant, operation=operation, status=status).inc()


def record_idempotency_conflict(tenant: str, endpoint: str) -> None:
    """Record an idempotency conflict."""
    idempotency_conflicts_total.labels(tenant=tenant, endpoint=endpoint).inc()


def record_payment_transaction(tenant: str, status: str) -> None:
    """Record a payment transaction."""
    payment_transactions_total.labels(tenant=tenant, status=status).inc()


def record_order_state_transition(tenant: str, from_state: str, to_state: str) -> None:
    """Record an order state transition."""
    order_state_transitions_total.labels(
        tenant=tenant,
        from_state=from_state,
        to_state=to_state
    ).inc()
