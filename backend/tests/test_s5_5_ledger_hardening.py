"""
S5.5: Ledger Hardening Tests

Tests for database-level immutability and application-level integrity.

Philosophy: "The Ledger is write-only. No exceptions."

Test Cases:
1. Database-level immutability (trigger blocks UPDATE)
2. Database-level immutability (trigger blocks DELETE)
3. Application-level integrity (unbalanced transaction rejected)
4. Versioning columns exist and work correctly
5. Hash column exists (placeholder for future use)
6. Existing S5-B tests still pass (regression check)
"""
import pytest
import uuid
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, InternalError

from models.ledger import LedgerEntry, AccountType
from services.ledger_service import LedgerService
from core.exceptions import LedgerIntegrityError


# ============================================================================
# Test Case 1: Database-Level Immutability - UPDATE Blocked
# ============================================================================

@pytest.mark.asyncio
async def test_database_blocks_update_operations(async_session):
    """
    S5.5-1: Test that database trigger prevents UPDATE operations.
    
    Philosophy: "The Ledger is write-only. No exceptions."
    
    Verifies:
    - Ledger entry can be inserted
    - Raw SQL UPDATE is blocked by trigger
    - Trigger raises appropriate exception
    """
    service = LedgerService(async_session)
    
    # Insert a ledger entry
    order_id = uuid.uuid4()
    entry = await service.post_entry(
        account_type=AccountType.RECEIVABLE,
        amount=Decimal("100.00"),
        reference_type="order",
        reference_id=order_id,
        description="Test entry for immutability"
    )
    
    # Commit to ensure entry is persisted
    await async_session.commit()
    
    # Attempt to UPDATE the entry using raw SQL
    # This should be blocked by the trigger
    with pytest.raises((IntegrityError, InternalError)) as exc_info:
        await async_session.execute(
            text(f"""
                UPDATE ledger_entries 
                SET amount = 200.00 
                WHERE id = :entry_id
            """),
            {"entry_id": entry.id}
        )
        await async_session.commit()
    
    # Verify the exception message mentions immutability
    error_msg = str(exc_info.value).lower()
    assert "immutable" in error_msg or "not allowed" in error_msg
    
    # Rollback the failed transaction
    await async_session.rollback()
    
    # Verify the entry is unchanged
    await async_session.refresh(entry)
    assert entry.amount == Decimal("100.00")


# ============================================================================
# Test Case 2: Database-Level Immutability - DELETE Blocked
# ============================================================================

@pytest.mark.asyncio
async def test_database_blocks_delete_operations(async_session):
    """
    S5.5-1: Test that database trigger prevents DELETE operations.
    
    Philosophy: "The Ledger is write-only. No exceptions."
    
    Verifies:
    - Ledger entry can be inserted
    - Raw SQL DELETE is blocked by trigger
    - Trigger raises appropriate exception
    """
    service = LedgerService(async_session)
    
    # Insert a ledger entry
    order_id = uuid.uuid4()
    entry = await service.post_entry(
        account_type=AccountType.RECEIVABLE,
        amount=Decimal("100.00"),
        reference_type="order",
        reference_id=order_id,
        description="Test entry for immutability"
    )
    
    entry_id = entry.id
    
    # Commit to ensure entry is persisted
    await async_session.commit()
    
    # Attempt to DELETE the entry using raw SQL
    # This should be blocked by the trigger
    with pytest.raises((IntegrityError, InternalError)) as exc_info:
        await async_session.execute(
            text(f"""
                DELETE FROM ledger_entries 
                WHERE id = :entry_id
            """),
            {"entry_id": entry_id}
        )
        await async_session.commit()
    
    # Verify the exception message mentions immutability
    error_msg = str(exc_info.value).lower()
    assert "immutable" in error_msg or "not allowed" in error_msg
    
    # Rollback the failed transaction
    await async_session.rollback()
    
    # Verify the entry still exists
    result = await async_session.execute(
        text("SELECT COUNT(*) FROM ledger_entries WHERE id = :entry_id"),
        {"entry_id": entry_id}
    )
    count = result.scalar()
    assert count == 1


# ============================================================================
# Test Case 3: Application-Level Integrity - Unbalanced Transaction
# ============================================================================

