"""U4-C internal-login-only intake workspace API contract tests."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")  # pragma: allowlist secret
os.environ.setdefault(
    "SECRET_KEY",
    hashlib.sha256(b"mpango-test-runner-key-not-for-production").hexdigest(),  # pragma: allowlist secret
)
os.environ.setdefault("REPORTING_USER_PASSWORD", "test")  # pragma: allowlist secret
os.environ["MPANGO_ENV"] = "test"

BACKEND_DIR = Path(__file__).resolve().parents[1]
INTAKE_API = BACKEND_DIR / "api" / "v1" / "intake.py"


def test_intake_workspace_routes_are_registered():
    from api.app import app

    route_paths = {getattr(route, "path", None) for route in app.routes}

    assert "/api/v1/intake/workspaces" in route_paths
    assert "/api/v1/intake/workspaces/{workspace_id}" in route_paths


def test_intake_routes_use_required_permissions():
    source = INTAKE_API.read_text(encoding="utf-8")

    assert source.count('RequirePermission("intake:create")') == 1
    assert source.count('RequirePermission("intake:read")') == 2


def test_intake_routes_require_tenant_db_session():
    source = INTAKE_API.read_text(encoding="utf-8")

    assert "get_tenant_db_session" in source
    assert "get_db_session" not in source


def test_intake_u4c_has_no_public_or_upload_or_sku_import_surface():
    source = INTAKE_API.read_text(encoding="utf-8")

    forbidden = [
        "intake_public",
        "UploadFile",
        "File(",
        "ImportService",
        "sku_import",
        "skus/import",
        "SKU(",
    ]
    for value in forbidden:
        assert value not in source, f"Forbidden U4-C API surface found: {value}"
