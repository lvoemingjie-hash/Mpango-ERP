"""
P7-0 + S7-1 + S7-4: Governance Package — BI Asset Modeling, URN System,
Policy Engine & Tenant-Scoped Assets.

This package provides the governance data model and policy engine for
Mpango ERP's BI layer.

- P7-0: BIAsset, URN, GovernanceRegistry (asset modeling)
- S7-1: PolicySubject, PolicyResult, evaluate_policy() (the law)
- S7-4: Owner Bypass, ACL, DynamicResolver, LRU Cache (tenant assets)

No enforcement logic (middleware/decorators) lives here — only models,
the registry, and pure policy evaluation logic.

Quick Start:
    from core.governance import (
        # P7-0: Models & Registry
        BIAction, BIAsset, BiUrn, ResourceType, BIDomain, DataFreshness,
        GOVERNANCE_REGISTRY, get_asset, list_assets,
        # S7-1 + S7-4: Policy Engine
        PolicySubject, PolicyResult, evaluate_policy,
        # S7-4: Dynamic Resolution
        get_asset_async, register_resolver, invalidate_asset,
    )

    # Evaluate a policy decision
    subject = PolicySubject(
        user_id="user-123",
        tenant_id="tenant-abc",
        roles=frozenset({"finance"}),
    )
    asset = get_asset("urn:bi:view:sales:mv_sales_daily")
    result = evaluate_policy(subject, BIAction.EXPORT, asset)
    # result.allowed == True, result.policy_name == "role_matrix_baseline"
"""
from core.governance.models import (
    ACL_MAX_ACTIONS,
    BIAction,
    BIAsset,
    BIDomain,
    BiUrn,
    DataFreshness,
    ResourceType,
)
from core.governance.resolver import (
    AssetResolver,
    CacheInvalidator,
    NullResolver,
)
from core.governance.registry import (
    GOVERNANCE_REGISTRY,
    get_asset,
    get_asset_async,
    list_assets,
    list_assets_async,
    list_urns,
    asset_count,
    register_resolver,
    get_resolver,
    invalidate_asset,
    invalidate_tenant,
    invalidate_all,
    dynamic_cache_size,
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
from core.governance.roles import (
    DEFAULT_BI_PERMISSIONS,
    ADMIN_ROLE_NAME,
    get_allowed_actions,
    is_action_allowed_for_role,
    list_roles_with_action,
)

__all__ = [
    # Enums (P7-0)
    "BIAction",
    "ResourceType",
    "BIDomain",
    "DataFreshness",
    # Models (P7-0 + S7-4)
    "BIAsset",
    "BiUrn",
    "ACL_MAX_ACTIONS",
    # Resolver (S7-4)
    "AssetResolver",
    "CacheInvalidator",
    "NullResolver",
    # Registry (P7-0 + S7-4)
    "GOVERNANCE_REGISTRY",
    "get_asset",
    "get_asset_async",
    "list_assets",
    "list_assets_async",
    "list_urns",
    "asset_count",
    "register_resolver",
    "get_resolver",
    "invalidate_asset",
    "invalidate_tenant",
    "invalidate_all",
    "dynamic_cache_size",
    # Policy Engine (S7-1 + S7-4)
    "PolicySubject",
    "PolicyResult",
    "evaluate_policy",
    "POLICY_TENANT_ISOLATION",
    "POLICY_ADMIN_BYPASS",
    "POLICY_OWNER_BYPASS",
    "POLICY_ACL_GRANT",
    "POLICY_ROLE_MATRIX",
    "POLICY_DEFAULT_DENY",
    # Roles (S7-1)
    "DEFAULT_BI_PERMISSIONS",
    "ADMIN_ROLE_NAME",
    "get_allowed_actions",
    "is_action_allowed_for_role",
    "list_roles_with_action",
]
