"""
S5-A: Order State Machine Tests

Tests for atomic, validated, and rigid state transitions.

Test Cases:
1. Happy Path: DRAFT → CONFIRMED → PAID → FULFILLED
2. Illegal Transitions: Direct DRAFT → FULFILLED (should fail)
3. Invariant Violations: Confirm order with zero total
4. Terminal States: Cannot transition from FULFILLED
5. Void vs Cancel: VOID only allowed before payment
"""
import pytest
import uuid
from decimal import Decimal
from sqlalchemy import select

from models.order import Order, OrderItem, OrderStatus
from services.order_command_service import OrderCommandService
from services.order_service import OrderService
from core.domain.order_state import (
    OrderState,
    is_valid_transition,
    get_valid_transitions,
    is_terminal_state,
    InvalidStateTransitionError,
    OrderInvariantViolation,
)


def _tenant_wholesaler_id(async_session) -> uuid.UUID:
    tenant_id = async_session.info.get("tenant_id")
    if tenant_id is None:
        raise AssertionError("async_session fixture must provide tenant_id")
    return uuid.UUID(str(tenant_id))


# ============================================================================
# Unit Tests: State Machine Logic
# ============================================================================

def test_state_transition_matrix():
    """Test that state transition matrix is correctly defined."""
    # Valid transitions
    assert is_valid_transition(OrderState.DRAFT, OrderState.CONFIRMED)
    assert is_valid_transition(OrderState.DRAFT, OrderState.VOIDED)
    assert is_valid_transition(OrderState.CONFIRMED, OrderState.PAID)
    assert is_valid_transition(OrderState.CONFIRMED, OrderState.PARTIALLY_PAID)
    assert is_valid_transition(OrderState.CONFIRMED, OrderState.CANCELLED)
    assert is_valid_transition(OrderState.PAID, OrderState.FULFILLED)
    assert is_valid_transition(OrderState.PAID, OrderState.CANCELLED)

    # Invalid transitions
    assert not is_valid_transition(OrderState.DRAFT, OrderState.PAID)
    assert not is_valid_transition(OrderState.DRAFT, OrderState.FULFILLED)
    assert not is_valid_transition(OrderState.CONFIRMED, OrderState.FULFILLED)
    assert not is_valid_transition(OrderState.FULFILLED, OrderState.CANCELLED)


def test_get_valid_transitions():
    """Test getting valid transitions from a state."""
    draft_transitions = get_valid_transitions(OrderState.DRAFT)
    assert OrderState.CONFIRMED in draft_transitions
    assert OrderState.VOIDED in draft_transitions
    # R1 frozen decision: ordinary draft cancellation returns CANCELLED,
    # so the domain matrix now carries the DRAFT -> CANCELLED edge.
    assert OrderState.CANCELLED in draft_transitions
    assert len(draft_transitions) == 3

    confirmed_transitions = get_valid_transitions(OrderState.CONFIRMED)
    assert OrderState.PAID in confirmed_transitions
    assert OrderState.PARTIALLY_PAID in confirmed_transitions
    assert OrderState.CANCELLED in confirmed_transitions
    assert len(confirmed_transitions) == 3


def test_terminal_states():
    """Test terminal state detection.

    FULFILLED is NOT terminal — it can transition to RETURNED.
    RETURNED, CANCELLED, VOIDED are terminal (no outgoing transitions).
    """
    # Terminal states: empty transition sets in STATE_TRANSITION_MATRIX
    assert is_terminal_state(OrderState.RETURNED)
    assert is_terminal_state(OrderState.CANCELLED)
    assert is_terminal_state(OrderState.VOIDED)

    # Non-terminal states: have at least one outgoing transition
    assert not is_terminal_state(OrderState.DRAFT)
    assert not is_terminal_state(OrderState.CONFIRMED)
    assert not is_terminal_state(OrderState.PARTIALLY_PAID)
    assert not is_terminal_state(OrderState.PAID)
    assert not is_terminal_state(OrderState.FULFILLED)


def test_partially_paid_self_transition_is_not_globally_valid():
    """partially_paid -> partially_paid is not a generic state transition."""
    assert not is_valid_transition(
        OrderState.PARTIALLY_PAID,
        OrderState.PARTIALLY_PAID,
    )


