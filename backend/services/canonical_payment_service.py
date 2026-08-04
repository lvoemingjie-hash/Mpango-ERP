from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.order_state import OrderState
from models.order import Order as OrderModel
import repositories.payment_repository as payment_repository_module
import services.ledger_service as ledger_service_module
import services.order_service as order_service_module
import services.payment_service as payment_service_module


def _payment_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


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
            .where(OrderModel.is_deleted == False)
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

    async def _replay_result(self, db: AsyncSession, payment_record: Mapping[str, Any]) -> CanonicalPaymentResult:
        order = await self._get_order_for_payment_record(db, uuid.UUID(str(payment_record["order_id"])))
        if not order:
            raise _payment_error(
                status.HTTP_404_NOT_FOUND,
                "ORDER_NOT_FOUND",
                "Order for idempotent payment was not found",
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
        locked_order: OrderModel | None = None,
        target_state: OrderState | None = None,
        is_credit_collection: bool | None = None,
        skip_prechecks: bool = False,
        allocate_receipt: bool = False,
    ) -> CanonicalPaymentResult:
        if amount.is_nan() or amount.is_infinite() or amount <= 0:
            raise _payment_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_PAYMENT_AMOUNT",
                "Payment amount must be a positive finite number",
            )

        if skip_prechecks:
            if locked_order is None or target_state is None or is_credit_collection is None:
                raise ValueError("skip_prechecks requires locked_order, target_state, and is_credit_collection")
            order = locked_order
        else:
            # Use the receipt-aware lookup when receipt allocation is needed
            # so that replay enforcement can see receipt_number (present only
            # in post-037 schemas).
            get_existing = (
                self._repo.get_by_idempotency_key_with_receipt
                if allocate_receipt
                else self._repo.get_by_idempotency_key
            )
            existing_payment = _payment_mapping_or_none(
                await get_existing(db, idempotency_key=idempotency_key)
            )
            if existing_payment:
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

            order = await self._get_order_by_id_for_update(db, order_id)
            if not order:
                raise _payment_error(
                    status.HTTP_404_NOT_FOUND,
                    "ORDER_NOT_FOUND",
                    f"Order with ID '{order_id}' not found",
                )

            existing_payment = _payment_mapping_or_none(
                await get_existing(db, idempotency_key=idempotency_key)
            )
            if existing_payment:
                if _same_payment_request(
                    existing_payment,
                    order_id=str(order.id),
                    amount=amount,
                    method=method,
                    transaction_id=transaction_id,
                ):
                    _enforce_receipt_on_replay(existing_payment, allocate_receipt)
                    return await self._replay_result(db, existing_payment)
                raise _idempotency_conflict()

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
                credit_collection_exposure = await self._repo.get_order_credit_exposure(db, order_id=order.id)
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

        payment_status = (
            "completed"
            if force_completed or is_credit_collection or (method == "transfer" and target_state == OrderState.PAID)
            else "pending"
        )

        # Receipt allocation is opt-in. Only the declaration-confirmation flow
        # passes allocate_receipt=True; the direct pay_order path leaves the
        # default False so its behavior (and the I2A tests) is unchanged.
        receipt_number: str | None = None
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
            created_by=created_by,
            receipt_number=receipt_number,
        )

        payment_service = payment_service_module.PaymentService()
        try:
            if is_credit_collection:
                await payment_service._apply_outstanding_balance_delta(
                    db,
                    wholesaler_id=order.wholesaler_id,
                    retailer_id=order.retailer_id,
                    delta=-amount,
                )
                await ledger_service_module.LedgerService(db).post_payment_received(
                    order_id=order.id,
                    amount=amount,
                    description=f"Credit collection for order {order.id} - Amount: {amount}",
                )
                await db.refresh(order)
            else:
                if method == "credit":
                    await payment_service._apply_outstanding_balance_delta(
                        db,
                        wholesaler_id=order.wholesaler_id,
                        retailer_id=order.retailer_id,
                        delta=amount,
                    )
                order = await order_service_module.OrderService(db).transition(
                    order_id=order.id,
                    target_state=target_state,
                    reason="Payment recorded",
                    updated_by=created_by,
                    payment_method=method,
                )
                order_status = getattr(order.status, "value", order.status)
                if not force_completed and order_status == OrderState.PAID.value:
                    await self._repo.update_cash_transfer_to_completed(db, order_id=order.id)
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
