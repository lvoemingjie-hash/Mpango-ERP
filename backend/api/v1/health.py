"""
Health check endpoints for monitoring and orchestration.

S2-4: Kubernetes-style health probes with deep dependency checks.

Provides:
- /healthz - Liveness probe (process alive check)
- /readyz - Readiness probe (DB + Redis connectivity)
- /health, /health/live, /health/ready - Legacy aliases
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_db_session

router = APIRouter()


class HealthStatus(BaseModel):
    """Health check response schema."""
    status: str = Field(..., description="Health status: healthy, degraded, unhealthy")
    service: str = Field(default="mpango-erp-backend", description="Service name")
    version: str = Field(default="0.2.0", description="Service version")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")


class ReadinessStatus(BaseModel):
    """Readiness check response schema."""
    status: str = Field(..., description="Readiness status")
    service: str = Field(default="mpango-erp-backend", description="Service name")
    version: str = Field(default="0.2.0", description="Service version")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")
    checks: dict = Field(default_factory=dict, description="Individual check results")


# S2-4: Kubernetes-style liveness probe
@router.get(
    "z",  # /healthz
    response_model=HealthStatus,
    status_code=status.HTTP_200_OK,
    summary="Kubernetes liveness probe",
    description="Returns 200 OK if the service process is alive. Does not check dependencies."
)
async def liveness_probe():
    """
    S2-4: Kubernetes liveness probe endpoint.

    Returns 200 OK if the service process is alive.
    Should be fast and not check external dependencies.

    Use this for Kubernetes livenessProbe configuration.
    """
    return HealthStatus(
        status="healthy",
        service="mpango-erp-backend",
        version="0.2.0",
        timestamp=datetime.utcnow()
    )


# S2-4: Kubernetes-style readiness probe
@router.get(
    "y",  # /healthy when combined with /health prefix
    response_model=ReadinessStatus,
    responses={
        200: {"description": "Service is ready"},
        503: {"description": "Service is not ready"}
    },
    summary="Kubernetes readiness probe",
    description="Checks if service is ready to accept traffic (DB + Redis checks)."
)
async def readiness_probe():
    """
    S2-4: Kubernetes readiness probe endpoint.

    Performs deep checks:
    - Database connectivity (SELECT 1)
    - Redis connectivity (PING)

    Returns 200 if all checks pass, 503 if any fail.

    Use this for Kubernetes readinessProbe configuration.
    """
    checks = {}
    overall_status = "healthy"

    # Check database connectivity
    db_status = await _check_database()
    checks["database"] = db_status
    if db_status["status"] != "healthy":
        overall_status = "unhealthy"

    # S2-4: Check Redis connectivity
    redis_status = await _check_redis()
    checks["redis"] = redis_status
    if redis_status["status"] != "healthy":
        overall_status = "unhealthy"

    response = ReadinessStatus(
        status=overall_status,
        service="mpango-erp-backend",
        version="0.2.0",
        timestamp=datetime.utcnow(),
        checks=checks
    )

    if overall_status != "healthy":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(mode="json")
        )

    return response


# Legacy endpoints for backward compatibility
@router.get(
    "",
    response_model=HealthStatus,
    status_code=status.HTTP_200_OK,
    summary="Basic health check (legacy)",
    description="Returns basic health status. Use /healthz for liveness checks."
)
async def health_check():
    """
    Basic health check endpoint (legacy).

    Returns 200 OK if the service is running.
    Does not check external dependencies.

    Prefer /healthz for new implementations.
    """
    return HealthStatus(
        status="healthy",
        service="mpango-erp-backend",
        version="0.2.0",
        timestamp=datetime.utcnow()
    )


@router.get(
    "/live",
    response_model=HealthStatus,
    status_code=status.HTTP_200_OK,
    summary="Liveness check (legacy)",
    description="Lightweight check for liveness. Prefer /healthz for new implementations."
)
async def liveness_check():
    """
    Kubernetes liveness probe endpoint (legacy).

    Returns 200 OK if the service process is alive.
    Should be fast and not check external dependencies.

    Prefer /healthz for new implementations.
    """
    return HealthStatus(
        status="healthy",
        service="mpango-erp-backend",
        version="0.2.0",
        timestamp=datetime.utcnow()
    )


@router.get(
    "/ready",
    response_model=ReadinessStatus,
    responses={
        200: {"description": "Service is ready"},
        503: {"description": "Service is not ready"}
    },
    summary="Readiness check (legacy)",
    description="Checks if service is ready to accept traffic. Prefer /readyz for new implementations."
)
async def readiness_check():
    """
    Kubernetes readiness probe endpoint (legacy).

    Checks:
    - Database connectivity
    - Redis connectivity

    Returns 200 if all checks pass, 503 if any fail.

    Prefer /readyz for new implementations.
    """
    return await readiness_probe()


async def _check_database() -> dict:
    """
    Check database connectivity with timing and basic diagnostics.

    Returns dict with status, latency, and optional error message.
    """
    import time
    start_time = time.time()

    try:
        # Import here to avoid circular imports
        from database.session import async_engine

        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            # Test tenant schema creation readiness
            await conn.execute(text("SELECT current_schema()"))

        latency_ms = round((time.time() - start_time) * 1000, 2)

        return {
            "status": "healthy",
            "latency_ms": latency_ms,
            "checks_performed": ["connectivity", "basic_query", "schema_access"]
        }
    except Exception as e:
        latency_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "status": "unhealthy",
            "error": str(e),
            "latency_ms": latency_ms,
            "error_type": type(e).__name__
        }


async def _check_redis() -> dict:
    """
    S2-4: Check Redis connectivity with timing and basic diagnostics.

    Returns dict with status, latency, and optional error message.
    """
    import time
    start_time = time.time()

    try:
        import redis.asyncio as redis
        from core.config import get_settings

        settings = get_settings()

        # Create Redis client
        client = redis.from_url(settings.REDIS_URL, decode_responses=True)

        # Perform PING check
        pong = await client.ping()

        # Close connection
        await client.close()

        latency_ms = round((time.time() - start_time) * 1000, 2)

        return {
            "status": "healthy",
            "latency_ms": latency_ms,
            "checks_performed": ["connectivity", "ping"],
            "response": "PONG" if pong else "unexpected"
        }
    except ImportError:
        latency_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "status": "unhealthy",
            "error": "redis package not installed",
            "latency_ms": latency_ms,
            "error_type": "ImportError",
            "note": "Install redis with: pip install redis"
        }
    except Exception as e:
        latency_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "status": "unhealthy",
            "error": str(e),
            "latency_ms": latency_ms,
            "error_type": type(e).__name__
        }