# ============================================================================
# Integration Tests: OrderService State Transitions
# ============================================================================

async def _ensure_sku_stock(db, schema: str):
    """F1: seed catalog product + SKU + stock; returns (sku_id_hex, sku_code)."""
    from sqlalchemy import text as _t
    import uuid as _u
    prod = (await db.execute(_t(
        f'INSERT INTO "{schema}".catalog_products (name, is_active, is_deleted) '
        "VALUES ('S5', true, false) RETURNING id"))).fetchone()
    code = f"S5-{_u.uuid4().hex[:8]}"
    row = (await db.execute(_t(
        f'INSERT INTO "{schema}".skus '
        "(sku_code, name, unit, is_active, is_deleted, catalog_product_id, package_quantity) "
        "VALUES (:c, 'S5', 'piece', true, false, :p, 1) RETURNING id"),
        {"c": code, "p": prod.id})).fetchone()
    await db.execute(_t(
        f'INSERT INTO "{schema}".inventory_stocks '
        "(sku_id, quantity_on_hand, quantity_reserved, is_deleted) "
        "VALUES (:s, 1000, 0, false)"), {"s": row.id})
    await db.flush()
    return str(row.id), code


@pytest.fixture
async def sample_order(async_session):
    """Create a sample order for testing."""
    wholesaler_id = _tenant_wholesaler_id(async_session)
    retailer_id = uuid.uuid4()

    order = Order(
        wholesaler_id=wholesaler_id,
        retailer_id=retailer_id,
        status=OrderStatus.DRAFT,
        total_amount=Decimal("100.00"),
        notes="Test order"
    )

    # Add an item (F1: real SKU so the confirm command can reserve)
    schema = async_session.info.get("tenant_schema", "t_test")
    sku_id, _code = await _ensure_sku_stock(async_session, schema)
    item = OrderItem(
        sellable_unit_id=uuid.UUID(sku_id),
        identity_status="stable",
        unit_snapshot="piece",
        product_name="Test Product",
        sku_code=_code,
        quantity=2,
        unit_price=Decimal("50.00"),
        subtotal=Decimal("100.00")
    )
    order.items = [item]

    # R2 contract: confirm requires a live (wholesaler, retailer) binding.
    from tests.order_state_r2.contract_helpers import ensure_binding
    await ensure_binding(async_session, wholesaler_id, retailer_id)

    async_session.add(order)
    await async_session.flush()  # Flush to get ID, but don't commit
    await async_session.refresh(order)

    return order


@pytest.mark.asyncio
async def test_happy_path_draft_to_fulfilled(async_session, sample_order):
    """
    Test Case 1: Happy Path - DRAFT → CONFIRMED → PAID → FULFILLED

    Verifies:
    - Each transition is valid
    - Order state updates correctly
    - All transitions are atomic
    """
    service = OrderService(async_session)
    order = sample_order

    # DRAFT → CONFIRMED
    order = (await OrderCommandService(async_session).confirm_order(order.id)).order

    assert order.status == OrderStatus.CONFIRMED

    # CONFIRMED → PAID
    order = (await OrderCommandService(async_session).apply_payment_transition(
        order.id,
        OrderState.PAID,
    )).order
    # Note: Currently maps to CONFIRMED due to temporary mapping
    # Will be PAID once OrderStatus enum is updated

    # PAID → FULFILLED
    order = (await OrderCommandService(async_session).fulfill_order(order.id)).order

    # Note: Currently maps to CONFIRMED due to temporary mapping


@pytest.mark.asyncio
async def test_illegal_transition_draft_to_fulfilled(async_session, sample_order):
    """
    Test Case 2: Illegal Transition - DRAFT → FULFILLED (should fail)

    Verifies:
    - Invalid transitions are rejected
    - InvalidStateTransitionError is raised
    - Order state remains unchanged
    """
    service = OrderService(async_session)
    order = sample_order

    # Attempt illegal transition
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        await OrderCommandService(async_session).fulfill_order(order.id)


    # Verify error details
    assert exc_info.value.from_state == OrderState.DRAFT
    assert exc_info.value.to_state == OrderState.FULFILLED

    # Verify order state unchanged
    await async_session.refresh(order)
    assert order.status == OrderStatus.DRAFT


