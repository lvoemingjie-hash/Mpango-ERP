from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
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


@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(
    request_body: PaymentCreateRequest,
    token: TokenPayload = Depends(RequirePermission("payments:create")),
    tenant_db: AsyncSession = Depends(get_tenant_db_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
):
    if request_body.method.value == "transfer":
        if not (idempotency_key or x_idempotency_key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "MISSING_IDEMPOTENCY_KEY", "message": "Idempotency-Key required for transfer"},
            )

    service = PaymentService()

    payment = await service.create_payment(
        tenant_db=tenant_db,
        order_id=request_body.order_id,
        amount=request_body.amount,
        method=request_body.method.value,
        transaction_id=request_body.transaction_id,
        created_by=token.user_id,
    )

    return PaymentResponse(
        success=True,
        data=_payment_row_to_data(payment),
        message="Payment created",
        timestamp=datetime.utcnow(),
    )
