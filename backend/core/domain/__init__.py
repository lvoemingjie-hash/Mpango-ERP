"""
S5: Domain Expansion - Core domain logic and business rules.
"""
from core.domain.order_state import (
    OrderState,
    STATE_TRANSITION_MATRIX,
    is_valid_transition,
    get_valid_transitions,
    is_terminal_state,
    InvalidStateTransitionError,
    OrderInvariantViolation,
)

__all__ = [
    "OrderState",
    "STATE_TRANSITION_MATRIX",
    "is_valid_transition",
    "get_valid_transitions",
    "is_terminal_state",
    "InvalidStateTransitionError",
    "OrderInvariantViolation",
]
