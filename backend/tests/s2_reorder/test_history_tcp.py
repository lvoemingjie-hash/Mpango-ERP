"""Declared historical SQL fixtures; current catalog/price/stock via product API.

SQL setup modifies only the test-owned historical source snapshots/identity,
never financial facts, schema constraints, live price or inventory authority.
All proof vectors are separate PostgreSQL READ ONLY transactions.
"""
from decimal import Decimal
from uuid import UUID
import uuid

import pytest

from tests.s2_reorder.support import (
    assert_zero_draft_effects, controlled_history_setup, decisions,
    submit_reorder, vector_for,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
async def test_ro07_linked_legacy_with_complete_persisted_unit_evidence_is_usable(live):
    product = await live.create_product('linked-complete', price='90')
    source = await live.create_source([live.item(product)])
    preview = await live.reorder_preview(source['id'])
    item_id = preview['rows'][0]['source_item_id']
    await controlled_history_setup(live,
        "UPDATE order_items SET identity_status='linked_legacy' WHERE id=$1 AND order_id=$2",
        UUID(item_id), UUID(source['id']),
        reason='DECLARED_HISTORY_FIXTURE: stable product-created UUID/unit/package snapshots retained; mark historical authoritative linkage classification')
    before = await vector_for(live, [source['id']], [product])
    linked = await live.reorder_preview(source['id'])
    assert linked['rows'][0]['original']['identity_status'] == 'linked_legacy'
    assert linked['rows'][0]['original']['sellable_unit_id'] == product['sku_id']
    assert linked['ready'] and linked['rows'][0]['status'] == 'READY', 'S2_VERIFIED_LINKED_LEGACY_NOT_BLANKET_REFUSED'
    result = (await submit_reorder(live, source, linked)).json()['data']
    assert await vector_for(live, [source['id']], [product]) == before
    assert_zero_draft_effects(await vector_for(live, [result['id']], [product]))


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
@pytest.mark.parametrize('kind,reason', [
    ('null_id', 'LEGACY_IDENTITY_UNRESOLVED'),
    ('missing_unit', 'LEGACY_IDENTITY_UNRESOLVED'),
    ('missing_package', 'LEGACY_IDENTITY_UNRESOLVED'),
    ('different_package', 'PACKAGING_IDENTITY_CHANGED'),
    ('different_unit', 'PACKAGING_IDENTITY_CHANGED'),
])
async def test_ro06_ro07_unresolved_history_or_changed_unit_never_guessed_explicit_replace(live, kind, reason):
    product = await live.create_product('historical-' + kind, price='90')
    replacement = await live.create_product('new-legal-unit', price='110', package_quantity='6')
    source = await live.create_source([live.item(product)])
    original = await live.reorder_preview(source['id'])
    item_id = original['rows'][0]['source_item_id']
    if kind == 'different_package':
        forbidden = await live.request('PUT',
            f"/api/v1/catalog-products/{product['product_id']}/sellable-units/{product['sku_id']}",
            {'package_quantity': '6'}, merchant=True, expected=409)
        assert forbidden.json()['code'] == 'SKU_PACKAGE_QUANTITY_IMMUTABLE_AFTER_USE'
    updates = {
        'null_id': "identity_status='legacy',sellable_unit_id=NULL,unit_snapshot=NULL,package_quantity_snapshot=NULL",
        'missing_unit': "identity_status='linked_legacy',unit_snapshot=NULL",
        'missing_package': "identity_status='linked_legacy',package_quantity_snapshot=NULL",
        'different_package': "identity_status='linked_legacy',package_quantity_snapshot=6",
        'different_unit': "identity_status='linked_legacy',unit_snapshot='Case'",
    }
    await controlled_history_setup(live, 'UPDATE order_items SET ' + updates[kind] + ' WHERE id=$1 AND order_id=$2',
        UUID(item_id), UUID(source['id']), reason='DECLARED_HISTORY_FIXTURE: retained historical ' + kind + '; current SKU and every price/stock/economic table remain product-owned')
    before = await vector_for(live, [source['id']], [product, replacement])
    unavailable = await live.reorder_preview(source['id'])
    assert len(unavailable['rows']) == 1
    assert unavailable['rows'][0]['original']['sku_code'] == product['sku_code']
    assert unavailable['rows'][0]['reason'] == reason
    assert unavailable['rows'][0]['status'] == 'UNAVAILABLE'
    assert not unavailable['ready'] and unavailable['quote'] is None
    assert unavailable['current_total'] is None and unavailable['rows'][0]['current'] is None
    assert await vector_for(live, [source['id']], [product, replacement]) == before
    selected = [{'source_item_id': item_id, 'action': 'replace',
                 'sellable_unit_id': replacement['sku_id'], 'quantity': 2}]
    explicit = await live.reorder_preview(source['id'], selected)
    assert explicit['ready'] and Decimal(explicit['current_total']) == Decimal('220')
    assert explicit['rows'][0]['current']['quantity'] == 2
    assert Decimal(explicit['rows'][0]['current']['package_quantity']) == 6
    result = (await submit_reorder(live, source, explicit)).json()['data']
    assert result['items'][0]['sellable_unit_id'] == replacement['sku_id']
    assert result['items'][0]['quantity'] == 2 and Decimal(result['total_amount']) == 220
    assert await vector_for(live, [source['id']], [product, replacement]) == before
    assert_zero_draft_effects(await vector_for(live, [result['id']], [product, replacement]))


@pytest.mark.parametrize('live', ['UG', 'KE'], indirect=True)
async def test_ro01_unknown_historical_currency_remains_raw_no_fabricated_delta(live):
    product = await live.create_product('currency-unknown', price='90')
    source = await live.create_source([live.item(product)])
    await controlled_history_setup(live,
        'UPDATE orders SET currency_snapshot=NULL,country_snapshot=NULL,registration_snapshot_id=NULL,'
        'creation_key_digest=NULL,creation_fingerprint=NULL,creation_operation=NULL,quote_seen=NULL,quote_resolved=NULL '
        'WHERE id=$1 AND wholesaler_id=$2 AND retailer_id=$3',
        UUID(source['id']), UUID(live.account['wholesaler']), UUID(live.account['retailer']),
        reason='DECLARED_HISTORY_FIXTURE: retained pre-S1 order with NULL currency and absent quote/creation metadata, without bypassing any constraint')
    await live.set_base(product, '110')
    before = await vector_for(live, [source['id']], [product])
    preview = await live.reorder_preview(source['id'])
    assert preview['historical_currency'] is None
    assert preview['historical_currency_status'] == 'LEGACY_CURRENCY_UNVERIFIED'
    assert isinstance(preview['historical_total'], str) and Decimal(preview['historical_total']) == Decimal('180')
    assert preview['delta'] is None, 'S2_UNKNOWN_HISTORICAL_CURRENCY_NO_FAKE_DELTA'
    assert preview['ready'] and preview['quote']['currency'] == live.currency
    result = (await submit_reorder(live, source, preview)).json()['data']
    assert result['currency'] == live.currency and Decimal(result['total_amount']) == Decimal('220')
    assert await vector_for(live, [source['id']], [product]) == before


@pytest.mark.parametrize('live', ['UG'], indirect=True)
async def test_ro01_fractional_ugx_legacy_history_readable_current_strict_no_delta(live):
    product = await live.create_product('fractional-historical', price='90')
    source = await live.create_source([live.item(product)])
    await controlled_history_setup(live,
        "UPDATE orders SET total_amount=180.50,creation_key_digest=NULL,creation_fingerprint=NULL,"
        "creation_operation=NULL,quote_seen=NULL,quote_resolved=NULL WHERE id=$1",
        UUID(source['id']), reason='DECLARED_HISTORY_FIXTURE: retained UGX fractional history allowed by NUMERIC(12,2), with no creation-intent or finance seed')
    await controlled_history_setup(live,
        'UPDATE order_items SET unit_price=90.25,subtotal=180.50 WHERE order_id=$1',
        UUID(source['id']), reason='DECLARED_HISTORY_FIXTURE: consistent old quantity2 historical fractional snapshots, no live price or finance writes')
    before = await vector_for(live, [source['id']], [product])
    response = await live.request('POST', f"/api/v1/client/orders/{source['id']}/reorder/quote", {}, expected=200)
    preview = response.json()['data']
    assert len(preview['rows']) == 1 and preview['ready']
    assert preview['historical_total'] == '180.50'
    assert preview['rows'][0]['original']['unit_price'] == '90.25'
    assert preview['rows'][0]['original']['subtotal'] == '180.50'
    assert preview['quote']['currency'] == 'UGX' and preview['quote']['total'] == '180'
    assert preview['delta'] is None, 'S2_NONCANONICAL_HISTORICAL_PRECISION_NO_FAKE_DELTA'
    assert await vector_for(live, [source['id']], [product]) == before
