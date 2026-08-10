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
from dataclasses import dataclass
from datetime import date, datetime, timezone
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
    StatementMovementView,
    StatementPendingDeclarationView,
    StatementPrintView,
    StatementSettledPaymentView,
)
from repositories.statement_repository import (
    StatementInternalInconsistent,
    StatementLedgerScopeIncomplete,
    StatementPeriodError,
    StatementReconciliationFailed,
    StatementRepository,
    eat_date_range_to_utc_half_open,
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

    # R2: the ORDER itself must belong to the same wholesaler + retailer.
    # This closes the four-way consistency: declaration, payment, order, and
    # binding must all share the same (wholesaler_id, retailer_id, order_id).
    # A missing or mismatched order -> False (no partial receipt).
    from crud.order import get_order_for_wholesaler

    order = await get_order_for_wholesaler(db, str(decl_order_id), str(ws_uuid))
    if order is None:
        return False
    if str(order.retailer_id) != str(rt_uuid):
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

    R2: if ``order`` is ``None`` (missing or wrong-ownership), this returns
    ``None`` -> the route emits 404. A partial receipt with null order total
    is never produced.
    """
    if row is None or payment is None or order is None:
        return None

    rt_id = row["retailer_id"]
    ws_id = wholesaler_id
    try:
        rt_uuid = uuid.UUID(str(rt_id))
        ws_uuid = uuid.UUID(str(ws_id))
    except (TypeError, ValueError):
        return None

    # R2: the order must belong to the same wholesaler + retailer.
    if str(order.wholesaler_id) != str(ws_uuid):
        return None
    if str(order.retailer_id) != str(rt_uuid):
        return None

    supplier_name, retailer_name = await _resolve_business_names(
        db, wholesaler_id=ws_uuid, retailer_id=rt_uuid
    )

    confirmed_at = payment.get("created_at")
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


# ===========================================================================
# Contract D — relationship account statement (read-only, ledger-derived)
# ===========================================================================


@dataclass
class StatementResult:
    """Strong-typed result of ``build_statement_print``.

    Exactly one of ``view`` / ``error`` is set. ``error`` is one of the
    ``Statement*`` exception types (the route maps each to a precise HTTP status:
    period -> 404, scope/inconsistent/reconciliation -> 409). ``not_found`` is a
    plain bool for the neutral 404 (no existence disclosure) case.
    """

    view: Optional[StatementPrintView] = None
    error: Optional[Exception] = None
    not_found: bool = False


async def build_statement_print(
    db: AsyncSession,
    *,
    schema: str,
    wholesaler_id: uuid.UUID,
    retailer_id: uuid.UUID,
    date_from: date,
    date_to: date,
    include_pending: bool = False,
) -> StatementResult:
    """Assemble a printable relationship account statement (Contract D).

    ``schema`` is the trusted server/token-derived tenant schema name (never
    client input) used to explicitly qualify all tenant tables. Accepts ONLY
    the final authoritative ``wholesaler_id`` / ``retailer_id`` (server-derived;
    never a request-supplied selector). Returns a ``StatementResult`` carrying
    either the assembled view or a precise fail-closed error that the route maps
    to the correct HTTP status. No partial document is ever returned after a
    fail-closed condition.

    Accounting rules enforced:
      * opening_balance = receivable ledger sum strictly before ``date_from``.
      * movements[] = receivable ledger entries in inclusive [from, to] (EAT day
        boundary -> UTC half-open).
      * closing_balance = opening + net_movement; independently re-checked
        against a DB period sum (STATEMENT_INTERNAL_INCONSISTENT on mismatch).
      * charge_total / collection_total / net_movement derive ONLY from movements.
      * settled_payments[] = canonical completed payments (independent list).
      * orphan receivable refs -> STATEMENT_LEDGER_SCOPE_INCOMPLETE (checked first).
      * credit-only binding -> ledger receivable sum must equal cached
        outstanding_balance (STATEMENT_RECONCILIATION_FAILED on mismatch).
    """
    repo = StatementRepository()

    # 1. Validate + convert the EAT date range to a UTC half-open interval.
    try:
        start_utc, next_day_utc = eat_date_range_to_utc_half_open(date_from, date_to)
    except StatementPeriodError as exc:
        return StatementResult(error=exc)

    # 2. Active binding check (neutral 404 if not active).
    if not await _binding_active(db, wholesaler_id=wholesaler_id, retailer_id=retailer_id):
        return StatementResult(not_found=True)

    # 3. Orphan receivable precheck (rule 9) — BEFORE any balance computation.
    orphan_count = await repo.count_orphan_receivable_refs(
        db, schema=schema, wholesaler_id=wholesaler_id, retailer_id=retailer_id
    )
    if orphan_count > 0:
        return StatementResult(error=StatementLedgerScopeIncomplete())

    # 4. Opening balance (strictly before the period start).
    opening = await repo.sum_receivable_before(
        db, schema=schema, wholesaler_id=wholesaler_id, retailer_id=retailer_id, before_utc=start_utc
    )

    # 5. Movements in [start, next_day) + DB period sum.
    movement_rows, movements_period_sum = await repo.list_movements(
        db,
        schema=schema,
        wholesaler_id=wholesaler_id,
        retailer_id=retailer_id,
        start_utc=start_utc,
        next_day_utc=next_day_utc,
    )

    # 6. Independent DB period sum (rule 12) — must equal the movements sum.
    db_period_sum = await repo.sum_receivable_period(
        db,
        schema=schema,
        wholesaler_id=wholesaler_id,
        retailer_id=retailer_id,
        start_utc=start_utc,
        next_day_utc=next_day_utc,
    )
    if db_period_sum != movements_period_sum:
        return StatementResult(error=StatementInternalInconsistent())

    # 7. Derived totals from movements only.
    charge_total = sum((Decimal(r["amount"]) for r in movement_rows if Decimal(r["amount"]) > 0), Decimal("0"))
    collection_total = abs(
        sum((Decimal(r["amount"]) for r in movement_rows if Decimal(r["amount"]) < 0), Decimal("0"))
    )
    net_movement = movements_period_sum
    closing = opening + net_movement

    # 8. Settled payments (independent list; rule 5/6).
    settled_rows = await repo.list_settled_payments(
        db,
        schema=schema,
        wholesaler_id=wholesaler_id,
        retailer_id=retailer_id,
        start_utc=start_utc,
        next_day_utc=next_day_utc,
    )

    # 9. Credit/mixed classification + reconciliation (rules 11/12), using the
    #    relationship's FULL history of completed payments (not just the range).
    has_non_credit = await repo.relationship_has_non_credit_payment(
        db, schema=schema, wholesaler_id=wholesaler_id, retailer_id=retailer_id
    )
    if not has_non_credit:
        # Credit-only binding: ledger receivable total must reconcile to the
        # cached binding outstanding_balance.
        ledger_total = await repo.ledger_receivable_total(
            db, schema=schema, wholesaler_id=wholesaler_id, retailer_id=retailer_id
        )
        cached = await repo.cached_binding_balance(
            db, wholesaler_id=wholesaler_id, retailer_id=retailer_id
        )
        if cached is None or ledger_total != cached:
            return StatementResult(error=StatementReconciliationFailed())
    # Mixed relationships: print the ledger-derived balance; do NOT expose or
    # reconcile binding.outstanding_balance in the public document (rule 12).

    # 10. Optional pending/rejected declarations (non-accounting; rule 7/11).
    pending_rows: list[Mapping[str, Any]] = []
    if include_pending:
        pending_rows = await repo.list_pending_declarations(
            db,
            schema=schema,
            wholesaler_id=wholesaler_id,
            retailer_id=retailer_id,
            start_utc=start_utc,
            next_day_utc=next_day_utc,
        )

    # 11. Resolve names + assemble the view.
    supplier_name, retailer_name = await _resolve_business_names(
        db, wholesaler_id=wholesaler_id, retailer_id=retailer_id
    )
    now_utc = datetime.now(timezone.utc)
    movements = [
        StatementMovementView(
            movement_id=str(r["id"]),
            date=r["transaction_date"],
            date_eat=_to_eat(r["transaction_date"]),
            signed_amount=Decimal(r["amount"]),
            description=r.get("description"),
            reference_type=r["reference_type"],
            reference_id=str(r["reference_id"]),
        )
        for r in movement_rows
    ]
    settled = [
        StatementSettledPaymentView(
            payment_id=str(r["id"]),
            date=r["created_at"],
            date_eat=_to_eat(r["created_at"]),
            order_id=str(r["order_id"]),
            amount=Decimal(r["amount"]),
            method=r["method"],
            receipt_number=r.get("receipt_number"),
        )
        for r in settled_rows
    ]
    pending = [
        StatementPendingDeclarationView(
            declaration_id=str(r["id"]),
            order_id=str(r["order_id"]),
            declared_amount=Decimal(r["declared_amount"]),
            method=r["method"],
            status=r["status"],
            submitted_at=r["submitted_at"],
            submitted_at_eat=_to_eat(r["submitted_at"]),
            transfer_reference=r.get("transfer_reference"),
        )
        for r in pending_rows
    ]

    view = StatementPrintView(
        supplier_name=supplier_name,
        retailer_name=retailer_name,
        period_from=date_from,
        period_to=date_to,
        opening_balance=opening,
        closing_balance=closing,
        charge_total=charge_total,
        collection_total=collection_total,
        net_movement=net_movement,
        movements=movements,
        settled_payments=settled,
        pending_declarations=pending,
        generated_at=now_utc,
        generated_at_eat=_to_eat(now_utc),
    )
    return StatementResult(view=view)
