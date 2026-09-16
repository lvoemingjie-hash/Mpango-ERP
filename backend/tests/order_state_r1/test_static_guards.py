"""R1 static/AST guards: production has exactly ONE direct order-status
writer (services/order_command_service.py) and ZERO confirmation ledger
calls (post_order_confirmation)."""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PRODUCTION_DIRS = ["api", "services", "crud", "repositories", "models",
                   "core", "db", "jobs", "workers", "auth"]
WRITER_MODULE = "order_command_service.py"


def _production_files():
    for d in PRODUCTION_DIRS:
        root = BACKEND / d
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            yield path


def _relative(path: Path) -> str:
    return str(path.relative_to(BACKEND))


def test_single_direct_status_writer():
    """Every direct ``<>.status = <expr>`` assignment on order-like targets
    must live in the command service module. Other modules may not assign
    order status at all (bindings/payments etc. live elsewhere and are not
    `.status` on Order — checked by the OrderStatus/OrderState value test
    below)."""
    offenders: list[str] = []
    for path in _production_files():
        if path.name == WRITER_MODULE:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "status":
                    src = ast.unparse(node.value)
                    owner = getattr(target.value, "id", None)
                    if ("OrderStatus" in src or "OrderState" in src
                            or owner in ("order", "self.order", "preloaded",
                                         "updated")):
                        offenders.append(
                            f"{_relative(path)}:{node.lineno} {ast.unparse(node)}")
    assert not offenders, (
        f"second direct order-status writer found: {offenders}")


def test_command_service_holds_exactly_one_status_assignment():
    writer = BACKEND / "services" / WRITER_MODULE
    tree = ast.parse(writer.read_text())
    assignments = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Attribute) and t.attr == "status":
                    src = ast.unparse(node.value)
                    owner = getattr(t.value, "id", None)
                    if ("OrderStatus" in src or "OrderState" in src
                            or owner in ("order", "self.order", "preloaded",
                                         "updated")):
                        assignments.append(node)
                    break
    assert len(assignments) == 1, (
        f"expected exactly one status assignment in the writer module, "
        f"found {len(assignments)}")


def test_no_confirmation_ledger_call_anywhere_in_production():
    """The frozen decision: confirmation must not post receivable/revenue.
    ``post_order_confirmation`` must not be CALLED anywhere in production
    (the LedgerService method may exist for history)."""
    offenders: list[str] = []
    for path in _production_files():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if (isinstance(func, ast.Attribute)
                        and func.attr == "post_order_confirmation"):
                    offenders.append(f"{_relative(path)}:{node.lineno}")
                if (isinstance(func, ast.Name)
                        and func.id == "post_order_confirmation"):
                    offenders.append(f"{_relative(path)}:{node.lineno}")
    assert not offenders, f"confirmation ledger call found: {offenders}"


def test_no_placeholder_notification_values_in_production():
    """No placeholder recipients in production notification code."""
    offenders: list[str] = []
    markers = ("placeholder.local", "+254000000000")
    for path in _production_files():
        src = path.read_text()
        for marker in markers:
            if marker in src:
                offenders.append(f"{_relative(path)} contains {marker!r}")
    assert not offenders, offenders


def test_payment_command_single_caller_guard():
    """F2: apply_payment_transition may be CALLED only by
    CanonicalPaymentService (production)."""
    allowed_caller = "services/canonical_payment_service.py"
    offenders: list[str] = []
    for path in _production_files():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = None
                if isinstance(func, ast.Attribute):
                    name = func.attr
                elif isinstance(func, ast.Name):
                    name = func.id
                if name == "apply_payment_transition":
                    if _relative(path) != allowed_caller:
                        offenders.append(
                            f"{_relative(path)}:{node.lineno}")
    assert not offenders, (
        f"non-canonical caller(s) of the payment command: {offenders}")


def test_adapter_refuses_payment_states():
    """F2 source shape: OrderService.transition makes no payment-command
    CALL (docstring mentions are fine) and refuses payment states."""
    src = (BACKEND / "services" / "order_service.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "apply_payment_transition":
            raise AssertionError(
                f"adapter calls the payment command at line {node.lineno}")
    assert "target_state in (OrderState.PAID, OrderState.PARTIALLY_PAID)" in src, (
        "adapter must explicitly refuse payment states")


def test_all_commands_share_prelock_strategy():
    """F2/F3 source shape: confirm/fulfill/return route item-derived stock
    locks through the shared _prelock_stocks; cancel routes
    reservation-derived locks through _prelock_reservation_stocks (F3:
    the cancel stock set comes from ACTIVE reservations, never from
    order.items). Both helpers lock in the ONE global sorted-sku_id
    order; no command locks stocks inline in its item loop."""
    src = (BACKEND / "services" / "order_command_service.py").read_text()
    tree = ast.parse(src)
    prelock_calls = []
    reservation_prelock_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "_prelock_stocks":
                prelock_calls.append(node.lineno)
            elif node.func.attr == "_prelock_reservation_stocks":
                reservation_prelock_calls.append(node.lineno)
    assert len(prelock_calls) >= 3, (
        f"expected >=3 _prelock_stocks call sites (confirm/fulfill/"
        f"return), found {prelock_calls}")
    assert len(reservation_prelock_calls) == 1, (
        f"expected exactly 1 _prelock_reservation_stocks call site "
        f"(cancel), found {reservation_prelock_calls}")
    # _locked_stock_by_sku_id may appear ONLY inside the two shared helpers
    helper_ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name in ("_prelock_stocks",
                                  "_prelock_reservation_stocks"):
            helper_ranges.append((node.lineno, node.end_lineno))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "_locked_stock_by_sku_id":
            if not any(a <= node.lineno <= b for a, b in helper_ranges):
                raise AssertionError(
                    f"command module locks stocks outside the shared "
                    f"prelock helpers at line {node.lineno}")
