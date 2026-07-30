from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from api.v1.client.dependencies import ClientIdentity, resolve_client_identity
from core.security import TokenPayload
from repositories.client_finance_repository import ClientFinanceRepository
from schemas.client import ClientFinanceBalanceView
from schemas.common import DataResponse


router = APIRouter()


def _parse_context_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_CLIENT_CONTEXT", "message": "Invalid client context"},
        )


@router.get("/balance", response_model=DataResponse[ClientFinanceBalanceView], status_code=status.HTTP_200_OK)
async def get_client_finance_balance(
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:finance:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    wholesaler_uuid = _parse_context_uuid(client.tenant_id)
    retailer_uuid = _parse_context_uuid(client.retailer_id)
    try:
        row = await ClientFinanceRepository().get_balance(
            db,
            wholesaler_id=wholesaler_uuid,
            retailer_id=retailer_uuid,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "FINANCIAL_INTEGRITY_ERROR", "message": "Financial balance is unavailable"},
        )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "BINDING_NOT_ACTIVE", "message": "No active relationship with this supplier"},
        )
    outstanding_balance = row["outstanding_balance"]
    return DataResponse(
        success=True,
        data=ClientFinanceBalanceView(
            outstanding_balance=outstanding_balance,
            has_outstanding_balance=outstanding_balance != 0,
            updated_at=row["updated_at"],
        ),
        timestamp=datetime.utcnow(),
    )
