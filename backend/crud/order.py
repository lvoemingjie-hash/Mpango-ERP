"""
CRUD operations for Order model.
Operates on tenant schema.

Implements order state machine:
- Draft → Confirmed
- Confirmed → Paid
- Paid → Fulfilled (with inventory deduction at API layer)
- Cancel only allowed in Draft or Confirmed
- Return only allowed in Fulfilled
"""
from typing import Optional, List, Tuple, Dict
from uuid import UUID
from decimal import Decimal
from sqlalchemy import select, func, text
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
    "pay": {
        "allowed_from": [OrderStatus.CONFIRMED],
        "target": OrderStatus.PAID
    },
    "fulfill": {
        "allowed_from": [OrderStatus.PAID],
        "target": OrderStatus.FULFILLED
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


async def batch_retailer_names(
    db: AsyncSession,
    retailer_ids: List[UUID],
) -> Dict[str, str]:
    """
    Batch-fetch retailer names from public.retailers.

    Args:
        db: Database session
        retailer_ids: List of retailer UUIDs

    Returns:
        Dict mapping retailer_id (str) -> name (str)
    """
    if not retailer_ids:
        return {}
    unique_ids = list(set(retailer_ids))
    result = await db.execute(
        text(
            "SELECT id, name FROM public.retailers "
            "WHERE id = ANY(:ids) AND is_deleted IS FALSE"
        ),
        {"ids": unique_ids},
    )
    return {str(row.id): (row.name or "—") for row in result.fetchall()}


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


async def get_order_for_wholesaler(
    db: AsyncSession,
    order_id: str,
    wholesaler_id: str,
) -> Optional[Order]:
    """
    DC-12R1-S3-S2B-I2C-I1-R2: supplier-scoped order fetch.

    Loads an order ONLY if it matches ``order_id`` AND ``wholesaler_id`` AND
    is not soft-deleted — a database-level dual-key predicate (not a
    load-then-compare). A wrong-supplier request returns ``None`` -> neutral
    404, without first fetching the row and disclosing its existence.
    """
    try:
        order_uuid = UUID(order_id)
        ws_uuid = UUID(wholesaler_id)
    except (ValueError, TypeError):
        return None

    result = await db.execute(
        select(Order)
        .where(Order.id == order_uuid)
        .where(Order.wholesaler_id == ws_uuid)
        .where(Order.is_deleted == False)
        .options(selectinload(Order.items))
    )
    return result.scalar_one_or_none()


async def get_order_for_retailer(
    db: AsyncSession,
    order_id: str,
    wholesaler_id: str,
    retailer_id: str,
) -> Optional[Order]:
    """
    DC-12R1-S3-S1: dual-key scoped order fetch for the retailer client API.

    Loads an order ONLY if it matches ``order_id`` AND ``wholesaler_id`` AND
    ``retailer_id`` AND is not soft-deleted. This enforces ownership at the
    database layer (defense-in-depth on top of the tenant-scoped session) so a
    wrong-retailer or wrong-supplier request returns ``None`` -> neutral 404,
    without first fetching the row and disclosing its existence.

    Used by the client ``get_order`` / ``cancel_order`` routes. The unscoped
    ``get_order_by_id`` remains for wholesaler-side use.
    """
    try:
        order_uuid = UUID(order_id)
        ws_uuid = UUID(wholesaler_id)
        retailer_uuid = UUID(retailer_id)
    except (ValueError, TypeError):
        return None

    result = await db.execute(
        select(Order)
        .where(Order.id == order_uuid)
        .where(Order.wholesaler_id == ws_uuid)
        .where(Order.retailer_id == retailer_uuid)
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


async def get_orders_for_retailer(
    db: AsyncSession,
    *,
    wholesaler_id: str,
    retailer_id: str,
    page: int = 1,
    size: int = 20,
    status_filter: Optional[OrderStatus] = None,
) -> Tuple[List[Order], int]:
    """DC-12R1-S3-S1-R1: retailer-specific paginated order list.

    Both ``wholesaler_id`` and ``retailer_id`` are **mandatory** and validated.
    Invalid UUIDs return an empty result (zero orders, zero count) — never an
    unscoped query and never a propagated ValueError/500.

    The generic ``get_orders_paginated`` remains for wholesaler-side use where
    filters are genuinely optional.
    """
    try:
        ws_uuid = UUID(wholesaler_id)
        retailer_uuid = UUID(retailer_id)
    except (ValueError, TypeError):
        return [], 0

    base_query = (
        select(Order)
        .where(Order.is_deleted == False)
        .where(Order.wholesaler_id == ws_uuid)
        .where(Order.retailer_id == retailer_uuid)
    )
    count_query = (
        select(func.count(Order.id))
        .where(Order.is_deleted == False)
        .where(Order.wholesaler_id == ws_uuid)
        .where(Order.retailer_id == retailer_uuid)
    )

    if status_filter:
        base_query = base_query.where(Order.status == status_filter)
        count_query = count_query.where(Order.status == status_filter)

    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

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
            sellable_unit_id=UUID(str(item["sellable_unit_id"])),
            identity_status="stable",
            product_name=item["product_name"],
            sku_code=item["sku_code"],
            unit_snapshot=item["unit_snapshot"],
            quantity=quantity,
            unit_price=unit_price,
            subtotal=subtotal,
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


async def pay_order(
    db: AsyncSession,
    order: Order,
    updated_by: Optional[str] = None
) -> Order:
    """
    Mark an order as paid (confirmed → paid).

    Args:
        db: Database session (tenant schema)
        order: Order to mark as paid
        updated_by: UUID of user marking payment

    Returns:
        Updated Order

    Raises:
        InvalidStateTransitionError: If order is not in confirmed status
    """
    validate_state_transition(order, "pay")

    order.status = OrderStatus.PAID

    if updated_by:
        try:
            order.updated_by = UUID(updated_by)
        except ValueError:
            pass

    await db.flush()
    await db.refresh(order, ["items"])

    return order


async def fulfill_order(
    db: AsyncSession,
    order: Order,
    updated_by: Optional[str] = None
) -> Order:
    """
    Fulfill an order (paid → fulfilled).

    Note: Inventory deduction is handled at the API layer via OrderService,
    not in this CRUD function.

    Args:
        db: Database session (tenant schema)
        order: Order to fulfill
        updated_by: UUID of user fulfilling

    Returns:
        Updated Order

    Raises:
        InvalidStateTransitionError: If order is not in paid status
    """
    validate_state_transition(order, "fulfill")

    order.status = OrderStatus.FULFILLED

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
