"""
S2-3: Prometheus Metrics Endpoint

Exposes /metrics endpoint for Prometheus scraping.
"""
from fastapi import APIRouter, Response

from core.prometheus_metrics import get_metrics, get_metrics_content_type
from core.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "",
    summary="Prometheus metrics",
    description="Exposes Prometheus metrics for scraping. Use this endpoint for monitoring.",
    response_class=Response
)
async def metrics_endpoint():
    """
    S2-3: Prometheus metrics endpoint.
    
    Returns metrics in Prometheus exposition format.
    
    Metrics include:
    - http_requests_total: Total HTTP requests by method, route, status, tenant
    - http_request_duration_seconds: Request duration histogram
    - http_requests_in_progress: Current in-progress requests
    - db_transactions_total: Database transaction counter
    - idempotency_conflicts_total: Idempotency conflict counter
    - payment_transactions_total: Payment transaction counter
    - order_state_transitions_total: Order state transition counter
    """
    metrics_data = get_metrics()
    
    return Response(
        content=metrics_data,
        media_type=get_metrics_content_type()
    )
