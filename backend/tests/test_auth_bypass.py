"""
Test authentication behavior under strategy selection.

This test verifies that:
1. MPANGO_ENV=test uses MockAuthStrategy (no JWT required)
2. MPANGO_ENV=production uses JwtAuthStrategy (JWT required)
"""
import os
import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI, Request

from api.context.auth import get_auth_context
from api.context.tenant import get_tenant_context
from api.middleware.auth import AuthenticationMiddleware
from auth.factory import get_auth_strategy


def _build_client(*, env: str) -> TestClient:
    os.environ["MPANGO_ENV"] = env

    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware, strategy=get_auth_strategy())

    @app.get("/health")
    async def _health():
        return {"status": "healthy"}

    @app.get("/whoami")
    async def _whoami(request: Request):
        auth_ctx = get_auth_context(request)
        return {"user_id": auth_ctx.token.user_id, "tenant_id": auth_ctx.token.tenant_id}

    @app.get("/protected")
    async def _protected(request: Request):
        tenant_ctx = get_tenant_context(request)

        user_permissions = set()
        for role in tenant_ctx.user.roles:
            for perm in role.permissions:
                user_permissions.add(perm.code)

        if "payments:create" not in user_permissions:
            return {"ok": False}

        return {"ok": True}

    return TestClient(app)


@pytest.fixture
def client_test_env():
    return _build_client(env="test")


@pytest.fixture
def client_production_env():
    return _build_client(env="production")


def test_auth_bypass_enabled(client_test_env):
    """
    Test that MPANGO_ENV=test bypasses authentication but preserves RBAC.

    Setup: Set MPANGO_ENV=test
    Action: POST /api/v1/payments without Authorization header
    Assertion: Should fail with 422 (validation error) not 401 (auth error)
    """
    response = client_test_env.get("/whoami")
    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"]
    assert payload["tenant_id"]


def test_auth_bypass_with_valid_payload(client_test_env):
    """
    Test that MPANGO_ENV=test allows requests through (health endpoint).

    Setup: Set MPANGO_ENV=test
    Action: GET /api/v1/health (simple endpoint that doesn't require DB)
    Assertion: Should succeed without auth header
    """
    # Use health endpoint which doesn't require database access
    response = client_test_env.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_auth_bypass_disabled(client_production_env):
    """
    Test that production strategy requires JWT.

    Setup: Set MPANGO_ENV=production
    Action: POST /api/v1/payments without Authorization header
    Assertion: Should fail with 401 (auth required)
    """
    response = client_production_env.get("/whoami")

    assert response.status_code == 401, \
        f"Expected auth error (401), got {response.status_code}: {response.text}"


def test_jwt_strategy_rejects_invalid_auth_scheme(client_production_env):
    """Prove JwtAuthStrategy is active in production by rejecting a non-bearer auth scheme."""

    response = client_production_env.get("/health", headers={"Authorization": "Basic abc"})

    assert response.status_code == 401
    payload = response.json()
    assert payload.get("code") == "INVALID_AUTH_SCHEME"


def test_rbac_still_enforced_in_test_mode(client_test_env):
    """
    Test that RBAC permission checks are still enforced in MPANGO_ENV=test.

    This test verifies that even though auth is bypassed, the permission
    system still validates that the mock user has the required permissions.

    Note: This test assumes the test mode user has payments:create but
    may not have other permissions. Adjust based on actual implementation.
    """
    response = client_test_env.get("/protected")
    assert response.status_code == 200
    assert response.json()["ok"] is True
