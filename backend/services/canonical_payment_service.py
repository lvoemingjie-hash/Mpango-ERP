from __future__ import annotations

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
        return current or payment_record

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
            existing_payment = _payment_mapping_or_none(
                await self._repo.get_by_idempotency_key(db, idempotency_key=idempotency_key)
            )
            if existing_payment:
                if _same_payment_request(
                    existing_payment,
                    order_id=order_id,
                    amount=amount,
                    method=method,
                    transaction_id=transaction_id,
                ):
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
                await self._repo.get_by_idempotency_key(db, idempotency_key=idempotency_key)
            )
            if existing_payment:
                if _same_payment_request(
                    existing_payment,
                    order_id=str(order.id),
                    amount=amount,
                    method=method,
                    transaction_id=transaction_id,
                ):
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
