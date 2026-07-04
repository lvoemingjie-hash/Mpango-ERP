"""
Order management API endpoints.
Implements openapi.yaml /orders/* endpoints.

Tenant isolation enforced via JWT-derived search_path.

State Machine:
- Draft - Confirmed
- Confirmed - Paid
- Paid - Fulfilled (with inventory auto-deduction)
- Cancel only allowed in Draft or Confirmed
- Return only allowed in Fulfilled
"""
from datetime import datetime
from math import ceil
from typing import Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.dependencies import get_current_user_context
from api.middleware.rbac import RequirePermission  # S2.5: Added RBAC import
from core.security import TokenPayload
from core.domain.order_state import (
    InvalidStateTransitionError as DomainInvalidStateTransitionError,
    OrderInvariantViolation,
)
from crud.order import (
    get_order_by_id,
    get_orders_paginated,
    create_order as crud_create_order,
    confirm_order as crud_confirm_order,
    pay_order as crud_pay_order,
    fulfill_order as crud_fulfill_order,
    cancel_order as crud_cancel_order,
    return_order as crud_return_order,
    batch_retailer_names,
    InvalidStateTransitionError
)
from schemas.order import (
    OrderCreateRequest,
    WholesalerOrderCreateRequest,
    OrderResponse,
    OrderListResponse,
    OrderActionResponse,
    OrderStatus,
    Order as OrderSchema,
    OrderItem as OrderItemSchema,
    PayOrderRequest,
)
from schemas.common import Pagination

router = APIRouter()


def order_to_schema(order, retailer_name: str | None = None) -> OrderSchema:
    """Convert Order model to Order schema."""
    return OrderSchema(
        id=str(order.id),
        wholesaler_id=str(order.wholesaler_id),
        retailer_id=str(order.retailer_id),
        retailer_name=retailer_name,
        status=OrderStatus(order.status.value),
        total_amount=order.total_amount,
        items=[
            OrderItemSchema(
                id=str(item.id),
                product_name=item.product_name,
                sku_code=item.sku_code,
                quantity=item.quantity,
                unit_price=item.unit_price,
                subtotal=item.subtotal
            )
            for item in order.items
        ],
        notes=order.notes,
        created_by=str(order.created_by) if order.created_by else None,
        created_at=order.created_at,
        updated_at=order.updated_at
    )


