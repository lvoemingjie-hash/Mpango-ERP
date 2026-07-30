from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ClientFinanceRepository:
    """Read-only client finance projections scoped by supplier and retailer."""

    @staticmethod
    def _require_uuid(value: uuid.UUID, name: str) -> uuid.UUID:
        if not isinstance(value, uuid.UUID):
            raise TypeError(f"{name} must be a validated UUID")
        return value

    async def list_payments(
        self,
        db: AsyncSession,
        *,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
        page: int,
        size: int,
        order_id: uuid.UUID | None = None,
        method: str | None = None,
        status: str | None = None,
    ) -> tuple[list[Mapping[str, Any]], int]:
        self._require_uuid(wholesaler_id, "wholesaler_id")
        self._require_uuid(retailer_id, "retailer_id")
        if order_id is not None:
            self._require_uuid(order_id, "order_id")

        predicates = [
            "p.retailer_id = :retailer_id",
            "o.retailer_id = :retailer_id",
            "o.wholesaler_id = :wholesaler_id",
            "p.is_deleted IS FALSE",
            "o.is_deleted IS FALSE",
        ]
        params: dict[str, Any] = {
            "wholesaler_id": wholesaler_id,
            "retailer_id": retailer_id,
        }
        if order_id is not None:
            predicates.append("p.order_id = :order_id")
            params["order_id"] = order_id
        if method is not None:
            predicates.append("p.method = :method")
            params["method"] = method
        if status is not None:
            predicates.append("p.status = :status")
            params["status"] = status

        where_sql = " AND ".join(predicates)
        from_join_sql = "FROM payments p JOIN orders o ON o.id = p.order_id"

        total = int((await db.execute(
            text(f"SELECT COUNT(*) {from_join_sql} WHERE {where_sql}"),
            params,
        )).scalar() or 0)

        page_params = dict(params)
        page_params["limit"] = size
        page_params["offset"] = (page - 1) * size
        rows = (await db.execute(
            text(
                "SELECT p.id, p.order_id, p.amount, p.method, p.status, p.created_at "
                f"{from_join_sql} WHERE {where_sql} "
                "ORDER BY p.created_at DESC, p.id DESC LIMIT :limit OFFSET :offset"
            ),
            page_params,
        )).mappings().all()
        return list(rows), total

    async def get_balance(
        self,
        db: AsyncSession,
        *,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
    ) -> Mapping[str, Any] | None:
        self._require_uuid(wholesaler_id, "wholesaler_id")
        self._require_uuid(retailer_id, "retailer_id")
        row = (await db.execute(
            text(
                "SELECT outstanding_balance, updated_at "
                "FROM public.wholesaler_retailer_bindings "
                "WHERE wholesaler_id = :wholesaler_id "
                "AND retailer_id = :retailer_id "
                "AND status = 'active' "
                "AND is_deleted IS FALSE "
                "LIMIT 1"
            ),
            {"wholesaler_id": wholesaler_id, "retailer_id": retailer_id},
        )).mappings().first()
        if row is not None and Decimal(str(row["outstanding_balance"])) < 0:
            raise ValueError("negative outstanding balance")
        return row