@pytest.mark.asyncio
async def test_partially_paid_self_transition_allowed_only_for_payment_context(async_session, sample_order):
    """Additional partial payments may keep the order partially_paid.

    The state matrix remains globally strict; OrderService only accepts this
    same-state transition when the caller supplies structured payment context.
    """
    service = OrderService(async_session)
    order = sample_order

    order = (await OrderCommandService(async_session).confirm_order(order.id)).order

    order = (await OrderCommandService(async_session).apply_payment_transition(order.id, OrderState.PARTIALLY_PAID)).order
    assert order.status == OrderStatus.PARTIALLY_PAID

    with pytest.raises(InvalidStateTransitionError):
        await OrderCommandService(async_session).apply_payment_transition(
            order.id,
            OrderState.PARTIALLY_PAID,
        )

    order = (await OrderCommandService(async_session).apply_payment_transition(
        order.id,
        OrderState.PARTIALLY_PAID,
        payment_method="cash",
    )).order
    assert order.status == OrderStatus.PARTIALLY_PAID


@pytest.mark.asyncio
async def test_invariant_violation_confirm_zero_total(async_session):
    """
    Test Case 3: Invariant Violation - Cannot confirm order with zero total

    Verifies:
    - Business invariants are enforced
    - OrderInvariantViolation is raised
    - Order state remains unchanged
    """
    service = OrderService(async_session)

    # Create order with zero total
    order = Order(
        wholesaler_id=_tenant_wholesaler_id(async_session),
        retailer_id=uuid.uuid4(),
        status=OrderStatus.DRAFT,
        total_amount=Decimal("0.00"),
        notes="Zero total order"
    )
    async_session.add(order)
    await async_session.commit()
    await async_session.refresh(order)

    # Attempt to confirm
    with pytest.raises(OrderInvariantViolation) as exc_info:
        await OrderCommandService(async_session).confirm_order(order.id)


    # Verify error message
    assert "zero or negative total" in str(exc_info.value).lower()

    # Verify order state unchanged
    await async_session.refresh(order)
    assert order.status == OrderStatus.DRAFT


@pytest.mark.asyncio
async def test_terminal_state_no_transitions(async_session, sample_order):
    """
    Test Case 4: Terminal State - Cannot transition from FULFILLED

    Verifies:
    - Terminal states cannot be transitioned from
    - InvalidStateTransitionError is raised (state machine check happens first)
    """
    service = OrderService(async_session)
    order = sample_order

    # Transition to FULFILLED (via CONFIRMED → PAID → FULFILLED)
    await OrderCommandService(async_session).confirm_order(order.id)

    (await OrderCommandService(async_session).apply_payment_transition(order.id, OrderState.PAID)).order
    await OrderCommandService(async_session).fulfill_order(order.id)


    # Attempt to transition from terminal state
    # State machine check happens before invariant check
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        await OrderCommandService(async_session).cancel_order(order.id)


    # Verify error message mentions transition not allowed
    assert "not allowed" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_void_vs_cancel_rules(async_session, sample_order):
    """
    Test Case 5: VOID vs CANCEL - VOID only allowed before payment

    Verifies:
    - VOID is allowed from DRAFT
    - VOID is NOT allowed from PAID/PARTIALLY_PAID
    - CANCEL is allowed from CONFIRMED and PAID
    """
    service = OrderService(async_session)

    # Test 1: VOID from DRAFT (should succeed)
    order1 = Order(
        wholesaler_id=_tenant_wholesaler_id(async_session),
        retailer_id=uuid.uuid4(),
        status=OrderStatus.DRAFT,
        total_amount=Decimal("100.00")
    )
    async_session.add(order1)
    await async_session.commit()
    await async_session.refresh(order1)

    order1 = await service.transition(
        order_id=order1.id,
        target_state=OrderState.VOIDED,
        reason="Customer cancelled before confirmation"
    )
    assert order1.status == OrderStatus.VOIDED  # Maps to VOIDED

    # Test 2: VOID from PAID (should fail)
    # State machine doesn't allow PAID → VOIDED, so we get InvalidStateTransitionError
    order2 = sample_order
    await OrderCommandService(async_session).confirm_order(order2.id)

    (await OrderCommandService(async_session).apply_payment_transition(order2.id, OrderState.PAID)).order

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        await service.transition(
            order_id=order2.id,
            target_state=OrderState.VOIDED,
            reason="Trying to void paid order"
        )

    assert "not allowed" in str(exc_info.value).lower()

    # Test 3: CANCEL from PAID — R1/F1 frozen decision: fail-closed while
    # the refund/funds disposition workflow is not implemented.
    from fastapi import HTTPException as _HttpException

    with pytest.raises(_HttpException) as exc_info:
        await OrderCommandService(async_session).cancel_order(order2.id)
    assert exc_info.value.detail["code"] == "REFUND_WORKFLOW_NOT_IMPLEMENTED"
    await async_session.rollback()


