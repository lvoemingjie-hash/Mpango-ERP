"""
S5-A: Order Service with State Machine

Implements atomic, validated, and rigid state transitions for orders.

Philosophy: "Transitions are atomic, validated, and rigid. No ad-hoc status updates."

Features:
- Atomic state transitions with row locking
- State transition validation against matrix
- Business invariant checks
- Optional domain event emission via job queue
"""
from typing import Optional
from uuid import UUID
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.order import Order
from core.domain.order_state import (
    OrderState,
    is_valid_transition,
    is_terminal_state,
    InvalidStateTransitionError,
    OrderInvariantViolation,
)
from core.structured_logging import get_logger

logger = get_logger(__name__)


class OrderService:
    """
    Service for managing order lifecycle and state transitions.

    All state transitions go through this service to ensure:
    1. Transitions are validated against the state machine
    2. Business invariants are checked
    3. Changes are atomic (single transaction with row locking)
    4. Domain events can be emitted (optional)
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize order service.

        Args:
            db: Database session (tenant schema)
        """
        self.db = db

    async def transition(
        self,
        order_id: UUID,
        target_state: OrderState,
        reason: Optional[str] = None,
        updated_by: Optional[UUID] = None,
        payment_method: Optional[str] = None,
    ) -> Order:
        """
        Transition an order to a new state.

        This is the ONLY way to change order state. Direct status updates
        are forbidden.

        Process:
        1. Lock the order row (SELECT FOR UPDATE)
        2. Validate transition is legal in state machine
        3. Check business invariants
        4. Update status
        5. Post ledger entries (S5-B integration)
        6. (Optional) Emit domain event

        All steps happen in a single atomic transaction.

        Args:
            order_id: Order UUID
            target_state: Target state to transition to
            reason: Optional reason for transition (for audit)
            updated_by: UUID of user making the transition
            payment_method: Optional payment method ("cash"/"transfer"/"credit").
                When "credit" and target is PAID, ledger skips cash-settlement
                entries so receivable exposure remains visible. None = legacy
                behavior (always post cash-settlement on PAID).

        Returns:
            Updated Order object

        Raises:
            InvalidStateTransitionError: If transition is not allowed
            OrderInvariantViolation: If business rules are violated
            ValueError: If order not found
        """
        # S5-2: Lock the order row for update
        result = await self.db.execute(
            select(Order)
            .where(Order.id == order_id)
            .where(Order.is_deleted == False)
            .with_for_update()
        )
        order = result.scalar_one_or_none()

        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Convert current status to OrderState
        current_state = OrderState(order.status.value)

        # S5-2: Check if transition is valid in state machine
        if not is_valid_transition(current_state, target_state):
            raise InvalidStateTransitionError(
                from_state=current_state,
                to_state=target_state,
                reason="Transition not allowed by state machine"
            )

        # S5-3: Run invariant checks
        self._check_invariants(order, current_state, target_state)

        # Update status
        # Note: Order.status is OrderStatus enum, need to map OrderState to it
        order.status = self._map_state_to_status(target_state)

        if updated_by:
            order.updated_by = updated_by

        await self.db.flush()

        # S5-B: Post ledger entries for financial state changes
        await self._post_ledger_entries(order, current_state, target_state, payment_method=payment_method)

        await self.db.refresh(order)

        logger.info(
            f"Order state transition: {current_state.value} → {target_state.value}",
            extra={
                "order_id": str(order_id),
                "from_state": current_state.value,
                "to_state": target_state.value,
                "reason": reason,
                "updated_by": str(updated_by) if updated_by else None,
            }
        )

        # Phase P-B: Fire-and-forget notifications on key transitions
        await self._send_transition_notifications(order, target_state)

        # S5-2 (Optional): Emit domain event via job queue
        # TODO: Implement when job queue integration is ready
        # await self._emit_state_changed_event(order, current_state, target_state, reason)

        return order

    def _check_invariants(
        self,
        order: Order,
        from_state: OrderState,
        to_state: OrderState
    ) -> None:
        """
        Check business invariants for state transition.

        S5-3: Invariant Rules:
        - Rule 1: Cannot CONFIRM order if total_amount is 0 (unless explicitly allowed)
        - Rule 2: Cannot VOID order if it is already PAID or PARTIALLY_PAID
        - Rule 3: Cannot transition from terminal state
        - Rule 4: Cannot FULFILL order if not PAID

        Args:
            order: Order being transitioned
            from_state: Current state
            to_state: Target state

        Raises:
            OrderInvariantViolation: If any invariant is violated
        """
        # Rule 1: Cannot confirm order with zero total
        if to_state == OrderState.CONFIRMED:
            if order.total_amount <= Decimal("0.00"):
                raise OrderInvariantViolation(
                    "Cannot confirm order with zero or negative total amount"
                )

        # Rule 2: Cannot void order if already paid
        if to_state == OrderState.VOIDED:
            if from_state in (OrderState.PAID, OrderState.PARTIALLY_PAID):
                raise OrderInvariantViolation(
                    f"Cannot void order in {from_state.value} state. "
                    "Use CANCEL instead for paid orders."
                )

        # Rule 3: Cannot transition from terminal state
        if is_terminal_state(from_state):
            raise OrderInvariantViolation(
                f"Cannot transition from terminal state {from_state.value}"
            )

        # Rule 4: Cannot fulfill order if not paid
        if to_state == OrderState.FULFILLED:
            if from_state != OrderState.PAID:
                raise OrderInvariantViolation(
                    f"Cannot fulfill order in {from_state.value} state. "
                    "Order must be PAID before fulfillment."
                )

        # Rule 5: Cannot return order unless it is FULFILLED
        if to_state == OrderState.RETURNED:
            if from_state != OrderState.FULFILLED:
                raise OrderInvariantViolation(
                    f"Cannot return order in {from_state.value} state. "
                    "Order must be FULFILLED before return."
                )

    def _map_state_to_status(self, state: OrderState) -> "OrderStatus":
        """
        Map OrderState to OrderStatus enum.

        Args:
            state: OrderState to map

        Returns:
            Corresponding OrderStatus
        """
        from models.order import OrderStatus

        # Direct 1:1 mapping now that OrderStatus has all states
        mapping = {
            OrderState.DRAFT: OrderStatus.DRAFT,
            OrderState.CONFIRMED: OrderStatus.CONFIRMED,
            OrderState.PARTIALLY_PAID: OrderStatus.PARTIALLY_PAID,
            OrderState.PAID: OrderStatus.PAID,
            OrderState.FULFILLED: OrderStatus.FULFILLED,
            OrderState.CANCELLED: OrderStatus.CANCELLED,
            OrderState.VOIDED: OrderStatus.VOIDED,
            OrderState.RETURNED: OrderStatus.RETURNED,
        }

        return mapping[state]

    async def _post_ledger_entries(
        self,
        order: Order,
        from_state: OrderState,
        to_state: OrderState,
        payment_method: Optional[str] = None,
    ) -> None:
        """
        Post ledger entries for order state transitions.

        S5-B: Financial ledger integration.

        Ledger entries are posted for:
        - CONFIRMED: Debit RECEIVABLE, Credit REVENUE
        - PAID (non-credit): Debit CASH, Credit RECEIVABLE
        - PAID (credit): Skip cash-settlement entries; receivable exposure
          must remain visible on the ledger.

        Args:
            order: Order being transitioned
            from_state: Previous state
            to_state: New state
            payment_method: "credit" skips post_payment_received on PAID
        """
        # Import here to avoid circular dependency
        from services.ledger_service import LedgerService

        ledger_service = LedgerService(self.db)

        # Post entries based on target state
        if to_state == OrderState.CONFIRMED:
            # Order confirmed: Customer owes us money, we earned revenue
            await ledger_service.post_order_confirmation(
                order_id=order.id,
                amount=order.total_amount,
                description=f"Order {order.id} confirmed - Total: {order.total_amount}"
            )

        elif to_state == OrderState.PAID:
            # Credit sales close order lifecycle as PAID but must NOT create
            # cash/receivable-settlement entries — the receivable exposure
            # from confirmation must remain visible on the ledger.
            if payment_method == "credit":
                logger.info(
                    f"Credit PAID transition: skipping cash-settlement ledger "
                    f"entries for order {order.id}",
                    extra={
                        "order_id": str(order.id),
                        "payment_method": "credit",
                    },
                )
            else:
                # Cash/transfer/legacy: We got cash, customer no longer owes
                await ledger_service.post_payment_received(
                    order_id=order.id,
                    amount=order.total_amount,
                    description=f"Payment received for order {order.id} - Amount: {order.total_amount}"
                )

        elif to_state == OrderState.RETURNED:
            # Full return: reverse the original confirmation entries
            await ledger_service.post_order_return(
                order_id=order.id,
                amount=order.total_amount,
                description=f"Full return for order {order.id} - Refund: {order.total_amount}"
            )

    async def _emit_state_changed_event(
        self,
        order: Order,
        from_state: OrderState,
        to_state: OrderState,
        reason: Optional[str]
    ) -> None:
        """
        Emit domain event for order state change.

        This can be used to trigger side effects like:
        - Sending notifications
        - Updating inventory
        - Creating audit logs
        - Triggering workflows

        Args:
            order: Order that changed state
            from_state: Previous state
            to_state: New state
            reason: Reason for transition
        """
        # TODO: Integrate with S4 job queue
        # from core.jobs.base import get_job_queue
        #
        # queue = get_job_queue()
        # await queue.enqueue(
        #     job_name="order_state_changed",
        #     payload={
        #         "order_id": str(order.id),
        #         "from_state": from_state.value,
        #         "to_state": to_state.value,
        #         "reason": reason,
        #         "timestamp": datetime.utcnow().isoformat(),
        #     }
        # )
        pass

    async def _send_transition_notifications(
        self,
        order: Order,
        target_state: OrderState,
    ) -> None:
        """
        Phase P-B: Fire-and-forget notifications for order state changes.

        Rules:
          - CONFIRMED → Send email "Order #{id} Confirmed"
          - FULFILLED (shipped) → Send SMS "Order #{id} is on the way"

        Failures are logged but never raise — notifications must not block
        the atomic transition.
        """
        try:
            from services.notification_service import notification_service

            short_id = str(order.id)[:8]

            if target_state == OrderState.CONFIRMED:
                await notification_service.send_email(
                    to=f"retailer-{order.retailer_id}@placeholder.local",
                    subject=f"Order #{short_id} Confirmed",
                    body=(
                        f"Your order #{short_id} for KES {order.total_amount:,.2f} "
                        f"has been confirmed. Thank you for your business!"
                    ),
                )

            elif target_state == OrderState.FULFILLED:
                await notification_service.send_sms(
                    phone=f"+254000000000",  # placeholder — real phone from retailer profile
                    message=(
                        f"Order #{short_id} is on the way! "
                        f"Amount: KES {order.total_amount:,.2f}"
                    ),
                )

        except Exception as exc:
            logger.warning(
                "notification_dispatch_failed",
                extra={
                    "order_id": str(order.id),
                    "target_state": target_state.value,
                    "error": str(exc),
                },
            )
