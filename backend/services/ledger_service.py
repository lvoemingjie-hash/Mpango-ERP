"""
S5-B: Ledger Service

Implements posting engine and balance projection for accounting-grade financial tracking.

Philosophy: "Payments are not 'updating a balance column'. Payments are immutable Ledger Entries."

Features:
- Immutable ledger entries (write-only)
- Double-entry bookkeeping
- Balance projection (calculated, not stored)
- Atomic posting with order state transitions
"""
from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.ledger import LedgerEntry, AccountType
from core.structured_logging import get_logger
from core.exceptions import LedgerIntegrityError

logger = get_logger(__name__)


class LedgerService:
    """
    Service for managing financial ledger entries.
    
    All financial transactions are recorded as immutable ledger entries.
    Balances are calculated on-demand, never stored.
    """
    
    def __init__(self, db: AsyncSession):
        """
        Initialize ledger service.
        
        Args:
            db: Database session (tenant schema)
        """
        self.db = db
    
    async def post_entry(
        self,
        account_type: AccountType,
        amount: Decimal,
        reference_type: str,
        reference_id: UUID,
        description: Optional[str] = None,
        transaction_date: Optional[datetime] = None
    ) -> LedgerEntry:
        """
        Post a single ledger entry.
        
        This is a low-level method. Use post_transaction() for balanced entries.
        
        Args:
            account_type: Account type from Chart of Accounts
            amount: Amount (positive for debit, negative for credit)
            reference_type: Type of reference ('order', 'payment', 'refund')
            reference_id: UUID of referenced entity
            description: Human-readable description
            transaction_date: Date/time of transaction (defaults to now)
        
        Returns:
            Created LedgerEntry
        """
        entry = LedgerEntry(
            transaction_date=transaction_date or datetime.now(timezone.utc),
            account_type=account_type,
            amount=amount,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description
        )
        
        self.db.add(entry)
        await self.db.flush()
        await self.db.refresh(entry)
        
        logger.info(
            f"Posted ledger entry: {account_type.value} {amount}",
            extra={
                "entry_id": str(entry.id),
                "account_type": account_type.value,
                "amount": str(amount),
                "reference_type": reference_type,
                "reference_id": str(reference_id),
            }
        )
        
        return entry
    
    async def post_transaction(
        self,
        entries: List[dict],
        reference_type: str,
        reference_id: UUID,
        transaction_date: Optional[datetime] = None
    ) -> List[LedgerEntry]:
        """
        Post a balanced transaction (multiple entries).
        
        Validates that debits equal credits before posting.
        
        S5.5-3: Enhanced integrity check - raises LedgerIntegrityError if unbalanced.
        
        Args:
            entries: List of entry dicts with 'account_type', 'amount', 'description'
            reference_type: Type of reference ('order', 'payment', 'refund')
            reference_id: UUID of referenced entity
            transaction_date: Date/time of transaction (defaults to now)
        
        Returns:
            List of created LedgerEntry objects
        
        Raises:
            LedgerIntegrityError: If transaction is not balanced (debits != credits)
        
        Example:
            await ledger_service.post_transaction(
                entries=[
                    {
                        'account_type': AccountType.RECEIVABLE,
                        'amount': Decimal('100.00'),  # Debit
                        'description': 'Customer owes for Order #123'
                    },
                    {
                        'account_type': AccountType.REVENUE,
                        'amount': Decimal('-100.00'),  # Credit
                        'description': 'Revenue recognized for Order #123'
                    }
                ],
                reference_type='order',
                reference_id=order_id
            )
        """
        # S5.5-3: Enforce ledger integrity - transaction must be balanced
        total = sum(Decimal(str(e['amount'])) for e in entries)
        if total != Decimal('0'):
            error_msg = (
                f"Transaction is not balanced: total={total}. "
                f"Debits must equal credits (net should be 0). "
                f"Philosophy: 'The Ledger is write-only. No exceptions.'"
            )
            logger.error(
                "Ledger integrity violation",
                extra={
                    "reference_type": reference_type,
                    "reference_id": str(reference_id),
                    "total": str(total),
                    "entry_count": len(entries),
                }
            )
            raise LedgerIntegrityError(error_msg)
        
        # Post all entries
        posted_entries = []
        for entry_data in entries:
            entry = await self.post_entry(
                account_type=entry_data['account_type'],
                amount=Decimal(str(entry_data['amount'])),
                reference_type=reference_type,
                reference_id=reference_id,
                description=entry_data.get('description'),
                transaction_date=transaction_date
            )
            posted_entries.append(entry)
        
        logger.info(
            f"Posted balanced transaction with {len(posted_entries)} entries",
            extra={
                "reference_type": reference_type,
                "reference_id": str(reference_id),
                "entry_count": len(posted_entries),
            }
        )
        
        return posted_entries
    
    async def get_balance(
        self,
        account_type: AccountType,
        as_of_date: Optional[datetime] = None
    ) -> Decimal:
        """
        Calculate account balance by summing all ledger entries.
        
        This is a READ MODEL - balance is calculated, not stored.
        
        Args:
            account_type: Account type to calculate balance for
            as_of_date: Calculate balance as of this date (defaults to now)
        
        Returns:
            Current balance for the account
        
        Example:
            receivable_balance = await ledger_service.get_balance(AccountType.RECEIVABLE)
            # Returns sum of all RECEIVABLE entries (positive = customer owes us)
        """
        query = select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.account_type == account_type
        )
        
        if as_of_date:
            query = query.where(LedgerEntry.transaction_date <= as_of_date)
        
        result = await self.db.execute(query)
        balance = result.scalar()
        
        # Ensure we return a Decimal, not None
        return Decimal(str(balance)) if balance is not None else Decimal('0')
    
    async def get_entries_for_reference(
        self,
        reference_type: str,
        reference_id: UUID
    ) -> List[LedgerEntry]:
        """
        Get all ledger entries for a specific reference.
        
        Useful for auditing and debugging.
        
        Args:
            reference_type: Type of reference ('order', 'payment', 'refund')
            reference_id: UUID of referenced entity
        
        Returns:
            List of LedgerEntry objects
        """
        result = await self.db.execute(
            select(LedgerEntry)
            .where(LedgerEntry.reference_type == reference_type)
            .where(LedgerEntry.reference_id == reference_id)
            .order_by(LedgerEntry.transaction_date)
        )
        
        return list(result.scalars().all())
    
    async def post_order_confirmation(
        self,
        order_id: UUID,
        amount: Decimal,
        description: Optional[str] = None
    ) -> List[LedgerEntry]:
        """
        Post ledger entries for order confirmation.
        
        Double-entry:
        - Debit RECEIVABLE (Customer owes us)
        - Credit REVENUE (We earned revenue)
        
        Args:
            order_id: Order UUID
            amount: Order total amount
            description: Optional description
        
        Returns:
            List of posted entries
        """
        return await self.post_transaction(
            entries=[
                {
                    'account_type': AccountType.RECEIVABLE,
                    'amount': amount,  # Debit (positive)
                    'description': description or f'Receivable for order {order_id}'
                },
                {
                    'account_type': AccountType.REVENUE,
                    'amount': -amount,  # Credit (negative)
                    'description': description or f'Revenue for order {order_id}'
                }
            ],
            reference_type='order',
            reference_id=order_id
        )
    
    async def post_payment_received(
        self,
        order_id: UUID,
        amount: Decimal,
        description: Optional[str] = None
    ) -> List[LedgerEntry]:
        """
        Post ledger entries for payment received.
        
        Double-entry:
        - Debit CASH (We received money)
        - Credit RECEIVABLE (Customer no longer owes)
        
        Args:
            order_id: Order UUID
            amount: Payment amount
            description: Optional description
        
        Returns:
            List of posted entries
        """
        return await self.post_transaction(
            entries=[
                {
                    'account_type': AccountType.CASH,
                    'amount': amount,  # Debit (positive)
                    'description': description or f'Payment received for order {order_id}'
                },
                {
                    'account_type': AccountType.RECEIVABLE,
                    'amount': -amount,  # Credit (negative)
                    'description': description or f'Payment applied to order {order_id}'
                }
            ],
            reference_type='order',
            reference_id=order_id
        )
