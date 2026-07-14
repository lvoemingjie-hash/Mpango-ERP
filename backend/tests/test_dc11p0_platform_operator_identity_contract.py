"""DC-11P0-R2 Platform Operator Identity + Credential Lifecycle Contract Tests.

Static contract tests that verify the current architecture matches the
assumptions in the DC-11P0-R2 contract document. These tests do NOT implement
the new platform operator system; they assert the current state so that
DC-11P1 implementation changes are detectable.

R1 additions: alembic head check (033), no 034 migration yet, no token
tables exist yet.
R2 additions: no recovery credentials model, no auth_version in TokenPayload.
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

class TestPlatformOperatorModelExists:
    """Confirm PlatformOperator model exists (created by DC-11P1)."""

    def test_platform_operator_model_in_models_init(self):
        """models/__init__.py must export PlatformOperator."""
        mod = importlib.import_module("models")
        assert hasattr(mod, "PlatformOperator"), (
            "PlatformOperator model must exist (created by DC-11P1)"
        )

    def test_platform_operator_model_file_exists(self):
        """platform_operator.py model file must exist."""
        import pathlib
        models_dir = pathlib.Path(__file__).resolve().parents[1] / "models"
        model_files = [f.name for f in models_dir.glob("*.py") if f.name != "__init__.py"]
        assert any("platform_operator" in f.lower() for f in model_files), (
            "platform_operator.py model file must exist"
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


# ---------------------------------------------------------------------------
# R1 additions: migration numbering and token table gap verification
# ---------------------------------------------------------------------------

class TestMigrationAndTableState:
    """Verify 034 migration exists and platform operator models are registered."""

    def test_034_migration_exists(self):
        """034 migration file must exist (created by DC-11P1)."""
        import pathlib
        versions_dir = (
            pathlib.Path(__file__).resolve().parents[1]
            / "alembic" / "versions"
        )
        matches = list(versions_dir.glob("034_*.py"))
        assert len(matches) >= 1, (
            "034 migration must exist (created by DC-11P1)"
        )

    def test_platform_operator_setup_tokens_model_exists(self):
        """PlatformOperatorSetupToken model must exist (created by DC-11P1)."""
        mod = importlib.import_module("models")
        assert hasattr(mod, "PlatformOperatorSetupToken"), (
            "PlatformOperatorSetupToken model must exist"
        )

    def test_platform_operator_reset_tokens_model_exists(self):
        """PlatformOperatorResetToken model must exist (created by DC-11P1)."""
        mod = importlib.import_module("models")
        assert hasattr(mod, "PlatformOperatorResetToken"), (
            "PlatformOperatorResetToken model must exist"
        )

    def test_recovery_credentials_model_exists(self):
        """PlatformOperatorRecoveryCredential model must exist (created by DC-11P1)."""
        mod = importlib.import_module("models")
        assert hasattr(mod, "PlatformOperatorRecoveryCredential"), (
            "PlatformOperatorRecoveryCredential model must exist"
        )

    def test_token_payload_has_no_auth_version(self):
        """TokenPayload must NOT have platform_auth_version yet (DC-11P3 adds it)."""
        from core.security import TokenPayload
        fields = TokenPayload.model_fields
        assert "platform_auth_version" not in fields, (
            "platform_auth_version must not exist on TokenPayload yet"
        )
        assert "platform_role" not in fields, (
            "platform_role must not exist on TokenPayload yet"
        )
