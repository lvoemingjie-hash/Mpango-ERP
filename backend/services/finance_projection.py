"""Read-only money projection; no new revenue/refund accounting policy."""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text

from services.payment_history_contract import assert_valid_payment_history


async def current_finance_projection(db, wholesaler_id):
    rows = (await db.execute(text(
        "SELECT id, status::text AS status, currency_snapshot, created_at "
        "FROM orders WHERE wholesaler_id=:wid AND is_deleted IS FALSE"
    ), {"wid": UUID(str(wholesaler_id))})).mappings().all()
    ids = [row['id'] for row in rows]
    await assert_valid_payment_history(db, order_ids=ids, context='Finance summary')
    totals = {}
    holds = {}
    if ids:
        totals = {row['order_id']: row for row in (await db.execute(text(
            "SELECT order_id, "
            "COALESCE(SUM(amount) FILTER (WHERE method='credit'),0) AS credit, "
            "COALESCE(SUM(amount) FILTER (WHERE method IN ('cash','transfer')),0) AS cash "
            "FROM payments WHERE order_id=ANY(:ids) AND is_deleted IS FALSE GROUP BY order_id"
        ), {'ids': ids})).mappings().all()}
        holds = {row['order_id']: Decimal(str(row['remaining'])) for row in (await db.execute(text(
            "SELECT order_id, remaining_amount AS remaining FROM order_credit_holds "
            "WHERE order_id=ANY(:ids) AND status='active'"
        ), {'ids': ids})).mappings().all()}
    currencies = set()
    outstanding = defaultdict(Decimal)
    cash_received = defaultdict(Decimal)
    overdue = 0
    now = datetime.now(timezone.utc)
    for row in rows:
        currency = row['currency_snapshot'] if row['currency_snapshot'] in ('KES', 'UGX') else 'LEGACY_CURRENCY_UNVERIFIED'
        currencies.add(currency)
        payment = totals.get(row['id'], {})
        credit = Decimal(str(payment.get('credit', 0)))
        cash = Decimal(str(payment.get('cash', 0)))
        debt = credit - cash if credit > 0 else Decimal(0)
        hold = holds.get(row['id'], Decimal(0))
        if debt < 0 or hold < 0 or (credit > 0 and hold > 0):
            raise HTTPException(409, detail={'code': 'PAYMENT_HISTORY_INTEGRITY', 'message': 'Finance projection found inconsistent hold or credit exposure'})
        # Return/refund treatment remains a separately adjudicated contract.
        due = hold + debt if row['status'] in ('confirmed', 'partially_paid', 'paid', 'fulfilled') else Decimal(0)
        outstanding[currency] += due
        cash_received[currency] += cash
        created = row['created_at']
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        overdue += int(due > 0 and created is not None and (now - created).days >= 30)
    known = len(currencies) == 1 and 'LEGACY_CURRENCY_UNVERIFIED' not in currencies
    return {
        'currency': next(iter(currencies)) if known else None,
        'currency_status': 'verified_snapshot' if known else ('mixed' if len(currencies) > 1 else 'unverified'),
        'outstanding': sum(outstanding.values(), Decimal(0)),
        'outstanding_by_currency': {key: float(value) for key, value in outstanding.items()},
        'cash_received_by_currency': {key: float(value) for key, value in cash_received.items()},
        'overdue_count': overdue,
    }
