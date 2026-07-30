"""
U1 — Tenant Bootstrap Permission Completeness.

Validates that every permission enforced by RequirePermission in the API
is present in the canonical runtime permission registry consumed by bootstrap.

This is a static analysis test — no database or server required.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.permission_registry import (
    ADMIN_PERMISSION_CODES,
    ADMIN_PERMISSIONS,
    RETAILER_OPERATOR_PERMISSION_CODES,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_require_permission_calls(api_dir: Path) -> set[str]:
    """Walk all .py files under api_dir and extract every RequirePermission("...")
    string literal."""
    found: set[str] = set()
    for py_file in api_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # Match RequirePermission("...") or Depends(RequirePermission("..."))
            if isinstance(func, ast.Name) and func.id == "RequirePermission":
                if node.args and isinstance(node.args[0], ast.Constant):
                    found.add(node.args[0].value)
            elif isinstance(func, ast.Attribute) and func.attr == "RequirePermission":
                if node.args and isinstance(node.args[0], ast.Constant):
                    found.add(node.args[0].value)
    return found


def _script_source(script_name: str) -> str:
    return (SCRIPTS_DIR / script_name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parents[1]
API_DIR = BACKEND_DIR / "api"
SCRIPTS_DIR = BACKEND_DIR / "scripts"


@pytest.fixture(scope="module")
def api_permissions() -> set[str]:
    """All permissions enforced by RequirePermission in the API layer."""
    perms = _extract_require_permission_calls(API_DIR)
    assert perms, "No RequirePermission calls found — is api_dir correct?"
    return perms


@pytest.fixture(scope="module")
def canonical_admin_permissions() -> set[str]:
    return set(ADMIN_PERMISSION_CODES)


@pytest.fixture(scope="module")
def canonical_permission_specs() -> tuple[tuple[str, str], ...]:
    return ADMIN_PERMISSIONS


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOnboardTenantPermissionCompleteness:
    """The canonical admin registry must cover every API-enforced permission."""

    def test_all_api_perms_in_onboard(
        self, api_permissions: set[str], canonical_admin_permissions: set[str]
    ):
        # DC-12R1-S3-S1: client:* permissions belong to the disjoint
        # retailer_operator registry (admin and retailer sets are mutually
        # exclusive by design), so they are a valid route-permission namespace
        # even though they are absent from the admin registry.
        all_canonical = canonical_admin_permissions | set(RETAILER_OPERATOR_PERMISSION_CODES)
        missing = api_permissions - all_canonical
        assert not missing, (
            f"canonical registries are missing {len(missing)} permissions "
            f"required by API endpoints: {sorted(missing)}"
        )

    def test_onboard_has_no_extra_unknown_perms(
        self, api_permissions: set[str], canonical_admin_permissions: set[str]
    ):
        """Permissions in admin registry that are NOT in the API are either legacy
        aliases, bootstrap-only permissions, or valid future-use permissions.

        U1-R2 CTO directive: orders:confirm/ship/cancel and role CRUD
        permissions are valid bootstrap permissions."
        """
        extra = canonical_admin_permissions - api_permissions
        # inventory:write is a known legacy alias kept for backward compat
        # orders:confirm/ship/cancel are bootstrap-only (used in seed/validation logic)
        # roles:create/update/delete are bootstrap-only (admin seed, not yet in API decorators)
        # skus:import is a U3 import-contract permission; endpoints land in a later slice.
        known_valid_extras = {
            "inventory:write",       # legacy alias
            "orders:confirm",        # bootstrap-only
            "orders:ship",           # bootstrap-only
            "orders:cancel",         # bootstrap-only
            "roles:create",          # bootstrap-only (seed creates admin role)
            "roles:update",          # bootstrap-only
            "roles:delete",          # bootstrap-only
            "skus:import",           # future-use import contract
            # U4-A: Data Intake permissions seeded for admin role.
            # U4-C uses read/create for workspace routes; the rest remain seeded
            # ahead of later U4 slices.
            "intake:read",
            "intake:create",
            "intake:update",
            "intake:approve",
            "intake:export",
            "intake:import_to_erp",
            # DC-12R1-S1 admin-only retailer credential controls.
            "invitations:revoke",
            "retailers:reissue_credential",
        }
        unexpected = extra - known_valid_extras
        assert not unexpected, (
            f"Unexpected canonical admin extras not enforced by any API endpoint: "
            f"{sorted(unexpected)}"
        )
        assert {"invitations:revoke", "retailers:reissue_credential"} <= canonical_admin_permissions


class TestCreateWholesalerPermissionCompleteness:
    """Bootstrap scripts must consume the canonical admin registry."""

    @pytest.mark.parametrize(
        "script_name",
        ("onboard_tenant.py", "create_wholesaler.py", "seed_test_tenant.py"),
    )
    def test_admin_bootstrap_scripts_use_canonical_registry(self, script_name: str):
        source = _script_source(script_name)
        assert "from core.permission_registry import" in source
        assert "ADMIN_PERMISSIONS" in source


class TestSeedTestTenantPermissionCompleteness:
    """The retailer operator registry must stay in the approved client namespace."""

    def test_retailer_operator_has_exact_six_client_permissions(self):
        assert RETAILER_OPERATOR_PERMISSION_CODES == {
            "client:catalog:read",
            "client:orders:read",
            "client:orders:create",
            "client:payments:read",
            "client:payments:create",
            "client:finance:read",
        }
        assert all(code.startswith("client:") for code in RETAILER_OPERATOR_PERMISSION_CODES)


class TestScriptPermissionConsistency:
    """The registry protects admin from generic client:* grant-all behavior."""

    def test_admin_registry_has_no_client_permissions(self):
        assert not {code for code in ADMIN_PERMISSION_CODES if code.startswith("client:")}

    def test_canonical_permission_specs_are_unique(self, canonical_permission_specs):
        codes = [code for code, _description in canonical_permission_specs]
        assert len(codes) == len(set(codes))

    def test_bootstrap_tenant_schema_uses_registry_for_s1_rbac(self):
        source = _script_source("bootstrap_tenant_schema.py")
        assert "RETAILER_OPERATOR_PERMISSIONS" in source
        assert "ADMIN_MANAGEMENT_PERMISSIONS" in source
