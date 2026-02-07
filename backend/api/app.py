"""
FastAPI application configuration helpers.

S2 Batch 2: Middleware stack ordering is critical:
1. RequestLoggingMiddleware - Generate request_id, set context, log requests
2. PrometheusMetricsMiddleware - Track metrics
3. CORS - Handle CORS
4. AuthenticationMiddleware - Authenticate and set tenant/user context
5. RateLimitingMiddleware - Enforce rate limits (S2-5)
6. IdempotencyMiddleware - Handle idempotency
7. BasicMetricsMiddleware - Legacy metrics (can be removed if using Prometheus)
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import Settings
from core.structured_logging import get_logger

logger = get_logger(__name__)


def configure_app(app: FastAPI, settings: Settings) -> None:
    """
    Wire middleware and routes onto the FastAPI application.
    
    S2 Batch 2 & 3: Middleware ordering ensures:
    - Request ID is generated first
    - Logging context is available for all middleware
    - Metrics capture full request lifecycle
    - Rate limiting happens after authentication
    - Errors are handled consistently
    
    S3-A: SQL profiling middleware tracks query performance
    """
    
    # S2-2: Request logging middleware (FIRST - generates request_id and span_id)
    from api.middleware.request_logging import RequestLoggingMiddleware
    app.add_middleware(RequestLoggingMiddleware)
    
    logger.info("Request logging middleware registered")
    
    # S3-A: SQL profiling middleware (SECOND - tracks SQL queries per request)
    if settings.ENABLE_SQL_PROFILING:
        from api.middleware.sql_profiling import SQLProfilingMiddleware
        app.add_middleware(SQLProfilingMiddleware)
        logger.info("SQL profiling middleware registered")
    
    # S2-3: Prometheus metrics middleware (THIRD - tracks all requests)
    from core.prometheus_metrics import PrometheusMetricsMiddleware
    app.add_middleware(PrometheusMetricsMiddleware)
    
    logger.info("Prometheus metrics middleware registered")
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Authentication middleware (sets tenant and user context)
    from api.middleware.auth import AuthenticationMiddleware
    from auth.factory import get_auth_strategy
    
    app.add_middleware(AuthenticationMiddleware, strategy=get_auth_strategy())
    
    logger.info("Authentication middleware registered")
    
    # S2-5: Rate limiting middleware (AFTER auth, BEFORE business logic)
    from api.middleware.rate_limiting import RateLimitingMiddleware
    app.add_middleware(RateLimitingMiddleware)
    
    logger.info("Rate limiting middleware registered")
    
    # Idempotency middleware
    from api.middleware.idempotency import IdempotencyMiddleware
    app.add_middleware(IdempotencyMiddleware)
    
    logger.info("Idempotency middleware registered")
    
    # Legacy metrics middleware (optional - can be removed if using Prometheus)
    from api.middleware.metrics import BasicMetricsMiddleware
    if settings.ENABLE_METRICS:
        app.add_middleware(BasicMetricsMiddleware)
        logger.info("Basic metrics middleware registered")

    # Routers
    from api.v1 import (
        auth, users, roles, orders, health, invitations, 
        retailers, skus, inventory, metrics, payments, prometheus,
        profiling_test,  # S3-A Part 4
        jobs_test  # S4-A
    )

    app.include_router(health.router, prefix="/health", tags=["health"])
    
    # S5-OPS: Register top-level /healthz and /readyz routes for Kubernetes probes.
    # The /health prefix router creates /healthz and /healthy, but Kubernetes
    # expects /readyz (not /healthy). These direct registrations fix that.
    app.get("/healthz", tags=["health"], summary="Liveness probe")(health.liveness_probe)
    app.get("/readyz", tags=["health"], summary="Readiness probe")(health.readiness_probe)
    
    app.include_router(prometheus.router, prefix="/metrics", tags=["metrics"])  # S2-3
    app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["legacy-metrics"])
    
    # S3-A Part 4: Profiling test endpoints (only in non-production)
    if settings.MPANGO_ENV != "production":
        app.include_router(profiling_test.router, prefix="/api/v1/test", tags=["profiling-test"])
        # S4-A: Job queue test endpoints (only in non-production)
        app.include_router(jobs_test.router, prefix="/api/v1/test/jobs", tags=["jobs-test"])
    
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
    app.include_router(roles.router, prefix="/api/v1/roles", tags=["roles"])
    app.include_router(orders.router, prefix="/api/v1/orders", tags=["orders"])
    app.include_router(skus.router, prefix="/api/v1/skus", tags=["skus"])
    app.include_router(inventory.router, prefix="/api/v1/inventory", tags=["inventory"])
    app.include_router(invitations.router, prefix="/api/v1", tags=["invitations"])
    app.include_router(retailers.router, prefix="/api/v1", tags=["retailers"])
    app.include_router(payments.router, prefix="/api/v1/payments", tags=["payments"])
    
    logger.info("All routers registered")
