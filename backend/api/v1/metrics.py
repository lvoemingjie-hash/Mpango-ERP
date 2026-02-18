"""
Metrics endpoint for operational monitoring.
Provides basic request metrics and performance data.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_context
from api.middleware.rbac import RequirePermission
from core.config import get_settings
from core.logging_config import get_request_logger
from core.security import TokenPayload

router = APIRouter()


class MetricsResponse(BaseModel):
    """Metrics response schema."""
    service: str = Field(default="mpango-erp-backend", description="Service name")
    version: str = Field(default="0.1.0", description="Service version")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Metrics timestamp")
    metrics_enabled: bool = Field(description="Whether metrics collection is enabled")
    data: dict = Field(description="Metrics data")


@router.get(
    "",
    response_model=MetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get service metrics",
    description="Returns basic request metrics and performance data. Requires authentication."
)
async def get_metrics(
    request: Request,
    token: TokenPayload = Depends(get_current_user_context),
):
    """
    Get current service metrics.

    Returns request counts, response times, and error rates.
    Only available when metrics are enabled in configuration.
    """
    # Get request context for logging
    request_id = getattr(request.state, 'request_id', 'N/A')
    tenant_id = getattr(request.state, 'tenant_id', 'N/A')
    logger = get_request_logger(request_id, tenant_id)

    settings = get_settings()

    if not settings.ENABLE_METRICS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "METRICS_DISABLED",
                "message": "Metrics collection is disabled. Set ENABLE_METRICS=true to enable."
            }
        )

    logger.info(
        "metrics_accessed",
        extra={
            "action": "get_metrics",
            "user_id": token.user_id
        }
    )

    try:
        # Get metrics from middleware (stored in app state)
        metrics_middleware = None
        for middleware in request.app.user_middleware:
            if hasattr(middleware.cls, '__name__') and 'BasicMetricsMiddleware' in str(middleware.cls):
                # Find the actual middleware instance
                break

        # Since we can't easily access the middleware instance, we'll store metrics in app state
        if not hasattr(request.app.state, '_metrics_middleware'):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "METRICS_UNAVAILABLE",
                    "message": "Metrics middleware not properly initialized."
                }
            )

        metrics_data = request.app.state._metrics_middleware.get_metrics()

        return MetricsResponse(
            service="mpango-erp-backend",
            version="0.1.0",
            timestamp=datetime.utcnow(),
            metrics_enabled=True,
            data=metrics_data
        )

    except Exception as e:
        logger.error(
            "metrics_failed",
            extra={
                "action": "get_metrics",
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "METRICS_ERROR",
                "message": "Failed to retrieve metrics."
            }
        )


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reset metrics",
    description="Reset all collected metrics. Requires authentication."
)
async def reset_metrics(
    request: Request,
    token: TokenPayload = Depends(RequirePermission("metrics:admin")),
):
    """
    Reset all collected metrics.

    Clears all stored metrics data. Useful for testing or periodic reset.
    Only available when metrics are enabled in configuration.
    """
    # Get request context for logging
    request_id = getattr(request.state, 'request_id', 'N/A')
    tenant_id = getattr(request.state, 'tenant_id', 'N/A')
    logger = get_request_logger(request_id, tenant_id)

    settings = get_settings()

    if not settings.ENABLE_METRICS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "METRICS_DISABLED",
                "message": "Metrics collection is disabled."
            }
        )

    logger.info(
        "metrics_reset",
        extra={
            "action": "reset_metrics",
            "user_id": token.user_id
        }
    )

    try:
        if not hasattr(request.app.state, '_metrics_middleware'):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "METRICS_UNAVAILABLE",
                    "message": "Metrics middleware not properly initialized."
                }
            )

        request.app.state._metrics_middleware.reset_metrics()

        return None  # 204 No Content

    except Exception as e:
        logger.error(
            "metrics_reset_failed",
            extra={
                "action": "reset_metrics",
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "METRICS_RESET_ERROR",
                "message": "Failed to reset metrics."
            }
        )
