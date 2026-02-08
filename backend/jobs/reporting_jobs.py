"""
S6-2: Reporting Job Handlers — Materialized View Refresh Worker.

Philosophy: "Staleness is acceptable; Locking is not."

This module registers S4 job handlers for refreshing materialized views.
Uses REFRESH MATERIALIZED VIEW CONCURRENTLY to avoid blocking reads.
Uses PostgreSQL advisory locks to prevent double-refresh per tenant.

Job: refresh_materialized_views
    - Iterates all tenant schemas
    - Acquires advisory lock per tenant (skip if already refreshing)
    - Executes REFRESH MATERIALIZED VIEW CONCURRENTLY mv_sales_daily
    - Logs refresh timestamp
"""
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.jobs.base import job_handler
from core.structured_logging import get_logger
from database.session import AsyncSessionLocal

logger = get_logger(__name__)

# Materialized views to refresh (add new ones here as they are created)
MATERIALIZED_VIEWS = [
    "mv_sales_daily",
]


@job_handler("refresh_materialized_views")
async def refresh_materialized_views(payload: dict) -> None:
    """
    Refresh all materialized views across tenant schemas.

    Payload options:
        tenant_schema (str, optional): Refresh only this tenant. If omitted,
            refreshes all tenants.
        views (list[str], optional): Refresh only these views. If omitted,
            refreshes all registered materialized views.

    Flow per tenant:
        1. Acquire advisory lock (hashtext of schema name) — skip if locked
        2. SET search_path to tenant schema
        3. REFRESH MATERIALIZED VIEW CONCURRENTLY <view>
        4. Release advisory lock
    """
    target_schema = payload.get("tenant_schema")
    target_views = payload.get("views", MATERIALIZED_VIEWS)

    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = "public"

        # Discover tenant schemas
        if target_schema:
            tenant_schemas = [target_schema]
        else:
            result = await session.execute(text("""
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name LIKE 't_%'
                ORDER BY schema_name
            """))
            tenant_schemas = [row[0] for row in result]

        refreshed = 0
        skipped = 0

        for schema in tenant_schemas:
            # Step 1: Try to acquire advisory lock for this schema
            # hashtext returns a stable int32 hash — unique per schema name
            lock_result = await session.execute(
                text(f"SELECT pg_try_advisory_lock(hashtext('mv_refresh_{schema}'))")
            )
            got_lock = lock_result.scalar()

            if not got_lock:
                logger.info(
                    f"Skipping {schema}: another refresh is in progress",
                    extra={"schema": schema, "action": "skip"}
                )
                skipped += 1
                continue

            try:
                # Step 2: Set search_path
                await session.execute(
                    text(f'SET LOCAL search_path TO "{schema}", public')
                )

                # Step 3: Refresh each materialized view
                for view_name in target_views:
                    try:
                        await session.execute(
                            text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}")
                        )
                        refreshed += 1
                        logger.info(
                            f"Refreshed {schema}.{view_name}",
                            extra={
                                "schema": schema,
                                "view": view_name,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to refresh {schema}.{view_name}: {e}",
                            extra={"schema": schema, "view": view_name, "error": str(e)}
                        )
                        raise

                await session.commit()

            finally:
                # Step 4: Release advisory lock (always, even on error)
                await session.execute(
                    text(f"SELECT pg_advisory_unlock(hashtext('mv_refresh_{schema}'))")
                )
                await session.commit()

    logger.info(
        f"MV refresh complete: {refreshed} refreshed, {skipped} skipped",
        extra={"refreshed": refreshed, "skipped": skipped}
    )