@pytest.mark.asyncio
async def test_application_rejects_unbalanced_transaction(async_session):
    """
    S5.5-3: Test that LedgerService rejects unbalanced transactions.
    
    Philosophy: "The Ledger is write-only. No exceptions."
    
    Verifies:
    - Unbalanced transaction (Debit +100, Credit -90) is rejected
    - LedgerIntegrityError is raised
    - No entries are created in database
    """
    service = LedgerService(async_session)
    
    order_id = uuid.uuid4()
    
    # Count entries before
    result = await async_session.execute(
        text("SELECT COUNT(*) FROM ledger_entries")
    )
    count_before = result.scalar()
    
    # Attempt to post unbalanced transaction
    with pytest.raises(LedgerIntegrityError) as exc_info:
        await service.post_transaction(
            entries=[
                {
                    'account_type': AccountType.RECEIVABLE,
                    'amount': Decimal('100.00'),  # Debit
                    'description': 'Customer owes'
                },
                {
                    'account_type': AccountType.REVENUE,
                    'amount': Decimal('-90.00'),  # Credit (WRONG AMOUNT)
                    'description': 'Revenue earned'
                }
            ],
            reference_type='order',
            reference_id=order_id
        )
    
    # Verify error message
    error_msg = str(exc_info.value).lower()
    assert "not balanced" in error_msg
    assert "write-only" in error_msg or "no exceptions" in error_msg
    
    # Verify no entries were created
    result = await async_session.execute(
        text("SELECT COUNT(*) FROM ledger_entries")
    )
    count_after = result.scalar()
    assert count_after == count_before


# ============================================================================
# Test Case 4: Versioning Columns Work Correctly
# ============================================================================

@pytest.mark.asyncio
async def test_entry_version_column_exists_and_defaults(async_session):
    """
    S5.5-2: Test that entry_version column exists and defaults to 1.
    
    Verifies:
    - entry_version column exists
    - Defaults to 1 for new entries
    - Can be read back correctly
    """
    service = LedgerService(async_session)
    
    # Insert a ledger entry
    order_id = uuid.uuid4()
    entry = await service.post_entry(
        account_type=AccountType.CASH,
        amount=Decimal("50.00"),
        reference_type="order",
        reference_id=order_id,
        description="Test entry for versioning"
    )
    
    # Verify entry_version defaults to 1
    assert hasattr(entry, 'entry_version')
    assert entry.entry_version == 1


@pytest.mark.asyncio
async def test_hash_column_exists_and_nullable(async_session):
    """
    S5.5-2: Test that hash column exists and is nullable.
    
    Verifies:
    - hash column exists
    - Is nullable (None by default)
    - Can be read back correctly
    """
    service = LedgerService(async_session)
    
    # Insert a ledger entry
    order_id = uuid.uuid4()
    entry = await service.post_entry(
        account_type=AccountType.CASH,
        amount=Decimal("50.00"),
        reference_type="order",
        reference_id=order_id,
        description="Test entry for hash column"
    )
    
    # Verify hash column exists and is None
    assert hasattr(entry, 'hash')
    assert entry.hash is None


# ============================================================================
# Test Case 5: Balanced Transactions Still Work (Regression)
# ============================================================================

@pytest.mark.asyncio
async def test_balanced_transaction_still_works(async_session):
    """
    S5.5: Regression test - balanced transactions still work after hardening.
    
    Verifies:
    - Balanced transactions are accepted
    - Entries are created correctly
    - All S5-B functionality remains intact
    """
    service = LedgerService(async_session)
    
    order_id = uuid.uuid4()
    
    # Post balanced transaction
    entries = await service.post_transaction(
        entries=[
            {
                'account_type': AccountType.RECEIVABLE,
                'amount': Decimal('100.00'),  # Debit
                'description': 'Customer owes'
            },
            {
                'account_type': AccountType.REVENUE,
                'amount': Decimal('-100.00'),  # Credit
                'description': 'Revenue earned'
            }
        ],
        reference_type='order',
        reference_id=order_id
    )
    
    # Verify entries were created
    assert len(entries) == 2
    assert entries[0].amount == Decimal('100.00')
    assert entries[1].amount == Decimal('-100.00')
    
    # Verify transaction is balanced
    total = sum(e.amount for e in entries)
    assert total == Decimal('0')
    
    # Verify versioning columns are set
    assert all(e.entry_version == 1 for e in entries)
    assert all(e.hash is None for e in entries)


# ============================================================================
# Test Case 6: Multiple Unbalanced Scenarios
# ============================================================================

