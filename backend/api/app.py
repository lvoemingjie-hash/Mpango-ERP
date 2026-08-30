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

    # PW1-R3: rate-limit context closure — middleware ORDER matters.
    # Starlette add_middleware makes the LAST-registered middleware the
    # OUTERMOST (first to see each request). The rate limiter must observe the
    # VERIFIED tenant/user context attached by AuthenticationMiddleware, so
    # AuthenticationMiddleware has to run FIRST — it must therefore be added
    # AFTER RateLimitingMiddleware below. The previous registration order
    # (auth first, rate limiting second) inverted this and left every request
    # — including fully authenticated ones — on the anonymous IP bucket
    # (100 req/min), which 429-stormed the PW1 browser matrix.
    # Rejected-auth requests (invalid/expired/malformed tokens) never reach
    # the inner limiter; AuthenticationMiddleware rate-limits its own
    # rejection path with the same IP bucket so no unlimited bypass exists.
    from api.middleware.rate_limiting import RateLimitingMiddleware
    app.add_middleware(RateLimitingMiddleware)

    logger.info("Rate limiting middleware registered")

    # Authentication middleware (sets verified tenant and user context)
    from api.middleware.auth import AuthenticationMiddleware
    from auth.factory import get_auth_strategy

    app.add_middleware(AuthenticationMiddleware, strategy=get_auth_strategy())

    logger.info("Authentication middleware registered")

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
        retailers, skus, catalog_products, inventory, metrics, payments, prometheus,
        wholesalers,
        public_join,  # DC-12R1-MVP-L1-J1-H2-A-R1: public dual-entry join
        profiling_test,  # S3-A Part 4
        jobs_test,  # S4-A
        sku_imports,  # U3-B2: SKU import preview/validate
        intake,  # U4-C: intake workspace skeleton
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
    app.include_router(catalog_products.router, prefix="/api/v1/catalog-products", tags=["catalog-products"])
    # U3-B2: SKU import preview + validate (write to import_runs only)
    app.include_router(sku_imports.router, prefix="/api/v1/skus/import", tags=["sku-imports"])
    # U4-C: internal-login-only intake workspace skeleton
    app.include_router(intake.router, prefix="/api/v1/intake", tags=["intake"])
    app.include_router(inventory.router, prefix="/api/v1/inventory", tags=["inventory"])
    app.include_router(wholesalers.router, prefix="/api/v1/wholesalers", tags=["wholesalers"])
    # R1 dual-entry: public supplier-code lookup served from its own router
    # (u6h2 no-edit contract on api/v1/wholesalers.py) at the canonical path.
    app.include_router(public_join.router, prefix="/api/v1", tags=["public-join"])
    app.include_router(invitations.router, prefix="/api/v1", tags=["invitations"])
    app.include_router(retailers.router, prefix="/api/v1", tags=["retailers"])
    app.include_router(payments.router, prefix="/api/v1/payments", tags=["payments"])

    # DC-12R1-S3-S2B-I2B: wholesaler cashier declaration confirm/reject + list/read
    from api.v1.declarations import router as declarations_router
    app.include_router(declarations_router, prefix="/api/v1/declarations", tags=["declarations"])
    # DC-12R1-S3-S2B-I2C-I2B (Contract D): wholesaler printable relationship statement
    from api.v1.statements import router as supplier_statements_router
    app.include_router(supplier_statements_router, prefix="/api/v1/statements", tags=["statements"])

    # GAP 2: Finance — Invoices, AR, Financial Summary
    from api.v1.finance import router as finance_router
    # Invoice endpoint lives under /orders (it's an order projection)
    app.include_router(finance_router, prefix="/api/v1", tags=["finance"])
    # Receivables & summary live under /finance
    app.include_router(finance_router, prefix="/api/v1/finance", tags=["finance"])

    # S6-3: Dashboard & Reporting API (Controlled BI Facade)
    from api.v1.dashboards import dashboards_router, reports_router
    app.include_router(dashboards_router, prefix="/api/v1/dashboards", tags=["dashboards"])
    app.include_router(reports_router, prefix="/api/v1/reports", tags=["reports"])

    # S6-4: Async Export Engine
    from api.v1.exports import exports_router
    app.include_router(exports_router, prefix="/api/v1/exports", tags=["exports"])

    # Phase P-B: Streaming CSV Data Export
    from api.v1.data_export import router as data_export_router
    app.include_router(data_export_router, prefix="/api/v1", tags=["data-export"])

    # S7-4-T3: Tenant-Scoped BI Assets CRUD
    from api.v1.bi_assets import bi_assets_router
    app.include_router(bi_assets_router, prefix="/api/bi/assets", tags=["bi-assets"])

    # Phase 4: Admin Pricing API
    from api.v1.pricing import router as pricing_router
    app.include_router(pricing_router, prefix="/api/v1/pricing", tags=["pricing"])

    # Platform Track P0 - isolated routing scaffold
    from api.v1.platform.health import router as platform_router
    app.include_router(platform_router, tags=["platform"])
    logger.info("Platform router registered (Track P0 scaffold)")

    from api.v1.platform.tenants import router as platform_tenants_router
    app.include_router(platform_tenants_router, tags=["platform-tenants"])
    logger.info("Platform tenants router registered (read-only)")

    from api.v1.platform.audit import router as platform_audit_router
    app.include_router(platform_audit_router, tags=["platform-audit"])
    logger.info("Platform audit router registered (read-only)")

    from api.v1.platform.stats import router as platform_stats_router
    app.include_router(platform_stats_router, tags=["platform-stats"])
    logger.info("Platform stats router registered (read-only)")

    # Platform Track P10 — Read-only API skeleton (contract-compliant)
    from api.v1.platform.p10.routes import router as platform_p10_router
    app.include_router(platform_p10_router)
    logger.info("Platform P10 router registered (read-only, contract-compliant)")

    # Platform Track P12 -- Support Console API (request-scoped diagnostics)
    from api.v1.platform.p12.routes import router as platform_p12_router
    app.include_router(platform_p12_router)
    logger.info("Platform P12 router registered (support console, request-scoped)")

    # Platform Track P13 -- Operations Observability Cockpit (read-only)
    from api.v1.platform.p13.routes import router as platform_p13_router
    app.include_router(platform_p13_router)
    logger.info("Platform P13 router registered (operations observability, read-only)")

    # Platform Track P15 -- Incident Triage (read-only snapshot, P15-B)
    from api.v1.platform.p15.routes import router as platform_p15_router
    app.include_router(platform_p15_router)
    logger.info("Platform P15 router registered (incident triage, read-only)")

    # Platform Track P17 -- Platform Registry (read-only tenant registry, P17-B)
    from api.v1.platform.p17.routes import router as platform_p17_router
    app.include_router(platform_p17_router)
    logger.info("Platform P17 router registered (platform registry, read-only)")

    # Platform Track P18 -- Controlled Platform Actions (request skeleton, P18-B/C)
    from api.v1.platform.p18.routes import router as platform_p18_router
    app.include_router(platform_p18_router)
    logger.info("Platform P18 router registered (controlled actions request skeleton)")

    # Platform Track P19 -- Controlled Action Approval Workflow (backend skeleton, P19-B)
    from api.v1.platform.p19.routes import router as platform_p19_router
    app.include_router(platform_p19_router)
    logger.info("Platform P19 router registered (approval workflow backend skeleton)")

    # Platform Track P20 -- Durable Approval Governance (backend skeleton, P20-B)
    from api.v1.platform.p20.routes import router as platform_p20_router
    app.include_router(platform_p20_router)
    logger.info("Platform P20 router registered (durable approval governance backend skeleton)")

    # Platform Track P22 -- Controlled Execution v0 (non-executing backend skeleton, P22-B)
    from api.v1.platform.p22.routes import router as platform_p22_router
    app.include_router(platform_p22_router)
    logger.info("Platform P22 router registered (controlled execution v0 non-executing skeleton)")

    # Platform Track P23 -- Operator Task / Notification Queue (non-executing, non-sending
    # in-memory backend skeleton, P23-B). A task is a view, not an executor; a
    # notification is a record, not a delivery. No P22 action execution, no real
    # notification delivery, no migration, no frontend, no auth/RBAC rewrite.
    from api.v1.platform.p23.routes import router as platform_p23_router
    app.include_router(platform_p23_router)
    logger.info("Platform P23 router registered (operator task / notification queue skeleton)")

    # Platform Track P24 -- Incident + Runbook Closeout (non-executing, non-sending
    # in-memory backend skeleton, P24-B). An incident closeout is a view, not an
    # executor; a runbook step is a pointer, not an execution; a follow-up task is
    # a record, not a repair. No P22 action execution, no approval decision, no
    # incident_active flag mutation, no registry mutation, no notification delivery,
    # no migration, no frontend, no auth/RBAC rewrite.
    from api.v1.platform.p24.routes import router as platform_p24_router
    app.include_router(platform_p24_router)
    logger.info("Platform P24 router registered (incident + runbook closeout skeleton)")

    # Client API — Retailer-facing endpoints (v0.3.0)
    from api.v1.client.products import router as client_products_router
    from api.v1.client.orders import router as client_orders_router
    from api.v1.client.payments import router as client_payments_router
    from api.v1.client.finance import router as client_finance_router
    from api.v1.client.auth import router as client_auth_router
    # DC-12R1-S3-S2B-I2B: retailer declaration views + statement
    from api.v1.client.declarations import router as client_declarations_router
    from api.v1.client.statements import router as client_statements_router
    app.include_router(client_products_router, prefix="/api/v1/client/products", tags=["client-products"])
    app.include_router(client_orders_router, prefix="/api/v1/client/orders", tags=["client-orders"])
    app.include_router(client_payments_router, prefix="/api/v1/client/payments", tags=["client-payments"])
    app.include_router(client_finance_router, prefix="/api/v1/client/finance", tags=["client-finance"])
    app.include_router(client_declarations_router, prefix="/api/v1/client/declarations", tags=["client-declarations"])
    app.include_router(client_statements_router, prefix="/api/v1/client/statements", tags=["client-statements"])
    # DC-12R1-S1: retailer self-service credential recovery (forgot/reset). Public.
    app.include_router(client_auth_router, prefix="/api/v1/client/auth", tags=["client-auth"])

    logger.info("All routers registered")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = Settings()
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        description="Mpango ERP API",
    )
    configure_app(app, settings)
    return app


app = create_app()
