"""
Phase P-B: Streaming CSV Data Export Endpoints.

Provides synchronous streaming downloads (unlike the async job-based exports
in exports.py which use the S4 job queue for heavy reports).

Architecture:
    GET /api/v1/orders/export?format=csv     → Stream orders as CSV
    GET /api/v1/inventory/export?format=csv   → Stream inventory as CSV

Performance:
    Uses Python generators + StreamingResponse to avoid loading all rows
    into memory.  Each batch of rows is fetched, serialised, and yielded
    to the HTTP client.

Permission: exports:create (defined in Phase P-A Security Hardening).
Tenant isolation: enforced via get_tenant_db_session (JWT-derived search_path).
"""
from __future__ import annotations

import csv
import io
import re
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import AsyncGenerator, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from models.order import Order, OrderItem, OrderStatus
from models.inventory_stock import InventoryStock
from models.sku import SKU

router = APIRouter()

# ── Constants ──────────────────────────────────────────────────────────────
_BATCH_SIZE = 500  # rows per DB round-trip
_FORMULA_PREFIX = re.compile(r"^[\s\ufeff\x00-\x1f]*[=+\-@]")


# ── Helpers ────────────────────────────────────────────────────────────────

def _csv_row(row: list) -> str:
    """Quote CSV normally and neutralize spreadsheet formulas in text cells."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "'" + value
        if isinstance(value, str)
        and (_FORMULA_PREFIX.match(value) or value.startswith(("\t", "\r", "\n")))
        else value
        for value in row
    ])
    return buf.getvalue()


def _validate_export_query(request: Request | None, allowed: set[str]) -> None:
    """Never silently broaden an export by ignoring unsupported filters."""
    if request is None:  # Compatibility for internal direct-call lifecycle tests.
        return
    keys = list(request.query_params.keys())
    if any(key not in allowed or len(request.query_params.getlist(key)) != 1 for key in keys):
        raise HTTPException(status_code=400, detail={
            "code": "INVALID_EXPORT_FILTER",
            "message": "An export filter is unsupported or repeated.",
        })


# ============================================================================
# GET /orders/export?format=csv
# ============================================================================

@router.get(
    "/orders/export",
    status_code=status.HTTP_200_OK,
    summary="Export orders as CSV (streaming)",
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "Streamed CSV file containing order data.",
        }
    },
)
async def export_orders_csv(
    format: str = Query("csv", description="Export format (only csv supported)"),
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Optional status filter (e.g. 'confirmed')",
    ),
    token: TokenPayload = Depends(RequirePermission("exports:create")),
    db: AsyncSession = Depends(get_tenant_db_session),
    request: Request = None,
):
    """
    Stream all orders as a CSV download.

    Uses batched DB fetches + generator to keep memory constant regardless
    of dataset size.

    Columns: Order ID, Status, Total Amount, Currency, Retailer ID,
             Notes, Item Count, Created At, Updated At

    Permission: exports:create
    """
    _validate_export_query(request, {"format", "status"})
    if format != "csv":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNSUPPORTED_FORMAT",
                "message": f"Format '{format}' is not supported. Use 'csv'.",
            },
        )

    order_status = None
    if status_filter is not None:
        try:
            order_status = OrderStatus(status_filter)
        except ValueError:
            raise HTTPException(status_code=400, detail={
                "code": "INVALID_STATUS_FILTER",
                "message": "The order status filter is invalid.",
            }) from None

    async def _generate_rows(export_db: AsyncSession) -> AsyncGenerator[str, None]:
        # Header row
        yield "\ufeff" + _csv_row([
            "Order ID",
            "Status",
            "Total Amount",
            "Currency",
            "Retailer ID",
            "Notes",
            "Item Count",
            "Created At",
            "Updated At",
        ])

        offset = 0
        while True:
            stmt = (
                select(Order)
                .where(Order.is_deleted.is_(False))
                .where(Order.wholesaler_id == UUID(token.tenant_id))
                .options(selectinload(Order.items))
                .order_by(Order.created_at.desc(), Order.id)
                .offset(offset)
                .limit(_BATCH_SIZE)
            )
            if order_status is not None:
                stmt = stmt.where(Order.status == order_status)

            result = await export_db.execute(stmt)
            rows = result.scalars().all()

            if not rows:
                break

            for order in rows:
                yield _csv_row([
                    str(order.id),
                    order.status.value,
                    Decimal(f"{order.total_amount:f}"),
                    order.currency_snapshot or 'LEGACY_CURRENCY_UNVERIFIED',
                    str(order.retailer_id) if order.retailer_id else "",
                    (order.notes or "").replace("\n", " "),
                    len(order.items),
                    order.created_at.isoformat() if order.created_at else "",
                    order.updated_at.isoformat() if order.updated_at else "",
                ])

            offset += _BATCH_SIZE

            # If we got fewer rows than the batch size, we're done
            if len(rows) < _BATCH_SIZE:
                break

    async def _generate() -> AsyncGenerator[str, None]:
        # Response streaming outlives the request transaction. Never race its
        # middleware commit/close using the same connection for batch reads.
        import sys
        import anyio
        from database.session import get_tenant_db
        from db.tenant_filter import set_current_tenant, reset_current_tenant
        scope = set_current_tenant(tenant_id=token.tenant_id, tenant_schema=token.tenant_schema)
        manager = asynccontextmanager(get_tenant_db)(token.tenant_schema)
        try:
            export_db = await manager.__aenter__()
            try:
                async for chunk in _generate_rows(export_db):
                    yield chunk
            except BaseException:
                # Preserve cancellation, but finish rollback/reset/close first.
                with anyio.CancelScope(shield=True):
                    await manager.__aexit__(*sys.exc_info())
                raise
            else:
                with anyio.CancelScope(shield=True):
                    await manager.__aexit__(None, None, None)
        finally:
            reset_current_tenant(*scope)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"orders_export_{timestamp}.csv"

    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ============================================================================
# GET /inventory/export?format=csv
# ============================================================================

@router.get(
    "/inventory/export",
    status_code=status.HTTP_200_OK,
    summary="Export inventory stock as CSV (streaming)",
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "Streamed CSV file containing inventory data.",
        }
    },
)
async def export_inventory_csv(
    format: str = Query("csv", description="Export format (only csv supported)"),
    token: TokenPayload = Depends(RequirePermission("exports:create")),
    db: AsyncSession = Depends(get_tenant_db_session),
    request: Request = None,
):
    """
    Stream all inventory stock records as a CSV download.

    Joins InventoryStock → SKU to include product metadata.

    Columns: Stock ID, SKU Code, SKU Name, Category, Unit,
             Quantity On Hand, Quantity Reserved, Available,
             Is Active, Last Updated

    Permission: exports:create
    """
    _validate_export_query(request, {"format"})
    if format != "csv":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNSUPPORTED_FORMAT",
                "message": f"Format '{format}' is not supported. Use 'csv'.",
            },
        )

    async def _generate_rows(export_db: AsyncSession) -> AsyncGenerator[str, None]:
        # Header row
        yield "\ufeff" + _csv_row([
            "Stock ID",
            "SKU Code",
            "SKU Name",
            "Category",
            "Unit",
            "Quantity On Hand",
            "Quantity Reserved",
            "Available",
            "Is Active",
            "Last Updated",
        ])

        offset = 0
        while True:
            stmt = (
                select(InventoryStock)
                .where(InventoryStock.is_deleted.is_(False))
                .options(selectinload(InventoryStock.sku))
                .order_by(InventoryStock.created_at.desc(), InventoryStock.id)
                .offset(offset)
                .limit(_BATCH_SIZE)
            )
            result = await export_db.execute(stmt)
            rows = result.scalars().all()

            if not rows:
                break

            for stock in rows:
                sku = stock.sku
                available = stock.quantity_on_hand - stock.quantity_reserved
                yield _csv_row([
                    str(stock.id),
                    sku.sku_code if sku else "",
                    sku.name if sku else "",
                    sku.category or "" if sku else "",
                    sku.unit if sku else "",
                    Decimal(f"{stock.quantity_on_hand:.2f}"),
                    Decimal(f"{stock.quantity_reserved:.2f}"),
                    Decimal(f"{available:.2f}"),
                    str(sku.is_active) if sku else "",
                    stock.updated_at.isoformat() if stock.updated_at else "",
                ])

            offset += _BATCH_SIZE

            if len(rows) < _BATCH_SIZE:
                break

    async def _generate() -> AsyncGenerator[str, None]:
        import sys
        import anyio
        from database.session import get_tenant_db
        from db.tenant_filter import set_current_tenant, reset_current_tenant

        scope = set_current_tenant(tenant_id=token.tenant_id, tenant_schema=token.tenant_schema)
        manager = asynccontextmanager(get_tenant_db)(token.tenant_schema)
        try:
            export_db = await manager.__aenter__()
            try:
                async for chunk in _generate_rows(export_db):
                    yield chunk
            except BaseException:
                # A disconnect must not cancel rollback/search-path reset/close.
                with anyio.CancelScope(shield=True):
                    await manager.__aexit__(*sys.exc_info())
                raise
            else:
                with anyio.CancelScope(shield=True):
                    await manager.__aexit__(None, None, None)
        finally:
            reset_current_tenant(*scope)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"inventory_export_{timestamp}.csv"

    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