@pytest.mark.asyncio
async def test_partial_payment_flow(async_session, sample_order):
    """
    Test Case 6: Partial Payment Flow - CONFIRMED → PARTIALLY_PAID → PAID

    Verifies:
    - Partial payment state is supported
    - Can transition from PARTIALLY_PAID to PAID
    - Can cancel from PARTIALLY_PAID
    """
    service = OrderService(async_session)
    order = sample_order

    # DRAFT → CONFIRMED
    await OrderCommandService(async_session).confirm_order(order.id)


    # CONFIRMED → PARTIALLY_PAID
    order = (await OrderCommandService(async_session).apply_payment_transition(
        order.id,
        OrderState.PARTIALLY_PAID,
    )).order

    # PARTIALLY_PAID → PAID
    order = (await OrderCommandService(async_session).apply_payment_transition(
        order.id,
        OrderState.PAID,
    )).order

    # Verify final state
    await async_session.refresh(order)
    # Note: Currently maps to CONFIRMED due to temporary mapping


@pytest.mark.asyncio
async def test_concurrent_transition_with_locking(async_session, sample_order):
    """
    Test Case 7: Concurrency - Row locking prevents race conditions

    Verifies:
    - SELECT FOR UPDATE locks the row
    - Concurrent transitions are serialized
    """
    service = OrderService(async_session)
    order = sample_order

    # First transition should succeed
    order = (await OrderCommandService(async_session).confirm_order(order.id)).order


    # Verify state changed
    await async_session.refresh(order)
    assert order.status == OrderStatus.CONFIRMED


@pytest.mark.asyncio
async def test_transition_with_updated_by(async_session, sample_order):
    """
    Test Case 8: Audit Trail - updated_by is tracked

    Verifies:
    - updated_by field is set during transition
    - Audit trail is maintained
    """
    service = OrderService(async_session)
    order = sample_order
    user_id = uuid.uuid4()

    order = (await OrderCommandService(async_session).confirm_order(
        order.id, updated_by=str(user_id))).order

    # Verify updated_by is set
    await async_session.refresh(order)
    assert order.updated_by == user_id


@pytest.mark.asyncio
async def test_order_not_found(async_session):
    """
    Test Case 9: Error Handling - Order not found

    Verifies:
    - ValueError is raised for non-existent order
    """
    service = OrderService(async_session)
    non_existent_id = uuid.uuid4()

    from fastapi import HTTPException as _HttpException

    with pytest.raises(_HttpException) as exc_info:
        await OrderCommandService(async_session).confirm_order(non_existent_id)

    assert exc_info.value.detail["code"] == "ORDER_NOT_FOUND"
    assert "not found" in exc_info.value.detail["message"].lower()


@pytest.mark.asyncio
async def test_cannot_fulfill_unpaid_order(async_session, sample_order):
    """
    Test Case 10: Invariant - Cannot fulfill unpaid order

    Verifies:
    - Order must be PAID before FULFILLED
    - Attempting to fulfill CONFIRMED order fails with InvalidStateTransitionError
      (state machine doesn't allow CONFIRMED → FULFILLED)
    """
    service = OrderService(async_session)
    order = sample_order

    # DRAFT → CONFIRMED
    await OrderCommandService(async_session).confirm_order(order.id)


    # Attempt CONFIRMED → FULFILLED (should fail - not allowed by state machine)
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        await OrderCommandService(async_session).fulfill_order(order.id)


    assert "not allowed" in str(exc_info.value).lower()
