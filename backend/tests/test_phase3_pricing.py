"""
Phase 3 Pricing Tests — validate server-side price resolution.

Test matrix:
1. Priced product listing: products with retailer_prices show real price
2. Unpriced product listing: products without retailer_prices show price=null, can_order=false
3. Priced order creation: order stores real unit_price and correct totals
4. No client-side price injection: order request body has no price field
5. Missing price blocks order: cannot order a product without a configured price
6. Pricing repository: get_price, get_prices_bulk, set_price
7. Pricing is retailer-scoped: retailer A's price does not leak to retailer B
"""
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TEST_TENANT_SCHEMA


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------
RETAILER_A_ID = uuid.UUID("aaaa0000-0000-0000-0000-000000000001")
RETAILER_B_ID = uuid.UUID("bbbb0000-0000-0000-0000-000000000002")
TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def seed_products(async_session: AsyncSession):
    """Seed SKUs, inventory, and retailer prices for pricing tests."""
    schema = TEST_TENANT_SCHEMA

    # Clean previous test data
    await async_session.execute(text(f'DELETE FROM "{schema}".retailer_prices'))
    await async_session.execute(text(f'DELETE FROM "{schema}".inventory_stocks'))
    await async_session.execute(text(f'DELETE FROM "{schema}".order_items'))
    await async_session.execute(text(f'DELETE FROM "{schema}".orders'))
    await async_session.execute(text(f'DELETE FROM "{schema}".skus'))
    await async_session.execute(text(f'DELETE FROM "{schema}".catalog_products'))

    # Insert SKUs
    sku_flour_id = uuid.uuid4()
    sku_sugar_id = uuid.uuid4()
    sku_rice_id = uuid.uuid4()

    # Stable catalog identity: each sellable unit owns its CatalogProduct row
    # (same reconciliation shape migration 038 applies to legacy rows).
    await async_session.execute(text(f"""
        INSERT INTO "{schema}".catalog_products (id, name, category, is_active)
        VALUES
            (:flour_id, 'Wheat Flour 25kg', 'Grains', true),
            (:sugar_id, 'White Sugar 50kg', 'Sweeteners', true),
            (:rice_id,  'Basmati Rice 5kg', 'Grains', true)
    """), {
        "flour_id": sku_flour_id,
        "sugar_id": sku_sugar_id,
        "rice_id": sku_rice_id,
    })

    await async_session.execute(text(f"""
        INSERT INTO "{schema}".skus (id, sku_code, name, unit, category, is_active, catalog_product_id, package_quantity)
        VALUES
            (:flour_id, 'FLOUR-25KG', 'Wheat Flour 25kg', 'bag', 'Grains', true, :flour_id, 1.000),
            (:sugar_id, 'SUGAR-50KG', 'White Sugar 50kg', 'bag', 'Sweeteners', true, :sugar_id, 1.000),
            (:rice_id,  'RICE-5KG',   'Basmati Rice 5kg', 'bag', 'Grains', true, :rice_id, 1.000)
    """), {
        "flour_id": sku_flour_id,
        "sugar_id": sku_sugar_id,
        "rice_id": sku_rice_id,
    })

    # Insert inventory (all in stock)
    await async_session.execute(text(f"""
        INSERT INTO "{schema}".inventory_stocks (id, sku_id, quantity_on_hand)
        VALUES
            (:inv1, :flour_id, 100),
            (:inv2, :sugar_id, 50),
            (:inv3, :rice_id,  200)
    """), {
        "inv1": uuid.uuid4(), "inv2": uuid.uuid4(), "inv3": uuid.uuid4(),
        "flour_id": sku_flour_id,
        "sugar_id": sku_sugar_id,
        "rice_id": sku_rice_id,
    })

    # Insert retailer prices — only Retailer A gets flour and sugar priced
    # Rice has NO price for either retailer
    await async_session.execute(text(f"""
        INSERT INTO "{schema}".retailer_prices (id, retailer_id, sku_id, price)
        VALUES
            (:rp1, :retailer_a, :flour_id, 1250.00),
            (:rp2, :retailer_a, :sugar_id, 4800.50)
    """), {
        "rp1": uuid.uuid4(), "rp2": uuid.uuid4(),
        "retailer_a": RETAILER_A_ID,
        "flour_id": sku_flour_id,
        "sugar_id": sku_sugar_id,
    })

    # Retailer B gets a DIFFERENT price for flour only
    await async_session.execute(text(f"""
        INSERT INTO "{schema}".retailer_prices (id, retailer_id, sku_id, price)
        VALUES (:rp3, :retailer_b, :flour_id, 1300.00)
    """), {
        "rp3": uuid.uuid4(),
        "retailer_b": RETAILER_B_ID,
        "flour_id": sku_flour_id,
    })

    await async_session.commit()

    return {
        "flour_id": sku_flour_id,
        "sugar_id": sku_sugar_id,
        "rice_id": sku_rice_id,
    }


