"""Repository for ``payment_declarations`` (DC-12R1-S3-S2B-I2B).

Tenant-scoped. Declarations are immutable audit rows: no soft delete, only
terminal status transitions (pending -> confirmed | rejected). The receipt
number is resolved from the linked canonical payment row, never stored on the
declaration itself.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PaymentDeclarationRepository:
    # ------------------------------------------------------------------
    # Scoped single-declaration fetches (dual-key for ownership enforcement)
    # ------------------------------------------------------------------
    async def get_by_id(
        self,
        db: AsyncSession,
        *,
        declaration_id: uuid.UUID,
    ) -> Mapping[str, Any] | None:
        result = await db.execute(
            text(
                """
                SELECT id, order_id, retailer_id, wholesaler_id, declared_amount,
                       method, transfer_reference, status, idempotency_key,
                       submitted_by, submitted_at, confirmed_by, confirmed_at,
                       confirmation_payment_id, rejected_by, rejected_at, reason
                FROM payment_declarations
                WHERE id = :did
                LIMIT 1
                """
            ),
            {"did": declaration_id},
        )
        return result.mappings().first()

    async def get_by_wholesaler_dual_key(
        self,
        db: AsyncSession,
        *,
        declaration_id: uuid.UUID,
        wholesaler_id: uuid.UUID,
    ) -> Mapping[str, Any] | None:
        """Fetch one declaration by (id, wholesaler_id) — cashier read."""
        result = await db.execute(
            text(
                """
                SELECT id, order_id, retailer_id, wholesaler_id, declared_amount,
                       method, transfer_reference, status, idempotency_key,
                       submitted_by, submitted_at, confirmed_by, confirmed_at,
                       confirmation_payment_id, rejected_by, rejected_at, reason
                FROM payment_declarations
                WHERE id = :did AND wholesaler_id = :wid
                LIMIT 1
                """
            ),
            {"did": declaration_id, "wid": wholesaler_id},
        )
        return result.mappings().first()

    async def get_by_retailer_dual_key(
        self,
        db: AsyncSession,
        *,
        declaration_id: uuid.UUID,
        retailer_id: uuid.UUID,
        wholesaler_id: uuid.UUID,
    ) -> Mapping[str, Any] | None:
        """Fetch one declaration by (id, retailer_id, wholesaler_id) — retailer read."""
        result = await db.execute(
            text(
                """
                SELECT id, order_id, retailer_id, wholesaler_id, declared_amount,
                       method, transfer_reference, status, idempotency_key,
                       submitted_by, submitted_at, confirmed_by, confirmed_at,
                       confirmation_payment_id, rejected_by, rejected_at, reason
                FROM payment_declarations
                WHERE id = :did AND retailer_id = :rid AND wholesaler_id = :wid
                LIMIT 1
                """
            ),
            {"did": declaration_id, "rid": retailer_id, "wid": wholesaler_id},
        )
        return result.mappings().first()

    async def get_for_update_by_wholesaler(
        self,
        db: AsyncSession,
        *,
        declaration_id: uuid.UUID,
        wholesaler_id: uuid.UUID,
    ) -> Mapping[str, Any] | None:
        """Lock one declaration by (id, wholesaler_id) — ownership enforcement."""
        result = await db.execute(
            text(
                """
                SELECT id, order_id, retailer_id, wholesaler_id, declared_amount,
                       method, transfer_reference, status, idempotency_key,
                       submitted_by, submitted_at, confirmed_by, confirmed_at,
                       confirmation_payment_id, rejected_by, rejected_at, reason
                FROM payment_declarations
                WHERE id = :did AND wholesaler_id = :wid
                FOR UPDATE
                """
            ),
            {"did": declaration_id, "wid": wholesaler_id},
        )
        return result.mappings().first()

    async def get_by_retailer_idempotency(
        self,
        db: AsyncSession,
        *,
        retailer_id: uuid.UUID,
        idempotency_key: str,
    ) -> Mapping[str, Any] | None:
        result = await db.execute(
            text(
                """
                SELECT id, order_id, retailer_id, wholesaler_id, declared_amount,
                       method, transfer_reference, status, idempotency_key,
                       submitted_by, submitted_at, confirmed_by, confirmed_at,
                       confirmation_payment_id, rejected_by, rejected_at, reason
                FROM payment_declarations
                WHERE retailer_id = :retailer_id
                  AND idempotency_key = :idempotency_key
                LIMIT 1
                """
            ),
            {"retailer_id": retailer_id, "idempotency_key": idempotency_key},
        )
        return result.mappings().first()

    async def create(
        self,
        db: AsyncSession,
        *,
        order_id: uuid.UUID,
        retailer_id: uuid.UUID,
        wholesaler_id: uuid.UUID,
        declared_amount: Decimal,
        method: str,
        transfer_reference: str | None,
        idempotency_key: str,
        submitted_by: uuid.UUID,
    ) -> Mapping[str, Any]:
        result = await db.execute(
            text(
                """
                INSERT INTO payment_declarations (
                    order_id, retailer_id, wholesaler_id, declared_amount,
                    method, transfer_reference, status, idempotency_key,
                    submitted_by, submitted_at
                )
                VALUES (
                    :order_id, :retailer_id, :wholesaler_id, :declared_amount,
                    :method, :transfer_reference, 'pending', :idempotency_key,
                    :submitted_by, now()
                )
                RETURNING id, order_id, retailer_id, wholesaler_id, declared_amount,
                          method, transfer_reference, status, idempotency_key,
                          submitted_by, submitted_at, confirmed_by, confirmed_at,
                          confirmation_payment_id, rejected_by, rejected_at, reason
                """
            ),
            {
                "order_id": order_id,
                "retailer_id": retailer_id,
                "wholesaler_id": wholesaler_id,
                "declared_amount": declared_amount,
                "method": method,
                "transfer_reference": transfer_reference,
                "idempotency_key": idempotency_key,
                "submitted_by": submitted_by,
            },
        )
        return result.mappings().one()

    async def mark_confirmed(
        self,
        db: AsyncSession,
        *,
        declaration_id: uuid.UUID,
        wholesaler_id: uuid.UUID,
        confirmed_by: uuid.UUID,
        confirmation_payment_id: uuid.UUID,
    ) -> None:
        result = await db.execute(
            text(
                """
                UPDATE payment_declarations
                SET status = 'confirmed',
                    confirmed_by = :confirmed_by,
                    confirmed_at = now(),
                    confirmation_payment_id = :confirmation_payment_id
                WHERE id = :did AND wholesaler_id = :wid AND status = 'pending'
                """
            ),
            {
                "did": declaration_id,
                "wid": wholesaler_id,
                "confirmed_by": confirmed_by,
                "confirmation_payment_id": confirmation_payment_id,
            },
        )
        if result.rowcount != 1:
            raise RuntimeError("mark_confirmed: expected exactly 1 row updated")

    async def mark_rejected(
        self,
        db: AsyncSession,
        *,
        declaration_id: uuid.UUID,
        wholesaler_id: uuid.UUID,
        rejected_by: uuid.UUID,
        reason: str,
    ) -> None:
        result = await db.execute(
            text(
                """
                UPDATE payment_declarations
                SET status = 'rejected',
                    rejected_by = :rejected_by,
                    rejected_at = now(),
                    reason = :reason
                WHERE id = :did AND wholesaler_id = :wid AND status = 'pending'
                """
            ),
            {
                "did": declaration_id,
                "wid": wholesaler_id,
                "rejected_by": rejected_by,
                "reason": reason,
            },
        )
        if result.rowcount != 1:
            raise RuntimeError("mark_rejected: expected exactly 1 row updated")

    async def list_by_retailer(
        self,
        db: AsyncSession,
        *,
        retailer_id: uuid.UUID,
        wholesaler_id: uuid.UUID,
        page: int,
        size: int,
        status: str | None = None,
    ) -> tuple[list[Mapping[str, Any]], int]:
        predicates = [
            "d.retailer_id = :retailer_id",
            "d.wholesaler_id = :wholesaler_id",
        ]
        params: dict[str, Any] = {
            "retailer_id": retailer_id,
            "wholesaler_id": wholesaler_id,
        }
        if status is not None:
            predicates.append("d.status = :status")
            params["status"] = status
        where_sql = " AND ".join(predicates)

        total = int(
            (
                await db.execute(
                    text(f"SELECT COUNT(*) FROM payment_declarations d WHERE {where_sql}"),
                    params,
                )
            ).scalar()
            or 0
        )

        page_params = dict(params)
        page_params["limit"] = size
        page_params["offset"] = (page - 1) * size
        rows = (
            await db.execute(
                text(
                    "SELECT d.id, d.order_id, d.retailer_id, d.wholesaler_id, "
                    "d.declared_amount, d.method, d.transfer_reference, d.status, "
                    "d.submitted_at, d.confirmed_at, d.rejected_at, d.reason, "
                    "d.confirmation_payment_id, "
                    "o.status AS order_status, "
                    "p.receipt_number AS receipt_number "
                    "FROM payment_declarations d "
                    "LEFT JOIN orders o ON o.id = d.order_id "
                    "LEFT JOIN payments p ON p.id = d.confirmation_payment_id "
                    f"WHERE {where_sql} "
                    "ORDER BY d.submitted_at DESC, d.id DESC LIMIT :limit OFFSET :offset"
                ),
                page_params,
            )
        ).mappings().all()
        return list(rows), total

    async def list_by_wholesaler(
        self,
        db: AsyncSession,
        *,
        wholesaler_id: uuid.UUID,
        page: int,
        size: int,
        status: str | None = None,
        retailer_id: uuid.UUID | None = None,
    ) -> tuple[list[Mapping[str, Any]], int]:
        predicates = ["d.wholesaler_id = :wholesaler_id"]
        params: dict[str, Any] = {"wholesaler_id": wholesaler_id}
        if status is not None:
            predicates.append("d.status = :status")
            params["status"] = status
        if retailer_id is not None:
            predicates.append("d.retailer_id = :retailer_id")
            params["retailer_id"] = retailer_id
        where_sql = " AND ".join(predicates)

        total = int(
            (
                await db.execute(
                    text(f"SELECT COUNT(*) FROM payment_declarations d WHERE {where_sql}"),
                    params,
                )
            ).scalar()
            or 0
        )

        page_params = dict(params)
        page_params["limit"] = size
        page_params["offset"] = (page - 1) * size
        rows = (
            await db.execute(
                text(
                    "SELECT d.id, d.order_id, d.retailer_id, d.wholesaler_id, "
                    "d.declared_amount, d.method, d.transfer_reference, d.status, "
                    "d.submitted_at, d.confirmed_at, d.rejected_at, d.reason, "
                    "d.confirmation_payment_id, "
                    "o.status AS order_status, "
                    "p.receipt_number AS receipt_number "
                    "FROM payment_declarations d "
                    "LEFT JOIN orders o ON o.id = d.order_id "
                    "LEFT JOIN payments p ON p.id = d.confirmation_payment_id "
                    f"WHERE {where_sql} "
                    "ORDER BY d.submitted_at DESC, d.id DESC LIMIT :limit OFFSET :offset"
                ),
                page_params,
            )
        ).mappings().all()
        return list(rows), total

    async def list_statement_lines(
        self,
        db: AsyncSession,
        *,
        retailer_id: uuid.UUID,
        wholesaler_id: uuid.UUID,
        page: int,
        size: int,
    ) -> tuple[list[Mapping[str, Any]], int]:
        """Retailer statement line items: confirmed canonical payments.

        Each line is a real canonical payment (status='completed') for the
        retailer within the supplier relationship, with its receipt number. No
        opening/closing balance is computed.
        """
        predicates = [
            "p.retailer_id = :retailer_id",
            "o.wholesaler_id = :wholesaler_id",
            "p.is_deleted IS FALSE",
            "p.status = 'completed'",
        ]
        params: dict[str, Any] = {
            "retailer_id": retailer_id,
            "wholesaler_id": wholesaler_id,
        }
        where_sql = " AND ".join(predicates)

        total = int(
            (
                await db.execute(
                    text(
                        "SELECT COUNT(*) FROM payments p "
                        "JOIN orders o ON o.id = p.order_id "
                        f"WHERE {where_sql}"
                    ),
                    params,
                )
            ).scalar()
            or 0
        )

        page_params = dict(params)
        page_params["limit"] = size
        page_params["offset"] = (page - 1) * size
        rows = (
            await db.execute(
                text(
                    "SELECT p.created_at AS date, p.order_id, p.amount, p.method, "
                    "p.receipt_number, p.transaction_id "
                    "FROM payments p "
                    "JOIN orders o ON o.id = p.order_id "
                    f"WHERE {where_sql} "
                    "ORDER BY p.created_at DESC, p.id DESC LIMIT :limit OFFSET :offset"
                ),
                page_params,
            )
        ).mappings().all()
        return list(rows), total
