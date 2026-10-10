"""Original Phase-4 nodes on S1's explicit quote contract and real JWT/PG.

No business case was removed. Positives now preview before creating and use
versioned prices; missing-base/inactive/selector errors occur at preview.
The old positional SQL mocks cannot represent the shared locked resolver.
"""
from decimal import Decimal
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from tests.s1_pricing_quote.conftest import world, r1_client  # noqa: F401
from tests.s1_pricing_quote.test_http import facts, headers, preview, selection, submit


class TestSchemaRejectsPrice:
    def test_schema_rejects_unit_price_field(self):
        from schemas.order import WholesalerOrderItemCreate
        fields = WholesalerOrderItemCreate.model_fields
        assert 'unit_price' not in fields
        assert 'product_name' not in fields

    def test_schema_accepts_stable_identity_selector_and_quantity(self):
        from schemas.order import WholesalerOrderItemCreate
        assert set(WholesalerOrderItemCreate.model_fields) == {'sellable_unit_id', 'sku_code', 'quantity'}

    def test_extra_fields_ignored_or_rejected(self):
        from schemas.order import WholesalerOrderItemCreate
        item = WholesalerOrderItemCreate(sku_code='TEST-SKU', quantity=5)
        assert item.sku_code == 'TEST-SKU' and item.quantity == 5
        assert not hasattr(item, 'unit_price')

    def test_wholesaler_request_shape(self):
        from schemas.order import WholesalerOrderCreateRequest
        assert set(WholesalerOrderCreateRequest.model_fields) == {'retailer_id', 'items', 'notes', 'quote_token'}


async def change(world, sql, parameters=None):
    async with world['session']() as db:
        await db.execute(text(sql), parameters or {})
        await db.commit()


async def refused_preview(http, world, body, code, status):
    before = await facts(world)
    response = await http.post('/api/v1/orders/quote', json=body, headers=headers(world))
    assert response.status_code == status and response.json()['code'] == code
    assert await facts(world) == before
    return response


class TestWholesalerOrderCreationAPI:
    @pytest.mark.asyncio
    async def test_create_order_slim_shape_happy_path(self, r1_client, world):
        await change(world, 'UPDATE skus SET base_price=25.50 WHERE id=:id', {'id': uuid.UUID(world['sku'])})
        body = {'retailer_id': world['rid'], 'items': [{'sku_code': 'BOX', 'quantity': 3}]}
        response = await r1_client.post('/api/v1/orders/quote', json=body, headers=headers(world))
        assert response.status_code == 200
        response = await r1_client.post('/api/v1/orders', json={**body,
            'quote_token': response.json()['data']['quote_token']}, headers=headers(world, key=str(uuid.uuid4())))
        assert response.status_code == 201
        data = response.json()['data']
        assert Decimal(data['total_amount']) == Decimal('76.50')
        assert len(data['items']) == 1
        assert Decimal(data['items'][0]['unit_price']) == Decimal('25.50')
        assert data['items'][0]['product_name'] == 'S1 boxes'

    @pytest.mark.asyncio
    async def test_matching_stable_id_and_code_create_stable_snapshot(self, r1_client, world):
        response = await submit(r1_client, world, await preview(r1_client, world))
        assert response.status_code == 201
        item = response.json()['data']['items'][0]
        assert item['sellable_unit_id'] == world['sku']
        assert item['sku_code'] == 'BOX' and item['unit_snapshot'] == 'Box'
        assert item['identity_status'] == 'stable' and item['quantity'] == 2
        assert item['product_name'] == 'S1 boxes'
        assert Decimal(item['unit_price']) == Decimal('90.00')
        assert Decimal(item['subtotal']) == Decimal('180.00')

    @pytest.mark.asyncio
    @pytest.mark.parametrize('include_code_row', [True, False])
    async def test_stable_id_and_code_mismatch_fails_closed(self, r1_client, world, include_code_row):
        other = 'OTHER' if include_code_row else 'ABSENT'
        if include_code_row:
            await change(world, "INSERT INTO skus(sku_code,name,unit,package_quantity,catalog_product_id,base_price) "
                "VALUES('OTHER','Other','Box',12,:id,90)", {'id': uuid.UUID(world['product'])})
        await refused_preview(r1_client, world, {'retailer_id': world['rid'], 'items': [
            {'sellable_unit_id': world['sku'], 'sku_code': other, 'quantity': 2}]},
            'SELLABLE_UNIT_NOT_FOUND', 400)

    @pytest.mark.asyncio
    async def test_retailer_order_stable_id_and_code_mismatch_fails_closed(self, r1_client, world):
        before = await facts(world)
        response = await r1_client.post('/api/v1/client/orders/quote', json={'items': [
            {'sellable_unit_id': world['sku'], 'sku_code': 'ABSENT', 'quantity': 2}]},
            headers=headers(world, client=True))
        assert response.status_code == 400 and response.json()['code'] == 'SELLABLE_UNIT_NOT_FOUND'
        assert await facts(world) == before

    @pytest.mark.asyncio
    async def test_missing_price_returns_order_validation_failed(self, r1_client, world):
        await change(world, 'UPDATE skus SET base_price=NULL WHERE id=:id', {'id': uuid.UUID(world['sku'])})
        await refused_preview(r1_client, world, {'retailer_id': world['rid'], 'items': selection(world)},
                              'BASE_PRICE_REQUIRED', 409)

    @pytest.mark.asyncio
    async def test_unbound_retailer_returns_retailer_not_bound(self, r1_client, world):
        await refused_preview(r1_client, world, {'retailer_id': str(uuid.uuid4()), 'items': selection(world)},
                              'RETAILER_NOT_BOUND', 403)

    @pytest.mark.asyncio
    async def test_inactive_sku_returns_validation_failed(self, r1_client, world):
        await change(world, 'UPDATE skus SET is_active=false WHERE id=:id', {'id': uuid.UUID(world['sku'])})
        await refused_preview(r1_client, world, {'retailer_id': world['rid'], 'items': selection(world)},
                              'SELLABLE_UNIT_UNAVAILABLE', 409)

    @pytest.mark.asyncio
    async def test_insufficient_stock_returns_validation_failed(self, r1_client, world):
        await change(world, 'UPDATE inventory_stocks SET quantity_on_hand=1 WHERE sku_id=:id', {'id': uuid.UUID(world['sku'])})
        before = await facts(world)
        response = await submit(r1_client, world, await preview(r1_client, world))
        assert response.status_code == 400 and response.json()['code'] == 'ORDER_VALIDATION_FAILED'
        assert await facts(world) == before

    @pytest.mark.asyncio
    async def test_unknown_sku_returns_validation_failed(self, r1_client, world):
        await refused_preview(r1_client, world, {'retailer_id': world['rid'], 'items': [
            {'sku_code': 'ABSENT', 'quantity': 1}]}, 'SELLABLE_UNIT_NOT_FOUND', 400)


