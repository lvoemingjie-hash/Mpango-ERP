"""Real HTTP/PG transactions for commercial proposals; assertions are economic."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from tests.s1_pricing_quote.test_http import headers, preview, submit

pytestmark = pytest.mark.asyncio


async def original(http, world):
    quote = await preview(http, world)
    response = await submit(http, world, quote)
    assert response.status_code == 201, 'S3_ORIGINAL_VERIFIED_DRAFT'
    saved = await http.get(f"/api/v1/orders/{response.json()['data']['id']}", headers=headers(world))
    assert saved.status_code == 200
    return saved.json()['data']


async def offer(http, world, source, *, price='70', expires=None):
    response = await http.post(f"/api/v1/orders/{source['id']}/negotiations", json={
        'lines': [{'sku_id': world['sku'], 'unit_price': price}],
        'expires_at': expires or (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
    }, headers=headers(world))
    return response


async def decide(http, world, source, proposal, action='accept', key=None, **changes):
    body = {'version': proposal['version'], 'digest': proposal['digest']} | changes
    return await http.post(
        f"/api/v1/client/orders/{source['id']}/negotiations/{proposal['id']}/{action}",
        json=body, headers=headers(world, client=True, key=key or str(uuid4())))


async def economics(world):
    async with world['session']() as db:
        return (await db.execute(text(
            'SELECT (SELECT count(*) FROM payments) AS payments, '
            '(SELECT count(*) FROM ledger_entries) AS ledger, '
            '(SELECT count(*) FROM inventory_movements) AS movements, '
            '(SELECT count(*) FROM inventory_reservations) AS reservations, '
            '(SELECT count(*) FROM order_credit_holds) AS holds, '
            '(SELECT sum(quantity_on_hand) FROM inventory_stocks) AS stock, '
            '(SELECT sum(quantity_reserved) FROM inventory_stocks) AS reserved, '
            '(SELECT outstanding_balance FROM public.wholesaler_retailer_bindings '
            'WHERE wholesaler_id=:wid AND retailer_id=:rid) AS binding'
        ), {'wid': UUID(world['wid']), 'rid': UUID(world['rid'])})).one()._asdict()


@pytest.mark.parametrize('world', ['UG', 'KE'], indirect=True)
async def test_accept_preserves_history_and_zero_economics_then_confirms_fixed_price(r1_client, world):
    source = await original(r1_client, world)
    before = await economics(world)
    response = await offer(r1_client, world, source)
    assert response.status_code == 201, 'S3_PROPOSAL_CREATED'
    proposal = response.json()['data']
    assert proposal['currency'] == world['currency']
    assert Decimal(proposal['total']) == 140
    result = await decide(r1_client, world, source, proposal)
    assert result.status_code == 200, 'S3_ACCEPTED_ATOMICALLY'
    new_id = result.json()['data']['accepted_order_id']
    assert new_id and new_id != source['id']
    assert await economics(world) == before, 'S3_ACCEPTANCE_ZERO_ECONOMIC_EFFECTS'
    old = await r1_client.get(f"/api/v1/orders/{source['id']}", headers=headers(world))
    assert old.json()['data']['status'] == 'cancelled'
    assert old.json()['data']['items'] == source['items'], 'S3_ORIGINAL_ITEMS_IMMUTABLE'
    async with world['session']() as db:
        await db.execute(text('UPDATE skus SET base_price=200,pricing_revision=pricing_revision+1'))
        await db.commit()
    confirmed = await r1_client.post(f'/api/v1/orders/{new_id}/confirm', headers=headers(world))
    assert confirmed.status_code == 200, 'S3_GENUINE_AGREEMENT_SURVIVES_ORDINARY_PRICE_CHANGE'
    after = await economics(world)
    assert after['holds'] == 1 and after['reservations'] == 1
    assert after['binding'] == Decimal('140'), 'S3_CONFIRM_ONLY_EXISTING_HOLD'
    assert after['reserved'] == Decimal('2'), 'S3_CONFIRM_ONCE_ONLY_RESERVATION'
    for key in ('payments', 'ledger', 'movements', 'stock'):
        assert after[key] == before[key]


async def test_one_pending_withdraw_new_version_and_reject(r1_client, world):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source)).json()['data']
    duplicate = await offer(r1_client, world, source)
    assert duplicate.status_code == 409 and duplicate.json()['code'] == 'NEGOTIATION_PENDING'
    withdrawn = await r1_client.post(
        f"/api/v1/orders/{source['id']}/negotiations/{proposal['id']}/withdraw",
        json={'version': proposal['version'], 'digest': proposal['digest']}, headers=headers(world))
    assert withdrawn.status_code == 200
    second = (await offer(r1_client, world, source, price='65')).json()['data']
    assert second['version'] == proposal['version'] + 1
    rejected = await decide(r1_client, world, source, second, 'reject')
    assert rejected.status_code == 200 and rejected.json()['data']['status'] == 'rejected'
    history = await r1_client.get(f"/api/v1/client/orders/{source['id']}/negotiations", headers=headers(world, client=True))
    assert [item['status'] for item in history.json()['data']['items']] == ['rejected', 'withdrawn']
    assert (await decide(r1_client, world, source, proposal)).status_code == 409


@pytest.mark.parametrize('price', ['0', '-1', 'NaN', 'Infinity', '99999999999999', '70.001'])
async def test_invalid_exact_money_has_no_proposal(r1_client, world, price):
    source = await original(r1_client, world)
    result = await offer(r1_client, world, source, price=price)
    assert result.status_code == 422, 'S3_EXACT_POSITIVE_MONEY'
    async with world['session']() as db:
        assert (await db.execute(text('SELECT count(*) FROM order_negotiation_proposals'))).scalar_one() == 0


@pytest.mark.parametrize('deadline', ['2000-01-01T00:00:00Z', '2099-01-01T12:00:00', None])
async def test_deadline_mandatory_aware_and_future(r1_client, world, deadline):
    source = await original(r1_client, world)
    body = {'lines': [{'sku_id': world['sku'], 'unit_price': '70'}]}
    if deadline is not None:
        body['expires_at'] = deadline
    result = await r1_client.post(f"/api/v1/orders/{source['id']}/negotiations", json=body, headers=headers(world))
    assert result.status_code in {409, 422}, 'S3_EXPLICIT_FUTURE_DEADLINE'


async def test_committed_replay_checks_intent_and_live_binding(r1_client, world):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source)).json()['data']
    key = str(uuid4())
    first = await decide(r1_client, world, source, proposal, key=key)
    assert first.status_code == 200
    replay = await decide(r1_client, world, source, proposal, key=key)
    assert replay.status_code == 200 and replay.json()['data']['replayed'] is True
    assert replay.json()['data']['accepted_order_id'] == first.json()['data']['accepted_order_id']
    conflict = await decide(r1_client, world, source, proposal, key=key, digest='0' * 64)
    assert conflict.status_code == 409 and conflict.json()['code'] == 'NEGOTIATION_INTENT_CONFLICT'
    assert (await decide(r1_client, world, source, proposal)).status_code == 409
    before = await economics(world)
    async with world['session']() as db:
        await db.execute(text("UPDATE public.wholesaler_retailer_bindings SET status='suspended' WHERE wholesaler_id=:wid"), {'wid': UUID(world['wid'])})
        await db.commit()
    denied = await decide(r1_client, world, source, proposal, key=key)
    assert denied.status_code == 403, 'S3_NO_CACHED_AUTHORITY_REPLAY'
    assert await economics(world) == before


async def test_merchant_cannot_accept_and_retailer_cannot_propose(r1_client, world):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source)).json()['data']
    denied = await r1_client.post(
        f"/api/v1/client/orders/{source['id']}/negotiations/{proposal['id']}/accept",
        json={'version': proposal['version'], 'digest': proposal['digest']},
        headers=headers(world, key=str(uuid4())))
    assert denied.status_code == 403
    denied = await r1_client.post(f"/api/v1/orders/{source['id']}/negotiations", json={
        'lines': [{'sku_id': world['sku'], 'unit_price': '70'}],
        'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }, headers=headers(world, client=True))
    assert denied.status_code == 403
