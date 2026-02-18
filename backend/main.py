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


async def graceful_shutdown():
    """
    S2 Batch 3: Graceful shutdown handler.

    Sequence:
    1. Stop accepting new connections
    2. Wait for in-flight requests to complete (grace period)
    3. Stop job queue and drain pending jobs
    4. Close database connections
    5. Close Redis connections
    6. Exit
    """
    logger.info(
        "Graceful shutdown initiated",
        extra={
            "grace_period_seconds": SHUTDOWN_GRACE_PERIOD
        }
    )

    # Signal shutdown event
    _shutdown_event.set()

    # Wait for grace period to allow in-flight requests to complete
    logger.info(f"Waiting {SHUTDOWN_GRACE_PERIOD}s for in-flight requests to complete")
    await asyncio.sleep(SHUTDOWN_GRACE_PERIOD)

    # S4-A: Stop job queue
    global _job_queue
    if _job_queue:
        try:
            await _job_queue.stop()
            logger.info("Job queue stopped")
        except Exception as e:
            logger.error(f"Error stopping job queue: {e}", exc_info=e)

    # Close database connections
    try:
        from database.session import async_engine
        await async_engine.dispose()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}", exc_info=e)

    # Close Redis connections
    try:
        from core.rate_limiter import close_rate_limiter
        await close_rate_limiter()
        logger.info("Redis connections closed")
    except Exception as e:
        logger.error(f"Error closing Redis connections: {e}", exc_info=e)

    # S3-C: Close cache Redis connections
    try:
        from core.cache import close_redis_client
        await close_redis_client()
        logger.info("Cache Redis connections closed")
    except Exception as e:
        logger.error(f"Error closing cache Redis connections: {e}", exc_info=e)

    logger.info("Graceful shutdown complete")


def setup_signal_handlers():
    """
    S2 Batch 3: Setup signal handlers for graceful shutdown.

    Captures SIGTERM and SIGINT to trigger graceful shutdown.
    """
    def signal_handler(signum, frame):
        logger.info(
            f"Received signal {signum}",
            extra={"signal": signal.Signals(signum).name}
        )
        # Create task for graceful shutdown
        asyncio.create_task(graceful_shutdown())

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("Signal handlers registered for graceful shutdown")


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

    # Setup signal handlers for graceful shutdown
    setup_signal_handlers()

    # S4-A: Initialize and start job queue
    global _job_queue
    from core.jobs import LocalJobQueue
    # Import job handlers to register them
    import core.jobs.handlers  # noqa: F401
    import jobs.reporting_jobs  # noqa: F401  # S6-2: MV refresh handler
    import jobs.export_jobs  # noqa: F401  # S6-4: Export worker
    _job_queue = LocalJobQueue(max_workers=5)
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

    # Shutdown
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
