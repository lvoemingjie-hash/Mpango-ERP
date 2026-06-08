"""
Platform-only access boundary guard for P10 endpoints.

P10-R1-A: All P10 endpoints require an explicit platform-operator marker.
This guard enforces deny-by-default:

  - Production: requires X-Platform-Operator header with a valid shared secret.
  - Test/Local:  requires X-Platform-Operator header OR
                  X-Platform-Test-Override header (test harness only).

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

# ── Configuration ──

_PLATFORM_OPERATOR_SECRET = os.environ.get("PLATFORM_OPERATOR_SECRET", "")
_MPANGO_ENV = os.environ.get("MPANGO_ENV", "development")


def _is_platform_operator(
    platform_operator: Optional[str],
    platform_test_override: Optional[str],
) -> bool:
    """
    Check whether the request carries a valid platform-operator marker.

    Production:
      - X-Platform-Operator header must match PLATFORM_OPERATOR_SECRET env var.
      - If PLATFORM_OPERATOR_SECRET is not set, deny by default.
      - X-Platform-Test-Override is NEVER accepted.

    Non-production (development, test, staging):
      - X-Platform-Operator header must match PLATFORM_OPERATOR_SECRET if configured.
      - If PLATFORM_OPERATOR_SECRET is not configured, operator header is NOT sufficient.
      - X-Platform-Test-Override header is accepted for test harness use.

    Returns True if the request is authorized as platform-operator.
    """
    # Test override is only valid in non-production
    if _MPANGO_ENV != "production" and platform_test_override:
        return True

    # Platform operator requires the shared secret (both production and non-production)
    if platform_operator and _PLATFORM_OPERATOR_SECRET:
        return platform_operator == _PLATFORM_OPERATOR_SECRET

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
        description="Test override (non-production only)",
    ),
) -> None:
    """
    FastAPI dependency that enforces platform-only access.

    Raises HTTPException 403 if no valid platform-operator marker is present.
    Raises HTTPException 401 if no marker at all (unauthenticated equivalent).
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
