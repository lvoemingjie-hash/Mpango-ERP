"""
Alembic environment configuration for multi-tenant schema support.

Implements database_contract.md section 5: Alembic multi-schema migration strategy.

Usage:
- Public schema only: alembic upgrade head
- Specific tenant: alembic upgrade head -x tenant_schema=t_abc123
"""
import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import all models for autogenerate support
from models import Base

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from DATABASE_URL env var if available.
# This allows alembic to work inside Docker where the DB host is
# a service name (e.g. 'postgres') rather than '127.0.0.1'.
_db_url = os.environ.get("DATABASE_URL")
if _db_url:
    # Alembic needs the async driver prefix
    if _db_url.startswith("postgresql://"):
        _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    config.set_main_option("sqlalchemy.url", _db_url)

# Target metadata for autogenerate
target_metadata = Base.metadata

ALEMBIC_VERSION_TABLE = "alembic_version"
ALEMBIC_VERSION_SCHEMA = "public"
ALEMBIC_VERSION_NUM_LENGTH = 128


def _ensure_alembic_version_table_capacity(connection: Connection) -> None:
    """Keep Alembic's public version table compatible with long revision IDs.

    Alembic 1.18 still creates ``version_num`` as ``VARCHAR(32)``. This repo
    already has revision identifiers longer than 32 characters, so fresh and
    existing databases must widen the column before Alembic writes a revision.
    """
    if connection.dialect.name != "postgresql":
        return

    connection.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {ALEMBIC_VERSION_SCHEMA}.{ALEMBIC_VERSION_TABLE} (
                version_num VARCHAR({ALEMBIC_VERSION_NUM_LENGTH}) NOT NULL,
                CONSTRAINT {ALEMBIC_VERSION_TABLE}_pkc PRIMARY KEY (version_num)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            DO $$
            DECLARE
                current_type TEXT;
                current_length INTEGER;
            BEGIN
                SELECT data_type, character_maximum_length
                  INTO current_type, current_length
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name = 'alembic_version'
                   AND column_name = 'version_num';

                IF current_type = 'character varying'
                   AND current_length IS NOT NULL
                   AND current_length < 128 THEN
                    ALTER TABLE public.alembic_version
                    ALTER COLUMN version_num TYPE VARCHAR(128);
                ELSIF current_type IN ('character varying', 'text') THEN
                    NULL;
                ELSE
                    RAISE EXCEPTION
                        'Unsupported public.alembic_version.version_num type: %',
                        current_type;
                END IF;
            END $$;
            """
        )
    )


def _emit_alembic_version_table_capacity_sql() -> None:
    """Emit offline SQL equivalent of _ensure_alembic_version_table_capacity."""
    context.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {ALEMBIC_VERSION_SCHEMA}.{ALEMBIC_VERSION_TABLE} (
            version_num VARCHAR({ALEMBIC_VERSION_NUM_LENGTH}) NOT NULL,
            CONSTRAINT {ALEMBIC_VERSION_TABLE}_pkc PRIMARY KEY (version_num)
        )
        """
    )
    context.execute(
        """
        ALTER TABLE public.alembic_version
        ALTER COLUMN version_num TYPE VARCHAR(128)
        """
    )


def get_tenant_schema() -> str:
    """
    Get tenant schema from -x parameter or use default.

    Returns:
        Tenant schema name (e.g., t_abc123) or None for public only
    """
    x_args = context.get_x_argument(as_dictionary=True)
    return x_args.get('tenant_schema')


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    Calls to context.execute() emit the given string to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    tenant_schema = get_tenant_schema()

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=ALEMBIC_VERSION_SCHEMA,  # Version table always in public
        version_table_pk=True,
        include_schemas=True,
    )

    with context.begin_transaction():
        _emit_alembic_version_table_capacity_sql()
        if tenant_schema:
            # Set search_path for tenant migrations
            context.execute(f'SET search_path TO "{tenant_schema}", public')
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Run migrations with the given connection.

    Args:
        connection: SQLAlchemy connection
    """
    tenant_schema = get_tenant_schema()

    if tenant_schema:
        # Create tenant schema if it doesn't exist
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{tenant_schema}"'))
        connection.commit()

    _ensure_alembic_version_table_capacity(connection)
    connection.commit()

    if tenant_schema:
        # Set search_path to tenant schema
        connection.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=ALEMBIC_VERSION_SCHEMA,  # Version table always in public
        version_table_pk=True,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations in 'online' mode with async engine.

    Creates an async Engine and associates a connection with the context.
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
