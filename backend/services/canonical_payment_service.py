from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.order_state import OrderState
from models.order import Order as OrderModel
from models.order_credit_hold import OrderCreditHold
import repositories.payment_repository as payment_repository_module
import services.ledger_service as ledger_service_module
import services.order_command_service as order_command_module
import services.payment_service as payment_service_module
from services.payment_history_contract import assert_valid_payment_history


def _payment_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _uuid_or_none(value):
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _credit_hold_mismatch(message: str) -> HTTPException:
    """R2 integrity refusal: any hold-lifecycle corruption is a hard 409
    with zero financial writes."""
    return _payment_error(
        status.HTTP_409_CONFLICT, "CREDIT_HOLD_MISMATCH", message)


def _same_payment_request(
    existing_payment: Mapping[str, Any],
    *,
    order_id: str,
    amount: Decimal,
    method: str,
    transaction_id: str | None,
) -> bool:
    return (
        str(existing_payment["order_id"]) == str(order_id)
        and Decimal(str(existing_payment["amount"])) == amount
        and str(existing_payment["method"]) == method
        and (existing_payment.get("transaction_id") or None) == (transaction_id or None)
    )


def _payment_mapping_or_none(candidate: Any) -> Mapping[str, Any] | None:
    return candidate if isinstance(candidate, Mapping) else None


#: The ONLY unique objects whose INSERT race the canonical service may
#: classify and answer with a replay/duplicate refusal. Any other
#: IntegrityError — including a unique violation on any other object — is
#: re-raised unchanged so it surfaces as the defect it is.
#:
#: The two names per contract cover both tenant-schema construction paths:
#: the alembic unique INDEXES (005/006/021) and the bootstrap-created
#: tenant schema, which declares payments.idempotency_key UNIQUE inline
#: (PostgreSQL names that constraint <table>_<column>_key).
_IDEMPOTENCY_UNIQUE_OBJECTS = frozenset({
    "uq_payments_idempotency_key",
    "payments_idempotency_key_key",
})
_TRANSACTION_UNIQUE_OBJECTS = frozenset({
    "uq_payments_transaction_id",
})
_REPLAYABLE_UNIQUE_OBJECTS = (
    _IDEMPOTENCY_UNIQUE_OBJECTS | _TRANSACTION_UNIQUE_OBJECTS
)
_UNIQUE_VIOLATION_SQLSTATE = "23505"
#: PostgreSQL's unique-violation message form, used ONLY as a fallback
#: when the driver's exception chain does not expose ``constraint_name``.
#: The name it yields is still checked against the closed object set
#: above, so message text can never widen the classification.
_UNIQUE_CONSTRAINT_MESSAGE = re.compile(r'unique constraint "([^"]+)"')


def _integrity_error_chain(exc: IntegrityError):
    """Walk the wrapped error to the origin: the asyncpg path nests
    (SQLAlchemy IntegrityError -> dialect adapter -> asyncpg error) and only
    the innermost asyncpg error carries the constraint name and sqlstate,
    while a directly constructed IntegrityError keeps the origin in
    ``orig``. Both links are followed."""
    node = exc
    seen: set[int] = set()
    for _ in range(8):
        if node is None or id(node) in seen:
            return
        seen.add(id(node))
        yield node
        node = (
            getattr(node, "__cause__", None)
            or getattr(node, "__context__", None)
            or getattr(node, "orig", None)
        )


def _integrity_sqlstate(exc: IntegrityError) -> str | None:
    for node in _integrity_error_chain(exc):
        state = (
            getattr(node, "sqlstate", None)
            or getattr(node, "pgcode", None)
            or getattr(getattr(node, "diag", None), "sqlstate", None)
        )
        if state:
            return str(state)
    return None


def _integrity_constraint_name(exc: IntegrityError) -> str | None:
    for node in _integrity_error_chain(exc):
        name = getattr(node, "constraint_name", None) or getattr(
            getattr(node, "diag", None), "constraint_name", None)
        if name:
            return str(name)
    match = _UNIQUE_CONSTRAINT_MESSAGE.search(str(exc))
    return match.group(1) if match else None


def _raise_invalid_amount(amount: Decimal) -> None:
    if amount.is_nan() or amount.is_infinite() or amount <= 0:
        raise _payment_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_PAYMENT_AMOUNT",
            "Payment amount must be a positive finite number",
        )


