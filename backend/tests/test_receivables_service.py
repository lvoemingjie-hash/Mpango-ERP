"""
Receivables Service Tests - Phase 6.2 Round 2

Tests for read-only receivables visibility service:
- Retailer summary aggregates totals correctly
- Uses public binding outstanding_balance field
- Order list classifies credit receivables
- Order list classifies unpaid orders
- Order list supports retailer filter
- Pagination metadata is correct
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import uuid


@pytest.fixture
def mock_db_session():
    """Create a mock async session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def receivables_service():
    """Create ReceivablesService instance."""
    from services.receivables_service import ReceivablesService
    return ReceivablesService()


# ---------------------------------------------------------------------------
# 1. Retailer Summary Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retailer_summary_aggregates_totals(mock_db_session, receivables_service):
    """Retailer summary correctly aggregates totals across retailers."""
    # Mock binding query result
    mock_binding_result = MagicMock()
    mock_binding_result.mappings.return_value.all.return_value = [
        {
            "retailer_id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
            "outstanding_balance": Decimal("5000.00"),
            "retailer_name": "Retailer A",
        },
        {
            "retailer_id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
            "outstanding_balance": Decimal("3000.00"),
            "retailer_name": "Retailer B",
        },
    ]

    # Mock orders query result
    mock_orders_result = MagicMock()
    retailer_a_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    retailer_b_id = uuid.UUID("22222222-2222-2222-2222-222222222222")

    # Create mock orders
    mock_order_a = MagicMock()
    mock_order_a.retailer_id = retailer_a_id
    mock_order_a.id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    mock_order_a.status = "confirmed"
    mock_order_a.total_amount = Decimal("2000.00")
    mock_order_a.created_at = datetime.utcnow()

    mock_order_b = MagicMock()
    mock_order_b.retailer_id = retailer_b_id
    mock_order_b.id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    mock_order_b.status = "paid"
    mock_order_b.total_amount = Decimal("1500.00")
    mock_order_b.created_at = datetime.utcnow()

    mock_orders_result.all.return_value = [mock_order_a, mock_order_b]

    # Mock credit totals
    mock_credit_result = MagicMock()
    mock_credit_result.mappings.return_value.all.return_value = [
        {"order_id": mock_order_a.id, "credit_total": Decimal("1000.00")},
        {"order_id": mock_order_b.id, "credit_total": Decimal("500.00")},
    ]

    # Mock cash totals
    mock_cash_result = MagicMock()
    mock_cash_result.mappings.return_value.all.return_value = [
        {"order_id": mock_order_a.id, "cash_total": Decimal("500.00")},
        {"order_id": mock_order_b.id, "cash_total": Decimal("1500.00")},
    ]

    # Setup execute to return different results based on query
    def mock_execute(query, params=None):
        if "wholesaler_retailer_bindings" in str(query):
            return mock_binding_result
        elif "SELECT orders.retailer_id" in str(query) or "SELECT" in str(query) and "orders" in str(query):
            return mock_orders_result
        elif "method = 'credit'" in str(query):
            return mock_credit_result
        elif "method IN ('cash', 'transfer')" in str(query):
            return mock_cash_result
        return MagicMock()

    mock_db_session.execute.side_effect = mock_execute

    # Call service
    result = await receivables_service.get_receivables_summary(tenant_db=mock_db_session)

    # Verify structure
    assert "total_outstanding" in result
    assert "retailer_count" in result
    assert "order_count" in result
    assert "credit_receivables" in result
    assert "unpaid_order_balance" in result
    assert "by_retailer" in result

    # Verify totals
    assert result["total_outstanding"] == 8000.00  # 5000 + 3000
    assert result["retailer_count"] == 2
    assert result["order_count"] == 2
    assert result["credit_receivables"] == 1500.00  # 1000 + 500


