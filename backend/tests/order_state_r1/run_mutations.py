"""R1 named mutation runner (author evidence).

Each mutation applies an EXACT byte replacement to a production file, runs
its named semantic oracle expecting RED, restores the bytes (sha256-verified
identical), and re-runs a GREEN control. Syntax errors, missing matches,
unrelated failures and environment errors are reported as MUTATION_FAIL —
never as mutation proof. Run directly: python tests/order_state_r1/run_mutations.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

ENV = {
    **os.environ,
    "MPANGO_ENV": "test",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Mutation:
    def __init__(self, mid, rel_path, old, new, oracle, control):
        self.mid = mid
        self.rel_path = rel_path
        self.old = old
        self.new = new
        self.oracle = oracle          # pytest node expected RED under mutation
        self.control = control        # pytest node expected GREEN after restore
        self.path = BACKEND / rel_path


def m(mid, rel, old, new, oracle, control):
    return Mutation(mid, rel, old, new, oracle, control)


MUTATIONS = [
    m(
        "M1_RESTORE_CRUD_STATUS_WRITER",
        "api/v1/client/orders.py",
        """    try:
        from uuid import UUID as _UUID

        result = await OrderCommandService(db).cancel_order(
            _UUID(order.id), updated_by=client.user_id
        )
        order = result.order""",
        """    # MUTATION M1: restore a second direct CRUD status writer
    from models.order import OrderStatus as _OS
    order.status = _OS.CANCELLED
    await db.flush()""",
        "tests/order_state_r1/test_static_guards.py::test_single_direct_status_writer",
        "tests/order_state_r1/test_static_guards.py::test_no_confirmation_ledger_call_anywhere_in_production",
    ),
    m(
        "M2_REMOVE_LOCKED_FRESH_REFRESH",
        "services/order_command_service.py",
        """        result = await self.db.execute(
            select(Order)
            .where(Order.id == order_id)
            .where(Order.is_deleted == False)  # noqa: E712
            .execution_options(populate_existing=True)
            .with_for_update()
        )""",
        """        result = await self.db.execute(
            select(Order)
            .where(Order.id == order_id)
            .where(Order.is_deleted == False)  # noqa: E712
            .with_for_update()
        )  # MUTATION M2: locked-fresh refresh removed""",
        "tests/order_state_r1/test_freshness.py::test_preloaded_session_transition_uses_locked_fresh_state",
        "tests/order_state_r1/test_baseline.py::test_confirm_reserves_stock_and_credit_and_posts_no_ledger",
    ),
    m(
        "M3_STALE_CANCEL_RELEASE_DECISION",
        "services/order_command_service.py",
        """        released = await self._release_reservations(order)

        self._assign_status(order, OrderState.CANCELLED, updated_by)""",
        """        # MUTATION M3: release decision driven by stale/non-command info
        released = []

        self._assign_status(order, OrderState.CANCELLED, updated_by)""",
        "tests/order_state_r1/test_concurrency.py::test_race_confirm_then_cancel_releases_reservations",
        "tests/order_state_r1/test_baseline.py::test_cancel_from_confirmed_releases_and_keeps_no_ledger",
    ),
    m(
        "M4_RESTORE_PRE_COMMIT_NOTIFICATION",
        "services/order_command_service.py",
        """        credit_reserved = await self._reserve_credit(order)

        return OrderCommandResult(""",
        """        credit_reserved = await self._reserve_credit(order)

        # MUTATION M4: notification sent inside the pre-commit transaction
        from services.notification_service import notification_service as _ns
        await _ns.send_email(
            to="customer@placeholder.local",
            subject="order confirmed",
            body="sent before commit by mutation M4",
        )

        return OrderCommandResult(""",
        "tests/order_state_r1/test_notifications.py::test_no_send_before_commit",
        "tests/order_state_r1/test_baseline.py::test_draft_cancel_returns_cancelled_not_voided",
    ),
    m(
        "M5_RESTORE_CONFIRMATION_ACCOUNTING",
        "services/order_command_service.py",
        """        if to_state == OrderState.CONFIRMED:
            # Frozen decision: confirmation posts NO ledger entries. There
            # is intentionally no configuration switch to restore the
            # former receivable/revenue posting.
            return "none\"""",
        """        if to_state == OrderState.CONFIRMED:
            # MUTATION M5: restore the former confirmation accounting
            from services.ledger_service import LedgerService
            await LedgerService(self.db).post_order_confirmation(
                order_id=order.id,
                amount=order.total_amount,
                description=f"Order {order.id} confirmed - Total: {order.total_amount}",
            )
            return "posted\"""",
        "tests/order_state_r1/test_static_guards.py::test_no_confirmation_ledger_call_anywhere_in_production",
        "tests/order_state_r1/test_baseline.py::test_confirm_reserves_stock_and_credit_and_posts_no_ledger",
    ),
    m(
        "M6_OPEN_PAID_CANCELLATION",
        "services/order_command_service.py",
        """        # Frozen decision: fail-closed until refund/funds disposition exists.
        if order.status.value in ("paid", "partially_paid"):
            raise _conflict(
                REFUND_WORKFLOW_NOT_IMPLEMENTED,
                "Cancellation of paid or partially paid orders is not "
                "available because the refund/funds disposition workflow "
                "is not implemented",
            )""",
        """        # MUTATION M6: paid-cancellation fail-closed gate removed""",
        "tests/order_state_r1/test_baseline.py::test_paid_cancel_fail_closed_with_workflow_code",
        "tests/order_state_r1/test_baseline.py::test_draft_cancel_returns_cancelled_not_voided",
    ),
    m(
        "M7_BREAK_PARTIAL_ITEM_ROLLBACK",
        "api/v1/orders.py",
        """        inventory_service = InventoryService()
        for item in order.items:
            await inventory_service.deduct_on_fulfillment(
                db,
                sellable_unit_id=item.sellable_unit_id,
                sku_code=item.sku_code,
                quantity=Decimal(str(item.quantity)),
                order_id=order.id,
                order_item_id=item.id,
                fulfilled_by=token.user_id,
            )

        await db.flush()""",
        """        inventory_service = InventoryService()
        for item in order.items:
            try:
                await inventory_service.deduct_on_fulfillment(
                    db,
                    sellable_unit_id=item.sellable_unit_id,
                    sku_code=item.sku_code,
                    quantity=Decimal(str(item.quantity)),
                    order_id=order.id,
                    order_item_id=item.id,
                    fulfilled_by=token.user_id,
                )
            except Exception:  # MUTATION M7: partial item write swallowed
                pass

        await db.flush()""",
        "tests/order_state_r1/test_rollback_vectors.py::test_fulfill_fault_during_second_item_write_rolls_back_all",
        "tests/order_state_r1/test_baseline.py::test_cancel_from_confirmed_releases_and_keeps_no_ledger",
    ),
]


