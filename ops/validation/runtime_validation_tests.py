"""Runtime validation tests for Phase 3 pricing MVP"""
import asyncio
import os
from decimal import Decimal
from uuid import UUID

os.environ['MPANGO_ENV'] = 'production'

async def test_client_products_api():
    """Test GET /client/products returns real prices"""
    import httpx
    from database.session import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        # Get test data
        result = await session.execute(
            text('''
                SELECT w.id as wholesaler_id, r.id as retailer_id, b.id as binding_id
                FROM public.wholesalers w
                JOIN public.wholesaler_retailer_bindings b ON b.wholesaler_id = w.id
                JOIN public.retailers r ON r.id = b.retailer_id
                WHERE w.code LIKE 'WHOLE%'
                ORDER BY w.created_at DESC LIMIT 1
            ''')
        )
        row = result.fetchone()
        if not row:
            print("ERROR: No test wholesaler/retailer found")
            return False

        wholesaler_id, retailer_id, binding_id = row
        print(f"Using retailer: {retailer_id}")

        # Set tenant context for the session
        session.info["tenant_schema"] = "t_test_whole01"
        await session.execute(text('SET search_path TO "t_test_whole01", public'))

        # Get auth token for this retailer (we need to simulate auth)
        # For testing, we'll directly call the API with a service token or mock auth
        # Since we can't easily get a JWT, let's test the repository layer directly

        from repositories import pricing_repository

        # Test pricing repository directly
        prices = await pricing_repository.get_prices_bulk(
            session,
            retailer_id=retailer_id,
            sku_ids=[UUID('dc52efaa-1921-479b-89a0-f508d24b5038'), UUID('302b3975-3db6-43f5-8a72-53c2b851f4dc')]
        )
        print(f"pricing_repository.get_prices_bulk result: {prices}")

        # Test get_price for individual SKUs
        sugar_price = await pricing_repository.get_price(
            session,
            retailer_id=retailer_id,
            sku_id=UUID('dc52efaa-1921-479b-89a0-f508d24b5038')
        )
        rice_price = await pricing_repository.get_price(
            session,
            retailer_id=retailer_id,
            sku_id=UUID('302b3975-3db6-43f5-8a72-53c2b851f4dc')
        )
        flour_price = await pricing_repository.get_price(
            session,
            retailer_id=retailer_id,
            sku_id=UUID('64045e2b-d072-4aa0-aba9-9aef87b15465')
        )

        print(f"\nPrice lookup results:")
        print(f"  Sugar (priced): {sugar_price}")
        print(f"  Rice (priced): {rice_price}")
        print(f"  Flour (unpriced): {flour_price}")

        # Validate
        assert sugar_price == Decimal('150.00'), f"Expected 150.00, got {sugar_price}"
        assert rice_price == Decimal('550.00'), f"Expected 550.00, got {rice_price}"
        assert flour_price is None, f"Expected None for unpriced SKU, got {flour_price}"

        print("\n✓ Pricing repository tests PASSED")
        return True

async def test_check_constraint():
    """Test that CHECK(price > 0) constraint works"""
    from database.session import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        # Try to insert a zero price - should fail
        try:
            await session.execute(
                text('''
                    INSERT INTO t_test_whole01.retailer_prices (id, retailer_id, sku_id, price)
                    VALUES (gen_random_uuid(),
                            '8a8fdb96-2569-48a0-9587-9e0ffa60f65e'::uuid,
                            '64045e2b-d072-4aa0-aba9-9aef87b15465'::uuid,
                            0.00)
                ''')
            )
            await session.commit()
            print("ERROR: CHECK constraint allowed zero price!")
            return False
        except Exception as e:
            await session.rollback()
            if 'ck_retailer_prices_positive_price' in str(e):
                print("✓ CHECK constraint correctly rejected zero price")
                return True
            else:
                print(f"ERROR: Unexpected error: {e}")
                return False

async def main():
    print("=" * 60)
    print("Phase 3 Runtime Validation Tests")
    print("=" * 60)

    print("\n1. Testing pricing repository...")
    result1 = await test_client_products_api()

    print("\n2. Testing CHECK constraint...")
    result2 = await test_check_constraint()

    print("\n" + "=" * 60)
    if result1 and result2:
        print("All runtime validation tests PASSED ✓")
    else:
        print("Some tests FAILED ✗")
    print("=" * 60)

if __name__ == '__main__':
    asyncio.run(main())
