"""Test order creation in t_test schema."""
import pytest
import uuid
from decimal import Decimal
from sqlalchemy import text

from models.order import Order, OrderItem, OrderStatus


@pytest.mark.asyncio
async def test_create_order_in_t_test(async_session):
    """Test creating an order in t_test schema."""
    # Verify search_path
    result = await async_session.execute(text("SHOW search_path"))
    search_path = result.scalar()
    print(f"\nSearch path: {search_path}")
    
    # Create order
    wholesaler_id = uuid.uuid4()
    retailer_id = uuid.uuid4()
    
    order = Order(
        wholesaler_id=wholesaler_id,
        retailer_id=retailer_id,
        status=OrderStatus.DRAFT,
        total_amount=Decimal("100.00"),
        notes="Test order"
    )
    
    async_session.add(order)
    
    try:
        await async_session.flush()
        print(f"Order created with ID: {order.id}")
        print(f"Order status: {order.status}")
        assert order.id is not None
        assert order.status == OrderStatus.DRAFT
    except Exception as e:
        print(f"Error: {e}")
        raise
