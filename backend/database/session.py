"""
Database session management for Mpango ERP.
Implements async SQLAlchemy 2.0 sessions with tenant schema support.
"""
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker
)

from core.config import get_settings


# Get settings
settings = get_settings()

# Create async engine
# Convert postgresql:// to postgresql+asyncpg://
async_database_url = settings.DATABASE_URL.replace(
    "postgresql://",
    "postgresql+asyncpg://"
)

async_engine = create_async_engine(
    async_database_url,
    echo=settings.DATABASE_ECHO,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session for public schema operations.
    
    Yields:
        AsyncSession: Database session
        
    Usage:
        async with get_db() as session:
            # Use session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_tenant_db(tenant_schema: str) -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session with tenant schema search_path set.
    
    Implements multi_tenancy_spec.md section 4.2:
    Sets search_path to "<tenant_schema>", public for tenant isolation.
    
    Args:
        tenant_schema: Tenant schema name (e.g., t_1234...)
        
    Yields:
        AsyncSession: Database session with tenant search_path
        
    Usage:
        async with get_tenant_db("t_abc123") as session:
            # Queries resolve to tenant schema first, then public
    """
    async with AsyncSessionLocal() as session:
        try:
            # Set search_path for tenant isolation
            await session.execute(
                text(f'SET LOCAL search_path TO "{tenant_schema}", public')
            )
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tenant_schema(tenant_schema: str) -> None:
    """
    Create a new tenant schema.
    
    Args:
        tenant_schema: Schema name to create (e.g., t_abc123)
        
    Raises:
        Exception: If schema creation fails
    """
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                text(f'CREATE SCHEMA IF NOT EXISTS "{tenant_schema}"')
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
