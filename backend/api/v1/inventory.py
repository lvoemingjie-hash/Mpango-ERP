from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_context, get_tenant_db_session
from api.middleware.rbac import RequirePermission  # S2.5: Added RBAC import
from core.logging_config import get_request_logger
from core.security import TokenPayload
from schemas.common import DataResponse, Pagination
from schemas.inventory import (
    StockViewRead,
    InventoryAdjustRequest,
    InventoryAdjustResponse,
    MovementLogEntry,
    MovementLogListData,
)
from services.inventory_service import InventoryService


router = APIRouter()


def _to_stock_view(sku, stock) -> StockViewRead:
    on_hand: Decimal = stock.quantity_on_hand
    reserved: Decimal = stock.quantity_reserved
    available = on_hand - reserved

    return StockViewRead(
        sku_id=str(sku.id),
        sku_code=sku.sku_code,
        sku_name=sku.name,
        quantity_on_hand=on_hand,
        quantity_reserved=reserved,
        quantity_available=available,
        updated_at=stock.updated_at,
    )


@router.get("/stocks", response_model=DataResponse[dict], status_code=status.HTTP_200_OK)
async def list_stock(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    sku_code: Optional[str] = Query(None, description="Filter by sku_code"),
    is_active: Optional[bool] = Query(None, description="Filter by SKU active flag"),
    token: TokenPayload = Depends(RequirePermission("inventory:read")),  # S2.5: Added RBAC
    db: AsyncSession = Depends(get_tenant_db_session),
):
    # Get request context for logging
    request_id = getattr(request.state, 'request_id', 'N/A')
    tenant_id = getattr(request.state, 'tenant_id', 'N/A')
    logger = get_request_logger(request_id, tenant_id)

    logger.info(
        "list_stock_started",
        extra={
            "action": "list_stock",
            "user_id": token.user_id,
            "page": page,
            "size": size,
            "sku_code": sku_code,
            "is_active": is_active
        }
    )

    try:
        service = InventoryService()
        rows, total = await service.list_stock(db, page=page, size=size, sku_code=sku_code, is_active=is_active)
        pages = ceil(total / size) if total > 0 else 0

        result = DataResponse(
            success=True,
            data={
                "items": [_to_stock_view(sku, stock) for sku, stock in rows],
                "pagination": Pagination(page=page, size=size, total=total, pages=pages).model_dump(),
            },
            timestamp=datetime.utcnow(),
        )

        logger.info(
            "list_stock_completed",
            extra={
                "action": "list_stock",
                "total_items": total,
                "pages": pages,
                "success": True
            }
        )

        return result

    except Exception as e:
        logger.error(
            "list_stock_failed",
            extra={
                "action": "list_stock",
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        raise


@router.get("/stocks/{sku_code}", response_model=DataResponse[StockViewRead], status_code=status.HTTP_200_OK)
async def get_stock_by_sku(
    sku_code: str,
    request: Request,
    token: TokenPayload = Depends(RequirePermission("inventory:read")),  # S2.5: Added RBAC
    db: AsyncSession = Depends(get_tenant_db_session),
):
    # Get request context for logging
    request_id = getattr(request.state, 'request_id', 'N/A')
    tenant_id = getattr(request.state, 'tenant_id', 'N/A')
    logger = get_request_logger(request_id, tenant_id)

    logger.info(
        "get_stock_by_sku_started",
        extra={
            "action": "get_stock_by_sku",
            "user_id": token.user_id,
            "sku_code": sku_code
        }
    )

    try:
        service = InventoryService()
        sku, stock = await service.get_stock_by_sku_code(db, sku_code=sku_code)

        result = DataResponse(success=True, data=_to_stock_view(sku, stock), timestamp=datetime.utcnow())

        logger.info(
            "get_stock_by_sku_completed",
            extra={
                "action": "get_stock_by_sku",
                "sku_id": str(sku.id),
                "sku_code": sku.sku_code,
                "quantity_on_hand": float(stock.quantity_on_hand),
                "quantity_reserved": float(stock.quantity_reserved),
                "success": True
            }
        )

        return result

    except HTTPException as e:
        logger.warning(
            "get_stock_by_sku_failed",
            extra={
                "action": "get_stock_by_sku",
                "sku_code": sku_code,
                "error_code": e.detail.get("code") if isinstance(e.detail, dict) else "UNKNOWN",
                "status_code": e.status_code
            }
        )
        raise
    except Exception as e:
        logger.error(
            "get_stock_by_sku_failed",
            extra={
                "action": "get_stock_by_sku",
                "sku_code": sku_code,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        raise


@router.post("/adjust", response_model=DataResponse[InventoryAdjustResponse], status_code=status.HTTP_200_OK)
async def adjust_inventory(
    request_body: InventoryAdjustRequest,
    request: Request,
    token: TokenPayload = Depends(RequirePermission("inventory:update")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Manual inventory adjustment (stocktake / damage / correction).

    Positive quantity = add stock, negative = remove stock.
    Creates an audit trail entry in inventory_movements.
    """
    request_id = getattr(request.state, 'request_id', 'N/A')
    tenant_id = getattr(request.state, 'tenant_id', 'N/A')
    logger = get_request_logger(request_id, tenant_id)

    logger.info(
        "adjust_inventory_started",
        extra={
            "action": "adjust_inventory",
            "user_id": token.user_id,
            "sku_code": request_body.sku_code,
            "quantity": float(request_body.quantity),
            "reason": request_body.reason,
        }
    )

    service = InventoryService()
    stock, movement = await service.adjust_stock(
        db,
        sku_code=request_body.sku_code,
        quantity=request_body.quantity,
        reason=request_body.reason,
        adjusted_by=token.user_id,
    )

    logger.info(
        "adjust_inventory_completed",
        extra={
            "action": "adjust_inventory",
            "sku_code": request_body.sku_code,
            "quantity_before": float(movement.quantity_before),
            "quantity_after": float(movement.quantity_after),
            "success": True,
        }
    )

    return DataResponse(
        success=True,
        data=InventoryAdjustResponse(
            sku_code=request_body.sku_code,
            quantity_before=movement.quantity_before,
            quantity_after=movement.quantity_after,
            adjustment=request_body.quantity,
            reason=request_body.reason,
        ),
        message="Stock adjusted successfully",
        timestamp=datetime.utcnow(),
    )


@router.get("/logs", response_model=DataResponse[MovementLogListData], status_code=status.HTTP_200_OK)
async def list_inventory_logs(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    sku_code: Optional[str] = Query(None, description="Filter by SKU code"),
    movement_type: Optional[str] = Query(None, description="Filter by type: adjustment, deduction, restock"),
    token: TokenPayload = Depends(RequirePermission("inventory:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    List inventory movement journal entries (audit log).
    """
    request_id = getattr(request.state, 'request_id', 'N/A')
    tenant_id = getattr(request.state, 'tenant_id', 'N/A')
    logger = get_request_logger(request_id, tenant_id)

    logger.info(
        "list_inventory_logs_started",
        extra={
            "action": "list_inventory_logs",
            "user_id": token.user_id,
            "page": page,
            "size": size,
            "sku_code": sku_code,
            "movement_type": movement_type,
        }
    )

    service = InventoryService()
    rows, total = await service.list_movements(
        db, page=page, size=size, sku_code=sku_code, movement_type=movement_type
    )
    pages = ceil(total / size) if total > 0 else 0

    items = [
        MovementLogEntry(
            id=str(mv.id),
            sku_id=str(mv.sku_id),
            sku_code=sc,
            movement_type=mv.movement_type,
            quantity=mv.quantity,
            quantity_before=mv.quantity_before,
            quantity_after=mv.quantity_after,
            reason=mv.reason,
            reference_type=mv.reference_type,
            reference_id=str(mv.reference_id) if mv.reference_id else None,
            created_at=mv.created_at,
            created_by=str(mv.created_by) if mv.created_by else None,
        )
        for mv, sc in rows
    ]

    data = MovementLogListData(
        items=items,
        pagination=Pagination(page=page, size=size, total=total, pages=pages).model_dump(),
    )

    logger.info(
        "list_inventory_logs_completed",
        extra={"action": "list_inventory_logs", "total": total, "success": True}
    )

    return DataResponse(success=True, data=data, timestamp=datetime.utcnow())


@router.get("/orders/{order_id}/stocks", response_model=DataResponse[dict], status_code=status.HTTP_200_OK)
async def stock_view_for_order(
    order_id: str,
    request: Request,
    token: TokenPayload = Depends(RequirePermission("inventory:read")),  # S2.5: Added RBAC
    db: AsyncSession = Depends(get_tenant_db_session),
):
    # Get request context for logging
    request_id = getattr(request.state, 'request_id', 'N/A')
    tenant_id = getattr(request.state, 'tenant_id', 'N/A')
    logger = get_request_logger(request_id, tenant_id)

    logger.info(
        "stock_view_for_order_started",
        extra={
            "action": "stock_view_for_order",
            "user_id": token.user_id,
            "order_id": order_id
        }
    )

    try:
        service = InventoryService()
        items = await service.stock_view_for_order(db, order_id=order_id)

        result = DataResponse(
            success=True,
            data={
                "order_id": order_id,
                "items": [_to_stock_view(sku, stock) for sku, stock in items],
            },
            timestamp=datetime.utcnow(),
        )

        logger.info(
            "stock_view_for_order_completed",
            extra={
                "action": "stock_view_for_order",
                "order_id": order_id,
                "item_count": len(items),
                "success": True
            }
        )

        return result

    except HTTPException as e:
        logger.warning(
            "stock_view_for_order_failed",
            extra={
                "action": "stock_view_for_order",
                "order_id": order_id,
                "error_code": e.detail.get("code") if isinstance(e.detail, dict) else "UNKNOWN",
                "status_code": e.status_code
            }
        )
        raise
    except Exception as e:
        logger.error(
            "stock_view_for_order_failed",
            extra={
                "action": "stock_view_for_order",
                "order_id": order_id,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        raise
