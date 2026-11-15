from __future__ import annotations

from datetime import datetime
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from repositories.payment_repository import TenantSchemaContextError
from schemas.common import DataResponse, Pagination
from schemas.payment import PaymentCreateRequest, PaymentResponse, PaymentData
from services.payment_service import PaymentService


router = APIRouter()


def _payment_row_to_data(row) -> PaymentData:
    return PaymentData(
        id=str(row["id"]),
        order_id=str(row["order_id"]),
        retailer_id=str(row["retailer_id"]),
        transaction_id=row.get("transaction_id"),
        amount=row["amount"],
        method=row["method"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _payment_list_item(row) -> dict:
    """List-GET projection: PaymentData plus the paying order's currency
    snapshot.  orders.currency_snapshot in the same validated tenant schema
    is the only currency authority; NULL/missing is reported explicitly as
    unverified, never defaulted from country/locale.  Detail GET and the
    retired POST keep the shared PaymentData contract untouched."""
    item = _payment_row_to_data(row).model_dump()
    snapshot = row.get("currency_snapshot")
    item["currency"] = snapshot
    item["currency_status"] = "KNOWN" if snapshot else "LEGACY_CURRENCY_UNVERIFIED"
    return item


@router.get("", response_model=DataResponse[dict], status_code=status.HTTP_200_OK)
async def list_payments(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    order_id: Optional[str] = Query(None, description="Filter by order ID"),
    method: Optional[str] = Query(None, description="Filter by payment method"),
    payment_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
    token: TokenPayload = Depends(RequirePermission("payments:read")),
    tenant_db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    List payments with pagination and optional filters.
    """
    # R4R1: the original service call chain is restored (API ->
    # PaymentService.list_payments -> PaymentRepository.list_paginated; no
    # service signature change).  The repository itself refuses a missing or
    # non-tenant schema from db.info BEFORE any payment query; only that
    # named context refusal is mapped to the existing 401 codes here —
    # database faults keep their own identity.
    service = PaymentService()
    try:
        rows, total = await service.list_payments(
            tenant_db=tenant_db, page=page, size=size,
            order_id=order_id, method=method, status=payment_status,
        )
    except TenantSchemaContextError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": exc.code, "message": str(exc)},
        )
    pages = ceil(total / size) if total > 0 else 0

    return DataResponse(
        success=True,
        data={
            "items": [_payment_list_item(r) for r in rows],
            "pagination": Pagination(page=page, size=size, total=total, pages=pages).model_dump(),
        },
        timestamp=datetime.utcnow(),
    )


@router.get("/{payment_id}", response_model=DataResponse[PaymentData], status_code=status.HTTP_200_OK)
async def get_payment(
    payment_id: str,
    token: TokenPayload = Depends(RequirePermission("payments:read")),
    tenant_db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Get a single payment by ID.
    """
    service = PaymentService()
    row = await service.get_payment_by_id(tenant_db=tenant_db, payment_id=payment_id)
    return DataResponse(
        success=True,
        data=_payment_row_to_data(row),
        timestamp=datetime.utcnow(),
    )


@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(
    request_body: PaymentCreateRequest,
    token: TokenPayload = Depends(RequirePermission("payments:create")),
    tenant_db: AsyncSession = Depends(get_tenant_db_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
):
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "PAYMENT_WRITE_PATH_DISABLED",
            "message": "Use POST /api/v1/orders/{order_id}/pay so order status and ledger stay consistent.",
        },
    )
