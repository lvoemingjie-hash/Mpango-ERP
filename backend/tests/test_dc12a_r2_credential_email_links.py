"""DC-12A-R2 Credential email link tests.

Tests:
- Three link builders generate absolute URLs with configured origin.
- Token is in URL fragment, not query string.
- Production Settings validation rejects missing/invalid PUBLIC_FRONTEND_URL.
- Link builders fall back to relative fragment when no base URL set.
"""
from __future__ import annotations

import os
import pytest
from urllib.parse import urlparse, parse_qs


def _make_settings(public_frontend_url=None, env="test"):
    """Create a minimal settings-like object for link builders."""
    class _S:
        MPANGO_ENV = env
        SECRET_KEY = "a" * 32
        PUBLIC_FRONTEND_URL = public_frontend_url
    return _S()


class TestLinkBuilders:
    """Verify three link builders produce absolute fragment URLs."""

    def test_verification_link_absolute_with_fragment(self):
        from services.onboarding_service import build_verification_link
        settings = _make_settings(public_frontend_url="https://app.mpango.io")
        link = build_verification_link("raw-token-123", settings)
        parsed = urlparse(link)
        assert parsed.scheme == "https"
        assert parsed.netloc == "app.mpango.io"
        assert parsed.path == "/verify-email"
        assert "token=raw-token-123" in (parsed.fragment or "")
        # Token NOT in query string
        assert not parse_qs(parsed.query or "")

    def test_setup_link_absolute_with_fragment(self):
        from services.onboarding_service import build_owner_setup_link
        settings = _make_settings(public_frontend_url="https://app.mpango.io")
        link = build_owner_setup_link("raw-token-456", settings)
        parsed = urlparse(link)
        assert parsed.scheme == "https"
        assert parsed.netloc == "app.mpango.io"
        assert parsed.path == "/setup-credential"
        assert "setupToken=raw-token-456" in (parsed.fragment or "")
        assert not parse_qs(parsed.query or "")

    def test_reset_link_absolute_with_fragment(self):
        from services.onboarding_service import build_password_reset_link
        settings = _make_settings(public_frontend_url="https://app.mpango.io")
        link = build_password_reset_link("raw-token-789", settings)
        parsed = urlparse(link)
        assert parsed.scheme == "https"
        assert parsed.netloc == "app.mpango.io"
        assert parsed.path == "/reset-password"
        assert "resetToken=raw-token-789" in (parsed.fragment or "")
        assert not parse_qs(parsed.query or "")

    def test_links_fall_back_to_relative_when_no_base(self):
        from services.onboarding_service import (
            build_verification_link, build_owner_setup_link, build_password_reset_link,
        )
        settings = _make_settings(public_frontend_url=None)
        v = build_verification_link("t1", settings)
        s = build_owner_setup_link("t2", settings)
        r = build_password_reset_link("t3", settings)
        assert v.startswith("/verify-email#token=")
        assert s.startswith("/setup-credential#setupToken=")
        assert r.startswith("/reset-password#resetToken=")

    def test_links_use_configured_http_localhost_in_test(self):
        from services.onboarding_service import build_verification_link
        settings = _make_settings(
            public_frontend_url="http://localhost:5173", env="test"
        )
        link = build_verification_link("tok", settings)
        assert link.startswith("http://localhost:5173/verify-email#token=")


class TestSettingsValidation:
    """Verify PUBLIC_FRONTEND_URL validation in Settings."""

    def test_valid_https_accepted(self):
        from core.config import Settings
        s = Settings(
            MPANGO_ENV="test",
            SECRET_KEY="a" * 32,
            PUBLIC_FRONTEND_URL="https://app.mpango.io",
        )
        assert s.PUBLIC_FRONTEND_URL == "https://app.mpango.io"

    def test_trailing_slash_stripped(self):
        from core.config import Settings
        s = Settings(
            MPANGO_ENV="test",
            SECRET_KEY="a" * 32,
            PUBLIC_FRONTEND_URL="https://app.mpango.io/",
        )
        assert s.PUBLIC_FRONTEND_URL == "https://app.mpango.io"

    def test_none_allowed_in_test(self):
        from core.config import Settings
        s = Settings(
            MPANGO_ENV="test",
            SECRET_KEY="a" * 32,
        )
        assert s.PUBLIC_FRONTEND_URL is None

    def test_production_missing_rejected(self):
        from core.config import Settings
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Settings(
                MPANGO_ENV="production",
                SECRET_KEY="a" * 32,
                DATABASE_URL="postgresql://real@host/db",
                REDIS_URL="redis://real:6379/0",
            )

    def test_production_http_rejected(self):
        from core.config import Settings
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Settings(
                MPANGO_ENV="production",
                SECRET_KEY="a" * 32,
                DATABASE_URL="postgresql://real@host/db",
                REDIS_URL="redis://real:6379/0",
                PUBLIC_FRONTEND_URL="http://app.mpango.io",
            )

    def test_credentials_in_url_rejected(self):
        from core.config import Settings
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Settings(
                MPANGO_ENV="test",
                SECRET_KEY="a" * 32,
                PUBLIC_FRONTEND_URL="https://user:pass@app.mpango.io",  # pragma: allowlist secret
            )

    def test_query_in_url_rejected(self):
        from core.config import Settings
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Settings(
                MPANGO_ENV="test",
                SECRET_KEY="a" * 32,
                PUBLIC_FRONTEND_URL="https://app.mpango.io?foo=bar",
            )

    def test_fragment_in_url_rejected(self):
        from core.config import Settings
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Settings(
                MPANGO_ENV="test",
                SECRET_KEY="a" * 32,
                PUBLIC_FRONTEND_URL="https://app.mpango.io#frag",
            )

    def test_path_in_url_rejected(self):
        from core.config import Settings
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Settings(
                MPANGO_ENV="test",
                SECRET_KEY="a" * 32,
                PUBLIC_FRONTEND_URL="https://app.mpango.io/path",
            )
