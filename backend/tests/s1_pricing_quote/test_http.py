"""Real ASGI/JWT/PG16 journeys. No permission or finance mocks."""
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


def headers(world, *, client=False, key=None):
    result = {"Authorization": "Bearer " + world["client_token" if client else "token"]}
    if key:
        result["X-Idempotency-Key"] = key
    return result


def selection(world, quantity=2):
    return [{"sellable_unit_id": world["sku"], "sku_code": "BOX", "quantity": quantity}]


async def preview(http, world, *, client=False, quantity=2):
    body = {"items": selection(world, quantity)}
    if not client:
        body["retailer_id"] = world["rid"]
    result = await http.post("/api/v1/" + ("client/" if client else "") + "orders/quote",
                             json=body, headers=headers(world, client=client))
    assert result.status_code == 200, "S1_PREVIEW_HTTP"
    return result.json()["data"]


async def submit(http, world, quote, *, client=False, key=None, replace=None, notes="S1"):
    body = {"items": selection(world), "quote_token": quote["quote_token"], "notes": notes}
    if not client:
        body["retailer_id"] = world["rid"]
    path = "/api/v1/" + ("client/" if client else "") + "orders"
    if replace:
        path += "/" + replace + "/replace-draft"
    return await http.post(path, json=body, headers=headers(world, client=client,
                             key=key or str(uuid.uuid4())))


async def facts(world):
    async with world["session"]() as db:
        return (await db.execute(text(
            "SELECT (SELECT count(*) FROM orders) AS orders, (SELECT count(*) FROM order_items) AS items, "
            "(SELECT count(*) FROM payments) AS payments, (SELECT count(*) FROM ledger_entries) AS ledger, "
            "(SELECT count(*) FROM inventory_reservations) AS reservations, "
            "(SELECT count(*) FROM order_credit_holds) AS holds, "
            "(SELECT quantity_on_hand FROM inventory_stocks WHERE sku_id=:sid) AS stock"
        ), {"sid": uuid.UUID(world["sku"])})).one()._asdict()


@pytest.mark.parametrize("world", ["KE", "UG"], indirect=True)
@pytest.mark.parametrize("client", [False, True])
async def test_two_countries_two_creation_entries(r1_client, world, client):
    quote = await preview(r1_client, world, client=client)
    assert quote["currency"] == world["currency"], "S1_COUNTRY_NOT_FIXED_KES"
    assert Decimal(quote["total"]) == Decimal("180")
    before = await facts(world)
    result = await submit(r1_client, world, quote, client=client)
    assert result.status_code == 201, "S1_DRAFT_CREATE_HTTP"
    data = result.json()["data"]
    assert type(data["total_amount"]) is str, "S1_HTTP_EXACT_MONEY_STRING"
    assert data["currency"] == world["currency"]
    assert data["items"][0]["unit_snapshot"] == "Box"
    assert Decimal(data["items"][0]["package_quantity_snapshot"]) == Decimal("12")
    after = await facts(world)
    assert (after["orders"], after["items"]) == (1, 1)
    for name in ("stock", "ledger", "payments", "holds", "reservations"):
        assert before[name] == after[name], "S1_DRAFT_ZERO_ECONOMICS"


async def test_reconsent_failure_does_not_consume_key(r1_client, world):
    quote = await preview(r1_client, world)
    key = str(uuid.uuid4())
    async with world["session"]() as db:
        await db.execute(text("UPDATE skus SET base_price=110,pricing_revision=pricing_revision+1 WHERE id=:id"),
                         {"id": uuid.UUID(world["sku"])})
        await db.commit()
    before = await facts(world)
    result = await submit(r1_client, world, quote, key=key)
    assert result.status_code == 409, "S1_STALE_REFUSES_BEFORE_WRITE"
    detail = {**result.json()["details"], "code": result.json()["code"]}
    assert detail["code"] == "PRICE_PREVIEW_STALE"
    assert detail["old_total"] == "180.00" and detail["new_total"] == "220.00"
    assert await facts(world) == before
    accepted = await submit(r1_client, world, detail["quote"], key=key)
    assert accepted.status_code == 201, "S1_EXPLICIT_RECONSENT_SUCCESS"
    async with world["session"]() as db:
        await db.execute(text("UPDATE skus SET base_price=120,pricing_revision=pricing_revision+1 WHERE id=:id"),
                         {"id": uuid.UUID(world["sku"])})
        await db.commit()
    replay = await submit(r1_client, world, detail["quote"], key=key)
    assert replay.status_code == 201 and replay.json()["data"]["id"] == accepted.json()["data"]["id"]
    assert Decimal(replay.json()["data"]["total_amount"]) == Decimal("220"), "S1_COMMITTED_REPLAY_PRESERVES_PRICE"
    stale_again = await submit(r1_client, world, detail["quote"])
    assert stale_again.status_code == 409
    assert stale_again.json()["details"]["new_total"] == "240.00"


