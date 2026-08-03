"""Client (retailer) statement (DC-12R1-S3-S2B-I2B).

Line-item statement of confirmed canonical payments for the authenticated
retailer within the active supplier relationship. No opening/closing balance is
computed (deferred per contract DD-06). Each line carries the receipt number
sourced from ``payments.receipt_number``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from math import ceil

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from api.v1.client.dependencies import ClientIdentity, resolve_client_identity
from core.security import TokenPayload
from repositories.payment_declaration_repository import PaymentDeclarationRepository
from schemas.common import DataResponse, Pagination


router = APIRouter()


@router.get("", response_model=DataResponse[dict], status_code=status.HTTP_200_OK)
async def get_client_statement(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:payments:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    rows, total = await PaymentDeclarationRepository().list_statement_lines(
        db,
        retailer_id=uuid.UUID(client.retailer_id),
        wholesaler_id=uuid.UUID(client.tenant_id),
        page=page,
        size=size,
    )
    pages = ceil(total / size) if total > 0 else 0
    items = [
        {
            "date": r["date"],
            "order_id": str(r["order_id"]),
            "amount": str(r["amount"]),
            "method": r["method"],
            "receipt_number": r.get("receipt_number"),
            "description": ("Transfer" if r["method"] == "transfer" else "Cash")
            + " payment received"
            + (f" - ref {r['transaction_id']}" if r.get("transaction_id") else ""),
        }
        for r in rows
    ]
    return DataResponse(
        success=True,
        data={
            "items": items,
            "pagination": Pagination(page=page, size=size, total=total, pages=pages).model_dump(),
        },
        timestamp=datetime.now(timezone.utc),
    )
