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
from typing import Annotated, Mapping, Optional
from uuid import UUID
from decimal import Decimal
from fastapi import APIRouter, Depends, Header, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from api.dependencies import get_tenant_db_session
from api.dependencies import get_current_user_context
from api.middleware.rbac import RequirePermission  # S2.5: Added RBAC import
from core.security import TokenPayload
from core.domain.order_state import (
    InvalidStateTransitionError as DomainInvalidStateTransitionError,
    OrderInvariantViolation,
)
from models.order import Order as OrderModel
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
from schemas.payment import PaymentMethod

router = APIRouter()

IDEMPOTENCY_KEY_MIN_LENGTH = 8
IDEMPOTENCY_KEY_MAX_LENGTH = 64
IDEMPOTENCY_KEY_ALLOWED_CHARS = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    ".:-_"
)


def _payment_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _validate_idempotency_key(value: str | None) -> str:
    key = (value or "").strip()
    if not key:
        raise _payment_error(
            status.HTTP_400_BAD_REQUEST,
            "MISSING_IDEMPOTENCY_KEY",
            "X-Idempotency-Key is required for payment requests",
        )
    if not (
        IDEMPOTENCY_KEY_MIN_LENGTH <= len(key) <= IDEMPOTENCY_KEY_MAX_LENGTH
    ):
        raise _payment_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_IDEMPOTENCY_KEY",
            "X-Idempotency-Key must be 8 to 64 visible ASCII characters",
        )
    if any(char not in IDEMPOTENCY_KEY_ALLOWED_CHARS for char in key):
        raise _payment_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_IDEMPOTENCY_KEY",
            "X-Idempotency-Key contains invalid characters",
        )
    return key


def _payment_method_value(payment_input: PayOrderRequest) -> str:
    if not payment_input.method:
        raise _payment_error(
            status.HTTP_400_BAD_REQUEST,
            "PAYMENT_METHOD_REQUIRED",
            "method is required for payment requests",
        )
    payment_method = (
        payment_input.method.value
        if isinstance(payment_input.method, PaymentMethod)
        else str(payment_input.method)
    )
    allowed_methods = {method.value for method in PaymentMethod}
    if payment_method not in allowed_methods:
        raise _payment_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_PAYMENT_METHOD",
            "Payment method must be one of: cash, transfer, credit",
        )
    return payment_method


def _same_payment_request(
    existing_payment,
    *,
    order_id: str,
    amount: Decimal,
    method: str,
    transaction_id: str | None,
) -> bool:
    return (
        str(existing_payment["order_id"]) == str(order_id)
        and Decimal(str(existing_payment["amount"])) == amount
        and str(existing_payment["method"]) == method
        and (existing_payment.get("transaction_id") or None) == (transaction_id or None)
    )


def _payment_mapping_or_none(candidate):
    return candidate if isinstance(candidate, Mapping) else None


def _payment_response_data(order, payment_record) -> dict:
    order_status = getattr(order.status, "value", order.status)
    return {
        "order_id": str(order.id),
        "status": str(order_status),
        "payment_id": str(payment_record["id"]),
        "payment_amount": str(payment_record["amount"]),
        "payment_method": payment_record["method"],
    }


async def _idempotency_replay_response(
    db: AsyncSession,
    *,
    payment_record,
) -> OrderActionResponse:
    order = await get_order_by_id(db, str(payment_record["order_id"]))
    if not order:
        raise _payment_error(
            status.HTTP_404_NOT_FOUND,
            "ORDER_NOT_FOUND",
            "Order for idempotent payment was not found",
        )
    return OrderActionResponse(
        success=True,
        data=_payment_response_data(order, payment_record),
        message="Payment replayed",
        timestamp=datetime.utcnow(),
    )


async def _get_order_by_id_for_update(
    db: AsyncSession,
    order_id: str,
) -> OrderModel | None:
    try:
        order_uuid = UUID(order_id)
    except ValueError:
        return None

    result = await db.execute(
        select(OrderModel)
        .where(OrderModel.id == order_uuid)
        .where(OrderModel.is_deleted == False)
        .options(selectinload(OrderModel.items))
        .with_for_update()
    )
    return result.scalar_one_or_none()


