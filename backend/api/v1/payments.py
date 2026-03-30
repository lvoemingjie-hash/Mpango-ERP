from __future__ import annotations

from datetime import datetime
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
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
    service = PaymentService()
    rows, total = await service.list_payments(
        tenant_db=tenant_db, page=page, size=size,
        order_id=order_id, method=method, status=payment_status,
    )
    pages = ceil(total / size) if total > 0 else 0

    return DataResponse(
        success=True,
        data={
            "items": [_payment_row_to_data(r) for r in rows],
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
    effective_idempotency_key = None
    if request_body.method.value == "transfer":
        if not x_idempotency_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "MISSING_IDEMPOTENCY_KEY", "message": "X-Idempotency-Key required for transfer"},
            )

        effective_idempotency_key = x_idempotency_key

    service = PaymentService()

    payment = await service.create_payment(
        tenant_db=tenant_db,
        order_id=request_body.order_id,
        amount=request_body.amount,
        method=request_body.method.value,
        transaction_id=request_body.transaction_id,
        idempotency_key=effective_idempotency_key,
        created_by=token.user_id,
    )

    return PaymentResponse(
        success=True,
        data=_payment_row_to_data(payment),
        message="Payment created",
        timestamp=datetime.utcnow(),
    )
