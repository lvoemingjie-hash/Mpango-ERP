"""
Finance API endpoints — Invoices, Accounts Receivable, Financial Summary.

GAP 2: Minimum financial visibility without building a full accounting suite.

Permission mapping (DEDUCED from existing patterns):
  - Invoice download: `orders:read`  (it's an order projection, not a new resource)
  - Receivables list: `finance:read` (new resource noun, read-only)
  - Financial summary: `finance:read`

Error codes follow the PaymentService convention:
  detail={"code": "SCREAMING_SNAKE", "message": "..."}

Tenant isolation: enforced via `get_tenant_db_session` (JWT-derived search_path).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from models.ledger import AccountType, LedgerEntry
from models.order import Order, OrderItem, OrderStatus
from schemas.common import DataResponse
from schemas.finance import (
    ReceivableOrdersResponse,
    ReceivablesSummaryResponse,
)
from services.receivables_service import ReceivablesService

router = APIRouter()


# ============================================================================
# GET /orders/{order_id}/invoice — Plain-text invoice (PDF future iteration)
# ============================================================================

@router.get(
    "/orders/{order_id}/invoice",
    status_code=status.HTTP_200_OK,
    summary="Generate invoice for an order",
)
async def get_order_invoice(
    order_id: str,
    token: TokenPayload = Depends(RequirePermission("orders:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Returns a structured invoice object for the given order.

    Permission: orders:read (invoice is a projection of order data).
    Tenant isolation: automatic via get_tenant_db_session.
    """
    try:
        oid = uuid.UUID(order_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_ORDER_ID", "message": "Invalid order_id format"},
        )

    result = await db.execute(
        select(Order)
        .where(Order.id == oid)
        .where(Order.is_deleted.is_(False))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ORDER_NOT_FOUND", "message": f"Order '{order_id}' not found"},
        )

    # Only confirmed+ orders have invoices
    non_invoiceable = {OrderStatus.DRAFT, OrderStatus.CANCELLED, OrderStatus.VOIDED}
    if order.status in non_invoiceable:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVOICE_NOT_AVAILABLE",
                "message": f"Invoices are not available for orders in '{order.status.value}' status.",
            },
        )

    # Fetch line items
    items_result = await db.execute(
        select(OrderItem)
        .where(OrderItem.order_id == oid)
        .where(OrderItem.is_deleted.is_(False))
        .order_by(OrderItem.created_at)
    )
    items = items_result.scalars().all()

    # Fetch ledger entries related to this order
    ledger_result = await db.execute(
        select(LedgerEntry)
        .where(or_(
            and_(LedgerEntry.reference_type.in_(('order', 'refund')), LedgerEntry.reference_id == oid),
            and_(LedgerEntry.reference_type == 'payment', LedgerEntry.reference_id.in_(
                select(text('id')).select_from(text('payments')).where(text('order_id = :invoice_order_id'))
            )),
        ))
        .where(LedgerEntry.is_deleted.is_(False))
        .order_by(LedgerEntry.transaction_date),
        {"invoice_order_id": oid},
    )
    ledger_entries = ledger_result.scalars().all()

    # Payment history is the shared settlement fact, including partial receipts.
    from repositories.payment_repository import PaymentRepository
    from services.payment_history_contract import assert_valid_payment_history
    await assert_valid_payment_history(db, order_ids=[oid], context='Invoice')
    total_paid = await PaymentRepository().get_order_paid_total(db, order_id=oid)

    invoice_data = {
        "invoice_number": f"INV-{str(order.id)[:8].upper()}",
        "order_id": str(order.id),
        "status": order.status.value,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        "retailer_id": str(order.retailer_id) if order.retailer_id else None,
        "wholesaler_id": str(order.wholesaler_id) if order.wholesaler_id else None,
        "line_items": [
            {
                "product_name": item.product_name,
                "sku_code": item.sku_code,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
                "subtotal": float(item.subtotal),
            }
            for item in items
        ],
        "subtotal": float(order.total_amount),
        "total_amount": float(order.total_amount),
        "currency": order.currency_snapshot,
        "total_paid": float(total_paid),
        "balance_due": float(order.total_amount - total_paid),
        "ledger_entries": [
            {
                "date": e.transaction_date.isoformat(),
                "account": e.account_type.value,
                "amount": float(e.amount),
                "description": e.description,
            }
            for e in ledger_entries
        ],
    }

    return DataResponse(
        success=True,
        data=invoice_data,
        message="Invoice generated",
        timestamp=datetime.utcnow(),
    )


# ============================================================================
# GET /finance/receivables — Unpaid / partially paid orders (AR)
# ============================================================================

