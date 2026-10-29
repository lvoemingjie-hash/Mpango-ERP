"""Bounded read-only cashier and current-retailer projections.

Business facts are read in one statement snapshot, never through a writer.
The existing permission dependency retains its short authority shared lock.
"""
from __future__ import annotations

from datetime import timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text

from services.payment_history_contract import _INVALID_ROW_PREDICATE
from services.pricing_quote_service import CURRENCY_SCALE, amount_string, money


REVIEWABLE_ORDER_STATES = frozenset({"confirmed", "partially_paid", "paid", "fulfilled"})
ORDER_STATES = REVIEWABLE_ORDER_STATES | {"draft", "cancelled", "voided", "returned"}


def _refuse(status: int, code: str, message: str):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


def validate_context(token, tenant):
    """Validate server-owned canonical context before interpolating a schema."""
    try:
        wid, uid = UUID(str(token.tenant_id)), UUID(str(token.user_id))
        schema = "t_" + wid.hex
        valid = (str(tenant.tenant_id) == str(wid)
                 and token.tenant_schema == tenant.tenant_schema == schema
                 and str(tenant.user.id) == str(uid))
    except (TypeError, ValueError, AttributeError):
        valid = False
    if not valid:
        _refuse(403, "TENANT_CONTEXT_REQUIRED", "A current trading context is required")
    return wid, uid, schema


def reject_selectors(request):
    if request.query_params:
        _refuse(400, "INVALID_CONTEXT_SELECTOR", "Context selectors are not accepted")


def _name_view(identifier, value):
    cleaned = value.strip() if isinstance(value, str) else ""
    return {"id": str(identifier), "name": cleaned or None,
            "name_resolution": "RESOLVED" if cleaned else "MISSING"}


def _decimal(value, *, positive=False):
    try:
        if not isinstance(value, Decimal):
            raise ValueError
        if not value.is_finite() or value < 0 or (positive and value == 0):
            raise ValueError
        return value
    except (ValueError, InvalidOperation):
        _refuse(409, "REVIEW_CONTEXT_INTEGRITY", "Review amounts are inconsistent")


def _exact_money(value, currency, *, positive=False):
    value = _decimal(value, positive=positive)
    if currency in CURRENCY_SCALE:
        try:
            return amount_string(money(value, currency, positive=positive), currency)
        except HTTPException:
            _refuse(409, "REVIEW_CONTEXT_INTEGRITY", "Review precision is inconsistent")
    return format(value, "f")


_CASHIER_QUERY = """
SELECT d.id AS declaration_id, d.order_id, d.status AS declaration_status,
       d.declared_amount, d.method, d.transfer_reference,
       o.status::text AS order_status, o.total_amount, o.currency_snapshot,
       w.id AS wholesaler_id, w.code AS supplier_code, w.name AS supplier_name,
       r.id AS retailer_id, r.name AS retailer_name, b.id AS binding_id,
       COUNT(*) OVER () AS visible_count, statement_timestamp() AS observed_at,
       pstats.paid_total, pstats.credit_total, pstats.credit_rows,
       pstats.invalid_rows, pstats.precision_rows,
       hstats.hold_count, hstats.hold_status, hstats.hold_amount, hstats.hold_remaining
FROM payment_declarations d
JOIN orders o ON o.id=d.order_id AND o.wholesaler_id=d.wholesaler_id
             AND o.retailer_id=d.retailer_id AND o.is_deleted IS FALSE
JOIN public.wholesalers w ON w.id=d.wholesaler_id
                          AND w.is_deleted IS FALSE AND w.status='active'
JOIN public.retailers r ON r.id=d.retailer_id AND r.is_deleted IS FALSE
JOIN public.wholesaler_retailer_bindings b ON b.wholesaler_id=w.id
     AND b.retailer_id=r.id AND b.is_deleted IS FALSE AND b.status='active'
LEFT JOIN LATERAL (
    SELECT COALESCE(SUM(p.amount) FILTER (WHERE p.method IN ('cash', 'transfer')), 0) AS paid_total,
           COALESCE(SUM(p.amount) FILTER (WHERE p.method='credit'), 0) AS credit_total,
           COUNT(*) FILTER (WHERE p.method='credit') AS credit_rows,
           COUNT(*) FILTER (WHERE ({invalid_predicate})) AS invalid_rows,
           COUNT(*) FILTER (WHERE (o.currency_snapshot='UGX' AND p.amount<>trunc(p.amount,0))
                              OR (o.currency_snapshot='KES' AND p.amount<>trunc(p.amount,2))) AS precision_rows
    FROM payments p WHERE p.order_id=o.id AND p.is_deleted IS FALSE
) pstats ON TRUE
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS hold_count, MIN(h.status) AS hold_status,
           MIN(h.amount) AS hold_amount, MIN(h.remaining_amount) AS hold_remaining
    FROM order_credit_holds h WHERE h.order_id=o.id
) hstats ON TRUE
WHERE d.id=:declaration_id AND d.wholesaler_id=:wholesaler_id
""".format(invalid_predicate=_INVALID_ROW_PREDICATE)