async def test_missing_base_even_with_override(r1_client, world):
    async with world["session"]() as db:
        await db.execute(text("UPDATE skus SET base_price=NULL WHERE id=:id"), {"id": uuid.UUID(world["sku"])})
        await db.execute(text("INSERT INTO retailer_prices (sku_id,retailer_id,price) VALUES (:sid,:rid,80)"),
                         {"sid": uuid.UUID(world["sku"]), "rid": uuid.UUID(world["rid"])})
        await db.commit()
    result = await r1_client.post("/api/v1/orders/quote",
        json={"items": selection(world), "retailer_id": world["rid"]}, headers=headers(world))
    assert result.status_code == 409 and result.json()["code"] == "BASE_PRICE_REQUIRED", "S1_BASE_REQUIRED"
    products = await r1_client.get("/api/v1/client/products", headers=headers(world, client=True))
    assert products.status_code == 200
    unit = products.json()["data"]["items"][0]["units"][0]
    assert not unit["can_order"] and unit["price"] is None


async def test_versioned_override_retire_restore_same_row(r1_client, world):
    body = {"retailer_id": world["rid"], "sku_id": world["sku"], "price": "80.00", "expected_revision": 0}
    result = await r1_client.put("/api/v1/pricing/prices", json=body, headers=headers(world))
    assert result.status_code == 200
    assert Decimal((await preview(r1_client, world))["total"]) == Decimal("160")
    conflict = await r1_client.put("/api/v1/pricing/prices", json=body, headers=headers(world))
    assert conflict.status_code == 409 and conflict.json()["code"] == "PRICE_VERSION_CONFLICT"
    for revision, retire, total in ((1, True, "180"), (2, False, "160")):
        result = await r1_client.put("/api/v1/pricing/prices",
            json={**body, "expected_revision": revision, "retire": retire}, headers=headers(world))
        assert result.status_code == 200
        assert Decimal((await preview(r1_client, world))["total"]) == Decimal(total)
    async with world["session"]() as db:
        assert (await db.execute(text("SELECT count(*) FROM retailer_prices"))).scalar_one() == 1


async def test_replay_rechecks_active_binding_and_conflicting_intent(r1_client, world):
    quote = await preview(r1_client, world, client=True)
    key = str(uuid.uuid4())
    first = await submit(r1_client, world, quote, client=True, key=key)
    assert first.status_code == 201
    conflict = await submit(r1_client, world, quote, client=True, key=key, notes="different")
    assert conflict.status_code == 409 and conflict.json()["code"] == "ORDER_CREATE_IDEMPOTENCY_CONFLICT"
    async with world["session"]() as db:
        await db.execute(text("UPDATE public.wholesaler_retailer_bindings SET status='inactive' "
                              "WHERE wholesaler_id=:wid AND retailer_id=:rid"),
                         {"wid": uuid.UUID(world["wid"]), "rid": uuid.UUID(world["rid"])})
        await db.commit()
    rejected = await submit(r1_client, world, quote, client=True, key=key)
    assert rejected.status_code == 403, "S1_REVOKED_REPLAY_NOT_CACHED"
    assert (await facts(world))["orders"] == 1


async def test_explicit_replacement_preserves_old_items(r1_client, world):
    quote = await preview(r1_client, world, client=True)
    old = await submit(r1_client, world, quote, client=True)
    assert old.status_code == 201
    old_id = old.json()["data"]["id"]
    async with world["session"]() as db:
        await db.execute(text("UPDATE skus SET base_price=110,pricing_revision=1 WHERE id=:id"),
                         {"id": uuid.UUID(world["sku"])})
        await db.commit()
    new_quote = await preview(r1_client, world, client=True)
    key = str(uuid.uuid4())
    replacement = await submit(r1_client, world, new_quote, client=True, key=key, replace=old_id)
    assert replacement.status_code == 201, "S1_REPLACEMENT_SUCCESS"
    repeat = await submit(r1_client, world, new_quote, client=True, key=key, replace=old_id)
    assert repeat.status_code == 201 and repeat.json()["data"]["id"] == replacement.json()["data"]["id"]
    async with world["session"]() as db:
        row = (await db.execute(text("SELECT status,total_amount FROM orders WHERE id=:id"),
                              {"id": uuid.UUID(old_id)})).one()
        assert row.status == "cancelled" and row.total_amount == Decimal("180"), "S1_OLD_SNAPSHOT_UNCHANGED"
    assert (await facts(world))["orders"] == 2


