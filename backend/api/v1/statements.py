"""Wholesaler (supplier) statement routes (DC-12R1-S3-S2B-I2C-I2B Contract D).

Read-only printable relationship account statement for a target retailer within
the active supplier (token tenant) relationship. ``retailer_id`` is only a target
selector; the active binding under the token tenant remains the authority.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from api.v1.statement_http import map_statement_result
from core.security import TokenPayload
from repositories.statement_repository import (
    StatementPeriodError,
    parse_statement_date_range,
)
from schemas.common import DataResponse
from schemas.print import StatementPrintView
from services.print_service import build_statement_print


router = APIRouter()


def _tenant_wholesaler_id(token: TokenPayload) -> uuid.UUID:
    if not token.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "PERMISSION_DENIED", "message": "Tenant context required"},
        )
    try:
        return uuid.UUID(token.tenant_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "PERMISSION_DENIED", "message": "Tenant context required"},
        )


async def _supplier_binding_active(db: AsyncSession, ws_uuid: uuid.UUID, rt_uuid: uuid.UUID) -> bool:
    """True iff the relationship binding is active and non-deleted."""
    row = (
        await db.execute(
            text(
                "SELECT status FROM public.wholesaler_retailer_bindings "
                "WHERE wholesaler_id = :wid AND retailer_id = :rid "
                "AND is_deleted IS FALSE LIMIT 1"
            ),
            {"wid": ws_uuid, "rid": rt_uuid},
        )
    ).first()
    return row is not None and row.status == "active"


@router.get(
    "/print",
    response_model=DataResponse[StatementPrintView],
    status_code=status.HTTP_200_OK,
)
async def print_supplier_statement(
    retailer_id: str = Query(..., description="Target retailer id (selector only)"),
    from_raw: Optional[str] = Query(None, alias="from", description="Inclusive period start (EAT day, YYYY-MM-DD)"),
    to_raw: Optional[str] = Query(None, alias="to", description="Inclusive period end (EAT day, YYYY-MM-DD)"),
    include_pending: bool = Query(False, description="Include non-accounting pending/rejected declarations"),
    token: TokenPayload = Depends(RequirePermission("finance:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """Printable relationship account statement (Contract D, supplier side).

    ``retailer_id`` is only a target selector; the active binding under the token
    tenant remains the authority. Zero database mutations. Integrity failures
    surface precise 409s; date-range failures surface a controlled 400 via the
    shared strict parser (R1 rule 3).
    """
    wholesaler_id = _tenant_wholesaler_id(token)
    # Shared strict date-range parser (R1 rule 3) — identical on both routes.
    try:
        date_from, date_to = parse_statement_date_range(from_raw, to_raw)
    except StatementPeriodError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_DATE_RANGE", "message": "Invalid date range."},
        )
    # Validate + scope the retailer selector. A malformed UUID or a retailer not
    # bound to this supplier yields a neutral 404 (no existence disclosure).
    try:
        rt_uuid = uuid.UUID(retailer_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "STATEMENT_NOT_AVAILABLE", "message": "Statement not available"},
        )
    if not await _supplier_binding_active(db, wholesaler_id, rt_uuid):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "STATEMENT_NOT_AVAILABLE", "message": "Statement not available"},
        )

    res = await build_statement_print(
        db,
        schema=token.tenant_schema or "",
        wholesaler_id=wholesaler_id,
        retailer_id=rt_uuid,
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
