"""DC-12A-R3 static source guard for orchestration link construction.

This is a static source guard. The actual orchestration runtime proof remains
the U6L email-verified onboarding orchestration suite.
"""
from __future__ import annotations

import pytest


class TestOrchestrationLinkRegression:
    """Static source guard for credential-link builder call sites."""

    def test_build_owner_setup_link_uses_local_settings(self):
        """Static source guard: complete_email_verified_onboarding
        must pass its local 'settings' parameter to build_owner_setup_link,
        not 'self.settings' (which would be a NameError)."""
        import inspect
        from services.onboarding_service import complete_email_verified_onboarding
        source = inspect.getsource(complete_email_verified_onboarding)
        assert "build_owner_setup_link(issued.raw_token, settings)" in source, (
            "complete_email_verified_onboarding must pass function-local 'settings' "
            "to build_owner_setup_link, not 'self.settings'"
        )
        assert "self.settings" not in source, (
            "complete_email_verified_onboarding must NOT reference self.settings"
        )

    def test_build_verification_link_uses_local_settings(self):
        """Static source guard: create_signup_registration must pass
        its local 'settings' parameter to build_verification_link."""
        import inspect
        from services.onboarding_service import create_signup_registration
        source = inspect.getsource(create_signup_registration)
        assert "build_verification_link(raw_token, settings)" in source, (
            "create_signup_registration must pass function-local 'settings' "
            "to build_verification_link"
        )

    def test_link_builders_accept_settings_kwarg(self):
        """Static source guard: all 3 link builders accept a settings keyword argument."""
        from services.onboarding_service import (
            build_verification_link,
            build_owner_setup_link,
            build_password_reset_link,
        )
        class _S:
            PUBLIC_FRONTEND_URL = "https://test.example.com"
            SECRET_KEY = "a" * 32
            MPANGO_ENV = "test"

        s = _S()
        for builder in (build_verification_link, build_owner_setup_link, build_password_reset_link):
            link = builder("tok", settings=s)
            assert link.startswith("https://test.example.com/")
            assert "#" in link  # fragment present
