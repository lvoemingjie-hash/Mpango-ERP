from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from api.v1.auth import get_current_user, select_tenant
from core.security import TokenPayload
from schemas.auth import CurrentUserResponse, SelectTenantRequest


@pytest.mark.asyncio
async def test_select_tenant_uses_user_roles_table_and_returns_contextual_tokens():
    user_id = "11111111-1111-1111-1111-111111111111"
    tenant_id = "22222222-2222-4222-8222-222222222222"
    tenant_schema = "t_demo"

    db = AsyncMock()

    user_result = MagicMock()
    user_result.fetchone.return_value = SimpleNamespace(id=UUID(user_id), is_active=True)

    roles_result = MagicMock()
    roles_result.fetchall.return_value = [("admin",), ("manager",)]

    db.execute = AsyncMock(side_effect=[user_result, roles_result])

    wholesaler = MagicMock()
    wholesaler.id = tenant_id
    wholesaler.get_tenant_schema.return_value = tenant_schema

    with patch("api.v1.auth.get_wholesaler_by_id", new=AsyncMock(return_value=wholesaler)), patch(
        "api.v1.auth.create_contextual_token",
        side_effect=["ctx-access-token", "ctx-refresh-token"],
    ) as mock_create_contextual_token:
        response = await select_tenant(
            request=SelectTenantRequest(tenant_id=tenant_id),
            token=TokenPayload(user_id=user_id, roles=["admin"]),
            db=db,
        )

    assert response.success is True
    assert response.data.access_token == "ctx-access-token"
    assert response.data.refresh_token == "ctx-refresh-token"
    assert response.data.user_id == user_id
    assert response.data.tenant_id == tenant_id
    assert response.data.tenant_schema == tenant_schema
    assert response.data.roles == ["admin", "manager"]

    roles_query = str(db.execute.await_args_list[1].args[0])
    assert f'"{tenant_schema}".user_roles' in roles_query
    assert f'"{tenant_schema}".user_role ' not in roles_query
    assert db.execute.await_args_list[1].args[1]["user_id"] == UUID(user_id)

    assert len(mock_create_contextual_token.call_args_list) == 2
    assert mock_create_contextual_token.call_args_list[0].kwargs["token_type"] == "access"
    assert mock_create_contextual_token.call_args_list[1].kwargs["token_type"] == "refresh"


@pytest.mark.asyncio
async def test_get_current_user_identity_token_returns_nullable_email():
    response = await get_current_user(
        request=MagicMock(),
        token=TokenPayload(user_id="identity-user", roles=["admin"]),
    )

    assert isinstance(response, CurrentUserResponse)
    assert response.success is True
    assert response.data.id == "identity-user"
    assert response.data.email is None
    assert response.data.tenant_id is None
    assert response.data.tenant_schema is None
    assert response.data.roles == ["admin"]
    assert response.data.permissions == []