@router.get("", response_model=OrderListResponse, status_code=status.HTTP_200_OK)
async def list_orders(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    retailer_id: Optional[str] = Query(None, description="Filter by retailer ID"),
    token: TokenPayload = Depends(RequirePermission("orders:read")),  # S2.5: Added RBAC
    db: AsyncSession = Depends(get_tenant_db_session)
):
    """
    List orders with pagination and optional filters.

    Implements openapi.yaml GET /orders

    Returns:
        OrderListResponse with paginated orders
    """
    # Convert status string to enum if provided
    status_enum = None
    if status_filter:
        try:
            from models.order import OrderStatus as ModelOrderStatus
            status_enum = ModelOrderStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_STATUS",
                    "message": f"Invalid status '{status_filter}'. Valid values: draft, confirmed, cancelled"
                }
            )

    orders, total = await get_orders_paginated(
        db,
        page=page,
        size=size,
        wholesaler_id=token.tenant_id,
        status_filter=status_enum,
        retailer_id=retailer_id,
    )

    # Batch-fetch retailer names to avoid N+1
    rids = [o.retailer_id for o in orders]
    name_map = await batch_retailer_names(db, rids)

    pages = ceil(total / size) if total > 0 else 0

    return OrderListResponse(
        success=True,
        data={
            "items": [
                order_to_schema(o, retailer_name=name_map.get(str(o.retailer_id)))
                for o in orders
            ],
            "pagination": Pagination(
                page=page,
                size=size,
                total=total,
                pages=pages
            ).model_dump()
        },
        timestamp=datetime.utcnow()
    )


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    request: WholesalerOrderCreateRequest,
    token: TokenPayload = Depends(RequirePermission("orders:create")),  # S2.5: Added RBAC
    db: AsyncSession = Depends(get_tenant_db_session)
):
    """
    Create a new order with server-resolved pricing.

    Phase 4: Price authority is enforced server-side.
    The request contains only sku_code + quantity per item.
    product_name and unit_price are resolved from the SKU catalog
    and retailer_prices table respectively. Any client-supplied
    price is structurally impossible (not in the request schema).

    Returns:
        OrderResponse with created order
    """
    from sqlalchemy import text as sa_text

    # ---------------------------------------------------------------
    # Step 1: Validate retailer binding exists for this tenant
    # ---------------------------------------------------------------
    binding_sql = """
        SELECT id FROM public.wholesaler_retailer_bindings
        WHERE wholesaler_id = :tenant_id
          AND retailer_id = :retailer_id
          AND status = 'active'
        LIMIT 1
    """
    binding_result = await db.execute(
        sa_text(binding_sql),
        {"tenant_id": token.tenant_id, "retailer_id": request.retailer_id},
    )
    if binding_result.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "RETAILER_NOT_BOUND",
                "message": "Retailer is not bound to this wholesaler or binding is inactive",
            },
        )

    # ---------------------------------------------------------------
    # Step 2: Resolve SKU data + retailer-specific pricing server-side
    # ---------------------------------------------------------------
    sku_codes = [item.sku_code for item in request.items]
    placeholders = ", ".join([f":sku_{i}" for i in range(len(sku_codes))])
    sku_params = {f"sku_{i}": code for i, code in enumerate(sku_codes)}

    sku_sql = f"""
        SELECT
            s.id   AS sku_id,
            s.sku_code,
            s.name,
            s.is_active,
            COALESCE(i.quantity_on_hand, 0) AS quantity_on_hand,
            rp.price AS sell_price
        FROM skus s
        LEFT JOIN inventory_stocks i
            ON i.sku_id = s.id AND i.is_deleted IS NOT TRUE
        LEFT JOIN retailer_prices rp
            ON rp.sku_id = s.id
            AND rp.retailer_id = :retailer_id
            AND rp.is_deleted IS NOT TRUE
        WHERE s.sku_code IN ({placeholders})
          AND s.is_deleted IS NOT TRUE
    """
    sku_params["retailer_id"] = request.retailer_id
    result = await db.execute(sa_text(sku_sql), sku_params)
    sku_rows = {row.sku_code: row for row in result.fetchall()}

    # ---------------------------------------------------------------
    # Step 3: Validate each item and build server-resolved order items
    # ---------------------------------------------------------------
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

        if sku_row.sell_price is None:
            errors.append(
                f"No price configured for '{item.sku_code}' for this retailer. "
                f"Set a price before creating orders."
            )
            continue

        resolved_price = Decimal(str(sku_row.sell_price))
        if resolved_price <= 0:
            errors.append(
                f"Invalid price for '{item.sku_code}'. Price must be positive."
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

    # ---------------------------------------------------------------
    # Step 4: Create order via existing CRUD (all prices server-resolved)
    # ---------------------------------------------------------------
    order = await crud_create_order(
        db=db,
        wholesaler_id=token.tenant_id,
        retailer_id=request.retailer_id,
        items=order_items,
        notes=request.notes,
        created_by=token.user_id
    )

    return OrderResponse(
        success=True,
        data=order_to_schema(order),
        message="Order created successfully",
        timestamp=datetime.utcnow()
    )


@router.get("/{order_id}", response_model=OrderResponse, status_code=status.HTTP_200_OK)
async def get_order(
    order_id: str,
    token: TokenPayload = Depends(RequirePermission("orders:read")),  # S2.5: Added RBAC
    db: AsyncSession = Depends(get_tenant_db_session)
):
    """
    Get order by ID.

    Implements openapi.yaml GET /orders/{order_id}

    Returns:
        OrderResponse with order data
    """
    order = await get_order_by_id(db, order_id)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ORDER_NOT_FOUND",
                "message": f"Order with ID '{order_id}' not found"
            }
        )

    name_map = await batch_retailer_names(db, [order.retailer_id])

    return OrderResponse(
        success=True,
        data=order_to_schema(order, retailer_name=name_map.get(str(order.retailer_id))),
        timestamp=datetime.utcnow()
    )


@router.post("/{order_id}/confirm", response_model=OrderActionResponse, status_code=status.HTTP_200_OK)
async def confirm_order(
    order_id: str,
    token: TokenPayload = Depends(RequirePermission("orders:update")),  # S2.5: Added RBAC
    db: AsyncSession = Depends(get_tenant_db_session)
):
    """
    Confirm an order (draft - confirmed).

    Implements openapi.yaml POST /orders/{order_id}/confirm

    Returns:
        OrderActionResponse with updated status
    """
    order = await get_order_by_id(db, order_id)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ORDER_NOT_FOUND",
                "message": f"Order with ID '{order_id}' not found"
            }
        )

    try:
        order = await crud_confirm_order(db, order, updated_by=token.user_id)

        from services.inventory_service import InventoryService

        await db.refresh(order, ["items"])
        await InventoryService().reserve_on_confirm(db, order=order)
        await db.flush()
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "INVALID_STATE_TRANSITION",
                "message": str(e)
            }
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise

    return OrderActionResponse(
        success=True,
        data={
            "order_id": str(order.id),
            "status": order.status.value
        },
        message="Order confirmed successfully",
        timestamp=datetime.utcnow()
    )


