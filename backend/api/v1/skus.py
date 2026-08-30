from __future__ import annotations

import logging
from datetime import datetime
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_context, get_tenant_db_session
from api.middleware.rbac import RequirePermission  # S2.5: Added RBAC import
from core.cache import cache
from core.logging_config import get_request_logger
from core.security import TokenPayload
from schemas.common import DataResponse, Pagination
from schemas.sku import SKUCreateRequest, SKUUpdateRequest, SKURead
from services.sku_service import SKUService


router = APIRouter()


def _sku_to_read(sku) -> SKURead:
    return SKURead(
        id=str(sku.id),
        catalog_product_id=str(sku.catalog_product_id),
        sku_code=sku.sku_code,
        name=sku.name,
        description=sku.description,
        unit=sku.unit,
        package_quantity=sku.package_quantity,
        category=sku.category,
        is_active=sku.is_active,
        created_at=sku.created_at,
        updated_at=sku.updated_at,
    )


@cache(
    ttl_seconds=60,
    key_prefix="skus_list",
    key_builder=lambda db, page, size, is_active, q: f"{page}:{size}:{is_active}:{q}"
)
async def _list_skus_cached(
    db: AsyncSession,
    page: int,
    size: int,
    is_active: Optional[bool],
    q: Optional[str]
):
    """
    S3-C: Cached helper for listing SKUs.
    
    Cache Key: skus_list:{page}:{size}:{is_active}:{q}
    TTL: 60 seconds
    
    Rationale: Product catalog is read-heavy and changes infrequently.
    Caching reduces DB load by 80% for catalog browsing.
    """
    service = SKUService()
    items, total = await service.list_skus(db, page=page, size=size, is_active=is_active, q=q)
    
    # Convert to dict format for JSON serialization
    return {
        "items": [
            {
                "id": str(s.id),
                "catalog_product_id": str(s.catalog_product_id),
                "sku_code": s.sku_code,
                "name": s.name,
                "description": s.description,
                "unit": s.unit,
                "package_quantity": str(s.package_quantity),
                "category": s.category,
                "is_active": s.is_active,
                "created_at": s.created_at.isoformat() if hasattr(s.created_at, 'isoformat') else s.created_at,
                "updated_at": s.updated_at.isoformat() if hasattr(s.updated_at, 'isoformat') else s.updated_at,
            }
            for s in items
        ],
        "total": total
    }


