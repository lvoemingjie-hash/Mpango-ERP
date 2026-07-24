"""DC-12R1-S1-R5A runtime permission registry parity contracts."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from core.permission_registry import (
    ADMIN_MANAGEMENT_PERMISSION_CODES,
    ADMIN_MANAGEMENT_PERMISSIONS,
    ADMIN_PERMISSION_CODES,
    RETAILER_OPERATOR_PERMISSION_CODES,
    RETAILER_OPERATOR_PERMISSIONS,
)


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_036 = BACKEND_DIR / "alembic" / "versions" / "036_retailer_mvp_identity.py"


def _migration_036():
    spec = importlib.util.spec_from_file_location("dc12r1_s1_migration_036", MIGRATION_036)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_036_does_not_import_runtime_permission_registry():
    source = MIGRATION_036.read_text(encoding="utf-8")
    assert "permission_registry" not in source
    assert "from core." not in source


def test_retailer_operator_registry_matches_self_contained_migration_constants():
    migration = _migration_036()
    assert tuple(migration.RETAILER_OPERATOR_PERMISSIONS) == RETAILER_OPERATOR_PERMISSIONS
    assert RETAILER_OPERATOR_PERMISSION_CODES == {
        "client:catalog:read",
        "client:orders:read",
        "client:orders:create",
        "client:payments:read",
        "client:payments:create",
        "client:finance:read",
    }
    assert all(code.startswith("client:") for code in RETAILER_OPERATOR_PERMISSION_CODES)


def test_admin_management_registry_matches_self_contained_migration_constants():
    migration = _migration_036()
    assert tuple(migration.ADMIN_EXTRA_PERMISSIONS) == ADMIN_MANAGEMENT_PERMISSIONS
    assert ADMIN_MANAGEMENT_PERMISSION_CODES == {
        "invitations:revoke",
        "retailers:reissue_credential",
    }


def test_admin_and_retailer_operator_registries_are_disjoint():
    assert not (ADMIN_PERMISSION_CODES & RETAILER_OPERATOR_PERMISSION_CODES)
    assert not {code for code in ADMIN_PERMISSION_CODES if code.startswith("client:")}