def _balance(row, total, paid, credit):
    balance = total - paid
    if balance < 0 or (credit > 0 and (credit != total or row["credit_rows"] != 1)):
        _refuse(409, "REVIEW_CONTEXT_INTEGRITY", "Review history is inconsistent")
    if row["order_status"] not in REVIEWABLE_ORDER_STATES:
        return None
    if row["hold_count"] != 1:
        _refuse(409, "REVIEW_CONTEXT_INTEGRITY", "Review hold is inconsistent")
    amount = _decimal(row["hold_amount"], positive=True)
    remaining = _decimal(row["hold_remaining"])
    if amount != total:
        _refuse(409, "REVIEW_CONTEXT_INTEGRITY", "Review hold is inconsistent")
    state = row["order_status"]
    if state in {"confirmed", "partially_paid"}:
        valid = (credit == 0 and row["hold_status"] == "active"
                 and remaining == balance and remaining > 0)
    elif credit > 0:
        valid = row["hold_status"] == "converted" and remaining == 0
    else:
        valid = row["hold_status"] == "settled" and remaining == 0 and balance == 0
    if not valid:
        _refuse(409, "REVIEW_CONTEXT_INTEGRITY", "Review hold is inconsistent")
    return balance


async def read_cashier_declaration_context(db, *, wholesaler_id, user_id, declaration_id):
    rows = (await db.execute(text(_CASHIER_QUERY), {
        "declaration_id": declaration_id, "wholesaler_id": wholesaler_id,
    })).mappings().all()
    if len(rows) != 1 or rows[0]["visible_count"] != 1:
        _refuse(404, "DECLARATION_NOT_FOUND", "Declaration not found")
    row = rows[0]
    if row["invalid_rows"]:
        _refuse(409, "PAYMENT_HISTORY_INTEGRITY", "Payment history is inconsistent")
    currency = row["currency_snapshot"]
    known = currency in CURRENCY_SCALE
    total = _decimal(row["total_amount"], positive=True)
    paid = _decimal(row["paid_total"])
    credit = _decimal(row["credit_total"])
    if (row["precision_rows"] or row["order_status"] not in ORDER_STATES
            or row["declaration_status"] not in {"pending", "confirmed", "rejected"}
            or row["method"] not in {"cash", "transfer"}):
        _refuse(409, "REVIEW_CONTEXT_INTEGRITY", "Review history is inconsistent")
    declared = _exact_money(row["declared_amount"], currency, positive=True)
    for value in (total, paid, credit):
        _exact_money(value, currency)
    raw_balance = _balance(row, total, paid, credit)
    balance = _exact_money(raw_balance, currency) if known and raw_balance is not None else None
    supplier = {**_name_view(row["wholesaler_id"], row["supplier_name"]),
                "code": row["supplier_code"]}
    retailer = _name_view(row["retailer_id"], row["retailer_name"])
    if not supplier["code"]:
        _refuse(409, "REVIEW_CONTEXT_INTEGRITY", "Supplier identity is inconsistent")
    nonaction, unresolved = [], []
    if row["declaration_status"] != "pending":
        nonaction.append("DECLARATION_NOT_PENDING")
    if row["order_status"] not in REVIEWABLE_ORDER_STATES:
        nonaction.append("ORDER_STATE_NOT_REVIEWABLE")
    if known and raw_balance is not None:
        if raw_balance == 0:
            nonaction.append("NO_REMAINING_BALANCE")
        elif row["declared_amount"] > raw_balance:
            nonaction.append("DECLARATION_EXCEEDS_BALANCE")
    if any(party["name_resolution"] != "RESOLVED" for party in (supplier, retailer)):
        unresolved.append("NAME_UNRESOLVED")
    if not known:
        unresolved.append("CURRENCY_UNVERIFIED")
    if row["method"] == "transfer" and not (row["transfer_reference"] or "").strip():
        unresolved.append("TRANSFER_REFERENCE_MISSING")
    state = "NOT_ACTIONABLE" if nonaction else "UNRESOLVED" if unresolved else "READY"
    return {
        "context": {"tenant_id": str(wholesaler_id), "user_id": str(user_id)},
        "declaration": {"id": str(row["declaration_id"]), "order_id": str(row["order_id"]),
                        "status": row["declaration_status"], "declared_amount": declared,
                        "method": row["method"], "transfer_reference": row["transfer_reference"]},
        "order": {"id": str(row["order_id"]), "status": row["order_status"]},
        "supplier": supplier, "retailer": retailer,
        "binding": {"id": str(row["binding_id"]), "status": "active"},
        "money": {"currency": currency if known else None,
                  "currency_status": "KNOWN" if known else "LEGACY_CURRENCY_UNVERIFIED" if currency is None else "UNSUPPORTED",
                  "balance_due": balance, "balance_status": "VERIFIED" if balance is not None else "UNVERIFIED"},
        "review_state": state, "reason_codes": nonaction + unresolved,
        "observed_at": row["observed_at"].astimezone(timezone.utc),
    }


