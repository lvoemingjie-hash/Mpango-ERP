from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PaymentRepository:
    async def get_by_transaction_id(
        self,
        db: AsyncSession,
        *,
        transaction_id: str,
    ) -> Mapping[str, Any] | None:
        result = await db.execute(
            text(
                """
                SELECT id, order_id, retailer_id, transaction_id, amount, method, status, created_at, updated_at
                FROM payments
                WHERE transaction_id = :transaction_id AND is_deleted IS FALSE
                LIMIT 1
                """
            ),
            {"transaction_id": transaction_id},
        )
        row = result.mappings().first()
        return row

    async def create(
        self,
        db: AsyncSession,
        *,
        order_id: uuid.UUID,
        retailer_id: uuid.UUID,
        transaction_id: str | None,
        amount: Decimal,
        method: str,
        status: str,
        created_by: uuid.UUID | None,
    ) -> Mapping[str, Any]:
        now = datetime.utcnow()
        result = await db.execute(
            text(
                """
                INSERT INTO payments (
                    order_id,
                    retailer_id,
                    transaction_id,
                    amount,
                    method,
                    status,
                    created_at,
                    updated_at,
                    is_deleted,
                    created_by,
                    updated_by
                )
                VALUES (
                    :order_id,
                    :retailer_id,
                    :transaction_id,
                    :amount,
                    :method,
                    :status,
                    :created_at,
                    :updated_at,
                    FALSE,
                    :created_by,
                    :updated_by
                )
                RETURNING id, order_id, retailer_id, transaction_id, amount, method, status, created_at, updated_at
                """
            ),
            {
                "order_id": order_id,
                "retailer_id": retailer_id,
                "transaction_id": transaction_id,
                "amount": amount,
                "method": method,
                "status": status,
                "created_at": now,
                "updated_at": now,
                "created_by": created_by,
                "updated_by": created_by,
            },
        )
        return result.mappings().one()