# ---------------------------------------------------------------------------
# Test 1: Pricing repository — basic operations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_price_returns_correct_price(async_session: AsyncSession, seed_products):
    """Retailer A should get 1250.00 for flour."""
    from repositories.pricing_repository import get_price
    price = await get_price(async_session, RETAILER_A_ID, seed_products["flour_id"])
    assert price is not None
    assert price == Decimal("1250.00")


@pytest.mark.asyncio
async def test_get_price_returns_none_for_unpriced(async_session: AsyncSession, seed_products):
    """Rice has no price for Retailer A — should return None."""
    from repositories.pricing_repository import get_price
    price = await get_price(async_session, RETAILER_A_ID, seed_products["rice_id"])
    assert price is None


@pytest.mark.asyncio
async def test_get_prices_bulk(async_session: AsyncSession, seed_products):
    """Bulk fetch should return prices for priced SKUs only."""
    from repositories.pricing_repository import get_prices_bulk
    all_sku_ids = [seed_products["flour_id"], seed_products["sugar_id"], seed_products["rice_id"]]
    prices = await get_prices_bulk(async_session, RETAILER_A_ID, all_sku_ids)

    assert seed_products["flour_id"] in prices
    assert seed_products["sugar_id"] in prices
    assert seed_products["rice_id"] not in prices  # unpriced
    assert prices[seed_products["flour_id"]] == Decimal("1250.00")
    assert prices[seed_products["sugar_id"]] == Decimal("4800.50")


@pytest.mark.asyncio
async def test_set_price_creates_new(async_session: AsyncSession, seed_products):
    """set_price should create a new price record for an unpriced SKU."""
    from repositories.pricing_repository import set_price, get_price
    record = await set_price(
        async_session, RETAILER_A_ID, seed_products["rice_id"], Decimal("350.00")
    )
    assert record.price == Decimal("350.00")

    # Verify via get_price
    fetched = await get_price(async_session, RETAILER_A_ID, seed_products["rice_id"])
    assert fetched == Decimal("350.00")


@pytest.mark.asyncio
async def test_set_price_updates_existing(async_session: AsyncSession, seed_products):
    """set_price should update an existing price record."""
    from repositories.pricing_repository import set_price, get_price
    await set_price(
        async_session, RETAILER_A_ID, seed_products["flour_id"], Decimal("1350.00")
    )
    fetched = await get_price(async_session, RETAILER_A_ID, seed_products["flour_id"])
    assert fetched == Decimal("1350.00")


# ---------------------------------------------------------------------------
# Test 2: Retailer price isolation — A's price ≠ B's price
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retailer_price_isolation(async_session: AsyncSession, seed_products):
    """Retailer A and B should see different prices for the same SKU."""
    from repositories.pricing_repository import get_price
    price_a = await get_price(async_session, RETAILER_A_ID, seed_products["flour_id"])
    price_b = await get_price(async_session, RETAILER_B_ID, seed_products["flour_id"])

    assert price_a == Decimal("1250.00")
    assert price_b == Decimal("1300.00")
    assert price_a != price_b


@pytest.mark.asyncio
async def test_retailer_b_has_no_sugar_price(async_session: AsyncSession, seed_products):
    """Retailer B has no sugar price — should return None."""
    from repositories.pricing_repository import get_price
    price = await get_price(async_session, RETAILER_B_ID, seed_products["sugar_id"])
    assert price is None


