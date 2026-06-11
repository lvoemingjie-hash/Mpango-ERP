"""
U1 — Tenant Bootstrap Permission Completeness.

Validates that every permission enforced by RequirePermission in the API
is present in the permissions_data / permission_codes of all bootstrap scripts.

This is a static analysis test — no database or server required.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

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


def _extract_permissions_from_script(script_path: Path) -> set[str]:
    """Extract the permission codes from permissions_data / permission_codes
    list literal in a bootstrap script."""
    text = script_path.read_text(encoding="utf-8")

    # Find tuples like ("some:permission", "description")
    codes: set[str] = set()
    for match in re.finditer(r'\(\s*"(?P<code>[a-z_:]+)"\s*,\s*"[^"]*"\s*\)', text):
        codes.add(match.group("code"))
    return codes


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
def onboard_permissions() -> set[str]:
    return _extract_permissions_from_script(SCRIPTS_DIR / "onboard_tenant.py")


@pytest.fixture(scope="module")
def create_wholesaler_permissions() -> set[str]:
    return _extract_permissions_from_script(SCRIPTS_DIR / "create_wholesaler.py")


@pytest.fixture(scope="module")
def seed_test_permissions() -> set[str]:
    return _extract_permissions_from_script(SCRIPTS_DIR / "seed_test_tenant.py")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOnboardTenantPermissionCompleteness:
    """onboard_tenant.py must cover every API-enforced permission."""

    def test_all_api_perms_in_onboard(
        self, api_permissions: set[str], onboard_permissions: set[str]
    ):
        missing = api_permissions - onboard_permissions
        assert not missing, (
            f"onboard_tenant.py is missing {len(missing)} permissions "
            f"required by API endpoints: {sorted(missing)}"
        )

    def test_onboard_has_no_extra_unknown_perms(
        self, api_permissions: set[str], onboard_permissions: set[str]
    ):
        """Permissions in onboard that are NOT in the API are either legacy
        aliases or unused. We warn but don't fail."""
        extra = onboard_permissions - api_permissions
        # inventory:write is a known legacy alias kept for backward compat
        known_legacy = {"inventory:write"}
        unexpected = extra - known_legacy
        assert not unexpected, (
            f"Unexpected permissions in onboard_tenant.py not enforced by "
            f"any API endpoint: {sorted(unexpected)}"
        )


class TestCreateWholesalerPermissionCompleteness:
    """create_wholesaler.py must also cover every API-enforced permission."""

    def test_all_api_perms_in_create_wholesaler(
        self, api_permissions: set[str], create_wholesaler_permissions: set[str]
    ):
        missing = api_permissions - create_wholesaler_permissions
        assert not missing, (
            f"create_wholesaler.py is missing {len(missing)} permissions "
            f"required by API endpoints: {sorted(missing)}"
        )


class TestSeedTestTenantPermissionCompleteness:
    """seed_test_tenant.py should also cover every API-enforced permission."""

    def test_all_api_perms_in_seed_test(
        self, api_permissions: set[str], seed_test_permissions: set[str]
    ):
        missing = api_permissions - seed_test_permissions
        assert not missing, (
            f"seed_test_tenant.py is missing {len(missing)} permissions "
            f"required by API endpoints: {sorted(missing)}"
        )


class TestScriptPermissionConsistency:
    """All three scripts must agree on the permission set."""

    def test_onboard_matches_create_wholesaler(
        self, onboard_permissions: set[str], create_wholesaler_permissions: set[str]
    ):
        assert onboard_permissions == create_wholesaler_permissions, (
            f"Permission mismatch between onboard_tenant.py and "
            f"create_wholesaler.py: "
            f"only in onboard: {sorted(onboard_permissions - create_wholesaler_permissions)}, "
            f"only in create_wholesaler: {sorted(create_wholesaler_permissions - onboard_permissions)}"
        )

    def test_onboard_matches_seed_test(
        self, onboard_permissions: set[str], seed_test_permissions: set[str]
    ):
        assert onboard_permissions == seed_test_permissions, (
            f"Permission mismatch between onboard_tenant.py and "
            f"seed_test_tenant.py"
        )
