from __future__ import annotations

import uuid
from datetime import datetime, timezone
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from api.v1.client.dependencies import ClientIdentity, resolve_client_identity
from core.security import TokenPayload
from repositories.client_finance_repository import ClientFinanceRepository
from schemas.client import ClientPaymentView
from schemas.common import DataResponse, Pagination


router = APIRouter()

_ALLOWED_METHODS = {"cash", "transfer", "credit"}
_ALLOWED_STATUSES = {"pending", "completed"}


def _parse_uuid(value: str, code: str, message: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": code, "message": message})


def _normalize_filter(value: str | None, code: str, message: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": code, "message": message})
    return normalized


@router.get("", response_model=DataResponse[dict], status_code=status.HTTP_200_OK)
async def list_client_payments(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    order_id: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    payment_status: Optional[str] = Query(None, alias="status"),
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:payments:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    wholesaler_uuid = _parse_uuid(client.tenant_id, "INVALID_CLIENT_CONTEXT", "Invalid client context")
    retailer_uuid = _parse_uuid(client.retailer_id, "INVALID_CLIENT_CONTEXT", "Invalid client context")
    order_filter = _normalize_filter(order_id, "INVALID_ORDER_ID", "Invalid order_id format")
    method_filter = _normalize_filter(method, "INVALID_PAYMENT_METHOD", "Invalid payment method filter")
    status_filter = _normalize_filter(payment_status, "INVALID_PAYMENT_STATUS", "Invalid payment status filter")
    order_uuid = _parse_uuid(order_filter, "INVALID_ORDER_ID", "Invalid order_id format") if order_filter else None
    method_filter = method_filter.lower() if method_filter else None
    status_filter = status_filter.lower() if status_filter else None
    if method_filter is not None and method_filter not in _ALLOWED_METHODS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_PAYMENT_METHOD", "message": "Invalid payment method filter"},
        )
    if status_filter is not None and status_filter not in _ALLOWED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_PAYMENT_STATUS", "message": "Invalid payment status filter"},
        )

    rows, total = await ClientFinanceRepository().list_payments(
        db,
        wholesaler_id=wholesaler_uuid,
        retailer_id=retailer_uuid,
        page=page,
        size=size,
        order_id=order_uuid,
        method=method_filter,
        status=status_filter,
    )
    pages = ceil(total / size) if total > 0 else 0
    return DataResponse(
        success=True,
        data={
            "items": [ClientPaymentView(id=str(row["id"]), order_id=str(row["order_id"]), amount=row["amount"], method=row["method"], status=row["status"], created_at=row["created_at"]).model_dump() for row in rows],
            "pagination": Pagination(page=page, size=size, total=total, pages=pages).model_dump(),
        },
        timestamp=datetime.now(timezone.utc),
    )
