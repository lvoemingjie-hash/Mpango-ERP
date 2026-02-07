"""
S5-B: Financial Ledger Model

Implements immutable ledger entries for accounting-grade financial tracking.

Philosophy: "Payments are not 'updating a balance column'. Payments are immutable Ledger Entries."

Chart of Accounts:
- RECEIVABLE: Accounts Receivable (Customer owes us money)
- REVENUE: Revenue Recognition (We earned money)
- CASH: Cash/Bank Account (We received money)
- LIABILITY: Liabilities (We owe money)
"""
from enum import Enum as PyEnum
from decimal import Decimal
from typing import Optional
import uuid

from sqlalchemy import String, Text, Numeric, DateTime, Index, Enum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone

from models.base import BaseModel


class AccountType(str, PyEnum):
    """
    Account types for the Chart of Accounts.
    
    Standard accounting equation: Assets = Liabilities + Equity
    Revenue increases Equity.
    
    Account Types:
    - RECEIVABLE: Asset account (Customer owes us money)
    - REVENUE: Equity account (We earned money)
    - CASH: Asset account (We have money)
    - LIABILITY: Liability account (We owe money)
    """
    RECEIVABLE = "receivable"
    REVENUE = "revenue"
    CASH = "cash"
    LIABILITY = "liability"


class LedgerEntry(BaseModel):
    """
    Immutable ledger entry for double-entry bookkeeping.
    
    Stored in tenant schema for tenant isolation.
    
    Philosophy:
    - Ledger entries are IMMUTABLE (never updated, only inserted)
    - Use positive amounts for Debits, negative for Credits
    - Every transaction creates balanced entries (Debits = Credits)
    
    Example - Order Confirmation ($100):
        Entry 1: Debit RECEIVABLE +100 (Customer owes us)
        Entry 2: Credit REVENUE -100 (We earned revenue)
        Net: +100 - 100 = 0 (Balanced)
    
    Example - Payment Received ($100):
        Entry 1: Debit CASH +100 (We received money)
        Entry 2: Credit RECEIVABLE -100 (Customer no longer owes)
        Net: +100 - 100 = 0 (Balanced)
    """
    __tablename__ = "ledger_entries"
    __table_args__ = (
        Index('ix_ledger_entries_reference', 'reference_type', 'reference_id'),
        Index('ix_ledger_entries_account_type', 'account_type'),
        Index('ix_ledger_entries_transaction_date', 'transaction_date'),
    )

    transaction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="Date/time of the transaction"
    )
    
    account_type: Mapped[AccountType] = mapped_column(
        Enum(AccountType, name="account_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
        comment="Account type from Chart of Accounts"
    )
    
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=4),
        nullable=False,
        comment="Amount: Positive for Debit, Negative for Credit"
    )
    
    reference_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type of reference: 'order', 'payment', 'refund'"
    )
    
    reference_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="UUID of the referenced entity"
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable description of the entry"
    )
    
    # S5.5-2: Ledger Versioning
    entry_version: Mapped[int] = mapped_column(
        nullable=False,
        default=1,
        comment="Entry format version for schema evolution tracking"
    )
    
    hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Cryptographic hash for blockchain/audit trail (future use)"
    )
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<LedgerEntry(id={self.id}, "
            f"date={self.transaction_date.date()}, "
            f"account={self.account_type.value}, "
            f"amount={self.amount}, "
            f"ref={self.reference_type}:{self.reference_id})>"
        )
