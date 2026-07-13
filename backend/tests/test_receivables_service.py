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


TEST_WHOLESALER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


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
    result = await receivables_service.get_receivables_summary(
        tenant_db=mock_db_session,
        wholesaler_id=TEST_WHOLESALER_ID,
    )

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

    result = await receivables_service.get_receivables_summary(
        tenant_db=mock_db_session,
        wholesaler_id=TEST_WHOLESALER_ID,
    )

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

    result = await receivables_service.get_receivables_summary(
        tenant_db=mock_db_session,
        wholesaler_id=TEST_WHOLESALER_ID,
    )

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
        wholesaler_id=TEST_WHOLESALER_ID,
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
        wholesaler_id=TEST_WHOLESALER_ID,
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
        wholesaler_id=TEST_WHOLESALER_ID,
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
        wholesaler_id=TEST_WHOLESALER_ID,
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
        wholesaler_id=TEST_WHOLESALER_ID,
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
    await receivables_service.get_receivables_summary(
        tenant_db=mock_db_session,
        wholesaler_id=TEST_WHOLESALER_ID,
    )
    await receivables_service.list_receivable_orders(
        tenant_db=mock_db_session,
        wholesaler_id=TEST_WHOLESALER_ID,
    )

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
    await receivables_service.get_receivables_summary(
        tenant_db=mock_db_session,
        wholesaler_id=TEST_WHOLESALER_ID,
    )
    await receivables_service.list_receivable_orders(
        tenant_db=mock_db_session,
        wholesaler_id=TEST_WHOLESALER_ID,
    )

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


# ---------------------------------------------------------------------------
# 6. Classification Pagination Tests (CTO Round 2 Polish)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_classification_pagination_across_db_pages(mock_db_session, receivables_service):
    """Classification filter finds items beyond first DB page and computes correct total."""
    retailer_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

    # Create 25 orders total (2 pages when page_size=20)
    # First 10 orders: credit_receivable
    # Next 10 orders: unpaid_order
    # Last 5 orders: credit_receivable (on page 2)
    mock_orders = []
    for i in range(25):
        mock_order = MagicMock()
        mock_order.id = uuid.UUID(f"{i:032x}")  # Generate UUID from index
        mock_order.retailer_id = retailer_id
        mock_order.status = "confirmed"
        mock_order.total_amount = Decimal("1000.00")
        mock_order.created_at = datetime.utcnow()
        mock_orders.append(mock_order)

    mock_orders_result = MagicMock()
    mock_orders_result.scalars.return_value.all.return_value = mock_orders

    # Mock credit payments for orders 0-9 and 20-24 (credit_receivable)
    credit_orders = [mock_orders[i].id for i in range(10)] + [mock_orders[i].id for i in range(20, 25)]
    mock_credit_result = MagicMock()
    mock_credit_result.mappings.return_value.all.return_value = [
        {"order_id": order_id, "credit_total": Decimal("500.00")}
        for order_id in credit_orders
    ]

    # Mock cash payments for all orders
    mock_cash_result = MagicMock()
    mock_cash_result.mappings.return_value.all.return_value = [
        {"order_id": order.id, "cash_total": Decimal("500.00")}
        for order in mock_orders
    ]

    mock_retailer_result = MagicMock()
    mock_retailer_result.mappings.return_value.all.return_value = [
        {"retailer_id": retailer_id, "retailer_name": "Test Retailer"},
    ]

    def mock_execute(query, params=None):
        query_str = str(query)
        # For classification filter, we should fetch ALL orders (no pagination)
        if "orders" in query_str.lower() and "count(" not in query_str.lower():
            return mock_orders_result
        elif "credit" in query_str.lower():
            return mock_credit_result
        elif "cash" in query_str.lower():
            return mock_cash_result
        elif "retailers" in query_str.lower():
            return mock_retailer_result
        return MagicMock()

    mock_db_session.execute.side_effect = mock_execute

    # Request page 1 with credit_receivable classification
    # Should find 15 credit_receivable orders (10 on page 1, 5 on page 2)
    result = await receivables_service.list_receivable_orders(
        tenant_db=mock_db_session,
        wholesaler_id=TEST_WHOLESALER_ID,
        page=1,
        size=10,
        classification="credit_receivable",
    )

    # Verify pagination reflects all 15 credit_receivable orders, not just first page
    assert result["pagination"]["total"] == 15
    assert result["pagination"]["pages"] == 2  # ceil(15/10) = 2
    assert result["pagination"]["page"] == 1
    assert result["pagination"]["size"] == 10

    # Verify we get 10 items on page 1
    assert len(result["items"]) == 10

    # Verify all items are credit_receivable
    for item in result["items"]:
        assert item["classification"] == "credit_receivable"


