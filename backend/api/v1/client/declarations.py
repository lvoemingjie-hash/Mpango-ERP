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
from crud.order import get_order_for_retailer
from repositories.payment_declaration_repository import PaymentDeclarationRepository
from repositories.payment_repository import PaymentRepository
from schemas.common import DataResponse, Pagination
from schemas.declaration import ClientDeclarationView  # noqa: F401  (re-export parity)
from schemas.print import DeclarationPrintView, ReceiptPrintView
from services.print_service import (
    build_declaration_print,
    build_receipt_print,
    check_receipt_eligibility,
)


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


# ---------------------------------------------------------------------------
# GET /client/declarations/{declaration_id}/print — Contract B (retailer side)
# ---------------------------------------------------------------------------

@router.get(
    "/{declaration_id}/print",
    response_model=DataResponse[DeclarationPrintView],
    status_code=status.HTTP_200_OK,
)
async def print_client_declaration(
    declaration_id: str,
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:payments:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """Printable payment declaration document (retailer side).

    Pending/rejected are explicitly marked NOT A RECEIPT. Confirmed exposes
    receipt content only when the receipt eligibility predicate passes.
    Triple-key scoped; wrong retailer/supplier -> neutral 404. Read-only.
    """
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
    view = await build_declaration_print(
        db,
        row=row,
        wholesaler_id=uuid.UUID(client.tenant_id),
        retailer_id=uuid.UUID(client.retailer_id),
    )
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DECLARATION_NOT_FOUND", "message": "Declaration not found"},
        )
    return DataResponse(
        success=True,
        data=view,
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# GET /client/declarations/{declaration_id}/receipt — Contract C (retailer side)
# ---------------------------------------------------------------------------

@router.get(
    "/{declaration_id}/receipt",
    response_model=DataResponse[ReceiptPrintView],
    status_code=status.HTTP_200_OK,
)
async def get_client_receipt(
    declaration_id: str,
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:payments:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """Confirmed receipt (retailer side). Receipt-eligible only; fail-closed 404.

    Never allocates or repairs a receipt. Replayed GET returns the same
    receipt identity. Any eligibility failure -> neutral 404
    RECEIPT_NOT_AVAILABLE.
    """
    try:
        did = uuid.UUID(declaration_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RECEIPT_NOT_AVAILABLE", "message": "Receipt not available"},
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
            detail={"code": "RECEIPT_NOT_AVAILABLE", "message": "Receipt not available"},
        )
    eligible = await check_receipt_eligibility(
        db, row=row, wholesaler_id=uuid.UUID(client.tenant_id)
    )
    if not eligible:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RECEIPT_NOT_AVAILABLE", "message": "Receipt not available"},
        )
    # Load the canonical payment (with receipt_number) and the order for totals.
    cpid = row.get("confirmation_payment_id")
    payment = await PaymentRepository().get_by_id_with_receipt(
        db, payment_id=uuid.UUID(str(cpid))
    )
    order = await get_order_for_retailer(
        db,
        order_id=str(row["order_id"]),
        wholesaler_id=client.tenant_id,
        retailer_id=client.retailer_id,
    )
    view = await build_receipt_print(
        db, row=row, payment=payment, order=order,
        wholesaler_id=uuid.UUID(client.tenant_id),
    )
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RECEIPT_NOT_AVAILABLE", "message": "Receipt not available"},
        )
    return DataResponse(
        success=True,
        data=view,
        timestamp=datetime.now(timezone.utc),
    )
