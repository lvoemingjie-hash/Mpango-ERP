"""Client (retailer) statement (DC-12R1-S3-S2B-I2B + I2C-I2B Contract D).

Line-item statement of confirmed canonical payments for the authenticated
retailer within the active supplier relationship. No opening/closing balance is
computed on the line-item route (Contract DD-06). Each line carries the receipt
number sourced from ``payments.receipt_number``.

Contract D (I2C-I2B) adds the printable relationship account statement
(``GET /print``): a ledger-derived, read-only document with opening/closing
balances, receivable movements, and an independent settled-payments list.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from api.v1.client.dependencies import ClientIdentity, resolve_client_identity
from api.v1.statement_http import map_statement_result
from core.security import TokenPayload
from repositories.payment_declaration_repository import PaymentDeclarationRepository
from repositories.statement_repository import (
    StatementPeriodError,
    parse_statement_date_range,
)
from schemas.common import DataResponse, Pagination
from schemas.print import StatementPrintView
from services.print_service import build_statement_print


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


# ---------------------------------------------------------------------------
# Contract D (I2C-I2B) — printable relationship account statement (retailer).
# GET /client/statements/print?from=YYYY-MM-DD&to=YYYY-MM-DD
# Permission: client:finance:read. Retailer identity is server-derived.
#
# WPR-004: the StatementResult → HTTP mapping is the shared
# ``api.v1.statement_http.map_statement_result`` (also used by the supplier
# route), so the retailer and supplier public contracts cannot drift apart.
# ---------------------------------------------------------------------------


@router.get(
    "/print",
    response_model=DataResponse[StatementPrintView],
    status_code=status.HTTP_200_OK,
)
async def print_client_statement(
    from_raw: Optional[str] = Query(None, alias="from", description="Inclusive period start (EAT day, YYYY-MM-DD)"),
    to_raw: Optional[str] = Query(None, alias="to", description="Inclusive period end (EAT day, YYYY-MM-DD)"),
    include_pending: bool = Query(False, description="Include non-accounting pending/rejected declarations"),
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:finance:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """Printable relationship account statement (Contract D, retailer side).

    Retailer identity is server-derived from the contextual JWT + active binding.
    Zero database mutations; the response carries ledger-derived balances and an
    independent settled-payments list. Integrity failures surface precise 409s.

    The date range is parsed by the shared strict parser shared with the
    supplier route (R1 rule 3): missing/blank/malformed/reversed/>365-day
    ranges return a controlled 400 INVALID_DATE_RANGE — never a framework 422
    or a neutral 404.
    """
    # Shared strict date-range parser (R1 rule 3) — identical on both routes.
    try:
        date_from, date_to = parse_statement_date_range(from_raw, to_raw)
    except StatementPeriodError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_DATE_RANGE", "message": "Invalid date range."},
        )

    res = await build_statement_print(
        db,
        schema=client.token.tenant_schema or "",
        wholesaler_id=uuid.UUID(client.tenant_id),
        retailer_id=uuid.UUID(client.retailer_id),
        date_from=date_from,
        date_to=date_to,
        include_pending=include_pending,
    )
    view = map_statement_result(res)
    return DataResponse(
        success=True,
        data=view,
        timestamp=datetime.now(timezone.utc),
    )
