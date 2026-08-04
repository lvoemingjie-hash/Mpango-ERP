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

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from math import ceil
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from api.v1.client.dependencies import ClientIdentity, resolve_client_identity
from api.v1.orders import (
    IDEMPOTENCY_KEY_ALLOWED_CHARS,
    IDEMPOTENCY_KEY_MAX_LENGTH,
    IDEMPOTENCY_KEY_MIN_LENGTH,
    RESERVED_IDEMPOTENCY_KEY_PREFIX,
    _restore_tenant_search_path_after_rollback,
)
from core.security import TokenPayload
from crud.order import (
    create_order as crud_create_order,
    get_order_for_retailer,
    get_orders_for_retailer,
    cancel_order as crud_cancel_order,
)
from repositories.payment_declaration_repository import PaymentDeclarationRepository
from schemas.client import (
    ClientCreateOrderRequest,
    ClientOrderView,
    ClientOrderItemView,
    map_order_status_for_client,
)
from schemas.common import DataResponse, Pagination
from schemas.declaration import ClientDeclarationView, DeclarationSubmitRequest
from schemas.print import OrderPrintView
from services.payment_declaration_service import PaymentDeclarationService
from services.print_service import build_order_print


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

    orders, total = await get_orders_for_retailer(
        db=db,
        wholesaler_id=client.tenant_id,  # mandatory validated dual-key scope
        retailer_id=client.retailer_id,  # mandatory validated dual-key scope
        page=page,
        size=size,
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
# GET /client/orders/{order_id}/print — Printable order document (Contract A)
# I2C-I1: 100% read-only, server-authoritative prices/totals, dual-key scoped.
# ---------------------------------------------------------------------------

@router.get(
    "/{order_id}/print",
    response_model=DataResponse[OrderPrintView],
    status_code=status.HTTP_200_OK,
)
async def print_order(
    order_id: str,
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:orders:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Printable order document — server-authoritative prices, subtotals, totals.

    Dual-key scoped (order_id + wholesaler_id + retailer_id); wrong
    retailer/supplier returns neutral 404 without existence disclosure.
    Read-only: no writes, no financial fingerprints changed.
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
    view = await build_order_print(
        db,
        order=order,
        wholesaler_id=uuid.UUID(client.tenant_id),
        retailer_id=uuid.UUID(client.retailer_id),
    )
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ORDER_NOT_FOUND", "message": "Order not found"},
        )
    return DataResponse(
        success=True,
        data=view,
        timestamp=datetime.now(timezone.utc),
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


# ---------------------------------------------------------------------------
# POST /client/orders/{order_id}/declare — Submit a payment declaration
# (DC-12R1-S3-S2B-I2B). Zero financial effect. Retailer identity from JWT only.
# ---------------------------------------------------------------------------

def _extract_constraint_name(exc) -> str:
    """Traverse the asyncpg IntegrityError chain for a constraint name.

    Handles ``exc.orig.diag.constraint_name``, bare ``exc.orig.constraint_name``,
    ``__cause__``, and ``__context__`` with cycle protection. Never parses
    human-readable exception messages.
    """
    visited: set[int] = set()
    stack = [exc]
    while stack:
        cur = stack.pop()
        cur_id = id(cur)
        if cur_id in visited:
            continue
        visited.add(cur_id)
        for attr in ("diag",):
            diag = getattr(cur, attr, None)
            if diag is not None:
                name = getattr(diag, "constraint_name", None)
                if isinstance(name, str) and name:
                    return name
        name = getattr(cur, "constraint_name", None)
        if isinstance(name, str) and name:
            return name
        for link in ("__cause__", "__context__"):
            linked = getattr(cur, link, None)
            if linked is not None and linked is not cur:
                stack.append(linked)
    return ""


def _validate_declaration_idempotency_key(value: str | None) -> str:
    """Declaration submission idempotency key (same charset/length rules as the
    canonical payment key). Rejects the reserved ``decl-confirm-`` namespace."""
    key = (value or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MISSING_DECLARATION_IDEMPOTENCY_KEY", "message": "X-Declaration-Idempotency-Key is required"},
        )
    if not (IDEMPOTENCY_KEY_MIN_LENGTH <= len(key) <= IDEMPOTENCY_KEY_MAX_LENGTH):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_DECLARATION_IDEMPOTENCY_KEY", "message": "X-Declaration-Idempotency-Key must be 8 to 64 visible ASCII characters"},
        )
    if any(char not in IDEMPOTENCY_KEY_ALLOWED_CHARS for char in key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_DECLARATION_IDEMPOTENCY_KEY", "message": "X-Declaration-Idempotency-Key contains invalid characters"},
        )
    if key.startswith(RESERVED_IDEMPOTENCY_KEY_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "RESERVED_IDEMPOTENCY_KEY", "message": "This idempotency-key prefix is reserved for internal declaration confirmation"},
        )
    return key


