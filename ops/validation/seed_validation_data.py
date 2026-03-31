"""Seed script for Phase 3 runtime validation"""
import asyncio
import os
from uuid import uuid4
from decimal import Decimal

os.environ['MPANGO_ENV'] = 'production'

from database.session import AsyncSessionLocal, get_tenant_db, create_tenant_schema
from sqlalchemy import text
from models import Wholesaler, Retailer
from models.sku import SKU
from models.inventory_stock import InventoryStock
from models.retailer_price import RetailerPrice

async def seed():
    async with AsyncSessionLocal() as session:
        # Set public schema for initial operations
        await session.execute(text('SET search_path TO public'))

        # Generate unique suffix for this run
        run_id = str(uuid4())[:8]

        # 1. Create Wholesaler
        wholesaler = Wholesaler(
            id=uuid4(),
            code=f'WHOLE{run_id}',
            name='Test Wholesaler',
            address='Test Address',
            contact='admin@wholesale.com',
            plan_type='standard'
        )
        session.add(wholesaler)
        await session.flush()
        print(f'Created wholesaler: {wholesaler.id}')

        # 2. Create Retailer
        retailer = Retailer(
            id=uuid4(),
            name='Test Retailer',
            phone=f'+254{run_id}',
            email='retailer@test.com',
            address='Test Location'
        )
        session.add(retailer)
        await session.flush()
        print(f'Created retailer: {retailer.id}')

        # 3. Create binding using raw SQL (outstanding_balance field required by DB but not in model)
        binding_id = uuid4()
        await session.execute(
            text('''
                INSERT INTO public.wholesaler_retailer_bindings
                (id, wholesaler_id, retailer_id, status, outstanding_balance, created_at, updated_at, is_deleted)
                VALUES (:id, :wholesaler_id, :retailer_id, :status, :outstanding_balance, NOW(), NOW(), FALSE)
            '''),
            {
                'id': binding_id,
                'wholesaler_id': wholesaler.id,
                'retailer_id': retailer.id,
                'status': 'active',
                'outstanding_balance': 0.00
            }
        )
        await session.commit()
        print(f'Created binding: {binding_id}')

        # 4. Create tenant schema and set it
        tenant_schema = 't_test_whole01'
        await create_tenant_schema(tenant_schema)
        await session.commit()

        # 5. Create SKUs in tenant schema
        tenant_session_gen = get_tenant_db(tenant_schema)
        tenant_session = await tenant_session_gen.__anext__()
        try:
            # SKU 1 - Sugar (priced)
            sku1 = SKU(
                id=uuid4(),
                sku_code='SUGAR001',
                name='Premium Sugar 1kg',
                category='Food',
                unit='kg',
                description='High quality sugar'
            )
            tenant_session.add(sku1)

            # SKU 2 - Rice (priced)
            sku2 = SKU(
                id=uuid4(),
                sku_code='RICE001',
                name='Basmati Rice 5kg',
                category='Food',
                unit='bag',
                description='Premium basmati rice'
            )
            tenant_session.add(sku2)

            # SKU 3 - Unpriced Product
            sku3 = SKU(
                id=uuid4(),
                sku_code='FLOUR001',
                name='Wheat Flour 2kg',
                category='Food',
                unit='bag',
                description='All purpose flour'
            )
            tenant_session.add(sku3)

            await tenant_session.flush()
            print(f'Created SKUs: {sku1.id}, {sku2.id}, {sku3.id}')

            # 6. Create inventory stocks (all in stock)
            stock1 = InventoryStock(
                id=uuid4(),
                sku_id=sku1.id,
                quantity_on_hand=100
            )
            stock2 = InventoryStock(
                id=uuid4(),
                sku_id=sku2.id,
                quantity_on_hand=50
            )
            stock3 = InventoryStock(
                id=uuid4(),
                sku_id=sku3.id,
                quantity_on_hand=75
            )
            tenant_session.add_all([stock1, stock2, stock3])
            await tenant_session.flush()
            print('Created inventory stocks')

            # 7. Create retailer prices for 2 SKUs (NOT for sku3 - unpriced)
            price1 = RetailerPrice(
                id=uuid4(),
                retailer_id=retailer.id,
                sku_id=sku1.id,
                price=Decimal('150.00')  # 150 KES for sugar
            )
            price2 = RetailerPrice(
                id=uuid4(),
                retailer_id=retailer.id,
                sku_id=sku2.id,
                price=Decimal('550.00')  # 550 KES for rice
            )
            tenant_session.add_all([price1, price2])
            # Note: sku3 has NO retailer price - it should be unpriced

            await tenant_session.commit()
            print(f'Created retailer prices for 2 SKUs')
            print(f'SKU1 (Sugar): {price1.price}')
            print(f'SKU2 (Rice): {price2.price}')
            print(f'SKU3 (Flour): NO PRICE (unpriced)')
            print('\nSeed complete!')

            result = {
                'wholesaler_id': str(wholesaler.id),
                'retailer_id': str(retailer.id),
                'sku1_id': str(sku1.id),
                'sku2_id': str(sku2.id),
                'sku3_id': str(sku3.id),
                'tenant_schema': tenant_schema
            }
        except Exception as e:
            await tenant_session.rollback()
            raise
        finally:
            await tenant_session.close()

        return result

if __name__ == '__main__':
    result = asyncio.run(seed())
    print(f"\nSeeded IDs: {result}")
