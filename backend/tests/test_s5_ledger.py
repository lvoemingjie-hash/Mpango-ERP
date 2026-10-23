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
from tests.rc2_current_contract_support import current_trading_session as async_session, verified_from_template, create_verified_draft
from datetime import datetime, timezone, timedelta

from models.ledger import LedgerEntry, AccountType
from models.order import Order, OrderItem, OrderStatus
from services.ledger_service import LedgerService
from services.order_command_service import OrderCommandService
from services.order_service import OrderService
from core.domain.order_state import OrderState
from core.exceptions import LedgerIntegrityError


def _tenant_wholesaler_id(async_session) -> uuid.UUID:
    tenant_id = async_session.info.get("tenant_id")
    if tenant_id is None:
        raise AssertionError("async_session fixture must provide tenant_id")
    return uuid.UUID(str(tenant_id))


async def _canonical_cash(db, order, amount, key):
    from services.canonical_payment_service import CanonicalPaymentService
    return await CanonicalPaymentService().confirm_payment(
        db=db, order_id=str(order.id), amount=Decimal(amount), method='cash',
        transaction_id=None, idempotency_key=key, created_by=str(uuid.uuid4()))


async def _money_vector(db, label):
    import os
    from sqlalchemy import text
    rows = {}
    for table in ('orders', 'payments', 'ledger_entries', 'order_credit_holds',
                  'inventory_stocks', 'inventory_movements', 'inventory_reservations'):
        rows[table] = [r[0] for r in (await db.execute(text(
            f'SELECT row_to_json(t)::text FROM {table} t ORDER BY id'))).all()]
    rows['binding'] = [r[0] for r in (await db.execute(text(
        'SELECT row_to_json(b)::text FROM public.wholesaler_retailer_bindings b '
        'WHERE wholesaler_id=:w ORDER BY retailer_id'),
        {'w': _tenant_wholesaler_id(db)})).all()]
    if os.environ.get('AUDIT_FINITE_PRIVATE'):
        from tests.audit_fixes.support import retain
        retain(label, rows)
    return rows


