"""S6-E RBAC permission registry drift gate."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.routing import APIRoute

from core.permission_registry import ADMIN_PERMISSION_CODES, ADMIN_PERMISSIONS
from tests.async_test_utils import run_coroutine


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
    "seed_test_tenant.py": SCRIPTS_DIR / "seed_test_tenant.py",
    "seed_demo_data.py": SCRIPTS_DIR / "seed_demo_data.py",
}

REQUIRED_DATA_INTAKE_PERMISSIONS = {
    "intake:create",
    "intake:read",
    "intake:update",
    "skus:import",
}

S6D_ALLOWED_DATA_INTAKE_PAGE_PERMISSIONS = REQUIRED_DATA_INTAKE_PERMISSIONS


class _FakeResult:
    def __init__(
        self,
        *,
        scalar_value: Any = None,
        fetchone_value: Any = None,
        fetchall_value: list[Any] | None = None,
    ) -> None:
        self._scalar_value = scalar_value
        self._fetchone_value = fetchone_value
        self._fetchall_value = list(fetchall_value or [])

    def scalar(self) -> Any:
        return self._scalar_value

    def fetchone(self) -> Any:
        return self._fetchone_value

    def fetchall(self) -> list[Any]:
        return list(self._fetchall_value)


class _PermissionCaptureDB:
    def __init__(self) -> None:
        self.permission_ids: dict[str, str] = {}
        self.role_ids: dict[str, str] = {}
        self.user_ids: dict[str, str] = {}

    @staticmethod
    def _sql(statement: Any) -> str:
        return " ".join(str(statement).split())

    @staticmethod
    def _new_id() -> str:
        return str(uuid.uuid4())

    def add(self, obj: Any) -> None:
        identifier = getattr(obj, "id", None) or uuid.uuid4()
        obj.id = identifier
        if hasattr(obj, "code"):
            self.permission_ids[str(obj.code)] = str(identifier)
        elif hasattr(obj, "name"):
            self.role_ids[str(obj.name)] = str(identifier)
        elif hasattr(obj, "email"):
            self.user_ids[str(obj.email)] = str(identifier)

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        params = params or {}
        sql = self._sql(statement)

        if "SELECT id FROM permissions WHERE code = :code" in sql or "SELECT * FROM permissions WHERE code = :code" in sql:
            code = str(params["code"])
            perm_id = self.permission_ids.get(code)
            if perm_id is None:
                return _FakeResult()
            return _FakeResult(scalar_value=perm_id, fetchone_value=(perm_id,))

        if "SELECT id FROM roles WHERE name = :name" in sql or "SELECT * FROM roles WHERE name = :name" in sql:
            role_name = str(params.get("name", "admin"))
            role_id = self.role_ids.get(role_name)
            if role_id is None:
                return _FakeResult()
            return _FakeResult(scalar_value=role_id, fetchone_value=(role_id,))

        if "SELECT id FROM users WHERE email = :email" in sql or "SELECT id FROM users WHERE email = :e" in sql:
            email = str(params.get("email") or params.get("e"))
            user_id = self.user_ids.get(email)
            if user_id is None:
                return _FakeResult()
            return _FakeResult(scalar_value=user_id, fetchone_value=(user_id,))

        if "SELECT 1 FROM role_permissions" in sql or "SELECT * FROM role_permissions" in sql:
            return _FakeResult()

        if "INSERT INTO roles (name, description)" in sql:
            role_name = str(params["n"])
            self.role_ids.setdefault(role_name, self._new_id())
            return _FakeResult()

        if "INSERT INTO users (email, password_hash, full_name, is_active)" in sql:
            email = str(params["e"])
            self.user_ids.setdefault(email, self._new_id())
            return _FakeResult()

        if "INSERT INTO permissions (code, description)" in sql:
            code = str(params.get("code") or params.get("c"))
            self.permission_ids.setdefault(code, self._new_id())
            return _FakeResult()

        if "SELECT id FROM roles WHERE name = 'admin'" in sql:
            role_id = self.role_ids.setdefault("admin", self._new_id())
            return _FakeResult(scalar_value=role_id, fetchone_value=(role_id,))

        if "SELECT id FROM permissions" in sql:
            return _FakeResult(fetchall_value=[(perm_id,) for perm_id in self.permission_ids.values()])

        if sql.startswith("SET LOCAL search_path TO") or sql.startswith("INSERT INTO user_roles") or sql.startswith(
            "INSERT INTO role_permissions"
        ):
            return _FakeResult()

        raise AssertionError(f"Unhandled SQL in permission capture DB: {sql}")

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def refresh(self, _obj: Any) -> None:
        return None

    def codes(self) -> set[str]:
        return set(self.permission_ids)


def _load_script_module(script_path: Path) -> Any:
    module_name = f"s6e_{script_path.stem}_{abs(hash(script_path))}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec and spec.loader, f"Unable to load provisioning script: {script_path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _run(awaitable: Any) -> Any:
    return run_coroutine(awaitable)


def _extract_onboard_permissions(script_path: Path) -> set[str]:
    module = _load_script_module(script_path)
    assert module.ADMIN_PERMISSIONS is ADMIN_PERMISSIONS

    class _DummyUser:
        def __init__(self, **kwargs: Any) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)
            self.id = uuid.uuid4()

    module.User = _DummyUser
    db = _PermissionCaptureDB()
    _run(module.setup_admin(db, "t_test", "admin@test.local", "password"))
    return db.codes()


def _extract_create_wholesaler_permissions(script_path: Path) -> set[str]:
    module = _load_script_module(script_path)
    assert module.ADMIN_PERMISSIONS is ADMIN_PERMISSIONS

    db = _PermissionCaptureDB()
    _run(module.create_permissions(db, "t_test"))
    return db.codes()


def _extract_seed_test_tenant_permissions(script_path: Path) -> set[str]:
    module = _load_script_module(script_path)
    captured: dict[str, Any] = {}

    async def _noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def _capture_seed_admin_rbac(*_args: Any, **kwargs: Any) -> None:
        captured["permission_codes"] = kwargs["permission_codes"]

    class _SessionManager:
        async def __aenter__(self) -> Any:
            return SimpleNamespace(commit=_noop)

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

    from core import config as core_config
    from database import session as database_session
    from models import wholesaler as wholesaler_model

    original_get_settings = core_config.get_settings
    original_async_session_local = database_session.AsyncSessionLocal
    original_derive_schema = wholesaler_model.Wholesaler.derive_schema_from_id

    try:
        core_config.get_settings = lambda: SimpleNamespace(
            DATABASE_URL="postgresql://pytest_gate:PytestGate_20260727!@127.0.0.1:56433/test_backend_v2_r1_source"
        )
        database_session.AsyncSessionLocal = lambda: _SessionManager()
        wholesaler_model.Wholesaler.derive_schema_from_id = staticmethod(lambda _value: "t_test")

        module._add_backend_to_path = lambda: None
        module._looks_like_production_db = lambda _url: False
        module._ensure_public_wholesaler = _noop
        module._ensure_tenant_tables = _noop
        module._seed_admin_rbac = _capture_seed_admin_rbac

        os.environ["MPANGO_ENV"] = "test"
        _run(module.seed(also_seed_t_dev=False, allow_production=False))
    finally:
        core_config.get_settings = original_get_settings
        database_session.AsyncSessionLocal = original_async_session_local
        wholesaler_model.Wholesaler.derive_schema_from_id = original_derive_schema

    assert captured.get("permission_codes") is ADMIN_PERMISSIONS
    return {code for code, _description in captured["permission_codes"]}


def _extract_seed_demo_permissions(script_path: Path) -> set[str]:
    module = _load_script_module(script_path)
    assert module.ADMIN_PERMISSIONS is ADMIN_PERMISSIONS
    assert module.PERMISSION_CODES is ADMIN_PERMISSIONS

    db = _PermissionCaptureDB()
    _run(module._seed_rbac(db, "t_test"))
    return db.codes()


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
    if script_path.name == "onboard_tenant.py":
        return _extract_onboard_permissions(script_path)
    if script_path.name == "create_wholesaler.py":
        return _extract_create_wholesaler_permissions(script_path)
    if script_path.name == "seed_test_tenant.py":
        return _extract_seed_test_tenant_permissions(script_path)
    if script_path.name == "seed_demo_data.py":
        return _extract_seed_demo_permissions(script_path)
    raise AssertionError(f"Unsupported provisioning permission script: {script_path}")


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


def test_provisioning_scripts_import_and_consume_canonical_registry_exactly():
    for script_name, script_path in PROVISIONING_PERMISSION_SCRIPTS.items():
        seed_permissions = extract_seed_permissions(script_path)
        missing = sorted(ADMIN_PERMISSION_CODES - seed_permissions)
        extra = sorted(seed_permissions - ADMIN_PERMISSION_CODES)
        assert seed_permissions == set(ADMIN_PERMISSION_CODES), (
            f"{script_name} drifted from canonical admin permissions; "
            f"missing={missing}, extra={extra}"
        )


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
