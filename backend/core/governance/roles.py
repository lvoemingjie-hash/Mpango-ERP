"""
S7-1: BI Role-Action Permission Matrix — The Default Baseline.

Philosophy: "The law must be written before it can be enforced."

This module defines the Global Default Baseline permission matrix that maps
(Role, BIAction) → Allow/Deny. It answers: "What can each role DO in the
BI layer, by default?"

🔒 Constraint S7-1-B (CTO Mandate, Frozen):
    This matrix is the GLOBAL DEFAULT BASELINE.
    It does NOT express any Asset-Specific or Override Policy.
    Future phases (P7-x) may introduce per-asset overrides, but this
    baseline remains the fallback for any (role, action) pair not
    covered by a more specific policy.

Design Decisions:
- Roles are strings (matching the existing `roles.name` column in tenant schema).
- The matrix is a dict-of-frozensets for O(1) lookup.
- BIAction hierarchy: VIEW < INTERACT < EXPORT < MANAGE.
- "admin" is NOT encoded in this matrix — admin bypass is handled by the
  policy engine's evaluation order (Step 2), not by the matrix.

Existing RBAC Roles (from rbac_matrix.md / create_wholesaler.py):
    admin, sales, warehouse, finance

Additional BI Roles (introduced by S7-1):
    viewer — read-only dashboard consumer (e.g., external stakeholder)

Boot Contract Compliance:
- New file in core/governance/ (no modification to frozen core/ files)
- No database changes
- No FastAPI imports
"""
from __future__ import annotations

from core.governance.models import BIAction


# ============================================================================
# 1. The Default Baseline Matrix
# ============================================================================

# Maps role_name → frozenset of allowed BIActions.
# If a role is not in this dict, it has NO BI permissions (default deny).
# "admin" is intentionally absent — admin bypass is in the policy engine.

DEFAULT_BI_PERMISSIONS: dict[str, frozenset[BIAction]] = {
    "finance": frozenset({
        BIAction.VIEW,
        BIAction.INTERACT,
        BIAction.EXPORT,
    }),
    "sales": frozenset({
        BIAction.VIEW,
        BIAction.INTERACT,
    }),
    "warehouse": frozenset({
        BIAction.VIEW,
    }),
    "viewer": frozenset({
        BIAction.VIEW,
    }),
}
"""
🔒 Constraint S7-1-B:
    This is the Global Default Baseline matrix.
    It does NOT represent Asset-Specific permissions.

    Future examples of Asset-Specific overrides (NOT implemented here):
    - finance can EXPORT finance reports but NOT operations reports
    - sales can only VIEW dashboards in the sales domain
    - tenant-custom dashboards have per-tenant permission overrides

    These overrides will be layered ON TOP of this baseline in P7-x.

Default Matrix:
    ┌───────────┬──────┬──────────┬────────┬────────┐
    │ Role      │ VIEW │ INTERACT │ EXPORT │ MANAGE │
    ├───────────┼──────┼──────────┼────────┼────────┤
    │ admin     │  ✅  │    ✅    │   ✅   │   ✅   │  ← handled by engine bypass
    │ finance   │  ✅  │    ✅    │   ✅   │   ❌   │
    │ sales     │  ✅  │    ✅    │   ❌   │   ❌   │
    │ warehouse │  ✅  │    ❌    │   ❌   │   ❌   │
    │ viewer    │  ✅  │    ❌    │   ❌   │   ❌   │
    └───────────┴──────┴──────────┴────────┴────────┘
"""


# ============================================================================
# 2. Lookup Helpers
# ============================================================================

ADMIN_ROLE_NAME = "admin"
"""The role name that triggers admin bypass in the policy engine.
Admin is NOT in the matrix — it is handled by evaluation Step 2."""


def get_allowed_actions(role_name: str) -> frozenset[BIAction]:
    """
    Get the set of allowed BIActions for a given role.

    Args:
        role_name: The role name (e.g., "finance", "sales").

    Returns:
        frozenset of allowed BIActions. Empty frozenset if role is unknown.
    """
    return DEFAULT_BI_PERMISSIONS.get(role_name, frozenset())


def is_action_allowed_for_role(role_name: str, action: BIAction) -> bool:
    """
    Check if a specific action is allowed for a role in the baseline matrix.

    This does NOT check admin bypass — that is the policy engine's job.

    Args:
        role_name: The role name.
        action: The BIAction to check.

    Returns:
        True if the action is in the role's allowed set.
    """
    return action in get_allowed_actions(role_name)


def list_roles_with_action(action: BIAction) -> list[str]:
    """
    List all roles that have a given action in the baseline matrix.

    Args:
        action: The BIAction to search for.

    Returns:
        List of role names that include this action.
    """
    return [
        role_name
        for role_name, actions in DEFAULT_BI_PERMISSIONS.items()
        if action in actions
    ]
