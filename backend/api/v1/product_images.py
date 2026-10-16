"""Protected media routes. No automatic body/multipart parsing."""
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from api.v1.client.dependencies import ClientIdentity, resolve_client_identity
from core.config import get_settings
from core.security import TokenPayload
from schemas.common import DataResponse
from schemas.product_image import ProductImageState
from services.product_image_service import read_image, write_image
from services.product_image_storage import refuse

router = APIRouter()


@router.put('/catalog-products/{product_id}/image', response_model=DataResponse[ProductImageState])
async def upload_product_image(product_id: str, request: Request,
    token: TokenPayload = Depends(RequirePermission('skus:update')),
    db: AsyncSession = Depends(get_tenant_db_session)):
    try:
        value = await write_image(db, request, product_id=product_id,
                                  tenant_id=token.tenant_id, actor_id=token.user_id)
    except OSError:
        refuse('IMAGE_UNAVAILABLE')
    return DataResponse(success=True, data=value, timestamp=datetime.utcnow())


@router.delete('/catalog-products/{product_id}/image', response_model=DataResponse[ProductImageState])
async def delete_product_image(product_id: str, request: Request,
    token: TokenPayload = Depends(RequirePermission('skus:update')),
    db: AsyncSession = Depends(get_tenant_db_session)):
    try:
        value = await write_image(db, request, product_id=product_id,
                                  tenant_id=token.tenant_id, actor_id=token.user_id, delete=True)
    except OSError:
        refuse('IMAGE_UNAVAILABLE')
    return DataResponse(success=True, data=value, timestamp=datetime.utcnow())


def image_response(data):
    return Response(content=data, media_type='image/webp', headers={
        'Cache-Control': 'private, no-store', 'Vary': 'Authorization',
        'X-Content-Type-Options': 'nosniff',
    })


@router.get('/catalog-products/{product_id}/image/{version}/{variant}')
async def merchant_product_image(product_id: str, version: str, variant: str,
    token: TokenPayload = Depends(RequirePermission('skus:read')),
    db: AsyncSession = Depends(get_tenant_db_session)):
    return image_response(await read_image(db, root=get_settings().PRODUCT_IMAGE_ROOT,
        tenant_id=token.tenant_id, product_id=product_id, version=version, variant=variant))


@router.get('/client/products/{product_id}/image/{version}/{variant}')
async def client_product_image(product_id: str, version: str, variant: str,
    client: ClientIdentity = Depends(resolve_client_identity),
    _perm: TokenPayload = Depends(RequirePermission('client:catalog:read')),
    db: AsyncSession = Depends(get_tenant_db_session)):
    return image_response(await read_image(db, root=get_settings().PRODUCT_IMAGE_ROOT,
        tenant_id=client.tenant_id, product_id=product_id, version=version, variant=variant, client=True))
