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
from datetime import datetime
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, Query, status
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


# ── Helpers ────────────────────────────────────────────────────────────────

def _csv_row(row: list) -> str:
    """Serialise a single CSV row to string (including newline)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(row)
    return buf.getvalue()


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
):
    """
    Stream all orders as a CSV download.

    Uses batched DB fetches + generator to keep memory constant regardless
    of dataset size.

    Columns: Order ID, Status, Total Amount (KES), Retailer ID,
             Notes, Item Count, Created At, Updated At

    Permission: exports:create
    """
    if format != "csv":
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNSUPPORTED_FORMAT",
                "message": f"Format '{format}' is not supported. Use 'csv'.",
            },
        )

    async def _generate() -> AsyncGenerator[str, None]:
        # Header row
        yield _csv_row([
            "Order ID",
            "Status",
            "Total Amount (KES)",
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
                .options(selectinload(Order.items))
                .order_by(Order.created_at.desc())
                .offset(offset)
                .limit(_BATCH_SIZE)
            )
            if status_filter:
                try:
                    enum_val = OrderStatus(status_filter)
                    stmt = stmt.where(Order.status == enum_val)
                except ValueError:
                    pass  # ignore invalid filter; return all

            result = await db.execute(stmt)
            rows = result.scalars().all()

            if not rows:
                break

            for order in rows:
                yield _csv_row([
                    str(order.id),
                    order.status.value,
                    f"{order.total_amount:.2f}",
                    str(order.retailer_id) if order.retailer_id else "",
                    (order.notes or "").replace("\n", " "),
                    str(len(order.items)),
                    order.created_at.isoformat() if order.created_at else "",
                    order.updated_at.isoformat() if order.updated_at else "",
                ])

            offset += _BATCH_SIZE

            # If we got fewer rows than the batch size, we're done
            if len(rows) < _BATCH_SIZE:
                break

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"orders_export_{timestamp}.csv"

    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
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
):
    """
    Stream all inventory stock records as a CSV download.

    Joins InventoryStock → SKU to include product metadata.

    Columns: Stock ID, SKU Code, SKU Name, Category, Unit,
             Quantity On Hand, Quantity Reserved, Available,
             Is Active, Last Updated

    Permission: exports:create
    """
    if format != "csv":
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNSUPPORTED_FORMAT",
                "message": f"Format '{format}' is not supported. Use 'csv'.",
            },
        )

    async def _generate() -> AsyncGenerator[str, None]:
        # Header row
        yield _csv_row([
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
                .order_by(InventoryStock.created_at.desc())
                .offset(offset)
                .limit(_BATCH_SIZE)
            )
            result = await db.execute(stmt)
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
                    f"{stock.quantity_on_hand:.2f}",
                    f"{stock.quantity_reserved:.2f}",
                    f"{available:.2f}",
                    str(sku.is_active) if sku else "",
                    stock.updated_at.isoformat() if stock.updated_at else "",
                ])

            offset += _BATCH_SIZE

            if len(rows) < _BATCH_SIZE:
                break

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"inventory_export_{timestamp}.csv"

    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )
