"""Order command service — the ONLY production order-status writer (R1).

CTO-AUTH-MPANGO-ORDER-STATE-AUTHORITY-R1-IMPLEMENTATION-2026-09-15.
Frozen business decisions implemented here:

- Confirm: locked-fresh read -> domain validation -> deterministic stock
  locks -> availability + reservations -> CONFIRMED -> credit reservation
  on the retailer binding. NO receivable/revenue/payment ledger entries
  (the former service-path ``post_order_confirmation`` is gone; there is
  deliberately NO configuration switch to bring it back).
- Cancel: locked-fresh read -> domain validation -> EXPLICIT rejection of
  locked-fresh PAID/PARTIALLY_PAID with 409 REFUND_WORKFLOW_NOT_IMPLEMENTED
  (temporary fail-closed: refund/funds disposition is not implemented; this
  is NOT stated as a permanent business prohibition) -> release owned
  reservations with aggregate updates -> CANCELLED.
- Every FOR UPDATE read used for a state decision uses
  ``populate_existing=True``; the check, the side effects and the single
  status assignment all act on that same refreshed object.
- Ordinary draft cancellation results in CANCELLED (the domain matrix
  gained the DRAFT->CANCELLED edge). VOIDED stays an internal state and is
  written by no route.
- Notification intents are typed, request-private values returned to the
  caller on the command result. They never touch ORM objects, module
  globals or public responses, and nothing is sent before the caller's
  transaction commits. Recipients are resolved from real retailer contact
  data at dispatch time; no placeholder addresses or phone numbers exist
  anywhere in this module.

Transaction ownership: the caller (HTTP tenant middleware or test harness)
owns the transaction; every command here runs inside it and never commits.

Lock order (see order-state-r1/LOCK-ORDER.md): the order row is always
locked FIRST; every distinct stock row is then locked in ONE global order
— sorted by sku_id (UUID), deduplicated — BEFORE any inventory write
(``_prelock_stocks`` for item-derived references in confirm/fulfill/
return). Cancel derives its stock set from the order's ACTIVE
RESERVATIONS (``_prelock_reservation_stocks``), locked by
reservation.sku_id in the same global sorted order, and only then locks
the owned reservation rows FOR UPDATE ordered by (sku_code, id) — the
historical cancel inverse order (reservations before stocks) is closed.
A legacy DRAFT order (no active reservations) cancels as a pure status
transition. A full cross-order proof and its limits are documented in
the implementation report.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.order_state import (
    InvalidStateTransitionError,
    OrderInvariantViolation,
    OrderState,
    is_terminal_state,
    is_valid_transition,
)
from core.structured_logging import get_logger
from models.inventory_reservation import InventoryReservation
from models.order import Order

logger = get_logger(__name__)

# Temporary fail-closed policy (CTO frozen decision): refund / funds
# disposition is not implemented in this round.
REFUND_WORKFLOW_NOT_IMPLEMENTED = "REFUND_WORKFLOW_NOT_IMPLEMENTED"

# F1: the generic transition path must NEVER perform a bare-state write for
# these targets — each has an explicit command (confirm/cancel/fulfill/
# return) or the canonical payment service (PAID/PARTIALLY_PAID).
COMMAND_OWNED_TARGETS = frozenset(
    {OrderState.CONFIRMED, OrderState.CANCELLED, OrderState.PAID,
     OrderState.PARTIALLY_PAID, OrderState.FULFILLED, OrderState.RETURNED})


@dataclass(frozen=True)
class OrderNotificationIntent:
    """Request-private notification intent (typed, no recipient baked in).

    Recipients are resolved from real retailer contact data at dispatch
    time by the post-commit dispatcher.
    """

    event: str            # "order_confirmed" | "order_fulfilled"
    order_id: uuid.UUID
    retailer_id: uuid.UUID


@dataclass
class OrderCommandResult:
    """Typed command result; carries request-private notification intents."""

    order: Order
    released_reservations: list[InventoryReservation] = field(default_factory=list)
    credit_reserved: Optional[Decimal] = None
    notification_intents: list[OrderNotificationIntent] = field(default_factory=list)


def _conflict(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": message},
    )


class OrderCommandService:
    """Single production writer of ``orders.status``.

    The one and only direct status-assignment statement lives in
    :meth:`_assign_status`. Static guard:
    ``tests/order_state_r1/test_static_guards.py``.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._locked_order: Optional[Order] = None

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def confirm_order(
        self,
        order_id: uuid.UUID,
        *,
        updated_by: Optional[str] = None,
    ) -> OrderCommandResult:
        """Confirm a DRAFT order: reserve inventory, reserve credit, CONFIRMED.

        No ledger entries of any kind are posted (frozen business decision).
        """
        order = await self._load_locked(order_id)

        self._validate_transition(order, OrderState.CONFIRMED)
        self._validate_item_identities(order)

        items = sorted(order.items, key=lambda i: str(i.sellable_unit_id))
        for item in items:
            if item.sellable_unit_id is None:
                raise _conflict(
                    "ORDER_ITEM_SELLABLE_ID_REQUIRED",
                    f"Order item '{item.id}' requires explicit legacy mapping",
                )
        stocks = await self._prelock_stocks(items, require_active=True)

        reservations = await self._reserve_inventory(order, stocks)

        self._assign_status(order, OrderState.CONFIRMED, updated_by)
        await self.db.flush()

        credit_reserved = await self._reserve_credit(order)

        return OrderCommandResult(
            order=order,
            released_reservations=[],
            credit_reserved=credit_reserved,
            notification_intents=[
                OrderNotificationIntent(
                    event="order_confirmed",
                    order_id=order.id,
                    retailer_id=order.retailer_id,
                ),
            ],
        )

    async def cancel_order(
        self,
        order_id: uuid.UUID,
        *,
        updated_by: Optional[str] = None,
    ) -> OrderCommandResult:
        """Cancel a DRAFT or CONFIRMED order, releasing owned reservations.

        Locked-fresh PAID/PARTIALLY_PAID are rejected 409
        REFUND_WORKFLOW_NOT_IMPLEMENTED (temporary fail-closed policy).
        VOIDED is deliberately NOT the ordinary cancel result.
        """
        order = await self._load_locked(order_id)

        self._validate_transition(order, OrderState.CANCELLED)

        # Frozen decision: fail-closed until refund/funds disposition exists.
        if order.status.value in ("paid", "partially_paid"):
            raise _conflict(
                REFUND_WORKFLOW_NOT_IMPLEMENTED,
                "Cancellation of paid or partially paid orders is not "
                "available because the refund/funds disposition workflow "
                "is not implemented",
            )

        # F3: the cancel stock set derives from the order's ACTIVE
        # RESERVATIONS, never from order.items — legacy DRAFT orders (no
        # reservations) cancel cleanly, and legacy orders WITH reservations
        # release exactly what was reserved, pre-locked by
        # reservation.sku_id in the global sorted order.
        stocks = await self._prelock_reservation_stocks(order)

        released = await self._release_reservations(order, stocks)

        self._assign_status(order, OrderState.CANCELLED, updated_by)
        await self.db.flush()

        return OrderCommandResult(
            order=order,
            released_reservations=released,
            credit_reserved=None,
            notification_intents=[],
        )

    async def apply_transition(
        self,
        order_id: uuid.UUID,
        target_state: OrderState,
        *,
        reason: Optional[str] = None,
        updated_by: Optional[str] = None,
        payment_method: Optional[str] = None,
    ) -> OrderCommandResult:
        """General locked-fresh transition used by pay/fulfill/return paths.

        Financial effects preserved from the former OrderService.transition:
        PAID (non-credit) posts the cash-settlement entries, PAID with
        method=credit deliberately posts none (credit exposure stays
        visible), RETURNED posts the reversal entries. CONFIRMED posts
        nothing (frozen decision — the former receivable/revenue posting
        was removed, and no switch exists to restore it).
        """
        if target_state in COMMAND_OWNED_TARGETS:
            raise InvalidStateTransitionError(
                from_state=target_state,
                to_state=target_state,
                reason=(
                    "Generic transition refuses command-owned targets; use "
                    "confirm_order/cancel_order/fulfill_order/return_order "
                    "or the canonical payment service"),
            )

        order = await self._load_locked(order_id)

        is_additional_partial_payment = (
            order.status.value == OrderState.PARTIALLY_PAID.value
            and target_state == OrderState.PARTIALLY_PAID
            and payment_method in {"cash", "transfer"}
        )
        if not is_valid_transition(
            OrderState(order.status.value), target_state
        ) and not is_additional_partial_payment:
            raise InvalidStateTransitionError(
                from_state=OrderState(order.status.value),
                to_state=target_state,
                reason="Transition not allowed by state machine",
            )

        self._locked_order = order
        self._check_invariants(OrderState(order.status.value), target_state)

        ledger_result = await self._post_transition_ledger(
            order, OrderState(order.status.value), target_state, payment_method
        )

        self._assign_status(order, target_state, updated_by)

        await self.db.flush()
        await self.db.refresh(order)

        intents: list[OrderNotificationIntent] = []
        if target_state == OrderState.CONFIRMED:
            intents.append(OrderNotificationIntent(
                event="order_confirmed",
                order_id=order.id,
                retailer_id=order.retailer_id,
            ))
        elif target_state == OrderState.FULFILLED:
            intents.append(OrderNotificationIntent(
                event="order_fulfilled",
                order_id=order.id,
                retailer_id=order.retailer_id,
            ))

        logger.info(
            f"Order state transition: {order.status.value if False else target_state.value}",
            extra={
                "order_id": str(order_id),
                "to_state": target_state.value,
                "reason": reason,
                "updated_by": str(updated_by) if updated_by else None,
            },
        )
        return OrderCommandResult(order=order, notification_intents=intents)

    async def fulfill_order(
        self,
        order_id: uuid.UUID,
        *,
        updated_by: Optional[str] = None,
    ) -> OrderCommandResult:
        """Fulfill a PAID order: pre-lock ALL stocks (deduped, sorted
        sku_id) BEFORE any inventory write, then consume reservations,
        deduct stock, journal movements, set FULFILLED."""
        from services.inventory_service import InventoryService

        order = await self._load_locked(order_id)
        self._locked_order = order
        self._validate_transition(order, OrderState.FULFILLED)
        self._check_invariants(OrderState(order.status.value), OrderState.FULFILLED)

        items = sorted(
            order.items,
            key=lambda i: str(i.sellable_unit_id or i.id),
        )
        missing = [i for i in items if i.sellable_unit_id is None]
        if missing:
            raise _conflict(
                "ORDER_ITEM_SELLABLE_ID_REQUIRED",
                f"Order item '{missing[0].id}' requires explicit legacy "
                "mapping before fulfillment",
            )
        stocks = await self._prelock_stocks(items)

        inventory = InventoryService()
        for item in items:
            await inventory.deduct_on_fulfillment(
                self.db,
                sellable_unit_id=item.sellable_unit_id,
                sku_code=item.sku_code,
                quantity=Decimal(str(item.quantity)),
                order_id=order.id,
                order_item_id=item.id,
                fulfilled_by=updated_by,
            )

        self._assign_status(order, OrderState.FULFILLED, updated_by)
        await self.db.flush()
        return OrderCommandResult(
            order=order,
            notification_intents=[OrderNotificationIntent(
                event="order_fulfilled",
                order_id=order.id,
                retailer_id=order.retailer_id)],
        )

    async def return_order(
        self,
        order_id: uuid.UUID,
        *,
        updated_by: Optional[str] = None,
    ) -> OrderCommandResult:
        """Return a FULFILLED order: ledger reversal first, pre-lock ALL
        stocks (deduped, sorted sku_id) BEFORE any inventory write, restock,
        journal movements, set RETURNED."""
        from services.inventory_service import InventoryService

        order = await self._load_locked(order_id)
        self._locked_order = order
        self._validate_transition(order, OrderState.RETURNED)
        self._check_invariants(OrderState(order.status.value), OrderState.RETURNED)

        items = sorted(
            order.items,
            key=lambda i: str(i.sellable_unit_id or i.id),
        )
        missing = [i for i in items if i.sellable_unit_id is None]
        if missing:
            raise _conflict(
                "ORDER_ITEM_SELLABLE_ID_REQUIRED",
                f"Order item '{missing[0].id}' requires explicit legacy "
                "mapping before return restock",
            )

        await self._post_transition_ledger(
            order, OrderState(order.status.value), OrderState.RETURNED, None)

        stocks = await self._prelock_stocks(items)

        inventory = InventoryService()
        for item in items:
            await inventory.restock_on_return(
                self.db,
                sellable_unit_id=item.sellable_unit_id,
                sku_code=item.sku_code,
                quantity=Decimal(str(item.quantity)),
                order_id=order.id,
                returned_by=updated_by,
            )

        self._assign_status(order, OrderState.RETURNED, updated_by)
        await self.db.flush()
        return OrderCommandResult(order=order)

    async def apply_payment_transition(
        self,
        order_id: uuid.UUID,
        target_state: OrderState,
        *,
        payment_method: Optional[str] = None,
        updated_by: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> OrderCommandResult:
        """EXPLICIT payment transition — the only writer for PAID /
        PARTIALLY_PAID, called solely by CanonicalPaymentService.

        Allows CONFIRMED/PARTIALLY_PAID -> PAID/PARTIALLY_PAID (plus the
        same-state partial-payment progress with cash/transfer context).
        """
        order = await self._load_locked(order_id)
        self._locked_order = order
        current = OrderState(order.status.value)

        is_additional_partial_payment = (
            current == OrderState.PARTIALLY_PAID
            and target_state == OrderState.PARTIALLY_PAID
            and payment_method in {"cash", "transfer"}
        )
        allowed = (
            (current == OrderState.CONFIRMED
             and target_state in (OrderState.PAID, OrderState.PARTIALLY_PAID))
            or (current == OrderState.PARTIALLY_PAID
                and target_state == OrderState.PAID)
            or is_additional_partial_payment
        )
        if not allowed:
            raise InvalidStateTransitionError(
                from_state=current,
                to_state=target_state,
                reason="Invalid payment transition",
            )

        ledger_result = await self._post_transition_ledger(
            order, current, target_state, payment_method)
        self._assign_status(order, target_state, updated_by)
        await self.db.flush()
        await self.db.refresh(order)
        return OrderCommandResult(order=order)

    async def _prelock_reservation_stocks(self, order: Order) -> dict:
        """F3 cancel discipline: lock stocks keyed by the order's ACTIVE
        reservations (sorted by reservation.sku_id — the same global
        sorted-sku_id order). A legacy order with no reservations yields an
        empty dict (pure status cancel)."""
        from services.inventory_service import InventoryService

        inventory = InventoryService()
        codes = (await self.db.execute(
            select(InventoryReservation.sku_id, InventoryReservation.sku_code)
            .where(InventoryReservation.order_id == order.id)
            .where(InventoryReservation.status == "reserved")
            .where(InventoryReservation.is_deleted.is_(False))
        )).all()
        codes_by_id = {row[0]: row[1] for row in codes}

        stocks: dict = {}
        for sku_id in sorted(codes_by_id):
            stocks[sku_id] = await inventory._locked_stock_by_sku_id(
                self.db,
                sku_id=sku_id,
                sku_code=codes_by_id[sku_id],
            )
        return stocks

    async def _prelock_stocks(self, items, *, require_active: bool = False) -> dict:
        """Lock EVERY distinct stock row in ONE global order (sorted
        sku_id) BEFORE any inventory write; returns the locked stocks.

        Shared by confirm/cancel/fulfill/return — the single lock-order
        strategy of the command layer.
        """
        from services.inventory_service import InventoryService

        inventory = InventoryService()
        stocks = {}
        for sku_id in sorted({str(i.sellable_unit_id) for i in items}):
            item = next(i for i in items if str(i.sellable_unit_id) == sku_id)
            stocks[uuid.UUID(sku_id)] = await inventory._locked_stock_by_sku_id(
                self.db,
                sku_id=uuid.UUID(sku_id),
                sku_code=item.sku_code,
                require_active=require_active,
            )
        return stocks

    # ------------------------------------------------------------------
    # Internals — the single write point and shared discipline
    # ------------------------------------------------------------------

    async def _load_locked(self, order_id: uuid.UUID) -> Order:
        """Lock the order row and force-refresh the ORM state.

        populate_existing is REQUIRED: without it the identity map keeps
        stale attributes and the matrix check would validate pre-lock state
        (the D1 R3 defect).
        """
        result = await self.db.execute(
            select(Order)
            .where(Order.id == order_id)
            .where(Order.is_deleted == False)  # noqa: E712
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise _conflict("ORDER_NOT_FOUND", f"Order {order_id} not found")
        return order

    def _validate_transition(self, order: Order, target: OrderState) -> None:
        current = OrderState(order.status.value)
        if is_terminal_state(current):
            raise OrderInvariantViolation(
                f"Cannot transition from terminal state {current.value}"
            )
        if not is_valid_transition(current, target):
            raise InvalidStateTransitionError(
                from_state=current,
                to_state=target,
                reason="Transition not allowed by state machine",
            )
        if target == OrderState.CONFIRMED and order.total_amount <= Decimal("0.00"):
            raise OrderInvariantViolation(
                "Cannot confirm order with zero or negative total amount"
            )

    def _validate_item_identities(self, order: Order) -> None:
        """Stable/legacy identity shapes must be intact before confirming."""
        for item in order.items:
            if item.identity_status == "legacy" and item.sellable_unit_id is not None:
                raise _conflict(
                    "ORDER_ITEM_IDENTITY_MISMATCH",
                    f"Order item '{item.id}' is legacy but carries a "
                    "sellable unit reference",
                )

    async def _reserve_inventory(
        self, order: Order, stocks: dict
    ) -> list[InventoryReservation]:
        """Create owned reservations from the ALREADY pre-locked stock rows
        (shared sorted-sku_id strategy — no inline locking here)."""
        reserved: list[InventoryReservation] = []
        for item in sorted(
            order.items,
            key=lambda i: str(i.sellable_unit_id),
        ):
            stock = stocks[item.sellable_unit_id]
            quantity = Decimal(str(item.quantity))
            available = stock.quantity_on_hand - stock.quantity_reserved
            if available < quantity:
                raise _conflict(
                    "INSUFFICIENT_AVAILABLE_STOCK",
                    f"Insufficient available stock for '{item.sku_code}': "
                    f"requested {quantity}, available {available}",
                )
            reservation = InventoryReservation(
                order_id=order.id,
                order_item_id=item.id,
                sku_id=item.sellable_unit_id,
                sku_code=item.sku_code,
                quantity=quantity,
                status="reserved",
                reference_type="order",
                reference_id=order.id,
            )
            self.db.add(reservation)
            stock.quantity_reserved = stock.quantity_reserved + quantity
            reserved.append(reservation)
        await self.db.flush()
        return reserved

    async def _release_reservations(
        self, order: Order, stocks: dict
    ) -> list[InventoryReservation]:
        """Release the order's own active reservations using the ALREADY
        pre-locked stock rows (no inline locking here)."""
        result = await self.db.execute(
            select(InventoryReservation)
            .where(InventoryReservation.order_id == order.id)
            .where(InventoryReservation.status == "reserved")
            .where(InventoryReservation.is_deleted.is_(False))
            .order_by(InventoryReservation.sku_code.asc(), InventoryReservation.id.asc())
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        reservations = list(result.scalars().all())
        for reservation in reservations:
            stock = stocks[reservation.sku_id]
            if stock.quantity_reserved < reservation.quantity:
                raise _conflict(
                    "RESERVATION_AGGREGATE_MISMATCH",
                    f"Aggregate reserved stock for '{reservation.sku_code}' "
                    "is lower than owned reservation quantity",
                )
            stock.quantity_reserved = stock.quantity_reserved - reservation.quantity
            reservation.status = "released"
        await self.db.flush()
        return reservations

    async def _reserve_credit(self, order: Order) -> Decimal:
        """Reserve retailer credit for the confirmed order total.

        Adds the order total to the binding's outstanding balance — the
        same single-column credit-occupation primitive the payment service
        uses for credit movements (no ledger entries; frozen decision).
        """
        delta = Decimal(str(order.total_amount))
        await self.db.execute(
            text(
                """
                UPDATE public.wholesaler_retailer_bindings
                SET outstanding_balance = outstanding_balance + :delta,
                    updated_at = now()
                WHERE wholesaler_id = :wholesaler_id
                  AND retailer_id = :retailer_id
                  AND is_deleted IS FALSE
                """
            ),
            {
                "delta": delta,
                "wholesaler_id": order.wholesaler_id,
                "retailer_id": order.retailer_id,
            },
        )
        return delta

    async def _post_transition_ledger(
        self,
        order: Order,
        from_state: OrderState,
        to_state: OrderState,
        payment_method: Optional[str],
    ) -> str:
        """Preserved financial effects for pay/return; NONE for CONFIRMED."""
        if to_state == OrderState.CONFIRMED:
            # Frozen decision: confirmation posts NO ledger entries. There
            # is intentionally no configuration switch to restore the
            # former receivable/revenue posting.
            return "none"

        if to_state == OrderState.PAID and payment_method != "credit":
            from services.ledger_service import LedgerService

            await LedgerService(self.db).post_payment_received(
                order_id=order.id,
                amount=order.total_amount,
                description=(
                    f"Payment received for order {order.id} - "
                    f"Amount: {order.total_amount}"
                ),
            )
            return "posted"

        if to_state == OrderState.RETURNED:
            from services.ledger_service import LedgerService

            await LedgerService(self.db).post_order_return(
                order_id=order.id,
                amount=order.total_amount,
                description=(
                    f"Full return for order {order.id} - "
                    f"Refund: {order.total_amount}"
                ),
            )
            return "posted"

        return "none"

    def _check_invariants(self, from_state: OrderState, to_state: OrderState) -> None:
        if to_state == OrderState.CONFIRMED and self._locked_order is not None \
                and self._locked_order.total_amount <= Decimal("0.00"):
            raise OrderInvariantViolation(
                "Cannot confirm order with zero or negative total amount"
            )
        if to_state == OrderState.VOIDED and from_state in (
            OrderState.PAID,
            OrderState.PARTIALLY_PAID,
        ):
            raise OrderInvariantViolation(
                f"Cannot void order in {from_state.value} state."
            )
        if to_state == OrderState.FULFILLED and from_state != OrderState.PAID:
            raise OrderInvariantViolation(
                f"Cannot fulfill order in {from_state.value} state. "
                "Order must be PAID before fulfillment."
            )
        if to_state == OrderState.RETURNED and from_state != OrderState.FULFILLED:
            raise OrderInvariantViolation(
                f"Cannot return order in {from_state.value} state. "
                "Order must be FULFILLED before return."
            )

    def _assign_status(self, order: Order, target: OrderState, updated_by: Optional[str]) -> None:
        """THE single direct order-status assignment in production code."""
        from models.order import OrderStatus

        order.status = OrderStatus(target.value)
        if updated_by:
            try:
                order.updated_by = uuid.UUID(str(updated_by))
            except ValueError:
                pass
        # keep items loaded for the caller without a second query pattern change
        if not order.items:
            pass  # lazy selectin relationship; refreshed object already carries items
