"""
S6-P4: Reporting Constraints Tests

Tests for database-level read-only enforcement and query timeout.

Philosophy: "Reporting reads the truth. It never writes it."

Test Cases:
1. reporting_role CANNOT execute INSERT on ledger_entries
2. reporting_role CANNOT execute UPDATE on ledger_entries
3. reporting_role CANNOT execute DELETE on ledger_entries
4. reporting_role CAN execute SELECT on ledger_entries
5. reporting_role query exceeding 30s is cancelled (pg_sleep test)
6. reporting_role has correct statement_timeout setting
7. reporting_currency_code constant is defined
"""
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from database.reporting_session import (
    REPORTING_CURRENCY_CODE,
    _build_reporting_url,
)
pytest_plugins = ("tests.reporting_bootstrap_contract_helpers",)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="module")
async def reporting_engine(ensure_reporting_user_password):
    """Create a reporting engine using the explicit test reporting DSN."""
    url = _build_reporting_url()
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def reporting_session(reporting_user_tenant_session: AsyncSession):
    """Provide a reporting_user session via the supported test helper."""
    yield reporting_user_tenant_session


# ============================================================================
# Test Case 1: reporting_user CANNOT INSERT
# ============================================================================

@pytest.mark.asyncio
async def test_reporting_user_cannot_insert(reporting_session):
    """
    S6-P2: Verify reporting_user cannot INSERT into ledger_entries.

    The reporting_role only has SELECT privileges. Any write operation
    must be rejected by PostgreSQL with a permission error.
    """
    with pytest.raises(Exception) as exc_info:
        await reporting_session.execute(
            text("""
                INSERT INTO ledger_entries
                (id, transaction_date, account_type, amount, reference_type,
                 reference_id, description, created_at, updated_at,
                 is_deleted, entry_version)
                VALUES (gen_random_uuid(), NOW(), 'receivable', 100.00,
                        'pentest', gen_random_uuid(),
                        'Should fail - reporting is read-only',
                        NOW(), NOW(), false, 1)
            """)
        )
        await reporting_session.commit()

    error_msg = str(exc_info.value).lower()
    assert "permission denied" in error_msg or "read-only" in error_msg, (
        f"Expected permission denied or read-only error, got: {exc_info.value}"
    )


# ============================================================================
# Test Case 2: reporting_user CANNOT UPDATE
# ============================================================================

@pytest.mark.asyncio
async def test_reporting_user_cannot_update(reporting_session):
    """
    S6-P2: Verify reporting_user cannot UPDATE ledger_entries.

    Even if the immutability trigger didn't exist, the role-level
    permissions should block this.
    """
    with pytest.raises(Exception) as exc_info:
        await reporting_session.execute(
            text("""
                UPDATE ledger_entries SET amount = 999999
                WHERE id = (SELECT id FROM ledger_entries LIMIT 1)
            """)
        )
        await reporting_session.commit()

    error_msg = str(exc_info.value).lower()
    assert "permission denied" in error_msg or "read-only" in error_msg, (
        f"Expected permission denied or read-only error, got: {exc_info.value}"
    )


# ============================================================================
# Test Case 3: reporting_user CANNOT DELETE
# ============================================================================

@pytest.mark.asyncio
async def test_reporting_user_cannot_delete(reporting_session):
    """
    S6-P2: Verify reporting_user cannot DELETE from ledger_entries.

    Triple protection: role permissions + read-only transaction + S5.5 trigger.
    """
    with pytest.raises(Exception) as exc_info:
        await reporting_session.execute(
            text("""
                DELETE FROM ledger_entries
                WHERE id = (SELECT id FROM ledger_entries LIMIT 1)
            """)
        )
        await reporting_session.commit()

    error_msg = str(exc_info.value).lower()
    assert "permission denied" in error_msg or "read-only" in error_msg, (
        f"Expected permission denied or read-only error, got: {exc_info.value}"
    )


# ============================================================================
# Test Case 4: reporting_user CAN SELECT
# ============================================================================

@pytest.mark.asyncio
async def test_reporting_user_can_select(reporting_session):
    """
    S6-P2: Verify reporting_user CAN execute SELECT queries.

    The whole point of the reporting role is to allow reads.
    """
    result = await reporting_session.execute(
        text("SELECT COUNT(*) FROM ledger_entries")
    )
    count = result.scalar()

    # Count should be a non-negative integer (table may be empty or have data)
    assert count >= 0
    assert isinstance(count, int)


# ============================================================================
# Test Case 5: Timeout enforcement (pg_sleep > 30s)
# ============================================================================

@pytest.mark.asyncio
async def test_reporting_query_timeout(reporting_engine):
    """
    S6-P2: Verify that queries exceeding 30s are cancelled.

    The reporting_role has statement_timeout = 30000 (30s).
    pg_sleep(35) should trigger a cancellation.

    Note: This test takes ~30s to complete (it waits for the timeout).
    """
    factory = async_sessionmaker(
        reporting_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        with pytest.raises(Exception) as exc_info:
            # pg_sleep(35) will exceed the 30s timeout
            await session.execute(text("SELECT pg_sleep(35)"))

        error_msg = str(exc_info.value).lower()
        assert (
            "cancel" in error_msg
            or "timeout" in error_msg
            or "statement timeout" in error_msg
        ), f"Expected timeout/cancel error, got: {exc_info.value}"


# ============================================================================
# Test Case 6: Verify statement_timeout is set on the role
# ============================================================================

@pytest.mark.asyncio
async def test_reporting_role_has_timeout(reporting_session):
    """
    S6-P2: Verify the reporting_role has statement_timeout configured.

    Checks pg_catalog for the role-level setting.
    """
    result = await reporting_session.execute(text("SHOW statement_timeout"))
    timeout_value = result.scalar()

    # Should be '30s' or '30000ms' depending on PostgreSQL formatting
    assert timeout_value is not None
    # PostgreSQL returns '30s' or '30000ms'
    assert "30" in timeout_value, (
        f"Expected statement_timeout containing '30', got: {timeout_value}"
    )


# ============================================================================
# Test Case 7: Reporting currency code constant
# ============================================================================

def test_reporting_currency_code_defined():
    """
    S6-P1: Verify REPORTING_CURRENCY_CODE is defined and valid.

    All Read Models must include this value.
    """
    assert REPORTING_CURRENCY_CODE == "USD"
    assert len(REPORTING_CURRENCY_CODE) == 3
    assert REPORTING_CURRENCY_CODE.isalpha()
    assert REPORTING_CURRENCY_CODE.isupper()


# ============================================================================
# Test Case 8: reporting_user CAN read from public schema tables
# ============================================================================

@pytest.mark.asyncio
async def test_reporting_user_can_read_public_tables(reporting_engine):
    """
    S6-P2: Verify reporting_user can read public schema tables (e.g., sys_jobs).
    """
    factory = async_sessionmaker(
        reporting_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM public.sys_jobs")
        )
        count = result.scalar()
        assert count >= 0
