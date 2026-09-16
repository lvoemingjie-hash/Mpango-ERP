"""R1 mutation runner — strict semantic RED only (F3 contract).

Contract (F1 directive #5, tightened by the F3 directive):
- pristine pass: every oracle AND control must be GREEN on the untouched
  tree BEFORE any mutation runs;
- anchor uniqueness: the anchor text must occur EXACTLY once;
- mutated source must remain valid (ast.parse) and importable (compile);
- a mutation counts ONLY when the single-node run selects exactly the
  named node, fails with the expected assertion marker and rc==1;
- F3: a single-node invocation containing ANY collection, setup or
  teardown ERROR is VOID (FAIL) — even when the same node also shows a
  valid assertion failure. Structural pytest error forms rejected:
  ``ERROR collecting``, ``ERROR at setup/teardown of`` section headers,
  and short-summary lines beginning ``ERROR ``;
- rc=4 / environment errors / timeouts are VOID (FAIL);
- finally: byte+mode restore and a git-clean proof for the touched path.
"""
from __future__ import annotations

import ast
import hashlib
import os
import re
import subprocess
import sys
from typing import NamedTuple
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

ENV = {**os.environ, "MPANGO_ENV": "test"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Mutation(NamedTuple):
    # NamedTuple (not @dataclass): dataclasses resolve string annotations
    # via sys.modules[cls.__module__], which breaks importlib loaders that
    # exec this module without registering it (test_classifier.py).
    mid: str
    rel_path: str
    old: str
    new: str
    oracle: str            # exact pytest node expected to go RED
    marker: str            # regex expected in the failing assertion output
    control: str           # node expected GREEN after restore


def m(mid, rel, old, new, oracle, marker, control):
    return Mutation(mid, rel, old, new, oracle, marker, control)


CONFIRM_LEDGER_INSERT = """        reservations = await self._reserve_inventory(order, stocks)

        self._assign_status(order, OrderState.CONFIRMED, updated_by)
        await self.db.flush()"""

CONFIRM_LEDGER_MUTATED = """        reservations = await self._reserve_inventory(order, stocks)

        # MUTATION M5: restore confirmation accounting on the real confirm path
        from services.ledger_service import LedgerService
        await LedgerService(self.db).post_order_confirmation(
            order_id=order.id,
            amount=order.total_amount,
            description=f"Order {order.id} confirmed - Total: {order.total_amount}",
        )

        self._assign_status(order, OrderState.CONFIRMED, updated_by)
        await self.db.flush()"""

MUTATIONS = [
    m(
        "M1_RESTORE_CRUD_STATUS_WRITER",
        "api/v1/client/orders.py",
        """        result = await OrderCommandService(db).cancel_order(
            _UUID(str(order.id)),  # populate_existing yields asyncpg's UUID type
            updated_by=client.user_id
        )
        order = result.order""",
        """        # MUTATION M1: second direct status writer (valid syntax)
        from models.order import OrderStatus as _OS
        order.status = _OS.CANCELLED
        await db.flush()""",
        "tests/order_state_r1/test_static_guards.py::test_single_direct_status_writer",
        "second direct order-status writer",
        "tests/order_state_r1/test_static_guards.py::test_no_confirmation_ledger_call_anywhere_in_production",
    ),
    m(
        "M2_REMOVE_LOCKED_FRESH_REFRESH",
        "services/order_command_service.py",
        """            .execution_options(populate_existing=True)
            .with_for_update()
        )
        order = result.scalar_one_or_none()""",
        """            .with_for_update()
        )  # MUTATION M2: locked-fresh refresh removed
        order = result.scalar_one_or_none()""",
        "tests/order_state_r1/test_freshness.py::test_confirm_after_external_cancel_uses_locked_fresh_state",
        "OSR1-M2-ORACLE",
        "tests/order_state_r1/test_baseline.py::test_confirm_reserves_stock_and_credit_and_posts_no_ledger",
    ),
    m(
        "M3_STALE_CANCEL_RELEASE_DECISION",
        "services/order_command_service.py",
        """        stocks = await self._prelock_reservation_stocks(order)

        released = await self._release_reservations(order, stocks)

        self._assign_status(order, OrderState.CANCELLED, updated_by)""",
        """        stocks = await self._prelock_reservation_stocks(order)

        # MUTATION M3: release decision no longer owned by the command
        released = []

        self._assign_status(order, OrderState.CANCELLED, updated_by)""",
        "tests/order_state_r1/test_concurrency.py::test_race_confirm_then_cancel_releases_reservations",
        "OSR1-M3-ORACLE",
        "tests/order_state_r1/test_baseline.py::test_cancel_from_confirmed_releases_and_keeps_no_ledger",
    ),
    m(
        "M4_RESTORE_PRE_COMMIT_NOTIFICATION",
        "services/order_command_service.py",
        """        self._assign_status(order, OrderState.CONFIRMED, updated_by)
        await self.db.flush()

        credit_reserved = await self._reserve_credit(order)""",
        """        self._assign_status(order, OrderState.CONFIRMED, updated_by)
        await self.db.flush()

        # MUTATION M4: pre-commit send with a placeholder recipient
        from services.notification_service import notification_service as _ns
        await _ns.send_email(
            to="customer@placeholder.local",
            subject="order confirmed",
            body="sent before commit by mutation M4",
        )

        credit_reserved = await self._reserve_credit(order)""",
        "tests/order_state_r1/test_notifications.py::test_rollback_produces_zero_sends",
        "sends observed for a rolled-back request",
        "tests/order_state_r1/test_baseline.py::test_draft_cancel_returns_cancelled_not_voided",
    ),
    m(
        "M5_RESTORE_CONFIRMATION_ACCOUNTING",
        "services/order_command_service.py",
        CONFIRM_LEDGER_INSERT,
        CONFIRM_LEDGER_MUTATED,
        "tests/order_state_r1/test_baseline.py::test_confirm_reserves_stock_and_credit_and_posts_no_ledger",
        "confirmation posted ledger entries",
        "tests/order_state_r1/test_static_guards.py::test_no_placeholder_notification_values_in_production",
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
        "OSR1-M6-ORACLE",
        "tests/order_state_r1/test_baseline.py::test_draft_cancel_returns_cancelled_not_voided",
    ),
    m(
        "M7_BREAK_PARTIAL_ITEM_ROLLBACK",
        "services/order_command_service.py",
        """        inventory = InventoryService()
        for item in items:
            await inventory.deduct_on_fulfillment(
                self.db,
                sellable_unit_id=item.sellable_unit_id,
                sku_code=item.sku_code,
                quantity=Decimal(str(item.quantity)),
                order_id=order.id,
                order_item_id=item.id,
                fulfilled_by=updated_by,
            )""",
        """        inventory = InventoryService()
        for item in items:
            try:
                await inventory.deduct_on_fulfillment(
                    self.db,
                    sellable_unit_id=item.sellable_unit_id,
                    sku_code=item.sku_code,
                    quantity=Decimal(str(item.quantity)),
                    order_id=order.id,
                    order_item_id=item.id,
                    fulfilled_by=updated_by,
                )
            except Exception:  # MUTATION M7: partial item write swallowed
                pass""",
        "tests/order_state_r1/test_rollback_vectors.py::test_fulfill_fault_during_second_item_write_rolls_back_all",
        "second per-item inventory write",
        "tests/order_state_r1/test_baseline.py::test_cancel_from_confirmed_releases_and_keeps_no_ledger",
    ),
    m(
        "M8_GENERIC_BYPASS",
        "services/order_command_service.py",
        """        if target_state in COMMAND_OWNED_TARGETS:
            raise InvalidStateTransitionError(""",
        """        if False and target_state in COMMAND_OWNED_TARGETS:
            raise InvalidStateTransitionError(""",
        "tests/order_state_r1/test_f1_faces.py::test_generic_transition_refuses_command_owned_targets",
        "OSR1-M8-ORACLE",
        "tests/order_state_r1/test_baseline.py::test_draft_cancel_returns_cancelled_not_voided",
    ),
    m(
        "M9_FULFILL_NO_PRELOCK",
        "services/order_command_service.py",
        """        stocks = await self._prelock_stocks(items)

        inventory = InventoryService()
        for item in items:
            await inventory.deduct_on_fulfillment(""",
        """        stocks = {}  # MUTATION M9: no pre-lock before inventory writes

        inventory = InventoryService()
        for item in items:
            await inventory.deduct_on_fulfillment(""",
        "tests/order_state_r1/test_prelock.py::test_fulfill_prelocks_all_stocks_before_first_write",
        "OSR1-M9-ORACLE",
        "tests/order_state_r1/test_baseline.py::test_cancel_from_confirmed_releases_and_keeps_no_ledger",
    ),
    m(
        "M11_PARTIALLY_PAID_BYPASS",
        "services/order_command_service.py",
        """COMMAND_OWNED_TARGETS = frozenset(
    {OrderState.CONFIRMED, OrderState.CANCELLED, OrderState.PAID,
     OrderState.PARTIALLY_PAID, OrderState.FULFILLED, OrderState.RETURNED})""",
        """COMMAND_OWNED_TARGETS = frozenset(
    {OrderState.CONFIRMED, OrderState.CANCELLED, OrderState.PAID,
     OrderState.FULFILLED, OrderState.RETURNED})  # MUTATION M11""",
        "tests/order_state_r1/test_f1_faces.py::test_generic_refuses_partially_paid_on_confirmed",
        "OSR1-M11-ORACLE",
        "tests/order_state_r1/test_baseline.py::test_draft_cancel_returns_cancelled_not_voided",
    ),
    m(
        "M12_NON_CANONICAL_PAYMENT_CALLER",
        "api/v1/orders.py",
        """    order = await _get_order_by_id_for_update(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ORDER_NOT_FOUND",
                "message": f"Order with ID '{order_id}' not found",
            },
        )""",
        """    order = await _get_order_by_id_for_update(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ORDER_NOT_FOUND",
                "message": f"Order with ID '{order_id}' not found",
            },
        )
    # MUTATION M12: non-canonical direct payment-command call
    from services.order_command_service import OrderCommandService as _OCS
    from core.domain.order_state import OrderState as _OS
    await _OCS(db).apply_payment_transition(
        order.id, _OS.PARTIALLY_PAID, payment_method="cash")""",
        "tests/order_state_r1/test_static_guards.py::test_payment_command_single_caller_guard",
        "non-canonical caller",
        "tests/order_state_r1/test_static_guards.py::test_no_placeholder_notification_values_in_production",
    ),
    m(
        "M13_CROSS_COMMAND_LOCK_ORDER",
        "services/order_command_service.py",
        """        for sku_id in sorted(codes_by_id):""",
        """        for sku_id in sorted(codes_by_id, reverse=True):  # MUTATION M13""",
        "tests/order_state_r1/test_prelock.py::test_cancel_prelocks_all_stocks_in_global_order",
        "OSR1-M13-ORACLE",
        "tests/order_state_r1/test_baseline.py::test_cancel_from_confirmed_releases_and_keeps_no_ledger",
    ),
    m(
        "M10_CLIENT_409_MAPPING_REMOVED",
        "api/v1/client/orders.py",
        """    except (InvalidStateTransitionError, OrderInvariantViolation) as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CANCEL_NOT_ALLOWED",
                "message": str(e),
            },
        )
    except HTTPException:""",
        """    except HTTPException:  # MUTATION M10: domain errors no longer mapped""",
        "tests/order_state_r1/test_f1_faces.py::test_client_cancel_route_maps_domain_errors_409_direct",
        "unmapped",
        "tests/order_state_r1/test_baseline.py::test_draft_cancel_returns_cancelled_not_voided",
    ),
    # ------------------------------------------------------------------
    # F3 mutations: legacy cancel stock derivation + NULL-identity guards
    # ------------------------------------------------------------------
    m(
        "M14_CANCEL_STOCKS_FROM_ORDER_ITEMS",
        "services/order_command_service.py",
        """        # F3: the cancel stock set derives from the order's ACTIVE
        # RESERVATIONS, never from order.items — legacy DRAFT orders (no
        # reservations) cancel cleanly, and legacy orders WITH reservations
        # release exactly what was reserved, pre-locked by
        # reservation.sku_id in the global sorted order.
        stocks = await self._prelock_reservation_stocks(order)""",
        """        # MUTATION M14: cancel stock derivation restored from order.items
        items = sorted(
            order.items,
            key=lambda i: str(i.sellable_unit_id),
        )
        stocks = await self._prelock_stocks(items)""",
        "tests/order_state_r1/test_f3_legacy_faces.py::test_legacy_with_reservations_cancel_releases_by_reservation_sku_id",
        "OSR1-F3-LEGACY-RESV-CANCEL-OK",
        "tests/order_state_r1/test_f3_legacy_faces.py::test_legacy_draft_cancel_pure_status_write",
    ),
    m(
        "M15_FULFILL_NULL_IDENTITY_GUARD_BYPASSED",
        "services/order_command_service.py",
        """        missing = [i for i in items if i.sellable_unit_id is None]
        if missing:
            raise _conflict(
                "ORDER_ITEM_SELLABLE_ID_REQUIRED",
                f"Order item '{missing[0].id}' requires explicit legacy "
                "mapping before fulfillment",
            )""",
        """        missing = [i for i in items if i.sellable_unit_id is None]
        if False and missing:  # MUTATION M15: fulfill NULL-identity guard bypassed
            raise _conflict(
                "ORDER_ITEM_SELLABLE_ID_REQUIRED",
                f"Order item '{missing[0].id}' requires explicit legacy "
                "mapping before fulfillment",
            )""",
        "tests/order_state_r1/test_f3_legacy_faces.py::test_fulfill_null_identity_controlled_409",
        "OSR1-F3-FULFILL-NULL-409",
        "tests/order_state_r1/test_f3_legacy_faces.py::test_return_null_identity_controlled_409",
    ),
    m(
        "M16_RETURN_NULL_IDENTITY_GUARD_BYPASSED",
        "services/order_command_service.py",
        """        missing = [i for i in items if i.sellable_unit_id is None]
        if missing:
            raise _conflict(
                "ORDER_ITEM_SELLABLE_ID_REQUIRED",
                f"Order item '{missing[0].id}' requires explicit legacy "
                "mapping before return restock",
            )""",
        """        missing = [i for i in items if i.sellable_unit_id is None]
        if False and missing:  # MUTATION M16: return NULL-identity guard bypassed
            raise _conflict(
                "ORDER_ITEM_SELLABLE_ID_REQUIRED",
                f"Order item '{missing[0].id}' requires explicit legacy "
                "mapping before return restock",
            )""",
        "tests/order_state_r1/test_f3_legacy_faces.py::test_return_null_identity_controlled_409",
        "OSR1-F3-RETURN-NULL-409",
        "tests/order_state_r1/test_f3_legacy_faces.py::test_fulfill_null_identity_controlled_409",
    ),
]


def run_node(node: str, timeout: float = 600.0) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", node, "-q", "--tb=long",
         "-p", "no:cacheprovider"],
        cwd=BACKEND, env=ENV, capture_output=True, text=True, timeout=timeout,
    )
    return proc.returncode, proc.stdout + proc.stderr


