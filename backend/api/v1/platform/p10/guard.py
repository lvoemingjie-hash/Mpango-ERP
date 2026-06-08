"""
Platform-only access boundary guard for P10 endpoints.

P11-B0: Extended to accept Bearer-authenticated super_admin users.
The frontend never receives or sends PLATFORM_OPERATOR_SECRET.
Browser-based super_admin access uses standard Bearer/JWT auth.

Access is allowed when ANY of these conditions is met:
  1. Valid platform operator secret: X-Platform-Operator matches
     PLATFORM_OPERATOR_SECRET (for server/operator contexts).
  2. Valid authenticated super_admin: request has auth context from
     the existing JWT middleware, and the token has super_admin role.
  3. Valid test override: X-Platform-Test-Override exactly matches
     PLATFORM_TEST_OVERRIDE_SECRET, only in MPANGO_ENV=test|testing.

Deny-by-default rules:

  All environments:
    - If no valid credential is presented, deny.
    - Auth context with non-super_admin role is NOT sufficient.
    - Auth context with super_admin role IS sufficient (P11-B0).

  Test (MPANGO_ENV=test or testing):
    - X-Platform-Test-Override accepted only if it exactly matches
      PLATFORM_TEST_OVERRIDE_SECRET.

This guard reuses the existing auth middleware and TokenPayload.
It does NOT rewrite auth/RBAC/session/tenancy -- it reads the
auth context that the middleware already attached to request.state.
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


# ── Auth context helper ──


def _get_super_admin_from_request(request: Request) -> bool:
    """
    Check if the request has a valid auth context with super_admin role.

    Returns True if:
      - Auth middleware attached an AuthContext to request.state
      - The token payload has 'super_admin' in roles

    Returns False if:
      - No auth context is attached (unauthenticated or middleware skipped)
      - Auth context exists but user is not super_admin

    This does NOT raise -- it returns False for any auth issue,
    allowing the guard to fall through to other credential checks.
    """
    try:
        from api.context.auth import get_auth_context
        auth_ctx = get_auth_context(request)
        return auth_ctx.token.is_super_admin
    except Exception:
        # No auth context or invalid -- not an error, just not super_admin
        return False


# ── Core authorization check ──


def _is_platform_operator(
    platform_operator: Optional[str],
    platform_test_override: Optional[str],
    is_super_admin: bool,
) -> bool:
    """
    Check whether the request carries valid platform credentials.

    All env vars are read fresh at call time -- no import-time capture.

    Returns True only if a valid credential is presented.
    """
    mpango_env = _get_env("MPANGO_ENV", "")
    operator_secret = _get_env("PLATFORM_OPERATOR_SECRET", "")
    test_secret = _get_env("PLATFORM_TEST_OVERRIDE_SECRET", "")

    # ── Authenticated super_admin via Bearer/JWT (P11-B0) ──
    if is_super_admin:
        return True

    # ── Test override: only in test|testing env, must match exact secret ──
    if platform_test_override:
        if _is_test_env(mpango_env) and test_secret and platform_test_override == test_secret:
            return True
        # If we get here, test override is invalid or env is wrong -> fall through

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

    Accepts any of:
      - Valid X-Platform-Operator secret (server/operator context)
      - Authenticated super_admin via Bearer/JWT (browser frontend)
      - Valid X-Platform-Test-Override (test harness, test env only)

    Raises HTTPException 401 if no credential at all.
    Raises HTTPException 403 if credential present but insufficient.
    """
    # Treat empty strings as absent
    op = x_platform_operator if x_platform_operator else None
    test = x_platform_test_override if x_platform_test_override else None

    # Check for Bearer-authenticated super_admin
    is_super_admin = _get_super_admin_from_request(request)

    if op is None and test is None and not is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "PLATFORM_ACCESS_REQUIRED",
                "message": "P10 endpoints require platform-operator credentials",
            },
        )

    if not _is_platform_operator(op, test, is_super_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PLATFORM_ACCESS_DENIED",
                "message": "Insufficient platform credentials for P10 access",
            },
        )
