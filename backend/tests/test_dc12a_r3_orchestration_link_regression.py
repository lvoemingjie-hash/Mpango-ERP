"""DC-12A-R3 Orchestration link regression test.

Proves that complete_email_verified_onboarding generates an absolute
owner setup link using the function-local settings object (not self.settings,
which would cause NameError in a module-level function).
"""
from __future__ import annotations

import pytest


class TestOrchestrationLinkRegression:

    def test_build_owner_setup_link_uses_local_settings(self):
        """The module-level function complete_email_verified_onboarding
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
        """The module-level function create_signup_registration must pass
        its local 'settings' parameter to build_verification_link."""
        import inspect
        from services.onboarding_service import create_signup_registration
        source = inspect.getsource(create_signup_registration)
        assert "build_verification_link(raw_token, settings)" in source, (
            "create_signup_registration must pass function-local 'settings' "
            "to build_verification_link"
        )

    def test_link_builders_accept_settings_kwarg(self):
        """All 3 link builders accept a settings keyword argument."""
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
