"""
S6-P3: Reporting Database Session — Read-Only Engine for BI Queries.

Philosophy: "Reporting reads the truth. It never writes it."

This module provides a separate SQLAlchemy engine and session factory
that connects using the reporting_user credentials. This ensures:

1. READ-ONLY: INSERT/UPDATE/DELETE will fail with permission error
2. TIMEOUT: Queries exceeding 30s are automatically cancelled (role-level)
3. POOL ISOLATION: Reporting queries cannot starve transactional connections

Usage:
    from database.reporting_session import get_reporting_session

    async for session in get_reporting_session("t_abc123"):
        result = await session.execute(text("SELECT * FROM rpt_sales_daily"))
"""
import os
from typing import AsyncGenerator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

from core.config import get_settings
from db.sql_safety import validate_identifier

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# The reporting engine connects as reporting_user (member of reporting_role).
# In production, REPORTING_DATABASE_URL should be set as an env var pointing
# to the same database but with reporting_user credentials.
#
# Fallback: If REPORTING_DATABASE_URL is not set, we derive it from the
# primary DATABASE_URL by replacing the username/password.  This works for
# dev/staging where the migration created reporting_user with a known password.
# ---------------------------------------------------------------------------

REPORTING_CURRENCY_CODE = "USD"

settings = get_settings()


def _build_reporting_url() -> str:
    """
    Build the reporting database URL.

    Priority:
    1. REPORTING_DATABASE_URL env var (explicit override)
    2. Derive from DATABASE_URL by swapping credentials to reporting_user
    """
    explicit_url = os.environ.get("REPORTING_DATABASE_URL")
    if explicit_url:
        return explicit_url.replace("postgresql://", "postgresql+asyncpg://")

    # Derive from primary DATABASE_URL
    # Format: postgresql://user:pass@host:port/db
    base_url = settings.DATABASE_URL
    # Extract host portion (everything after @)
    if "@" in base_url:
        host_part = base_url.split("@", 1)[1]
    else:
        host_part = "localhost:5432/mpango_erp"

    reporting_password = os.environ.get(
        "REPORTING_USER_PASSWORD", "RptR3adOnly_S6P!"
    )
    return f"postgresql+asyncpg://reporting_user:{reporting_password}@{host_part}"


# ---------------------------------------------------------------------------
# Engine & Session Factory
# ---------------------------------------------------------------------------
# Separate pool from the transactional engine.  Smaller pool because
# reporting queries are fewer but potentially longer-running.
# ---------------------------------------------------------------------------

reporting_engine = create_async_engine(
    _build_reporting_url(),
    echo=settings.DATABASE_ECHO,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=5,
    pool_timeout=10,
    connect_args={
        "command_timeout": 35,  # Slightly above role timeout (30s) for clean error
        "server_settings": {
            "application_name": f"{settings.APP_NAME} [reporting]",
            "jit": "off",
        },
    },
)

ReportingSessionLocal = async_sessionmaker(
    reporting_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# Session Generators
# ---------------------------------------------------------------------------

async def get_reporting_session(
    tenant_schema: Optional[str] = None,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Get a read-only reporting session.

    If tenant_schema is provided, sets search_path to that tenant schema.
    Otherwise, uses the public schema.

    Args:
        tenant_schema: Optional tenant schema (e.g., "t_abc123")

    Yields:
        AsyncSession: Read-only database session

    Raises:
        Exception: If the reporting_user cannot connect or query fails
    """
    async with ReportingSessionLocal() as session:
        try:
            if tenant_schema:
                validate_identifier(tenant_schema, "tenant_schema")
                await session.execute(
                    text(f'SET LOCAL search_path TO "{tenant_schema}", public')
                )
            yield session
        finally:
            await session.close()


async def get_reporting_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a reporting session for public schema operations.

    Convenience wrapper for dependency injection in FastAPI routes.
    """
    async for session in get_reporting_session():
        yield session