@pytest.mark.asyncio
async def test_various_unbalanced_scenarios(async_session):
    """
    S5.5-3: Test various unbalanced transaction scenarios.
    
    Verifies:
    - Positive imbalance rejected
    - Negative imbalance rejected
    - Single-entry transaction rejected (must have at least 2 entries)
    """
    service = LedgerService(async_session)
    
    order_id = uuid.uuid4()
    
    # Scenario 1: Positive imbalance (more debits than credits)
    with pytest.raises(LedgerIntegrityError):
        await service.post_transaction(
            entries=[
                {'account_type': AccountType.RECEIVABLE, 'amount': Decimal('100.00')},
                {'account_type': AccountType.REVENUE, 'amount': Decimal('-50.00')}
            ],
            reference_type='order',
            reference_id=order_id
        )
    
    # Scenario 2: Negative imbalance (more credits than debits)
    with pytest.raises(LedgerIntegrityError):
        await service.post_transaction(
            entries=[
                {'account_type': AccountType.RECEIVABLE, 'amount': Decimal('50.00')},
                {'account_type': AccountType.REVENUE, 'amount': Decimal('-100.00')}
            ],
            reference_type='order',
            reference_id=order_id
        )
    
    # Scenario 3: Single entry (not balanced)
    with pytest.raises(LedgerIntegrityError):
        await service.post_transaction(
            entries=[
                {'account_type': AccountType.CASH, 'amount': Decimal('100.00')}
            ],
            reference_type='order',
            reference_id=order_id
        )


# ============================================================================
# Test Case 7: Trigger Function Exists in Database
# ============================================================================

@pytest.mark.asyncio
async def test_trigger_function_exists(async_session):
    """
    S5.5-1: Verify that the trigger function exists in the database.
    
    Verifies:
    - prevent_ledger_modification() function exists in public schema
    - Function is properly defined
    """
    result = await async_session.execute(
        text("""
            SELECT COUNT(*) 
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE n.nspname = 'public' 
            AND p.proname = 'prevent_ledger_modification'
        """)
    )
    count = result.scalar()
    
    assert count == 1, "Trigger function prevent_ledger_modification() not found in public schema"


@pytest.mark.asyncio
async def test_trigger_attached_to_table(async_session):
    """
    S5.5-1: Verify that the trigger is attached to ledger_entries table.
    
    Verifies:
    - Trigger exists on ledger_entries table
    - Trigger is configured for BEFORE UPDATE OR DELETE
    """
    result = await async_session.execute(
        text("""
            SELECT COUNT(*) 
            FROM pg_trigger t
            JOIN pg_class c ON t.tgrelid = c.oid
            WHERE c.relname = 'ledger_entries'
            AND t.tgname = 'prevent_ledger_modification_trigger'
        """)
    )
    count = result.scalar()
    
    assert count >= 1, "Trigger prevent_ledger_modification_trigger not found on ledger_entries table"


# ============================================================================
# Test Case 8: Edge Cases
# ============================================================================

@pytest.mark.asyncio
async def test_zero_amount_entries_allowed_if_balanced(async_session):
    """
    S5.5: Test that zero-amount entries are allowed if transaction is balanced.
    
    Edge case: Some accounting systems allow zero-amount entries for memo purposes.
    """
    service = LedgerService(async_session)
    
    order_id = uuid.uuid4()
    
    # Post transaction with zero amounts (balanced)
    entries = await service.post_transaction(
        entries=[
            {'account_type': AccountType.RECEIVABLE, 'amount': Decimal('0.00')},
            {'account_type': AccountType.REVENUE, 'amount': Decimal('0.00')}
        ],
        reference_type='order',
        reference_id=order_id
    )
    
    assert len(entries) == 2
    assert all(e.amount == Decimal('0.00') for e in entries)


@pytest.mark.asyncio
async def test_high_precision_amounts_balanced_correctly(async_session):
    """
    S5.5: Test that high-precision amounts (4 decimal places) are balanced correctly.
    
    Verifies:
    - Numeric(20, 4) precision is maintained
    - Balance check works with high precision
    """
    service = LedgerService(async_session)
    
    order_id = uuid.uuid4()
    
    # Post transaction with high-precision amounts
    entries = await service.post_transaction(
        entries=[
            {'account_type': AccountType.RECEIVABLE, 'amount': Decimal('100.1234')},
            {'account_type': AccountType.REVENUE, 'amount': Decimal('-100.1234')}
        ],
        reference_type='order',
        reference_id=order_id
    )
    
    assert len(entries) == 2
    assert entries[0].amount == Decimal('100.1234')
    assert entries[1].amount == Decimal('-100.1234')
    
    # Verify balance
    total = sum(e.amount for e in entries)
    assert total == Decimal('0.0000')
