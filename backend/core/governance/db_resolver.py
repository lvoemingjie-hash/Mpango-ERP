"""
S7-4-T3: Database Asset Resolver — Concrete AssetResolver Implementation.

Philosophy: "The Resolver bridges the governance model and the database."

This module implements the AssetResolver Protocol by querying the
sys_reports table in the tenant schema. It converts DB rows (SysReport)
into governance-layer BIAsset objects that the policy engine understands.

Resolution Flow:
    1. Receive URN + tenant_id from GovernanceRegistry.
    2. Parse URN to extract report ID.
    3. Open a tenant-scoped DB session.
    4. Query sys_reports WHERE id = report_id AND is_deleted = false.
    5. Convert SysReport row → BIAsset (with owner_id, acl, tenant_id).
    6. Return BIAsset to registry (which caches it).

🔒 S7-4-C1: URN format is urn:bi:report:<domain>:<id>.
    tenant_id is passed as context, NOT embedded in URN.

🔒 S7-4-C4: This resolver does NOT manage cache invalidation.
    The CRUD API is responsible for calling invalidate_asset(urn)
    after any mutation.

Design Decisions:
- Uses AsyncSessionLocal directly (not request-scoped session) because
  the resolver is called from the registry's resolution chain, which
  may run outside of a request context (e.g., background jobs).
- Parses URN to extract the report UUID from the last segment.
- Soft-deleted reports (is_deleted=True) are NOT resolved.
- Logs errors but returns None (never raises) per Protocol contract.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.governance.models import (
    BIAsset,
    BIDomain,
    BiUrn,
    DataFreshness,
    ResourceType,
)
from core.governance.resolver import AssetResolver

logger = logging.getLogger("mpango.governance.db_resolver")


class DbAssetResolver:
    """
    Concrete AssetResolver that queries sys_reports in tenant schema.

    Implements the AssetResolver Protocol for dynamic resolution of
    tenant-created report assets from the database.

    Args:
        session_factory: An async_sessionmaker for creating DB sessions.
                         Sessions are opened per-resolve call and closed
                         after the query completes.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def resolve(
        self,
        urn: str,
        tenant_id: Optional[str] = None,
    ) -> Optional[BIAsset]:
        """
        Resolve a URN to a BIAsset by querying sys_reports.

        Steps:
        1. Parse URN → extract report UUID from last segment.
        2. Open tenant-scoped session.
        3. Query sys_reports WHERE id = uuid AND is_deleted = false.
        4. Convert row → BIAsset.

        Returns None if:
        - URN is not a report type
        - UUID is invalid
        - Report not found or soft-deleted
        - tenant_id is not provided (cannot scope query)
        - Any DB error (logged, not raised)
        """
        # Step 1: Parse URN to extract report ID
        report_id = _extract_report_id(urn)
        if report_id is None:
            return None

        if tenant_id is None:
            logger.debug("resolve_skipped_no_tenant", extra={"urn": urn})
            return None

        # Step 2-3: Query DB
        try:
            # Import here to avoid circular imports at module level
            from models.report import SysReport
            from models.wholesaler import Wholesaler

            tenant_schema = Wholesaler.derive_schema_from_id(tenant_id)

            async with self._session_factory() as session:
                from sqlalchemy import text
                await session.execute(
                    text(f'SET LOCAL search_path TO "{tenant_schema}", public')
                )
                session.info["tenant_schema"] = tenant_schema

                stmt = (
                    select(SysReport)
                    .where(SysReport.id == report_id)
                    .where(SysReport.is_deleted.is_(False))
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()

                if row is None:
                    return None

                # Step 4: Convert row → BIAsset
                return _row_to_asset(row, tenant_id)

        except Exception as exc:
            logger.error(
                "db_resolver_error",
                exc_info=exc,
                extra={"urn": urn, "tenant_id": tenant_id},
            )
            return None

    async def resolve_by_tenant(
        self,
        tenant_id: str,
        resource_type: Optional[ResourceType] = None,
    ) -> list[BIAsset]:
        """
        List all non-deleted reports for a tenant.

        Args:
            tenant_id: The tenant to list reports for.
            resource_type: If provided and not REPORT, returns empty list.
        """
        # Only resolve REPORT type (or None = all types)
        if resource_type is not None and resource_type != ResourceType.REPORT:
            return []

        try:
            from models.report import SysReport
            from models.wholesaler import Wholesaler

            tenant_schema = Wholesaler.derive_schema_from_id(tenant_id)

            async with self._session_factory() as session:
                from sqlalchemy import text
                await session.execute(
                    text(f'SET LOCAL search_path TO "{tenant_schema}", public')
                )
                session.info["tenant_schema"] = tenant_schema

                stmt = (
                    select(SysReport)
                    .where(SysReport.is_deleted.is_(False))
                    .order_by(SysReport.created_at.desc())
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()

                return [_row_to_asset(row, tenant_id) for row in rows]

        except Exception as exc:
            logger.error(
                "db_resolver_list_error",
                exc_info=exc,
                extra={"tenant_id": tenant_id},
            )
            return []


# ============================================================================
# Internal Helpers
# ============================================================================

def _extract_report_id(urn: str) -> Optional[uuid.UUID]:
    """
    Extract the report UUID from a URN string.

    Expected format: urn:bi:report:<domain>:<uuid>
    Returns None if the URN is not a report URN or the ID is not a valid UUID.
    """
    try:
        parts = urn.split(":")
        if len(parts) != 5:
            return None
        prefix, namespace, resource_type, domain, identifier = parts
        if prefix != "urn" or namespace != "bi" or resource_type != "report":
            return None
        return uuid.UUID(identifier)
    except (ValueError, AttributeError):
        return None


def _row_to_asset(row, tenant_id: str) -> BIAsset:
    """
    Convert a SysReport DB row to a BIAsset governance object.

    This is the critical mapping function that bridges the storage layer
    (ORM model) and the governance layer (BIAsset model).

    Mapping:
        SysReport.id          → BIAsset.urn (urn:bi:report:<domain>:<id>)
        SysReport.title       → BIAsset.display_name
        SysReport.description → BIAsset.description
        SysReport.owner_id    → BIAsset.owner_id (as string)
        SysReport.acl         → BIAsset.acl
        SysReport.domain      → BiUrn.domain (mapped to BIDomain)
        SysReport.created_at  → BIAsset.created_at
        tenant_id (context)   → BIAsset.tenant_id
    """
    # Map domain string to BIDomain enum, fallback to SALES for unknown
    domain_map = {
        "sales": BIDomain.SALES,
        "finance": BIDomain.FINANCE,
        "executive": BIDomain.EXECUTIVE,
        "operations": BIDomain.OPERATIONS,
    }
    bi_domain = domain_map.get(row.domain, BIDomain.SALES)

    return BIAsset(
        urn=BiUrn(
            resource_type=ResourceType.REPORT,
            domain=bi_domain,
            identifier=str(row.id),
        ),
        display_name=row.title,
        description=row.description or "",
        owner="tenant-user",
        freshness=DataFreshness.SNAPSHOT,
        source_phase="S7-4",
        tenant_id=tenant_id,
        owner_id=str(row.owner_id),
        acl=row.acl if isinstance(row.acl, list) else [],
        tags=["user-created", "report", row.domain],
        created_at=row.created_at.isoformat() if row.created_at else "",
    )