@router.post("/{order_id}/pay", response_model=OrderActionResponse, status_code=status.HTTP_200_OK)
async def pay_order(
    order_id: str,
    token: TokenPayload = Depends(RequirePermission("payments:create")),
    db: AsyncSession = Depends(get_tenant_db_session),
    payment_input: Optional[PayOrderRequest] = None,
):
    """
    Record a payment against an order and transition state.

    Phase 5: Extended to support optional structured payment recording.

    Backward compatible:
    - No body -> state-only transition (confirmed -> paid), same as before
    - With body (method + amount) -> creates Payment record + transitions state

    Transactional safety (P0 repair):
    - Both payment creation and order state transition execute inside
      a single `async with db.begin()` block.
    - If either step fails, the entire transaction rolls back: no
      orphaned payment, no stale order state.
    """

    # -- Validate order exists (outside transaction for cheap read) --
    order = await get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ORDER_NOT_FOUND",
                "message": f"Order with ID '{order_id}' not found",
            },
        )

    # -- Determine what we need to do --
    from core.domain.order_state import OrderState

    if payment_input and payment_input.amount is not None:
        # Structured payment path
        if not payment_input.method:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "PAYMENT_METHOD_REQUIRED",
                    "message": "method is required when amount is provided",
                },
            )

        pay_amount = Decimal(str(payment_input.amount))
        order_total = order.total_amount

        # Phase 5 repair: compute TRUE outstanding balance from prior payments
        from repositories.payment_repository import PaymentRepository
        payment_repo = PaymentRepository()
        prior_paid = await payment_repo.get_order_paid_total(db, order_id=order.id)
        remaining_balance = order_total - prior_paid

        if pay_amount > remaining_balance:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "PAYMENT_EXCEEDS_REMAINING",
                    "message": (
                        f"Payment amount ({pay_amount}) exceeds "
                        f"remaining balance ({remaining_balance}). "
                        f"Order total: {order_total}, already paid: {prior_paid}."
                    ),
                },
            )

        current_state = OrderState(order.status.value)
        if current_state not in (OrderState.CONFIRMED, OrderState.PARTIALLY_PAID):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "INVALID_STATE_TRANSITION",
                    "message": (
                        f"Cannot record payment on order in "
                        f"'{order.status.value}' state. "
                        f"Order must be 'confirmed' or 'partially_paid'."
                    ),
                },
            )

        # Determine target state from CUMULATIVE settlement.
        # Credit closes the order lifecycle (PAID) but does NOT inflate
        # paid_total (which counts only cash/transfer for financial reporting).
        # MVP constraint: credit is full-credit sale only — amount must equal
        # remaining balance.  No partial credit or split tender in this slice.
        if payment_input.method == "credit":
            # Guard 1: No duplicate credit on the same order.
            credit_count = await payment_repo.count_order_payments(
                db, order_id=order.id, method="credit",
            )
            if credit_count > 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "DUPLICATE_CREDIT_PAYMENT",
                        "message": (
                            "A credit payment already exists for this order. "
                            "Only one credit payment is allowed per order."
                        ),
                    },
                )
            # Guard 2: No split tender — credit is only allowed on a clean
            # order with zero prior cash/transfer settlement.
            if prior_paid > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "CREDIT_SPLIT_TENDER_UNSUPPORTED",
                        "message": (
                            f"Phase 6 MVP does not support split tender. "
                            f"This order already has {prior_paid} in "
                            f"cash/transfer payments. Credit is allowed only "
                            f"on a clean order with no prior settlement."
                        ),
                    },
                )
            # Guard 3: Full-credit sale only — amount must equal order total.
            if pay_amount != order_total:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "CREDIT_AMOUNT_MISMATCH",
                        "message": (
                            f"Phase 6 MVP supports full-credit sale only. "
                            f"Credit amount ({pay_amount}) must equal "
                            f"order total ({order_total}). "
                            f"Partial credit is not supported."
                        ),
                    },
                )

        cumulative_after_payment = prior_paid + pay_amount
        target_state = (
            OrderState.PAID
            if cumulative_after_payment >= order_total
            else OrderState.PARTIALLY_PAID
        )

    else:
        # Legacy empty-body path: confirmed -> paid, no payment record
        target_state = OrderState.PAID
        prior_paid = None
        remaining_balance = None
        payment_repo = None

    # -- Single atomic transaction: payment + state transition --
    from services.order_service import OrderService

    order_service = OrderService(db)

    if payment_input and payment_input.amount is not None:
        # Structured path: payment + state transition
        # Transaction is managed by get_tenant_db_session dependency
        try:
            payment_record = await payment_repo.create(
                db,
                order_id=order.id,
                retailer_id=order.retailer_id,
                transaction_id=payment_input.transaction_id,
                idempotency_key=None,
                amount=pay_amount,
                method=payment_input.method,
                status=(
                    "completed"
                    if (
                        payment_input.method == "transfer"
                        and target_state == OrderState.PAID
                    )
                    else "pending"
                ),
                created_by=(
                    token.user_id
                    if token.user_id
                    else None
                ),
            )

            # Apply outstanding balance delta (method-dependent):
            #   cash/transfer: -amount (receivable decreases)
            #   credit:        +amount (new receivable created)
            from services.payment_service import PaymentService
            payment_svc = PaymentService()
            balance_delta = (
                pay_amount
                if payment_input.method == "credit"
                else -pay_amount
            )
            await payment_svc._apply_outstanding_balance_delta(
                db,
                wholesaler_id=order.wholesaler_id,
                retailer_id=order.retailer_id,
                delta=balance_delta,
            )

            order = await order_service.transition(
                order_id=order.id,
                target_state=target_state,
                reason=(
                    f"Payment recorded: {payment_input.method} "
                    f"{payment_input.amount}"
                ),
                updated_by=token.user_id,
                payment_method=payment_input.method,
            )

            # S5-D4B: Settle only after the transition returns an actual PAID
            # order, not merely because the proposed target was PAID.
            order_status = getattr(order.status, "value", order.status)
            if order_status == OrderState.PAID.value:
                await payment_repo.update_cash_transfer_to_completed(
                    db, order_id=order.id,
                )
        except InvalidStateTransitionError as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "INVALID_STATE_TRANSITION",
                    "message": str(e),
                },
            )
        except Exception as e:
            if "Invalid state transition" in str(e) or "invariant" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "INVALID_STATE_TRANSITION",
                        "message": str(e),
                    },
                )
            raise

    else:
        # Legacy path: state transition only (no new transaction needed;
        # FastAPI session commit handles it)
        try:
            order = await order_service.transition(
                order_id=order.id,
                target_state=target_state,
                reason="Payment confirmed",
                updated_by=token.user_id,
            )
        except InvalidStateTransitionError as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "INVALID_STATE_TRANSITION",
                    "message": str(e),
                },
            )
        except Exception as e:
            if "Invalid state transition" in str(e) or "invariant" in str(e).lower():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "INVALID_STATE_TRANSITION",
                        "message": str(e),
                    },
                )
            raise
        payment_record = None

    # -- Build response --
    response_data = {
        "order_id": str(order.id),
        "status": order.status.value,
    }
    if payment_record:
        response_data["payment_id"] = str(payment_record["id"])
        response_data["payment_amount"] = str(payment_record["amount"])
        response_data["payment_method"] = payment_record["method"]

    return OrderActionResponse(
        success=True,
        data=response_data,
        message=(
            "Payment recorded and order updated"
            if payment_record
            else "Order marked as paid"
        ),
        timestamp=datetime.utcnow(),
    )

