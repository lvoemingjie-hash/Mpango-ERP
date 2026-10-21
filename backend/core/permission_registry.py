"""Canonical runtime permission registry for tenant bootstrap paths."""

from __future__ import annotations

from typing import Final, TypeAlias

PermissionSpec: TypeAlias = tuple[str, str]

ADMIN_ROLE: Final = "admin"
RETAILER_OPERATOR_ROLE: Final = "retailer_operator"

ADMIN_MANAGEMENT_PERMISSIONS: Final[tuple[PermissionSpec, ...]] = (
    ("invitations:revoke", "Revoke an outstanding retailer invitation"),
    ("retailers:reissue_credential", "Reissue a retailer credential setup token"),
)

ADMIN_PERMISSIONS: Final[tuple[PermissionSpec, ...]] = (
    ("users:read", "Read users"),
    ("users:create", "Create users"),
    ("users:update", "Update users"),
    ("users:deactivate", "Deactivate users"),
    ("wholesalers:read", "Read wholesalers"),
    ("wholesalers:write", "Create/update/delete wholesalers"),
    ("roles:read", "Read roles"),
    ("roles:create", "Create roles"),
    ("roles:update", "Update roles"),
    ("roles:delete", "Delete roles"),
    ("roles:assign", "Assign roles to users"),
    ("orders:read", "Read orders"),
    ("orders:create", "Create orders"),
    ("orders:update", "Update orders"),
    ("orders:confirm", "Confirm orders"),
    ("orders:ship", "Ship orders"),
    ("orders:cancel", "Cancel orders"),
    ("orders:return", "Return orders"),
    ("skus:read", "Read SKUs"),
    ("skus:create", "Create SKUs"),
    ("skus:update", "Update SKUs"),
    ("skus:import", "Import SKUs via preview/validate/apply contract"),
    ("intake:read", "Read data intake batches"),
    ("intake:create", "Create data intake batches"),
    ("intake:update", "Update data intake batches"),
    ("intake:approve", "Approve data intake batches for ERP import"),
    ("intake:export", "Export data intake batches"),
    ("intake:import_to_erp", "Import approved data intake into ERP"),
    ("inventory:read", "Read inventory"),
    ("inventory:write", "Write inventory (legacy alias)"),
    ("inventory:update", "Update inventory (adjustments)"),
    ("payments:read", "Read payments"),
    ("payments:create", "Create payments"),
    ("payments:confirm_declaration", "Confirm or reject a retailer payment declaration"),
    ("retailers:read", "Read retailers"),
    # DC-12R1-MVP-L1-J1-H2-A-R1: wholesaler-side post-hoc control for the
    # dual-entry join (deactivate a retailer relationship). Enforced by
    # POST /retailers/{id}/deactivate; granted to admin idempotently at
    # tenant bootstrap (see scripts/bootstrap_tenant_schema.py).
    ("retailers:deactivate", "Deactivate a retailer binding relationship"),
    *ADMIN_MANAGEMENT_PERMISSIONS,
    ("invitations:create", "Create invitations"),
    ("pricing:read", "Read pricing"),
    ("pricing:write", "Write pricing"),
    ("finance:read", "View invoices, receivables, financial summary"),
    ("dashboards:read", "View dashboard KPIs and charts"),
    ("reports:read", "Read reports"),
    ("reports:analyze", "Analyze reports"),
    ("exports:create", "Request data exports"),
    ("system:admin", "Full system administration (job queues, debug endpoints)"),
    ("metrics:admin", "Reset application metrics"),
)

RETAILER_OPERATOR_PERMISSIONS: Final[tuple[PermissionSpec, ...]] = (
    ("client:catalog:read", "Retailer: browse wholesaler catalog"),
    ("client:orders:read", "Retailer: read own orders"),
    ("client:orders:create", "Retailer: create own orders"),
    ("client:payments:read", "Retailer: read own payments"),
    ("client:payments:declare", "Retailer: submit payment declaration"),
    ("client:finance:read", "Retailer: read own outstanding balance"),
)

ADMIN_PERMISSION_CODES: Final[frozenset[str]] = frozenset(code for code, _ in ADMIN_PERMISSIONS)
ADMIN_MANAGEMENT_PERMISSION_CODES: Final[frozenset[str]] = frozenset(
    code for code, _ in ADMIN_MANAGEMENT_PERMISSIONS
)
RETAILER_OPERATOR_PERMISSION_CODES: Final[frozenset[str]] = frozenset(
    code for code, _ in RETAILER_OPERATOR_PERMISSIONS
)

# M1 templates reuse native Role/Permission rows, not a second RBAC engine.
# M2 adjustment request/read/approve capabilities are deliberately not active.
STAFF_DELEGABLE_PERMISSION_CODES: Final[frozenset[str]] = frozenset({
    'orders:read', 'orders:create', 'orders:confirm', 'orders:ship', 'orders:cancel', 'orders:return',
    'skus:read', 'inventory:read', 'retailers:read', 'pricing:read', 'pricing:write',
    'payments:read', 'payments:create', 'payments:confirm_declaration', 'finance:read', 'dashboards:read',
})
STAFF_DEFAULT_PERMISSION_CODES: Final = {
    'warehouse': frozenset({'skus:read', 'inventory:read', 'orders:read', 'orders:ship'}),
    'sales': frozenset({'skus:read', 'retailers:read', 'pricing:read', 'orders:read', 'orders:create'}),
    'finance': frozenset({'orders:read', 'payments:read', 'finance:read'}),
}


def validate_staff_permission_codes(codes: list[str]) -> frozenset[str]:
    """Exact capability strings only; no wildcards, aliases or role UUIDs."""
    if not isinstance(codes, list) or any(type(code) is not str for code in codes):
        raise ValueError('INVALID_STAFF_TEMPLATE')
    result = frozenset(codes)
    if len(result) != len(codes) or not result <= STAFF_DELEGABLE_PERMISSION_CODES:
        raise ValueError('INVALID_STAFF_TEMPLATE')
    return result


def assert_unique_permission_codes(permission_specs: tuple[PermissionSpec, ...]) -> None:
    """Fail closed if a registry consumer receives duplicate permission codes."""
    seen: set[str] = set()
    duplicates: set[str] = set()
    for code, _description in permission_specs:
        if code in seen:
            duplicates.add(code)
        seen.add(code)
    if duplicates:
        raise RuntimeError(f"Duplicate permission codes: {sorted(duplicates)}")


assert_unique_permission_codes(ADMIN_PERMISSIONS)
assert_unique_permission_codes(RETAILER_OPERATOR_PERMISSIONS)
if ADMIN_PERMISSION_CODES & RETAILER_OPERATOR_PERMISSION_CODES:
    raise RuntimeError("Admin and retailer_operator permission registries must be disjoint")
