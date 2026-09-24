"""Shared valid-payment-history contract (R2-R1 SR1 closure).

A live payment row is EFFECTIVE HISTORY only when it carries a positive and
FINITE amount, one of the canonical methods, a known status, the same
retailer as its order, and belongs to a live order. Every consumer of the
effective history — the canonical payment write path and both receivables
read paths — runs this contract BEFORE using the rows, so a row outside it
is a NAMED refusal instead of a value that aggregation silently ignores.

The query is deliberately a single grouped aggregate over the caller's
order scope: the write path passes the one locked order, the read paths
pass the orders of their visible page/scope. Rows already soft-deleted
(``is_deleted`` true) are not history and are never counted.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

PAYMENT_HISTORY_INTEGRITY = "PAYMENT_HISTORY_INTEGRITY"

ALLOWED_PAYMENT_METHODS = ("cash", "transfer", "credit")
ALLOWED_PAYMENT_STATUSES = ("pending", "completed")
#: Numeric literals PostgreSQL accepts in a numeric column that are not
#: finite business amounts. ``amount <= 0`` alone does NOT catch NaN or
#: +Infinity (NaN sorts above every non-NaN value in PostgreSQL).
NON_FINITE_NUMERIC_LITERALS = ("NaN", "Infinity", "-Infinity")

_INVALID_ROW_PREDICATE = """
                p.amount IS NULL
                OR p.amount <= 0
                OR p.amount::text IN {non_finite}
                OR p.method IS NULL
                OR p.method NOT IN {methods}
                OR p.status IS NULL
                OR p.status NOT IN {statuses}
                OR p.retailer_id IS DISTINCT FROM o.retailer_id
                OR o.is_deleted IS TRUE
""" \
    .format(
        non_finite="(" + ", ".join(
            f"'{literal}'" for literal in NON_FINITE_NUMERIC_LITERALS) + ")",
        methods="(" + ", ".join(
            f"'{method}'" for method in ALLOWED_PAYMENT_METHODS) + ")",
        statuses="(" + ", ".join(
            f"'{state}'" for state in ALLOWED_PAYMENT_STATUSES) + ")",
    )


def _history_integrity(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": PAYMENT_HISTORY_INTEGRITY, "message": message},
    )


async def find_invalid_history_orders(
    db: AsyncSession,
    *,
    order_ids: Iterable[Any],
) -> dict[str, int]:
    """Return ``{order_id: invalid_live_row_count}`` for the given scope.

    Orders with no invalid rows are absent from the mapping. Callers pass
    the primary keys they already hold (ORM UUIDs); the values are handed
    to the driver unchanged.
    """
    ids = [value for value in order_ids if value is not None]
    if not ids:
        return {}

    result = await db.execute(
        text(
            f"""
            SELECT p.order_id, COUNT(*) AS invalid_rows
            FROM payments p
            JOIN orders o ON o.id = p.order_id
            WHERE p.order_id = ANY(:order_ids)
              AND p.is_deleted IS FALSE
              AND ({_INVALID_ROW_PREDICATE})
            GROUP BY p.order_id
            """
        ),
        {"order_ids": ids},
    )
    return {
        str(row["order_id"]): int(row["invalid_rows"])
        for row in result.mappings().all()
    }


async def assert_valid_payment_history(
    db: AsyncSession,
    *,
    order_ids: Iterable[Any],
    context: str,
) -> None:
    """Named refusal when any order in scope carries invalid live history."""
    invalid = await find_invalid_history_orders(db, order_ids=order_ids)
    if not invalid:
        return
    sample = ", ".join(
        f"{order_id}={count}" for order_id, count in sorted(invalid.items())
    )
    raise _history_integrity(
        f"{context}: {sum(invalid.values())} invalid live payment row(s) "
        "in effective history — every live row needs a positive finite "
        "amount, a canonical method, a known status and the order's own "
        f"retailer (per order: {sample})"
    )