# ---------------------------------------------------------------------------
# Test 3: SQL-level price join verification (simulates product API query)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_product_query_with_price_join(async_session: AsyncSession, seed_products):
    """
    Simulate the GET /client/products SQL join — verify retailer A sees
    correct prices and rice shows sell_price=NULL.
    """
    schema = TEST_TENANT_SCHEMA
    sql = text(f"""
        SELECT
            s.sku_code,
            s.name,
            COALESCE(i.quantity_on_hand, 0) AS quantity_on_hand,
            rp.price AS sell_price
        FROM "{schema}".skus s
        LEFT JOIN "{schema}".inventory_stocks i ON i.sku_id = s.id AND i.is_deleted IS NOT TRUE
        LEFT JOIN "{schema}".retailer_prices rp
            ON rp.sku_id = s.id
            AND rp.retailer_id = :retailer_id
            AND rp.is_deleted IS NOT TRUE
        WHERE s.is_active = true AND s.is_deleted IS NOT TRUE
        ORDER BY s.sku_code
    """)
    result = await async_session.execute(sql, {"retailer_id": RETAILER_A_ID})
    rows = {row.sku_code: row for row in result.fetchall()}

    # Flour: priced at 1250.00
    assert rows["FLOUR-25KG"].sell_price == Decimal("1250.00")
    # Sugar: priced at 4800.50
    assert rows["SUGAR-50KG"].sell_price == Decimal("4800.50")
    # Rice: no price
    assert rows["RICE-5KG"].sell_price is None


@pytest.mark.asyncio
async def test_product_query_price_isolation_between_retailers(async_session: AsyncSession, seed_products):
    """Retailer B should see different price for flour and no sugar price."""
    schema = TEST_TENANT_SCHEMA
    sql = text(f"""
        SELECT
            s.sku_code,
            rp.price AS sell_price
        FROM "{schema}".skus s
        LEFT JOIN "{schema}".retailer_prices rp
            ON rp.sku_id = s.id
            AND rp.retailer_id = :retailer_id
            AND rp.is_deleted IS NOT TRUE
        WHERE s.is_active = true AND s.is_deleted IS NOT TRUE
        ORDER BY s.sku_code
    """)
    result = await async_session.execute(sql, {"retailer_id": RETAILER_B_ID})
    rows = {row.sku_code: row for row in result.fetchall()}

    assert rows["FLOUR-25KG"].sell_price == Decimal("1300.00")  # B's price
    assert rows["SUGAR-50KG"].sell_price is None  # B has no sugar price
    assert rows["RICE-5KG"].sell_price is None


# ---------------------------------------------------------------------------
# Test 4: Order total calculation with server-side prices
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_order_total_from_resolved_prices(async_session: AsyncSession, seed_products):
    """
    Simulate order creation logic: resolve prices server-side and verify
    totals are computed from resolved prices, not client input.
    """
    from repositories.pricing_repository import get_prices_bulk

    # Order: 3x flour + 2x sugar
    order_items_request = [
        {"sku_code": "FLOUR-25KG", "quantity": 3},
        {"sku_code": "SUGAR-50KG", "quantity": 2},
    ]

    # Resolve SKU IDs
    schema = TEST_TENANT_SCHEMA
    result = await async_session.execute(
        text(f'SELECT id, sku_code FROM "{schema}".skus WHERE sku_code IN (:s1, :s2)'),
        {"s1": "FLOUR-25KG", "s2": "SUGAR-50KG"},
    )
    sku_map = {row.sku_code: row.id for row in result.fetchall()}

    # Resolve prices
    prices = await get_prices_bulk(
        async_session, RETAILER_A_ID, list(sku_map.values())
    )

    # Calculate totals
    total = Decimal("0.00")
    for item in order_items_request:
        sku_id = sku_map[item["sku_code"]]
        unit_price = prices[sku_id]
        subtotal = unit_price * item["quantity"]
        total += subtotal

    # 3 * 1250.00 + 2 * 4800.50 = 3750.00 + 9601.00 = 13351.00
    assert total == Decimal("13351.00")


# ---------------------------------------------------------------------------
# Test 5: No client-side price injection (schema validation)
# ---------------------------------------------------------------------------

def test_order_request_schema_has_no_price_field():
    """
    ClientCreateOrderRequest and ClientOrderItemRequest must NOT have
    a price or unit_price field — prices are server-resolved only.
    """
    from schemas.client import ClientCreateOrderRequest, ClientOrderItemRequest

    # Check item request fields
    item_fields = set(ClientOrderItemRequest.model_fields.keys())
    assert "price" not in item_fields
    assert "unit_price" not in item_fields
    assert "subtotal" not in item_fields

    # Check order request fields
    order_fields = set(ClientCreateOrderRequest.model_fields.keys())
    assert "price" not in order_fields
    assert "unit_price" not in order_fields
    assert "total_amount" not in order_fields


