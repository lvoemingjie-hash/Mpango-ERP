"""R1 real-HTTP permission and tenant-isolation controls."""
from __future__ import annotations

from http import HTTPStatus

import pytest

from tests.order_state_r1.support import (
    http_action,
    http_create_order,
    make_bound_retailer,
    order_vector,
    osd1_cashier_token,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio


async def test_confirm_permission_denied_control(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """A real JWT WITHOUT orders:update is RBAC-denied before any write."""
    from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (
        _create_retailer_user,
        _grant_retailer_operator,
    )
    from tests.test_dc12r1_s3_s2b_i2b_payment_declarations import _CASHIER_PW

    db, reg = s2_clean_db
    a = provisioned_pool.tenants["a"]
    uid = await _create_retailer_user(db, tenant_schema=a["schema"],
                                      email=f"r1rbac-{__import__('uuid').uuid4().hex[:6]}@mpango-local.dev",
                                      password=_CASHIER_PW, registry=reg)
    await _grant_retailer_operator(db, tenant_schema=a["schema"], user_id=uid)

    resp = await r1_client.post("/api/v1/auth/login",
                                json={"email": None, "password": _CASHIER_PW})
    # login needs the exact email; re-login with the created identity
    from sqlalchemy import text
    row = (await db.execute(text(
        f'SELECT email FROM "{a["schema"]}".users WHERE id = :u'),
        {"u": uid})).fetchone()
    resp = await r1_client.post("/api/v1/auth/login",
                                json={"email": row.email, "password": _CASHIER_PW})
    assert resp.status_code == 200, resp.text
    identity_token = resp.json()["data"]["access_token"]
    sel = await r1_client.post("/api/v1/auth/select-tenant",
                               json={"tenant_id": a["ws_id"]},
                               headers={"Authorization": f"Bearer {identity_token}"})
    assert sel.status_code == 200, sel.text
    limited = sel.json()["data"]["access_token"]

    admin = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, admin, ret_id,
                                  [{"sku_code": sku, "quantity": 1}])

    denied = await http_action(r1_client, limited, oid, "confirm")
    assert denied.status_code in (HTTPStatus.FORBIDDEN, HTTPStatus.UNAUTHORIZED), (
        denied.status_code, denied.text)
    assert (await order_vector(db, schema, oid))["status"] == "draft"


async def test_confirm_cross_tenant_isolation_control(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """Tenant B's REAL cashier cannot confirm tenant A's order (404)."""
    import uuid as _uuid

    from tests.order_state_r1.support import make_tenant_cashier as _mtc
    from tests.order_state_r1.support import (
        make_tenant_cashier,
        osd1_cashier_token,
    )

    db, reg = s2_clean_db
    token_a = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, token_a, ret_id,
                                  [{"sku_code": sku, "quantity": 1}])

    b_cashier = await make_tenant_cashier(db, reg, provisioned_pool.tenants["b"])
    token_b = await osd1_cashier_token(r1_client, b_cashier)

    resp = await http_action(r1_client, token_b, oid, "confirm")
    assert resp.status_code == HTTPStatus.NOT_FOUND, (
        resp.status_code, resp.text)
    assert (await order_vector(db, schema, oid))["status"] == "draft"
