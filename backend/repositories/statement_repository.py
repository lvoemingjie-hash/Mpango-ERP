"""Repository for the Contract D relationship account statement (DC-12R1-S3-S2B-I2C-I2B).

100% read-only. All queries are raw ``text()`` SQL against the tenant session.

Authoritative sources (binding accounting rules):
  * movements[]      -> immutable receivable ledger entries (account_type='receivable',
                        reference_type IN ('order','refund')), scoped to the
                        (wholesaler_id, retailer_id) pair via a JOIN on orders.
                        orders.is_deleted is intentionally NOT filtered (rule 8:
                        soft-deleted orders remain in historical accounting scope).
  * settled_payments -> canonical completed payments for the pair in the period
                        (a fully independent list; never associated with movements).
  * opening_balance  -> SUM(receivable amount) strictly before the period start.
  * closing_balance  -> opening + SUM(movements signed_amount).

Every tenant-schema table is explicitly schema-qualified (``"{schema}".table``)
so queries work regardless of the session ``search_path`` (the API sets it, but
tests use plain sessions).

Date windowing uses a fixed ``Africa/Nairobi`` (EAT) day boundary converted to a
UTC half-open interval ``[start_utc, next_day_start_utc)`` so inclusive EAT days
map to exclusive UTC bounds unambiguously.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# Fixed MVP display timezone (matches print_service._EAT_UTC_OFFSET_HOURS).
_EAT_TZNAME = "Africa/Nairobi"
_EAT_UTC_OFFSET = timedelta(hours=3)
_MAX_SPAN_DAYS = 365

# Public aggregate statement-line cap (DC-12R1-S3-S2B-I2C-I2B-R1-R1 rule 5).
# Every list query fetches at most CAP+1 rows so overflow is detectable (never
# silently truncated). The single authoritative constant is shared by the
# service, the routes and the tests — no scattered literals anywhere.
STATEMENT_LINE_CAP: int = 1000

# Strict canonical calendar-date shape: exactly YYYY-MM-DD (zero-padded). The
# R1-R1 truth contract rejects non-zero-padded variants (e.g. 2026-8-1) that
# datetime.strptime would otherwise accept.
_DATE_FORMAT_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class StatementPeriodError(ValueError):
    """Raised when the requested period is missing/blank/malformed/out-of-range."""


class StatementLedgerScopeIncomplete(Exception):
    """An orphan receivable ledger reference cannot resolve to an order (rule 9)."""


class StatementInternalInconsistent(Exception):
    """Recomputed closing balance disagrees with the DB period sum (rule 10),
    a receivable movement is zero-valued, or completed-payment ownership is
    inconsistent (R1 rules 2/1)."""


class StatementReconciliationFailed(Exception):
    """Credit-only binding: ledger receivable sum != cached outstanding_balance (rule 11)."""


class StatementRangeTooLarge(Exception):
    """The aggregate statement line count exceeds the exact cap (R1 rule 5)."""


def parse_statement_date_range(
    raw_from: str | None, raw_to: str | None
) -> tuple[date, date]:
    """Strictly parse and validate the inclusive EAT date range from raw query
    strings (DC-12R1-S3-S2B-I2C-I2B-R1 rule 3; R1-R1 strict shape).

    Missing/blank, non-canonical, malformed, reversed, or >365-day ranges raise
    ``StatementPeriodError`` (mapped to a controlled 400 INVALID_DATE_RANGE by
    the routes — never a framework 422 or a neutral 404). No raw parser
    details ever reach the public message. Returns the validated ``date`` pair
    (the UTC half-open conversion happens inside the service).

    R1-R1: the shape is enforced with ``re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")``
    BEFORE parsing, so non-zero-padded variants that ``strptime`` would accept
    (e.g. ``2026-8-1``) are rejected, and extra characters are rejected too.
    """
    for label, value in (("from", raw_from), ("to", raw_to)):
        if value is None or str(value).strip() == "":
            raise StatementPeriodError(f"{label} date is required.")
    f_raw = str(raw_from).strip()
    t_raw = str(raw_to).strip()
    if not _DATE_FORMAT_RE.fullmatch(f_raw) or not _DATE_FORMAT_RE.fullmatch(t_raw):
        raise StatementPeriodError("Invalid date format.")
    try:
        date_from = datetime.strptime(f_raw, "%Y-%m-%d").date()
        date_to = datetime.strptime(t_raw, "%Y-%m-%d").date()
    except ValueError:
        raise StatementPeriodError("Invalid date format.")
    # Reversed + >365-day validation (raises StatementPeriodError).
    eat_date_range_to_utc_half_open(date_from, date_to)
    return date_from, date_to


def eat_date_range_to_utc_half_open(
    date_from: date, date_to: date
) -> tuple[datetime, datetime]:
    """Convert inclusive EAT calendar days to a UTC half-open interval.

    ``[date_from 00:00 EAT, (date_to + 1 day) 00:00 EAT)`` expressed in UTC. EAT
    is UTC+3, so an EAT midnight is 21:00 the prior UTC day. Raises
    ``StatementPeriodError`` if ``date_from > date_to`` or the span exceeds
    ``_MAX_SPAN_DAYS``.
    """
    if date_from is None or date_to is None:
        raise StatementPeriodError("Both from and to dates are required.")
    if date_to < date_from:
        raise StatementPeriodError("from date must not be after to date.")
    span = (date_to - date_from).days + 1
    if span > _MAX_SPAN_DAYS:
        raise StatementPeriodError(
            f"Statement period exceeds the maximum span of {_MAX_SPAN_DAYS} days."
        )
    eat = timezone(_EAT_UTC_OFFSET, _EAT_TZNAME)
    start_utc = datetime(date_from.year, date_from.month, date_from.day, tzinfo=eat).astimezone(timezone.utc)
    next_day_utc = datetime(date_to.year, date_to.month, date_to.day, tzinfo=eat).astimezone(timezone.utc) + timedelta(days=1)
    return start_utc, next_day_utc


class StatementRepository:
    """Read-only receivable-ledger + canonical-payment queries for Contract D.

    Every tenant-schema table is explicitly qualified with ``schema`` (a trusted
    server/token-derived tenant schema name, never client input).
    """

    # ------------------------------------------------------------------
    # Orphan precheck (rule 9) — run BEFORE computing balances.
    # ------------------------------------------------------------------
    async def count_orphan_receivable_refs(
        self,
        db: AsyncSession,
        *,
        schema: str,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
    ) -> int:
        """Count receivable ledger rows whose reference_id resolves to NO order.

        An orphan is a receivable row that cannot be attributed to ANY order in
        this tenant schema (the order row is missing). Rows that resolve to an
        existing order belonging to ANOTHER retailer are NOT orphans — they are
        simply another relationship's history and must not trip this retailer's
        statement. Any non-zero orphan count means the ledger scope is
        incomplete -> 409 STATEMENT_LEDGER_SCOPE_INCOMPLETE.
        """
        row = (
            await db.execute(
                text(
                    f"""
                    SELECT COUNT(*) AS n
                    FROM "{schema}".ledger_entries le
                    LEFT JOIN "{schema}".orders o ON o.id = le.reference_id
                    WHERE le.account_type = 'receivable'
                      AND le.reference_type IN ('order', 'refund')
                      AND o.id IS NULL
                    """
                ),
            )
        ).first()
        return int(row.n if row else 0)

    # ------------------------------------------------------------------
    # Opening balance (rule 1) — strictly before the UTC period start.
    # ------------------------------------------------------------------
    async def sum_receivable_before(
        self,
        db: AsyncSession,
        *,
        schema: str,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
        before_utc: datetime,
    ) -> Decimal:
        row = (
            await db.execute(
                text(
                    f"""
                    SELECT COALESCE(SUM(le.amount), 0) AS opening
                    FROM "{schema}".ledger_entries le
                    JOIN "{schema}".orders o ON o.id = le.reference_id
                    WHERE le.account_type = 'receivable'
                      AND le.reference_type IN ('order', 'refund')
                      AND o.wholesaler_id = :wid
                      AND o.retailer_id = :rid
                      AND le.transaction_date < :before
                    """
                ),
                {"wid": wholesaler_id, "rid": retailer_id, "before": before_utc},
            )
        ).first()
        return Decimal(row.opening) if row and row.opening is not None else Decimal("0")

    # ------------------------------------------------------------------
    # Movements (rule 2) — receivable ledger entries in [start, next_day).
    # Also returns the DB period sum for the arithmetic consistency check.
    # LIMIT cap+1 so an over-cap period is detectable, never silently
    # truncated (R1 rule 5).
    # ------------------------------------------------------------------
    async def list_movements(
        self,
        db: AsyncSession,
        *,
        schema: str,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
        start_utc: datetime,
        next_day_utc: datetime,
    ) -> tuple[list[Mapping[str, Any]], Decimal]:
        rows = (
            await db.execute(
                text(
                    f"""
                    SELECT le.id, le.transaction_date, le.amount,
                           le.reference_type, le.reference_id, le.description
                    FROM "{schema}".ledger_entries le
                    JOIN "{schema}".orders o ON o.id = le.reference_id
                    WHERE le.account_type = 'receivable'
                      AND le.reference_type IN ('order', 'refund')
                      AND o.wholesaler_id = :wid
                      AND o.retailer_id = :rid
                      AND le.transaction_date >= :start
                      AND le.transaction_date < :next_day
                    ORDER BY le.transaction_date ASC, le.id ASC
                    LIMIT :limit
                    """
                ),
                {
                    "wid": wholesaler_id,
                    "rid": retailer_id,
                    "start": start_utc,
                    "next_day": next_day_utc,
                    "limit": STATEMENT_LINE_CAP + 1,
                },
            )
        ).mappings().all()
        period_sum = sum((Decimal(r["amount"]) for r in rows), Decimal("0"))
        return list(rows), period_sum

    # ------------------------------------------------------------------
    # DB period closing sum (rule 12) — independent recompute of the period total
    # directly from the DB, to compare against opening + net_movement.
    # ------------------------------------------------------------------
    async def sum_receivable_period(
        self,
        db: AsyncSession,
        *,
        schema: str,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
        start_utc: datetime,
        next_day_utc: datetime,
    ) -> Decimal:
        row = (
            await db.execute(
                text(
                    f"""
                    SELECT COALESCE(SUM(le.amount), 0) AS s
                    FROM "{schema}".ledger_entries le
                    JOIN "{schema}".orders o ON o.id = le.reference_id
                    WHERE le.account_type = 'receivable'
                      AND le.reference_type IN ('order', 'refund')
                      AND o.wholesaler_id = :wid
                      AND o.retailer_id = :rid
                      AND le.transaction_date >= :start
                      AND le.transaction_date < :next_day
                    """
                ),
                {
                    "wid": wholesaler_id,
                    "rid": retailer_id,
                    "start": start_utc,
                    "next_day": next_day_utc,
                },
            )
        ).first()
        return Decimal(row.s) if row and row.s is not None else Decimal("0")

    # ------------------------------------------------------------------
    # Settled payments (rule 5) — canonical completed payments, independent list.
    # Never associated with movements (rule 6). R1: ownership is fully pinned —
    # payment retailer, order retailer AND order wholesaler must all match the
    # statement pair.
    # ------------------------------------------------------------------
    async def list_settled_payments(
        self,
        db: AsyncSession,
        *,
        schema: str,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
        start_utc: datetime,
        next_day_utc: datetime,
    ) -> list[Mapping[str, Any]]:
        rows = (
            await db.execute(
                text(
                    f"""
                    SELECT p.id, p.created_at, p.order_id, p.amount, p.method,
                           p.receipt_number, p.transaction_id
                    FROM "{schema}".payments p
                    JOIN "{schema}".orders o ON o.id = p.order_id
                    WHERE p.retailer_id = :rid
                      AND o.retailer_id = :rid
                      AND o.wholesaler_id = :wid
                      AND p.is_deleted IS FALSE
                      AND p.status = 'completed'
                      AND p.created_at >= :start
                      AND p.created_at < :next_day
                    ORDER BY p.created_at ASC, p.id ASC
                    LIMIT :limit
                    """
                ),
                {
                    "wid": wholesaler_id,
                    "rid": retailer_id,
                    "start": start_utc,
                    "next_day": next_day_utc,
                    "limit": STATEMENT_LINE_CAP + 1,
                },
            )
        ).mappings().all()
        return list(rows)

    # ------------------------------------------------------------------
    # Completed-payment ownership-integrity precheck (R1 rule 1).
    # Any completed payment in this tenant schema whose retailer differs from
    # its order's retailer makes the ledger/payment scope inconsistent. The
    # statement fails closed (409 STATEMENT_INTERNAL_INCONSISTENT) so corrupt
    # rows neither leak into the document nor silently disappear.
    # ------------------------------------------------------------------
    async def count_completed_payment_ownership_mismatch(
        self, db: AsyncSession, *, schema: str
    ) -> int:
        row = (
            await db.execute(
                text(
                    f"""
                    SELECT COUNT(*) AS n
                    FROM "{schema}".payments p
                    JOIN "{schema}".orders o ON o.id = p.order_id
                    WHERE p.status = 'completed'
                      AND p.is_deleted IS FALSE
                      AND p.retailer_id IS DISTINCT FROM o.retailer_id
                    """
                ),
            )
        ).first()
        return int(row.n if row and row.n is not None else 0)

    # ------------------------------------------------------------------
    # Pending/rejected declarations (non-accounting; only when explicitly requested).
    # LIMIT cap+1 so over-cap periods fail closed (R1 rule 5).
    # ------------------------------------------------------------------
    async def list_pending_declarations(
        self,
        db: AsyncSession,
        *,
        schema: str,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
        start_utc: datetime,
        next_day_utc: datetime,
    ) -> list[Mapping[str, Any]]:
        rows = (
            await db.execute(
                text(
                    f"""
                    SELECT pd.id, pd.order_id, pd.declared_amount, pd.method,
                           pd.status, pd.submitted_at, pd.transfer_reference
                    FROM "{schema}".payment_declarations pd
                    WHERE pd.wholesaler_id = :wid
                      AND pd.retailer_id = :rid
                      AND pd.status IN ('pending', 'rejected')
                      AND pd.submitted_at >= :start
                      AND pd.submitted_at < :next_day
                    ORDER BY pd.submitted_at ASC, pd.id ASC
                    LIMIT :limit
                    """
                ),
                {
                    "wid": wholesaler_id,
                    "rid": retailer_id,
                    "start": start_utc,
                    "next_day": next_day_utc,
                    "limit": STATEMENT_LINE_CAP + 1,
                },
            )
        ).mappings().all()
        return list(rows)

    # ------------------------------------------------------------------
    # Credit/mixed classification + reconciliation (rules 11/12).
    # Inspects the relationship's FULL history of completed payments (not just
    # the print range) to classify credit-only vs mixed. R1: ownership fully
    # pinned (payment retailer + order retailer + order wholesaler).
    # ------------------------------------------------------------------
    async def relationship_has_non_credit_payment(
        self,
        db: AsyncSession,
        *,
        schema: str,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
    ) -> bool:
        """True iff any completed payment for the pair used a non-credit method
        (cash/transfer). If False, the relationship is credit-only and the
        ledger receivable sum must reconcile to bindings.outstanding_balance.
        """
        row = (
            await db.execute(
                text(
                    f"""
                    SELECT EXISTS (
                      SELECT 1 FROM "{schema}".payments p
                      JOIN "{schema}".orders o ON o.id = p.order_id
                      WHERE p.retailer_id = :rid
                        AND o.retailer_id = :rid
                        AND o.wholesaler_id = :wid
                        AND p.is_deleted IS FALSE
                        AND p.status = 'completed'
                        AND p.method IN ('cash', 'transfer')
                    ) AS has_non_credit
                    """
                ),
                {"wid": wholesaler_id, "rid": retailer_id},
            )
        ).first()
        return bool(row.has_non_credit) if row else False

    async def ledger_receivable_total(
        self,
        db: AsyncSession,
        *,
        schema: str,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
    ) -> Decimal:
        """Full-history receivable ledger sum for the pair (all time)."""
        row = (
            await db.execute(
                text(
                    f"""
                    SELECT COALESCE(SUM(le.amount), 0) AS total
                    FROM "{schema}".ledger_entries le
                    JOIN "{schema}".orders o ON o.id = le.reference_id
                    WHERE le.account_type = 'receivable'
                      AND le.reference_type IN ('order', 'refund')
                      AND o.wholesaler_id = :wid
                      AND o.retailer_id = :rid
                    """
                ),
                {"wid": wholesaler_id, "rid": retailer_id},
            )
        ).first()
        return Decimal(row.total) if row and row.total is not None else Decimal("0")

    async def cached_binding_balance(
        self,
        db: AsyncSession,
        *,
        wholesaler_id: uuid.UUID,
        retailer_id: uuid.UUID,
    ) -> Decimal | None:
        """The live cached ``outstanding_balance`` on the active binding, or None."""
        row = (
            await db.execute(
                text(
                    """
                    SELECT outstanding_balance
                    FROM public.wholesaler_retailer_bindings
                    WHERE wholesaler_id = :wid AND retailer_id = :rid
                      AND is_deleted IS FALSE AND status = 'active'
                    LIMIT 1
                    """
                ),
                {"wid": wholesaler_id, "rid": retailer_id},
            )
        ).first()
        return Decimal(row.outstanding_balance) if row and row.outstanding_balance is not None else None
