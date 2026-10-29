"""Current self portal context: real identity and no financial capability."""
from uuid import uuid4

from fastapi.routing import APIRoute
import pytest
from sqlalchemy import text

from tests.test_cashier_context_readonly_contract import context_world, headers, code

pytestmark = pytest.mark.asyncio


async def test_current_self_context_has_no_financial_fields(context_world):
    world = context_world
    for tenant, retailer in ((world.a, world.ra), (world.a, world.ra2), (world.b, world.rb)):
        response = await world.http.get("/api/v1/client/auth/context", headers=headers(retailer["token"]))
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert set(data) == {"context", "supplier", "retailer", "binding", "observed_at"}
        assert data["context"] == {"tenant_id": str(tenant.wid), "user_id": str(retailer["uid"])}
        assert data["supplier"]["id"] == str(tenant.wid) and data["supplier"]["code"] == tenant.code
        assert data["retailer"]["id"] == str(retailer["id"]) and data["binding"]["id"] == str(retailer["binding"])
        assert set(data["binding"]) == {"id", "status"}


@pytest.mark.parametrize("selector", ["retailer_id", "wholesaler_id", "order_id", "binding_id", "schema"])
async def test_self_context_rejects_other_identity_selectors(context_world, selector):
    world = context_world
    response = await world.http.get(f"/api/v1/client/auth/context?{selector}={uuid4()}", headers=headers(world.ra["token"]))
    assert (response.status_code, code(response)) == (400, "INVALID_CONTEXT_SELECTOR")


async def test_not_public_and_merchant_is_not_client(context_world):
    world = context_world
    response = await world.http.get("/api/v1/client/auth/context")
    assert response.status_code == 401
    response = await world.http.get("/api/v1/client/auth/context", headers=headers(world.owner))
    assert (response.status_code, code(response)) == (403, "NOT_RETAILER_OPERATOR")
    from api.v1.client.dependencies import resolve_client_identity
    route = next(route for route in world.app.routes if isinstance(route, APIRoute) and route.path == "/api/v1/client/auth/context")
    assert any(dep.call is resolve_client_identity for dep in route.dependant.dependencies)
    assert not any(getattr(dep.call, "permission", None) == "client:finance:read" for dep in route.dependant.dependencies)


async def test_binding_revocation_is_current_not_login_cached(context_world):
    world = context_world
    # SQL is a disclosed damaged/inactive relationship fixture, never an auth
    # grant. This tests the exact current resolver refusal with a prior JWT.
    async with world.damage(world.a,
        "UPDATE public.wholesaler_retailer_bindings SET status='inactive' WHERE id=:b",
        "UPDATE public.wholesaler_retailer_bindings SET status='active' WHERE id=:b", {"b": world.ra["binding"]}):
        response = await world.http.get("/api/v1/client/auth/context", headers=headers(world.ra["token"]))
        assert (response.status_code, code(response)) == (403, "BINDING_NOT_ACTIVE")


async def test_live_directory_and_name_resolution(context_world):
    world = context_world
    async with world.damage(world.a, "UPDATE public.retailers SET is_deleted=TRUE WHERE id=:r",
                            "UPDATE public.retailers SET is_deleted=FALSE WHERE id=:r", {"r": world.ra["id"]}):
        response = await world.http.get("/api/v1/client/auth/context", headers=headers(world.ra["token"]))
        assert (response.status_code, code(response)) == (403, "PORTAL_CONTEXT_UNAVAILABLE")
    async with world.damage(world.a, "UPDATE public.retailers SET name=NULL WHERE id=:r",
                            "UPDATE public.retailers SET name='Retailer' WHERE id=:r", {"r": world.ra["id"]}):
        response = await world.http.get("/api/v1/client/auth/context", headers=headers(world.ra["token"]))
        assert response.status_code == 200
        assert response.json()["data"]["retailer"]["name"] is None
        assert response.json()["data"]["retailer"]["name_resolution"] == "MISSING"


async def test_second_read_rechecks_binding_after_resolver(context_world):
    world = context_world
    from services import party_context_service
    original = party_context_service.read_client_portal_context
    from unittest.mock import patch

    async def change_then_read(db, **kwargs):
        # A separate committed write occurs after real resolve_client_identity,
        # before the new service's statement. Do not replace that statement.
        async with world.a.session() as change:
            await change.execute(text("UPDATE public.wholesaler_retailer_bindings SET status='inactive' WHERE id=:b"), {"b": world.ra["binding"]})
        return await original(db, **kwargs)

    try:
        with patch.object(party_context_service, "read_client_portal_context", change_then_read):
            response = await world.http.get("/api/v1/client/auth/context", headers=headers(world.ra["token"]))
        assert (response.status_code, code(response)) == (403, "PORTAL_CONTEXT_UNAVAILABLE")
    finally:
        async with world.a.session() as db:
            await db.execute(text("UPDATE public.wholesaler_retailer_bindings SET status='active' WHERE id=:b"), {"b": world.ra["binding"]})
