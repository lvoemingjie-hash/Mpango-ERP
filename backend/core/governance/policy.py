"""
S7-1 + S7-4: BI Policy Engine — The Law.

Philosophy: "Given a Subject, an Action, and an Asset in a Tenant Context,
is this allowed?"

This module is the pure-logic policy engine for Mpango ERP's BI governance
layer. It evaluates access decisions without any dependency on web frameworks,
HTTP requests, or middleware. It is a bottom-layer service that can be called
from HTTP API handlers, background job workers (S6-4), CLI tools, or tests.

🔒 Constraint S7-1-A (CTO Mandate, Frozen):
    PolicySubject.roles MUST originate from a backend-trusted authority
    (Database / Directory / IAM). It is STRICTLY FORBIDDEN to directly
    trust roles or scopes from JWT tokens, request payloads, or any
    client-supplied source. The HTTP/Job layer is responsible for loading
    roles from the DB and constructing a PolicySubject before calling
    this engine.

Evaluation Order (S7-1 + S7-4, Canonical):
    1. Tenant Isolation   — subject.tenant_id ≠ asset.tenant_id → DENY
    2. Admin Bypass        — "admin" ∈ subject.roles → ALLOW
    3. Owner Bypass (S7-4) — asset.owner_id == subject.user_id → ALLOW
       🔒 S7-4-C2: Only for tenant-scoped assets, not system assets.
       Owner cannot bypass tenant isolation (already checked in step 1).
    4. ACL Check (S7-4)    — subject matches asset.acl entry → ALLOW
       🔒 S7-4-C3′: ACL grants VIEW/INTERACT/EXPORT only, NEVER MANAGE.
       ACL is an independent authorization channel (Semantic B).
    5. Role-Action Matrix  — lookup (role, action) in baseline matrix → ALLOW/DENY
    6. Default Deny        — no matching policy → DENY

    ⚠️ Tenant Isolation is ALWAYS before Admin Bypass.
    admin ≠ god. An admin of Tenant A cannot access Tenant B's assets.

Design Principles:
- Pure Python logic. No FastAPI, no Request, no Depends, no HTTPException.
- Framework-agnostic: serves HTTP API, Background Jobs (S6-4), and CLI.
- Strongly typed: BIAction enum, BIAsset model, PolicySubject model.
- Auditable: PolicyResult contains all fields needed for compliance logging.

Boot Contract Compliance:
- New file in core/governance/ (no modification to frozen core/ files)
- No database changes
- No imports from api.*, middleware, or dependencies
"""
from __future__ import annotations

from typing import Optional, Union

from pydantic import BaseModel, Field, field_validator

from core.governance.models import ACL_MAX_ACTIONS, BIAction, BIAsset, BiUrn
from core.governance.roles import (
    ADMIN_ROLE_NAME,
    DEFAULT_BI_PERMISSIONS,
    get_allowed_actions,
)


# ============================================================================
# 1. PolicySubject — Who is asking?
# ============================================================================

class PolicySubject(BaseModel):
    """
    The identity context for policy evaluation.

    This is a framework-agnostic representation of "who is making the request."
    It is constructed by the HTTP layer (from TokenPayload + DB-loaded roles)
    or by the job worker (from job payload + DB-loaded roles).

    🔒 Constraint S7-1-A (CTO Mandate, Frozen):
        The `roles` field MUST be populated from a backend-trusted authority
        (Database query, Directory service, IAM provider).
        It is STRICTLY FORBIDDEN to directly trust roles from:
        - JWT token claims (tokens can be mis-issued)
        - Request payloads (clients can forge roles)
        - SSO assertions without backend verification (SSO config can drift)

        The caller (HTTP middleware, job worker) is responsible for:
        1. Authenticating the user (JWT verification)
        2. Loading the user's roles from the tenant DB
        3. Constructing this PolicySubject with DB-sourced roles
        4. Passing it to evaluate_policy()

    Attributes:
        user_id: Authenticated user UUID (from JWT, verified).
        tenant_id: Tenant UUID (from JWT, verified).
        roles: Set of role names loaded from the backend DB.
               Must NOT come directly from token claims.
    """
    user_id: str = Field(
        ...,
        min_length=1,
        description="Authenticated user UUID"
    )
    tenant_id: str = Field(
        ...,
        min_length=1,
        description="Tenant UUID from verified JWT"
    )
    roles: frozenset[str] = Field(
        ...,
        description="Role names loaded from backend DB. "
                    "MUST NOT come directly from token claims (S7-1-A)."
    )

    @field_validator("roles", mode="before")
    @classmethod
    def coerce_roles(cls, v):
        """Accept set, list, tuple, or frozenset and normalize to frozenset."""
        if isinstance(v, frozenset):
            return v
        if isinstance(v, (set, list, tuple)):
            return frozenset(v)
        raise ValueError(f"roles must be a set-like collection, got {type(v)}")

    @property
    def is_admin(self) -> bool:
        """Check if subject has the admin role."""
        return ADMIN_ROLE_NAME in self.roles

    model_config = {"frozen": True}


