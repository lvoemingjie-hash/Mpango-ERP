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
# The reporting engine connects as reporting_user (member of reporting_role)
# through the EXPLICIT runtime DSN carried in REPORTING_DATABASE_URL (R1-R7).
# There is NO fallback: the DSN is never derived from DATABASE_URL, the
# setup-only REPORTING_USER_PASSWORD is never read at runtime, and the DSN is
# structurally normalized to the asyncpg driver exactly once without ever
# being echoed.  The initial preflight proves the DSN password equals the
# setup-time REPORTING_USER_PASSWORD before any side effect.
# ---------------------------------------------------------------------------

REPORTING_CURRENCY_CODE = "USD"

settings = get_settings()


def _build_reporting_url() -> str:
    """Build the reporting database URL (R1-R7).

    The explicit REPORTING_DATABASE_URL runtime DSN is REQUIRED.  It is
    structurally normalized to the asyncpg driver exactly once (never by
    global string replacement, so a pre-suffixed async URL is not doubled).
    Diagnostics are fixed neutral messages that never contain the DSN, its
    authority, or any credential form.
    """
    from urllib.parse import urlsplit, urlunsplit

    url = os.environ.get("REPORTING_DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "REPORTING_DATABASE_URL environment variable must be set for the "
            "reporting engine")
    parts = urlsplit(url)
    if parts.scheme not in ("postgresql", "postgresql+asyncpg"):
        raise RuntimeError(
            "reporting DSN scheme must be postgresql or postgresql+asyncpg")
    if not parts.hostname:
        raise RuntimeError("reporting DSN must include a host")
    if parts.fragment:
        raise RuntimeError("reporting DSN must not contain a fragment")
    if (parts.username or "") != "reporting_user":
        raise RuntimeError("reporting DSN must bind the reporting_user identity")
    if not (parts.password or ""):
        raise RuntimeError("reporting DSN must include a password")
    if not (parts.path.lstrip("/") or ""):
        raise RuntimeError("reporting DSN must include a database")
    # structural single normalization; query options are preserved verbatim
    return urlunsplit(parts._replace(scheme="postgresql+asyncpg"))


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
