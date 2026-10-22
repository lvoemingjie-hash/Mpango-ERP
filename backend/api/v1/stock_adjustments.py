from uuid import UUID

from fastapi import APIRouter, Depends, Header

from api.dependencies import get_current_user_context, get_tenant_db_session
from schemas.stock_adjustments import AdjustmentCreate, AdjustmentDecision, AdjustmentPolicyEdit
from services.inventory_adjustment_service import InventoryAdjustmentService

router = APIRouter()


def service(db, token):
    db.info['_staff_stock_actor'] = str(token.user_id)
    return InventoryAdjustmentService(db, token.tenant_id, token.tenant_schema)


@router.get('/adjustment-policy')
async def policy(token=Depends(get_current_user_context), db=Depends(get_tenant_db_session)):
    return {'success': True, 'data': await service(db, token).policy(token.user_id)}


@router.put('/adjustment-policy')
async def edit_policy(body: AdjustmentPolicyEdit, token=Depends(get_current_user_context), db=Depends(get_tenant_db_session)):
    return {'success': True, 'data': await service(db, token).set_policy(token.user_id, **body.model_dump())}


@router.get('/adjustment-snapshot/{sku_id}')
async def snapshot(sku_id: UUID, token=Depends(get_current_user_context), db=Depends(get_tenant_db_session)):
    return {'success': True, 'data': await service(db, token).snapshot(token.user_id, sku_id)}


@router.get('/adjustment-requests')
async def requests(token=Depends(get_current_user_context), db=Depends(get_tenant_db_session)):
    return {'success': True, 'data': await service(db, token).list_requests(token.user_id)}


@router.post('/adjustment-requests', status_code=201)
async def submit(body: AdjustmentCreate, key: str | None=Header(default=None, alias='Idempotency-Key'),
                 token=Depends(get_current_user_context), db=Depends(get_tenant_db_session)):
    return {'success': True, 'data': await service(db, token).submit(token.user_id, key=key, **body.model_dump())}


@router.post('/owner-adjustments', status_code=201)
async def direct(body: AdjustmentCreate, key: str | None=Header(default=None, alias='Idempotency-Key'),
                 token=Depends(get_current_user_context), db=Depends(get_tenant_db_session)):
    return {'success': True, 'data': await service(db, token).submit(token.user_id, key=key, direct=True, **body.model_dump())}


@router.get('/adjustment-requests/{request_id}')
async def detail(request_id: UUID, token=Depends(get_current_user_context), db=Depends(get_tenant_db_session)):
    return {'success': True, 'data': await service(db, token).detail(token.user_id, request_id)}


@router.post('/adjustment-requests/{request_id}/{action}')
async def decide(request_id: UUID, action: str, body: AdjustmentDecision,
                 key: str | None=Header(default=None, alias='Idempotency-Key'),
                 token=Depends(get_current_user_context), db=Depends(get_tenant_db_session)):
    return {'success': True, 'data': await service(db, token).decide(token.user_id, request_id,
        action=action, key=key, **body.model_dump())}