@pytest.mark.asyncio
async def test_retailer_summary_uses_public_binding_outstanding_balance(mock_db_session, receivables_service):
    """Retailer summary uses public.wholesaler_retailer_bindings.outstanding_balance field."""
    # Mock binding query to return outstanding_balance from public schema
    mock_binding_result = MagicMock()
    mock_binding_result.mappings.return_value.all.return_value = [
        {
            "retailer_id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
            "outstanding_balance": Decimal("7500.50"),  # From public binding
            "retailer_name": "Test Retailer",
        },
    ]

    mock_orders_result = MagicMock()
    mock_orders_result.all.return_value = []

    mock_credit_result = MagicMock()
    mock_credit_result.mappings.return_value.all.return_value = []

    mock_cash_result = MagicMock()
    mock_cash_result.mappings.return_value.all.return_value = []

    def mock_execute(query, params=None):
        if "wholesaler_retailer_bindings" in str(query):
            # Verify query targets public schema
            assert "public.wholesaler_retailer_bindings" in str(query)
            assert "outstanding_balance" in str(query)
            return mock_binding_result
        elif "orders" in str(query):
            return mock_orders_result
        elif "credit" in str(query):
            return mock_credit_result
        elif "cash" in str(query):
            return mock_cash_result
        return MagicMock()

    mock_db_session.execute.side_effect = mock_execute

    result = await receivables_service.get_receivables_summary(tenant_db=mock_db_session)

    # Verify outstanding_balance from public binding is used
    assert result["total_outstanding"] == 7500.50
    assert len(result["by_retailer"]) == 1
    assert result["by_retailer"][0]["outstanding_balance"] == 7500.50


@pytest.mark.asyncio
async def test_retailer_summary_empty_when_no_bindings(mock_db_session, receivables_service):
    """Retailer summary returns empty structure when no bindings found."""
    mock_binding_result = MagicMock()
    mock_binding_result.mappings.return_value.all.return_value = []

    mock_db_session.execute.return_value = mock_binding_result

    result = await receivables_service.get_receivables_summary(tenant_db=mock_db_session)

    assert result["total_outstanding"] == 0.0
    assert result["retailer_count"] == 0
    assert result["order_count"] == 0
    assert result["credit_receivables"] == 0.0
    assert result["unpaid_order_balance"] == 0.0
    assert result["by_retailer"] == []


# ---------------------------------------------------------------------------
# 2. Order List Classification Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_order_list_classifies_credit_receivable(mock_db_session, receivables_service):
    """Order list correctly classifies credit_receivable orders."""
    order_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    retailer_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

    # Mock count
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 1

    # Mock orders
    mock_order = MagicMock()
    mock_order.id = order_id
    mock_order.retailer_id = retailer_id
    mock_order.status = "paid"  # PAID but with credit exposure
    mock_order.total_amount = Decimal("1000.00")
    mock_order.created_at = datetime.utcnow()

    mock_orders_result = MagicMock()
    mock_orders_result.scalars.return_value.all.return_value = [mock_order]

    # Mock credit payment (creates credit receivable exposure)
    mock_credit_result = MagicMock()
    mock_credit_result.mappings.return_value.all.return_value = [
        {"order_id": order_id, "credit_total": Decimal("800.00")},
    ]

    # Mock cash payment
    mock_cash_result = MagicMock()
    mock_cash_result.mappings.return_value.all.return_value = [
        {"order_id": order_id, "cash_total": Decimal("200.00")},
    ]

    # Mock retailer names
    mock_retailer_result = MagicMock()
    mock_retailer_result.mappings.return_value.all.return_value = [
        {"retailer_id": retailer_id, "retailer_name": "Test Retailer"},
    ]

    def mock_execute(query, params=None):
        query_str = str(query)
        # Match count queries first (before generic "orders" match)
        if "count(" in query_str.lower() or "count(" in query_str:
            return mock_count_result
        elif "FROM orders" in query_str or ("orders" in query_str.lower() and "count(" not in query_str.lower()):
            return mock_orders_result
        elif "method = 'credit'" in query_str or "credit" in query_str.lower():
            return mock_credit_result
        elif "method IN ('cash', 'transfer')" in query_str or "cash" in query_str.lower():
            return mock_cash_result
        elif "retailers" in query_str:
            return mock_retailer_result
        return MagicMock()

    mock_db_session.execute.side_effect = mock_execute

    result = await receivables_service.list_receivable_orders(
        tenant_db=mock_db_session,
        page=1,
        size=20,
    )

    assert len(result["items"]) == 1
    order = result["items"][0]
    assert order["classification"] == "credit_receivable"
    assert order["credit_amount"] == 800.00
    assert order["status"] == "paid"