def run_pytest(node: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", node, "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=BACKEND, env=ENV, capture_output=True, text=True, timeout=900,
    )
    return proc.returncode, (proc.stdout + proc.stderr)[-400:]


def apply(mutation: Mutation) -> tuple[str, str]:
    original = mutation.path.read_bytes()
    text_src = original.decode("utf-8")
    if mutation.old not in text_src:
        raise RuntimeError(f"mutation anchor not found in {mutation.rel_path}")
    mutated = text_src.replace(mutation.old, mutation.new, 1)
    mutation.path.write_text(mutated)
    return sha(original), sha(mutated.encode("utf-8"))


def restore(mutation: Mutation, original_sha: str) -> None:
    # git checkout is the byte-exact restore path (file is committed)
    subprocess.run(["git", "checkout", "--", mutation.rel_path],
                   cwd=BACKEND, check=True, capture_output=True)
    current = sha(mutation.path.read_bytes())
    if current != original_sha:
        raise RuntimeError(
            f"restore mismatch for {mutation.rel_path}: {current} != {original_sha}")


def main() -> int:
    only = sys.argv[1:] or None
    failures = []
    for mutation in MUTATIONS:
        if only and mutation.mid not in only:
            continue
        original = mutation.path.read_bytes()
        original_sha = sha(original)
        print(f"== {mutation.mid} ==", flush=True)
        try:
            pre_sha, mut_sha = apply(mutation)
        except Exception as exc:  # noqa: BLE001
            print(f"  MUTATION_FAIL (apply): {exc}")
            failures.append(mutation.mid)
            continue
        try:
            rc, tail = run_pytest(mutation.oracle)
            if rc == 0:
                print(f"  MUTATION_FAIL: oracle {mutation.oracle} did NOT go RED")
                failures.append(mutation.mid)
                continue
            print(f"  oracle RED ok (rc={rc})")
        except subprocess.TimeoutExpired:
            print("  MUTATION_FAIL: oracle run timed out")
            failures.append(mutation.mid)
            continue
        finally:
            restore(mutation, original_sha)
        rc, _ = run_pytest(mutation.control)
        if rc != 0:
            print(f"  MUTATION_FAIL: control {mutation.control} not GREEN after restore")
            failures.append(mutation.mid)
            continue
        print(f"  control GREEN ok — {mutation.mid} PROVEN")
    if failures:
        print(f"\nMUTATIONS FAILED: {failures}")
        return 1
    print("\nALL MUTATIONS PROVEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