async def read_client_portal_context(db, *, wholesaler_id, user_id, retailer_id, schema):
    # schema was derived from the verified tenant UUID, never a selector.
    rows = (await db.execute(text(f"""
        SELECT w.id AS wholesaler_id,w.code,w.name AS supplier_name,
               r.id AS retailer_id,r.name AS retailer_name,b.id AS binding_id,
               COUNT(*) OVER () AS visible_count,statement_timestamp() AS observed_at
        FROM public.wholesaler_retailer_bindings b
        JOIN public.wholesalers w ON w.id=b.wholesaler_id
             AND w.is_deleted IS FALSE AND w.status='active'
        JOIN public.retailers r ON r.id=b.retailer_id AND r.is_deleted IS FALSE
        JOIN "{schema}".users u ON u.id=b.tenant_user_id
             AND u.is_active IS TRUE AND u.is_deleted IS FALSE
        WHERE b.wholesaler_id=:wid AND b.tenant_user_id=:uid AND b.retailer_id=:rid
          AND b.is_deleted IS FALSE AND b.status='active'
          AND EXISTS (SELECT 1 FROM "{schema}".user_roles ur
                      JOIN "{schema}".roles role ON role.id=ur.role_id
                      WHERE ur.user_id=u.id AND role.name='retailer_operator'
                        AND role.is_deleted IS FALSE)
    """), {"wid": wholesaler_id, "uid": user_id, "rid": retailer_id})).mappings().all()
    if len(rows) != 1 or rows[0]["visible_count"] != 1:
        _refuse(403, "PORTAL_CONTEXT_UNAVAILABLE", "Current portal context is unavailable")
    row = rows[0]
    if not row["code"]:
        _refuse(403, "PORTAL_CONTEXT_UNAVAILABLE", "Current portal context is unavailable")
    return {
        "context": {"tenant_id": str(wholesaler_id), "user_id": str(user_id)},
        "supplier": {**_name_view(row["wholesaler_id"], row["supplier_name"]), "code": row["code"]},
        "retailer": _name_view(row["retailer_id"], row["retailer_name"]),
        "binding": {"id": str(row["binding_id"]), "status": "active"},
        "observed_at": row["observed_at"].astimezone(timezone.utc),
    }
