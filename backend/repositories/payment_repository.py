from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PaymentRepository:
    async def get_by_idempotency_key(
        self,
        db: AsyncSession,
        *,
        idempotency_key: str,
    ) -> Mapping[str, Any] | None:
        result = await db.execute(
            text(
                """
                SELECT id, order_id, retailer_id, transaction_id, idempotency_key, amount, method, status, created_at, updated_at
                FROM payments
                WHERE idempotency_key = :idempotency_key AND is_deleted IS FALSE
                LIMIT 1
                """
            ),
            {"idempotency_key": idempotency_key},
        )
        row = result.mappings().first()
        return row

    async def get_by_transaction_id(
        self,
        db: AsyncSession,
        *,
        transaction_id: str,
    ) -> Mapping[str, Any] | None:
        result = await db.execute(
            text(
                """
                SELECT id, order_id, retailer_id, transaction_id, idempotency_key, amount, method, status, created_at, updated_at
                FROM payments
                WHERE transaction_id = :transaction_id AND is_deleted IS FALSE
                LIMIT 1
                """
            ),
            {"transaction_id": transaction_id},
        )
        row = result.mappings().first()
        return row

    async def list_paginated(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        size: int = 20,
        order_id: str | None = None,
        method: str | None = None,
        status: str | None = None,
    ) -> tuple[list[Mapping[str, Any]], int]:
        filters = ["is_deleted IS FALSE"]
        params: dict[str, Any] = {}
        if order_id:
            filters.append("order_id = :order_id")
            params["order_id"] = uuid.UUID(order_id)
        if method:
            filters.append("method = :method")
            params["method"] = method
        if status:
            filters.append("status = :pstatus")
            params["pstatus"] = status

        where = " AND ".join(filters)

        count_result = await db.execute(
            text(f"SELECT COUNT(*) FROM payments WHERE {where}"),
            params,
        )
        total = int(count_result.scalar() or 0)

        offset = (page - 1) * size
        params["limit"] = size
        params["offset"] = offset
        result = await db.execute(
            text(
                f"SELECT id, order_id, retailer_id, transaction_id, "
                f"idempotency_key, amount, method, status, created_at, updated_at "
                f"FROM payments WHERE {where} "
                f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        )
        rows = [dict(r) for r in result.mappings().all()]
        return rows, total

    async def get_by_id(
        self,
        db: AsyncSession,
        *,
        payment_id: uuid.UUID,
    ) -> Mapping[str, Any] | None:
        result = await db.execute(
            text(
                "SELECT id, order_id, retailer_id, transaction_id, "
                "idempotency_key, amount, method, status, created_at, updated_at "
                "FROM payments WHERE id = :pid AND is_deleted IS FALSE LIMIT 1"
            ),
            {"pid": payment_id},
        )
        return result.mappings().first()

    async def get_order_paid_total(
        self,
        db: AsyncSession,
        *,
        order_id: uuid.UUID,
    ) -> Decimal:
        """Return the sum of all non-deleted payments for an order."""
        result = await db.execute(
            text(
                "SELECT COALESCE(SUM(amount), 0) "
                "FROM payments "
                "WHERE order_id = :order_id AND is_deleted IS FALSE"
            ),
            {"order_id": order_id},
        )
        return Decimal(str(result.scalar() or 0))

    async def create(
        self,
        db: AsyncSession,
        *,
        order_id: uuid.UUID,
        retailer_id: uuid.UUID,
        transaction_id: str | None,
        idempotency_key: str | None,
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
                    idempotency_key,
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
                    :idempotency_key,
                    :amount,
                    :method,
                    :status,
                    :created_at,
                    :updated_at,
                    FALSE,
                    :created_by,
                    :updated_by
                )
                RETURNING id, order_id, retailer_id, transaction_id, idempotency_key, amount, method, status, created_at, updated_at
                """
            ),
            {
                "order_id": order_id,
                "retailer_id": retailer_id,
                "transaction_id": transaction_id,
                "idempotency_key": idempotency_key,
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