def _idempotency_conflict() -> HTTPException:
    return _payment_error(
        status.HTTP_409_CONFLICT,
        "IDEMPOTENCY_KEY_CONFLICT",
        "X-Idempotency-Key was already used with a different payment request",
    )


def _duplicate_transfer_reference() -> HTTPException:
    return _payment_error(
        status.HTTP_409_CONFLICT,
        "DUPLICATE_TRANSFER_REFERENCE",
        "Transfer transaction_id has already been recorded",
    )


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
    x_idempotency_key: Annotated[
        Optional[str], Header(alias="X-Idempotency-Key")
    ] = None,
):
    """
    Record a payment against an order and transition state.

    DC-11D: only structured payment requests are accepted. Each request must
    include a validated X-Idempotency-Key, and all financial reads/writes are
    performed after acquiring the order row lock in the same tenant session.
    """
    if payment_input is None or (
        payment_input.amount is None
        and payment_input.method is None
        and payment_input.transaction_id is None
        and payment_input.notes is None
    ):
        raise _payment_error(
            status.HTTP_400_BAD_REQUEST,
            "PAYMENT_BODY_REQUIRED",
            "Payment body with method and positive amount is required",
        )
    if payment_input.amount is None:
        raise _payment_error(
            status.HTTP_400_BAD_REQUEST,
            "PAYMENT_AMOUNT_REQUIRED",
            "amount is required for payment requests",
        )

    payment_method = _payment_method_value(payment_input)
    pay_amount = Decimal(str(payment_input.amount))
    idempotency_key = _validate_idempotency_key(x_idempotency_key)

    from repositories.payment_repository import PaymentRepository

    payment_repo = PaymentRepository()

    existing_payment = await payment_repo.get_by_idempotency_key(
        db,
        idempotency_key=idempotency_key,
    )
    existing_payment = _payment_mapping_or_none(existing_payment)
    if existing_payment:
        if _same_payment_request(
            existing_payment,
            order_id=order_id,
            amount=pay_amount,
            method=payment_method,
            transaction_id=payment_input.transaction_id,
        ):
            return await _idempotency_replay_response(
                db,
                payment_record=existing_payment,
            )
        raise _idempotency_conflict()

    # Acquire the order row lock before reading prior payments or deciding the
    # target state. This serializes competing payments for the same order.
    order = await _get_order_by_id_for_update(db, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ORDER_NOT_FOUND",
                "message": f"Order with ID '{order_id}' not found",
            },
        )

    from core.domain.order_state import OrderState

    existing_payment = await payment_repo.get_by_idempotency_key(
        db,
        idempotency_key=idempotency_key,
    )
    existing_payment = _payment_mapping_or_none(existing_payment)
    if existing_payment:
        if _same_payment_request(
            existing_payment,
            order_id=str(order.id),
            amount=pay_amount,
            method=payment_method,
            transaction_id=payment_input.transaction_id,
        ):
            return await _idempotency_replay_response(
                db,
                payment_record=existing_payment,
            )
        raise _idempotency_conflict()

    order_total = order.total_amount
    prior_paid = await payment_repo.get_order_paid_total(db, order_id=order.id)
    remaining_balance = order_total - prior_paid

    if pay_amount > remaining_balance:
        raise _payment_error(
            status.HTTP_400_BAD_REQUEST,
            "PAYMENT_EXCEEDS_REMAINING",
            "Payment amount exceeds remaining balance",
        )

    current_state = OrderState(order.status.value)
    if current_state not in (OrderState.CONFIRMED, OrderState.PARTIALLY_PAID):
        raise _payment_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE_TRANSITION",
            "Order must be confirmed or partially_paid before payment",
        )

    if payment_method == "transfer" and payment_input.transaction_id:
        existing_transfer = await payment_repo.get_by_transaction_id(
            db,
            transaction_id=payment_input.transaction_id,
        )
        existing_transfer = _payment_mapping_or_none(existing_transfer)
        if existing_transfer:
            raise _duplicate_transfer_reference()

    # Credit closes the order lifecycle (PAID) but does NOT inflate paid_total
    # (which counts only cash/transfer for financial reporting).
    if payment_method == "credit":
        credit_count = await payment_repo.count_order_payments(
            db, order_id=order.id, method="credit",
        )
        if credit_count > 0:
            raise _payment_error(
                status.HTTP_409_CONFLICT,
                "DUPLICATE_CREDIT_PAYMENT",
                "Only one credit payment is allowed per order",
            )
        if prior_paid > 0:
            raise _payment_error(
                status.HTTP_400_BAD_REQUEST,
                "CREDIT_SPLIT_TENDER_UNSUPPORTED",
                "Credit is allowed only on an order with no prior cash or transfer settlement",
            )
        if pay_amount != order_total:
            raise _payment_error(
                status.HTTP_400_BAD_REQUEST,
                "CREDIT_AMOUNT_MISMATCH",
                "Credit amount must equal order total",
            )

    cumulative_after_payment = prior_paid + pay_amount
    target_state = (
        OrderState.PAID
        if cumulative_after_payment >= order_total
        else OrderState.PARTIALLY_PAID
    )

    from services.order_service import OrderService

    order_service = OrderService(db)

    try:
        payment_record = await payment_repo.create(
            db,
            order_id=order.id,
            retailer_id=order.retailer_id,
            transaction_id=payment_input.transaction_id,
            idempotency_key=idempotency_key,
            amount=pay_amount,
            method=payment_method,
            status=(
                "completed"
                if (
                    payment_method == "transfer"
                    and target_state == OrderState.PAID
                )
                else "pending"
            ),
            created_by=token.user_id if token.user_id else None,
        )

        # Apply outstanding balance delta (method-dependent):
        #   cash/transfer: -amount (receivable decreases)
        #   credit:        +amount (new receivable created)
        from services.payment_service import PaymentService

        payment_svc = PaymentService()
        balance_delta = pay_amount if payment_method == "credit" else -pay_amount
        await payment_svc._apply_outstanding_balance_delta(
            db,
            wholesaler_id=order.wholesaler_id,
            retailer_id=order.retailer_id,
            delta=balance_delta,
        )

        order = await order_service.transition(
            order_id=order.id,
            target_state=target_state,
            reason="Payment recorded",
            updated_by=token.user_id,
            payment_method=payment_method,
        )

        # S5-D4B: Settle only after the transition returns an actual PAID
        # order, not merely because the proposed target was PAID.
        order_status = getattr(order.status, "value", order.status)
        if order_status == OrderState.PAID.value:
            await payment_repo.update_cash_transfer_to_completed(
                db, order_id=order.id,
            )
    except IntegrityError:
        await db.rollback()
        existing_payment = await payment_repo.get_by_idempotency_key(
            db,
            idempotency_key=idempotency_key,
        )
        existing_payment = _payment_mapping_or_none(existing_payment)
        if existing_payment and _same_payment_request(
            existing_payment,
            order_id=order_id,
            amount=pay_amount,
            method=payment_method,
            transaction_id=payment_input.transaction_id,
        ):
            return await _idempotency_replay_response(
                db,
                payment_record=existing_payment,
            )
        if payment_method == "transfer" and payment_input.transaction_id:
            existing_transfer = await payment_repo.get_by_transaction_id(
                db,
                transaction_id=payment_input.transaction_id,
            )
            existing_transfer = _payment_mapping_or_none(existing_transfer)
            if existing_transfer:
                raise _duplicate_transfer_reference()
        raise _idempotency_conflict()
    except (InvalidStateTransitionError, DomainInvalidStateTransitionError, OrderInvariantViolation):
        await db.rollback()
        raise _payment_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATE_TRANSITION",
            "Payment cannot transition the order from its current state",
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise

    return OrderActionResponse(
        success=True,
        data=_payment_response_data(order, payment_record),
        message="Payment recorded and order updated",
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
