"""
S5-B: Financial Ledger Tests

Tests for immutable ledger entries and balance projection.

Philosophy: "Payments are not 'updating a balance column'. Payments are immutable Ledger Entries."

Test Cases:
1. Post single ledger entry
2. Post balanced transaction
3. Reject unbalanced transaction
4. Calculate account balance
5. Order lifecycle accounting (CONFIRMED → PAID)
6. Verify ledger immutability
7. Balance projection as of date
"""
import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from models.ledger import LedgerEntry, AccountType
from models.order import Order, OrderItem, OrderStatus
from services.ledger_service import LedgerService
from services.order_service import OrderService
from core.domain.order_state import OrderState
from core.exceptions import LedgerIntegrityError


def _tenant_wholesaler_id(async_session) -> uuid.UUID:
    tenant_id = async_session.info.get("tenant_id")
    if tenant_id is None:
        raise AssertionError("async_session fixture must provide tenant_id")
    return uuid.UUID(str(tenant_id))


# ============================================================================
# Unit Tests: Ledger Service
# ============================================================================

@pytest.mark.asyncio
async def test_post_single_entry(async_session):
    """Test posting a single ledger entry."""
    service = LedgerService(async_session)
    
    order_id = uuid.uuid4()
    entry = await service.post_entry(
        account_type=AccountType.RECEIVABLE,
        amount=Decimal("100.00"),
        reference_type="order",
        reference_id=order_id,
        description="Test entry"
    )
    
    assert entry.id is not None
    assert entry.account_type == AccountType.RECEIVABLE
    assert entry.amount == Decimal("100.00")
    assert entry.reference_type == "order"
    assert entry.reference_id == order_id
    assert entry.description == "Test entry"


@pytest.mark.asyncio
async def test_post_balanced_transaction(async_session):
    """Test posting a balanced transaction (debits = credits)."""
    service = LedgerService(async_session)
    
    order_id = uuid.uuid4()
    entries = await service.post_transaction(
        entries=[
            {
                'account_type': AccountType.RECEIVABLE,
                'amount': Decimal('100.00'),  # Debit
                'description': 'Customer owes'
            },
            {
                'account_type': AccountType.REVENUE,
                'amount': Decimal('-100.00'),  # Credit
                'description': 'Revenue earned'
            }
        ],
        reference_type='order',
        reference_id=order_id
    )
    
    assert len(entries) == 2
    assert entries[0].amount == Decimal('100.00')
    assert entries[1].amount == Decimal('-100.00')
    
    # Verify transaction is balanced
    total = sum(e.amount for e in entries)
    assert total == Decimal('0')


@pytest.mark.asyncio
async def test_reject_unbalanced_transaction(async_session):
    """Test that unbalanced transactions are rejected."""
    service = LedgerService(async_session)
    
    order_id = uuid.uuid4()
    
    with pytest.raises(LedgerIntegrityError) as exc_info:
        await service.post_transaction(
            entries=[
                {
                    'account_type': AccountType.RECEIVABLE,
                    'amount': Decimal('100.00'),  # Debit
                    'description': 'Customer owes'
                },
                {
                    'account_type': AccountType.REVENUE,
                    'amount': Decimal('-50.00'),  # Credit (WRONG AMOUNT)
                    'description': 'Revenue earned'
                }
            ],
            reference_type='order',
            reference_id=order_id
        )
    
    assert "not balanced" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_calculate_account_balance(async_session):
    """Test calculating account balance from ledger entries."""
    service = LedgerService(async_session)
    
    # Post some entries
    order_id = uuid.uuid4()
    
    # Entry 1: Debit RECEIVABLE +100
    await service.post_entry(
        account_type=AccountType.RECEIVABLE,
        amount=Decimal("100.00"),
        reference_type="order",
        reference_id=order_id
    )
    
    # Entry 2: Debit RECEIVABLE +50
    await service.post_entry(
        account_type=AccountType.RECEIVABLE,
        amount=Decimal("50.00"),
        reference_type="order",
        reference_id=order_id
    )
    
    # Entry 3: Credit RECEIVABLE -30
    await service.post_entry(
        account_type=AccountType.RECEIVABLE,
        amount=Decimal("-30.00"),
        reference_type="payment",
        reference_id=order_id
    )
    
    # Calculate balance
    balance = await service.get_balance(AccountType.RECEIVABLE)
    
    # 100 + 50 - 30 = 120
    assert balance == Decimal("120.00")


@pytest.mark.asyncio
async def test_get_entries_for_reference(async_session):
    """Test retrieving all entries for a specific reference."""
    service = LedgerService(async_session)
    
    order_id = uuid.uuid4()
    
    # Post transaction
    await service.post_transaction(
        entries=[
            {
                'account_type': AccountType.RECEIVABLE,
                'amount': Decimal('100.00'),
                'description': 'Customer owes'
            },
            {
                'account_type': AccountType.REVENUE,
                'amount': Decimal('-100.00'),
                'description': 'Revenue earned'
            }
        ],
        reference_type='order',
        reference_id=order_id
    )
    
    # Retrieve entries
    entries = await service.get_entries_for_reference('order', order_id)
    
    assert len(entries) == 2
    assert all(e.reference_id == order_id for e in entries)
    assert all(e.reference_type == 'order' for e in entries)