@pytest.mark.asyncio
async def test_order_list_classifies_unpaid_order(mock_db_session, receivables_service):
    """Order list correctly classifies unpaid_order."""
    order_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    retailer_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 1

    # Mock confirmed order with unpaid balance
    mock_order = MagicMock()
    mock_order.id = order_id
    mock_order.retailer_id = retailer_id
    mock_order.status = "confirmed"
    mock_order.total_amount = Decimal("2000.00")
    mock_order.created_at = datetime.utcnow()

    mock_orders_result = MagicMock()
    mock_orders_result.scalars.return_value.all.return_value = [mock_order]

    # No credit payments
    mock_credit_result = MagicMock()
    mock_credit_result.mappings.return_value.all.return_value = []

    # Partial cash payment
    mock_cash_result = MagicMock()
    mock_cash_result.mappings.return_value.all.return_value = [
        {"order_id": order_id, "cash_total": Decimal("500.00")},
    ]

    mock_retailer_result = MagicMock()
    mock_retailer_result.mappings.return_value.all.return_value = [
        {"retailer_id": retailer_id, "retailer_name": "Test Retailer"},
    ]

    def mock_execute(query, params=None):
        query_str = str(query)
        # Match count queries first (before generic "orders" match)
        if "count(" in query_str.lower() or "count(" in query_str:
            return mock_count_result
        elif "orders" in query_str.lower() and "count(" not in query_str.lower():
            return mock_orders_result
        elif "credit" in query_str.lower():
            return mock_credit_result
        elif "cash" in query_str.lower():
            return mock_cash_result
        elif "retailers" in query_str.lower():
            return mock_retailer_result
        return MagicMock()

    mock_db_session.execute.side_effect = mock_execute

    result = await receivables_service.list_receivable_orders(
        tenant_db=mock_db_session,
        page=1,
        size=20,
    )

    assert len(result["items"]) == 1
    order = result["items"][0]
    assert order["classification"] == "unpaid_order"
    assert order["balance_due"] == 1500.00  # 2000 - 500
    assert order["status"] == "confirmed"


# ---------------------------------------------------------------------------
# 3. Filter Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_order_list_supports_retailer_filter(mock_db_session, receivables_service):
    """Order list supports retailer_id filter."""
    retailer_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 1

    mock_order = MagicMock()
    mock_order.id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    mock_order.retailer_id = retailer_id
    mock_order.status = "confirmed"
    mock_order.total_amount = Decimal("1000.00")
    mock_order.created_at = datetime.utcnow()

    mock_orders_result = MagicMock()
    mock_orders_result.scalars.return_value.all.return_value = [mock_order]

    mock_credit_result = MagicMock()
    mock_credit_result.mappings.return_value.all.return_value = []

    mock_cash_result = MagicMock()
    mock_cash_result.mappings.return_value.all.return_value = []

    mock_retailer_result = MagicMock()
    mock_retailer_result.mappings.return_value.all.return_value = [
        {"retailer_id": retailer_id, "retailer_name": "Test Retailer"},
    ]

    def mock_execute(query, params=None):
        query_str = str(query)
        # Match count queries first (before generic "orders" match)
        if "count(" in query_str.lower() or "count(" in query_str:
            return mock_count_result
        elif "orders" in query_str.lower() and "count(" not in query_str.lower():
            return mock_orders_result
        elif "credit" in query_str.lower():
            return mock_credit_result
        elif "cash" in query_str.lower():
            return mock_cash_result
        elif "retailers" in query_str.lower():
            return mock_retailer_result
        return MagicMock()

    mock_db_session.execute.side_effect = mock_execute

    result = await receivables_service.list_receivable_orders(
        tenant_db=mock_db_session,
        page=1,
        size=20,
        retailer_id=str(retailer_id),
    )

    assert len(result["items"]) == 1
    # Verify retailer filter was applied in the query
    assert any(
        str(retailer_id) in str(call)
        for call in mock_db_session.execute.call_args_list
    )