# ============================================================================
# 2. PolicyResult — The verdict
# ============================================================================

class PolicyResult(BaseModel):
    """
    The structured result of a policy evaluation.

    Every field is designed for auditability. This object can be:
    - Logged to an audit trail (P7-3 future)
    - Returned to the caller for error messaging
    - Used in "Explain Why" UX ("Why can't I export this?")

    Attributes:
        allowed: Whether the action is permitted.
        reason: Human-readable explanation of the decision.
        policy_name: Which policy rule produced this result.
        subject_id: The user who requested access (audit trail).
        asset_urn: The asset that was accessed (audit trail).
        action: The action that was attempted (audit trail).
    """
    allowed: bool
    reason: str = Field(
        ...,
        description="Human-readable explanation of the decision"
    )
    policy_name: str = Field(
        ...,
        description="Name of the policy rule that produced this result "
                    "(e.g., 'tenant_isolation', 'admin_bypass', 'role_matrix')"
    )
    subject_id: str = Field(
        ...,
        description="User ID of the subject (for audit trail)"
    )
    asset_urn: str = Field(
        ...,
        description="URN of the asset (for audit trail)"
    )
    action: str = Field(
        ...,
        description="BIAction value that was evaluated (for audit trail)"
    )

    model_config = {"frozen": True}


# ============================================================================
# 3. Policy Names (Constants)
# ============================================================================

POLICY_TENANT_ISOLATION = "tenant_isolation"
POLICY_ADMIN_BYPASS = "admin_bypass"
POLICY_OWNER_BYPASS = "owner_bypass"
POLICY_ACL_GRANT = "acl_grant"
POLICY_ROLE_MATRIX = "role_matrix_baseline"
POLICY_DEFAULT_DENY = "default_deny"


# ============================================================================
# 4. The Policy Engine — evaluate_policy()
# ============================================================================

