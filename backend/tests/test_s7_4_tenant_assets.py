"""
S7-4: Tenant-Scoped Assets — Unit Tests.

Tests the S7-4 evolution: Owner Bypass, ACL authorization channel,
Dynamic Registry resolution, and LRU cache with invalidation.

Test Categories:
    1. BIAsset Model — owner_id, acl fields, validation, helpers
    2. Owner Bypass Policy — 🔒 S7-4-C2
    3. ACL Policy — 🔒 S7-4-C3′ (Semantic B, independent channel)
    4. Policy Backwards Compatibility — system assets unchanged
    5. Dynamic Registry — Static + Cache + Resolver chain
    6. Cache Invalidation — 🔒 S7-4-C4
"""
from typing import Optional
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from core.governance.models import (
    ACL_MAX_ACTIONS,
    BIAction,
    BIAsset,
    BIDomain,
    BiUrn,
    DataFreshness,
    ResourceType,
)
from core.governance.policy import (
    PolicySubject,
    PolicyResult,
    evaluate_policy,
    POLICY_TENANT_ISOLATION,
    POLICY_ADMIN_BYPASS,
    POLICY_OWNER_BYPASS,
    POLICY_ACL_GRANT,
    POLICY_ROLE_MATRIX,
    POLICY_DEFAULT_DENY,
)
from core.governance.registry import (
    GOVERNANCE_REGISTRY,
    get_asset,
    get_asset_async,
    register_resolver,
    invalidate_asset,
    invalidate_tenant,
    invalidate_all,
    dynamic_cache_size,
    _dynamic_cache,
    _dynamic_cache_lock,
    _cache_put,
    _cache_get,
    asset_count,
)
from core.governance.resolver import AssetResolver, NullResolver


# ============================================================================
# Helpers
# ============================================================================

def _make_tenant_asset(
    identifier: str = "my_custom_report",
    domain: BIDomain = BIDomain.SALES,
    resource_type: ResourceType = ResourceType.REPORT,
    tenant_id: str = "tenant-abc",
    owner_id: Optional[str] = "user-owner-001",
    acl: Optional[list[str]] = None,
) -> BIAsset:
    """Create a tenant-scoped BIAsset for testing."""
    return BIAsset(
        urn=BiUrn(
            resource_type=resource_type,
            domain=domain,
            identifier=identifier,
        ),
        display_name=f"Test Asset: {identifier}",
        tenant_id=tenant_id,
        owner_id=owner_id,
        acl=acl or [],
        source_phase="S7-4",
    )


def _make_subject(
    user_id: str = "user-001",
    tenant_id: str = "tenant-abc",
    roles: frozenset[str] = frozenset({"viewer"}),
) -> PolicySubject:
    return PolicySubject(user_id=user_id, tenant_id=tenant_id, roles=roles)


# ============================================================================
# 1. BIAsset Model Tests — owner_id, acl, validation
# ============================================================================

