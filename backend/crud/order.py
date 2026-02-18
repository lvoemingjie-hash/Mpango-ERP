"""
CRUD operations for Order model.
Operates on tenant schema.

Implements order state machine:
- Draft → Confirmed
- Cancel only allowed in Draft or Confirmed
"""
from typing import Optional, List, Tuple
from uuid import UUID
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.order import Order, OrderItem, OrderStatus


class InvalidStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    def __init__(self, current_status: str, action: str, allowed_statuses: List[str]):
        self.current_status = current_status
        self.action = action
        self.allowed_statuses = allowed_statuses
        super().__init__(
            f"Cannot {action} order in '{current_status}' status. "
            f"Allowed statuses: {', '.join(allowed_statuses)}"
        )


# State machine rules
STATE_TRANSITIONS = {
    "confirm": {
        "allowed_from": [OrderStatus.DRAFT],
        "target": OrderStatus.CONFIRMED
    },
    "cancel": {
        "allowed_from": [OrderStatus.DRAFT, OrderStatus.CONFIRMED],
        "target": OrderStatus.CANCELLED
    },
    "return": {
        "allowed_from": [OrderStatus.FULFILLED],
        "target": OrderStatus.RETURNED
    }
}


def validate_state_transition(order: Order, action: str) -> None:
    """
    Validate that a state transition is allowed.

    Args:
        order: Order to validate
        action: Action to perform (confirm, ship, cancel)

    Raises:
        InvalidStateTransitionError: If transition is not allowed
    """
    if action not in STATE_TRANSITIONS:
        raise ValueError(f"Unknown action: {action}")

    rules = STATE_TRANSITIONS[action]
    if order.status not in rules["allowed_from"]:
        raise InvalidStateTransitionError(
            current_status=order.status.value,
            action=action,
            allowed_statuses=[s.value for s in rules["allowed_from"]]
        )


async def get_order_by_id(
    db: AsyncSession,
    order_id: str
) -> Optional[Order]:
    """
    Get order by ID with items loaded.

    Args:
        db: Database session (tenant schema)
        order_id: Order UUID as string

    Returns:
        Order with items loaded, None if not found
    """
    try:
        order_uuid = UUID(order_id)
    except ValueError:
        return None

    result = await db.execute(
        select(Order)
        .where(Order.id == order_uuid)
        .where(Order.is_deleted == False)
        .options(selectinload(Order.items))
    )
    return result.scalar_one_or_none()


async def get_orders_paginated(
    db: AsyncSession,
    page: int = 1,
    size: int = 10,
    wholesaler_id: Optional[str] = None,
    status_filter: Optional[OrderStatus] = None,
    retailer_id: Optional[str] = None
) -> Tuple[List[Order], int]:
    """
    Get paginated list of orders with optional filters.

    Args:
        db: Database session (tenant schema)
        page: Page number (1-based)
        size: Items per page
        status_filter: Optional status filter
        retailer_id: Optional retailer ID filter

    Returns:
        Tuple of (orders list, total count)
    """
    # Build base query
    base_query = select(Order).where(Order.is_deleted == False)
    count_query = select(func.count(Order.id)).where(Order.is_deleted == False)

    # Apply filters
    if wholesaler_id:
        try:
            wholesaler_uuid = UUID(wholesaler_id)
            base_query = base_query.where(Order.wholesaler_id == wholesaler_uuid)
            count_query = count_query.where(Order.wholesaler_id == wholesaler_uuid)
        except ValueError:
            pass

    if status_filter:
        base_query = base_query.where(Order.status == status_filter)
        count_query = count_query.where(Order.status == status_filter)

    if retailer_id:
        try:
            retailer_uuid = UUID(retailer_id)
            base_query = base_query.where(Order.retailer_id == retailer_uuid)
            count_query = count_query.where(Order.retailer_id == retailer_uuid)
        except ValueError:
            pass

    # Get total count
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    # Get paginated orders
    offset = (page - 1) * size
    result = await db.execute(
        base_query
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    orders = list(result.scalars().all())

    return orders, total


async def create_order(
    db: AsyncSession,
    wholesaler_id: str,
    retailer_id: str,
    items: List[dict],
    notes: Optional[str] = None,
    created_by: Optional[str] = None
) -> Order:
    """
    Create a new order with items.

    Args:
        db: Database session (tenant schema)
        wholesaler_id: Wholesaler/Tenant UUID as string
        retailer_id: Retailer UUID as string
        items: List of item dicts with product_name, sku_code, quantity, unit_price
        notes: Optional order notes
        created_by: UUID of user creating this order

    Returns:
        Created Order object with items
    """
    # Calculate total
    total_amount = Decimal("0.00")
    order_items = []

    for item in items:
        quantity = item["quantity"]
        unit_price = item["unit_price"]
        subtotal = Decimal(str(quantity)) * unit_price
        total_amount += subtotal

        order_item = OrderItem(
            product_name=item["product_name"],
            sku_code=item["sku_code"],
            quantity=quantity,
            unit_price=unit_price,
            subtotal=subtotal
        )
        order_items.append(order_item)

    # Create order
    order = Order(
        wholesaler_id=UUID(wholesaler_id),
        retailer_id=UUID(retailer_id),
        status=OrderStatus.DRAFT,
        total_amount=total_amount,
        notes=notes,
        items=order_items
    )

    if created_by:
        try:
            order.created_by = UUID(created_by)
        except ValueError:
            pass

    db.add(order)
    await db.flush()
    await db.refresh(order, ["items"])

    return order


async def confirm_order(
    db: AsyncSession,
    order: Order,
    updated_by: Optional[str] = None
) -> Order:
    """
    Confirm an order (draft → confirmed).

    Args:
        db: Database session (tenant schema)
        order: Order to confirm
        updated_by: UUID of user confirming

    Returns:
        Updated Order

    Raises:
        InvalidStateTransitionError: If order is not in draft status
    """
    validate_state_transition(order, "confirm")

    order.status = OrderStatus.CONFIRMED

    if updated_by:
        try:
            order.updated_by = UUID(updated_by)
        except ValueError:
            pass

    await db.flush()
    await db.refresh(order, ["items"])

    return order


async def cancel_order(
    db: AsyncSession,
    order: Order,
    updated_by: Optional[str] = None
) -> Order:
    """
    Cancel an order (draft/confirmed → cancelled).

    Args:
        db: Database session (tenant schema)
        order: Order to cancel
        updated_by: UUID of user cancelling

    Returns:
        Updated Order

    Raises:
        InvalidStateTransitionError: If order is not in draft or confirmed status
    """
    validate_state_transition(order, "cancel")

    order.status = OrderStatus.CANCELLED

    if updated_by:
        try:
            order.updated_by = UUID(updated_by)
        except ValueError:
            pass

    await db.flush()
    await db.refresh(order, ["items"])

    return order


async def return_order(
    db: AsyncSession,
    order: Order,
    updated_by: Optional[str] = None
) -> Order:
    """
    Process a full return on a fulfilled order (fulfilled → returned).

    This function handles status change only. Ledger entries and inventory
    restocking are handled by OrderService.transition() when used via the
    API layer.

    Args:
        db: Database session (tenant schema)
        order: Order to return
        updated_by: UUID of user processing the return

    Returns:
        Updated Order

    Raises:
        InvalidStateTransitionError: If order is not in fulfilled status
    """
    validate_state_transition(order, "return")

    order.status = OrderStatus.RETURNED

    if updated_by:
        try:
            order.updated_by = UUID(updated_by)
        except ValueError:
            pass

    await db.flush()
    await db.refresh(order, ["items"])

    return order
