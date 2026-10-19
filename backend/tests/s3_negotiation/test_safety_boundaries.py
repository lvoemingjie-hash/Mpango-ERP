"""Storage history, scoped intent, another real retailer and completed expiry."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.s1_pricing_quote.test_http import headers
from tests.s3_negotiation.test_atomicity_and_races import until_deadline
from tests.s3_negotiation.test_contract import decide, economics, offer, original

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('change', ['price', 'deadline', 'delete'])
async def test_offer_immutable_and_pending_unique_at_storage(r1_client, world, change):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source)).json()['data']
    async with world['session']() as db:
        with pytest.raises(DBAPIError, match='NEGOTIATION_HISTORY_IMMUTABLE'):
            async with db.begin_nested():
                if change == 'price':
                    await db.execute(text("UPDATE order_negotiation_proposals SET payload=jsonb_set(payload,'{total}','\"1\"'::jsonb) WHERE id=:id"), {'id': UUID(proposal['id'])})
                elif change == 'deadline':
                    await db.execute(text("UPDATE order_negotiation_proposals SET expires_at=expires_at+interval '1 day' WHERE id=:id"), {'id': UUID(proposal['id'])})
                else:
                    await db.execute(text('DELETE FROM order_negotiation_proposals WHERE id=:id'), {'id': UUID(proposal['id'])})
        with pytest.raises(DBAPIError, match='ux_negotiation_pending_source'):
            async with db.begin_nested():
                await db.execute(text('INSERT INTO order_negotiation_proposals '
                    '(id,source_order_id,wholesaler_id,retailer_id,created_by,created_at,version,expires_at,payload,digest,status) '
                    'SELECT :new,source_order_id,wholesaler_id,retailer_id,created_by,created_at,version+1,expires_at,payload,digest,status '
                    'FROM order_negotiation_proposals WHERE id=:id'), {'new': uuid4(), 'id': UUID(proposal['id'])})
        await db.commit()
    history = await r1_client.get(f"/api/v1/client/orders/{source['id']}/negotiations", headers=headers(world, client=True))
    assert history.json()['data']['items'] == [proposal], 'S3_NO_HISTORY_REWRITE_OR_DUPLICATE_PENDING'


async def test_key_cannot_accept_a_different_proposal(r1_client, world):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source)).json()['data']
    key = str(uuid4())
    assert (await decide(r1_client, world, source, proposal, key=key)).status_code == 200
    second = await original(r1_client, world)
    second_proposal = (await offer(r1_client, world, second, price='65')).json()['data']
    before = await economics(world)
    refused = await decide(r1_client, world, second, second_proposal, key=key)
    assert refused.status_code == 409 and refused.json()['code'] == 'NEGOTIATION_IDEMPOTENCY_CONFLICT', 'S3_DURABLE_KEY_DIFFERENT_PROPOSAL_CONFLICT'
    assert await economics(world) == before


async def test_foreign_retailer_within_same_tenant_is_denied(r1_client, world):
    from core.security import create_contextual_token, hash_password
    import secrets
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source)).json()['data']
    uid, rid = uuid4(), uuid4()
    async with world['session']() as db:
        await db.execute(text("INSERT INTO users (id,email,password_hash,is_active) VALUES (:id,:email,:hash,true)"),
                         {'id': uid, 'email': uid.hex+'@example.com', 'hash': hash_password(secrets.token_urlsafe(32))})
        await db.execute(text("INSERT INTO user_roles(user_id,role_id) SELECT :id,id FROM roles WHERE name='retailer_operator'"), {'id': uid})
        await db.execute(text("INSERT INTO public.retailers(id,phone,name) VALUES (:id,:phone,'Other customer')"),
                         {'id': rid, 'phone': '+256'+str(rid.int)[:12]})
        await db.execute(text("INSERT INTO public.wholesaler_retailer_bindings(wholesaler_id,retailer_id,tenant_user_id,status,outstanding_balance) VALUES(:wid,:rid,:uid,'active',0)"),
                         {'wid': UUID(world['wid']), 'rid': rid, 'uid': uid})
        await db.commit()
    token = create_contextual_token(str(uid), ['retailer_operator'], world['wid'], world['schema'])
    before = await economics(world)
    refused = await r1_client.post(f"/api/v1/client/orders/{source['id']}/negotiations/{proposal['id']}/accept",
        json={'version': proposal['version'], 'digest': proposal['digest']},
        headers={'Authorization': 'Bearer '+token, 'X-Idempotency-Key': str(uuid4())})
    assert refused.status_code == 404, 'S3_OTHER_REAL_RETAILER_NOT_FOUND'
    assert await economics(world) == before


async def test_confirmed_agreement_is_not_undone_by_later_expiry(r1_client, world):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source,
        expires=(datetime.now(timezone.utc)+timedelta(seconds=5)).isoformat())).json()['data']
    accepted = await decide(r1_client, world, source, proposal)
    assert accepted.status_code == 200
    new_id = accepted.json()['data']['accepted_order_id']
    assert (await r1_client.post(f'/api/v1/orders/{new_id}/confirm', headers=headers(world))).status_code == 200
    before = await economics(world)
    await until_deadline(world, proposal['expires_at'])
    assert await economics(world) == before, 'S3_SUCCESSFUL_CONFIRMATION_NOT_REVERSED_AT_EXPIRY'
    order = await r1_client.get(f'/api/v1/orders/{new_id}', headers=headers(world))
    assert order.json()['data']['status'] == 'confirmed'


@pytest.mark.parametrize('method,hold_state,balance', [('cash', 'settled', '0'), ('credit', 'converted', '140')])
async def test_negotiated_price_reaches_only_canonical_payment_once(r1_client, world, method, hold_state, balance):
    """Existing payment semantics, not a new commercial-credit approval claim."""
    from decimal import Decimal
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source)).json()['data']
    accepted = await decide(r1_client, world, source, proposal)
    assert accepted.status_code == 200
    new_id = accepted.json()['data']['accepted_order_id']
    assert (await r1_client.post(f'/api/v1/orders/{new_id}/confirm', headers=headers(world))).status_code == 200
    key = str(uuid4())
    body = {'amount': '140', 'method': method}
    result = await r1_client.post(f'/api/v1/orders/{new_id}/pay', json=body, headers=headers(world, key=key))
    assert result.status_code == 200, 'S3_NEGOTIATED_TOTAL_CANONICAL_PAYMENT'
    before = await economics(world)
    replay = await r1_client.post(f'/api/v1/orders/{new_id}/pay', json=body, headers=headers(world, key=key))
    assert replay.status_code == 200 and replay.json()['data']['payment_id'] == result.json()['data']['payment_id']
    assert await economics(world) == before, 'S3_CANONICAL_PAYMENT_REPLAY_ONCE'
    assert before['payments'] == 1 and before['binding'] == Decimal(balance)
    async with world['session']() as db:
        hold = (await db.execute(text('SELECT status,remaining_amount FROM order_credit_holds WHERE order_id=:id'), {'id': UUID(new_id)})).one()
        payment = (await db.execute(text('SELECT method,amount FROM payments WHERE order_id=:id'), {'id': UUID(new_id)})).one()
        assert tuple(hold) == (hold_state, Decimal('0'))
        assert tuple(payment) == (method, Decimal('140'))


@pytest.mark.parametrize('spelling', ['uppercase', 'compact', 'urn', 'braces'])
async def test_alternate_uuid_request_rechecks_live_authority(r1_client, world, spelling):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source)).json()['data']

    def render(value):
        parsed = UUID(value)
        return {'uppercase': str(parsed).upper(), 'compact': parsed.hex,
                'urn': parsed.urn, 'braces': '{'+str(parsed)+'}'}[spelling]

    path = f"/api/v1/client/orders/{render(source['id'])}/negotiations/{render(proposal['id'])}/accept"
    body = {'version': proposal['version'], 'digest': proposal['digest']}
    key = str(uuid4())
    warm = await r1_client.post(path, json=body, headers=headers(world, client=True, key=key))
    assert warm.status_code == 200, 'S3_ALTERNATE_UUID_IS_A_VALID_ROUTE'
    async with world['session']() as db:
        await db.execute(text("DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE name='retailer_operator') AND permission_id IN (SELECT id FROM permissions WHERE code='client:orders:create')"))
        await db.commit()
    before = await economics(world)
    replay = await r1_client.post(path, json=body, headers=headers(world, client=True, key=key))
    assert replay.status_code == 403, 'S3_ALTERNATE_UUID_NEVER_CACHES_LIVE_CONSENT_AUTHORITY'
    assert replay.headers.get('X-Idempotency-Replayed') is None
    assert await economics(world) == before
