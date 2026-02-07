"""
S5-A: Order Lifecycle State Machine

Defines the order state graph, legal transitions, and validation rules.

Philosophy: "Transitions are atomic, validated, and rigid. No ad-hoc status updates."

State Graph:
    DRAFT → CONFIRMED, VOIDED
    CONFIRMED → PAID, PARTIALLY_PAID, CANCELLED
    PAID → FULFILLED, CANCELLED (with refund)
    PARTIALLY_PAID → PAID, CANCELLED
    FULFILLED → (Terminal)
    CANCELLED → (Terminal)
    VOIDED → (Terminal)
"""
from enum import Enum as PyEnum
from typing import Dict, Set, Optional


class OrderState(str, PyEnum):
    """
    Order state enum for accounting-grade state machine.
    
    States:
    - DRAFT: Order is being created, not yet confirmed
    - CONFIRMED: Order is confirmed and awaiting payment
    - PARTIALLY_PAID: Order has received partial payment
    - PAID: Order is fully paid
    - FULFILLED: Order has been delivered/completed
    - CANCELLED: Order was cancelled (may have refund implications)
    - VOIDED: Order was voided before any payment (clean cancellation)
    """
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    VOIDED = "voided"


# S5-1: State Transition Matrix
# Defines all legal state transitions
# Any transition NOT in this matrix is STRICTLY FORBIDDEN
STATE_TRANSITION_MATRIX: Dict[OrderState, Set[OrderState]] = {
    OrderState.DRAFT: {
        OrderState.CONFIRMED,
        OrderState.VOIDED,
    },
    OrderState.CONFIRMED: {
        OrderState.PAID,
        OrderState.PARTIALLY_PAID,
        OrderState.CANCELLED,
    },
    OrderState.PARTIALLY_PAID: {
        OrderState.PAID,
        OrderState.CANCELLED,
    },
    OrderState.PAID: {
        OrderState.FULFILLED,
        OrderState.CANCELLED,  # With refund logic
    },
    OrderState.FULFILLED: set(),  # Terminal state
    OrderState.CANCELLED: set(),  # Terminal state
    OrderState.VOIDED: set(),     # Terminal state
}


def is_valid_transition(from_state: OrderState, to_state: OrderState) -> bool:
    """
    Check if a state transition is valid according to the state machine.
    
    Args:
        from_state: Current order state
        to_state: Target order state
    
    Returns:
        True if transition is valid, False otherwise
    """
    if from_state not in STATE_TRANSITION_MATRIX:
        return False
    
    return to_state in STATE_TRANSITION_MATRIX[from_state]


def get_valid_transitions(from_state: OrderState) -> Set[OrderState]:
    """
    Get all valid transitions from a given state.
    
    Args:
        from_state: Current order state
    
    Returns:
        Set of valid target states
    """
    return STATE_TRANSITION_MATRIX.get(from_state, set())


def is_terminal_state(state: OrderState) -> bool:
    """
    Check if a state is terminal (no further transitions allowed).
    
    Args:
        state: Order state to check
    
    Returns:
        True if state is terminal, False otherwise
    """
    return len(STATE_TRANSITION_MATRIX.get(state, set())) == 0


class InvalidStateTransitionError(Exception):
    """
    Raised when an invalid state transition is attempted.
    
    This is a business logic error that should be caught and handled
    by the application layer.
    """
    def __init__(
        self,
        from_state: OrderState,
        to_state: OrderState,
        reason: Optional[str] = None
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        
        message = f"Invalid state transition: {from_state.value} → {to_state.value}"
        if reason:
            message += f". Reason: {reason}"
        
        super().__init__(message)


class OrderInvariantViolation(Exception):
    """
    Raised when an order invariant is violated during state transition.
    
    Invariants are business rules that must be satisfied for a transition
    to be valid (e.g., "cannot confirm order with zero total").
    """
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
