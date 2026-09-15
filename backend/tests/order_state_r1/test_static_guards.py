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
