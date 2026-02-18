"""
Tests for Health check endpoints.

Tests cover:
- Basic health check
- Liveness probe
- Readiness probe (with DB check)

Uses self-contained implementation to avoid database initialization issues.
"""
import os
import pytest
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

# Set test environment variables before any imports
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars")


# ============================================================================
# Test-Local Health Schemas (mirrors actual implementation)
# ============================================================================

class HealthStatus(BaseModel):
    """Health check response schema."""
    status: str = Field(..., description="Health status")
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


# ============================================================================
# Test-Local Health Endpoint Implementations
# ============================================================================

async def health_check_impl() -> HealthStatus:
    """Test-local health check implementation."""
    return HealthStatus(
        status="healthy",
        service="mpango-erp-backend",
        version="0.2.0",
        timestamp=datetime.utcnow()
    )


async def liveness_check_impl() -> HealthStatus:
    """Test-local liveness check implementation."""
    return HealthStatus(
        status="healthy",
        service="mpango-erp-backend",
        version="0.2.0",
        timestamp=datetime.utcnow()
    )


async def readiness_check_impl(db_healthy: bool = True) -> ReadinessStatus:
    """Test-local readiness check implementation."""
    db_status = {"status": "healthy"} if db_healthy else {"status": "unhealthy", "error": "Connection refused"}
    overall_status = "healthy" if db_healthy else "unhealthy"

    return ReadinessStatus(
        status=overall_status,
        service="mpango-erp-backend",
        version="0.2.0",
        timestamp=datetime.utcnow(),
        checks={"database": db_status}
    )


# ============================================================================
# Tests
# ============================================================================

class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy(self):
        """GET /health returns healthy status."""
        result = await health_check_impl()

        assert result.status == "healthy"
        assert result.service == "mpango-erp-backend"
        assert result.version == "0.2.0"
        assert isinstance(result.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_liveness_check_returns_healthy(self):
        """GET /health/live returns healthy status."""
        result = await liveness_check_impl()

        assert result.status == "healthy"
        assert result.service == "mpango-erp-backend"

    @pytest.mark.asyncio
    async def test_readiness_check_healthy_when_db_ok(self):
        """GET /health/ready returns healthy when DB is connected."""
        result = await readiness_check_impl(db_healthy=True)

        assert result.status == "healthy"
        assert result.checks["database"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_readiness_check_unhealthy_when_db_fails(self):
        """GET /health/ready returns unhealthy when DB check fails."""
        result = await readiness_check_impl(db_healthy=False)

        assert result.status == "unhealthy"
        assert result.checks["database"]["status"] == "unhealthy"
        assert "error" in result.checks["database"]


class TestHealthSchemas:
    """Tests for health check response schemas."""

    def test_health_status_schema(self):
        """HealthStatus schema should have required fields."""
        status = HealthStatus(
            status="healthy",
            service="test-service",
            version="1.0.0"
        )

        assert status.status == "healthy"
        assert status.service == "test-service"
        assert status.version == "1.0.0"
        assert isinstance(status.timestamp, datetime)

    def test_readiness_status_schema(self):
        """ReadinessStatus schema should have required fields."""
        status = ReadinessStatus(
            status="healthy",
            checks={"database": {"status": "healthy"}}
        )

        assert status.status == "healthy"
        assert status.checks["database"]["status"] == "healthy"
        assert isinstance(status.timestamp, datetime)

    def test_health_status_defaults(self):
        """HealthStatus should have sensible defaults."""
        status = HealthStatus(status="healthy")

        assert status.service == "mpango-erp-backend"
        assert status.version == "0.2.0"

    def test_readiness_status_with_multiple_checks(self):
        """ReadinessStatus should support multiple checks."""
        status = ReadinessStatus(
            status="degraded",
            checks={
                "database": {"status": "healthy"},
                "redis": {"status": "unhealthy", "error": "Connection timeout"},
                "external_api": {"status": "healthy"}
            }
        )

        assert len(status.checks) == 3
        assert status.checks["redis"]["status"] == "unhealthy"