def _idempotency_conflict() -> HTTPException:
    return _payment_error(
        status.HTTP_409_CONFLICT,
        "IDEMPOTENCY_KEY_CONFLICT",
        "X-Idempotency-Key was already used with a different payment request",
    )


def _duplicate_transfer_reference() -> HTTPException:
    return _payment_error(
        status.HTTP_409_CONFLICT,
        "DUPLICATE_TRANSFER_REFERENCE",
        "Transfer transaction_id has already been recorded",
    )


#: Authoritative receipt number format: RCT-YYYYMMDD-NNNNNN (tenant-local sequence).
_RECEIPT_NUMBER_PATTERN = re.compile(r"^RCT-[0-9]{8}-[0-9]{6}$")


def _is_valid_receipt_number(value: Any) -> bool:
    """True only when ``value`` is a non-empty string matching the receipt format."""
    return isinstance(value, str) and bool(_RECEIPT_NUMBER_PATTERN.match(value))


def _declaration_confirmation_key_conflict() -> HTTPException:
    """Raised when a declaration-confirmation replay hits a payment row that is
    missing a well-formed receipt number (e.g. the canonical key slot was
    occupied by a non-cashier payment). Fail-closed: never reuse that payment,
    never re-allocate a receipt, never mark the declaration confirmed."""
    return _payment_error(
        status.HTTP_409_CONFLICT,
        "DECLARATION_CONFIRMATION_KEY_CONFLICT",
        "Declaration confirmation key collides with a non-receipt payment",
    )


def _enforce_receipt_on_replay(existing_payment: Mapping[str, Any], allocate_receipt: bool) -> None:
    """When the caller requested receipt allocation (declaration confirmation),
    a replayed payment must carry a well-formed receipt number. A NULL or
    malformed receipt means the canonical key slot was occupied by a payment
    that was not produced by a cashier confirmation — refuse to reuse it."""
    if allocate_receipt and not _is_valid_receipt_number(existing_payment.get("receipt_number")):
        raise _declaration_confirmation_key_conflict()


@dataclass(frozen=True)
class CanonicalPaymentResult:
    order: OrderModel
    payment_record: Mapping[str, Any]
    replayed: bool
    order_state: str


class CanonicalPaymentMutationHttpError(Exception):
    def __init__(self, http_exception: HTTPException) -> None:
        super().__init__(str(http_exception.detail))
        self.http_exception = http_exception


