"""
Receivables Service - Read-only receivables visibility for Phase 6.2 Round 2.

This service provides READ-ONLY access to accounts receivable data:
- Retailer summary with outstanding balances
- Order-level receivables breakdown
- Credit vs unpaid order classification

NO mutations to payments, orders, ledger_entries, or bindings.
NO collection recording (Round 3 scope).

Uses public.wholesaler_retailer_bindings.outstanding_balance as the
authoritative retailer balance cache.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import select, func, case, text, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models.order import Order, OrderStatus
from models.ledger import LedgerEntry, AccountType


class ReceivablesService:
    """Read-only receivables visibility service."""

    def __init__(self) -> None:
        pass

    async def get_receivables_summary(
        self,
        *,
        tenant_db: AsyncSession,
    ) -> dict[str, Any]:
        """
        Generate comprehensive receivables summary by retailer.

        Returns:
            Dict with:
            - total_outstanding: sum of all retailer outstanding balances
            - retailer_count: number of retailers with balances
            - order_count: total orders with receivable exposure
            - credit_receivables: total credit payment exposure
            - unpaid_order_balance: total unpaid order balances
            - by_retailer: list of per-retailer breakdowns

        Raises:
            Exception: Database query errors (read-only, no rollback needed)
        """
        # Query 1: Get all retailers with their binding balances from public schema
        binding_result = await tenant_db.execute(
            text(
                """
                SELECT
                    wrb.retailer_id,
                    wrb.outstanding_balance,
                    r.name as retailer_name
                FROM public.wholesaler_retailer_bindings wrb
                JOIN public.retailers r ON r.id = wrb.retailer_id
                WHERE wrb.is_deleted IS FALSE
                  AND wrb.outstanding_balance != 0
                ORDER BY wrb.outstanding_balance DESC
                """
            )
        )
        binding_rows = binding_result.mappings().all()

        if not binding_rows:
            return {
                "total_outstanding": 0.0,
                "retailer_count": 0,
                "order_count": 0,
                "credit_receivables": 0.0,
                "unpaid_order_balance": 0.0,
                "by_retailer": [],
            }

        retailer_ids = [row["retailer_id"] for row in binding_rows]
        retailer_data = {row["retailer_id"]: row for row in binding_rows}

        # Query 2: Get all orders for these retailers to build breakdown
        orders_result = await tenant_db.execute(
            select(
                Order.retailer_id,
                Order.id,
                Order.status,
                Order.total_amount,
                Order.created_at,
            )
            .where(Order.retailer_id.in_(retailer_ids))
            .where(Order.is_deleted.is_(False))
            .order_by(Order.retailer_id, Order.created_at.desc())
        )
        order_rows = orders_result.all()

        # Query 3: Get credit payment totals per order (exclude from paid calculation)
        credit_totals_result = await tenant_db.execute(
            text(
                """
                SELECT
                    order_id,
                    COALESCE(SUM(amount), 0) as credit_total
                FROM payments
                WHERE order_id = ANY(:order_ids)
                  AND is_deleted IS FALSE
                  AND method = 'credit'
                GROUP BY order_id
                """
            ),
            {"order_ids": [order.id for order in order_rows]},
        )
        credit_totals = {row["order_id"]: Decimal(str(row["credit_total"])) for row in credit_totals_result.mappings().all()}

        # Query 4: Get cash/transfer payment totals per order
        cash_totals_result = await tenant_db.execute(
            text(
                """
                SELECT
                    order_id,
                    COALESCE(SUM(amount), 0) as cash_total
                FROM payments
                WHERE order_id = ANY(:order_ids)
                  AND is_deleted IS FALSE
                  AND method IN ('cash', 'transfer')
                GROUP BY order_id
                """
            ),
            {"order_ids": [order.id for order in order_rows]},
        )
        cash_totals = {row["order_id"]: Decimal(str(row["cash_total"])) for row in cash_totals_result.mappings().all()}

        # Build per-retailer breakdown
        by_retailer = []
        total_outstanding = Decimal("0")
        total_credit_receivables = Decimal("0")
        total_unpaid_balance = Decimal("0")
        total_order_count = 0

        for retailer_id in retailer_ids:
            binding_info = retailer_data[retailer_id]
            retailer_orders = [o for o in order_rows if o.retailer_id == retailer_id]

            retailer_credit = Decimal("0")
            retailer_unpaid = Decimal("0")

            for order in retailer_orders:
                order_id = order.id
                credit_amt = credit_totals.get(order_id, Decimal("0"))
                cash_amt = cash_totals.get(order_id, Decimal("0"))
                balance_due = order.total_amount - cash_amt

                # Credit receivable: orders with credit payment exposure
                if credit_amt > 0:
                    retailer_credit += credit_amt

                # Unpaid order: confirmed/partially_paid with remaining balance
                if order.status in [OrderStatus.CONFIRMED, OrderStatus.PARTIALLY_PAID] and balance_due > 0:
                    retailer_unpaid += balance_due

            by_retailer.append({
                "retailer_id": str(binding_info["retailer_id"]),
                "retailer_name": binding_info["retailer_name"] or "Unknown",
                "outstanding_balance": float(binding_info["outstanding_balance"]),
                "credit_receivables": float(retailer_credit),
                "unpaid_order_balance": float(retailer_unpaid),
                "order_count": len(retailer_orders),
            })

            total_outstanding += binding_info["outstanding_balance"]
            total_credit_receivables += retailer_credit
            total_unpaid_balance += retailer_unpaid
            total_order_count += len(retailer_orders)

        return {
            "total_outstanding": float(total_outstanding),
            "retailer_count": len(by_retailer),
            "order_count": total_order_count,
            "credit_receivables": float(total_credit_receivables),
            "unpaid_order_balance": float(total_unpaid_balance),
            "by_retailer": by_retailer,
        }

    async def list_receivable_orders(
        self,
        *,
        tenant_db: AsyncSession,
        page: int = 1,
        size: int = 20,
        retailer_id: str | None = None,
        classification: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """
        List orders with receivables exposure, paginated and filterable.

        Args:
            tenant_db: AsyncSession for tenant schema
            page: Page number (1-based)
            size: Page size (1-100)
            retailer_id: Optional retailer UUID filter
            classification: Optional filter - 'credit_receivable' or 'unpaid_order'
            status: Optional order status filter

        Returns:
            Dict with:
            - items: list of order dicts with receivables details
            - pagination: page metadata

        Classification definitions:
            - credit_receivable: order with credit payment exposure (may be PAID)
            - unpaid_order: confirmed/partially_paid with remaining non-credit balance
        """
        # Build base query for orders with potential receivables
        # Include PAID orders because they may have credit receivables
        receivable_statuses = [
            OrderStatus.CONFIRMED,
            OrderStatus.PARTIALLY_PAID,
            OrderStatus.PAID,
        ]

        # Build filters
        filters = [Order.is_deleted.is_(False), Order.status.in_(receivable_statuses)]

        if retailer_id:
            try:
                retailer_uuid = uuid.UUID(retailer_id)
                filters.append(Order.retailer_id == retailer_uuid)
            except ValueError:
                return {"items": [], "pagination": {"page": 1, "size": size, "total": 0, "pages": 0}}

        if status:
            try:
                status_enum = OrderStatus(status)
                filters.append(Order.status == status_enum)
            except ValueError:
                return {"items": [], "pagination": {"page": 1, "size": size, "total": 0, "pages": 0}}

        # Count query
        count_stmt = select(func.count(Order.id)).where(*filters)
        total = int((await tenant_db.execute(count_stmt)).scalar() or 0)

        # Calculate pagination
        import math
        pages = math.ceil(total / size) if total > 0 else 0
        offset = (page - 1) * size

        # Fetch orders
        orders_stmt = (
            select(Order)
            .where(*filters)
            .order_by(Order.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        order_rows = (await tenant_db.execute(orders_stmt)).scalars().all()

        if not order_rows:
            return {
                "items": [],
                "pagination": {"page": page, "size": size, "total": total, "pages": pages},
            }

        order_ids = [order.id for order in order_rows]

        # Fetch payment totals
        credit_result = await tenant_db.execute(
            text(
                """
                SELECT
                    order_id,
                    COALESCE(SUM(amount), 0) as credit_total
                FROM payments
                WHERE order_id = ANY(:order_ids)
                  AND is_deleted IS FALSE
                  AND method = 'credit'
                GROUP BY order_id
                """
            ),
            {"order_ids": order_ids},
        )
        credit_totals = {row["order_id"]: Decimal(str(row["credit_total"])) for row in credit_result.mappings().all()}

        cash_result = await tenant_db.execute(
            text(
                """
                SELECT
                    order_id,
                    COALESCE(SUM(amount), 0) as cash_total
                FROM payments
                WHERE order_id = ANY(:order_ids)
                  AND is_deleted IS FALSE
                  AND method IN ('cash', 'transfer')
                GROUP BY order_id
                """
            ),
            {"order_ids": order_ids},
        )
        cash_totals = {row["order_id"]: Decimal(str(row["cash_total"])) for row in cash_result.mappings().all()}

        # Get retailer names from public bindings
        retailer_ids = list(set([order.retailer_id for order in order_rows]))
        retailer_result = await tenant_db.execute(
            text(
                """
                SELECT
                    wrb.retailer_id,
                    r.name as retailer_name
                FROM public.wholesaler_retailer_bindings wrb
                JOIN public.retailers r ON r.id = wrb.retailer_id
                WHERE wrb.retailer_id = ANY(:retailer_ids)
                  AND wrb.is_deleted IS FALSE
                """
            ),
            {"retailer_ids": retailer_ids},
        )
        retailer_names = {row["retailer_id"]: row["retailer_name"] for row in retailer_result.mappings().all()}

        # Build items with classification
        items = []
        now = datetime.utcnow()

        for order in order_rows:
            order_id = order.id
            credit_amt = credit_totals.get(order_id, Decimal("0"))
            cash_amt = cash_totals.get(order_id, Decimal("0"))
            balance_due = order.total_amount - cash_amt

            # Determine classification
            order_classification = None
            if credit_amt > 0:
                order_classification = "credit_receivable"
            elif balance_due > 0 and order.status in [OrderStatus.CONFIRMED, OrderStatus.PARTIALLY_PAID]:
                order_classification = "unpaid_order"

            # Apply classification filter
            if classification and order_classification != classification:
                continue

            # Determine primary payment method (highest amount)
            payment_method = "unknown"
            if credit_amt >= cash_amt and credit_amt > 0:
                payment_method = "credit"
            elif cash_amt > 0:
                payment_method = "cash"  # Represents cash or transfer

            age_days = (now - order.created_at).days if order.created_at else 0

            # Handle both enum and string status values
            status_value = order.status.value if hasattr(order.status, "value") else order.status

            items.append({
                "order_id": str(order_id),
                "retailer_id": str(order.retailer_id),
                "retailer_name": retailer_names.get(order.retailer_id, "Unknown"),
                "status": status_value,
                "classification": order_classification,
                "payment_method": payment_method,
                "total_amount": float(order.total_amount),
                "cash_paid": float(cash_amt),
                "credit_amount": float(credit_amt),
                "balance_due": float(balance_due),
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "age_days": age_days,
            })

        # Recalculate total after classification filter
        if classification:
            total = len(items)
            pages = math.ceil(total / size) if total > 0 else 0

        return {
            "items": items,
            "pagination": {
                "page": page,
                "size": size,
                "total": total,
                "pages": pages,
            },
        }
