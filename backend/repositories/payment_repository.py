from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import bindparam, text
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
                SELECT id, order_id, retailer_id, transaction_id, idempotency_key, amount, method, status, receipt_number, created_at, updated_at
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
                SELECT id, order_id, retailer_id, transaction_id, idempotency_key, amount, method, status, receipt_number, created_at, updated_at
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
                f"idempotency_key, amount, method, status, receipt_number, created_at, updated_at "
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
                "idempotency_key, amount, method, status, receipt_number, created_at, updated_at "
                "FROM payments WHERE id = :pid AND is_deleted IS FALSE LIMIT 1"
            ),
            {"pid": payment_id},
        )
        return result.mappings().first()

    async def count_order_payments(
        self,
        db: AsyncSession,
        *,
        order_id: uuid.UUID,
        method: str,
    ) -> int:
        """Return count of non-deleted payments for an order with the given method."""
        result = await db.execute(
            text(
                "SELECT COUNT(*) FROM payments "
                "WHERE order_id = :order_id AND is_deleted IS FALSE "
                "AND method = :method"
            ),
            {"order_id": order_id, "method": method},
        )
        return int(result.scalar() or 0)

    async def get_order_paid_total(
        self,
        db: AsyncSession,
        *,
        order_id: uuid.UUID,
    ) -> Decimal:
        """Return the sum of cash and transfer payments for an order.

        Credit payments are excluded because they represent receivable
        increases, not actual settlement.  Only cash and transfer count
        toward the paid-total used for order state calculations.
        """
        result = await db.execute(
            text(
                "SELECT COALESCE(SUM(amount), 0) "
                "FROM payments "
                "WHERE order_id = :order_id AND is_deleted IS FALSE "
                "AND method IN ('cash', 'transfer')"
            ),
            {"order_id": order_id},
        )
        return Decimal(str(result.scalar() or 0))

    async def get_order_method_total(
        self,
        db: AsyncSession,
        *,
        order_id: uuid.UUID,
        methods: tuple[str, ...],
    ) -> Decimal:
        """Return the sum of non-deleted payments for an order and methods."""
        if not methods:
            return Decimal("0")

        stmt = text(
            "SELECT COALESCE(SUM(amount), 0) "
            "FROM payments "
            "WHERE order_id = :order_id AND is_deleted IS FALSE "
            "AND method IN :methods"
        ).bindparams(
            bindparam("methods", expanding=True),
        )
        result = await db.execute(
            stmt,
            {"order_id": order_id, "methods": list(methods)},
        )
        return Decimal(str(result.scalar() or 0))

    async def get_order_credit_exposure(
        self,
        db: AsyncSession,
        *,
        order_id: uuid.UUID,
    ) -> Decimal:
        """Return credit payments less cash/transfer collections, never negative."""
        credit_total = await self.get_order_method_total(
            db, order_id=order_id, methods=("credit",),
        )
        collection_total = await self.get_order_method_total(
            db, order_id=order_id, methods=("cash", "transfer"),
        )
        exposure = credit_total - collection_total
        return exposure if exposure > Decimal("0") else Decimal("0")

    async def update_cash_transfer_to_completed(
        self,
        db: AsyncSession,
        *,
        order_id: uuid.UUID,
    ) -> int:
        """S5-D4B: Idempotently settle cash/transfer payments for a PAID order.

        Advances `payments.status` from 'pending' to 'completed' for all rows
        matching the order that are method IN ('cash', 'transfer') AND currently
        'pending'. This closes the lifecycle gap where a fully-paid order left
        its cash/transfer payments stuck at 'pending'.

        Contract:
          - Scoped to the single order_id (no cross-order side effects).
          - Only cash/transfer rows touched; credit rows are left unchanged.
          - Only 'pending' rows touched; already-'completed' rows are no-ops
            (idempotent: safe to call repeatedly).
          - Returns the number of rows actually updated.

        Args:
            db: AsyncSession (tenant schema).
            order_id: Order whose cash/transfer payments should be settled.

        Returns:
            Count of payment rows updated (0 if none were pending).
        """
        result = await db.execute(
            text(
                "UPDATE payments "
                "SET status = 'completed', updated_at = now() "
                "WHERE order_id = :order_id "
                "  AND is_deleted IS FALSE "
                "  AND method IN ('cash', 'transfer') "
                "  AND status = 'pending'"
            ),
            {"order_id": order_id},
        )
        return int(result.rowcount or 0)

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
        receipt_number: str | None = None,
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
                    receipt_number,
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
                    :receipt_number,
                    :created_at,
                    :updated_at,
                    FALSE,
                    :created_by,
                    :updated_by
                )
                RETURNING id, order_id, retailer_id, transaction_id, idempotency_key, amount, method, status, receipt_number, created_at, updated_at
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
                "receipt_number": receipt_number,
                "created_at": now,
                "updated_at": now,
                "created_by": created_by,
                "updated_by": created_by,
            },
        )
        return result.mappings().one()

    async def allocate_receipt_number(self, db: AsyncSession) -> str:
        """Atomically allocate the next tenant-local receipt number.

        Uses the ``receipt_sequences`` allocator table within the caller's
        transaction. The increment is rolled back together with the payment if
        the surrounding transaction fails, so a failed confirmation never leaks
        a receipt gap.

        Format: ``RCT-YYYYMMDD-NNNNNN`` where the date is the aware UTC business
        date at allocation time.
        """
        from datetime import datetime, timezone

        business_date = datetime.now(timezone.utc).strftime("%Y%m%d")
        result = await db.execute(
            text(
                """
                INSERT INTO receipt_sequences (business_date, next_seq)
                VALUES (:business_date, 1)
                ON CONFLICT (business_date) DO UPDATE
                SET next_seq = receipt_sequences.next_seq + 1
                RETURNING next_seq
                """
            ),
            {"business_date": business_date},
        )
        seq = int(result.scalar() or 1)
        return f"RCT-{business_date}-{seq:06d}"
