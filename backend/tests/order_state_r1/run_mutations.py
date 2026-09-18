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

R2-final governance closure — disposable detached worktree execution:
every mutated byte lives ONLY inside a throwaway ``git worktree add
--detach`` copy of HEAD. The authoritative tree hosting this runner is
never written to: it is proven clean before the run, never touched by
any mutation, and re-proven unchanged after the run. Restore inside the
disposable copy is an in-memory byte backup plus chmod with sha256
verification — there is deliberately NO git-restore code path in this
file, so an interruption at any point can only ever leave the disposable
copy dirty (which ``git worktree remove --force`` discards wholesale).
"""
from __future__ import annotations

import ast
import atexit
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import NamedTuple
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent

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
        # R2-final: narrow anchor on the UNIQUE _release_reservations call
        # site (the R2 cancel path inserts the settle-cancel-hold gate
        # between the release and the status write, which broke the old
        # three-statement block anchor without removing the semantic).
        "M3_STALE_CANCEL_RELEASE_DECISION",
        "services/order_command_service.py",
        """        released = await self._release_reservations(order, stocks)""",
        """        released = []  # MUTATION M3: release decision no longer owned by the command""",
        "tests/order_state_r1/test_concurrency.py::test_race_confirm_then_cancel_releases_reservations",
        "OSR1-M3-ORACLE",
        "tests/order_state_r1/test_baseline.py::test_cancel_from_confirmed_releases_and_keeps_no_ledger",
    ),
    m(
        # R2-final: narrow anchor on the UNIQUE _open_credit_hold call site
        # (the R2 confirm path replaced _reserve_credit with the per-order
        # credit hold; the pre-commit send is injected immediately before
        # it, exactly where the R1 seam sat).
        "M4_RESTORE_PRE_COMMIT_NOTIFICATION",
        "services/order_command_service.py",
        """        credit_reserved = await self._open_credit_hold(order, updated_by, actor=actor)""",
        """        # MUTATION M4: pre-commit send with a placeholder recipient
        from services.notification_service import notification_service as _ns
        await _ns.send_email(
            to="customer@placeholder.local",
            subject="order confirmed",
            body="sent before commit by mutation M4",
        )
        credit_reserved = await self._open_credit_hold(order, updated_by, actor=actor)""",
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


# ---------------------------------------------------------------------------
# Disposable detached worktree execution (R2-final governance closure)
# ---------------------------------------------------------------------------


def make_disposable_worktree() -> tuple[Path, Path]:
    """Create a throwaway detached worktree of HEAD.

    Returns (repo_root, backend_dir) of the disposable copy. Every mutated
    byte the runner ever writes lives under this copy only; the tree
    hosting the runner is never a write target.
    """
    tmp = tempfile.mkdtemp(prefix="osr1-mutations-disposable-")
    target = Path(tmp) / "disposable"
    proc = subprocess.run(
        ["git", "worktree", "add", "--detach", str(target), "HEAD"],
        cwd=REPO, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(f"disposable worktree creation failed: {proc.stderr}")
    return target, target / "backend"


def drop_disposable_worktree(repo_root: Path) -> None:
    """Force-remove a disposable worktree and its temp parent.

    ``--force`` is required precisely because an interrupted mutation may
    have left the disposable copy dirty; discarding it wholesale is the
    safety property (the authoritative tree was never touched).
    """
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(repo_root)],
        cwd=REPO, capture_output=True, text=True,
    )
    parent = repo_root.parent
    if parent.name.startswith("osr1-mutations-disposable-"):
        shutil.rmtree(parent, ignore_errors=True)


def authoritative_clean() -> str:
    """Tracked-file dirt of the authoritative tree ('' when clean)."""
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO, capture_output=True, text=True,
    )
    return proc.stdout.strip()


def apply_mutation(path: Path, old: str, new: str) -> tuple[bytes, int]:
    """Write the mutated bytes; return (original_bytes, original_mode).

    The caller MUST hold the returned backup until the restore step; the
    restore itself is write_bytes + chmod, never a git operation.
    """
    original = path.read_bytes()
    original_mode = path.stat().st_mode
    src = original.decode("utf-8")
    if src.count(old) != 1:
        raise ValueError(f"anchor count={src.count(old)} (must be exactly 1)")
    path.write_text(src.replace(old, new, 1))
    return original, original_mode


