import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from models import *  # noqa
from database.base import Base
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_tenant_schema():
    """获取租户schema名称"""
    # 从命令行参数获取 -x tenant_schema=xxx
    tenant_schema = context.get_x_argument(as_dictionary=True).get('tenant_schema')
    if tenant_schema:
        return tenant_schema
    
    # 如果没有指定，使用默认的开发schema
    from core.config import settings
    return settings.DEFAULT_TENANT_SCHEMA


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    tenant_schema = get_tenant_schema()
    
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="public",  # 版本表存储在public schema
        include_schemas=True,
    )

    with context.begin_transaction():
        # 设置搜索路径
        context.execute(f'SET search_path TO "{tenant_schema}", public')
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    tenant_schema = get_tenant_schema()
    
    # 设置搜索路径到租户schema
    connection.execute(f'SET LOCAL search_path TO "{tenant_schema}", public')
    
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        version_table_schema="public",  # 版本表存储在public schema
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()