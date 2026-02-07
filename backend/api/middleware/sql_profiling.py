"""
S3-A: SQL Profiling Middleware

Tracks SQL query execution per HTTP request.
Provides visibility into query count and total database time.
"""
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from core.sql_profiling import (
    init_sql_tracking,
    get_sql_stats,
    clear_sql_tracking,
    sql_queries_total,
    sql_queries_per_request
)
from core.structured_logging import get_logger

logger = get_logger(__name__)


class SQLProfilingMiddleware(BaseHTTPMiddleware):
    """
    S3-A: Middleware to profile SQL queries per request.
    
    Tracks:
    - Number of SQL queries per request
    - Total database time per request
    - Logs warnings for requests with >10 queries or >500ms DB time
    """
    
    # S3-A: Thresholds for warnings
    MAX_QUERIES_WARNING = 10
    MAX_DB_TIME_MS_WARNING = 500
    
    async def dispatch(self, request: Request, call_next):
        # Skip profiling for metrics endpoint
        if request.url.path == "/metrics":
            return await call_next(request)
        
        # Initialize SQL tracking for this request
        init_sql_tracking()
        
        try:
            # Process request
            response = await call_next(request)
            
            # Get SQL statistics
            stats = get_sql_stats()
            
            # Extract metadata
            route = request.url.path
            tenant = getattr(request.state, 'tenant_id', 'unknown')
            request_id = getattr(request.state, 'request_id', 'unknown')
            
            # Record Prometheus metrics
            sql_queries_total.labels(
                tenant=tenant,
                route=self._normalize_route(route)
            ).inc(stats.query_count)
            
            sql_queries_per_request.labels(
                tenant=tenant,
                route=self._normalize_route(route)
            ).observe(stats.query_count)
            
            # S3-A Part 1: Log warnings for excessive queries or DB time
            if stats.query_count > self.MAX_QUERIES_WARNING or stats.total_duration_ms > self.MAX_DB_TIME_MS_WARNING:
                logger.warning(
                    f"High SQL load detected: {stats.query_count} queries, {stats.total_duration_ms:.2f}ms total",
                    extra={
                        "request_id": request_id,
                        "route": route,
                        "method": request.method,
                        "tenant": tenant,
                        "sql_query_count": stats.query_count,
                        "sql_total_duration_ms": stats.total_duration_ms,
                        "sql_slow_query_count": len(stats.slow_queries),
                        "threshold_queries": self.MAX_QUERIES_WARNING,
                        "threshold_duration_ms": self.MAX_DB_TIME_MS_WARNING
                    }
                )
            
            # Add SQL stats to response headers (for debugging)
            response.headers["X-SQL-Query-Count"] = str(stats.query_count)
            response.headers["X-SQL-Duration-Ms"] = f"{stats.total_duration_ms:.2f}"
            
            return response
            
        finally:
            # Clear SQL tracking
            clear_sql_tracking()
    
    def _normalize_route(self, path: str) -> str:
        """Normalize route path for metrics (same logic as PrometheusMetricsMiddleware)."""
        if path == "/metrics":
            return "/metrics"
        
        if path.startswith("/health"):
            return "/health"
        
        if path.startswith("/api/v1/"):
            parts = path.split("/")
            
            if len(parts) >= 5:
                last_part = parts[-1]
                if self._is_id(last_part):
                    parts[-1] = "{id}"
                    return "/".join(parts)
            
            if len(parts) == 4:
                return path
        
        return path
    
    def _is_id(self, value: str) -> bool:
        """Check if value looks like an ID."""
        if value.isdigit():
            return True
        
        if len(value) == 36 and value.count('-') == 4:
            return True
        
        return False