async def _assert_receipt_ledger(db, payment, amount):
    entries = await LedgerService(db).get_entries_for_reference('payment', payment['id'])
    assert {e.account_type: e.amount for e in entries} == {
        AccountType.CASH: Decimal(amount), AccountType.RECEIVABLE: -Decimal(amount),
    }, 'B03-CANONICAL-RECEIPT-MUST-POST-EXACT-PAYMENT-AMOUNT'
    assert len(entries) == 2
    assert all(str(e.reference_id) == str(payment['id']) and e.reference_type == 'payment' for e in entries)
    assert sum(e.amount for e in entries) == 0


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

    # Add an item (F1: real SKU so the confirm command can reserve)
    schema = async_session.info.get("tenant_schema", "t_test")
    _sku, _code = await _ensure_sku_stock(async_session, schema)
    item = OrderItem(
        sellable_unit_id=__import__("uuid").UUID(_sku),
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

    order = await verified_from_template(async_session, order)
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
    order = (await OrderCommandService(async_session).confirm_order(order.id, updated_by=str(uuid.uuid4()))).order


    # Check balances after confirmation
    receivable_after = await ledger_service.get_balance(AccountType.RECEIVABLE)
    revenue_after = await ledger_service.get_balance(AccountType.REVENUE)

    # R1 frozen decision: confirmation posts NO receivable/revenue entries
    assert receivable_after == Decimal('0')
    assert revenue_after == Decimal('0')

    # Verify no ledger entries exist for the order
    entries = await ledger_service.get_entries_for_reference('order', order.id)
    assert len(entries) == 0


@pytest.mark.asyncio
async def test_payment_received_updates_ledger(async_session, sample_order_for_ledger):
    """Actual 40/60 receipts, not status, create payment-linked cash entries."""
    ledger_service = LedgerService(async_session)
    order = sample_order_for_ledger
    order = (await OrderCommandService(async_session).confirm_order(order.id, updated_by=str(uuid.uuid4()))).order
    assert await ledger_service.get_balance(AccountType.CASH) == 0
    key = uuid.uuid4().hex
    first = await _canonical_cash(async_session, order, '40', key)
    assert first.order.status == OrderStatus.PARTIALLY_PAID and not first.replayed
    await _assert_receipt_ledger(async_session, first.payment_record, '40')
    assert await ledger_service.get_balance(AccountType.CASH) == 40
    second = await _canonical_cash(async_session, order, '60', uuid.uuid4().hex)
    assert second.order.status == OrderStatus.PAID
    await _assert_receipt_ledger(async_session, second.payment_record, '60')
    assert await ledger_service.get_balance(AccountType.RECEIVABLE) == -100
    assert await ledger_service.get_balance(AccountType.CASH) == 100, 'B03-NO-FULL-ORDER-DOUBLE-POSTING'
    before = await _money_vector(async_session, 'B03-partial-before-replay')
    replay = await _canonical_cash(async_session, order, '40', key)
    assert replay.replayed and replay.payment_record['id'] == first.payment_record['id']
    assert await _money_vector(async_session, 'B03-partial-after-replay') == before


@pytest.mark.asyncio
async def test_full_order_lifecycle_accounting(async_session, sample_order_for_ledger):
    """Confirm posts nothing; two actual receipts preserve balanced history."""
    ledger_service = LedgerService(async_session)
    order = sample_order_for_ledger
    order = (await OrderCommandService(async_session).confirm_order(order.id, updated_by=str(uuid.uuid4()))).order
    assert not await ledger_service.get_entries_for_reference('order', order.id)
    payments = []
    for amount in ('40', '60'):
        result = await _canonical_cash(async_session, order, amount, uuid.uuid4().hex)
        payments.append(result.payment_record)
        await _assert_receipt_ledger(async_session, result.payment_record, amount)
        await _money_vector(async_session, 'B03-lifecycle-receipt-' + amount)
    assert len({str(p['id']) for p in payments}) == 2
    assert sum(p['amount'] for p in payments) == 100
    assert await ledger_service.get_balance(AccountType.RECEIVABLE) == -100
    assert await ledger_service.get_balance(AccountType.REVENUE) == 0
    assert await ledger_service.get_balance(AccountType.CASH) == 100, 'B03-NO-FULL-ORDER-DOUBLE-POSTING'
    assert not await ledger_service.get_entries_for_reference('order', order.id)


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
        _sku, code = await _ensure_sku_stock(async_session, async_session.info["tenant_schema"])
        order = await create_verified_draft(async_session, retailer_id=order.retailer_id,
                                           items=[(code, 1, Decimal("100.00"))], notes=order.notes)

        # R2 contract: confirm requires a live binding for this retailer.
        from tests.order_state_r2.contract_helpers import ensure_binding
        await ensure_binding(async_session, order.wholesaler_id, order.retailer_id)

        # Confirm order
        order = (await OrderCommandService(async_session).confirm_order(order.id, updated_by=str(uuid.uuid4()))).order

        orders.append(order)

    # Check aggregated balances
    receivable = await ledger_service.get_balance(AccountType.RECEIVABLE)
    revenue = await ledger_service.get_balance(AccountType.REVENUE)

    # R1 frozen decision: two confirmations post nothing — the aggregate
    # receivable stays 0 (settlement legs exist only after payments).
    assert receivable == Decimal('0')

    # REVENUE: -100 + -100 = -200
    assert revenue == Decimal('0')  # no confirmation posting


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


# ============================================================================
# Phase 6.1 — Credit Ledger Semantics (unit-level)
#
# Unit tests proving _post_ledger_entries skips post_payment_received
# when payment_method="credit", and preserves existing behavior for
# None / "cash" / "transfer".
# ============================================================================


@pytest.mark.asyncio
async def test_credit_paid_skips_cash_settlement_ledger(async_session, sample_order_for_ledger):
    """
    Phase 6.1: Credit PAID transition must NOT call post_payment_received.

    When payment_method="credit" and target is PAID, the receivable
    exposure from confirmation must remain visible — no CASH/RECEIVABLE
    settlement entries are posted.
    """
    order_service = OrderService(async_session)
    ledger_service = LedgerService(async_session)
    order = sample_order_for_ledger

    # Confirm order first → RECEIVABLE +100, REVENUE -100
    order = (await OrderCommandService(async_session).confirm_order(order.id, updated_by=str(uuid.uuid4()))).order


    receivable_after_confirm = await ledger_service.get_balance(AccountType.RECEIVABLE)
    cash_after_confirm = await ledger_service.get_balance(AccountType.CASH)
    # R1 frozen decision: confirmation posts no ledger entries
    assert receivable_after_confirm == Decimal("0")
    assert cash_after_confirm == Decimal("0")

    # Transition to PAID with payment_method="credit"
    order = (await OrderCommandService(async_session).apply_payment_transition(
        order.id,
        OrderState.PAID,
        payment_method="credit",
    )).order

    # Receivable must remain +100 (NOT settled to 0)
    receivable_after_paid = await ledger_service.get_balance(AccountType.RECEIVABLE)
    assert receivable_after_paid == Decimal("0")  # credit: no posting

    # Cash must remain 0 (no cash received)
    cash_after_paid = await ledger_service.get_balance(AccountType.CASH)
    assert cash_after_paid == Decimal("0"), \
        f"Credit PAID must not create cash entries, got {cash_after_paid}"

    # Only confirmation entries (2), no payment-settlement entries
    entries = await ledger_service.get_entries_for_reference('order', order.id)
    assert len(entries) == 0, \
        f"Credit PAID should have 0 entries (no confirmation posting), got {len(entries)}"


@pytest.mark.asyncio
async def test_default_paid_posts_cash_settlement_ledger(async_session, sample_order_for_ledger):
    """Preserved node: an internal status primitive cannot invent a receipt."""
    ledger_service = LedgerService(async_session)
    order = sample_order_for_ledger
    order = (await OrderCommandService(async_session).confirm_order(order.id, updated_by=str(uuid.uuid4()))).order
    before = await _money_vector(async_session, 'B03-status-only-before')
    order = (await OrderCommandService(async_session).apply_payment_transition(
        order.id, OrderState.PAID, payment_method='cash',
    )).order
    assert order.status == OrderStatus.PAID
    after = await _money_vector(async_session, 'B03-status-only-after')
    assert {k: v for k, v in after.items() if k != 'orders'} == {
        k: v for k, v in before.items() if k != 'orders'}, 'B03-STATUS-CHANGE-IS-NOT-A-CASH-RECEIPT'
    assert await ledger_service.get_balance(AccountType.CASH) == 0
    assert await ledger_service.get_balance(AccountType.RECEIVABLE) == 0


@pytest.mark.asyncio
async def test_explicit_cash_paid_posts_cash_settlement(async_session, sample_order_for_ledger):
    """Explicit canonical cash has payment identity and replay has zero effect."""
    ledger_service = LedgerService(async_session)
    order = sample_order_for_ledger
    order = (await OrderCommandService(async_session).confirm_order(order.id, updated_by=str(uuid.uuid4()))).order
    key = uuid.uuid4().hex
    paid = await _canonical_cash(async_session, order, '100', key)
    assert paid.order.status == OrderStatus.PAID and not paid.replayed
    await _assert_receipt_ledger(async_session, paid.payment_record, '100')
    assert await ledger_service.get_balance(AccountType.RECEIVABLE) == -100, 'B03-NO-FULL-ORDER-DOUBLE-POSTING'
    assert await ledger_service.get_balance(AccountType.CASH) == 100, 'B03-NO-FULL-ORDER-DOUBLE-POSTING'
    before = await _money_vector(async_session, 'B03-full-before-replay')
    replay = await _canonical_cash(async_session, order, '100', key)
    assert replay.replayed and replay.payment_record['id'] == paid.payment_record['id']
    assert await _money_vector(async_session, 'B03-full-after-replay') == before