@pytest.mark.parametrize("world", ["KE", "UG"], indirect=True)
async def test_confirm_uses_snapshot_and_one_quantity_contract(r1_client, world):
    quote = await preview(r1_client, world)
    result = await submit(r1_client, world, quote)
    oid = result.json()["data"]["id"]
    confirmed = await r1_client.post(f"/api/v1/orders/{oid}/confirm", headers=headers(world))
    assert confirmed.status_code == 200, "S1_CONFIRM_VERIFIED_DRAFT"
    async with world["session"]() as db:
        row = (await db.execute(text("SELECT quantity_on_hand,quantity_reserved "
                              "FROM inventory_stocks WHERE sku_id=:sid"),
                              {"sid": uuid.UUID(world["sku"])})).one()
        assert (row.quantity_on_hand, row.quantity_reserved) == (100, 2), "S1_QUANTITY_NOT_PACK_MULTIPLIED"
        assert (await db.execute(text("SELECT count(*) FROM ledger_entries"))).scalar_one() == 0


async def test_used_unit_change_refuses_both_entries_label_preserves_history(r1_client, world):
    quote = await preview(r1_client, world)
    old = await submit(r1_client, world, quote)
    for path in ("/api/v1/skus/BOX", f"/api/v1/catalog-products/{world['product']}/sellable-units/{world['sku']}"):
        rejected = await r1_client.put(path, json={"unit": "box"}, headers=headers(world))
        assert (rejected.status_code == 409 and rejected.json()['code'] ==
                'SKU_PACKAGE_QUANTITY_IMMUTABLE_AFTER_USE'), "S1_USED_UNIT_REQUIRES_NEW_SKU"
        changed = await r1_client.put(path, json={"display_label": "Boxes"}, headers=headers(world))
        assert changed.status_code == 200, "S1_HARMLESS_DISPLAY_LABEL"
    read = await r1_client.get("/api/v1/orders/" + old.json()["data"]["id"], headers=headers(world))
    assert read.json()["data"]["items"][0]["unit_snapshot"] == "Box"
    assert read.json()["data"]["items"][0]["display_label_snapshot"] == "Box"
    accepted = await submit(r1_client, world, quote)
    assert accepted.status_code == 201, "S1_LABEL_SAME_PRICE_NO_EXTRA_CONSENT"


async def test_client_cannot_replace_merchant_or_confirmed_draft(r1_client, world):
    merchant = await submit(r1_client, world, await preview(r1_client, world))
    client_quote = await preview(r1_client, world, client=True)
    before = await facts(world)
    result = await submit(r1_client, world, client_quote, client=True, replace=merchant.json()["data"]["id"])
    assert result.status_code == 403, "S1_CLIENT_REPLACEMENT_PROVENANCE"
    assert await facts(world) == before


async def test_stale_confirm_does_not_reprice_or_start_economics(r1_client, world):
    draft = await submit(r1_client, world, await preview(r1_client, world))
    async with world["session"]() as db:
        await db.execute(text("UPDATE skus SET base_price=120 WHERE id=:id"), {"id": uuid.UUID(world["sku"])})
        await db.commit()
    before = await facts(world)
    result = await r1_client.post("/api/v1/orders/" + draft.json()["data"]["id"] + "/confirm", headers=headers(world))
    assert result.status_code == 409 and result.json()["code"] == "DRAFT_REQUOTE_REQUIRED"
    assert await facts(world) == before, "S1_STALE_CONFIRM_ZERO_ECONOMICS"


async def test_quote_cannot_move_to_another_authorized_customer(r1_client, world):
    quote = await preview(r1_client, world)
    second = uuid.uuid4()
    async with world['session']() as db:
        await db.execute(text("INSERT INTO public.retailers(id,phone,name) VALUES(:id,:phone,'S1 second')"),
                         {'id': second, 'phone': '+256' + str(second.int)[:12]})
        await db.execute(text("INSERT INTO public.wholesaler_retailer_bindings(wholesaler_id,retailer_id,status,outstanding_balance) "
                              "VALUES(:wid,:rid,'active',0)"), {'wid': uuid.UUID(world['wid']), 'rid': second})
        await db.commit()
    before = await facts(world)
    result = await submit(r1_client, {**world, 'rid': str(second)}, quote)
    assert result.status_code == 409 and result.json()['code'] == 'QUOTE_CONTEXT_CHANGED', 'S1_CROSS_CUSTOMER_TOKEN_REFUSED'
    assert await facts(world) == before


