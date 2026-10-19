"""A JSON source label never grants negotiated prices or another party's consent."""
from copy import deepcopy
from decimal import Decimal
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from tests.s1_pricing_quote.test_http import headers
from tests.s3_negotiation.test_contract import decide, economics, offer, original

pytestmark = pytest.mark.asyncio


async def test_counterfeit_source_cannot_skip_s1_price_validation(r1_client, world):
    source = await original(r1_client, world)
    async with world['session']() as db:
        await db.execute(text("UPDATE orders SET creation_operation='client-negotiation', "
            "quote_resolved=jsonb_set(quote_resolved,'{negotiation}',CAST(:fake AS jsonb)) WHERE id=:id"),
            {'fake': json.dumps({'id': str(uuid4()), 'version': 1, 'digest': '0' * 64}), 'id': UUID(source['id'])})
        await db.commit()
    before = await economics(world)
    response = await r1_client.post(f"/api/v1/orders/{source['id']}/confirm", headers=headers(world))
    assert response.status_code == 409 and response.json()['code'] == 'NEGOTIATION_CONSENT_REQUIRED', 'S3_PERSISTED_CONSENT_NOT_SOURCE_LABEL'
    assert await economics(world) == before


async def test_same_total_different_lines_never_reuses_consent(r1_client, world):
    async with world['session']() as db:
        second = (await db.execute(text(
            "INSERT INTO skus (sku_code,name,unit,package_quantity,catalog_product_id,is_active,base_price) "
            "VALUES ('SECOND','Second box','Box',6,:pid,true,10) RETURNING id"
        ), {'pid': UUID(world['product'])})).scalar_one()
        await db.execute(text('INSERT INTO inventory_stocks (sku_id,quantity_on_hand) VALUES (:id,100)'), {'id': second})
        await db.commit()
    items = [{'sellable_unit_id': world['sku'], 'quantity': 1}, {'sellable_unit_id': str(second), 'quantity': 1}]
    quote = await r1_client.post('/api/v1/orders/quote', json={'retailer_id': world['rid'], 'items': items}, headers=headers(world))
    created = await r1_client.post('/api/v1/orders', json={'retailer_id': world['rid'], 'items': items,
        'quote_token': quote.json()['data']['quote_token']}, headers=headers(world, key=str(uuid4())))
    assert created.status_code == 201
    source = created.json()['data']
    response = await r1_client.post(f"/api/v1/orders/{source['id']}/negotiations", json={
        'lines': [{'sku_id': world['sku'], 'unit_price': '70'}, {'sku_id': str(second), 'unit_price': '30'}],
        'expires_at': '2099-10-19T12:00:00Z'}, headers=headers(world))
    assert response.status_code == 201
    proposal = response.json()['data']
    accepted = await decide(r1_client, world, source, proposal)
    assert accepted.status_code == 200
    new_id = UUID(accepted.json()['data']['accepted_order_id'])
    async with world['session']() as db:
        quote = (await db.execute(text('SELECT quote_resolved FROM orders WHERE id=:id'), {'id': new_id})).scalar_one()
        tampered = deepcopy(quote)
        for line in tampered['lines']:
            price = Decimal('80') if line['sku_id'] == world['sku'] else Decimal('20')
            line['unit_price'] = line['subtotal'] = format(price, '.2f')
            await db.execute(text('UPDATE order_items SET unit_price=:p,subtotal=:p WHERE order_id=:id AND sellable_unit_id=:sid'),
                {'p': price, 'id': new_id, 'sid': UUID(line['sku_id'])})
        await db.execute(text('UPDATE orders SET quote_seen=CAST(:q AS jsonb),quote_resolved=CAST(:q AS jsonb) WHERE id=:id'),
                         {'q': json.dumps(tampered), 'id': new_id})
        await db.commit()
    before = await economics(world)
    confirmed = await r1_client.post(f'/api/v1/orders/{new_id}/confirm', headers=headers(world))
    assert confirmed.status_code == 409 and confirmed.json()['code'] == 'NEGOTIATION_INTEGRITY', 'S3_SAME_TOTAL_DIFFERENT_LINES_NOT_CONSENT'
    assert await economics(world) == before