@router.get(
    "/receivables",
    response_model=DataResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="List accounts receivable (unpaid/partially paid orders)",
)
async def list_receivables(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    token: TokenPayload = Depends(RequirePermission("finance:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Returns orders in CONFIRMED, PARTIALLY_PAID, or PAID status with
    outstanding balances.  These represent money owed to the wholesaler.

    Permission: finance:read
    """
    projection = await ReceivablesService().list_receivable_orders(
        tenant_db=db, wholesaler_id=token.tenant_id, page=page, size=size,
    )
    items = [{**row, 'total_paid': row['cash_paid']} for row in projection['items']]

    return DataResponse(
        success=True,
        data={
            "items": items,
            "pagination": projection['pagination'],
        },
        timestamp=datetime.utcnow(),
    )


# ============================================================================
# GET /finance/summary — Aggregate financial summary
# ============================================================================

@router.get(
    "/summary",
    response_model=DataResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Financial summary (revenue, receivables, cash)",
)
async def get_financial_summary(
    token: TokenPayload = Depends(RequirePermission("finance:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Returns aggregated financial KPIs:
      - Total Revenue (sum of REVENUE credits)
      - Total Cash Received (sum of CASH debits)
      - Outstanding Receivables (sum of RECEIVABLE debits - credits)
      - Order counts by status

    Permission: finance:read
    """
    # --- Ledger aggregates ---
    ledger_stmt = select(
        LedgerEntry.account_type,
        func.sum(LedgerEntry.amount).label("net"),
    ).where(
        LedgerEntry.is_deleted.is_(False)
    ).group_by(
        LedgerEntry.account_type
    )
    ledger_rows = (await db.execute(ledger_stmt)).all()

    account_totals = {row.account_type: float(row.net or 0) for row in ledger_rows}

    # Revenue is stored as negative (credits), so abs() for display
    total_revenue = -account_totals.get(AccountType.REVENUE, 0)
    total_cash = account_totals.get(AccountType.CASH, 0)
    from services.finance_projection import current_finance_projection
    projection = await current_finance_projection(db, token.tenant_id)
    total_receivable = float(projection['outstanding'])

    # --- Order counts by status ---
    order_counts_stmt = select(
        Order.status,
        func.count(Order.id).label("cnt"),
    ).where(
        Order.is_deleted.is_(False)
    ).group_by(
        Order.status
    )
    order_rows = (await db.execute(order_counts_stmt)).all()
    order_counts = {row.status.value: row.cnt for row in order_rows}
    total_orders = sum(order_counts.values())

    # --- AR aging (number of unresolved receivables > 30 days) ---
    overdue_count = projection['overdue_count']

    summary = {
        "total_revenue": None if projection['currency_status'] == 'mixed' else total_revenue,
        "total_cash_received": None if projection['currency_status'] == 'mixed' else total_cash,
        "outstanding_receivables": None if projection['currency_status'] == 'mixed' else total_receivable,
        "currency": projection['currency'],
        "currency_status": projection['currency_status'],
        "outstanding_by_currency": projection['outstanding_by_currency'],
        "cash_received_by_currency": projection['cash_received_by_currency'],
        "revenue_recognition_scope": "EXISTING_LEDGER_ONLY__FULL_RECOGNITION_CONTRACT_PENDING",
        "overdue_receivables_count": overdue_count,
        "order_counts": order_counts,
        "total_orders": total_orders,
        "generated_at": datetime.utcnow().isoformat(),
    }

    return DataResponse(
        success=True,
        data=summary,
        message="Financial summary generated",
        timestamp=datetime.utcnow(),
    )


# ============================================================================
# Phase 6.2 Round 2: Receivables Visibility MVP
# ============================================================================

@router.get(
    "/receivables/summary",
    response_model=DataResponse[ReceivablesSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="Receivables summary by retailer",
)
async def get_receivables_summary(
    token: TokenPayload = Depends(RequirePermission("finance:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Returns comprehensive receivables summary by retailer:
      - total_outstanding: sum of all retailer outstanding balances
      - retailer_count: number of retailers with balances
      - order_count: total orders with receivable exposure
      - credit_receivables: total credit payment exposure
      - unpaid_order_balance: total unpaid order balances
      - by_retailer: list of per-retailer breakdowns

    Uses public.wholesaler_retailer_bindings.outstanding_balance as the
    authoritative retailer balance cache.

    Permission: finance:read
    """
    service = ReceivablesService()
    summary = await service.get_receivables_summary(
        tenant_db=db,
        wholesaler_id=token.tenant_id,
    )

    return DataResponse(
        success=True,
        data=summary,
        message="Receivables summary generated",
        timestamp=datetime.utcnow(),
    )


@router.get(
    "/receivables/orders",
    response_model=DataResponse[ReceivableOrdersResponse],
    status_code=status.HTTP_200_OK,
    summary="List orders with receivables exposure",
)
async def get_receivable_orders(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    retailer_id: str | None = Query(None, description="Filter by retailer ID"),
    classification: str | None = Query(None, description="Filter by classification: credit_receivable or unpaid_order"),
    status_filter: str | None = Query(None, alias="status", description="Filter by order status"),
    token: TokenPayload = Depends(RequirePermission("finance:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """
    Returns orders with receivables exposure, paginated and filterable.

    Query params:
      - page: page number (default 1)
      - size: items per page (default 20, max 100)
      - retailer_id: optional retailer UUID filter
      - classification: optional filter (credit_receivable or unpaid_order)
      - status: optional order status filter

    Classification definitions:
      - credit_receivable: order with credit payment exposure (may be PAID)
      - unpaid_order: confirmed/partially_paid with remaining non-credit balance

    Permission: finance:read
    """
    service = ReceivablesService()
    result = await service.list_receivable_orders(
        tenant_db=db,
        page=page,
        size=size,
        retailer_id=retailer_id,
        classification=classification,
        status=status_filter,
        wholesaler_id=token.tenant_id,
    )

    return DataResponse(
        success=True,
        data=result,
        message="Receivable orders listed",
        timestamp=datetime.utcnow(),
    )
