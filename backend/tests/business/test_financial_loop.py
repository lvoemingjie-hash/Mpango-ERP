"""
v0.2.0 QA — Financial Closed-Loop Integration Test (A项)

Scenario:
    1. Create a DRAFT order for $100
    2. Transition DRAFT → CONFIRMED  (Ledger: +100 RECEIVABLE, -100 REVENUE)
    3. Transition CONFIRMED → PAID   (Ledger: +100 CASH, -100 RECEIVABLE)
    4. Transition PAID → FULFILLED

Assertions:
    - After CONFIRMED: RECEIVABLE balance = +100, REVENUE balance = -100
    - After PAID: CASH balance = +100, RECEIVABLE balance = 0 (net)
    - After FULFILLED: Order status is FULFILLED (terminal)
    - Inventory deduction is NOT yet implemented (documented gap)
"""
import uuid
from decimal import Decimal

import pytest

from core.domain.order_state import OrderState
from models.ledger import AccountType
from models.order import Order, OrderStatus
from services.ledger_service import LedgerService
from services.order_service import OrderService


@pytest.mark.asyncio
async def test_order_confirm_pay_fulfill_ledger_entries(async_session):
    """Full financial loop: Order $100 → Confirm → Pay → Fulfill."""

    tenant_id = async_session.info["tenant_id"]
    retailer_id = str(uuid.uuid4())

    # ── Step 0: Create DRAFT order ────────────────────────────────
    order = Order(
        wholesaler_id=uuid.UUID(tenant_id),
        retailer_id=uuid.UUID(retailer_id),
        status=OrderStatus.DRAFT,
        total_amount=Decimal("100.00"),
        notes="QA financial loop test",
    )
    async_session.add(order)
    await async_session.commit()

    order_svc = OrderService(async_session)
    ledger_svc = LedgerService(async_session)

    # ── Step 1: DRAFT → CONFIRMED ─────────────────────────────────
    order = await order_svc.transition(order.id, OrderState.CONFIRMED)
    await async_session.commit()

    assert order.status == OrderStatus.CONFIRMED

    # Ledger check: RECEIVABLE +100, REVENUE -100
    receivable_balance = await ledger_svc.get_balance(AccountType.RECEIVABLE)
    revenue_balance = await ledger_svc.get_balance(AccountType.REVENUE)
    assert receivable_balance == Decimal("100.0000"), (
        f"Expected RECEIVABLE +100, got {receivable_balance}"
    )
    assert revenue_balance == Decimal("-100.0000"), (
        f"Expected REVENUE -100, got {revenue_balance}"
    )

    # ── Step 2: CONFIRMED → PAID ──────────────────────────────────
    order = await order_svc.transition(order.id, OrderState.PAID)
    await async_session.commit()

    assert order.status == OrderStatus.PAID

    # Ledger check: CASH +100, RECEIVABLE net 0 (+100 - 100)
    cash_balance = await ledger_svc.get_balance(AccountType.CASH)
    receivable_balance = await ledger_svc.get_balance(AccountType.RECEIVABLE)
    assert cash_balance == Decimal("100.0000"), (
        f"Expected CASH +100, got {cash_balance}"
    )
    assert receivable_balance == Decimal("0.0000"), (
        f"Expected RECEIVABLE net 0, got {receivable_balance}"
    )

    # ── Step 3: PAID → FULFILLED ──────────────────────────────────
    order = await order_svc.transition(order.id, OrderState.FULFILLED)
    await async_session.commit()

    assert order.status == OrderStatus.FULFILLED

    # ── Step 4: Verify all ledger entries ─────────────────────────
    entries = await ledger_svc.get_entries_for_reference("order", order.id)
    assert len(entries) == 4, (
        f"Expected 4 ledger entries (2 confirm + 2 payment), got {len(entries)}"
    )

    # Verify double-entry balance: sum of all entries must be 0
    total = sum(e.amount for e in entries)
    assert total == Decimal("0"), (
        f"Ledger is unbalanced! Sum of all entries = {total}"
    )


@pytest.mark.asyncio
async def test_ledger_entries_are_immutable(async_session):
    """Verify that ledger entries cannot be updated or deleted (DB trigger)."""

    tenant_id = async_session.info["tenant_id"]
    retailer_id = str(uuid.uuid4())

    order = Order(
        wholesaler_id=uuid.UUID(tenant_id),
        retailer_id=uuid.UUID(retailer_id),
        status=OrderStatus.DRAFT,
        total_amount=Decimal("50.00"),
        notes="Immutability test",
    )
    async_session.add(order)
    await async_session.commit()

    order_svc = OrderService(async_session)
    await order_svc.transition(order.id, OrderState.CONFIRMED)
    await async_session.commit()

    ledger_svc = LedgerService(async_session)
    entries = await ledger_svc.get_entries_for_reference("order", order.id)
    assert len(entries) == 2

    # Attempt to update a ledger entry — should be blocked by DB trigger
    from sqlalchemy import text

    with pytest.raises(Exception) as exc:
        await async_session.execute(
            text(
                'UPDATE ledger_entries SET amount = 999 WHERE id = :eid'
            ),
            {"eid": str(entries[0].id)},
        )
    assert "immutable" in str(exc.value).lower() or "integrity" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_inventory_deduction_gap_documented(async_session):
    """
    Document that inventory deduction on FULFILLED is NOT yet implemented.

    The OrderService._emit_state_changed_event is a TODO stub.
    This test explicitly verifies the gap exists so it can be tracked.
    """
    tenant_id = async_session.info["tenant_id"]
    retailer_id = str(uuid.uuid4())

    order = Order(
        wholesaler_id=uuid.UUID(tenant_id),
        retailer_id=uuid.UUID(retailer_id),
        status=OrderStatus.DRAFT,
        total_amount=Decimal("100.00"),
        notes="Inventory gap test",
    )
    async_session.add(order)
    await async_session.commit()

    order_svc = OrderService(async_session)
    await order_svc.transition(order.id, OrderState.CONFIRMED)
    await async_session.commit()
    await order_svc.transition(order.id, OrderState.PAID)
    await async_session.commit()
    order = await order_svc.transition(order.id, OrderState.FULFILLED)
    await async_session.commit()

    assert order.status == OrderStatus.FULFILLED

    # Verify: No inventory deduction logic exists in OrderService.transition
    # The _emit_state_changed_event method is a pass-through stub
    # This test passes to document the gap — when inventory deduction is
    # implemented, this test should be updated to assert stock changes.
    ledger_svc = LedgerService(async_session)
    entries = await ledger_svc.get_entries_for_reference("order", order.id)

    # Only 4 entries (confirm + pay), no fulfillment/inventory entries
    assert len(entries) == 4, (
        f"Expected 4 entries (no inventory entries yet), got {len(entries)}"
    )
