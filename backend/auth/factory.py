from __future__ import annotations

import os

from auth.strategy import AuthStrategy


def get_auth_strategy() -> AuthStrategy:
    """Select auth strategy strictly based on MPANGO_ENV.

    Allowed values:
    - production
    - test

    Any other value defaults to production.

    NOTE: This is the only place allowed to branch on environment.
    """

    env = os.getenv("MPANGO_ENV", "production").strip().lower()

    if env == "test":
        from auth.strategies.mock import MockAuthStrategy

        return MockAuthStrategy()

    from auth.strategies.jwt import JwtAuthStrategy

    return JwtAuthStrategy()