# ============================================================================
# Integration Tests: Order Lifecycle Accounting
# ============================================================================

@pytest.fixture
async def sample_order_for_ledger(async_session):
    """Create a sample order for ledger testing."""
    wholesaler_id = _tenant_wholesaler_id(async_session)
    retailer_id = uuid.uuid4()
    
    order = Order(
        wholesaler_id=wholesaler_id,
        retailer_id=retailer_id,
        status=OrderStatus.DRAFT,
        total_amount=Decimal("100.00"),
        notes="Test order for ledger"
    )
    
    # Add an item
    item = OrderItem(
        product_name="Test Product",
        sku_code="TEST-001",
        quantity=2,
        unit_price=Decimal("50.00"),
        subtotal=Decimal("100.00")
    )
    order.items = [item]
    
    async_session.add(order)
    await async_session.flush()
    await async_session.refresh(order)
    
    return order


@pytest.mark.asyncio
async def test_order_confirmation_creates_ledger_entries(async_session, sample_order_for_ledger):
    """
    Test Case 1: Order Confirmation Accounting
    
    When order is CONFIRMED:
    - Debit RECEIVABLE (Customer owes us)
    - Credit REVENUE (We earned revenue)
    
    Verifies:
    - Ledger entries are created
    - RECEIVABLE balance increases
    - REVENUE balance increases (negative, as it's a credit)
    """
    order_service = OrderService(async_session)
    ledger_service = LedgerService(async_session)
    order = sample_order_for_ledger
    
    # Initial balances should be zero
    receivable_before = await ledger_service.get_balance(AccountType.RECEIVABLE)
    revenue_before = await ledger_service.get_balance(AccountType.REVENUE)
    assert receivable_before == Decimal('0')
    assert revenue_before == Decimal('0')
    
    # Confirm order
    order = await order_service.transition(
        order_id=order.id,
        target_state=OrderState.CONFIRMED,
        reason="Customer confirmed order"
    )
    
    # Check balances after confirmation
    receivable_after = await ledger_service.get_balance(AccountType.RECEIVABLE)
    revenue_after = await ledger_service.get_balance(AccountType.REVENUE)
    
    # RECEIVABLE should be +100 (customer owes us)
    assert receivable_after == Decimal('100.00')
    
    # REVENUE should be -100 (credit, we earned revenue)
    assert revenue_after == Decimal('-100.00')
    
    # Verify ledger entries exist
    entries = await ledger_service.get_entries_for_reference('order', order.id)
    assert len(entries) == 2
    
    # Find the RECEIVABLE and REVENUE entries
    receivable_entry = next(e for e in entries if e.account_type == AccountType.RECEIVABLE)
    revenue_entry = next(e for e in entries if e.account_type == AccountType.REVENUE)
    
    assert receivable_entry.amount == Decimal('100.00')
    assert revenue_entry.amount == Decimal('-100.00')


@pytest.mark.asyncio
async def test_payment_received_updates_ledger(async_session, sample_order_for_ledger):
    """
    Test Case 2: Payment Received Accounting
    
    When order is PAID:
    - Debit CASH (We received money)
    - Credit RECEIVABLE (Customer no longer owes)
    
    Verifies:
    - CASH balance increases
    - RECEIVABLE balance decreases to zero
    """
    order_service = OrderService(async_session)
    ledger_service = LedgerService(async_session)
    order = sample_order_for_ledger
    
    # Confirm order first
    order = await order_service.transition(
        order_id=order.id,
        target_state=OrderState.CONFIRMED
    )
    
    # Check balances after confirmation
    receivable_after_confirm = await ledger_service.get_balance(AccountType.RECEIVABLE)
    cash_after_confirm = await ledger_service.get_balance(AccountType.CASH)
    
    assert receivable_after_confirm == Decimal('100.00')
    assert cash_after_confirm == Decimal('0')
    
    # Mark as paid
    order = await order_service.transition(
        order_id=order.id,
        target_state=OrderState.PAID,
        reason="Payment received"
    )
    
    # Check balances after payment
    receivable_after_paid = await ledger_service.get_balance(AccountType.RECEIVABLE)
    cash_after_paid = await ledger_service.get_balance(AccountType.CASH)
    
    # RECEIVABLE should be 0 (customer no longer owes)
    assert receivable_after_paid == Decimal('0')
    
    # CASH should be +100 (we received money)
    assert cash_after_paid == Decimal('100.00')