class TestBIAssetOwnershipFields:
    """Test S7-4 additions to BIAsset model."""

    def test_system_asset_defaults(self):
        """System assets have no owner_id and empty acl by default."""
        asset = get_asset("urn:bi:view:sales:mv_sales_daily")
        assert asset.owner_id is None
        assert asset.acl == []
        assert asset.has_owner is False
        assert asset.is_shared is False
        assert asset.is_system_wide is True
        assert asset.is_tenant_scoped is False

    def test_tenant_asset_with_owner(self):
        """Tenant asset with owner_id set."""
        asset = _make_tenant_asset(owner_id="user-123")
        assert asset.owner_id == "user-123"
        assert asset.has_owner is True
        assert asset.is_system_wide is False
        assert asset.is_tenant_scoped is True

    def test_is_owned_by(self):
        """is_owned_by checks owner_id match."""
        asset = _make_tenant_asset(owner_id="user-123")
        assert asset.is_owned_by("user-123") is True
        assert asset.is_owned_by("user-456") is False

    def test_is_owned_by_no_owner(self):
        """is_owned_by returns False when no owner."""
        asset = _make_tenant_asset(owner_id=None)
        assert asset.is_owned_by("user-123") is False

    def test_acl_entries(self):
        """ACL entries are stored correctly."""
        asset = _make_tenant_asset(acl=["user:u1", "role:finance", "tenant:*"])
        assert asset.is_shared is True
        assert len(asset.acl) == 3

    def test_acl_validation_invalid_prefix(self):
        """ACL entries with invalid prefix are rejected."""
        with pytest.raises(ValidationError):
            _make_tenant_asset(acl=["invalid:entry"])

    def test_acl_validation_empty_value(self):
        """ACL entries with empty value after prefix are rejected."""
        with pytest.raises(ValidationError):
            _make_tenant_asset(acl=["user:"])

    def test_acl_check_user_match(self):
        """check_acl matches user:<id> entries."""
        asset = _make_tenant_asset(acl=["user:u1", "user:u2"])
        assert asset.check_acl("u1", frozenset()) is True
        assert asset.check_acl("u3", frozenset()) is False

    def test_acl_check_role_match(self):
        """check_acl matches role:<name> entries."""
        asset = _make_tenant_asset(acl=["role:finance"])
        assert asset.check_acl("u1", frozenset({"finance"})) is True
        assert asset.check_acl("u1", frozenset({"sales"})) is False

    def test_acl_check_tenant_wildcard(self):
        """check_acl matches tenant:* for any user."""
        asset = _make_tenant_asset(acl=["tenant:*"])
        assert asset.check_acl("anyone", frozenset()) is True

    def test_acl_check_empty_acl(self):
        """check_acl returns False for empty ACL."""
        asset = _make_tenant_asset(acl=[])
        assert asset.check_acl("u1", frozenset({"admin"})) is False

    def test_acl_max_actions_constant(self):
        """ACL_MAX_ACTIONS contains VIEW, INTERACT, EXPORT but not MANAGE."""
        assert BIAction.VIEW in ACL_MAX_ACTIONS
        assert BIAction.INTERACT in ACL_MAX_ACTIONS
        assert BIAction.EXPORT in ACL_MAX_ACTIONS
        assert BIAction.MANAGE not in ACL_MAX_ACTIONS


# ============================================================================
# 2. Owner Bypass Policy — 🔒 S7-4-C2
# ============================================================================

