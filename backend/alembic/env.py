"""
Alembic environment configuration for multi-tenant schema support.

Implements database_contract.md section 5: Alembic multi-schema migration strategy.

Usage:
- Public schema only: alembic upgrade head
- Specific tenant: alembic -x tenant_schema=t_abc123 upgrade head
"""
import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import all models for autogenerate support
from models import Base

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Explicit database URL selection for migrations.
#
# alembic.ini intentionally ships `sqlalchemy.url` empty: the repository
# carries no default DSN. The migration URL must be supplied explicitly,
# with this precedence:
#   1. the DATABASE_URL environment variable, whenever the key exists —
#      a blank or malformed value is rejected by name and never falls
#      back to another source;
#   2. otherwise a non-empty `sqlalchemy.url` set on this Alembic Config
#      object by the caller (programmatic invocation path).
# When neither source yields a usable URL, migrations fail fast here,
# before any engine is created (online) or the offline context is
# configured, with a value-free error.
class MigrationDatabaseUrlError(RuntimeError):
    """No explicit, usable migration database URL is configured.

    The message carries only fixed key names and a reason category:
    offending values are never echoed, and the exception chain is kept
    free of library errors that would embed the URL.
    """


_ENV_URL_KEY = "DATABASE_URL"
_MAIN_URL_OPTION = "sqlalchemy.url"

_CONFIG_OPTION_UNREADABLE = object()


def _named_reject(reason_category: str) -> None:
    # Invoked only outside except blocks, so the raised error keeps a
    # clean, value-free exception chain (no __cause__ / __context__).
    raise MigrationDatabaseUrlError(
        "Refusing to run migrations: no usable database URL "
        f"(reason: {reason_category}). Supply {_ENV_URL_KEY} in the "
        f"environment or a non-empty {_MAIN_URL_OPTION} on the Alembic "
        f"Config object; alembic.ini ships {_MAIN_URL_OPTION} empty by "
        "design."
    )


def _url_is_parseable(candidate: str) -> bool:
    # SQLAlchemy parse errors embed the offending URL, so the attempt is
    # reduced to a boolean here; the exception never leaves this frame.
    try:
        make_url(candidate)
    except Exception:
        return False
    return True


def _config_url_value_free():
    # A ConfigParser interpolation failure would embed the stored value in
    # its message; reduce any read failure to a sentinel instead.
    try:
        return config.get_main_option(_MAIN_URL_OPTION)
    except Exception:
        return _CONFIG_OPTION_UNREADABLE


def _resolve_migration_url() -> str:
    """Pick the migration URL: env key wins over explicit Config input."""
    if _ENV_URL_KEY in os.environ:
        raw = os.environ[_ENV_URL_KEY]
        if not raw.strip():
            _named_reject(f"{_ENV_URL_KEY}_EMPTY")
        # Alembic needs the async driver prefix. Byte-exact scheme rewrite
        # as before; the rest of the URL is left untouched.
        resolved = raw
        if resolved.startswith("postgresql://"):
            resolved = resolved.replace("postgresql://", "postgresql+asyncpg://", 1)
        if not _url_is_parseable(resolved):
            _named_reject(f"{_ENV_URL_KEY}_MALFORMED")
        # BasicInterpolation would reject or rewrite a bare '%' (e.g. in
        # percent-encoded credentials); store the ConfigParser-escaped
        # form so reads deliver the original bytes.
        config.set_main_option(_MAIN_URL_OPTION, resolved.replace("%", "%%"))
        return resolved

    raw = _config_url_value_free()
    if raw is _CONFIG_OPTION_UNREADABLE:
        _named_reject(f"{_MAIN_URL_OPTION}_MALFORMED")
    if not (raw or "").strip():
        _named_reject(f"{_MAIN_URL_OPTION}_EMPTY")
    if not _url_is_parseable(raw):
        _named_reject(f"{_MAIN_URL_OPTION}_MALFORMED")
    return raw


# Resolve once per env.py execution; online and offline share this
# selection, so `heads`/`history` (which never execute env.py) are
# unaffected while every migration run is gated before any connection.
_resolved_db_url = _resolve_migration_url()

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
