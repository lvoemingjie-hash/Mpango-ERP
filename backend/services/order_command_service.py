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

Lock order (see tests/order_state_r1/test_lock_order_matrix.py): the order
row is always locked FIRST; inventory rows follow in one deterministic
per-command order; stock rows are always locked ordered by
(sku_code, sku_id); reservations owned by the command's order are locked
ordered by (sku_code, id). Cross-command inverse table order (confirm:
stocks->reservations vs cancel: reservations->stocks) is safe under the
orders-lock-first invariant — a full cross-order proof and its limits are
documented in the implementation report.
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

        reservations = await self._reserve_inventory(order)

        self._assign_status(order, OrderState.CONFIRMED, updated_by)

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

        released = await self._release_reservations(order)

        self._assign_status(order, OrderState.CANCELLED, updated_by)

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

    async def _reserve_inventory(self, order: Order) -> list[InventoryReservation]:
        """Create owned reservations with deterministic stock lock order.

        Stock rows are locked ordered by (sku_code, sku_id) — the same
        ordering policy the cancel path uses for its reservation locks.
        """
        from services.inventory_service import InventoryService

        inventory = InventoryService()
        reserved: list[InventoryReservation] = []
        for item in sorted(
            order.items,
            key=lambda i: (i.sku_code, str(i.sellable_unit_id)),
        ):
            if item.sellable_unit_id is None:
                raise _conflict(
                    "ORDER_ITEM_SELLABLE_ID_REQUIRED",
                    f"Order item '{item.id}' requires explicit legacy mapping",
                )
            stock = await inventory._locked_stock_by_sku_id(
                self.db,
                sku_id=item.sellable_unit_id,
                sku_code=item.sku_code,
                require_active=True,
            )
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

    async def _release_reservations(self, order: Order) -> list[InventoryReservation]:
        """Release the order's own active reservations (deterministic order)."""
        from services.inventory_service import InventoryService

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
        inventory = InventoryService()
        for reservation in reservations:
            stock = await inventory._locked_stock_by_sku_id(
                self.db,
                sku_id=reservation.sku_id,
                sku_code=reservation.sku_code,
            )
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
