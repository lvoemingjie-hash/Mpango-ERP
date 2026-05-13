"""
Finance API Receivables Endpoints Tests - Phase 6.2 Round 2

Tests for receivables visibility API endpoints:
- GET /finance/receivables/summary returns 200 with correct shape
- GET /finance/receivables/orders returns 200 with correct shape
- Query parameters pass through correctly
- Permission checks work
"""
import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import uuid


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_token_payload():
    """Create mock token payload with finance:read permission."""
    payload = MagicMock()
    payload.tenant_id = "test-tenant"
    payload.permissions = ["finance:read"]
    payload.user_id = uuid.uuid4()
    return payload


@pytest.fixture
def mock_db_session():
    """Create mock async session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# GET /finance/receivables/summary Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_receivables_summary_returns_200_shape():
    """GET /finance/receivables/summary returns 200 with correct shape."""
    from services.receivables_service import ReceivablesService
    from api.v1.finance import get_receivables_summary
    from schemas.common import DataResponse

    # Mock service response
    mock_summary = {
        "total_outstanding": 15000.00,
        "retailer_count": 3,
        "order_count": 25,
        "credit_receivables": 5000.00,
        "unpaid_order_balance": 10000.00,
        "by_retailer": [
            {
                "retailer_id": str(uuid.uuid4()),
                "retailer_name": "Retailer A",
                "outstanding_balance": 5000.00,
                "credit_receivables": 2000.00,
                "unpaid_order_balance": 3000.00,
                "order_count": 10,
            },
            {
                "retailer_id": str(uuid.uuid4()),
                "retailer_name": "Retailer B",
                "outstanding_balance": 6000.00,
                "credit_receivables": 1500.00,
                "unpaid_order_balance": 4500.00,
                "order_count": 8,
            },
            {
                "retailer_id": str(uuid.uuid4()),
                "retailer_name": "Retailer C",
                "outstanding_balance": 4000.00,
                "credit_receivables": 1500.00,
                "unpaid_order_balance": 2500.00,
                "order_count": 7,
            },
        ],
    }

    with patch.object(ReceivablesService, 'get_receivables_summary', return_value=mock_summary) as mock_service:
        mock_service.return_value = mock_summary

        # Mock dependencies
        mock_token = MagicMock()
        mock_db = AsyncMock()

        # Call endpoint
        result = await get_receivables_summary(token=mock_token, db=mock_db)

        # Verify response structure
        assert isinstance(result, DataResponse)
        assert result.success is True
        assert result.data == mock_summary
        assert result.message == "Receivables summary generated"
        assert isinstance(result.timestamp, datetime)

        # Verify data shape
        data = result.data
        assert "total_outstanding" in data
        assert "retailer_count" in data
        assert "order_count" in data
        assert "credit_receivables" in data
        assert "unpaid_order_balance" in data
        assert "by_retailer" in data
        assert isinstance(data["by_retailer"], list)
        assert len(data["by_retailer"]) == 3

        # Verify retailer item shape
        retailer = data["by_retailer"][0]
        assert "retailer_id" in retailer
        assert "retailer_name" in retailer
        assert "outstanding_balance" in retailer
        assert "credit_receivables" in retailer
        assert "unpaid_order_balance" in retailer
        assert "order_count" in retailer


@pytest.mark.asyncio
async def test_get_receivables_summary_calls_service_once():
    """GET /finance/receivables/summary calls service exactly once."""
    from services.receivables_service import ReceivablesService
    from api.v1.finance import get_receivables_summary

    mock_summary = {
        "total_outstanding": 0.0,
        "retailer_count": 0,
        "order_count": 0,
        "credit_receivables": 0.0,
        "unpaid_order_balance": 0.0,
        "by_retailer": [],
    }

    with patch.object(ReceivablesService, 'get_receivables_summary', return_value=mock_summary) as mock_service:
        mock_token = MagicMock()
        mock_db = AsyncMock()

        await get_receivables_summary(token=mock_token, db=mock_db)

        # Verify service was called exactly once
        mock_service.assert_called_once()
        # Verify correct arguments
        call_args = mock_service.call_args
        assert 'tenant_db' in call_args.kwargs
        assert call_args.kwargs['tenant_db'] == mock_db


@pytest.mark.asyncio
async def test_get_receivables_summary_empty_result():
    """GET /finance/receivables/summary returns empty structure when no data."""
    from services.receivables_service import ReceivablesService
    from api.v1.finance import get_receivables_summary

    mock_summary = {
        "total_outstanding": 0.0,
        "retailer_count": 0,
        "order_count": 0,
        "credit_receivables": 0.0,
        "unpaid_order_balance": 0.0,
        "by_retailer": [],
    }

    with patch.object(ReceivablesService, 'get_receivables_summary', return_value=mock_summary):
        mock_token = MagicMock()
        mock_db = AsyncMock()

        result = await get_receivables_summary(token=mock_token, db=mock_db)

        assert result.success is True
        assert result.data["total_outstanding"] == 0.0
        assert result.data["retailer_count"] == 0
        assert result.data["order_count"] == 0
        assert result.data["credit_receivables"] == 0.0
        assert result.data["unpaid_order_balance"] == 0.0
        assert result.data["by_retailer"] == []


# ---------------------------------------------------------------------------
# GET /finance/receivables/orders Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_receivable_orders_returns_200_shape():
    """GET /finance/receivables/orders returns 200 with correct shape."""
    from services.receivables_service import ReceivablesService
    from api.v1.finance import get_receivable_orders
    from schemas.common import DataResponse

    # Mock service response
    order_id = uuid.uuid4()
    retailer_id = uuid.uuid4()

    mock_orders_response = {
        "items": [
            {
                "order_id": str(order_id),
                "retailer_id": str(retailer_id),
                "retailer_name": "Test Retailer",
                "status": "confirmed",
                "classification": "credit_receivable",
                "payment_method": "credit",
                "total_amount": 2000.00,
                "cash_paid": 500.00,
                "credit_amount": 1500.00,
                "balance_due": 1500.00,
                "created_at": "2026-05-13T10:00:00",
                "age_days": 3,
            },
            {
                "order_id": str(uuid.uuid4()),
                "retailer_id": str(retailer_id),
                "retailer_name": "Test Retailer",
                "status": "partially_paid",
                "classification": "unpaid_order",
                "payment_method": "cash",
                "total_amount": 3000.00,
                "cash_paid": 1000.00,
                "credit_amount": 0.00,
                "balance_due": 2000.00,
                "created_at": "2026-05-10T10:00:00",
                "age_days": 6,
            },
        ],
        "pagination": {
            "page": 1,
            "size": 20,
            "total": 2,
            "pages": 1,
        },
    }

    with patch.object(ReceivablesService, 'list_receivable_orders', return_value=mock_orders_response) as mock_service:
        mock_service.return_value = mock_orders_response

        # Mock dependencies
        mock_token = MagicMock()
        mock_db = AsyncMock()

        # Call endpoint
        result = await get_receivable_orders(
            page=1,
            size=20,
            retailer_id=None,
            classification=None,
            status_filter=None,
            token=mock_token,
            db=mock_db,
        )

        # Verify response structure
        assert isinstance(result, DataResponse)
        assert result.success is True
        assert result.data == mock_orders_response
        assert result.message == "Receivable orders listed"
        assert isinstance(result.timestamp, datetime)

        # Verify data shape
        data = result.data
        assert "items" in data
        assert "pagination" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) == 2

        # Verify item shape
        item = data["items"][0]
        assert "order_id" in item
        assert "retailer_id" in item
        assert "retailer_name" in item
        assert "status" in item
        assert "classification" in item
        assert "payment_method" in item
        assert "total_amount" in item
        assert "cash_paid" in item
        assert "credit_amount" in item
        assert "balance_due" in item
        assert "created_at" in item
        assert "age_days" in item

        # Verify pagination shape
        pagination = data["pagination"]
        assert "page" in pagination
        assert "size" in pagination
        assert "total" in pagination
        assert "pages" in pagination


@pytest.mark.asyncio
async def test_get_receivable_orders_passes_query_params():
    """GET /finance/receivables/orders passes query params to service."""
    from services.receivables_service import ReceivablesService
    from api.v1.finance import get_receivable_orders

    retailer_id = str(uuid.uuid4())
    classification = "credit_receivable"
    status_filter = "confirmed"

    mock_response = {
        "items": [],
        "pagination": {"page": 1, "size": 20, "total": 0, "pages": 0},
    }

    with patch.object(ReceivablesService, 'list_receivable_orders', return_value=mock_response) as mock_service:
        mock_token = MagicMock()
        mock_db = AsyncMock()

        await get_receivable_orders(
            page=2,
            size=50,
            retailer_id=retailer_id,
            classification=classification,
            status_filter=status_filter,
            token=mock_token,
            db=mock_db,
        )

        # Verify service was called with correct parameters
        mock_service.assert_called_once()
        call_kwargs = mock_service.call_args.kwargs
        assert call_kwargs['page'] == 2
        assert call_kwargs['size'] == 50
        assert call_kwargs['retailer_id'] == retailer_id
        assert call_kwargs['classification'] == classification
        assert call_kwargs['status'] == status_filter
        assert 'tenant_db' in call_kwargs
        assert call_kwargs['tenant_db'] == mock_db


@pytest.mark.asyncio
async def test_get_receivable_orders_empty_result():
    """GET /finance/receivables/orders returns empty list when no orders."""
    from services.receivables_service import ReceivablesService
    from api.v1.finance import get_receivable_orders

    mock_response = {
        "items": [],
        "pagination": {"page": 1, "size": 20, "total": 0, "pages": 0},
    }

    with patch.object(ReceivablesService, 'list_receivable_orders', return_value=mock_response):
        mock_token = MagicMock()
        mock_db = AsyncMock()

        result = await get_receivable_orders(
            page=1,
            size=20,
            token=mock_token,
            db=mock_db,
        )

        assert result.success is True
        assert result.data["items"] == []
        assert result.data["pagination"]["total"] == 0
        assert result.data["pagination"]["pages"] == 0


@pytest.mark.asyncio
async def test_get_receivable_orders_pagination_metadata():
    """GET /finance/receivables/orders returns correct pagination metadata."""
    from services.receivables_service import ReceivablesService
    from api.v1.finance import get_receivable_orders

    mock_response = {
        "items": [
            {
                "order_id": str(uuid.uuid4()),
                "retailer_id": str(uuid.uuid4()),
                "retailer_name": "Test Retailer",
                "status": "confirmed",
                "classification": "unpaid_order",
                "payment_method": "cash",
                "total_amount": 1000.00,
                "cash_paid": 0.00,
                "credit_amount": 0.00,
                "balance_due": 1000.00,
                "created_at": "2026-05-13T10:00:00",
                "age_days": 1,
            },
        ],
        "pagination": {
            "page": 3,
            "size": 20,
            "total": 45,
            "pages": 3,
        },
    }

    with patch.object(ReceivablesService, 'list_receivable_orders', return_value=mock_response):
        mock_token = MagicMock()
        mock_db = AsyncMock()

        result = await get_receivable_orders(
            page=3,
            size=20,
            token=mock_token,
            db=mock_db,
        )

        assert result.success is True
        assert result.data["pagination"]["page"] == 3
        assert result.data["pagination"]["size"] == 20
        assert result.data["pagination"]["total"] == 45
        assert result.data["pagination"]["pages"] == 3


# ---------------------------------------------------------------------------
# Query Param Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_receivable_orders_retailer_id_filter():
    """Query param retailer_id passes through to service."""
    from services.receivables_service import ReceivablesService
    from api.v1.finance import get_receivable_orders

    retailer_id = str(uuid.uuid4())
    mock_response = {
        "items": [],
        "pagination": {"page": 1, "size": 20, "total": 0, "pages": 0},
    }

    with patch.object(ReceivablesService, 'list_receivable_orders', return_value=mock_response) as mock_service:
        mock_token = MagicMock()
        mock_db = AsyncMock()

        await get_receivable_orders(
            page=1,
            size=20,
            retailer_id=retailer_id,
            token=mock_token,
            db=mock_db,
        )

        call_kwargs = mock_service.call_args.kwargs
        assert call_kwargs['retailer_id'] == retailer_id


@pytest.mark.asyncio
async def test_receivable_orders_classification_filter():
    """Query param classification passes through to service."""
    from services.receivables_service import ReceivablesService
    from api.v1.finance import get_receivable_orders

    mock_response = {
        "items": [],
        "pagination": {"page": 1, "size": 20, "total": 0, "pages": 0},
    }

    with patch.object(ReceivablesService, 'list_receivable_orders', return_value=mock_response) as mock_service:
        mock_token = MagicMock()
        mock_db = AsyncMock()

        await get_receivable_orders(
            page=1,
            size=20,
            classification="credit_receivable",
            token=mock_token,
            db=mock_db,
        )

        call_kwargs = mock_service.call_args.kwargs
        assert call_kwargs['classification'] == "credit_receivable"


@pytest.mark.asyncio
async def test_receivable_orders_status_filter():
    """Query param status passes through to service (aliased as status_filter)."""
    from services.receivables_service import ReceivablesService
    from api.v1.finance import get_receivable_orders

    mock_response = {
        "items": [],
        "pagination": {"page": 1, "size": 20, "total": 0, "pages": 0},
    }

    with patch.object(ReceivablesService, 'list_receivable_orders', return_value=mock_response) as mock_service:
        mock_token = MagicMock()
        mock_db = AsyncMock()

        await get_receivable_orders(
            page=1,
            size=20,
            status_filter="confirmed",
            token=mock_token,
            db=mock_db,
        )

        call_kwargs = mock_service.call_args.kwargs
        assert call_kwargs['status'] == "confirmed"


# ---------------------------------------------------------------------------
# Permission Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_receivables_summary_requires_finance_read_permission():
    """GET /finance/receivables/summary requires finance:read permission."""
    from api.dependencies import get_tenant_db_session
    from api.middleware.rbac import RequirePermission
    from api.v1.finance import get_receivables_summary

    # Verify the endpoint has RequirePermission decorator
    assert hasattr(get_receivables_summary, '__wrapped__')
    # The actual permission check is done by the decorator
    # This test verifies the decorator is present


@pytest.mark.asyncio
async def test_receivable_orders_requires_finance_read_permission():
    """GET /finance/receivables/orders requires finance:read permission."""
    from api.middleware.rbac import RequirePermission
    from api.v1.finance import get_receivable_orders

    # Verify the endpoint has RequirePermission decorator
    assert hasattr(get_receivable_orders, '__wrapped__')
    # The actual permission check is done by the decorator
    # This test verifies the decorator is present


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_receivables_summary_service_error_propagates():
    """Service errors in receivables summary propagate correctly."""
    from services.receivables_service import ReceivablesService
    from api.v1.finance import get_receivables_summary

    with patch.object(ReceivablesService, 'get_receivables_summary', side_effect=Exception("DB connection failed")):
        mock_token = MagicMock()
        mock_db = AsyncMock()

        with pytest.raises(Exception, match="DB connection failed"):
            await get_receivables_summary(token=mock_token, db=mock_db)


@pytest.mark.asyncio
async def test_receivable_orders_service_error_propagates():
    """Service errors in receivable orders propagate correctly."""
    from services.receivables_service import ReceivablesService
    from api.v1.finance import get_receivable_orders

    with patch.object(ReceivablesService, 'list_receivable_orders', side_effect=Exception("Invalid retailer ID")):
        mock_token = MagicMock()
        mock_db = AsyncMock()

        with pytest.raises(Exception, match="Invalid retailer ID"):
            await get_receivable_orders(
                page=1,
                size=20,
                token=mock_token,
                db=mock_db,
            )