def classify(rc: int, out: str, node: str, marker: str) -> str:
    """F3 contract: ONLY rc==1 with exactly the named FAILED node, the
    named assertion marker present, and ZERO collection/setup/teardown
    ERRORs anywhere in the single-node invocation counts as a semantic
    RED. Any pytest ERROR form voids the run — even when the named node
    also shows a valid assertion failure."""
    if rc == 0:
        return "NOT_RED"
    if rc != 1:
        return f"VOID_RC_{rc}"
    if "no tests ran" in out or "ERROR collecting" in out:
        return "VOID_COLLECTION"
    # F3 zero-error contract: the whole single-node invocation must be
    # error-free. Structural pytest error forms: setup/teardown ERROR
    # section headers and short-summary lines beginning "ERROR ".
    if re.search(r"ERROR at (?:setup|teardown) of \S+", out):
        return "VOID_SETUP_OR_TEARDOWN_ERROR"
    if re.search(r"^ERROR \S", out, re.M):
        return "VOID_ERROR_SUMMARY"
    failed = re.findall(r"^FAILED (\S+)", out, re.M)
    if failed != [node]:
        return f"WRONG_NODE:{failed}"
    if not re.search(marker, out):
        return "MARKER_MISSING"
    return "SEMANTIC_RED"


def main() -> int:
    only = sys.argv[1:] or None

    # --- pristine gate: every oracle and control GREEN before mutating ---
    nodes = []
    for mutation in MUTATIONS:
        if only and mutation.mid not in only:
            continue
        nodes += [mutation.oracle, mutation.control]
    print("== PRISTINE GATE ==", flush=True)
    bad = []
    for node in nodes:
        rc, out = run_node(node)
        status = "GREEN" if rc == 0 else f"rc={rc}"
        print(f"  {node}: {status}", flush=True)
        if rc != 0:
            bad.append(node)
    if bad:
        print(f"\nPRISTINE GATE FAILED: {bad} — no mutation is valid evidence")
        return 2

    failures: list[str] = []
    for mutation in MUTATIONS:
        if only and mutation.mid not in only:
            continue
        print(f"== {mutation.mid} ==", flush=True)
        path = BACKEND / mutation.rel_path
        original = path.read_bytes()
        original_mode = path.stat().st_mode
        original_sha = sha(original)

        src = original.decode("utf-8")
        count = src.count(mutation.old)
        if count != 1:
            print(f"  FAIL anchor count={count} (must be exactly 1)")
            failures.append(mutation.mid)
            continue
        mutated_src = src.replace(mutation.old, mutation.new, 1)
        try:
            ast.parse(mutated_src)
            compile(mutated_src, mutation.rel_path, "exec")
        except SyntaxError as exc:
            print(f"  FAIL mutated source invalid: {exc}")
            failures.append(mutation.mid)
            continue

        path.write_text(mutated_src)
        try:
            rc, out = run_node(mutation.oracle)
            verdict = classify(rc, out, mutation.oracle, mutation.marker)
            if verdict != "SEMANTIC_RED":
                tail = out[-300:].replace("\n", " | ")
                print(f"  FAIL {verdict} :: {tail}")
                failures.append(mutation.mid)
                continue
            print(f"  semantic RED ok")
        except subprocess.TimeoutExpired:
            print("  FAIL TIMEOUT (void)")
            failures.append(mutation.mid)
            continue
        finally:
            subprocess.run(["git", "checkout", "--", mutation.rel_path],
                           cwd=BACKEND, check=True, capture_output=True)
            os.chmod(path, original_mode)
            restored = path.read_bytes()
            if sha(restored) != original_sha:
                print("  FAIL restore mismatch")
                failures.append(mutation.mid)
                continue
            status = subprocess.run(
                ["git", "status", "--porcelain", "--", mutation.rel_path],
                cwd=BACKEND, capture_output=True, text=True).stdout.strip()
            if status:
                print(f"  FAIL worktree not clean: {status}")
                failures.append(mutation.mid)
                continue
            print("  restore byte+mode identical, worktree clean")

        rc, _ = run_node(mutation.control)
        if rc != 0:
            print(f"  FAIL control not GREEN after restore")
            failures.append(mutation.mid)
            continue
        print(f"  control GREEN — {mutation.mid} PROVEN")

    if failures:
        print(f"\nMUTATIONS FAILED: {failures}")
        return 1
    print("\nALL MUTATIONS PROVEN (strict semantic RED)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
