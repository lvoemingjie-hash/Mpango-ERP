"""
DC-12R1-S3-S2B-I2C-I1 — Read-only printable record service (Contracts A-C).

Provides server-authoritative, read-only assembly of printable documents:
  A. Order document
  B. Payment declaration document
  C. Confirmed receipt

Binding truth contract (I2C-D/R2):
- 100% read-only. No writes to any table. No receipt allocation. No events.
- Authority is never client-supplied: ``wholesaler_id`` and ``retailer_id``
  come from the contextual JWT + active binding.
- Receipt eligibility is a fail-closed render-time predicate. Any failure
  returns ``None`` (the route maps that to a neutral 404).
- No persisted key links a ledger movement to a payment; receipt content is
  sourced only from the canonical payment joined via
  ``confirmation_payment_id``.
- Timestamps: authoritative UTC + fixed ``Africa/Nairobi`` (EAT) display.

This service performs **no mutation** and raises no exception on
not-found/ineligible — it returns ``None`` so callers can emit a neutral 404
without existence disclosure.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.client import map_order_status_for_client
from schemas.print import (
    DeclarationPrintView,
    OrderPrintView,
    PrintOrderItemView,
    ReceiptPrintView,
)

# Receipt number canonical format — must match canonical_payment_service.py:61-67.
_RECEIPT_NUMBER_PATTERN = re.compile(r"^RCT-[0-9]{8}-[0-9]{6}$")

# Fixed MVP display timezone (no tenant-configurable timezone exists).
_EAT_TZNAME = "Africa/Nairobi"
_EAT_UTC_OFFSET_HOURS = 3


def _to_eat(utc_dt: Optional[datetime]) -> Optional[datetime]:
    """Convert an aware (or naive-assumed-UTC) datetime to fixed EAT display.

    Returns ``None`` if input is ``None``. Does not query any tenant config.
    """
    if utc_dt is None:
        return None
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    from datetime import timedelta

    return utc_dt.astimezone(timezone(timedelta(hours=_EAT_UTC_OFFSET_HOURS), _EAT_TZNAME))


def _safe_name(value: Optional[str], fallback: str) -> str:
    """Return a display-safe business name; never expose a UUID."""
    if value is None:
        return fallback
    cleaned = str(value).strip()
    return cleaned if cleaned else fallback


async def _resolve_business_names(
    db: AsyncSession,
    *,
    wholesaler_id: uuid.UUID,
    retailer_id: uuid.UUID,
) -> tuple[str, str]:
    """Resolve supplier (wholesaler) and retailer business names from public schema.

    Names are display-only; a missing name yields a controlled placeholder,
    never a UUID.
    """
    ws_row = (
        await db.execute(
            text("SELECT name FROM public.wholesalers WHERE id = :wid"),
            {"wid": wholesaler_id},
        )
    ).first()
    rt_row = (
        await db.execute(
            text("SELECT name FROM public.retailers WHERE id = :rid"),
            {"rid": retailer_id},
        )
    ).first()
    supplier_name = _safe_name(ws_row.name if ws_row else None, "Supplier")
    retailer_name = _safe_name(rt_row.name if rt_row else None, "Retailer")
    return supplier_name, retailer_name


async def _binding_active(
    db: AsyncSession,
    *,
    wholesaler_id: uuid.UUID,
    retailer_id: uuid.UUID,
) -> bool:
    """True iff the relationship binding is active and non-deleted."""
    row = (
        await db.execute(
            text(
                "SELECT status FROM public.wholesaler_retailer_bindings "
                "WHERE wholesaler_id = :wid AND retailer_id = :rid "
                "AND is_deleted IS FALSE LIMIT 1"
            ),
            {"wid": wholesaler_id, "rid": retailer_id},
        )
    ).first()
    return row is not None and row.status == "active"


# ---------------------------------------------------------------------------
# Contract A — Order document
# ---------------------------------------------------------------------------


async def build_order_print(
    db: AsyncSession,
    *,
    order,  # Order ORM object (already dual-key scoped by the caller)
    wholesaler_id: uuid.UUID,
    retailer_id: uuid.UUID,
) -> Optional[OrderPrintView]:
    """Assemble a printable order document from a server-authoritative order row.

    The caller is responsible for dual-key scoping (``get_order_for_retailer``
    or ``get_order_by_id``); this function only reads names and maps the view.
    Returns ``None`` only if the order is falsy (defensive).
    """
    if order is None:
        return None

    supplier_name, retailer_name = await _resolve_business_names(
        db, wholesaler_id=wholesaler_id, retailer_id=retailer_id
    )

    items = [
        PrintOrderItemView(
            product_name=item.product_name,
            sku_code=item.sku_code,
            quantity=item.quantity,
            unit_price=item.unit_price,
            subtotal=item.subtotal,
        )
        for item in (order.items or [])
    ]

    return OrderPrintView(
        order_id=str(order.id),
        status=map_order_status_for_client(order.status.value),
        supplier_name=supplier_name,
        retailer_name=retailer_name,
        items=items,
        total_amount=order.total_amount,
        item_count=len(items),
        notes=order.notes,
        created_at=order.created_at,
        created_at_eat=_to_eat(order.created_at),
    )


# ---------------------------------------------------------------------------
# Contract B — Payment declaration document
# ---------------------------------------------------------------------------

_PENDING_NOTICE = (
    "Payment Declaration — Not Received. This declaration has not been "
    "confirmed and is not a receipt. It does not prove that payment was "
    "received or settled."
)
_REJECTED_NOTICE = (
    "Payment Declaration — Rejected. This declaration was not confirmed and "
    "is not a receipt."
)


async def build_declaration_print(
    db: AsyncSession,
    *,
    row: Mapping[str, Any],
    wholesaler_id: uuid.UUID,
    retailer_id: uuid.UUID,
    receipt_eligible: bool = False,
) -> Optional[DeclarationPrintView]:
    """Assemble a printable payment declaration document.

    ``row`` is the joined detail row from
    ``PaymentDeclarationRepository.get_detail_by_*``. Pending/rejected carry a
    prominent non-receipt notice; confirmed delegates receipt rendering to the
    caller (receipt eligibility is checked separately).

    R1 correction: a confirmed declaration is **not** automatically a receipt.
    The caller must pass ``receipt_eligible`` (computed via
    ``check_receipt_eligibility``). If the declaration is confirmed but NOT
    receipt-eligible (missing/invalid/deleted payment, bad receipt number,
    inactive binding), this function returns ``None`` so the route emits a
    neutral 404 — it never renders a confirmed declaration with
    ``is_receipt=True`` unless the full eligibility predicate passes.
    """
    if row is None:
        return None

    rt_id = row["retailer_id"] if "retailer_id" in row else retailer_id
    ws_id = row["wholesaler_id"] if "wholesaler_id" in row else wholesaler_id
    supplier_name, retailer_name = await _resolve_business_names(
        db, wholesaler_id=ws_id, retailer_id=rt_id
    )

    status = row["status"]

    # R1: confirmed-but-ineligible must fail closed (return None -> 404).
    if status == "confirmed" and not receipt_eligible:
        return None

    is_receipt = status == "confirmed" and receipt_eligible
    non_receipt_notice: Optional[str] = None
    rejection_reason: Optional[str] = None
    if status == "pending":
        non_receipt_notice = _PENDING_NOTICE
    elif status == "rejected":
        non_receipt_notice = _REJECTED_NOTICE
        reason = row.get("reason")
        rejection_reason = str(reason).strip() if reason else None

    return DeclarationPrintView(
        declaration_id=str(row["id"]),
        order_id=str(row["order_id"]),
        supplier_name=supplier_name,
        retailer_name=retailer_name,
        status=status,
        declared_amount=row["declared_amount"],
        method=row["method"],
        transfer_reference=row.get("transfer_reference"),
        is_receipt=is_receipt,
        non_receipt_notice=non_receipt_notice,
        rejection_reason=rejection_reason,
        submitted_at=row["submitted_at"],
        submitted_at_eat=_to_eat(row["submitted_at"]),
        confirmed_at=row.get("confirmed_at"),
        confirmed_at_eat=_to_eat(row.get("confirmed_at")),
        rejected_at=row.get("rejected_at"),
        rejected_at_eat=_to_eat(row.get("rejected_at")),
        order_status=str(row["order_status"]) if row.get("order_status") is not None else None,
    )


# ---------------------------------------------------------------------------
# Contract C — Confirmed receipt (receipt eligibility predicate)
# ---------------------------------------------------------------------------


async def check_receipt_eligibility(
    db: AsyncSession,
    *,
    row: Mapping[str, Any],
    wholesaler_id: uuid.UUID,
) -> bool:
    """Fail-closed receipt eligibility predicate (I2C-D §7.1).

    Returns ``True`` iff ALL hold:
      1. ``declaration.status == 'confirmed'``
      2. ``confirmation_payment_id`` is non-null
      3. the joined payment exists and ``is_deleted IS FALSE``
      4. ``payment.status == 'completed'``
      5. ``receipt_number`` matches ``^RCT-[0-9]{8}-[0-9]{6}$``
      6. the relationship binding is active and non-deleted

    Any failure returns ``False`` (the route emits a neutral 404). This never
    allocates or repairs a receipt.
    """
    if row is None:
        return False
    if row.get("status") != "confirmed":
        return False
    cpid = row.get("confirmation_payment_id")
    if cpid is None:
        return False
    try:
        payment_id = uuid.UUID(str(cpid))
    except (TypeError, ValueError):
        return False

    # Fetch the canonical payment row (with receipt_number), scoped to
    # non-deleted. This is a read; no allocation.
    from repositories.payment_repository import PaymentRepository

    payment = await PaymentRepository().get_by_id_with_receipt(db, payment_id=payment_id)
    if payment is None:
        return False
    if payment.get("status") != "completed":
        return False

    # R1: the payment must belong to the SAME order and retailer as the
    # declaration. Without this, a corrupted confirmation_payment_id could
    # cross-associate declaration A with payment B's amount/receipt.
    decl_order_id = str(row["order_id"])
    decl_retailer_id = str(row["retailer_id"])
    pay_order_id = str(payment["order_id"]) if payment.get("order_id") is not None else None
    pay_retailer_id = str(payment["retailer_id"]) if payment.get("retailer_id") is not None else None
    if pay_order_id is None or pay_order_id != decl_order_id:
        return False
    if pay_retailer_id is None or pay_retailer_id != decl_retailer_id:
        return False

    receipt_number = payment.get("receipt_number")
    if not receipt_number or not _RECEIPT_NUMBER_PATTERN.match(str(receipt_number)):
        return False

    # Active, non-deleted binding for this relationship.
    retailer_id = row["retailer_id"]
    try:
        rt_uuid = uuid.UUID(str(retailer_id))
        ws_uuid = uuid.UUID(str(wholesaler_id))
    except (TypeError, ValueError):
        return False
    if not await _binding_active(db, wholesaler_id=ws_uuid, retailer_id=rt_uuid):
        return False

    return True


async def build_receipt_print(
    db: AsyncSession,
    *,
    row: Mapping[str, Any],
    payment: Mapping[str, Any],
    order,
    wholesaler_id: uuid.UUID,
) -> Optional[ReceiptPrintView]:
    """Assemble a confirmed-receipt document.

    Only called after ``check_receipt_eligibility`` returns ``True``. The
    receipt identity comes from the canonical payment (``receipt_number``,
    ``amount``, ``method``, ``created_at``); the declaration supplies context
    (``declared_amount``, ``order_id``); the order supplies the total.
    """
    if row is None or payment is None:
        return None

    rt_id = row["retailer_id"]
    ws_id = wholesaler_id
    try:
        rt_uuid = uuid.UUID(str(rt_id))
        ws_uuid = uuid.UUID(str(ws_id))
    except (TypeError, ValueError):
        return None

    supplier_name, retailer_name = await _resolve_business_names(
        db, wholesaler_id=ws_uuid, retailer_id=rt_uuid
    )

    confirmed_at = payment.get("created_at")
    order_total = None
    order_status = None
    if order is not None:
        order_total = order.total_amount
        order_status = map_order_status_for_client(order.status.value)

    return ReceiptPrintView(
        declaration_id=str(row["id"]),
        order_id=str(row["order_id"]),
        supplier_name=supplier_name,
        retailer_name=retailer_name,
        receipt_number=str(payment["receipt_number"]),
        confirmed_amount=Decimal(payment["amount"]),
        method=payment["method"],
        confirmed_at=confirmed_at,
        confirmed_at_eat=_to_eat(confirmed_at),
        declared_amount=Decimal(row["declared_amount"]),
        order_status=order_status,
        order_total_amount=order_total,
    )