@router.post("/{order_id}/fulfill", response_model=OrderActionResponse, status_code=status.HTTP_200_OK)
async def fulfill_order(
    order_id: str,
    token: TokenPayload = Depends(RequirePermission("orders:update")),
    db: AsyncSession = Depends(get_tenant_db_session)
):
    """
    Fulfill an order (paid - fulfilled) with inventory auto-deduction.

    Implements POST /orders/{order_id}/fulfill
    Uses OrderService.transition() for atomic state change + ledger entries,
    then deducts inventory_stocks.quantity_on_hand for each order item.

    Returns:
        OrderActionResponse with updated status
    """
    order = await get_order_by_id(db, order_id)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ORDER_NOT_FOUND",
                "message": f"Order with ID '{order_id}' not found"
            }
        )

    try:
        from services.order_service import OrderService
        from core.domain.order_state import OrderState

        # Expire the preflight object so OrderService.transition() reloads the
        # locked row from the database instead of reusing stale identity-map state.
        order_uuid = order.id
        db.expire(order)

        order_service = OrderService(db)
        order = await order_service.transition(
            order_id=order_uuid,
            target_state=OrderState.FULFILLED,
            reason="Order fulfilled",
            updated_by=token.user_id
        )

        from services.inventory_service import InventoryService

        await db.refresh(order, ["items"])
        inventory_service = InventoryService()
        for item in order.items:
            await inventory_service.deduct_on_fulfillment(
                db,
                sku_code=item.sku_code,
                quantity=Decimal(str(item.quantity)),
                order_id=order.id,
                order_item_id=item.id,
                fulfilled_by=token.user_id,
            )

        await db.flush()

    except (InvalidStateTransitionError, DomainInvalidStateTransitionError, OrderInvariantViolation) as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "INVALID_STATE_TRANSITION",
                "message": str(e)
            }
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        if "Invalid state transition" in str(e) or "invariant" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "INVALID_STATE_TRANSITION",
                    "message": str(e)
                }
            )
        raise

    return OrderActionResponse(
        success=True,
        data={
            "order_id": str(order.id),
            "status": order.status.value
        },
        message="Order fulfilled. Inventory deducted.",
        timestamp=datetime.utcnow()
    )


