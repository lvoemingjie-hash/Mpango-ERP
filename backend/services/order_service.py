"""S5-A: Order Service — compatibility adapter over the order command service.

R1 (CTO-AUTH-MPANGO-ORDER-STATE-AUTHORITY-R1-IMPLEMENTATION): the ONLY
production order-status writer is
``services.order_command_service.OrderCommandService`` (its
``_assign_status`` holds the single direct status assignment). This module
keeps the historical ``OrderService.transition`` signature for its callers
(CanonicalPaymentService and any remaining internal callers) and delegates
to the command service; it performs NO direct status assignment, posts NO
confirmation ledger (there is no switch — frozen decision) and sends NO
notifications (intents are returned on the command result for post-commit
dispatch by the caller).
"""
from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.structured_logging import get_logger
from core.domain.order_state import OrderState
from models.order import Order
from services.order_command_service import OrderCommandResult, OrderCommandService

logger = get_logger(__name__)


class OrderService:
    """Compatibility adapter; see services/order_command_service.py."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.last_result: Optional[OrderCommandResult] = None

    async def transition(
        self,
        order_id: UUID,
        target_state: OrderState,
        reason: Optional[str] = None,
        updated_by: Optional[UUID] = None,
        payment_method: Optional[str] = None,
    ) -> Order:
        """Delegating transition (locked-fresh, single-writer).

        Returns the updated Order for signature compatibility; the command
        result (including notification intents) is available via
        ``last_result`` after the call.
        """
        command = OrderCommandService(self.db)
        try:
            result: OrderCommandResult = await command.apply_transition(
                order_id,
                target_state,
                reason=reason,
                updated_by=str(updated_by) if updated_by else None,
                payment_method=payment_method,
            )
        except HTTPException as exc:
            # historical contract: direct service callers see ValueError
            # for a missing order; HTTP routes pre-check with 404.
            if (exc.detail or {}).get("code") == "ORDER_NOT_FOUND":
                raise ValueError(f"Order {order_id} not found")
            raise
        # exposed for callers that need intents without a second query
        self.last_result = result
        return result.order

    async def _post_ledger_entries(
        self,
        order,
        from_state: OrderState,
        to_state: OrderState,
        payment_method: Optional[str] = None,
    ) -> None:
        """Compatibility seam for ledger semantics (delegates to the
        command service's preserved pay/return posting; CONFIRMED posts
        nothing — frozen decision, no switch)."""
        command = OrderCommandService(self.db)
        await command._post_transition_ledger(
            order, from_state, to_state, payment_method
        )
