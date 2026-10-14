"""Product-issued JWT over real TCP + READ ONLY PG economic projections.

Sample mapping: RO01/RO03/RO08 use the vertical source projection; later
cases exercise RO02-RO11 and NR06. UI RO12 belongs to the browser envelope.
"""
import asyncio
from decimal import Decimal
import uuid

import httpx
import pytest

from tests.s2_reorder.support import (
    assert_zero_draft_effects, count_intent, decisions, submit_body, submit_reorder, vector_for,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
async def test_ro01_ro03_ro08_vertical_preview_all_lines_new_zero_effect_draft(live):
    first = await live.create_product('vertical-one', price='90')
    second = await live.create_product('vertical-two', price='50')
    source = await live.create_source([live.item(first, 2), live.item(second, 1)])
    await live.set_base(first, '110')
    before = await vector_for(live, [source['id']], [first, second], label=live.country + '-vertical-before')
    preview = await live.reorder_preview(source['id'])
    repeated = await live.reorder_preview(source['id'])
    assert len(preview['rows']) == 2, 'S2_NO_SILENT_ORIGINAL_LINE_DROP'
    assert [row['source_item_id'] for row in preview['rows']] == sorted(row['id'] for row in before['items'])
    assert preview['order_basis'] == 'HISTORICAL_ITEM_ID'
    assert preview['ready'] and repeated['ready']
    assert preview['historical_currency'] == preview['current_currency'] == live.currency
    assert preview['historical_total'] == ('230' if live.country == 'UG' else '230.00')
    assert preview['current_total'] == ('270' if live.country == 'UG' else '270.00')
    assert preview['delta'] == ('40' if live.country == 'UG' else '40.00')
    assert await vector_for(live, [source['id']], [first, second]) == before, 'S2_PREVIEW_ZERO_WRITES'
    result = await live.api('POST', '/api/v1/client/orders', {**submit_body(preview), 'source_order_id': source['id']},
        expected=201, headers={'X-Idempotency-Key': 's2-vertical-' + uuid.uuid4().hex})
    assert result['id'] != source['id']
    assert result['source_order_id'] == source['id'] and result['replaces_order_id'] is None
    assert isinstance(result['total_amount'], str), 'S2_HTTP_EXACT_AMOUNT_STRING'
    assert Decimal(result['total_amount']) == Decimal(preview['current_total'])
    new = await vector_for(live, [result['id']], [first, second], label=live.country + '-vertical-new')
    # The economic array checks precede status checks so a real accidental
    # confirmation is detected by its reservations/holds, not only its label.
    assert_zero_draft_effects(new)
    assert result['status'] == 'CREATED'
    assert await vector_for(live, [source['id']], [first, second], label=live.country + '-vertical-source-after') == before, 'S2_SOURCE_EVERY_RETAINED_FACT_UNCHANGED'
    for name in ('stocks', 'stock_movements', 'binding'):
        assert new[name] == before[name], 'S2_ZERO_' + name.upper() + '_CHANGE'
    audit = new['orders'][0]['quote_resolved']
    if isinstance(audit, str):
        import json
        audit = json.loads(audit)
    assert audit['reorder']['version'] == 1
    assert audit['reorder']['source_order_id'] == source['id']
    assert audit['reorder']['selections'] == decisions(preview)


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
@pytest.mark.parametrize('current_price,delta', [('90', '0'), ('110', '40'), ('80', '-20')])
async def test_ro02_ro03_ro04_current_price_unchanged_rise_fall_requires_explicit_acceptance(live, current_price, delta):
    product = await live.create_product('price-comparison', price='90')
    source = await live.create_source([live.item(product, 2)])
    await live.set_base(product, current_price)
    preview = await live.reorder_preview(source['id'])
    assert preview['ready'] and len(preview['rows']) == 1
    assert Decimal(preview['historical_total']) == Decimal('180')
    assert Decimal(preview['current_total']) == Decimal(current_price) * 2
    assert Decimal(preview['delta']) == Decimal(delta)
    assert preview['quote']['currency'] == preview['historical_currency'] == live.currency
    before = await vector_for(live, [source['id']], [product])
    response = await submit_reorder(live, source, preview)
    result = response.json()['data']
    assert Decimal(result['total_amount']) == Decimal(current_price) * 2
    assert await vector_for(live, [source['id']], [product]) == before
    assert_zero_draft_effects(await vector_for(live, [result['id']], [product]))


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
async def test_ro05_unavailable_stays_visible_old_consent_refused_explicit_remove(live):
    good = await live.create_product('visible-good', price='90')
    bad = await live.create_product('visible-inactive', price='50')
    source = await live.create_source([live.item(good, 2), live.item(bad, 1)])
    original_quote = await live.reorder_preview(source['id'])
    await live.set_active(bad, False)
    before = await vector_for(live, [source['id']], [good, bad])
    preview = await live.reorder_preview(source['id'])
    assert len(preview['rows']) == 2, 'S2_UNAVAILABLE_ORIGINAL_ROW_MUST_REMAIN_VISIBLE'
    assert not preview['ready'] and preview['quote'] is None and preview['current_total'] is None
    unavailable = next(row for row in preview['rows'] if row['original']['sellable_unit_id'] == bad['sku_id'])
    assert unavailable['status'] == 'UNAVAILABLE' and unavailable['reason'] == 'SELLABLE_UNIT_UNAVAILABLE'
    assert unavailable['original']['subtotal'] == ('50' if live.country == 'UG' else '50.00')
    key = 's2-unavailable-' + uuid.uuid4().hex
    stale = await submit_reorder(live, source, original_quote, key=key, expected=409)
    assert stale.json()['code'] == 'SELLABLE_UNIT_UNAVAILABLE'
    assert await count_intent(live, key) == 0
    assert await vector_for(live, [source['id']], [good, bad]) == before
    selected = [{'source_item_id': row['source_item_id'],
                 'action': 'remove' if row['source_item_id'] == unavailable['source_item_id'] else 'keep'}
                for row in preview['rows']]
    resolved = await live.reorder_preview(source['id'], selected)
    assert resolved['ready'] and len(resolved['rows']) == 2
    removed = next(row for row in resolved['rows'] if row['source_item_id'] == unavailable['source_item_id'])
    assert removed['status'] == 'REMOVED' and removed['current'] is None
    result = (await submit_reorder(live, source, resolved)).json()['data']
    assert Decimal(result['total_amount']) == Decimal('180')
    assert len(result['items']) == 1
    assert await vector_for(live, [source['id']], [good, bad]) == before
    assert_zero_draft_effects(await vector_for(live, [result['id']], [good, bad]))


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
async def test_ro05_missing_price_explicit_replacement_is_unavailable_not_zero(live):
    original = await live.create_product('missing-price-original', price='90')
    unpriced = await live.create_product('missing-price-target', price=None)
    source = await live.create_source([live.item(original)])
    baseline = await live.reorder_preview(source['id'])
    selected = [{'source_item_id': baseline['rows'][0]['source_item_id'], 'action': 'replace',
                 'sellable_unit_id': unpriced['sku_id'], 'quantity': 2}]
    before = await vector_for(live, [source['id']], [original, unpriced])
    preview = await live.reorder_preview(source['id'], selected)
    assert len(preview['rows']) == 1 and preview['rows'][0]['reason'] == 'BASE_PRICE_REQUIRED'
    assert preview['rows'][0]['current'] is None and preview['quote'] is None
    assert preview['current_total'] is None and not preview['ready']
    assert await vector_for(live, [source['id']], [original, unpriced]) == before


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
async def test_ro09_price_change_same_total_rejects_every_changed_economic_line(live):
    first = await live.create_product('equal-total-one', price='90')
    second = await live.create_product('equal-total-two', price='50')
    source = await live.create_source([live.item(first, 1), live.item(second, 1)])
    accepted = await live.reorder_preview(source['id'])
    await live.set_base(first, '100')
    await live.set_base(second, '40')
    before = await vector_for(live, [source['id']], [first, second])
    key = 's2-equal-total-' + uuid.uuid4().hex
    response = await submit_reorder(live, source, accepted, key=key, expected=409)
    assert response.json()['code'] == 'REORDER_PREVIEW_STALE'
    details = response.json()['details']
    assert Decimal(details['old_total']) == Decimal(details['new_total']) == Decimal('140')
    assert Decimal(details['delta']) == 0
    assert {line['unit_price'] for line in details['quote']['lines']} != {line['unit_price'] for line in accepted['quote']['lines']}
    assert await count_intent(live, key) == 0
    assert await vector_for(live, [source['id']], [first, second]) == before
    refreshed = await live.reorder_preview(source['id'])
    result = (await submit_reorder(live, source, refreshed, key=key)).json()['data']
    assert_zero_draft_effects(await vector_for(live, [result['id']], [first, second]))


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
async def test_ro09_aba_revision_source_label_changes_same_economics_need_no_extra_acceptance(live):
    product = await live.create_product('aba', price='90')
    source = await live.create_source([live.item(product)])
    accepted = await live.reorder_preview(source['id'])
    await live.set_base(product, '110')
    await live.set_base(product, '90')
    # Same-value override changes source/base-vs-override audit, not economics.
    await live.api('PUT', '/api/v1/pricing/prices', {
        'retailer_id': live.account['retailer'], 'sku_id': product['sku_id'],
        'price': '90', 'expected_revision': product['revision']}, merchant=True)
    await live.api('PUT', f"/api/v1/catalog-products/{product['product_id']}/sellable-units/{product['sku_id']}",
                   {'display_label': 'Updated harmless display label'}, merchant=True)
    before = await vector_for(live, [source['id']], [product])
    result = (await submit_reorder(live, source, accepted)).json()['data']
    assert Decimal(result['total_amount']) == Decimal('180')
    new = await vector_for(live, [result['id']], [product])
    assert_zero_draft_effects(new)
    import json
    seen, resolved = new['orders'][0]['quote_seen'], new['orders'][0]['quote_resolved']
    seen = json.loads(seen) if isinstance(seen, str) else seen
    resolved = json.loads(resolved) if isinstance(resolved, str) else resolved
    assert resolved['lines'][0]['revision'] > seen['lines'][0]['revision']
    assert resolved['lines'][0]['source'] != seen['lines'][0]['source']
    assert await vector_for(live, [source['id']], [product]) == before


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
async def test_ro10_independent_tcp_clients_same_key_one_draft_replay_and_conflicts(live):
    product = await live.create_product('concurrent', price='90')
    source = await live.create_source([live.item(product)])
    preview = await live.reorder_preview(source['id'])
    body = {**submit_body(preview), 'source_order_id': source['id']}
    key = 's2-concurrent-' + uuid.uuid4().hex
    before = await vector_for(live, [source['id']], [product])
    ready = asyncio.Event()
    async def one_independent_request():
        async with httpx.AsyncClient(base_url=live.env['BACKEND_BASE_URL'], trust_env=False, timeout=35) as client:
            await ready.wait()
            return await client.post('/api/v1/client/orders', json=body,
                headers={**live.client_headers, 'X-Idempotency-Key': key})
    tasks = [asyncio.create_task(one_independent_request()) for _ in range(2)]
    ready.set()
    responses = await asyncio.gather(*tasks)
    assert [response.status_code for response in responses] == [201, 201]
    ids = [response.json()['data']['id'] for response in responses]
    assert ids[0] == ids[1], 'S2_CONCURRENT_ONE_PERSISTENT_RESULT'
    assert await count_intent(live, key) == 1
    assert await vector_for(live, [source['id']], [product]) == before
    assert_zero_draft_effects(await vector_for(live, [ids[0]], [product]))
    await live.set_base(product, '110')
    # This models a lost response: resend original accepted body/key, fresh TCP.
    replay = await submit_reorder(live, source, preview, key=key)
    assert replay.json()['data']['id'] == ids[0]
    assert Decimal(replay.json()['data']['total_amount']) == Decimal('180')
    different_notes = submit_body(preview, notes='Different explicit purchase intent')
    conflict = await submit_reorder(live, source, preview, key=key, body=different_notes, expected=409)
    assert conflict.json()['code'] == 'ORDER_CREATE_IDEMPOTENCY_CONFLICT'
    other_source = await live.create_source([live.item(product)])
    other_quote = await live.reorder_preview(other_source['id'])
    other_conflict = await submit_reorder(live, other_source, other_quote, key=key, expected=409)
    assert other_conflict.json()['code'] == 'ORDER_CREATE_IDEMPOTENCY_CONFLICT'
    separate = (await submit_reorder(live, source, await live.reorder_preview(source['id']))).json()['data']
    assert separate['id'] != ids[0], 'S2_SOURCE_CAN_BE_REORDERED_WITH_NEW_EXPLICIT_INTENT'


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
async def test_ro10_same_economic_lines_different_original_decisions_conflict(live):
    first = await live.create_product('decision-one', price='90')
    second = await live.create_product('decision-two', price='50')
    source = await live.create_source([live.item(first, 2), live.item(second, 1)])
    base = await live.reorder_preview(source['id'])
    first_row = next(row for row in base['rows'] if row['original']['sellable_unit_id'] == first['sku_id'])
    second_row = next(row for row in base['rows'] if row['original']['sellable_unit_id'] == second['sku_id'])
    one = [{'source_item_id': first_row['source_item_id'], 'action': 'keep'},
           {'source_item_id': second_row['source_item_id'], 'action': 'remove'}]
    two = [{'source_item_id': first_row['source_item_id'], 'action': 'remove'},
           {'source_item_id': second_row['source_item_id'], 'action': 'replace',
            'sellable_unit_id': first['sku_id'], 'quantity': 2}]
    q1, q2 = await live.reorder_preview(source['id'], one), await live.reorder_preview(source['id'], two)
    assert q1['current_total'] == q2['current_total']
    assert q1['quote']['lines'] == q2['quote']['lines'], 'S2_CONFLICT_CASE_HAS_IDENTICAL_CURRENT_ECONOMICS'
    key = 's2-decisions-' + uuid.uuid4().hex
    await submit_reorder(live, source, q1, key=key)
    response = await submit_reorder(live, source, q2, key=key, expected=409)
    assert response.json()['code'] == 'ORDER_CREATE_IDEMPOTENCY_CONFLICT'
    assert await count_intent(live, key) == 1


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
async def test_no_silent_omission_duplicate_selected_units_or_all_removed_submission(live):
    first = await live.create_product('selection-one', price='90')
    second = await live.create_product('selection-two', price='50')
    source = await live.create_source([live.item(first, 2), live.item(second, 1)])
    base = await live.reorder_preview(source['id'])
    original = decisions(base)
    response = await live.request('POST', f"/api/v1/client/orders/{source['id']}/reorder/quote",
                                  {'selections': original[:1]}, expected=422)
    assert response.json()['code'] == 'REORDER_SELECTION_INVALID'
    first_row = next(row for row in base['rows'] if row['original']['sellable_unit_id'] == first['sku_id'])
    second_row = next(row for row in base['rows'] if row['original']['sellable_unit_id'] == second['sku_id'])
    duplicate = [{'source_item_id': first_row['source_item_id'], 'action': 'keep'},
                 {'source_item_id': second_row['source_item_id'], 'action': 'replace',
                  'sellable_unit_id': first['sku_id'], 'quantity': 1}]
    preview = await live.reorder_preview(source['id'], duplicate)
    assert len(preview['rows']) == 2 and all(row['reason'] == 'QUOTE_DUPLICATE_LINE' for row in preview['rows'])
    assert not preview['ready'] and preview['quote'] is None
    removed = [{'source_item_id': row['source_item_id'], 'action': 'remove'} for row in base['rows']]
    empty = await live.reorder_preview(source['id'], removed)
    assert not empty['ready'] and empty['quote'] is None
    key = 's2-all-removed-' + uuid.uuid4().hex
    rejected = await submit_reorder(live, source, base, key=key,
        body=submit_body(base, selections=removed), expected=422)
    assert rejected.json()['code'] == 'REORDER_EMPTY_SELECTION'
    assert await count_intent(live, key) == 0


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
async def test_nr06_shortage_preserves_quantity_zero_effects_confirmation_atomic_refusal(live):
    product = await live.create_product('shortage', price='100', stock='100')
    source = await live.create_source([live.item(product, 10)])
    await live.adjust_stock(product, '-94')
    preview = await live.reorder_preview(source['id'])
    assert preview['ready'] and preview['rows'][0]['stock_warning'] == 'INSUFFICIENT_STOCK'
    assert preview['rows'][0]['current']['quantity'] == 10 and Decimal(preview['current_total']) == Decimal('1000')
    assert not any('quantity_on_hand' in row or 'quantity_available' in row for row in preview['rows'])
    before = await vector_for(live, [source['id']], [product])
    result = (await submit_reorder(live, source, preview)).json()['data']
    assert result['items'][0]['quantity'] == 10 and Decimal(result['total_amount']) == Decimal('1000')
    new_before = await vector_for(live, [result['id']], [product])
    assert_zero_draft_effects(new_before)
    assert await vector_for(live, [source['id']], [product]) == before
    refused = await live.request('POST', f"/api/v1/orders/{result['id']}/confirm", merchant=True, expected=409)
    assert refused.json()['code'] == 'INSUFFICIENT_AVAILABLE_STOCK'
    assert await vector_for(live, [result['id']], [product]) == new_before, 'S2_SHORTAGE_CONFIRM_ZERO_PARTIAL_EFFECT'
    ordinary = await live.quote([live.item(product, 10)])
    invalid_flag = await live.request('POST', '/api/v1/client/orders',
        {'items': [live.item(product, 10)], 'quote_token': ordinary['quote_token'], 'allow_shortage': True},
        headers={'X-Idempotency-Key': 's2-invalid-flag-' + uuid.uuid4().hex}, expected=422)
    assert invalid_flag.status_code == 422, 'S2_NO_HTTP_SHORTAGE_BYPASS_FLAG'
    normal = await live.request('POST', '/api/v1/client/orders',
        {'items': [live.item(product, 10)], 'quote_token': ordinary['quote_token']},
        headers={'X-Idempotency-Key': 's2-normal-stock-' + uuid.uuid4().hex}, expected=400)
    assert normal.json()['code'] == 'ORDER_VALIDATION_FAILED', 'S2_ORDINARY_CREATE_STOCK_GATE_RETAINED'