def restore_mutation(path: Path, original: bytes, original_mode: int) -> bool:
    """In-memory byte+mode restore with sha verification (no git ops)."""
    path.write_bytes(original)
    os.chmod(path, original_mode)
    return sha(path.read_bytes()) == sha(original)


def run_node(backend_dir: Path, node: str, timeout: float = 600.0) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", node, "-q", "--tb=long",
         "-p", "no:cacheprovider"],
        cwd=backend_dir, env=ENV, capture_output=True, text=True, timeout=timeout,
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

    pre_dirt = authoritative_clean()
    if pre_dirt:
        print(f"AUTHORITATIVE TREE NOT CLEAN BEFORE RUN: {pre_dirt!r}")
        return 3

    repo_root, backend_dir = make_disposable_worktree()
    atexit.register(drop_disposable_worktree, repo_root)
    print(f"== DISPOSABLE DETACHED WORKTREE: {repo_root} ==")
    print(f"== AUTHORITATIVE TREE {REPO} IS NEVER A WRITE TARGET ==")

    try:
        # --- pristine gate: every oracle and control GREEN before mutating ---
        nodes = []
        for mutation in MUTATIONS:
            if only and mutation.mid not in only:
                continue
            nodes += [mutation.oracle, mutation.control]
        print("== PRISTINE GATE ==", flush=True)
        bad = []
        for node in nodes:
            rc, out = run_node(backend_dir, node)
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
            path = backend_dir / mutation.rel_path
            backup: tuple[bytes, int] | None = None
            try:
                try:
                    backup = apply_mutation(path, mutation.old, mutation.new)
                except ValueError as exc:
                    print(f"  FAIL {exc}")
                    failures.append(mutation.mid)
                    continue
                mutated_src = path.read_text(encoding="utf-8")
                try:
                    ast.parse(mutated_src)
                    compile(mutated_src, mutation.rel_path, "exec")
                except SyntaxError as exc:
                    print(f"  FAIL mutated source invalid: {exc}")
                    failures.append(mutation.mid)
                    continue

                rc, out = run_node(backend_dir, mutation.oracle)
                verdict = classify(rc, out, mutation.oracle, mutation.marker)
                if verdict != "SEMANTIC_RED":
                    tail = out[-300:].replace("\n", " | ")
                    print(f"  FAIL {verdict} :: {tail}")
                    failures.append(mutation.mid)
                    continue
                print("  semantic RED ok")
            except subprocess.TimeoutExpired:
                print("  FAIL TIMEOUT (void)")
                failures.append(mutation.mid)
                continue
            finally:
                # In-memory byte+mode restore INSIDE the disposable copy.
                # A hard kill skips this — the authoritative tree stays
                # byte-identical regardless; the disposable copy is
                # discarded wholesale at exit.
                if backup is not None:
                    if not restore_mutation(path, *backup):
                        print("  FAIL restore mismatch")
                        failures.append(mutation.mid)
                        continue
                    status = subprocess.run(
                        ["git", "status", "--porcelain", "--",
                         f"backend/{mutation.rel_path}"],
                        cwd=repo_root, capture_output=True, text=True,
                    ).stdout.strip()
                    if status:
                        print(f"  FAIL disposable tree not clean: {status}")
                        failures.append(mutation.mid)
                        continue
                    print("  restore byte+mode identical, disposable tree clean")

            rc, _ = run_node(backend_dir, mutation.control)
            if rc != 0:
                print(f"  FAIL control not GREEN after restore")
                failures.append(mutation.mid)
                continue
            print(f"  control GREEN — {mutation.mid} PROVEN")
    finally:
        drop_disposable_worktree(repo_root)
        atexit.unregister(drop_disposable_worktree)

    post_dirt = authoritative_clean()
    if post_dirt != pre_dirt:
        print(f"AUTHORITATIVE TREE DRIFTED DURING RUN: {post_dirt!r}")
        return 3

    if failures:
        print(f"\nMUTATIONS FAILED: {failures}")
        return 1
    print("\nALL MUTATIONS PROVEN (strict semantic RED)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