class TestOwnerBypass:
    """Test owner bypass rule in evaluate_policy."""

    def test_owner_can_view_own_asset(self):
        """Owner can VIEW their own tenant asset."""
        asset = _make_tenant_asset(owner_id="user-001", tenant_id="tenant-abc")
        subject = _make_subject(user_id="user-001", tenant_id="tenant-abc")
        result = evaluate_policy(subject, BIAction.VIEW, asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_OWNER_BYPASS

    def test_owner_can_manage_own_asset(self):
        """Owner can MANAGE their own tenant asset."""
        asset = _make_tenant_asset(owner_id="user-001", tenant_id="tenant-abc")
        subject = _make_subject(user_id="user-001", tenant_id="tenant-abc")
        result = evaluate_policy(subject, BIAction.MANAGE, asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_OWNER_BYPASS

    def test_owner_can_export_own_asset(self):
        """Owner can EXPORT their own tenant asset."""
        asset = _make_tenant_asset(owner_id="user-001", tenant_id="tenant-abc")
        subject = _make_subject(user_id="user-001", tenant_id="tenant-abc")
        result = evaluate_policy(subject, BIAction.EXPORT, asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_OWNER_BYPASS

    def test_owner_bypass_not_for_system_assets(self):
        """🔒 S7-4-C2: Owner bypass does NOT apply to system assets."""
        system_asset = get_asset("urn:bi:view:sales:mv_sales_daily")
        subject = _make_subject(
            user_id="backend-engineering",  # matches asset.owner default
            tenant_id="tenant-abc",
        )
        result = evaluate_policy(subject, BIAction.MANAGE, system_asset)
        # Should NOT get owner_bypass — system asset has no owner_id
        assert result.policy_name != POLICY_OWNER_BYPASS

    def test_owner_bypass_requires_same_tenant(self):
        """🔒 S7-4-C2: Owner bypass requires tenant match."""
        asset = _make_tenant_asset(
            owner_id="user-001", tenant_id="tenant-abc"
        )
        subject = _make_subject(
            user_id="user-001", tenant_id="tenant-xyz"
        )
        result = evaluate_policy(subject, BIAction.VIEW, asset)
        # Tenant isolation should deny BEFORE owner bypass
        assert result.allowed is False
        assert result.policy_name == POLICY_TENANT_ISOLATION

    def test_non_owner_does_not_get_bypass(self):
        """Non-owner does not get owner bypass."""
        asset = _make_tenant_asset(
            owner_id="user-001", tenant_id="tenant-abc"
        )
        subject = _make_subject(
            user_id="user-other", tenant_id="tenant-abc",
            roles=frozenset(),
        )
        result = evaluate_policy(subject, BIAction.VIEW, asset)
        # No owner bypass, no role match → default deny
        assert result.allowed is False
        assert result.policy_name == POLICY_DEFAULT_DENY

    def test_owner_bypass_not_for_no_owner_asset(self):
        """Tenant asset without owner_id does not trigger owner bypass."""
        asset = _make_tenant_asset(owner_id=None, tenant_id="tenant-abc")
        subject = _make_subject(
            user_id="user-001", tenant_id="tenant-abc",
            roles=frozenset(),
        )
        result = evaluate_policy(subject, BIAction.VIEW, asset)
        assert result.policy_name != POLICY_OWNER_BYPASS
        assert result.allowed is False


# ============================================================================
# 3. ACL Policy — 🔒 S7-4-C3′ (Semantic B)
# ============================================================================

class TestACLPolicy:
    """Test ACL authorization channel in evaluate_policy."""

    def test_acl_grants_view_to_shared_user(self):
        """ACL user entry grants VIEW."""
        asset = _make_tenant_asset(
            owner_id="owner-001",
            tenant_id="tenant-abc",
            acl=["user:viewer-001"],
        )
        subject = _make_subject(
            user_id="viewer-001", tenant_id="tenant-abc",
            roles=frozenset(),  # no roles at all
        )
        result = evaluate_policy(subject, BIAction.VIEW, asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ACL_GRANT

    def test_acl_grants_export_independent_of_role(self):
        """🔒 S7-4-C3′ Semantic B: ACL grants EXPORT even if role only has VIEW."""
        asset = _make_tenant_asset(
            owner_id="owner-001",
            tenant_id="tenant-abc",
            acl=["user:viewer-001"],
        )
        subject = _make_subject(
            user_id="viewer-001", tenant_id="tenant-abc",
            roles=frozenset({"viewer"}),  # viewer only has VIEW in matrix
        )
        result = evaluate_policy(subject, BIAction.EXPORT, asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ACL_GRANT

    def test_acl_never_grants_manage(self):
        """🔒 S7-4-C3′: ACL NEVER grants MANAGE, even with user entry."""
        asset = _make_tenant_asset(
            owner_id="owner-001",
            tenant_id="tenant-abc",
            acl=["user:viewer-001"],
        )
        subject = _make_subject(
            user_id="viewer-001", tenant_id="tenant-abc",
            roles=frozenset(),
        )
        result = evaluate_policy(subject, BIAction.MANAGE, asset)
        assert result.allowed is False
        # ACL cannot grant MANAGE → falls through to default deny
        assert result.policy_name == POLICY_DEFAULT_DENY

    def test_acl_role_entry_grants_access(self):
        """ACL role entry grants access to users with that role."""
        asset = _make_tenant_asset(
            owner_id="owner-001",
            tenant_id="tenant-abc",
            acl=["role:finance"],
        )
        subject = _make_subject(
            user_id="finance-user", tenant_id="tenant-abc",
            roles=frozenset({"finance"}),
        )
        result = evaluate_policy(subject, BIAction.INTERACT, asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ACL_GRANT

    def test_acl_tenant_wildcard_grants_access(self):
        """ACL tenant:* grants access to all users in the tenant."""
        asset = _make_tenant_asset(
            owner_id="owner-001",
            tenant_id="tenant-abc",
            acl=["tenant:*"],
        )
        subject = _make_subject(
            user_id="random-user", tenant_id="tenant-abc",
            roles=frozenset(),
        )
        result = evaluate_policy(subject, BIAction.VIEW, asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ACL_GRANT

    def test_acl_does_not_match_wrong_user(self):
        """ACL user entry does not match a different user."""
        asset = _make_tenant_asset(
            owner_id="owner-001",
            tenant_id="tenant-abc",
            acl=["user:specific-user"],
        )
        subject = _make_subject(
            user_id="other-user", tenant_id="tenant-abc",
            roles=frozenset(),
        )
        result = evaluate_policy(subject, BIAction.VIEW, asset)
        assert result.allowed is False

    def test_acl_does_not_bypass_tenant_isolation(self):
        """ACL cannot bypass tenant isolation."""
        asset = _make_tenant_asset(
            owner_id="owner-001",
            tenant_id="tenant-abc",
            acl=["user:cross-tenant-user"],
        )
        subject = _make_subject(
            user_id="cross-tenant-user", tenant_id="tenant-xyz",
        )
        result = evaluate_policy(subject, BIAction.VIEW, asset)
        assert result.allowed is False
        assert result.policy_name == POLICY_TENANT_ISOLATION

    def test_empty_acl_no_grant(self):
        """Empty ACL does not grant access."""
        asset = _make_tenant_asset(
            owner_id="owner-001",
            tenant_id="tenant-abc",
            acl=[],
        )
        subject = _make_subject(
            user_id="other-user", tenant_id="tenant-abc",
            roles=frozenset(),
        )
        result = evaluate_policy(subject, BIAction.VIEW, asset)
        assert result.allowed is False

    def test_acl_interact_granted(self):
        """ACL grants INTERACT."""
        asset = _make_tenant_asset(
            owner_id="owner-001",
            tenant_id="tenant-abc",
            acl=["user:analyst-001"],
        )
        subject = _make_subject(
            user_id="analyst-001", tenant_id="tenant-abc",
            roles=frozenset(),
        )
        result = evaluate_policy(subject, BIAction.INTERACT, asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ACL_GRANT


# ============================================================================
# 4. Policy Backwards Compatibility
# ============================================================================

class TestPolicyBackwardsCompat:
    """Verify S7-4 changes are no-ops for system assets."""

    def test_admin_still_bypasses_on_system_asset(self):
        """Admin bypass unchanged for system assets."""
        asset = get_asset("urn:bi:view:sales:mv_sales_daily")
        subject = _make_subject(
            user_id="admin-001", tenant_id="tenant-abc",
            roles=frozenset({"admin"}),
        )
        result = evaluate_policy(subject, BIAction.VIEW, asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ADMIN_BYPASS

    def test_finance_still_exports_system_asset(self):
        """Finance role matrix unchanged for system assets."""
        asset = get_asset("urn:bi:view:sales:mv_sales_daily")
        subject = _make_subject(
            user_id="fin-001", tenant_id="tenant-abc",
            roles=frozenset({"finance"}),
        )
        result = evaluate_policy(subject, BIAction.EXPORT, asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ROLE_MATRIX

    def test_viewer_still_denied_export_system_asset(self):
        """Viewer still denied EXPORT on system assets."""
        asset = get_asset("urn:bi:view:sales:mv_sales_daily")
        subject = _make_subject(
            user_id="viewer-001", tenant_id="tenant-abc",
            roles=frozenset({"viewer"}),
        )
        result = evaluate_policy(subject, BIAction.EXPORT, asset)
        assert result.allowed is False
        assert result.policy_name == POLICY_DEFAULT_DENY

    def test_cross_tenant_still_denied_system_asset(self):
        """Cross-tenant access still works for system assets (they're system-wide)."""
        asset = get_asset("urn:bi:view:sales:mv_sales_daily")
        subject = _make_subject(
            user_id="admin-001", tenant_id="tenant-xyz",
            roles=frozenset({"admin"}),
        )
        result = evaluate_policy(subject, BIAction.VIEW, asset)
        # System assets have tenant_id=None → accessible to all tenants
        assert result.allowed is True

    def test_all_system_assets_have_no_owner_no_acl(self):
        """All 16 system assets have owner_id=None and acl=[]."""
        for urn, asset in GOVERNANCE_REGISTRY.items():
            assert asset.owner_id is None, f"{urn} has unexpected owner_id"
            assert asset.acl == [], f"{urn} has unexpected acl"

    def test_evaluation_order_owner_before_acl_before_role(self):
        """Owner bypass (step 3) is checked before ACL (step 4) before role matrix (step 5)."""
        # Owner is also in ACL and has a role — should get owner_bypass
        asset = _make_tenant_asset(
            owner_id="user-001",
            tenant_id="tenant-abc",
            acl=["user:user-001", "role:finance"],
        )
        subject = _make_subject(
            user_id="user-001", tenant_id="tenant-abc",
            roles=frozenset({"finance"}),
        )
        result = evaluate_policy(subject, BIAction.EXPORT, asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_OWNER_BYPASS  # Not ACL, not role matrix


# ============================================================================
# 5. Dynamic Registry — Static + Cache + Resolver chain
# ============================================================================

class TestDynamicRegistry:
    """Test the S7-4 resolution chain: Static → Cache → Resolver."""

    def test_static_lookup_unchanged(self):
        """get_asset() still works for static assets."""
        asset = get_asset("urn:bi:view:sales:mv_sales_daily")
        assert asset.display_name == "Daily Sales Revenue"

    def test_static_lookup_raises_for_unknown(self):
        """get_asset() raises KeyError for unknown URN."""
        with pytest.raises(KeyError):
            get_asset("urn:bi:report:sales:nonexistent")

    @pytest.mark.asyncio
    async def test_async_static_lookup(self):
        """get_asset_async() resolves static assets without resolver."""
        asset = await get_asset_async("urn:bi:view:sales:mv_sales_daily")
        assert asset.display_name == "Daily Sales Revenue"

    @pytest.mark.asyncio
    async def test_async_resolver_called_for_unknown_urn(self):
        """get_asset_async() calls resolver when static lookup fails."""
        tenant_asset = _make_tenant_asset(
            identifier="dynamic_report",
            tenant_id="tenant-abc",
        )

        mock_resolver = AsyncMock(spec=AssetResolver)
        mock_resolver.resolve = AsyncMock(return_value=tenant_asset)

        # Save and restore original resolver
        from core.governance import registry as reg
        original = reg._resolver
        try:
            register_resolver(mock_resolver)
            # Clear cache to force resolver call
            invalidate_all()

            result = await get_asset_async(
                "urn:bi:report:sales:dynamic_report",
                tenant_id="tenant-abc",
            )
            assert result.display_name == "Test Asset: dynamic_report"
            mock_resolver.resolve.assert_called_once_with(
                "urn:bi:report:sales:dynamic_report", "tenant-abc"
            )
        finally:
            reg._resolver = original
            invalidate_all()

    @pytest.mark.asyncio
    async def test_async_cache_hit_skips_resolver(self):
        """get_asset_async() uses cache and skips resolver on cache hit."""
        tenant_asset = _make_tenant_asset(identifier="cached_report")

        mock_resolver = AsyncMock(spec=AssetResolver)
        mock_resolver.resolve = AsyncMock(return_value=tenant_asset)

        from core.governance import registry as reg
        original = reg._resolver
        try:
            register_resolver(mock_resolver)
            invalidate_all()

            # First call: resolver is called, result cached
            urn = "urn:bi:report:sales:cached_report"
            await get_asset_async(urn, tenant_id="tenant-abc")
            assert mock_resolver.resolve.call_count == 1

            # Second call: cache hit, resolver NOT called
            await get_asset_async(urn, tenant_id="tenant-abc")
            assert mock_resolver.resolve.call_count == 1  # still 1
        finally:
            reg._resolver = original
            invalidate_all()

    @pytest.mark.asyncio
    async def test_async_raises_for_truly_unknown(self):
        """get_asset_async() raises KeyError when all sources fail."""
        mock_resolver = AsyncMock(spec=AssetResolver)
        mock_resolver.resolve = AsyncMock(return_value=None)

        from core.governance import registry as reg
        original = reg._resolver
        try:
            register_resolver(mock_resolver)
            invalidate_all()

            with pytest.raises(KeyError, match="Asset not found in any source"):
                await get_asset_async(
                    "urn:bi:report:sales:truly_nonexistent",
                    tenant_id="tenant-abc",
                )
        finally:
            reg._resolver = original
            invalidate_all()

    def test_null_resolver_returns_none(self):
        """NullResolver always returns None."""
        resolver = NullResolver()
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            resolver.resolve("urn:bi:report:sales:anything")
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_null_resolver_list_empty(self):
        """NullResolver.resolve_by_tenant returns empty list."""
        resolver = NullResolver()
        result = await resolver.resolve_by_tenant("tenant-abc")
        assert result == []


# ============================================================================
# 6. Cache Invalidation — 🔒 S7-4-C4
# ============================================================================

class TestCacheInvalidation:
    """Test cache invalidation per S7-4-C4."""

    def setup_method(self):
        """Clear cache before each test."""
        invalidate_all()

    def teardown_method(self):
        """Clear cache after each test."""
        invalidate_all()

    def test_cache_put_and_get(self):
        """Basic cache put/get."""
        asset = _make_tenant_asset(identifier="cache_test")
        _cache_put("urn:bi:report:sales:cache_test", asset)
        result = _cache_get("urn:bi:report:sales:cache_test")
        assert result is not None
        assert result.urn_string == "urn:bi:report:sales:cache_test"

    def test_cache_miss(self):
        """Cache miss returns None."""
        result = _cache_get("urn:bi:report:sales:nonexistent")
        assert result is None

    def test_invalidate_asset_removes_entry(self):
        """invalidate_asset removes a specific cached entry."""
        asset = _make_tenant_asset(identifier="to_invalidate")
        urn = "urn:bi:report:sales:to_invalidate"
        _cache_put(urn, asset)
        assert _cache_get(urn) is not None

        invalidate_asset(urn)
        assert _cache_get(urn) is None

    def test_invalidate_tenant_removes_all_tenant_entries(self):
        """invalidate_tenant removes all entries for a tenant."""
        asset1 = _make_tenant_asset(identifier="t1_report1", tenant_id="tenant-abc")
        asset2 = _make_tenant_asset(identifier="t1_report2", tenant_id="tenant-abc")
        asset3 = _make_tenant_asset(identifier="t2_report1", tenant_id="tenant-xyz")

        _cache_put("urn:bi:report:sales:t1_report1", asset1)
        _cache_put("urn:bi:report:sales:t1_report2", asset2)
        _cache_put("urn:bi:report:sales:t2_report1", asset3)

        assert dynamic_cache_size() == 3

        invalidate_tenant("tenant-abc")

        assert dynamic_cache_size() == 1
        assert _cache_get("urn:bi:report:sales:t1_report1") is None
        assert _cache_get("urn:bi:report:sales:t1_report2") is None
        assert _cache_get("urn:bi:report:sales:t2_report1") is not None

    def test_invalidate_all_clears_cache(self):
        """invalidate_all clears the entire cache."""
        for i in range(5):
            asset = _make_tenant_asset(identifier=f"bulk_{i}")
            _cache_put(f"urn:bi:report:sales:bulk_{i}", asset)

        assert dynamic_cache_size() == 5
        invalidate_all()
        assert dynamic_cache_size() == 0

    def test_cache_lru_eviction(self):
        """Cache evicts oldest entry when at capacity."""
        from core.governance import registry as reg
        original_max = reg._LRU_CACHE_MAX_SIZE
        try:
            # Temporarily set small cache size
            reg._LRU_CACHE_MAX_SIZE = 3

            for i in range(4):
                asset = _make_tenant_asset(identifier=f"lru_{i}")
                _cache_put(f"urn:bi:report:sales:lru_{i}", asset)

            # Oldest (lru_0) should have been evicted
            assert _cache_get("urn:bi:report:sales:lru_0") is None
            assert _cache_get("urn:bi:report:sales:lru_3") is not None
        finally:
            reg._LRU_CACHE_MAX_SIZE = original_max
            invalidate_all()


# ============================================================================
# 7. Combined Scenarios — Owner + ACL + Role Matrix interaction
# ============================================================================

class TestCombinedScenarios:
    """Test realistic multi-factor scenarios."""

    def test_finance_shares_report_with_viewer_for_export(self):
        """
        Product scenario: Finance user creates a report and shares it
        with a viewer colleague, granting them EXPORT capability.
        Viewer normally can only VIEW in the role matrix.
        """
        asset = _make_tenant_asset(
            identifier="quarterly_revenue",
            owner_id="finance-user-001",
            tenant_id="tenant-abc",
            acl=["user:viewer-colleague"],
        )
        # Viewer colleague can EXPORT via ACL (Semantic B: independent channel)
        subject = _make_subject(
            user_id="viewer-colleague",
            tenant_id="tenant-abc",
            roles=frozenset({"viewer"}),
        )
        result = evaluate_policy(subject, BIAction.EXPORT, asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ACL_GRANT

    def test_viewer_cannot_manage_shared_report(self):
        """Viewer with ACL access cannot MANAGE the shared report."""
        asset = _make_tenant_asset(
            identifier="quarterly_revenue",
            owner_id="finance-user-001",
            tenant_id="tenant-abc",
            acl=["user:viewer-colleague"],
        )
        subject = _make_subject(
            user_id="viewer-colleague",
            tenant_id="tenant-abc",
            roles=frozenset({"viewer"}),
        )
        result = evaluate_policy(subject, BIAction.MANAGE, asset)
        assert result.allowed is False

    def test_owner_can_manage_but_shared_user_cannot(self):
        """Owner can MANAGE, shared user cannot."""
        asset = _make_tenant_asset(
            identifier="my_dashboard",
            owner_id="creator-001",
            tenant_id="tenant-abc",
            acl=["user:collaborator-001"],
        )
        # Owner can MANAGE
        owner = _make_subject(
            user_id="creator-001", tenant_id="tenant-abc",
            roles=frozenset({"viewer"}),
        )
        assert evaluate_policy(owner, BIAction.MANAGE, asset).allowed is True

        # Collaborator cannot MANAGE
        collab = _make_subject(
            user_id="collaborator-001", tenant_id="tenant-abc",
            roles=frozenset({"viewer"}),
        )
        assert evaluate_policy(collab, BIAction.MANAGE, asset).allowed is False

    def test_admin_can_manage_any_tenant_asset(self):
        """Admin can MANAGE any asset in their tenant (step 2 bypass)."""
        asset = _make_tenant_asset(
            identifier="someone_elses_report",
            owner_id="other-user",
            tenant_id="tenant-abc",
            acl=[],
        )
        admin = _make_subject(
            user_id="admin-001", tenant_id="tenant-abc",
            roles=frozenset({"admin"}),
        )
        result = evaluate_policy(admin, BIAction.MANAGE, asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ADMIN_BYPASS

    def test_role_shared_report_grants_to_all_finance(self):
        """ACL with role:finance grants access to all finance users."""
        asset = _make_tenant_asset(
            identifier="team_report",
            owner_id="lead-001",
            tenant_id="tenant-abc",
            acl=["role:finance"],
        )
        fin_user = _make_subject(
            user_id="fin-analyst",
            tenant_id="tenant-abc",
            roles=frozenset({"finance"}),
        )
        result = evaluate_policy(fin_user, BIAction.EXPORT, asset)
        assert result.allowed is True
        assert result.policy_name == POLICY_ACL_GRANT

    def test_no_role_no_acl_no_owner_denied(self):
        """User with no roles, not in ACL, not owner → denied."""
        asset = _make_tenant_asset(
            identifier="private_report",
            owner_id="owner-001",
            tenant_id="tenant-abc",
            acl=[],
        )
        stranger = _make_subject(
            user_id="stranger", tenant_id="tenant-abc",
            roles=frozenset(),
        )
        result = evaluate_policy(stranger, BIAction.VIEW, asset)
        assert result.allowed is False
        assert result.policy_name == POLICY_DEFAULT_DENY