class CanonicalPaymentService:
    def __init__(self) -> None:
        self._repo = payment_repository_module.PaymentRepository()

    async def _get_order_by_id_for_update(self, db: AsyncSession, order_id: str) -> OrderModel | None:
        try:
            order_uuid = uuid.UUID(order_id)
        except ValueError:
            return None

        result = await db.execute(
            select(OrderModel)
            .where(OrderModel.id == order_uuid)
            .where(OrderModel.is_deleted == False)  # noqa: E712
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def _get_order_for_payment_record(self, db: AsyncSession, order_id: uuid.UUID) -> OrderModel | None:
        result = await db.execute(
            select(OrderModel)
            .where(OrderModel.id == order_id)
            .where(OrderModel.is_deleted == False)
        )
        return result.scalar_one_or_none()

    async def _lock_hold_rows(self, db: AsyncSession, order_id: uuid.UUID) -> list[OrderCreditHold]:
        """Lock the order's credit-hold lifecycle rows (0 or 1 — the UNIQUE
        constraint allows at most one)."""
        result = await db.execute(
            select(OrderCreditHold)
            .where(OrderCreditHold.order_id == order_id)
            .order_by(OrderCreditHold.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())

    async def _verify_hold_contract(
        self,
        db: AsyncSession,
        order: OrderModel,
        holds: list[OrderCreditHold],
        *,
        method: str,
        amount: Decimal,
        is_credit_collection: bool,
    ) -> None:
        """C1: validate the lifecycle contract BEFORE any financial write.

        Collection (PAID credit order) requires exactly one CONVERTED hold
        with remaining=0 and amount == order.total == effective credit
        total. Settlement (cash/transfer) and credit conversion require
        exactly one ACTIVE hold with remaining == total - effective paid.
        Any other shape is refused with zero writes.
        """
        total = Decimal(str(order.total_amount))
        shapes = [(h.status, str(h.remaining_amount)) for h in holds]

        if is_credit_collection:
            if len(holds) != 1 or holds[0].status != "converted":
                raise _credit_hold_mismatch(
                    "Credit collection requires exactly one converted "
                    f"credit hold, found {shapes or 'none'}")
            hold = holds[0]
            if Decimal(str(hold.remaining_amount)) != Decimal("0"):
                raise _credit_hold_mismatch(
                    "Converted credit hold must have remaining_amount = 0, "
                    f"found {hold.remaining_amount}")
            if Decimal(str(hold.amount)) != total:
                raise _credit_hold_mismatch(
                    f"Converted credit hold amount {hold.amount} does not "
                    f"match the order total {total}")
            credit_total = await self._repo.get_order_method_total(
                db, order_id=order.id, methods=("credit",))
            if credit_total != total:
                raise _credit_hold_mismatch(
                    f"Effective credit total {credit_total} does not match "
                    f"the order total {total}")
            # E1/F2: the total alone cannot legalize the history — two
            # split credit rows sum to the same total. The frozen contract
            # (039 preflight, duplicate-credit refusal) allows EXACTLY ONE
            # effective credit sale per order; soft-deleted rows do not
            # count. Both the direct pay path and the declaration
            # confirmation reach this seam, so the refusal path is shared.
            credit_rows = await self._repo.count_order_payments(
                db, order_id=order.id, method="credit")
            if credit_rows != 1:
                raise _credit_hold_mismatch(
                    "Credit sale requires exactly one effective credit "
                    f"payment, found {credit_rows} (a split or duplicated "
                    "credit history cannot be collected)")
            return

        if len(holds) != 1 or holds[0].status != "active":
            raise _credit_hold_mismatch(
                f"{method} settlement requires exactly one active credit "
                f"hold, found {shapes or 'none'}")
        hold = holds[0]
        if Decimal(str(hold.amount)) != total:
            raise _credit_hold_mismatch(
                f"Active credit hold amount {hold.amount} does not match "
                f"the order total {total}")
        prior_paid = await self._repo.get_order_paid_total(db, order_id=order.id)
        expected_remaining = total - prior_paid
        if Decimal(str(hold.remaining_amount)) != expected_remaining:
            raise _credit_hold_mismatch(
                f"Active credit hold remaining {hold.remaining_amount} does "
                f"not match the effective unsettled total "
                f"{expected_remaining}")
        if method in ("cash", "transfer") and amount > expected_remaining:
            raise _credit_hold_mismatch(
                f"Settlement amount {amount} exceeds the hold remaining "
                f"{hold.remaining_amount}")

    async def _convert_hold(
        self, db: AsyncSession, holds: list[OrderCreditHold], actor: str | None,
    ) -> None:
        hold = holds[0]
        hold.status = "converted"
        hold.remaining_amount = Decimal("0.00")
        hold.updated_by = _uuid_or_none(actor)
        await db.flush()

    async def _reduce_hold(
        self,
        db: AsyncSession,
        holds: list[OrderCreditHold],
        amount: Decimal,
        actor: str | None,
    ) -> None:
        hold = holds[0]
        remaining = Decimal(str(hold.remaining_amount)) - Decimal(str(amount))
        if remaining < Decimal("0"):
            raise _credit_hold_mismatch(
                f"Settlement would drive the hold remaining below zero "
                f"({hold.remaining_amount} - {amount})")
        hold.remaining_amount = remaining
        if remaining == Decimal("0"):
            hold.status = "settled"
        hold.updated_by = _uuid_or_none(actor)
        await db.flush()

    async def _replay_result(self, db: AsyncSession, payment_record: Mapping[str, Any]) -> CanonicalPaymentResult:
        """Zero-write replay. R2-R1 C6: the replayed payment's ORDER and
        RETAILER attribution are verified against the linked order; a
        mismatched or missing record is a neutral refusal, never a
        cross-order replay."""
        order = await self._get_order_for_payment_record(db, uuid.UUID(str(payment_record["order_id"])))
        if not order:
            raise _payment_error(
                status.HTTP_404_NOT_FOUND,
                "ORDER_NOT_FOUND",
                "Order for idempotent payment was not found",
            )
        if str(payment_record.get("retailer_id")) != str(order.retailer_id):
            raise _payment_error(
                status.HTTP_409_CONFLICT,
                "IDEMPOTENCY_KEY_CONFLICT",
                "Idempotent payment attribution does not match its order",
            )
        order_state = getattr(order.status, "value", order.status)
        return CanonicalPaymentResult(
            order=order,
            payment_record=payment_record,
            replayed=True,
            order_state=str(order_state),
        )

    async def _latest_payment_record(self, db: AsyncSession, payment_record: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            payment_id = uuid.UUID(str(payment_record["id"]))
        except (KeyError, TypeError, ValueError):
            return payment_record
        current = _payment_mapping_or_none(
            await self._repo.get_by_id(db, payment_id=payment_id)
        )
        result = current or payment_record
        # Preserve receipt_number from the original record even when the
        # re-fetched row (pre-037 schema) doesn't carry the column.
        if result is not payment_record and payment_record.get("receipt_number"):
            result = dict(result)
            result.setdefault("receipt_number", payment_record["receipt_number"])
        return result

    async def _lookup_idempotent_payment(
        self,
        db: AsyncSession,
        *,
        idempotency_key: str,
        allocate_receipt: bool,
    ) -> Mapping[str, Any] | None:
        get_existing = (
            self._repo.get_by_idempotency_key_with_receipt
            if allocate_receipt
            else self._repo.get_by_idempotency_key
        )
        return _payment_mapping_or_none(
            await get_existing(db, idempotency_key=idempotency_key)
        )

    async def _replay_or_conflict_for_locked_order(
        self,
        db: AsyncSession,
        *,
        order: OrderModel,
        existing_payment: Mapping[str, Any],
        amount: Decimal,
        method: str,
        transaction_id: str | None,
        allocate_receipt: bool,
    ) -> CanonicalPaymentResult:
        """Zero-write replay classification against a LOCKED order.

        The caller holds the order FOR UPDATE lock; this helper performs NO
        order query and NO order lock. The replayed payment's order and
        retailer attribution are verified against the locked order, so a
        mismatched record can never replay across orders or retailers.
        """
        if not _same_payment_request(
            existing_payment,
            order_id=str(order.id),
            amount=amount,
            method=method,
            transaction_id=transaction_id,
        ):
            raise _idempotency_conflict()
        _enforce_receipt_on_replay(existing_payment, allocate_receipt)
        if str(existing_payment.get("retailer_id")) != str(order.retailer_id):
            raise _payment_error(
                status.HTTP_409_CONFLICT,
                "IDEMPOTENCY_KEY_CONFLICT",
                "Idempotent payment attribution does not match its order",
            )
        order_state = getattr(order.status, "value", order.status)
        return CanonicalPaymentResult(
            order=order,
            payment_record=existing_payment,
            replayed=True,
            order_state=str(order_state),
        )

    async def _classify_payment_insert_race(
        self,
        db: AsyncSession,
        *,
        exc: IntegrityError,
        order: OrderModel,
        amount: Decimal,
        method: str,
        transaction_id: str | None,
        idempotency_key: str,
        allocate_receipt: bool,
    ) -> CanonicalPaymentResult:
        """Classify an INSERT race on the payment unique constraints.

        R2-R1 SR1: ONLY ``uq_payments_idempotency_key`` and
        ``uq_payments_transaction_id`` may be answered here — the INSERT
        runs inside a SAVEPOINT, so the failed statement is undone while
        the caller's order lock and transaction stay intact. Every other
        IntegrityError (different sqlstate, or a unique violation on any
        other constraint) is re-raised unchanged.
        """
        if (
            _integrity_sqlstate(exc) != _UNIQUE_VIOLATION_SQLSTATE
            or _integrity_constraint_name(exc) not in _REPLAYABLE_UNIQUE_OBJECTS
        ):
            raise exc

        constraint = _integrity_constraint_name(exc)
        if constraint in _TRANSACTION_UNIQUE_OBJECTS:
            existing_transfer = _payment_mapping_or_none(
                await self._repo.get_by_transaction_id(
                    db, transaction_id=transaction_id)
            )
            if existing_transfer is not None:
                raise _duplicate_transfer_reference()
            raise exc

        existing_payment = await self._lookup_idempotent_payment(
            db, idempotency_key=idempotency_key, allocate_receipt=allocate_receipt)
        if existing_payment is None:
            # The constraint fired but no live row carries the key: not an
            # idempotency race this service can explain — propagate as-is.
            raise exc
        return await self._replay_or_conflict_for_locked_order(
            db,
            order=order,
            existing_payment=existing_payment,
            amount=amount,
            method=method,
            transaction_id=transaction_id,
            allocate_receipt=allocate_receipt,
        )

    async def confirm_payment(
        self,
        *,
        db: AsyncSession,
        order_id: str,
        amount: Decimal,
        method: str,
        transaction_id: str | None,
        idempotency_key: str,
        created_by: str | None,
        force_completed: bool = False,
        allocate_receipt: bool = False,
    ) -> CanonicalPaymentResult:
        """The PUBLIC canonical entry — locks and refreshes the order.

        R2-R1 SR1: this entry validates the amount, takes the fast
        idempotency replay path, then LOCKS AND REFRESHES the order
        (FOR UPDATE + populate_existing) and hands that locked order to
        the private locked-order write implementation. There is NO public
        bypass parameter and no public way to hand in a pre-locked order:
        a caller that already holds the lock (the declaration
        confirmation) calls ``_confirm_payment_for_locked_order`` directly.
        """
        _raise_invalid_amount(amount)

        existing_payment = await self._lookup_idempotent_payment(
            db, idempotency_key=idempotency_key, allocate_receipt=allocate_receipt)
        if existing_payment is not None:
            if _same_payment_request(
                existing_payment,
                order_id=order_id,
                amount=amount,
                method=method,
                transaction_id=transaction_id,
            ):
                _enforce_receipt_on_replay(existing_payment, allocate_receipt)
                return await self._replay_result(db, existing_payment)
            raise _idempotency_conflict()

        # The ONLY order lock of the public path: locked-fresh
        # (populate_existing defeats a stale identity map).
        order = await self._get_order_by_id_for_update(db, order_id)
        if not order:
            raise _payment_error(
                status.HTTP_404_NOT_FOUND,
                "ORDER_NOT_FOUND",
                f"Order with ID '{order_id}' not found",
            )

        return await self._confirm_payment_for_locked_order(
            db=db,
            order=order,
            amount=amount,
            method=method,
            transaction_id=transaction_id,
            idempotency_key=idempotency_key,
            created_by=created_by,
            force_completed=force_completed,
            allocate_receipt=allocate_receipt,
        )

    async def _confirm_payment_for_locked_order(
        self,
        *,
        db: AsyncSession,
        order: OrderModel,
        amount: Decimal,
        method: str,
        transaction_id: str | None,
        idempotency_key: str,
        created_by: str | None,
        force_completed: bool = False,
        allocate_receipt: bool = False,
    ) -> CanonicalPaymentResult:
        """Private locked-order write implementation.

        PRECONDITION: the caller holds this order's FOR UPDATE lock in the
        same transaction — the public entry takes it, the declaration
        confirmation already holds it. This method runs the entire write
        sequence (idempotency re-check, shared payment-history contract,
        state/balance/credit/transfer-reference prechecks, hold
        verification and the financial writes) and NEVER queries or locks
        the order row.
        """
        _raise_invalid_amount(amount)

        existing_payment = await self._lookup_idempotent_payment(
            db, idempotency_key=idempotency_key, allocate_receipt=allocate_receipt)
        if existing_payment is not None:
            return await self._replay_or_conflict_for_locked_order(
                db,
                order=order,
                existing_payment=existing_payment,
                amount=amount,
                method=method,
                transaction_id=transaction_id,
                allocate_receipt=allocate_receipt,
            )

        await self._assert_history_integrity(db, order)

        current_state = OrderState(order.status.value)
        order_total = order.total_amount
        prior_paid = await self._repo.get_order_paid_total(db, order_id=order.id)
        is_credit_collection = False

        if current_state == OrderState.PAID:
            if method not in {"cash", "transfer"}:
                raise _payment_error(
                    status.HTTP_409_CONFLICT,
                    "ORDER_ALREADY_PAID",
                    "Paid credit orders accept only cash or transfer collections",
                )
            # RAW exposure (never clamped): a negative value on a
            # credit-bearing order is corrupt history and fails closed with
            # a named integrity refusal. A zero-credit PAID order simply has
            # no credit exposure to collect.
            credit_total = await self._repo.get_order_method_total(
                db, order_id=order.id, methods=("credit",))
            collection_total = await self._repo.get_order_method_total(
                db, order_id=order.id, methods=("cash", "transfer"))
            credit_collection_exposure = credit_total - collection_total
            if credit_total > 0 and credit_collection_exposure < 0:
                raise _credit_hold_mismatch(
                    f"Credit history is over-collected: credit {credit_total} "
                    f"vs collections {collection_total}")
            if credit_collection_exposure <= 0:
                raise _payment_error(
                    status.HTTP_409_CONFLICT,
                    "ORDER_ALREADY_PAID",
                    "Order has no remaining credit exposure to collect",
                )
            if amount > credit_collection_exposure:
                raise _payment_error(
                    status.HTTP_400_BAD_REQUEST,
                    "PAYMENT_EXCEEDS_REMAINING",
                    "Payment amount exceeds remaining credit exposure",
                )
            target_state = OrderState.PAID
            is_credit_collection = True
        else:
            remaining_balance = order_total - prior_paid
            if amount > remaining_balance:
                raise _payment_error(
                    status.HTTP_400_BAD_REQUEST,
                    "PAYMENT_EXCEEDS_REMAINING",
                    "Payment amount exceeds remaining balance",
                )
            if current_state not in (OrderState.CONFIRMED, OrderState.PARTIALLY_PAID):
                raise _payment_error(
                    status.HTTP_409_CONFLICT,
                    "INVALID_STATE_TRANSITION",
                    "Order must be confirmed or partially_paid before payment",
                )
            if method == "credit":
                credit_count = await self._repo.count_order_payments(db, order_id=order.id, method="credit")
                if credit_count > 0:
                    raise _payment_error(
                        status.HTTP_409_CONFLICT,
                        "DUPLICATE_CREDIT_PAYMENT",
                        "Only one credit payment is allowed per order",
                    )
                if prior_paid > 0:
                    raise _payment_error(
                        status.HTTP_400_BAD_REQUEST,
                        "CREDIT_SPLIT_TENDER_UNSUPPORTED",
                        "Credit is allowed only on an order with no prior cash or transfer settlement",
                    )
                if amount != order_total:
                    raise _payment_error(
                        status.HTTP_400_BAD_REQUEST,
                        "CREDIT_AMOUNT_MISMATCH",
                        "Credit amount must equal order total",
                    )
            cumulative_after_payment = prior_paid + amount
            target_state = OrderState.PAID if cumulative_after_payment >= order_total else OrderState.PARTIALLY_PAID

        if method == "transfer" and transaction_id:
            existing_transfer = _payment_mapping_or_none(
                await self._repo.get_by_transaction_id(db, transaction_id=transaction_id)
            )
            if existing_transfer:
                raise _duplicate_transfer_reference()

        # R2 C1: lock and verify the order's credit-hold lifecycle BEFORE
        # any financial write (payment, receipt, ledger, binding). Lock
        # order: order -> hold -> payment/receipt/ledger -> binding.
        holds = await self._lock_hold_rows(db, order.id)
        await self._verify_hold_contract(
            db, order, holds,
            method=method,
            amount=amount,
            is_credit_collection=is_credit_collection,
        )

        payment_status = (
            "completed"
            if force_completed or is_credit_collection or (method == "transfer" and target_state == OrderState.PAID)
            else "pending"
        )

        # Receipt allocation is opt-in. Only the declaration-confirmation flow
        # passes allocate_receipt=True; the direct pay_order path leaves the
        # default False so its behavior (and the I2A tests) is unchanged.
        #
        # The allocation and the INSERT share ONE savepoint: a unique-constraint
        # race on the payment row rolls both back together, so a replayed
        # confirmation never leaks a receipt gap, the caller's order lock
        # survives, and only the two payment unique constraints are answered.
        receipt_number: str | None = None
        try:
            async with db.begin_nested():
                if allocate_receipt and payment_status == "completed":
                    receipt_number = await self._repo.allocate_receipt_number(db)

                payment_record = await self._repo.create(
                    db,
                    order_id=order.id,
                    retailer_id=order.retailer_id,
                    transaction_id=transaction_id,
                    idempotency_key=idempotency_key,
                    amount=amount,
                    method=method,
                    status=payment_status,
                    created_by=_uuid_or_none(created_by),
                    receipt_number=receipt_number,
                )
        except IntegrityError as exc:
            return await self._classify_payment_insert_race(
                db,
                exc=exc,
                order=order,
                amount=amount,
                method=method,
                transaction_id=transaction_id,
                idempotency_key=idempotency_key,
                allocate_receipt=allocate_receipt,
            )

        payment_service = payment_service_module.PaymentService()
        try:
            if is_credit_collection:
                # R2: the converted lifecycle row is preserved untouched;
                # a collection only reduces the real credit exposure and
                # the binding cache. Lock order: ledger -> binding.
                await ledger_service_module.LedgerService(db).post_payment_received(
                    order_id=order.id,
                    amount=amount,
                    description=f"Credit collection for order {order.id} - Amount: {amount}",
                )
                await payment_service._apply_outstanding_balance_delta(
                    db,
                    wholesaler_id=order.wholesaler_id,
                    retailer_id=order.retailer_id,
                    delta=-amount,
                )
                await db.refresh(order)
            else:
                if method == "credit":
                    # R2: the full active hold converts to the real credit
                    # exposure. The binding is NOT incremented again — the
                    # confirm-time reservation already occupies the cache
                    # (removes the parent double-count).
                    await self._convert_hold(db, holds, created_by)
                else:
                    # R2: cash/transfer settlement reduces the order's own
                    # hold first; the binding cache drops by the same
                    # amount — but only AFTER the whole payment-side write
                    # sequence below (E1/F3: frozen C6 resource partial
                    # order is hold -> payment/receipt/ledger -> binding).
                    await self._reduce_hold(db, holds, amount, created_by)
                # F2/SR1-R1: the caller's locked order is handed to the
                # command service's PRIVATE locked-order implementation —
                # the whole payment chain takes exactly ONE order FOR
                # UPDATE (this method's own lock; the declaration chain's
                # single declaration-side lock). The binding identity is
                # captured from the caller's locked order BEFORE the
                # reassignment: same locked row, same transaction.
                binding_ws = order.wholesaler_id
                binding_ret = order.retailer_id
                order = (
                    await order_command_module.OrderCommandService(
                        db
                    )._apply_payment_transition_for_locked(
                        order,
                        target_state,
                        payment_method=method,
                        updated_by=created_by,
                    )
                ).order
                order_status = getattr(order.status, "value", order.status)
                if not force_completed and order_status == OrderState.PAID.value:
                    await self._repo.update_cash_transfer_to_completed(db, order_id=order.id)
                if method != "credit":
                    # E1/F3: the binding cache is the LAST financial write
                    # of the settlement path — after the hold reduction,
                    # the payment row, the receipt, the transition's
                    # ledger posting and the cash/transfer batch settle,
                    # all inside the SAME transaction (a failure at any
                    # earlier point rolls the whole settlement back; a
                    # failure here rolls back everything before it too).
                    await payment_service._apply_outstanding_balance_delta(
                        db,
                        wholesaler_id=binding_ws,
                        retailer_id=binding_ret,
                        delta=-amount,
                    )
        except HTTPException as exc:
            raise CanonicalPaymentMutationHttpError(exc) from exc

        payment_record = await self._latest_payment_record(db, payment_record)
        order_state = getattr(order.status, "value", order.status)
        return CanonicalPaymentResult(
            order=order,
            payment_record=payment_record,
            replayed=False,
            order_state=str(order_state),
        )

    async def _assert_history_integrity(self, db: AsyncSession, order: OrderModel) -> None:
        """R2-R1 SR1: the SHARED valid-payment-history contract, enforced
        here on the write path and by both receivables read paths. Live
        rows must carry a positive finite amount, a canonical method, a
        known status and the order's own retailer; anything else is the
        named PAYMENT_HISTORY_INTEGRITY refusal — never aggregated around.
        """
        await assert_valid_payment_history(
            db, order_ids=[order.id], context="Payment write path")