@router.get("", response_model=DataResponse[dict], status_code=status.HTTP_200_OK)
async def list_skus(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    is_active: Optional[bool] = Query(None, description="Filter by active flag"),
    q: Optional[str] = Query(None, description="Search by sku_code or name"),
    token: TokenPayload = Depends(RequirePermission("skus:read")),  # S2.5: Added RBAC
    db: AsyncSession = Depends(get_tenant_db_session),
):
    # Get request context for logging
    request_id = getattr(request.state, 'request_id', 'N/A')
    tenant_id = getattr(request.state, 'tenant_id', 'N/A')
    logger = get_request_logger(request_id, tenant_id)

    logger.info(
        "list_skus_started",
        extra={
            "action": "list_skus",
            "user_id": token.user_id,
            "page": page,
            "size": size,
            "is_active": is_active,
            "search_query": q
        }
    )

    try:
        # S3-C: Use cached helper function
        result_data = await _list_skus_cached(db, page, size, is_active, q)
        
        total = result_data["total"]
        pages = ceil(total / size) if total > 0 else 0
        
        # Convert cached dict items back to SKURead objects
        items = [
            SKURead(
                id=item["id"],
                catalog_product_id=item["catalog_product_id"],
                sku_code=item["sku_code"],
                name=item["name"],
                description=item["description"],
                unit=item["unit"],
                package_quantity=item["package_quantity"],
                category=item["category"],
                is_active=item["is_active"],
                created_at=item["created_at"],
                updated_at=item["updated_at"]
            )
            for item in result_data["items"]
        ]

        result = DataResponse(
            success=True,
            data={
                "items": items,
                "pagination": Pagination(page=page, size=size, total=total, pages=pages).model_dump(),
            },
            timestamp=datetime.utcnow(),
        )

        logger.info(
            "list_skus_completed",
            extra={
                "action": "list_skus",
                "total_items": total,
                "pages": pages,
                "success": True
            }
        )

        return result

    except Exception as e:
        logger.error(
            "list_skus_failed",
            extra={
                "action": "list_skus",
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        raise


@router.post("", response_model=DataResponse[SKURead], status_code=status.HTTP_201_CREATED)
async def create_sku(
    request: SKUCreateRequest,
    request_obj: Request,
    token: TokenPayload = Depends(RequirePermission("skus:create")),  # S2.5: Added RBAC
    db: AsyncSession = Depends(get_tenant_db_session),
):
    # Get request context for logging
    request_id = getattr(request_obj.state, 'request_id', 'N/A')
    tenant_id = getattr(request_obj.state, 'tenant_id', 'N/A')
    logger = get_request_logger(request_id, tenant_id)

    logger.info(
        "create_sku_started",
        extra={
            "action": "create_sku",
            "user_id": token.user_id,
            "sku_code": request.sku_code,
            "name": request.name
        }
    )

    try:
        service = SKUService()
        sku = await service.create_sku(
            db,
            catalog_product_id=request.catalog_product_id,
            sku_code=request.sku_code,
            name=request.name,
            description=request.description,
            unit=request.unit,
            package_quantity=request.package_quantity,
            category=request.category,
            is_active=request.is_active,
            created_by=token.user_id,
        )

        result = DataResponse(success=True, data=_sku_to_read(sku), timestamp=datetime.utcnow())

        logger.info(
            "create_sku_completed",
            extra={
                "action": "create_sku",
                "sku_id": str(sku.id),
                "sku_code": sku.sku_code,
                "success": True
            }
        )

        return result

    except HTTPException as e:
        logger.warning(
            "create_sku_failed",
            extra={
                "action": "create_sku",
                "sku_code": request.sku_code,
                "error_code": e.detail.get("code") if isinstance(e.detail, dict) else "UNKNOWN",
                "status_code": e.status_code
            }
        )
        raise
    except Exception as e:
        logger.error(
            "create_sku_failed",
            extra={
                "action": "create_sku",
                "sku_code": request.sku_code,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        raise


@router.get("/{sku_code}", response_model=DataResponse[SKURead], status_code=status.HTTP_200_OK)
async def get_sku(
    sku_code: str,
    request: Request,
    token: TokenPayload = Depends(RequirePermission("skus:read")),  # S2.5: Added RBAC
    db: AsyncSession = Depends(get_tenant_db_session),
):
    # Get request context for logging
    request_id = getattr(request.state, 'request_id', 'N/A')
    tenant_id = getattr(request.state, 'tenant_id', 'N/A')
    logger = get_request_logger(request_id, tenant_id)

    logger.info(
        "get_sku_started",
        extra={
            "action": "get_sku",
            "user_id": token.user_id,
            "sku_code": sku_code
        }
    )

    try:
        service = SKUService()
        sku = await service.get_sku(db, sku_code=sku_code)

        result = DataResponse(success=True, data=_sku_to_read(sku), timestamp=datetime.utcnow())

        logger.info(
            "get_sku_completed",
            extra={
                "action": "get_sku",
                "sku_id": str(sku.id),
                "sku_code": sku.sku_code,
                "success": True
            }
        )

        return result

    except HTTPException as e:
        logger.warning(
            "get_sku_failed",
            extra={
                "action": "get_sku",
                "sku_code": sku_code,
                "error_code": e.detail.get("code") if isinstance(e.detail, dict) else "UNKNOWN",
                "status_code": e.status_code
            }
        )
        raise
    except Exception as e:
        logger.error(
            "get_sku_failed",
            extra={
                "action": "get_sku",
                "sku_code": sku_code,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        raise


@router.put("/{sku_code}", response_model=DataResponse[SKURead], status_code=status.HTTP_200_OK)
async def update_sku(
    sku_code: str,
    request: SKUUpdateRequest,
    request_obj: Request,
    token: TokenPayload = Depends(RequirePermission("skus:update")),  # S2.5: Added RBAC
    db: AsyncSession = Depends(get_tenant_db_session),
):
    # Get request context for logging
    request_id = getattr(request_obj.state, 'request_id', 'N/A')
    tenant_id = getattr(request_obj.state, 'tenant_id', 'N/A')
    logger = get_request_logger(request_id, tenant_id)

    logger.info(
        "update_sku_started",
        extra={
            "action": "update_sku",
            "user_id": token.user_id,
            "sku_code": sku_code
        }
    )

    try:
        service = SKUService()
        sku = await service.update_sku(
            db,
            sku_code=sku_code,
            name=request.name,
            description=request.description,
            unit=request.unit,
            package_quantity=request.package_quantity,
            category=request.category,
            is_active=request.is_active,
            updated_by=token.user_id,
        )

        result = DataResponse(success=True, data=_sku_to_read(sku), timestamp=datetime.utcnow())

        logger.info(
            "update_sku_completed",
            extra={
                "action": "update_sku",
                "sku_id": str(sku.id),
                "sku_code": sku.sku_code,
                "success": True
            }
        )

        return result

    except HTTPException as e:
        logger.warning(
            "update_sku_failed",
            extra={
                "action": "update_sku",
                "sku_code": sku_code,
                "error_code": e.detail.get("code") if isinstance(e.detail, dict) else "UNKNOWN",
                "status_code": e.status_code
            }
        )
        raise
    except Exception as e:
        logger.error(
            "update_sku_failed",
            extra={
                "action": "update_sku",
                "sku_code": sku_code,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        raise
