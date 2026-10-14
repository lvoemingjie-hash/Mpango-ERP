"""Live source/actor/binding authority, including actual completed cache hits."""
import datetime
import json
from uuid import UUID
import uuid

import asyncpg
import pytest

from tests.s2_reorder.support import (
    controlled_history_setup, count_intent, submit_body, submit_reorder, vector_for,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
async def test_ro11_cross_tenant_and_other_retailer_sources_neutral_404(live):
    from s2_fixture_api import FixtureAPI
    other_country = 'KE' if live.country == 'UG' else 'UG'
    async with FixtureAPI(other_country) as foreign:
        product = await foreign.create_product('foreign-scope', price='90')
        source = await foreign.create_source([foreign.item(product)])
        preview = await foreign.reorder_preview(source['id'])
        before = await vector_for(foreign, [source['id']], [product])
        refused_preview = await live.request('POST', f"/api/v1/client/orders/{source['id']}/reorder/quote", {}, expected=404)
        refused_submit = await submit_reorder(live, source, preview, expected=404)
        assert refused_preview.json()['code'] == refused_submit.json()['code'] == 'ORDER_NOT_FOUND'
        assert refused_preview.json()['message'] == refused_submit.json()['message'] == 'Order not found'
        assert await vector_for(foreign, [source['id']], [product]) == before
    # A second retailer is registered through the real invitation/product
    # registration API; no fabricated JWT or SQL auth identity is needed.
    invitation = await live.api('POST', '/api/v1/invitations', {}, merchant=True, expected=201)
    registered = await live.api('POST', '/api/v1/retailers/register', {
        'invitation_code': invitation['code'],
        'phone': ('256' if live.country == 'UG' else '254') + str(uuid.uuid4().int)[:9],
        'name': 'S2 distinct source retailer', 'email': 's2-other-' + uuid.uuid4().hex + '@example.com'}, expected=201)
    retailer = registered['retailer']['id']
    own_product = await live.create_product('other-retailer', price='90')
    items = [live.item(own_product)]
    quote = await live.api('POST', '/api/v1/orders/quote', {'items': items, 'retailer_id': retailer}, merchant=True)
    owned_elsewhere = await live.api('POST', '/api/v1/orders', {
        'items': items, 'retailer_id': retailer, 'quote_token': quote['quote_token']}, merchant=True,
        headers={'X-Idempotency-Key': 's2-other-source-' + uuid.uuid4().hex}, expected=201)
    rejected = await live.request('POST', f"/api/v1/client/orders/{owned_elsewhere['id']}/reorder/quote", {}, expected=404)
    assert rejected.json()['code'] == 'ORDER_NOT_FOUND'
    own_source = await live.create_source(items)
    own_preview = await live.reorder_preview(own_source['id'])
    rejected_submit = await submit_reorder(live, owned_elsewhere, own_preview, expected=404)
    assert rejected_submit.json()['code'] == 'ORDER_NOT_FOUND'


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
async def test_ro11_completed_cache_replay_rechecks_source_evidence_and_visibility(live):
    product = await live.create_product('cached-source', price='90')
    source = await live.create_source([live.item(product)])
    preview = await live.reorder_preview(source['id'])
    key = 's2-cached-source-' + uuid.uuid4().hex
    created = await submit_reorder(live, source, preview, key=key)
    result = created.json()['data']
    cached = await submit_reorder(live, source, preview, key=key)
    assert cached.headers.get('X-Idempotency-Replayed') == 'true', 'S2_CASE_REALLY_TRAVERSED_COMPLETED_CACHE'
    assert cached.json()['data']['id'] == result['id']
    original_unit = preview['rows'][0]['original']['unit']
    item_id = preview['rows'][0]['source_item_id']
    try:
        await controlled_history_setup(live, 'UPDATE order_items SET unit_snapshot=$1 WHERE id=$2 AND order_id=$3',
            'Changed historical proof', UUID(item_id), UUID(source['id']),
            reason='DECLARED_HISTORY_FIXTURE: test-owned source identity evidence changes after committed cache result')
        before = await vector_for(live, [source['id'], result['id']], [product])
        refused = await submit_reorder(live, source, preview, key=key, expected=409)
        assert refused.json()['code'] == 'QUOTE_CONTEXT_CHANGED', 'S2_CACHE_CANNOT_BYPASS_CURRENT_SOURCE_PROOF'
        assert await count_intent(live, key) == 1
        assert await vector_for(live, [source['id'], result['id']], [product]) == before
    finally:
        await controlled_history_setup(live, 'UPDATE order_items SET unit_snapshot=$1 WHERE id=$2 AND order_id=$3',
            original_unit, UUID(item_id), UUID(source['id']),
            reason='DECLARED_HISTORY_FIXTURE: restore test-owned source historical proof after cached-replay negative control')
    try:
        await controlled_history_setup(live, 'UPDATE orders SET is_deleted=true WHERE id=$1', UUID(source['id']),
            reason='DECLARED_HISTORY_FIXTURE: test-owned source becomes invisible after committed cache result')
        invisible = await submit_reorder(live, source, preview, key=key, expected=404)
        assert invisible.json()['code'] == 'ORDER_NOT_FOUND', 'S2_CACHE_CANNOT_BYPASS_SOURCE_VISIBILITY'
        assert await count_intent(live, key) == 1
    finally:
        await controlled_history_setup(live, 'UPDATE orders SET is_deleted=false WHERE id=$1', UUID(source['id']),
            reason='DECLARED_HISTORY_FIXTURE: restore test-owned source visibility after negative control')


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
@pytest.mark.parametrize('field', ['quote_seen', 'quote_resolved', 'creation_fingerprint'])
async def test_ro10_completed_cache_replay_checks_persisted_source_and_fingerprint(live, field):
    product = await live.create_product('cached-persistent-proof', price='90')
    source = await live.create_source([live.item(product)])
    preview = await live.reorder_preview(source['id'])
    key = 's2-cache-proof-' + uuid.uuid4().hex
    new = (await submit_reorder(live, source, preview, key=key)).json()['data']
    cached = await submit_reorder(live, source, preview, key=key)
    assert cached.headers.get('X-Idempotency-Replayed') == 'true'
    original = (await vector_for(live, [new['id']], [product]))['orders'][0][field]
    changed = '0' * 64
    if field in ('quote_seen', 'quote_resolved'):
        payload = json.loads(original) if isinstance(original, str) else original.copy()
        payload['reorder']['source_order_id'] = str(uuid.uuid4())
        changed = json.dumps(payload)
    try:
        cast = '::jsonb' if field != 'creation_fingerprint' else ''
        await controlled_history_setup(live, 'UPDATE orders SET ' + field + '=$1' + cast + ' WHERE id=$2',
            changed, UUID(new['id']), reason='DECLARED_HISTORY_FIXTURE: test-owned committed draft ' + field + ' is inconsistent after completed cache warmup; no constraint or economic table changes')
        before = await vector_for(live, [source['id'], new['id']], [product])
        refused = await submit_reorder(live, source, preview, key=key, expected=409)
        assert refused.json()['code'] == 'ORDER_CREATE_IDEMPOTENCY_CONFLICT', 'S2_CACHE_MUST_VALIDATE_DURABLE_' + field.upper()
        assert await vector_for(live, [source['id'], new['id']], [product]) == before
        assert await count_intent(live, key) == 1
    finally:
        cast = '::jsonb' if field != 'creation_fingerprint' else ''
        if field != 'creation_fingerprint' and not isinstance(original, str):
            original = json.dumps(original)
        await controlled_history_setup(live, 'UPDATE orders SET ' + field + '=$1' + cast + ' WHERE id=$2',
            original, UUID(new['id']), reason='DECLARED_HISTORY_FIXTURE: restore exact committed acceptance metadata/fingerprint after cache negative control')


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
async def test_ro11_binding_deactivation_refuses_first_submit_and_committed_cached_replay(live):
    product = await live.create_product('binding-live', price='90')
    source = await live.create_source([live.item(product)])
    preview = await live.reorder_preview(source['id'])
    key = 's2-binding-replay-' + uuid.uuid4().hex
    created = (await submit_reorder(live, source, preview, key=key)).json()['data']
    cached = await submit_reorder(live, source, preview, key=key)
    assert cached.headers.get('X-Idempotency-Replayed') == 'true'
    before = await vector_for(live, [source['id'], created['id']], [product])
    binding = before['binding'][0]
    new_key = 's2-binding-first-' + uuid.uuid4().hex
    try:
        await live.api('POST', f"/api/v1/retailers/{live.account['retailer']}/deactivate", merchant=True)
        inactive = await vector_for(live, [source['id'], created['id']], [product])
        replay_refused = await submit_reorder(live, source, preview, key=key, expected=403)
        first_refused = await submit_reorder(live, source, preview, key=new_key, expected=403)
        assert replay_refused.json()['code'] == first_refused.json()['code'] == 'BINDING_NOT_ACTIVE'
        assert await count_intent(live, key) == 1 and await count_intent(live, new_key) == 0
        assert await vector_for(live, [source['id'], created['id']], [product]) == inactive, 'S2_REVOKED_ATTEMPTS_ZERO_ECONOMIC_WRITES'
    finally:
        # There is no product reactivation endpoint. Exact task-owned fixture
        # cleanup restores the captured status/updated_at only, never balances
        # or finance rows; revoke itself was the real product command.
        connection = await asyncpg.connect(live.env['APP_DB_DSN'])
        try:
            async with connection.transaction():
                await connection.execute('UPDATE public.wholesaler_retailer_bindings SET status=$1,updated_at=$2 '
                    'WHERE id=$3 AND wholesaler_id=$4 AND retailer_id=$5', binding['status'],
                    datetime.datetime.fromisoformat(binding['updated_at']), UUID(binding['id']),
                    UUID(live.account['wholesaler']), UUID(live.account['retailer']))
        finally:
            await connection.close()
    assert await vector_for(live, [source['id'], created['id']], [product]) == before, 'S2_BINDING_FIXTURE_EXACT_RESTORE'