@pytest.mark.asyncio
async def test_classification_pagination_page_beyond_first_db_page(mock_db_session, receivables_service):
    """Classification filter page 2 returns items from DB page 2 that match classification."""
    retailer_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

    # Create 25 orders total (2 pages when page_size=20)
    # First 10 orders: credit_receivable
    # Next 10 orders: unpaid_order
    # Last 5 orders: credit_receivable (on page 2)
    mock_orders = []
    for i in range(25):
        mock_order = MagicMock()
        mock_order.id = uuid.UUID(f"{i:032x}")
        mock_order.retailer_id = retailer_id
        mock_order.status = "confirmed"
        mock_order.total_amount = Decimal("1000.00")
        mock_order.created_at = datetime.utcnow()
        mock_orders.append(mock_order)

    mock_orders_result = MagicMock()
    mock_orders_result.scalars.return_value.all.return_value = mock_orders

    # Mock credit payments for orders 0-9 and 20-24 (credit_receivable)
    credit_orders = [mock_orders[i].id for i in range(10)] + [mock_orders[i].id for i in range(20, 25)]
    mock_credit_result = MagicMock()
    mock_credit_result.mappings.return_value.all.return_value = [
        {"order_id": order_id, "credit_total": Decimal("500.00")}
        for order_id in credit_orders
    ]

    # Mock cash payments for all orders
    mock_cash_result = MagicMock()
    mock_cash_result.mappings.return_value.all.return_value = [
        {"order_id": order.id, "cash_total": Decimal("500.00")}
        for order in mock_orders
    ]

    mock_retailer_result = MagicMock()
    mock_retailer_result.mappings.return_value.all.return_value = [
        {"retailer_id": retailer_id, "retailer_name": "Test Retailer"},
    ]

    def mock_execute(query, params=None):
        query_str = str(query)
        if "orders" in query_str.lower() and "count(" not in query_str.lower():
            return mock_orders_result
        elif "credit" in query_str.lower():
            return mock_credit_result
        elif "cash" in query_str.lower():
            return mock_cash_result
        elif "retailers" in query_str.lower():
            return mock_retailer_result
        return MagicMock()

    mock_db_session.execute.side_effect = mock_execute

    # Request page 2 with credit_receivable classification
    # Should return the remaining 5 credit_receivable orders from DB page 2
    result = await receivables_service.list_receivable_orders(
        tenant_db=mock_db_session,
        wholesaler_id=TEST_WHOLESALER_ID,
        page=2,
        size=10,
        classification="credit_receivable",
    )

    # Verify pagination
    assert result["pagination"]["total"] == 15
    assert result["pagination"]["pages"] == 2
    assert result["pagination"]["page"] == 2
    assert result["pagination"]["size"] == 10

    # Verify we get 5 items on page 2
    assert len(result["items"]) == 5

    # Verify all items are credit_receivable
    for item in result["items"]:
        assert item["classification"] == "credit_receivable"