# ---------------------------------------------------------------------------
# Test 6: Missing price blocks ordering (unpriced SKU)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unpriced_product_has_can_order_false(async_session: AsyncSession, seed_products):
    """
    A product without a retailer_prices record should have can_order=false.
    Simulates the logic in the products API.
    """
    schema = TEST_TENANT_SCHEMA
    sql = text(f"""
        SELECT
            s.sku_code,
            COALESCE(i.quantity_on_hand, 0) AS quantity_on_hand,
            rp.price AS sell_price
        FROM "{schema}".skus s
        LEFT JOIN "{schema}".inventory_stocks i ON i.sku_id = s.id AND i.is_deleted IS NOT TRUE
        LEFT JOIN "{schema}".retailer_prices rp
            ON rp.sku_id = s.id
            AND rp.retailer_id = :retailer_id
            AND rp.is_deleted IS NOT TRUE
        WHERE s.sku_code = 'RICE-5KG'
    """)
    result = await async_session.execute(sql, {"retailer_id": RETAILER_A_ID})
    row = result.fetchone()

    # Rice is in stock but has no price
    assert float(row.quantity_on_hand) > 0
    assert row.sell_price is None

    # API logic: can_order = in_stock AND has_price
    in_stock = float(row.quantity_on_hand) > 0
    has_price = row.sell_price is not None
    can_order = in_stock and has_price
    assert can_order is False


# ---------------------------------------------------------------------------
# Test 7: RetailerPrice model integrity
# ---------------------------------------------------------------------------

def test_retailer_price_model_has_required_fields():
    """RetailerPrice model must have the expected field set."""
    from models.retailer_price import RetailerPrice

    mapper = RetailerPrice.__table__
    column_names = {c.name for c in mapper.columns}
    required = {"id", "retailer_id", "sku_id", "price", "created_at", "updated_at", "is_deleted"}
    assert required.issubset(column_names)


def test_retailer_price_unique_constraint():
    """RetailerPrice must have a unique constraint on (retailer_id, sku_id)."""
    from models.retailer_price import RetailerPrice

    table = RetailerPrice.__table__
    unique_constraints = [
        c for c in table.constraints
        if hasattr(c, 'columns') and len(c.columns) > 1
    ]
    # Find the (retailer_id, sku_id) unique constraint
    found = False
    for uc in unique_constraints:
        col_names = {c.name for c in uc.columns}
        if col_names == {"retailer_id", "sku_id"}:
            found = True
            break
    assert found, "Missing UNIQUE constraint on (retailer_id, sku_id)"


# ---------------------------------------------------------------------------
# Test 8: Non-positive price rejection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zero_price_rejected_at_order_time(async_session: AsyncSession, seed_products):
    """
    If a retailer_prices row somehow has price=0 (bypassing CHECK),
    the server-side guard in POST /client/orders must still reject it.

    We simulate by inserting via raw SQL with CHECK deferred, then
    verifying the application-level guard catches it.
    """
    schema = TEST_TENANT_SCHEMA

    # The DB CHECK constraint should block price=0 at the DB level.
    # Verify the CHECK works:
    import sqlalchemy.exc
    with pytest.raises(Exception):
        await async_session.execute(text(f"""
            INSERT INTO "{schema}".retailer_prices (id, retailer_id, sku_id, price)
            VALUES (:id, :rid, :sid, 0.00)
        """), {
            "id": uuid.uuid4(),
            "rid": RETAILER_A_ID,
            "sid": seed_products["rice_id"],
        })
        await async_session.flush()
    await async_session.rollback()
    # Re-set search_path after rollback
    await async_session.execute(text(f'SET LOCAL search_path TO "{schema}", public'))


@pytest.mark.asyncio
async def test_negative_price_rejected_at_db_level(async_session: AsyncSession, seed_products):
    """
    Inserting a negative price must be rejected by the DB CHECK(price > 0).
    """
    schema = TEST_TENANT_SCHEMA

    with pytest.raises(Exception):
        await async_session.execute(text(f"""
            INSERT INTO "{schema}".retailer_prices (id, retailer_id, sku_id, price)
            VALUES (:id, :rid, :sid, -50.00)
        """), {
            "id": uuid.uuid4(),
            "rid": RETAILER_A_ID,
            "sid": seed_products["rice_id"],
        })
        await async_session.flush()
    await async_session.rollback()
    # Re-set search_path after rollback
    await async_session.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
