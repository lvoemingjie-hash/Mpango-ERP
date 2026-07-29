"""Client Order API — Retailer-facing order management.

CTO P0 Security Mandates:
1. retailer_id = current_user.retailer_id (NEVER from request body)
2. Retailer can only VIEW their own orders (enforced server-side)
3. Retailer can CREATE orders and CANCEL (if draft/confirmed only)
4. Retailer cannot modify order status beyond cancel

Order State Machine (client-visible):
    CREATED → CONFIRMED → DELIVERED
               ↓
            CANCELLED

Internal mapping:
    draft        → CREATED
    confirmed    → CONFIRMED
    paid         → CONFIRMED  (payment detail hidden from client)
    fulfilled    → DELIVERED
    cancelled    → CANCELLED
    voided       → CANCELLED
    returned     → RETURNED
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from api.v1.client.dependencies import ClientIdentity, resolve_client_identity
from core.security import TokenPayload
from crud.order import (
    create_order as crud_create_order,
    get_order_for_retailer,
    get_orders_paginated,
    cancel_order as crud_cancel_order,
)
from schemas.client import (
    ClientCreateOrderRequest,
    ClientOrderView,
    ClientOrderItemView,
    map_order_status_for_client,
)
from schemas.common import DataResponse, Pagination


router = APIRouter()


# ---------------------------------------------------------------------------
# Helper: Convert Order ORM → ClientOrderView
# ---------------------------------------------------------------------------

def _order_to_client_view(order) -> ClientOrderView:
    """Convert internal Order model to client-safe view model."""
    items = [
        ClientOrderItemView(
            product_name=item.product_name,
            sku_code=item.sku_code,
            quantity=item.quantity,
            unit_price=item.unit_price,
            subtotal=item.subtotal,
        )
        for item in (order.items or [])
    ]

    return ClientOrderView(
        id=str(order.id),
        status=map_order_status_for_client(order.status.value),
        total_amount=order.total_amount,
        item_count=len(items),
        notes=order.notes,
        items=items,
        created_at=order.created_at,
    )


# ---------------------------------------------------------------------------
# POST /client/orders — Create order (retailer_id from JWT, NOT request)
# ---------------------------------------------------------------------------

@router.post("", response_model=DataResponse[ClientOrderView], status_code=status.HTTP_201_CREATED)
async def create_order(
    request: ClientCreateOrderRequest,
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:orders:create")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Create an order on behalf of the authenticated retailer.

    Security: retailer_id is derived from the authenticated user's
    server-side identity resolution. It is NEVER accepted from the
    request body. Any attempt to inject a foreign retailer_id is
    structurally impossible.

    DC-12R1-S3-S1: requires the ``client:orders:create`` permission. MVP
    create authority also covers cancellation of the retailer's own
    DRAFT/CONFIRMED order (no separate cancel permission in this slice).
    """
    # Validate all SKUs exist, are active, and have stock
    sku_codes = [item.sku_code for item in request.items]
    placeholders = ", ".join([f":sku_{i}" for i in range(len(sku_codes))])
    sku_params = {f"sku_{i}": code for i, code in enumerate(sku_codes)}

    sku_sql = f"""
        SELECT
            s.id AS sku_id,
            s.sku_code,
            s.name,
            s.is_active,
            COALESCE(i.quantity_on_hand, 0) AS quantity_on_hand,
            rp.price AS sell_price
        FROM skus s
        LEFT JOIN inventory_stocks i ON i.sku_id = s.id AND i.is_deleted IS NOT TRUE
        LEFT JOIN retailer_prices rp
            ON rp.sku_id = s.id
            AND rp.retailer_id = :retailer_id
            AND rp.is_deleted IS NOT TRUE
        WHERE s.sku_code IN ({placeholders})
          AND s.is_deleted IS NOT TRUE
    """
    sku_params["retailer_id"] = client.retailer_id
    result = await db.execute(text(sku_sql), sku_params)
    sku_rows = {row.sku_code: row for row in result.fetchall()}

    # Validate each requested item and resolve server-side pricing
    errors = []
    order_items = []
    for item in request.items:
        sku_row = sku_rows.get(item.sku_code)
        if sku_row is None:
            errors.append(f"Product '{item.sku_code}' not found")
            continue
        if not sku_row.is_active:
            errors.append(f"Product '{item.sku_code}' is no longer available")
            continue
        qty_available = float(sku_row.quantity_on_hand)
        if qty_available < item.quantity:
            errors.append(
                f"Insufficient stock for '{item.sku_code}': "
                f"requested {item.quantity}, available {int(qty_available)}"
            )
            continue

        # P0: Price is resolved server-side from retailer_prices, NEVER from client
        if sku_row.sell_price is None:
            errors.append(
                f"No price configured for '{item.sku_code}'. "
                f"Please contact your supplier."
            )
            continue

        resolved_price = Decimal(str(sku_row.sell_price))

        if resolved_price <= 0:
            errors.append(
                f"Invalid price for '{item.sku_code}'. "
                f"Please contact your supplier."
            )
            continue

        order_items.append({
            "product_name": sku_row.name,
            "sku_code": item.sku_code,
            "quantity": item.quantity,
            "unit_price": resolved_price,
        })

    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "ORDER_VALIDATION_FAILED",
                "message": "Some items cannot be ordered",
                "errors": errors,
            },
        )

    # Create order — retailer_id is from server-side resolution
    order = await crud_create_order(
        db=db,
        wholesaler_id=client.tenant_id,
        retailer_id=client.retailer_id,  # P0: NEVER from request
        items=order_items,
        notes=request.notes,
        created_by=client.user_id,
    )

    return DataResponse(
        success=True,
        data=_order_to_client_view(order),
        message="Order submitted successfully",
        timestamp=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# GET /client/orders — List retailer's own orders only
# ---------------------------------------------------------------------------

@router.get("", response_model=DataResponse[dict], status_code=status.HTTP_200_OK)
async def list_orders(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    order_status: Optional[str] = Query(None, alias="status", description="Filter by client status"),
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:orders:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    List orders belonging to the authenticated retailer only.

    Security: Enforces retailer_id filter server-side — retailer can
    never see another retailer's orders within the same tenant.

    DC-12R1-S3-S1: dual-key scope — both wholesaler_id (tenant) and
    retailer_id are passed to the repository (defense-in-depth on top of
    the tenant-scoped session).
    """
    from models.order import OrderStatus

    # Map client-visible status back to internal statuses for filtering
    internal_status = None
    if order_status:
        status_map = {
            "CREATED": OrderStatus.DRAFT,
            "CONFIRMED": OrderStatus.CONFIRMED,
            "DELIVERED": OrderStatus.FULFILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "RETURNED": OrderStatus.RETURNED,
        }
        internal_status = status_map.get(order_status.upper())

    orders, total = await get_orders_paginated(
        db=db,
        page=page,
        size=size,
        wholesaler_id=client.tenant_id,  # DC-12R1-S3-S1: dual-key scope
        retailer_id=client.retailer_id,  # P0: server-enforced scope
        status_filter=internal_status,
    )

    pages = ceil(total / size) if total > 0 else 0

    return DataResponse(
        success=True,
        data={
            "items": [_order_to_client_view(o).model_dump() for o in orders],
            "pagination": Pagination(
                page=page, size=size, total=total, pages=pages
            ).model_dump(),
        },
        timestamp=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# GET /client/orders/{order_id} — Single order detail (own orders only)
# ---------------------------------------------------------------------------

@router.get(
    "/{order_id}",
    response_model=DataResponse[ClientOrderView],
    status_code=status.HTTP_200_OK,
)
async def get_order(
    order_id: str,
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:orders:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Get order detail — only if it belongs to the authenticated retailer.

    DC-12R1-S3-S1: the order is fetched with a dual-key scoped query
    (order_id + wholesaler_id + retailer_id + is_deleted=false) so a
    wrong-retailer / wrong-supplier request returns a neutral 404 without
    first loading the row and disclosing its existence.
    """
    order = await get_order_for_retailer(
        db,
        order_id=order_id,
        wholesaler_id=client.tenant_id,
        retailer_id=client.retailer_id,
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ORDER_NOT_FOUND", "message": "Order not found"},
        )

    return DataResponse(
        success=True,
        data=_order_to_client_view(order),
        timestamp=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# POST /client/orders/{order_id}/cancel — Cancel own order (draft/confirmed only)
# ---------------------------------------------------------------------------

@router.post(
    "/{order_id}/cancel",
    response_model=DataResponse[ClientOrderView],
    status_code=status.HTTP_200_OK,
)
async def cancel_order(
    order_id: str,
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:orders:create")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Cancel an order — only allowed if status is CREATED or CONFIRMED,
    and only if the order belongs to the authenticated retailer.

    DC-12R1-S3-S1: MVP create authority (``client:orders:create``) also
    covers cancellation of the retailer's own DRAFT/CONFIRMED order — no
    separate cancel permission is introduced in this slice. The order is
    fetched with a dual-key scoped query so a wrong-retailer /
    wrong-supplier cancel returns a neutral 404 without loading the row.
    """
    order = await get_order_for_retailer(
        db,
        order_id=order_id,
        wholesaler_id=client.tenant_id,
        retailer_id=client.retailer_id,
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ORDER_NOT_FOUND", "message": "Order not found"},
        )

    # Validate cancellation is allowed
    from crud.order import InvalidStateTransitionError
    release_reservation = order.status.value == "confirmed"
    try:
        order = await crud_cancel_order(
            db=db,
            order=order,
            updated_by=client.user_id,
        )
        if release_reservation:
            from services.inventory_service import InventoryService

            await db.refresh(order, ["items"])
            await InventoryService().release_on_cancel(db, order=order)
            await db.flush()
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CANCEL_NOT_ALLOWED",
                "message": str(e),
            },
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise

    return DataResponse(
        success=True,
        data=_order_to_client_view(order),
        message="Order cancelled",
        timestamp=datetime.utcnow(),
    )
