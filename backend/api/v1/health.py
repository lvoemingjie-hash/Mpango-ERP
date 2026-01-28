"""
Health check endpoints for monitoring and orchestration.

Provides:
- /health - Basic liveness check
- /health/ready - Readiness check (includes DB connectivity)
- /health/live - Kubernetes liveness probe
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
    version: str = Field(default="0.1.0", description="Service version")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")


class ReadinessStatus(BaseModel):
    """Readiness check response schema."""
    status: str = Field(..., description="Readiness status")
    service: str = Field(default="mpango-erp-backend", description="Service name")
    version: str = Field(default="0.1.0", description="Service version")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")
    checks: dict = Field(default_factory=dict, description="Individual check results")


@router.get(
    "",
    response_model=HealthStatus,
    status_code=status.HTTP_200_OK,
    summary="Basic health check",
    description="Returns basic health status. Use for simple liveness checks."
)
async def health_check():
    """
    Basic health check endpoint.
    
    Returns 200 OK if the service is running.
    Does not check external dependencies.
    """
    return HealthStatus(
        status="healthy",
        service="mpango-erp-backend",
        version="0.1.0",
        timestamp=datetime.utcnow()
    )


@router.get(
    "/live",
    response_model=HealthStatus,
    status_code=status.HTTP_200_OK,
    summary="Kubernetes liveness probe",
    description="Lightweight check for Kubernetes liveness probes."
)
async def liveness_check():
    """
    Kubernetes liveness probe endpoint.
    
    Returns 200 OK if the service process is alive.
    Should be fast and not check external dependencies.
    """
    return HealthStatus(
        status="healthy",
        service="mpango-erp-backend",
        version="0.1.0",
        timestamp=datetime.utcnow()
    )


@router.get(
    "/ready",
    response_model=ReadinessStatus,
    responses={
        200: {"description": "Service is ready"},
        503: {"description": "Service is not ready"}
    },
    summary="Kubernetes readiness probe",
    description="Checks if service is ready to accept traffic (includes DB check)."
)
async def readiness_check():
    """
    Kubernetes readiness probe endpoint.
    
    Checks:
    - Database connectivity
    
    Returns 200 if all checks pass, 503 if any fail.
    """
    checks = {}
    overall_status = "healthy"
    
    # Check database connectivity
    db_status = await _check_database()
    checks["database"] = db_status
    if db_status["status"] != "healthy":
        overall_status = "unhealthy"
    
    response = ReadinessStatus(
        status=overall_status,
        service="mpango-erp-backend",
        version="0.1.0",
        timestamp=datetime.utcnow(),
        checks=checks
    )
    
    if overall_status != "healthy":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(mode="json")
        )
    
    return response


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
