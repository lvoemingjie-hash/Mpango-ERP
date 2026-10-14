"""Non-empty source economic facts arise solely through canonical product APIs."""
import json
from decimal import Decimal
import uuid

import pytest

from tests.s2_reorder.support import assert_zero_draft_effects, submit_reorder, vector_for

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
async def test_ro08_nonempty_source_payments_declaration_hold_reservation_ledger_movement_unchanged(live):
    product = await live.create_product('real-economic-source', price='90', stock='100')
    source = await live.create_source([live.item(product, 2)], client=False)
    await live.api('POST', f"/api/v1/orders/{source['id']}/confirm", merchant=True)
    await live.api('POST', f"/api/v1/orders/{source['id']}/pay", {'method': 'cash', 'amount': '50'},
        merchant=True, headers={'X-Idempotency-Key': 's2-source-partial-' + uuid.uuid4().hex})
    await live.api('POST', f"/api/v1/client/orders/{source['id']}/declare", {'method': 'cash', 'declared_amount': '30'},
        headers={'X-Declaration-Idempotency-Key': 's2-source-declare-' + uuid.uuid4().hex}, expected=201)
    await live.set_base(product, '110')
    partial_before = await vector_for(live, [source['id']], [product], label=live.country + '-nonempty-partial-before')
    for name in ('payments', 'declarations', 'holds', 'reservations'):
        assert len(partial_before[name]) > 0, 'S2_REAL_SOURCE_NONEMPTY_' + name.upper()
    assert partial_before['orders'][0]['status'] == 'partially_paid'
    assert Decimal(partial_before['orders'][0]['total_amount']) == Decimal('180')
    assert Decimal(partial_before['holds'][0]['remaining_amount']) == Decimal('130')
    partial_preview = await live.reorder_preview(source['id'])
    first_new = (await submit_reorder(live, source, partial_preview)).json()['data']
    first_vector = await vector_for(live, [first_new['id']], [product])
    assert_zero_draft_effects(first_vector)
    assert await vector_for(live, [source['id']], [product], label=live.country + '-nonempty-partial-after') == partial_before, 'S2_NONEMPTY_PARTIAL_SOURCE_FULL_FACTS_UNCHANGED'
    # Complete the same source through existing settlement/fulfillment, so a
    # retained order-owned movement is tested alongside the other source rows.
    await live.api('POST', f"/api/v1/orders/{source['id']}/pay", {'method': 'cash', 'amount': '130'},
        merchant=True, headers={'X-Idempotency-Key': 's2-source-remainder-' + uuid.uuid4().hex})
    await live.api('POST', f"/api/v1/orders/{source['id']}/fulfill", merchant=True)
    fulfilled_before = await vector_for(live, [source['id']], [product], label=live.country + '-nonempty-fulfilled-before')
    for name in ('payments', 'declarations', 'holds', 'reservations', 'ledger', 'order_movements'):
        assert len(fulfilled_before[name]) > 0, 'S2_FULFILLED_SOURCE_NONEMPTY_' + name.upper()
    assert fulfilled_before['orders'][0]['status'] == 'fulfilled'
    assert Decimal(fulfilled_before['orders'][0]['total_amount']) == Decimal('180')
    assert Decimal(fulfilled_before['holds'][0]['remaining_amount']) == 0
    assert Decimal(fulfilled_before['stocks'][0]['quantity_on_hand']) == Decimal('98')
    fulfilled_preview = await live.reorder_preview(source['id'])
    second_new = (await submit_reorder(live, source, fulfilled_preview)).json()['data']
    assert first_new['id'] != second_new['id']
    assert_zero_draft_effects(await vector_for(live, [second_new['id']], [product]))
    assert await vector_for(live, [source['id']], [product], label=live.country + '-nonempty-fulfilled-after') == fulfilled_before, 'S2_FULFILLED_SOURCE_EVERY_ECONOMIC_FACT_UNCHANGED'
    # Public-sized proof has dimensions/counts and routes; full retained rows
    # remain in private READ ONLY projections, with no credentials in either.
    from tests.s2_reorder.support import TASK_ROOT
    directory = TASK_ROOT / 'records' / 'evidence'
    directory.mkdir(exist_ok=True)
    proof = {'country': live.country, 'source': source['id'], 'new_drafts': [first_new['id'], second_new['id']],
             'sql_economic_seed_writes': 0, 'partial_dimension_counts': {name: len(partial_before[name]) for name in ('payments', 'declarations', 'holds', 'reservations', 'ledger', 'order_movements')},
             'fulfilled_nonempty_counts': {name: len(fulfilled_before[name]) for name in ('payments', 'declarations', 'holds', 'reservations', 'ledger', 'order_movements')},
             'canonical_source_route_actions': ['confirm', 'pay cash50', 'client declare cash30', 'pay cash130', 'fulfill'],
             'partial_source_full_vector_unchanged': True, 'fulfilled_source_full_vector_unchanged': True,
             'both_new_draft_economic_arrays_empty': True}
    (directory / ('nonempty-source-' + live.country + '-' + live.evidence_suffix + '.json')).write_text(json.dumps(proof, indent=2) + '\n')
