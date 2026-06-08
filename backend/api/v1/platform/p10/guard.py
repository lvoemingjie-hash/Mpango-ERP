"""
Platform-only access boundary guard for P10 endpoints.

P10-R2: Hardened guard — test override restricted to MPANGO_ENV=test|testing
only, requires PLATFORM_TEST_OVERRIDE_SECRET, env read at runtime (not import time).

Deny-by-default rules:

  Production (MPANGO_ENV=production):
    - Only X-Platform-Operator matching PLATFORM_OPERATOR_SECRET is accepted.
    - If PLATFORM_OPERATOR_SECRET is unset, deny by default.
    - X-Platform-Test-Override is NEVER accepted.

  Test (MPANGO_ENV=test or testing):
    - X-Platform-Test-Override accepted only if it exactly matches
      PLATFORM_TEST_OVERRIDE_SECRET.
    - If PLATFORM_TEST_OVERRIDE_SECRET is unset, deny by default.
    - X-Platform-Operator matching PLATFORM_OPERATOR_SECRET also accepted.

  All other environments (development, staging, unset, default):
    - X-Platform-Operator matching PLATFORM_OPERATOR_SECRET accepted.
    - X-Platform-Test-Override is NEVER accepted.
    - If PLATFORM_OPERATOR_SECRET is unset, deny by default.

This is a SKELETON guard for the P10 read-only API surface.
It does NOT rewrite auth/RBAC/session/tenancy — it adds a single
local dependency inside the P10 module.

When P11 platform auth is built, this guard will be replaced with
proper platform role context.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException, Request, status

# ── Env readers (fresh per-request, not captured at import time) ──


def _get_env(key: str, default: str = "") -> str:
    """Read an environment variable. Called inside the check for freshness."""
    return os.environ.get(key, default)


def _is_test_env(env: str) -> bool:
    """MPANGO_ENV must be exactly 'test' or 'testing' for test override."""
    return env in ("test", "testing")


def _is_production_env(env: str) -> bool:
    """MPANGO_ENV is 'production'."""
    return env == "production"


# ── Core authorization check ──


def _is_platform_operator(
    platform_operator: Optional[str],
    platform_test_override: Optional[str],
) -> bool:
    """
    Check whether the request carries a valid platform-operator marker.

    All env vars are read fresh at call time — no import-time capture.

    Returns True only if a valid credential is presented.
    """
    mpango_env = _get_env("MPANGO_ENV", "")
    operator_secret = _get_env("PLATFORM_OPERATOR_SECRET", "")
    test_secret = _get_env("PLATFORM_TEST_OVERRIDE_SECRET", "")

    # ── Test override: only in test|testing env, must match exact secret ──
    if platform_test_override:
        if _is_test_env(mpango_env) and test_secret and platform_test_override == test_secret:
            return True
        # If we get here, test override is invalid or env is wrong → fall through

    # ── Operator header: works in all envs if secret is configured ──
    if platform_operator and operator_secret:
        return platform_operator == operator_secret

    # ── Deny by default ──
    return False


def require_platform_operator(
    request: Request,
    x_platform_operator: Optional[str] = Header(
        None,
        alias="X-Platform-Operator",
        description="Platform operator shared secret",
    ),
    x_platform_test_override: Optional[str] = Header(
        None,
        alias="X-Platform-Test-Override",
        description="Test override (MPANGO_ENV=test|testing only)",
    ),
) -> None:
    """
    FastAPI dependency that enforces platform-only access.

    Raises HTTPException 401 if no marker at all (unauthenticated equivalent).
    Raises HTTPException 403 if marker present but invalid (insufficient credentials).
    """
    # Treat empty strings as absent
    op = x_platform_operator if x_platform_operator else None
    test = x_platform_test_override if x_platform_test_override else None

    if op is None and test is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "PLATFORM_ACCESS_REQUIRED",
                "message": "P10 endpoints require platform-operator credentials",
            },
        )

    if not _is_platform_operator(op, test):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PLATFORM_ACCESS_DENIED",
                "message": "Insufficient platform credentials for P10 access",
            },
        )