def _declaration_to_client_view(row) -> ClientDeclarationView:
    return ClientDeclarationView(
        id=str(row["id"]),
        order_id=str(row["order_id"]),
        declared_amount=row["declared_amount"],
        method=row["method"],
        transfer_reference=row.get("transfer_reference"),
        status=row["status"],
        submitted_at=row["submitted_at"],
        confirmed_at=row.get("confirmed_at"),
        rejected_at=row.get("rejected_at"),
        reason=row.get("reason"),
        receipt_number=row.get("receipt_number"),
        order_status=str(row["order_status"]) if row.get("order_status") is not None else None,
    )


@router.post(
    "/{order_id}/declare",
    response_model=DataResponse[ClientDeclarationView],
    status_code=status.HTTP_201_CREATED,
)
async def declare_payment(
    order_id: str,
    body: DeclarationSubmitRequest,
    response: Response,
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission("client:payments:declare")),
    db: AsyncSession = Depends(get_tenant_db_session),
    x_declaration_idempotency_key: Annotated[Optional[str], Header(alias="X-Declaration-Idempotency-Key")] = None,
):
    """Submit a payment declaration. This is NOT a payment: zero effect on
    payments, ledger, receivables, or order status until a cashier confirms."""
    idempotency_key = _validate_declaration_idempotency_key(x_declaration_idempotency_key)

    # Controlled body validation (fields optional at schema level).
    if body.declared_amount is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "DECLARATION_AMOUNT_REQUIRED", "message": "declared_amount is required"})
    if body.method is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "DECLARATION_METHOD_INVALID", "message": "method is required (cash or transfer)"})

    service = PaymentDeclarationService()
    is_replay = False
    try:
        record, is_replay = await service.submit_declaration(
            db=db,
            order_id=order_id,
            retailer_id=uuid.UUID(client.retailer_id),
            wholesaler_id=uuid.UUID(client.tenant_id),
            submitted_by=uuid.UUID(client.user_id),
            declared_amount=body.declared_amount,
            method=body.method,
            transfer_reference=body.transfer_reference,
            idempotency_key=idempotency_key,
        )
    except IntegrityError as exc:
        # Always rollback and restore search_path first.
        await db.rollback()
        await _restore_tenant_search_path_after_rollback(db)

        # Traverse the asyncpg exception chain for the constraint name.
        # Never parse human-readable messages.
        constraint_name = _extract_constraint_name(exc)
        if constraint_name != "ux_payment_declarations_retailer_idem":
            # FK, CHECK, or unrelated UNIQUE — re-raise unchanged.
            raise

        repo = PaymentDeclarationRepository()
        existing = await repo.get_by_retailer_idempotency(
            db, retailer_id=uuid.UUID(client.retailer_id), idempotency_key=idempotency_key
        )
        if existing is None:
            # Constraint was reported but no row found — re-raise original.
            raise
        if existing is not None:
            # Resolve the same way submit would, then classify.
            same = (
                str(existing["order_id"]) == str(order_id)
                and Decimal(str(existing["declared_amount"])) == body.declared_amount
                and str(existing["method"]) == body.method
                and (existing.get("transfer_reference") or None) == ((body.transfer_reference.strip() if body.transfer_reference else None) or None)
            )
            if same:
                record = existing
                is_replay = True
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "DECLARATION_IDEMPOTENCY_KEY_CONFLICT", "message": "Declaration idempotency key was already used with a different request"},
                )
        else:
            # Not the (retailer, key) unique conflict we expected. Re-raise so
            # the structured exception boundary handles it; never fake a 409.
            raise

    # Always resolve the joined view columns (receipt_number, order_status)
    # via exact dual-key lookup so the response is consistent for create+replay.
    repo = PaymentDeclarationRepository()
    detail = await repo.get_detail_by_retailer(
        db,
        declaration_id=record["id"],
        retailer_id=uuid.UUID(client.retailer_id),
        wholesaler_id=uuid.UUID(client.tenant_id),
    )
    if detail is not None:
        record = detail

    if is_replay:
        response.status_code = status.HTTP_200_OK

    return DataResponse(
        success=True,
        data=_declaration_to_client_view(record),
        message="Payment declaration replayed" if is_replay else "Payment declaration submitted",
        timestamp=datetime.utcnow(),
    )
