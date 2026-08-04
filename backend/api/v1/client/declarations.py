"""Client (retailer) payment declaration views (DC-12R1-S3-S2B-I2B).

Read-only retailer views scoped to the authenticated retailer + active binding.
Identity is resolved server-side via ``resolve_client_identity``; no
client-supplied retailer/wholesaler ids are accepted.
"""
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
from api.v1.client.orders import _declaration_to_client_view
from core.security import TokenPayload
from repositories.payment_declaration_repository import PaymentDeclarationRepository
from schemas.common import DataResponse, Pagination
from schemas.declaration import ClientDeclarationView  # noqa: F401  (re-export parity)


router = APIRouter()

_ALLOWED_STATUSES = {"pending", "confirmed", "rejected"}


@router.get("", response_model=DataResponse[dict], status_code=status.HTTP_200_OK)
async def list_client_declarations(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    declaration_status: Optional[str] = Query(None, alias="status"),
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:payments:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    retailer_id = uuid.UUID(client.retailer_id)
    wholesaler_id = uuid.UUID(client.tenant_id)
    status_filter = declaration_status.lower() if declaration_status else None
    if status_filter is not None and status_filter not in _ALLOWED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_DECLARATION_STATUS", "message": "Invalid status filter"},
        )

    rows, total = await PaymentDeclarationRepository().list_by_retailer(
        db,
        retailer_id=retailer_id,
        wholesaler_id=wholesaler_id,
        page=page,
        size=size,
        status=status_filter,
    )
    pages = ceil(total / size) if total > 0 else 0
    return DataResponse(
        success=True,
        data={
            "items": [_declaration_to_client_view(r).model_dump() for r in rows],
            "pagination": Pagination(page=page, size=size, total=total, pages=pages).model_dump(),
        },
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/{declaration_id}", response_model=DataResponse[dict], status_code=status.HTTP_200_OK)
async def get_client_declaration(
    declaration_id: str,
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:payments:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    try:
        did = uuid.UUID(declaration_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DECLARATION_NOT_FOUND", "message": "Declaration not found"},
        )

    row = await PaymentDeclarationRepository().get_detail_by_retailer(
        db,
        declaration_id=did,
        retailer_id=uuid.UUID(client.retailer_id),
        wholesaler_id=uuid.UUID(client.tenant_id),
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DECLARATION_NOT_FOUND", "message": "Declaration not found"},
        )
    return DataResponse(
        success=True,
        data=_declaration_to_client_view(row).model_dump(),
        timestamp=datetime.now(timezone.utc),
    )
