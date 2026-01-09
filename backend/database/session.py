from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from typing import AsyncGenerator

from core.config import settings

# 同步引擎（用于Alembic迁移）
sync_engine = create_engine(settings.DATABASE_URL)

# 异步引擎（用于应用程序）
async_database_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
async_engine = create_async_engine(async_database_url, echo=True)

# 异步会话工厂
AsyncSessionLocal = sessionmaker(
    async_engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_tenant_db(tenant_schema: str) -> AsyncGenerator[AsyncSession, None]:
    """获取租户特定的数据库会话"""
    async with AsyncSessionLocal() as session:
        try:
            # 设置搜索路径到租户schema
            await session.execute(
                text(f'SET LOCAL search_path TO "{tenant_schema}", public')
            )
            yield session
        finally:
            await session.close()


async def create_tenant_schema(tenant_schema: str) -> None:
    """创建租户schema"""
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                text(f'CREATE SCHEMA IF NOT EXISTS "{tenant_schema}"')
            )
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e