@router.post("/{order_id}/cancel", response_model=OrderActionResponse, status_code=status.HTTP_200_OK)
async def cancel_order(
    order_id: str,
    token: TokenPayload = Depends(RequirePermission("orders:update")),  # S2.5: Added RBAC
    db: AsyncSession = Depends(get_tenant_db_session)
):
    """
    Cancel an order (draft/confirmed - cancelled).

    Implements openapi.yaml POST /orders/{order_id}/cancel

    Returns:
        OrderActionResponse with updated status
    """
    order = await get_order_by_id(db, order_id)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ORDER_NOT_FOUND",
                "message": f"Order with ID '{order_id}' not found"
            }
        )

    release_reservation = order.status.value == "confirmed"
    try:
        order = await crud_cancel_order(db, order, updated_by=token.user_id)
        if release_reservation:
            from services.inventory_service import InventoryService

            await db.refresh(order, ["items"])
            await InventoryService().release_on_cancel(db, order=order)
            await db.flush()
    except InvalidStateTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "INVALID_STATE_TRANSITION",
                "message": str(e)
            }
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise

    return OrderActionResponse(
        success=True,
        data={
            "order_id": str(order.id),
            "status": order.status.value
        },
        message="Order cancelled successfully",
        timestamp=datetime.utcnow()
    )


@router.post("/{order_id}/return", response_model=OrderActionResponse, status_code=status.HTTP_200_OK)
async def return_order(
    order_id: str,
    token: TokenPayload = Depends(RequirePermission("orders:update")),
    db: AsyncSession = Depends(get_tenant_db_session)
):
    """
    Process a full return on a fulfilled order (fulfilled - returned).

    This endpoint:
    1. Validates order is in "fulfilled" status
    2. Transitions order status to "returned"
    3. Posts reversal ledger entries (via OrderService)
    4. Restores fulfilled inventory and writes restock movement entries

    Returns:
        OrderActionResponse with updated status
    """
    order = await get_order_by_id(db, order_id)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ORDER_NOT_FOUND",
                "message": f"Order with ID '{order_id}' not found"
            }
        )

    try:
        # Use OrderService for atomic transition + ledger posting, then restore
        # inventory in the same DB transaction before the request commits.
        from services.order_service import OrderService
        from core.domain.order_state import OrderState
        from services.inventory_service import InventoryService

        order_service = OrderService(db)
        order = await order_service.transition(
            order_id=order.id,
            target_state=OrderState.RETURNED,
            reason="Full return requested",
            updated_by=token.user_id
        )

        await db.refresh(order, ["items"])
        inventory_service = InventoryService()
        for item in order.items:
            await inventory_service.restock_on_return(
                db,
                sku_code=item.sku_code,
                quantity=Decimal(str(item.quantity)),
                order_id=order.id,
                returned_by=token.user_id,
            )

        await db.flush()
    except (InvalidStateTransitionError, DomainInvalidStateTransitionError, OrderInvariantViolation) as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "INVALID_STATE_TRANSITION",
                "message": str(e)
            }
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        if "Invalid state transition" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "INVALID_STATE_TRANSITION",
                    "message": str(e)
                }
            )
        raise

    return OrderActionResponse(
        success=True,
        data={
            "order_id": str(order.id),
            "status": order.status.value
        },
        message="Order returned successfully. Refund ledger entries posted and inventory restored.",
        timestamp=datetime.utcnow()
    )