@pytest.mark.parametrize('problem', ['short_stock', 'inactive_sku', 'inactive_product', 'unit'])
async def test_unavailable_or_short_stock_cannot_confirm(r1_client, world, problem):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source)).json()['data']
    accepted = await decide(r1_client, world, source, proposal)
    assert accepted.status_code == 200
    new_id = accepted.json()['data']['accepted_order_id']
    statements = {
        'short_stock': 'UPDATE inventory_stocks SET quantity_on_hand=1',
        'inactive_sku': 'UPDATE skus SET is_active=false',
        'inactive_product': 'UPDATE catalog_products SET is_active=false',
        'unit': "UPDATE skus SET unit='Changed'",
    }
    async with world['session']() as db:
        await db.execute(text(statements[problem]))
        await db.commit()
    before = await economics(world)
    confirmed = await r1_client.post(f'/api/v1/orders/{new_id}/confirm', headers=headers(world))
    assert confirmed.status_code in {400, 409}, 'S3_NONPRICE_ELIGIBILITY_STILL_REQUIRED'
    assert await economics(world) == before


async def test_retained_economic_effect_refuses_accept(r1_client, world):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source)).json()['data']
    async with world['session']() as db:
        await db.execute(text(
            "INSERT INTO inventory_movements (sku_id,movement_type,quantity,quantity_before,quantity_after,reference_type,reference_id) "
            "VALUES (:sid,'deduction',-1,100,99,'order',:id)"
        ), {'sid': UUID(world['sku']), 'id': UUID(source['id'])})
        await db.commit()
    before = await economics(world)
    response = await decide(r1_client, world, source, proposal)
    assert response.status_code == 409 and response.json()['code'] == 'NEGOTIATION_SOURCE_CHANGED'
    assert await economics(world) == before


async def test_negotiated_history_reorders_at_current_price(r1_client, world):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source)).json()['data']
    accepted = await decide(r1_client, world, source, proposal)
    new_id = accepted.json()['data']['accepted_order_id']
    async with world['session']() as db:
        await db.execute(text('UPDATE skus SET base_price=120,pricing_revision=pricing_revision+1'))
        await db.commit()
    preview = await r1_client.post(f'/api/v1/client/orders/{new_id}/reorder/quote', json={}, headers=headers(world, client=True))
    assert preview.status_code == 200
    data = preview.json()['data']
    assert data['ready'] and Decimal(data['current_total']) == 240, 'S3_S2_CURRENT_PRICE_NOT_OLD_AGREEMENT'
    assert Decimal(data['historical_total']) == 140
    response = await r1_client.post('/api/v1/client/orders', json={
        'source_order_id': new_id, 'selections': [row['selection'] for row in data['rows']],
        'quote_token': data['quote']['quote_token'],
    }, headers=headers(world, client=True, key=str(uuid4())))
    assert response.status_code == 201
    async with world['session']() as db:
        op, quote = (await db.execute(text('SELECT creation_operation,quote_resolved FROM orders WHERE id=:id'),
                                     {'id': UUID(response.json()['data']['id'])})).one()
        assert op == 'client-reorder' and 'negotiation' not in quote


@pytest.mark.parametrize('revoke', ['permission', 'user'])
async def test_durable_replay_rechecks_user_and_permission(r1_client, world, revoke):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source)).json()['data']
    key = str(uuid4())
    assert (await decide(r1_client, world, source, proposal, key=key)).status_code == 200
    async with world['session']() as db:
        if revoke == 'user':
            await db.execute(text('UPDATE users SET is_active=false WHERE id=:id'), {'id': UUID(world['customer'])})
        else:
            await db.execute(text("DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE name='retailer_operator') AND permission_id IN (SELECT id FROM permissions WHERE code='client:orders:create')"))
        await db.commit()
    before = await economics(world)
    replay = await decide(r1_client, world, source, proposal, key=key)
    assert replay.status_code in {401, 403}, 'S3_LIVE_REVOCATION_REPLAY_REFUSED'
    assert await economics(world) == before


async def test_other_tenant_never_reads_or_accepts_proposal(r1_client, world, other_world):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source)).json()['data']
    before = await economics(world)
    response = await decide(r1_client, other_world, source, proposal)
    assert response.status_code == 404, 'S3_FOREIGN_TENANT_PROPOSAL_NOT_FOUND'
    listed = await r1_client.get(f"/api/v1/client/orders/{source['id']}/negotiations", headers=headers(other_world, client=True))
    assert listed.status_code == 404
    assert await economics(world) == before
