"""R2 credit-hold test support.

Hold-row helpers degrade to explicit "gap" markers when the
``order_credit_holds`` table does not exist (the parent-commit state): a
missing table means the product persists NO per-order lifecycle, so the
business assertions observe an empty/absent hold set and fail with a named
product-RED message. No assertion is weakened: once the table exists every
shape check runs for real and tampering helpers return True.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

# Re-export the R1 fact vectors so R2 tests read persisted truth the same way.
from tests.order_state_r1.support import (  # noqa: F401
    binding_balance,
    errcode,
    http_action,
    http_create_order,
    inventory_vector,
    make_bound_retailer,
    order_vector,
    osd1_cashier_token,
    payment_ledger_vector,
    reservation_vector,
    seed_sku_with_stock,
)

HOLD_COLUMNS = {
    "id", "order_id", "amount", "remaining_amount", "status",
    "created_at", "updated_at", "created_by", "updated_by",
}


def _is_undefined_table(exc: Exception) -> bool:
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return code == "42P01"


async def fetch_holds(db: AsyncSession, schema: str, order_id: str) -> list[dict[str, Any]]:
    """Return the order's lifecycle rows ordered by id. Empty list when the
    product has no hold table at all (parent-commit gap)."""
    try:
        rows = (await db.execute(text(
            f'SELECT id, order_id, amount, remaining_amount, status, '
            f'created_by, updated_by FROM "{schema}".order_credit_holds '
            "WHERE order_id = :oid ORDER BY id"),
            {"oid": order_id})).mappings().all()
    except ProgrammingError as exc:
        if _is_undefined_table(exc):
            await db.rollback()
            return []
        raise
    return [{
        "id": str(r["id"]),
        "order_id": str(r["order_id"]),
        "amount": str(r["amount"]),
        "remaining": str(r["remaining_amount"]),
        "status": r["status"],
        "created_by": str(r["created_by"]) if r["created_by"] else None,
        "updated_by": str(r["updated_by"]) if r["updated_by"] else None,
    } for r in rows]


async def fetch_all_holds(db: AsyncSession, schema: str) -> list[dict[str, Any]]:
    try:
        rows = (await db.execute(text(
            f'SELECT order_id, amount, remaining_amount, status '
            f'FROM "{schema}".order_credit_holds ORDER BY order_id'))).mappings().all()
    except ProgrammingError as exc:
        if _is_undefined_table(exc):
            await db.rollback()
            return []
        raise
    return [{
        "order_id": str(r["order_id"]),
        "amount": str(r["amount"]),
        "remaining": str(r["remaining_amount"]),
        "status": r["status"],
    } for r in rows]


async def insert_hold(
    db: AsyncSession, schema: str, order_id: str, *,
    amount: str, remaining: str, status: str,
) -> bool:
    """Corruption injection: force a lifecycle row into existence. Returns
    False when the product has no hold table (tamper is a documented no-op)."""
    try:
        await db.execute(text(
            f'INSERT INTO "{schema}".order_credit_holds '
            "(order_id, amount, remaining_amount, status) "
            "VALUES (:o, :a, :r, :s)"),
            {"o": order_id, "a": amount, "r": remaining, "s": status})
    except ProgrammingError as exc:
        if _is_undefined_table(exc):
            await db.rollback()
            return False
        raise
    await db.commit()
    return True


async def tamper_hold(
    db: AsyncSession, schema: str, order_id: str, **sets: str,
) -> bool:
    """Corruption injection: UPDATE the order's (single) hold row. Returns
    False (no-op) when the table does not exist."""
    if not sets:
        raise ValueError("tamper_hold requires at least one column")
    clause = ", ".join(f"{k} = :{k}" for k in sets)
    params: dict[str, Any] = {"oid": order_id}
    params.update(sets)
    try:
        await db.execute(text(
            f'UPDATE "{schema}".order_credit_holds SET {clause} '
            "WHERE order_id = :oid"), params)
    except ProgrammingError as exc:
        if _is_undefined_table(exc):
            await db.rollback()
            return False
        raise
    await db.commit()
    return True


async def delete_holds(db: AsyncSession, schema: str, order_id: str) -> bool:
    """Corruption injection: remove the order's lifecycle rows entirely."""
    try:
        await db.execute(text(
            f'DELETE FROM "{schema}".order_credit_holds WHERE order_id = :oid'),
            {"oid": order_id})
    except ProgrammingError as exc:
        if _is_undefined_table(exc):
            await db.rollback()
            return False
        raise
    await db.commit()
    return True


async def payments_vector(db: AsyncSession, schema: str, order_id: str) -> list[dict[str, Any]]:
    """All payment rows including soft-deleted ones (the migration/aggregate
    boundary treats is_deleted rows as non-history; tests must SEE them)."""
    rows = (await db.execute(text(
        f'SELECT id, method, amount, status, is_deleted, receipt_number '
        f'FROM "{schema}".payments WHERE order_id = :oid ORDER BY created_at, id'),
        {"oid": order_id})).mappings().all()
    return [{
        "method": r["method"],
        "amount": str(r["amount"]),
        "status": r["status"],
        "is_deleted": bool(r["is_deleted"]),
        "receipt_number": r["receipt_number"],
    } for r in rows]


async def soft_delete_payment(
    db: AsyncSession, schema: str, order_id: str, method: str,
) -> int:
    result = await db.execute(text(
        f'UPDATE "{schema}".payments SET is_deleted = TRUE, deleted_at = now() '
        "WHERE order_id = :oid AND method = :m AND is_deleted IS FALSE"),
        {"oid": order_id, "m": method})
    await db.commit()
    return int(result.rowcount or 0)


async def payment_count(db: AsyncSession, schema: str, order_id: str) -> int:
    return int((await db.execute(text(
        f'SELECT count(*) FROM "{schema}".payments WHERE order_id = :oid'),
        {"oid": order_id})).scalar_one())


async def receipt_numbers(db: AsyncSession, schema: str, order_id: str) -> list[str]:
    rows = (await db.execute(text(
        f'SELECT receipt_number FROM "{schema}".payments '
        "WHERE order_id = :oid AND receipt_number IS NOT NULL"),
        {"oid": order_id})).scalars().all()
    return [str(r) for r in rows]


async def binding_exists(db: AsyncSession, ws_id: str, retailer_id: str) -> bool:
    row = (await db.execute(text(
        "SELECT 1 FROM public.wholesaler_retailer_bindings "
        "WHERE wholesaler_id = :w AND retailer_id = :r AND is_deleted IS FALSE"),
        {"w": ws_id, "r": retailer_id})).first()
    return row is not None


async def soft_delete_binding(db: AsyncSession, ws_id: str, retailer_id: str) -> None:
    await db.execute(text(
        "UPDATE public.wholesaler_retailer_bindings SET is_deleted = TRUE, "
        "deleted_at = now() WHERE wholesaler_id = :w AND retailer_id = :r"),
        {"w": ws_id, "r": retailer_id})
    await db.commit()


async def summary_for(db: AsyncSession, ws_id: str) -> dict[str, Any]:
    """Production read path: ReceivablesService.get_receivables_summary."""
    from services.receivables_service import ReceivablesService
    return await ReceivablesService().get_receivables_summary(
        tenant_db=db, wholesaler_id=ws_id)


def summary_row(summary: dict[str, Any], retailer_id: str) -> dict[str, Any] | None:
    for row in summary.get("by_retailer") or []:
        if str(row.get("retailer_id")) == str(retailer_id):
            return row
    return None