def evaluate_policy(
    subject: PolicySubject,
    action: BIAction,
    asset: Union[BIAsset, str],
) -> PolicyResult:
    """
    Evaluate whether a subject is allowed to perform an action on an asset.

    This is the core entry point of the S7-1 + S7-4 Policy Engine.
    It implements the canonical evaluation order:

        1. Tenant Isolation   → DENY if tenant mismatch
        2. Admin Bypass       → ALLOW if subject is admin
        3. Owner Bypass (S7-4) → ALLOW if owner matches (tenant assets only)
        4. ACL Check (S7-4)   → ALLOW if subject in ACL (ceiling: EXPORT)
        5. Role-Action Matrix → ALLOW if any role grants the action
        6. Default Deny       → DENY (no matching policy)

    Args:
        subject: The authenticated identity context (PolicySubject).
                 roles MUST be loaded from backend DB (S7-1-A).
        action: The BIAction being attempted (VIEW, INTERACT, EXPORT, MANAGE).
        asset: The target BIAsset, or a URN string to be resolved.

    Returns:
        PolicyResult with the decision, reason, and audit fields.

    Raises:
        ValueError: If asset is a string that cannot be parsed as a valid URN.
        TypeError: If asset is neither a BIAsset nor a string.

    Example:
        from core.governance.policy import evaluate_policy, PolicySubject
        from core.governance.models import BIAction
        from core.governance.registry import get_asset

        subject = PolicySubject(
            user_id="user-123",
            tenant_id="tenant-abc",
            roles=frozenset({"finance"}),
        )
        asset = get_asset("urn:bi:view:sales:mv_sales_daily")
        result = evaluate_policy(subject, BIAction.EXPORT, asset)
        # result.allowed == True (finance can export)
    """
    # --- Resolve asset if string ---
    resolved_asset = _resolve_asset(asset)
    urn_str = resolved_asset.urn_string

    # --- Common result kwargs ---
    base = {
        "subject_id": subject.user_id,
        "asset_urn": urn_str,
        "action": action.value,
    }

    # ================================================================
    # Step 1: Tenant Isolation (ALWAYS FIRST — frozen order)
    # ================================================================
    # An admin of Tenant A cannot access Tenant B's assets.
    # System-wide assets (tenant_id=None) are accessible to all tenants.
    if not _check_tenant_isolation(subject, resolved_asset):
        return PolicyResult(
            allowed=False,
            reason=(
                f"Tenant isolation violation: subject tenant '{subject.tenant_id}' "
                f"does not match asset tenant '{resolved_asset.tenant_id}'"
            ),
            policy_name=POLICY_TENANT_ISOLATION,
            **base,
        )

    # ================================================================
    # Step 2: Admin Bypass (after tenant check — admin ≠ god)
    # ================================================================
    if subject.is_admin:
        return PolicyResult(
            allowed=True,
            reason="Admin role grants unrestricted BI access within tenant scope",
            policy_name=POLICY_ADMIN_BYPASS,
            **base,
        )

    # ================================================================
    # Step 3: Owner Bypass (S7-4)
    # ================================================================
    # 🔒 S7-4-C2: Owner bypass conditions:
    #   1. asset.owner_id == subject.user_id
    #   2. asset.tenant_id == subject.tenant_id (cannot bypass tenant isolation)
    #   3. asset.is_system_wide == False (not applicable to system assets)
    owner_result = _check_owner_bypass(subject, action, resolved_asset)
    if owner_result is not None:
        return PolicyResult(**owner_result, **base)

    # ================================================================
    # Step 4: ACL Check (S7-4)
    # ================================================================
    # 🔒 S7-4-C3′: ACL is an independent authorization channel.
    #   - Grants VIEW / INTERACT / EXPORT only (hard ceiling).
    #   - NEVER grants MANAGE.
    #   - Does not depend on Role-Action Matrix.
    acl_result = _check_acl(subject, action, resolved_asset)
    if acl_result is not None:
        return PolicyResult(**acl_result, **base)

    # ================================================================
    # Step 5: Role-Action Matrix (baseline lookup)
    # ================================================================
    # 🔒 Constraint S7-1-B: This is the Global Default Baseline.
    # It does NOT express Asset-Specific permissions.
    granting_role = _check_role_matrix(subject, action)
    if granting_role is not None:
        return PolicyResult(
            allowed=True,
            reason=(
                f"Role '{granting_role}' grants '{action.value}' action "
                f"in the default baseline matrix"
            ),
            policy_name=POLICY_ROLE_MATRIX,
            **base,
        )

    # ================================================================
    # Step 6: Default Deny (no matching policy)
    # ================================================================
    role_list = ", ".join(sorted(subject.roles)) if subject.roles else "(none)"
    return PolicyResult(
        allowed=False,
        reason=(
            f"No policy grants '{action.value}' action for roles [{role_list}]. "
            f"Default deny applied."
        ),
        policy_name=POLICY_DEFAULT_DENY,
        **base,
    )


# ============================================================================
# 5. Internal Policy Checks
# ============================================================================

def _resolve_asset(asset: Union[BIAsset, str]) -> BIAsset:
    """
    Resolve an asset argument to a BIAsset instance.

    If the input is already a BIAsset, return it directly.
    If it's a URN string, look it up in the static governance registry.

    Note: For async resolution (including dynamic/tenant assets),
    the enforcement layer should use get_asset_async() before calling
    evaluate_policy() with the resolved BIAsset object.

    Args:
        asset: BIAsset instance or URN string.

    Returns:
        Resolved BIAsset.

    Raises:
        ValueError: If string is not a valid URN or not in registry.
        TypeError: If asset is neither BIAsset nor str.
    """
    if isinstance(asset, BIAsset):
        return asset

    if isinstance(asset, str):
        from core.governance.registry import get_asset as registry_get
        try:
            return registry_get(asset)
        except KeyError:
            raise ValueError(
                f"URN '{asset}' not found in governance registry. "
                f"Cannot evaluate policy for unregistered assets."
            )

    raise TypeError(
        f"asset must be BIAsset or URN string, got {type(asset).__name__}"
    )