class TestPricingListAPI:
    @pytest.mark.asyncio
    async def test_list_prices_happy_path(self, r1_client, world):
        await change(world, "INSERT INTO skus(sku_code,name,unit,package_quantity,catalog_product_id,base_price) "
            "VALUES('SECOND','Second','Box',12,:id,30)", {'id': uuid.UUID(world['product'])})
        response = await r1_client.get('/api/v1/pricing/prices', params={'retailer_id': world['rid']},
                                       headers=headers(world))
        assert response.status_code == 200
        data = response.json()['data']
        assert data['total'] == 2 and len(data['items']) == 2
        row = next(item for item in data['items'] if item['sku_id'] == world['sku'])
        assert row['sku_id'] == world['sku'] and row['sku_code'] == 'BOX'
        assert row['price'] == '90.00' and row['currency'] == 'KES'
        assert next(item for item in data['items'] if item['sku_code'] == 'SECOND')['price'] == '30.00'

    @pytest.mark.asyncio
    async def test_list_prices_unbound_retailer_rejected(self, r1_client, world):
        response = await r1_client.get('/api/v1/pricing/prices', params={'retailer_id': str(uuid.uuid4())},
                                       headers=headers(world))
        assert response.status_code == 403 and response.json()['code'] == 'RETAILER_NOT_BOUND'


async def price_request(http, world, price='42.00', revision=0, sku=None, retailer=None):
    return await http.put('/api/v1/pricing/prices', json={
        'sku_id': sku or world['sku'], 'retailer_id': retailer or world['rid'],
        'price': price, 'expected_revision': revision}, headers=headers(world))


class TestPricingSetAPI:
    @pytest.mark.asyncio
    async def test_set_price_creates_new(self, r1_client, world):
        response = await price_request(r1_client, world)
        assert response.status_code == 200 and response.json()['data']['price'] == '42.00'
        async with world['session']() as db:
            assert (await db.execute(text('SELECT count(*) FROM retailer_prices'))).scalar_one() == 1

    @pytest.mark.asyncio
    async def test_set_price_updates_existing(self, r1_client, world):
        assert (await price_request(r1_client, world)).status_code == 200
        response = await price_request(r1_client, world, '99.00', 1)
        assert response.status_code == 200 and response.json()['data']['price'] == '99.00'
        async with world['session']() as db:
            assert (await db.execute(text('SELECT count(*) FROM retailer_prices'))).scalar_one() == 1

    @pytest.mark.asyncio
    async def test_set_price_unknown_sku_rejected(self, r1_client, world):
        response = await price_request(r1_client, world, sku=str(uuid.uuid4()))
        assert response.status_code == 404 and response.json()['code'] == 'SKU_NOT_FOUND'
        assert (await facts(world))['orders'] == 0

    @pytest.mark.asyncio
    async def test_set_price_unbound_retailer_rejected(self, r1_client, world):
        response = await price_request(r1_client, world, retailer=str(uuid.uuid4()))
        assert response.status_code == 403 and response.json()['code'] == 'RETAILER_NOT_BOUND'

    def test_set_price_schema_rejects_zero_price(self):
        from api.v1.pricing import SetPriceRequest
        with pytest.raises(ValidationError, match='positive decimal'):
            SetPriceRequest(retailer_id=uuid.uuid4(), sku_id=uuid.uuid4(), price='0', expected_revision=0)

    def test_set_price_schema_rejects_negative_price(self):
        from api.v1.pricing import SetPriceRequest
        with pytest.raises(ValidationError, match='positive decimal'):
            SetPriceRequest(retailer_id=uuid.uuid4(), sku_id=uuid.uuid4(), price='-5.00', expected_revision=0)
