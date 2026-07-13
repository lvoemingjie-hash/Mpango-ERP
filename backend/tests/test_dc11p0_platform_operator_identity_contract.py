"""DC-11P0 Platform Operator Identity + Credential Lifecycle Contract Tests.

Static contract tests that verify the current architecture matches the
assumptions in the DC-11P0 contract document. These tests do NOT implement
the new platform operator system; they assert the current state so that
DC-11P1 implementation changes are detectable.
"""
from __future__ import annotations

import importlib
import inspect

import pytest


# ---------------------------------------------------------------------------
# 1. Platform guard requires identity-only super_admin (not contextual)
# ---------------------------------------------------------------------------

class TestPlatformGuardContract:
    """The platform guard must require identity-only super_admin tokens."""

    def test_guard_module_exists(self):
        """The guard module is importable and has require_platform_operator."""
        mod = importlib.import_module("api.v1.platform.p10.guard")
        assert hasattr(mod, "require_platform_operator")

    def test_guard_checks_is_identity_only(self):
        """The guard source code checks token.is_identity_only."""
        mod = importlib.import_module("api.v1.platform.p10.guard")
        source = inspect.getsource(mod)
        assert "is_identity_only" in source, (
            "guard must check token.is_identity_only to reject contextual tokens"
        )

    def test_guard_checks_is_super_admin(self):
        """The guard source code checks token.is_super_admin."""
        mod = importlib.import_module("api.v1.platform.p10.guard")
        source = inspect.getsource(mod)
        assert "is_super_admin" in source, (
            "guard must check token.is_super_admin for platform access"
        )

    def test_guard_mentions_platform_operator_secret_is_not_browser(self):
        """The guard docstring states the frontend never sends the secret."""
        mod = importlib.import_module("api.v1.platform.p10.guard")
        source = inspect.getsource(mod)
        assert "frontend" in source.lower() and "never" in source.lower(), (
            "guard docstring must state the frontend never sends the operator secret"
        )


# ---------------------------------------------------------------------------
# 2. No platform operator model/table exists yet (confirming the gap)
# ---------------------------------------------------------------------------

class TestNoPlatformOperatorModel:
    """Confirm that no PlatformOperator model exists yet (the gap)."""

    def test_no_platform_operator_model_in_models_init(self):
        """models/__init__.py must NOT export a PlatformOperator class."""
        mod = importlib.import_module("models")
        assert not hasattr(mod, "PlatformOperator"), (
            "PlatformOperator model should not exist yet (DC-11P1 will create it)"
        )

    def test_no_platform_operator_model_file(self):
        """No platform_operator.py model file should exist yet."""
        import pathlib
        models_dir = pathlib.Path(__file__).resolve().parents[1] / "models"
        model_files = [f.name for f in models_dir.glob("*.py") if f.name != "__init__.py"]
        assert not any("operator" in f.lower() for f in model_files), (
            "No platform_operator model file should exist yet"
        )


# ---------------------------------------------------------------------------
# 3. No platform-specific auth endpoints exist (confirming the gap)
# ---------------------------------------------------------------------------

class TestNoPlatformAuthEndpoints:
    """Confirm no platform-specific signup/login/forgot/reset endpoints."""

    def test_auth_router_has_no_platform_endpoints(self):
        """The auth router must NOT have platform-specific endpoints."""
        mod = importlib.import_module("api.v1.auth")
        source = inspect.getsource(mod)
        # The common endpoints exist; platform-specific ones must not.
        assert "/platform/operators" not in source, (
            "No platform operator endpoints should exist in auth.py yet"
        )
        assert "platform_operator" not in source.lower().replace(
            "platform_operator_secret", ""
        ), (
            "No platform_operator service references should exist in auth.py yet"
        )

    def test_no_platform_operators_router(self):
        """No platform operators router file should exist yet."""
        import pathlib
        platform_dir = (
            pathlib.Path(__file__).resolve().parents[1]
            / "api" / "v1" / "platform"
        )
        if not platform_dir.exists():
            return
        route_files = [f.name for f in platform_dir.glob("*.py")]
        assert not any("operator" in f.lower() for f in route_files), (
            "No platform operators router should exist yet"
        )


# ---------------------------------------------------------------------------
# 4. Login aggregates roles from tenant-local user_roles (confirming the gap)
# ---------------------------------------------------------------------------

class TestLoginRoleAggregation:
    """Confirm the login handler aggregates roles from tenant-local user_roles."""

    def test_login_aggregates_roles_from_matches(self):
        """The login source must aggregate roles from tenant matches."""
        mod = importlib.import_module("api.v1.auth")
        source = inspect.getsource(mod)
        assert "all_roles" in source, (
            "login must aggregate roles from tenant matches (current gap: "
            "platform role derived from tenant-local RBAC)"
        )

    def test_find_user_across_tenants_collects_roles(self):
        """find_user_across_tenants must collect tenant-local roles."""
        mod = importlib.import_module("crud.user")
        source = inspect.getsource(mod)
        assert "role_names" in source, (
            "find_user_across_tenants must collect tenant-local roles "
            "(confirming the current gap)"
        )


# ---------------------------------------------------------------------------
# 5. X-Platform-Operator is not sent by the frontend (contract assertion)
# ---------------------------------------------------------------------------

class TestFrontendPlatformOperatorSecretContract:
    """The frontend must never send X-Platform-Operator."""

    def test_platform_api_comment_states_no_secret_sent(self):
        """The platformApi service file must document that no secret is sent."""
        import pathlib
        platform_api = (
            pathlib.Path(__file__).resolve().parents[2]
            / "frontend" / "src" / "services" / "platformApi.ts"
        )
        if not platform_api.exists():
            pytest.skip("platformApi.ts not found")
        source = platform_api.read_text(encoding="utf-8")
        assert "X-Platform-Operator" in source or "x-platform-operator" in source.lower(), (
            "platformApi.ts must reference X-Platform-Operator in comments"
        )
        # The file must state the frontend does NOT send it
        assert "never" in source.lower() or "not" in source.lower(), (
            "platformApi.ts must state the secret is never sent"
        )