# ---------------------------------------------------------------------------
# 4. Pagination Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pagination_metadata_correct(mock_db_session, receivables_service):
    """Pagination metadata is calculated correctly."""
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 45  # 45 total items

    mock_orders_result = MagicMock()
    mock_orders_result.scalars.return_value.all.return_value = []

    mock_credit_result = MagicMock()
    mock_credit_result.mappings.return_value.all.return_value = []

    mock_cash_result = MagicMock()
    mock_cash_result.mappings.return_value.all.return_value = []

    mock_retailer_result = MagicMock()
    mock_retailer_result.mappings.return_value.all.return_value = []

    def mock_execute(query, params=None):
        query_str = str(query)
        # Match count queries first (before generic "orders" match)
        if "count(" in query_str.lower() or "count(" in query_str:
            return mock_count_result
        elif "orders" in query_str.lower() and "count(" not in query_str.lower():
            return mock_orders_result
        elif "credit" in query_str.lower():
            return mock_credit_result
        elif "cash" in query_str.lower():
            return mock_cash_result
        elif "retailers" in query_str.lower():
            return mock_retailer_result
        return MagicMock()

    mock_db_session.execute.side_effect = mock_execute

    # Test page 2, size 20
    result = await receivables_service.list_receivable_orders(
        tenant_db=mock_db_session,
        page=2,
        size=20,
    )

    assert result["pagination"]["page"] == 2
    assert result["pagination"]["size"] == 20
    assert result["pagination"]["total"] == 45
    assert result["pagination"]["pages"] == 3  # ceil(45/20) = 3


@pytest.mark.asyncio
async def test_pagination_empty_result(mock_db_session, receivables_service):
    """Pagination returns empty items and zero pages when no results."""
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 0

    def mock_execute(query, params=None):
        query_str = str(query)
        # Match count queries
        if "count(" in query_str.lower() or "count(" in query_str:
            return mock_count_result
        return MagicMock()

    mock_db_session.execute.side_effect = mock_execute

    result = await receivables_service.list_receivable_orders(
        tenant_db=mock_db_session,
        page=1,
        size=20,
    )

    assert result["items"] == []
    assert result["pagination"]["total"] == 0
    assert result["pagination"]["pages"] == 0


# ---------------------------------------------------------------------------
# 5. Read-Only Behavior Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_service_does_not_commit_or_rollback(mock_db_session, receivables_service):
    """Service never calls commit() or rollback() on the session."""
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 0

    mock_db_session.execute.return_value = mock_count_result

    # Call both methods
    await receivables_service.get_receivables_summary(tenant_db=mock_db_session)
    await receivables_service.list_receivable_orders(tenant_db=mock_db_session)

    # Verify no commit or rollback
    mock_db_session.commit.assert_not_called()
    mock_db_session.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_service_does_not_mutate_db_state(mock_db_session, receivables_service):
    """Service only uses SELECT queries, no INSERT/UPDATE/DELETE."""
    import re

    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 0

    mock_db_session.execute.return_value = mock_count_result

    # Call service methods
    await receivables_service.get_receivables_summary(tenant_db=mock_db_session)
    await receivables_service.list_receivable_orders(tenant_db=mock_db_session)

    # Verify all queries are SELECT (not INSERT/UPDATE/DELETE as standalone operations)
    for call in mock_db_session.execute.call_args_list:
        query_str = str(call[0][0]).strip()
        query_lower = query_str.lower()

        # Check that query starts with SELECT or WITH (CTE)
        assert query_lower.startswith("select") or query_lower.startswith("with") or query_lower.startswith("select(") or query_lower.startswith("with(")

        # Check for mutation operations as standalone statements (not in column names like "is_deleted")
        # Use regex to match DELETE/INSERT/UPDATE only as statement keywords
        mutation_pattern = r'\b(delete|insert|update)\b.*?\b(from|into|table|set)\b'
        assert not re.search(mutation_pattern, query_lower, re.IGNORECASE | re.DOTALL), \
            f"Found mutation operation in query: {query_str}"