# ---------------------------------------------------------------------------
# 7. Empty Order ID Collection Safety Tests (CTO Round 2 Polish)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_receivables_summary_empty_orders_safe(mock_db_session, receivables_service):
    """Receivables summary handles empty order_ids collection safely (no raw SQL with ANY)."""
    # Mock bindings with outstanding balance but no orders
    mock_binding_result = MagicMock()
    mock_binding_result.mappings.return_value.all.return_value = [
        {
            "retailer_id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
            "outstanding_balance": Decimal("5000.00"),
            "retailer_name": "Retailer A",
        },
    ]

    # Mock empty orders result
    mock_orders_result = MagicMock()
    mock_orders_result.all.return_value = []

    def mock_execute(query, params=None):
        query_str = str(query)
        if "wholesaler_retailer_bindings" in query_str:
            return mock_binding_result
        elif "orders" in query_str:
            return mock_orders_result
        return MagicMock()

    mock_db_session.execute.side_effect = mock_execute

    # Should not crash with empty order_ids collection
    result = await receivables_service.get_receivables_summary(
        tenant_db=mock_db_session,
        wholesaler_id=TEST_WHOLESALER_ID,
    )

    # Verify result structure with zero order data
    assert result["total_outstanding"] == 5000.00  # Still has binding balance
    assert result["retailer_count"] == 1
    assert result["order_count"] == 0  # No orders
    assert result["credit_receivables"] == 0.0
    assert result["unpaid_order_balance"] == 0.0
    assert len(result["by_retailer"]) == 1

    # Verify retailer entry has zero order data
    retailer = result["by_retailer"][0]
    assert retailer["credit_receivables"] == 0.0
    assert retailer["unpaid_order_balance"] == 0.0
    assert retailer["order_count"] == 0


@pytest.mark.asyncio
async def test_receivables_summary_binding_only_tenant_safe(mock_db_session, receivables_service):
    """Receivables summary for binding-only tenant (no orders) returns safely."""
    # Mock tenant with bindings but completely empty orders table
    mock_binding_result = MagicMock()
    mock_binding_result.mappings.return_value.all.return_value = [
        {
            "retailer_id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
            "outstanding_balance": Decimal("10000.00"),
            "retailer_name": "Binding Only Retailer",
        },
    ]

    mock_orders_result = MagicMock()
    mock_orders_result.all.return_value = []

    def mock_execute(query, params=None):
        query_str = str(query)
        if "wholesaler_retailer_bindings" in query_str:
            return mock_binding_result
        elif "orders" in query_str:
            return mock_orders_result
        return MagicMock()

    mock_db_session.execute.side_effect = mock_execute

    # Should not attempt payment aggregation with empty order_ids
    result = await receivables_service.get_receivables_summary(
        tenant_db=mock_db_session,
        wholesaler_id=TEST_WHOLESALER_ID,
    )

    # Verify safe return with binding data but zero order breakdown
    assert result["total_outstanding"] == 10000.00
    assert result["retailer_count"] == 1
    assert result["order_count"] == 0
    assert result["credit_receivables"] == 0.0
    assert result["unpaid_order_balance"] == 0.0


@pytest.mark.asyncio
async def test_receivable_orders_empty_result_safe(mock_db_session, receivables_service):
    """Receivable orders list handles empty result safely (no payment aggregation queries)."""
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 0

    def mock_execute(query, params=None):
        query_str = str(query)
        if "count(" in query_str.lower() or "count(" in query_str:
            return mock_count_result
        return MagicMock()

    mock_db_session.execute.side_effect = mock_execute

    # Should not crash with empty orders
    result = await receivables_service.list_receivable_orders(
        tenant_db=mock_db_session,
        wholesaler_id=TEST_WHOLESALER_ID,
        page=1,
        size=20,
    )

    # Verify empty result structure
    assert result["items"] == []
    assert result["pagination"]["total"] == 0
    assert result["pagination"]["pages"] == 0
    assert result["pagination"]["page"] == 1
    assert result["pagination"]["size"] == 20
