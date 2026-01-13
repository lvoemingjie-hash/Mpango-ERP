"""
Order management API endpoints.
Implements openapi.yaml /orders/* endpoints as stubs.

All endpoints return 501 Not Implemented for skeleton.
RBAC permissions enforced per rbac_matrix.md.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query

from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from schemas.order import (
    OrderCreateRequest,
    OrderResponse,
    OrderListResponse,
    OrderActionResponse,
    OrderStatus
)

router = APIRouter()


@router.get("", response_model=OrderListResponse, status_code=status.HTTP_200_OK)
async def list_orders(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    status_filter: Optional[OrderStatus] = Query(None, alias="status", description="Filter by status"),
    retailer_id: Optional[str] = Query(None, description="Filter by retailer ID"),
    token: TokenPayload = Depends(RequirePermission("orders:read"))
):
    """
    List orders with pagination and filters.
    
    Implements openapi.yaml GET /orders
    
    Requires: orders:read permission
    
    Returns:
        501 Not Implemented (skeleton)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="List orders endpoint not implemented in skeleton"
    )


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    request: OrderCreateRequest,
    token: TokenPayload = Depends(RequirePermission("orders:create"))
):
    """
    Create a new order.
    
    Implements openapi.yaml POST /orders
    
    Creates order with status=pending. Inventory is NOT deducted at this stage (MVP).
    
    Requires: orders:create permission
    
    Returns:
        501 Not Implemented (skeleton)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Create order endpoint not implemented in skeleton"
    )


@router.get("/{order_id}", response_model=OrderResponse, status_code=status.HTTP_200_OK)
async def get_order(
    order_id: str,
    token: TokenPayload = Depends(RequirePermission("orders:read"))
):
    """
    Get order by ID.
    
    Implements openapi.yaml GET /orders/{order_id}
    
    Requires: orders:read permission
    
    Returns:
        501 Not Implemented (skeleton)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Get order endpoint not implemented in skeleton"
    )


@router.post("/{order_id}/confirm", response_model=OrderActionResponse, status_code=status.HTTP_200_OK)
async def confirm_order(
    order_id: str,
    token: TokenPayload = Depends(RequirePermission("orders:confirm"))
):
    """
    Confirm order and deduct inventory.
    
    Implements openapi.yaml POST /orders/{order_id}/confirm
    
    Transitions order from pending → confirmed.
    Deducts inventory and creates inventory_logs.
    
    Requires: orders:confirm permission
    
    Returns:
        501 Not Implemented (skeleton)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Confirm order endpoint not implemented in skeleton"
    )


@router.post("/{order_id}/ship", response_model=OrderActionResponse, status_code=status.HTTP_200_OK)
async def ship_order(
    order_id: str,
    token: TokenPayload = Depends(RequirePermission("orders:ship"))
):
    """
    Mark order as shipped.
    
    Implements openapi.yaml POST /orders/{order_id}/ship
    
    Transitions order from confirmed → shipped.
    Does NOT affect inventory (MVP).
    
    Requires: orders:ship permission
    
    Returns:
        501 Not Implemented (skeleton)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Ship order endpoint not implemented in skeleton"
    )


@router.post("/{order_id}/cancel", response_model=OrderActionResponse, status_code=status.HTTP_200_OK)
async def cancel_order(
    order_id: str,
    token: TokenPayload = Depends(RequirePermission("orders:cancel"))
):
    """
    Cancel order.
    
    Implements openapi.yaml POST /orders/{order_id}/cancel
    
    Can cancel from pending or confirmed status.
    If confirmed, rolls back inventory and creates cancel-type inventory_log.
    
    Requires: orders:cancel permission
    
    Returns:
        501 Not Implemented (skeleton)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Cancel order endpoint not implemented in skeleton"
    )
