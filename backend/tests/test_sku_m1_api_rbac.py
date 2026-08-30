"""Registered-route RBAC contract for catalog products and packaging."""

from __future__ import annotations

from fastapi.routing import APIRoute

from api.middleware.rbac import RequirePermission
from api.v1.catalog_products import router


def _route_permissions() -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        permissions = {
            dependency.call.permission
            for dependency in route.dependant.dependencies
            if isinstance(dependency.call, RequirePermission)
        }
        assert len(permissions) == 1, f"{route.path} must have exactly one RBAC dependency"
        permission = next(iter(permissions))
        for method in route.methods or set():
            result[(method, route.path)] = permission
    return result


def test_catalog_product_routes_use_exact_read_create_update_permissions() -> None:
    assert _route_permissions() == {
        ("GET", ""): "skus:read",
        ("POST", ""): "skus:create",
        ("GET", "/{product_id}"): "skus:read",
        ("PUT", "/{product_id}"): "skus:update",
        ("POST", "/{product_id}/sellable-units"): "skus:create",
        ("PUT", "/{product_id}/sellable-units/{sellable_unit_id}"): "skus:update",
    }
