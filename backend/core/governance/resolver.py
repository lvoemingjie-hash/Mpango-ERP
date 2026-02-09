"""
S7-4: Asset Resolver — Dynamic Resolution Protocol for Tenant-Scoped Assets.

Philosophy: "The Registry knows what exists. The Resolver finds what's needed."

This module defines the AssetResolver Protocol — the interface that allows
the GovernanceRegistry to resolve URNs that are NOT in the static manifest.
When a URN is not found in the static GOVERNANCE_REGISTRY dict, the registry
delegates to the registered resolver (if any) to look up tenant-created assets
from the database.

Resolution Chain:
    1. Static Lookup (GOVERNANCE_REGISTRY dict)  — O(1), always first
    2. LRU Cache (in-memory)                     — O(1), avoids DB
    3. DynamicResolver.resolve(urn, tenant_id)   — async DB query

🔒 S7-4-C1 (CTO Mandate, Frozen):
    URN does NOT carry tenant_id. The resolver receives tenant_id as a
    separate parameter (context), not embedded in the URN.

🔒 S7-4-C4 (CTO Mandate, Frozen):
    Cache Invalidation Canon — the following events MUST invalidate cache:
    1. Asset CRUD (create/update/delete)  → invalidate(urn)
    2. ACL change                         → invalidate(urn)
    3. Owner change                       → invalidate(urn)
    4. Tenant deletion                    → invalidate_tenant(tenant_id)

Boot Contract Compliance:
- New file in core/governance/ (no modification to frozen core/ files)
- No database changes
- No imports from api.*, middleware, or dependencies
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from core.governance.models import BIAsset, ResourceType


# ============================================================================
# 1. AssetResolver Protocol — The Pluggable Interface
# ============================================================================

@runtime_checkable
class AssetResolver(Protocol):
    """
    Protocol for dynamic asset resolution from external sources (DB, cache, etc.).

    Implementations:
    - DbAssetResolver: Queries sys_reports table (future S7-4-T3)
    - MockAssetResolver: For unit tests

    The resolver is registered at app startup via register_resolver().
    If no resolver is registered, dynamic resolution is skipped and
    only static assets are available (backwards compatible).

    🔒 S7-4-C1: tenant_id is passed as context, NOT embedded in URN.
    """

    async def resolve(
        self,
        urn: str,
        tenant_id: Optional[str] = None,
    ) -> Optional[BIAsset]:
        """
        Resolve a single URN to a BIAsset.

        Args:
            urn: The full URN string (e.g., "urn:bi:report:sales:my_custom_report").
            tenant_id: Optional tenant context for scoping the lookup.
                       If provided, only assets belonging to this tenant
                       (or system-wide assets) should be returned.

        Returns:
            BIAsset if found, None if not found.
            Must NOT raise exceptions for "not found" — return None instead.
        """
        ...

    async def resolve_by_tenant(
        self,
        tenant_id: str,
        resource_type: Optional[ResourceType] = None,
    ) -> list[BIAsset]:
        """
        List all dynamic assets for a tenant, optionally filtered by type.

        Args:
            tenant_id: The tenant to list assets for.
            resource_type: Optional filter by resource type.

        Returns:
            List of BIAsset objects. Empty list if none found.
        """
        ...


# ============================================================================
# 2. Cache Invalidation Interface
# ============================================================================

class CacheInvalidator(Protocol):
    """
    Protocol for cache invalidation operations.

    🔒 S7-4-C4 (CTO Mandate, Frozen):
        Cache Invalidation Canon — these events MUST trigger invalidation:
        1. Asset CRUD (create/update/delete)  → invalidate(urn)
        2. ACL change                         → invalidate(urn)
        3. Owner change                       → invalidate(urn)
        4. Tenant deletion                    → invalidate_tenant(tenant_id)

    The registry implements this protocol internally. External callers
    (CRUD API, admin endpoints) call these methods after mutations.
    """

    def invalidate(self, urn: str) -> None:
        """
        Invalidate a single cached asset by URN.

        Called after: asset create, update, delete, ACL change, owner change.
        """
        ...

    def invalidate_tenant(self, tenant_id: str) -> None:
        """
        Invalidate ALL cached assets for a tenant.

        Called after: tenant deletion, bulk tenant operations.
        """
        ...

    def invalidate_all(self) -> None:
        """
        Invalidate the entire dynamic asset cache.

        Called after: schema migrations, emergency cache flush.
        """
        ...


# ============================================================================
# 3. Null Resolver — Default when no resolver is registered
# ============================================================================

class NullResolver:
    """
    No-op resolver that always returns None / empty list.

    This is the default when no dynamic resolver is registered.
    Ensures backwards compatibility: the system works with static assets only.
    """

    async def resolve(
        self,
        urn: str,
        tenant_id: Optional[str] = None,
    ) -> Optional[BIAsset]:
        return None

    async def resolve_by_tenant(
        self,
        tenant_id: str,
        resource_type: Optional[ResourceType] = None,
    ) -> list[BIAsset]:
        return []
