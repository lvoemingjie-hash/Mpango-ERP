from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Mapping

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.order import Order
from repositories.payment_repository import PaymentRepository


class PaymentService:
    def __init__(self) -> None:
        self._repo = PaymentRepository()

    async def create_payment(
        self,
        *,
        tenant_db: AsyncSession,
        order_id: str,
        amount: Decimal,
        method: str,
        transaction_id: str | None,
        created_by: str | None,
    ) -> Mapping[str, Any]:
        try:
            order_uuid = uuid.UUID(order_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_ORDER_ID", "message": "Invalid order_id"},
            )

        created_by_uuid: uuid.UUID | None = None
        if created_by:
            try:
                created_by_uuid = uuid.UUID(created_by)
            except Exception:
                created_by_uuid = None

        if method == "transfer" and not transaction_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "MISSING_TRANSACTION_ID", "message": "transaction_id is required for transfer"},
            )

        if transaction_id:
            existing = await self._repo.get_by_transaction_id(tenant_db, transaction_id=transaction_id)
            if existing:
                if (
                    str(existing["order_id"]) == str(order_uuid)
                    and Decimal(str(existing["amount"])) == amount
                    and str(existing["method"]) == method
                ):
                    return existing

                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "DUPLICATE_TRANSACTION_ID",
                        "message": "transaction_id already used with different payload",
                    },
                )

        order = (
            await tenant_db.execute(
                select(Order).where(Order.id == order_uuid).where(Order.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "ORDER_NOT_FOUND", "message": f"Order with ID '{order_id}' not found"},
            )

        retailer_id: uuid.UUID = order.retailer_id

        payment_status = "completed" if method == "transfer" else "pending"
        try:
            payment = await self._repo.create(
                tenant_db,
                order_id=order_uuid,
                retailer_id=retailer_id,
                transaction_id=transaction_id,
                amount=amount,
                method=method,
                status=payment_status,
                created_by=created_by_uuid,
            )
        except IntegrityError:
            if not transaction_id:
                raise

            existing = await self._repo.get_by_transaction_id(tenant_db, transaction_id=transaction_id)
            if not existing:
                raise

            if (
                str(existing["order_id"]) == str(order_uuid)
                and Decimal(str(existing["amount"])) == amount
                and str(existing["method"]) == method
            ):
                return existing

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "DUPLICATE_TRANSACTION_ID",
                    "message": "transaction_id already used with different payload",
                },
            )

        if method == "transfer":
            await self._apply_outstanding_balance_delta(
                tenant_db,
                wholesaler_id=order.wholesaler_id,
                retailer_id=retailer_id,
                delta=-amount,
            )

        if method == "credit":
            await self._apply_outstanding_balance_delta(
                tenant_db,
                wholesaler_id=order.wholesaler_id,
                retailer_id=retailer_id,
                delta=amount,
            )

        if method == "cash":
            await self._apply_outstanding_balance_delta(
                tenant_db,
                wholesaler_id=order.wholesaler_id,
                retailer_id=retailer_id,
                delta=-amount,
            )

        return payment

    async def _apply_outstanding_balance_delta(
        self,
        tenant_db: AsyncSession,
        *,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
        delta: Decimal,
    ) -> None:
        result = await tenant_db.execute(
            text(
                """
                UPDATE public.wholesaler_retailer_bindings
                SET outstanding_balance = outstanding_balance + :delta,
                    updated_at = now()
                WHERE wholesaler_id = :wholesaler_id
                  AND retailer_id = :retailer_id
                  AND is_deleted IS FALSE
                """
            ),
            {"delta": delta, "wholesaler_id": wholesaler_id, "retailer_id": retailer_id},
        )
        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "BINDINGNOTFOUND", "message": "Retailer not bound to wholesaler"},
            )
