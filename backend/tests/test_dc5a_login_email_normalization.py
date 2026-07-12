from types import SimpleNamespace

import pytest

from api.v1 import auth as auth_api
from schemas.auth import LoginRequest


@pytest.mark.asyncio
async def test_login_normalizes_email_before_cross_tenant_lookup(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_find_user_across_tenants(db, email: str, password: str):
        captured["email"] = email
        captured["password"] = password
        match = SimpleNamespace(
            roles=["admin"],
            wholesaler=SimpleNamespace(
                id="00000000-0000-0000-0000-000000000001",
                code="ACME",
                name="Acme Wholesale",
            ),
            user=SimpleNamespace(id="00000000-0000-0000-0000-000000000002"),
        )
        return "00000000-0000-0000-0000-000000000002", [match]

    def fake_create_identity_token(**kwargs):
        return f"identity-{kwargs['token_type']}-value"

    monkeypatch.setattr(auth_api, "find_user_across_tenants", fake_find_user_across_tenants)
    monkeypatch.setattr(auth_api, "create_identity_token", fake_create_identity_token)

    response = await auth_api.login(
        LoginRequest(email="  Owner@Example.COM  ", password="valid-passphrase"),  # pragma: allowlist secret
        db=object(),
    )

    assert captured == {
        "email": "owner@example.com",
        "password": "valid-passphrase",  # pragma: allowlist secret
    }
    assert response.success is True
