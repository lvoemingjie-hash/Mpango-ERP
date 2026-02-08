"""
S6-1/S6-2: Reporting Read Models — SQLAlchemy Mappings for Views & Materialized Views.

Philosophy: "Build the eyes of the ERP."

These are read-only SQLAlchemy models mapped to reporting objects:
- mv_*  : Materialized Views (S6-2, near-real-time, refreshed by S4 job)
- rpt_* : Standard Views (S6-1, real-time)

S6-P Compliance:
- All models include reporting_currency_code
- All use transaction_date as time axis
- All monetary columns are NUMERIC(20, 4)
- All objects are read-only (no INSERT/UPDATE/DELETE)

Usage:
    from database.reporting_session import get_reporting_session
    from models.reporting import MvSalesDaily

    async for session in get_reporting_session("t_abc123"):
        result = await session.execute(select(MvSalesDaily))
        rows = result.scalars().all()
"""
from decimal import Decimal
from datetime import date, datetime
from typing import Optional
import uuid

from sqlalchemy import String, Numeric, DateTime, Date, Integer, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base


class MvSalesDaily(Base):
    """
    Materialized View: Daily Revenue Aggregation (S6-2).

    Source: ledger_entries WHERE account_type = 'revenue'
    Grain: One row per calendar day
    Join Depth: 0
    Refresh: CONCURRENTLY via S4 job (every 15 min)
    Unique Index: (transaction_date, reporting_currency_code)

    Display Rule (S6-P §2.1):
        Revenue is stored as negative (Credit) but displayed as positive.
        This view applies ABS(SUM(amount)) so daily_revenue is always positive.
    """
    __tablename__ = "mv_sales_daily"
    __table_args__ = {"info": {"is_view": True}}

    transaction_date: Mapped[date] = mapped_column(
        Date,
        primary_key=True,
        comment="Accounting date (S6-P: never use created_at)"
    )
    reporting_currency_code: Mapped[str] = mapped_column(
        String(3),
        primary_key=True,
        comment="ISO 4217 currency code (hardcoded 'USD' for now)"
    )
    daily_revenue: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4),
        comment="ABS(SUM(amount)) — always positive for display"
    )
    transaction_count: Mapped[int] = mapped_column(
        Integer,
        comment="Number of revenue entries for this day"
    )


# Backward-compatible alias for code that still references the old name
RptSalesDaily = MvSalesDaily


class RptReceivablesSummary(Base):
    """
    Read Model: Accounts Receivable Summary by Entity.

    Source: ledger_entries WHERE account_type = 'receivable'
    Grain: One row per (entity_id, entity_type)
    Join Depth: 0

    Display Rule (S6-P §2.1):
        Receivable uses natural sign. Positive = customer owes us.
        outstanding_balance = SUM(amount) — no ABS needed.
    """
    __tablename__ = "rpt_receivables_summary"
    __table_args__ = {"info": {"is_view": True}}

    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        comment="Reference ID (typically order/customer UUID)"
    )
    entity_type: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
        comment="Reference type (e.g., 'order', 'payment')"
    )
    reporting_currency_code: Mapped[str] = mapped_column(
        String(3),
        comment="ISO 4217 currency code (hardcoded 'USD' for now)"
    )
    outstanding_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4),
        comment="SUM(amount) — positive means customer owes us"
    )
    entry_count: Mapped[int] = mapped_column(
        Integer,
        comment="Number of receivable entries for this entity"
    )
    earliest_transaction: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        comment="First transaction date for this entity"
    )
    latest_transaction: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        comment="Most recent transaction date for this entity"
    )


class RptCashFlowDaily(Base):
    """
    Read Model: Daily Cash Flow with Running Balance.

    Source: ledger_entries WHERE account_type = 'cash'
    Grain: One row per calendar day
    Join Depth: 0

    Display Rule (S6-P §2.1):
        Cash uses natural sign. Positive = cash received (Debit).
        net_change = SUM(amount) — positive is inflow, negative is outflow.
        running_balance = cumulative SUM via window function.
    """
    __tablename__ = "rpt_cash_flow_daily"
    __table_args__ = {"info": {"is_view": True}}

    transaction_date: Mapped[date] = mapped_column(
        Date,
        primary_key=True,
        comment="Accounting date (S6-P: never use created_at)"
    )
    reporting_currency_code: Mapped[str] = mapped_column(
        String(3),
        comment="ISO 4217 currency code (hardcoded 'USD' for now)"
    )
    net_change: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4),
        comment="SUM(amount) — positive is inflow, negative is outflow"
    )
    transaction_count: Mapped[int] = mapped_column(
        Integer,
        comment="Number of cash entries for this day"
    )
    running_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4),
        comment="Cumulative cash balance up to this date"
    )