def _check_tenant_isolation(
    subject: PolicySubject,
    asset: BIAsset,
) -> bool:
    """
    Check tenant isolation constraint.

    Rules:
    - If asset.tenant_id is None → system-wide asset → accessible to all tenants.
    - If asset.tenant_id matches subject.tenant_id → same tenant → OK.
    - Otherwise → tenant mismatch → DENY.

    Returns:
        True if tenant check passes, False if it fails.
    """
    if asset.is_system_wide:
        return True
    return subject.tenant_id == asset.tenant_id


def _check_owner_bypass(
    subject: PolicySubject,
    action: BIAction,
    asset: BIAsset,
) -> Optional[dict]:
    """
    Check owner bypass rule (S7-4, Step 3).

    🔒 S7-4-C2 (CTO Mandate, Frozen):
        Owner bypass conditions (ALL must be true):
        1. asset.owner_id == subject.user_id
        2. asset.tenant_id == subject.tenant_id (cannot bypass tenant isolation)
        3. asset.is_system_wide == False (not applicable to system assets)

        Owner bypass grants: VIEW, INTERACT, EXPORT, MANAGE.
        (MANAGE only when all 3 conditions are met.)

    Args:
        subject: The policy subject.
        action: The BIAction being attempted.
        asset: The target BIAsset.

    Returns:
        Dict with PolicyResult fields if owner bypass applies, None otherwise.
    """
    # Owner bypass does not apply to system-wide assets
    if asset.is_system_wide:
        return None

    # Must have an owner
    if not asset.has_owner:
        return None

    # Owner must match
    if not asset.is_owned_by(subject.user_id):
        return None

    # Tenant must match (redundant with step 1, but defense-in-depth)
    if asset.tenant_id != subject.tenant_id:
        return None

    return {
        "allowed": True,
        "reason": (
            f"Asset owner '{subject.user_id}' granted '{action.value}' "
            f"on owned tenant asset"
        ),
        "policy_name": POLICY_OWNER_BYPASS,
    }


def _check_acl(
    subject: PolicySubject,
    action: BIAction,
    asset: BIAsset,
) -> Optional[dict]:
    """
    Check ACL-based access grant (S7-4, Step 4).

    🔒 S7-4-C3′ (CTO Mandate, Frozen — Semantic B):
        ACL is an INDEPENDENT authorization channel.
        - Grants: VIEW, INTERACT, EXPORT (hard ceiling).
        - NEVER grants: MANAGE.
        - Does NOT depend on Role-Action Matrix.
        - ACL is a sharing mechanism, not an authorization escalation tool.

    Args:
        subject: The policy subject.
        action: The BIAction being attempted.
        asset: The target BIAsset.

    Returns:
        Dict with PolicyResult fields if ACL grants access, None otherwise.
    """
    # ACL cannot grant MANAGE (hard ceiling)
    if action not in ACL_MAX_ACTIONS:
        return None

    # Asset must have ACL entries
    if not asset.is_shared:
        return None

    # Check if subject matches any ACL entry
    if not asset.check_acl(subject.user_id, subject.roles):
        return None

    return {
        "allowed": True,
        "reason": (
            f"ACL grants '{action.value}' on shared asset "
            f"(independent authorization channel, ceiling: EXPORT)"
        ),
        "policy_name": POLICY_ACL_GRANT,
    }


def _check_role_matrix(
    subject: PolicySubject,
    action: BIAction,
) -> Optional[str]:
    """
    Check the baseline role-action matrix for a matching grant.

    Iterates through the subject's roles and checks if ANY role
    grants the requested action in the DEFAULT_BI_PERMISSIONS matrix.

    🔒 Constraint S7-1-B: This checks the Global Default Baseline only.

    Args:
        subject: The policy subject with roles.
        action: The BIAction to check.

    Returns:
        The name of the first role that grants the action, or None.
    """
    for role_name in sorted(subject.roles):
        allowed_actions = get_allowed_actions(role_name)
        if action in allowed_actions:
            return role_name
    return None
