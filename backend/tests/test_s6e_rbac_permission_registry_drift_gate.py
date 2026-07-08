"""S6-E RBAC permission registry drift gate."""

from __future__ import annotations

import ast
import hashlib
import os
import re
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute


os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")  # pragma: allowlist secret
os.environ.setdefault(
    "SECRET_KEY",
    hashlib.sha256(b"s6e-rbac-permission-registry-drift-gate").hexdigest(),  # pragma: allowlist secret
)
os.environ["MPANGO_ENV"] = "test"
os.environ.setdefault(
    "REPORTING_DATABASE_URL",
    "postgresql://reporting_user:test@localhost:5432/mpango_erp",  # pragma: allowlist secret
)
os.environ.setdefault("REPORTING_USER_PASSWORD", "test")  # pragma: allowlist secret

try:
    from core.config import get_settings as _get_settings

    _get_settings.cache_clear()
except Exception:
    pass

from api.app import app  # noqa: E402


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
SCRIPTS_DIR = BACKEND_DIR / "scripts"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"

PROVISIONING_PERMISSION_SCRIPTS = {
    "onboard_tenant.py": SCRIPTS_DIR / "onboard_tenant.py",
    "create_wholesaler.py": SCRIPTS_DIR / "create_wholesaler.py",
    "seed_demo_data.py": SCRIPTS_DIR / "seed_demo_data.py",
    "seed_test_tenant.py": SCRIPTS_DIR / "seed_test_tenant.py",
}

REQUIRED_DATA_INTAKE_PERMISSIONS = {
    "intake:create",
    "intake:read",
    "intake:update",
    "skus:import",
}

S6D_ALLOWED_DATA_INTAKE_PAGE_PERMISSIONS = REQUIRED_DATA_INTAKE_PERMISSIONS


def _collect_all_dependencies(route: APIRoute) -> list[Any]:
    seen: set[int] = set()
    result: list[Any] = []

    def _walk(dependant: Any) -> None:
        for sub in getattr(dependant, "dependencies", []) or []:
            obj_id = id(sub)
            if obj_id in seen:
                continue
            seen.add(obj_id)
            if sub.call is not None:
                result.append(sub.call)
            _walk(sub)

    _walk(getattr(route, "dependant", None))
    return result


def _route_dependency_permissions(dep: Any) -> set[str]:
    permissions: set[str] = set()

    permission = getattr(dep, "permission", None)
    if isinstance(permission, str) and ":" in permission:
        permissions.add(permission)

    multi_permissions = getattr(dep, "permissions", None)
    if isinstance(multi_permissions, (set, list, tuple)):
        permissions.update(
            str(value)
            for value in multi_permissions
            if isinstance(value, str) and ":" in value
        )

    return permissions


def extract_api_route_permissions() -> set[str]:
    permissions: set[str] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/v1"):
            continue
        for dep in _collect_all_dependencies(route):
            permissions.update(_route_dependency_permissions(dep))
    assert permissions, "No API route permissions extracted from FastAPI dependency tree"
    return permissions


def extract_seed_permissions(script_path: Path) -> set[str]:
    tree = ast.parse(script_path.read_text(encoding="utf-8"))
    target_names = {"PERMISSION_CODES", "permissions_data", "permission_codes"}
    permissions: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id in target_names for target in node.targets):
            continue
        if not isinstance(node.value, ast.List):
            continue

        for element in node.value.elts:
            if not isinstance(element, ast.Tuple) or len(element.elts) < 2:
                continue
            code_node = element.elts[0]
            if isinstance(code_node, ast.Constant) and isinstance(code_node.value, str) and ":" in code_node.value:
                permissions.add(code_node.value)

    assert permissions, f"No seed permissions extracted from {script_path}"
    return permissions


def extract_frontend_permissions() -> set[str]:
    permission_pattern = re.compile(r"['\"]([a-z_]+:[a-z_]+)['\"]")
    permissions: set[str] = set()

    # G2-R2: Exclude test/spec files and __tests__ directories from the scan.
    # Permission codes are defined in production source only. Test files
    # contain mock fixtures and error-message literals (e.g. "denied:close")
    # that match the regex but are NOT permission tokens.
    _is_test_file = re.compile(r"\.(test|spec)\.(ts|tsx|js|jsx)$", re.IGNORECASE)

    # G2-R2: Known false-positive prefixes -- tokens matched by the regex
    # that are structurally like "<word>:<word>" but are never permission
    # codes in this codebase:
    #   - "node:*"  : Node.js built-in module specifiers (node:fs, node:path)
    #   - "denied:*": platform transition/error status descriptors
    #                 (denied:acknowledge, denied:close, denied:complete)
    _false_positive_prefixes = ("node:", "denied:")

    for root in (FRONTEND_SRC / "utils", FRONTEND_SRC / "pages"):
        for source_file in root.rglob("*.ts*"):
            # Skip test files and __tests__ directories entirely.
            if "__tests__" in source_file.parts or _is_test_file.search(source_file.name):
                continue
            for token in permission_pattern.findall(source_file.read_text(encoding="utf-8")):
                if any(token.startswith(prefix) for prefix in _false_positive_prefixes):
                    continue
                permissions.add(token)

    assert permissions, "No frontend permission constants or UI gates extracted"
    return permissions


def test_api_route_permissions_are_seeded_in_all_tenant_provisioning_paths():
    api_permissions = extract_api_route_permissions()
    tenant_api_permissions = {permission for permission in api_permissions if not permission.startswith("platform:")}

    for script_name, script_path in PROVISIONING_PERMISSION_SCRIPTS.items():
        seed_permissions = extract_seed_permissions(script_path)
        missing = tenant_api_permissions - seed_permissions
        assert not missing, f"{script_name} missing API route permissions: {sorted(missing)}"


def test_provisioning_paths_seed_required_data_intake_permissions():
    for script_name, script_path in PROVISIONING_PERMISSION_SCRIPTS.items():
        seed_permissions = extract_seed_permissions(script_path)
        missing = REQUIRED_DATA_INTAKE_PERMISSIONS - seed_permissions
        assert not missing, f"{script_name} missing Data Intake permissions: {sorted(missing)}"


def test_frontend_permission_references_are_seeded():
    frontend_permissions = extract_frontend_permissions()
    seeded_permissions = set().union(
        *(extract_seed_permissions(script_path) for script_path in PROVISIONING_PERMISSION_SCRIPTS.values())
    )

    missing = frontend_permissions - seeded_permissions
    assert not missing, f"Frontend references permissions missing from backend seeds: {sorted(missing)}"


def test_s6d_catalog_only_wording_added_no_new_data_intake_permission_semantics():
    source = (FRONTEND_SRC / "pages" / "skus" / "DataIntakePage.tsx").read_text(encoding="utf-8")
    data_intake_page_permissions = set(re.findall(r"['\"]([a-z_]+:[a-z_]+)['\"]", source))
    unexpected = data_intake_page_permissions - S6D_ALLOWED_DATA_INTAKE_PAGE_PERMISSIONS

    assert not unexpected, f"DataIntakePage introduced unexpected permission semantics: {sorted(unexpected)}"