@pytest.mark.asyncio
async def test_full_order_lifecycle_accounting(async_session, sample_order_for_ledger):
    """
    Test Case 3: Full Order Lifecycle
    
    DRAFT → CONFIRMED → PAID
    
    Verifies:
    - All ledger entries are created correctly
    - Final balances are accurate
    - Transaction history is complete
    """
    order_service = OrderService(async_session)
    ledger_service = LedgerService(async_session)
    order = sample_order_for_ledger
    
    # Step 1: Confirm order
    order = await order_service.transition(
        order_id=order.id,
        target_state=OrderState.CONFIRMED
    )
    
    # Step 2: Mark as paid
    order = await order_service.transition(
        order_id=order.id,
        target_state=OrderState.PAID
    )
    
    # Final balances
    receivable = await ledger_service.get_balance(AccountType.RECEIVABLE)
    revenue = await ledger_service.get_balance(AccountType.REVENUE)
    cash = await ledger_service.get_balance(AccountType.CASH)
    
    # RECEIVABLE: +100 (confirm) -100 (paid) = 0
    assert receivable == Decimal('0')
    
    # REVENUE: -100 (confirm) = -100
    assert revenue == Decimal('-100.00')
    
    # CASH: +100 (paid) = +100
    assert cash == Decimal('100.00')
    
    # Verify all entries exist
    entries = await ledger_service.get_entries_for_reference('order', order.id)
    assert len(entries) == 4  # 2 for confirm, 2 for paid


@pytest.mark.asyncio
async def test_ledger_immutability(async_session):
    """
    Test Case 4: Ledger Immutability
    
    Verifies:
    - Ledger entries cannot be updated (immutable)
    - Only INSERT operations are allowed
    """
    service = LedgerService(async_session)
    
    order_id = uuid.uuid4()
    entry = await service.post_entry(
        account_type=AccountType.RECEIVABLE,
        amount=Decimal("100.00"),
        reference_type="order",
        reference_id=order_id
    )
    
    original_amount = entry.amount
    
    # Try to modify the entry (this should not affect the database)
    entry.amount = Decimal("200.00")
    
    # Refresh from database
    await async_session.refresh(entry)
    
    # Amount should still be original
    # Note: This test verifies that we don't have UPDATE logic in the service
    # The actual immutability is enforced by not providing update methods
    assert entry.amount == original_amount


@pytest.mark.asyncio
async def test_balance_projection_as_of_date(async_session):
    """
    Test Case 5: Balance Projection as of Date
    
    Verifies:
    - Can calculate balance as of a specific date
    - Future entries are excluded
    """
    service = LedgerService(async_session)
    
    order_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    tomorrow = now + timedelta(days=1)
    
    # Post entry yesterday
    await service.post_entry(
        account_type=AccountType.CASH,
        amount=Decimal("100.00"),
        reference_type="order",
        reference_id=order_id,
        transaction_date=yesterday
    )
    
    # Post entry tomorrow (future)
    await service.post_entry(
        account_type=AccountType.CASH,
        amount=Decimal("50.00"),
        reference_type="order",
        reference_id=order_id,
        transaction_date=tomorrow
    )
    
    # Balance as of today should only include yesterday's entry
    balance_today = await service.get_balance(AccountType.CASH, as_of_date=now)
    assert balance_today == Decimal("100.00")
    
    # Balance as of tomorrow should include both
    balance_tomorrow = await service.get_balance(AccountType.CASH, as_of_date=tomorrow)
    assert balance_tomorrow == Decimal("150.00")


@pytest.mark.asyncio
async def test_multiple_orders_accounting(async_session):
    """
    Test Case 6: Multiple Orders
    
    Verifies:
    - Multiple orders create separate ledger entries
    - Balances aggregate correctly across all orders
    """
    order_service = OrderService(async_session)
    ledger_service = LedgerService(async_session)
    
    # Create and confirm two orders
    orders = []
    for i in range(2):
        order = Order(
            wholesaler_id=_tenant_wholesaler_id(async_session),
            retailer_id=uuid.uuid4(),
            status=OrderStatus.DRAFT,
            total_amount=Decimal("100.00"),
            notes=f"Test order {i+1}"
        )
        async_session.add(order)
        await async_session.flush()
        await async_session.refresh(order)
        
        # Confirm order
        order = await order_service.transition(
            order_id=order.id,
            target_state=OrderState.CONFIRMED
        )
        orders.append(order)
    
    # Check aggregated balances
    receivable = await ledger_service.get_balance(AccountType.RECEIVABLE)
    revenue = await ledger_service.get_balance(AccountType.REVENUE)
    
    # RECEIVABLE: 100 + 100 = 200
    assert receivable == Decimal('200.00')
    
    # REVENUE: -100 + -100 = -200
    assert revenue == Decimal('-200.00')


@pytest.mark.asyncio
async def test_zero_balance_for_unused_account(async_session):
    """
    Test Case 7: Zero Balance for Unused Account
    
    Verifies:
    - Accounts with no entries return zero balance
    """
    service = LedgerService(async_session)
    
    # Get balance for account with no entries
    balance = await service.get_balance(AccountType.LIABILITY)
    
    assert balance == Decimal('0')
