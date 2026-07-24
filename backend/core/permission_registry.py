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
    ("retailers:read", "Read retailers"),
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
    ("client:payments:create", "Retailer: pay own orders"),
    ("client:finance:read", "Retailer: read own outstanding balance"),
)

ADMIN_PERMISSION_CODES: Final[frozenset[str]] = frozenset(code for code, _ in ADMIN_PERMISSIONS)
ADMIN_MANAGEMENT_PERMISSION_CODES: Final[frozenset[str]] = frozenset(
    code for code, _ in ADMIN_MANAGEMENT_PERMISSIONS
)
RETAILER_OPERATOR_PERMISSION_CODES: Final[frozenset[str]] = frozenset(
    code for code, _ in RETAILER_OPERATOR_PERMISSIONS
)


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
