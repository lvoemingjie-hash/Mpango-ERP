"""
Mpango ERP Backend - Main FastAPI Application.

v0.1.0-platform - Stabilization release with:
- Full RBAC enforcement
- Tenant isolation
- Order state machine
- Idempotency middleware
- Health checks
- S2-1: Strict config validation and fail-fast behavior
- S2-2: Structured JSON logging with context injection
- S2-3: Prometheus metrics
- S2-5: Rate limiting with Redis
- S2-6: Central error codes and exception handling
- S2 Batch 3: Graceful shutdown
"""
import sys
import signal
import asyncio
import yaml
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from api.app import configure_app
from core.config import validate_startup_config
from core.structured_logging import setup_structured_logging, get_logger
from core.error_codes import register_exception_handlers


# S2-1: Validate configuration on startup (fail fast if invalid)
try:
    settings = validate_startup_config()
except Exception as e:
    print(f"\n💥 FATAL: Configuration validation failed", file=sys.stderr)
    print(f"   {str(e)}", file=sys.stderr)
    print(f"\n   Application cannot start with invalid configuration.", file=sys.stderr)
    sys.exit(1)

# S2-2: Setup structured JSON logging
setup_structured_logging(level=settings.LOG_LEVEL)
logger = get_logger(__name__)

# Version
__version__ = "0.2.0"

# Graceful shutdown configuration
SHUTDOWN_GRACE_PERIOD = 10  # seconds
_shutdown_event = asyncio.Event()

# S4-A: Job queue singleton
_job_queue = None


def get_job_queue():
    """Get the S4 job queue singleton. Used by API endpoints to enqueue jobs."""
    if _job_queue is None:
        raise RuntimeError("Job queue not initialized. Is the app running?")
    return _job_queue


_shutdown_task = None
_shutdown_loop = None


async def _close_lifecycle():
    _shutdown_event.set()
    if _job_queue is not None:
        await _job_queue.stop()
    # A queue failure propagates before either engine is disposed.
    from database.session import async_engine
    from database.reporting_session import reporting_engine
    await async_engine.dispose()
    await reporting_engine.dispose()
    from core.rate_limiter import close_rate_limiter
    from core.cache import close_redis_client
    await close_rate_limiter()
    await close_redis_client()
    logger.info("Graceful shutdown complete")


async def graceful_shutdown():
    global _shutdown_task, _shutdown_loop
    loop = asyncio.get_running_loop()
    if _shutdown_task is None or _shutdown_loop is not loop:
        if _shutdown_task is not None and not _shutdown_task.done():
            from core.jobs.base import JobQueueShutdownIncomplete
            raise JobQueueShutdownIncomplete()
        _shutdown_loop = loop
        _shutdown_task = asyncio.create_task(_close_lifecycle())
    return await asyncio.shield(_shutdown_task)


def setup_signal_handlers():
    """Compatibility entry: ASGI server retains ownership of its signals."""
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info(
        f"Mpango ERP Backend v{__version__} starting",
        extra={
            "version": __version__,
            "environment": settings.MPANGO_ENV
        }
    )
    logger.info("Loading OpenAPI spec from docs/contracts/openapi.yaml")

    # Signal handling belongs to the ASGI host.

    # S4-A: Initialize and start job queue
    global _job_queue, _shutdown_task, _shutdown_loop, _shutdown_event
    if _shutdown_task is not None and not _shutdown_task.done():
        from core.jobs.base import JobQueueShutdownIncomplete
        raise JobQueueShutdownIncomplete()
    _shutdown_task = None
    _shutdown_loop = asyncio.get_running_loop()
    _shutdown_event = asyncio.Event()
    from core.jobs import LocalJobQueue
    # Import job handlers to register them
    import core.jobs.handlers  # noqa: F401
    import jobs.reporting_jobs  # noqa: F401  # S6-2: MV refresh handler
    import jobs.export_jobs  # noqa: F401  # S6-4: Export worker
    _job_queue = LocalJobQueue(max_workers=5)
    try:
        await _job_queue.start()
        logger.info("Job queue started")

        # S7-4-T3: Register DbAssetResolver for dynamic tenant asset resolution
        from core.governance.db_resolver import DbAssetResolver
        from core.governance.registry import register_resolver
        from database.session import AsyncSessionLocal
        db_resolver = DbAssetResolver(session_factory=AsyncSessionLocal)
        register_resolver(db_resolver)
        logger.info("DbAssetResolver registered for tenant asset resolution")

        yield
    finally:
        logger.info("Mpango ERP Backend shutting down")
        await graceful_shutdown()


# Create FastAPI app
app = FastAPI(
    title="Mpango ERP API",
    description="Multi-tenant ERP system for African wholesale-retail operations",
    version=__version__,
    lifespan=lifespan
)

# S2-6: Register exception handlers (must be done before middleware)
register_exception_handlers(app)


def custom_openapi():
    """
    Load and serve OpenAPI specification from canonical source.

    Implements requirement 4.1: Load OpenAPI spec from docs/contracts/openapi.yaml
    """
    if app.openapi_schema:
        return app.openapi_schema

    try:
        # Load canonical OpenAPI spec
        with open("docs/contracts/openapi.yaml", "r") as f:
            openapi_schema = yaml.safe_load(f)

        # Cache the schema
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    except FileNotFoundError:
        # Fallback to FastAPI's generated schema if file not found
        logger.warning("docs/contracts/openapi.yaml not found, using generated schema")
        return get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )


# Override OpenAPI schema generation
app.openapi = custom_openapi


# Configure middleware and routers per Boot Contract layering
configure_app(app, settings)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Mpango ERP API",
        "version": __version__,
        "status": "v0.1-platform",
        "endpoints": {
            "health": "/health",
            "api": "/api/v1"
        }
    }