async def test_wrong_tenant_and_current_rbac_revoke_before_replay(r1_client, world):
    from core.security import create_contextual_token
    quote = await preview(r1_client, world)
    key = str(uuid.uuid4())
    first = await submit(r1_client, world, quote, key=key)
    assert first.status_code == 201
    # A genuine signed JWT with a different tenant must not read the durable result.
    foreign = create_contextual_token(world['actor'], ['admin'], str(uuid.uuid4()), world['schema'])
    denied = await submit(r1_client, {**world, 'token': foreign}, quote, key=key)
    assert denied.status_code in (401, 403), 'S1_CROSS_TENANT_REPLAY_NO_RESULT'
    async with world['session']() as db:
        await db.execute(text('DELETE FROM user_roles WHERE user_id=:id'), {'id': uuid.UUID(world['actor'])})
        await db.commit()
    denied = await submit(r1_client, world, quote, key=key)
    assert denied.status_code == 403, 'S1_CURRENT_RBAC_REVOKE_NOT_CACHED'


async def test_opposing_prices_same_total_requires_real_http_consent(r1_client, world):
    async with world['session']() as db:
        second = (await db.execute(text(
            "INSERT INTO skus(sku_code,name,unit,package_quantity,catalog_product_id,base_price) "
            "VALUES('BOX2','Second','Box',12,:pid,90) RETURNING id"
        ), {'pid': uuid.UUID(world['product'])})).scalar_one()
        await db.execute(text('INSERT INTO inventory_stocks(sku_id,quantity_on_hand) VALUES(:s,100)'), {'s': second})
        await db.commit()
    body = {'retailer_id': world['rid'], 'items': selection(world) + [{'sellable_unit_id': str(second), 'quantity': 2}]}
    quote = (await r1_client.post('/api/v1/orders/quote', json=body, headers=headers(world))).json()['data']
    before = await facts(world)
    async with world['session']() as db:
        await db.execute(text('UPDATE skus SET base_price=CASE WHEN id=:a THEN 110 ELSE 70 END, pricing_revision=pricing_revision+1'),
                         {'a': uuid.UUID(world['sku'])})
        await db.commit()
    result = await r1_client.post('/api/v1/orders', json={**body, 'quote_token': quote['quote_token']},
                                 headers=headers(world, key=str(uuid.uuid4())))
    assert result.status_code == 409 and result.json()['code'] == 'PRICE_PREVIEW_STALE', 'S1_SAME_TOTAL_NOT_CONSENT'
    assert result.json()['details']['delta'] == '0.00'
    assert await facts(world) == before, 'S1_SAME_TOTAL_ZERO_ECONOMICS'


async def test_same_economics_aba_success_records_both_revisions(r1_client, world):
    quote = await preview(r1_client, world)
    async with world['session']() as db:
        for value in (110, 90):
            await db.execute(text('UPDATE skus SET base_price=:v,pricing_revision=pricing_revision+1 WHERE id=:id'),
                             {'v': value, 'id': uuid.UUID(world['sku'])})
            await db.commit()
    result = await submit(r1_client, world, quote)
    assert result.status_code == 201, 'S1_SAME_ECONOMICS_ABA_ACCEPTED'
    async with world['session']() as db:
        row = (await db.execute(text('SELECT quote_seen,quote_resolved FROM orders'))).one()
        assert row.quote_seen['lines'][0]['revision'] == 0 and row.quote_resolved['lines'][0]['revision'] == 2


@pytest.mark.parametrize('world', ['UG'], indirect=True)
async def test_old_fractional_ugx_price_remains_readable_but_not_orderable(r1_client, world):
    before = await facts(world)
    async with world['session']() as db:
        await db.execute(text('UPDATE skus SET base_price=90.01 WHERE id=:id'), {'id': uuid.UUID(world['sku'])})
        await db.commit()
    listed = await r1_client.get('/api/v1/pricing/prices', params={'retailer_id': world['rid']}, headers=headers(world))
    assert listed.status_code == 200
    row = listed.json()['data']['items'][0]
    assert row['base_price'] == '90.01' and row['price'] is None and row['unorderable_reason'] == 'MONEY_PRECISION'
    rejected = await r1_client.post('/api/v1/orders/quote',
        json={'retailer_id': world['rid'], 'items': selection(world)}, headers=headers(world))
    assert rejected.status_code == 422 and rejected.json()['code'] == 'MONEY_PRECISION'
    assert await facts(world) == before, 'S1_LEGACY_PRECISION_REFUSAL_ZERO_EFFECTS'
