from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request, HTTPException

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequireOwner
from schemas.staff import StaffCreate, StaffEdit, StaffInvite, StaffRoleEdit, StaffTemplateEdit, StaffRecoveryRequest
from core.structured_logging import get_logger
from services.staff_management_service import StaffManagementService
from services.staff_credential_service import StaffCredentialService

router=APIRouter()
logger=get_logger(__name__)


def service(db,token):
    return StaffManagementService(db,token.tenant_id,token.tenant_schema)


@router.get('')
async def members(token=Depends(RequireOwner()),db=Depends(get_tenant_db_session)):
    return {'success':True,'data':await service(db,token).members(token.user_id)}


@router.get('/role-templates')
async def templates(token=Depends(RequireOwner()),db=Depends(get_tenant_db_session)):
    return {'success':True,'data':await service(db,token).templates(token.user_id)}


@router.put('/role-templates/{key}')
async def edit_template(key: str,body: StaffTemplateEdit,token=Depends(RequireOwner()),db=Depends(get_tenant_db_session)):
    return {'success':True,'data':await service(db,token).edit_template(token.user_id,key,body.permission_codes,body.expected_version)}


@router.post('',status_code=201)
async def create(body: StaffCreate,token=Depends(RequireOwner()),db=Depends(get_tenant_db_session),
                 create_key: str | None=Header(default=None,alias='Idempotency-Key')):
    return {'success':True,'data':await service(db,token).create_member(token.user_id,create_key=create_key,**body.model_dump())}


@router.patch('/{user_id}')
async def edit(user_id: UUID,body: StaffEdit,token=Depends(RequireOwner()),db=Depends(get_tenant_db_session)):
    return {'success':True,'data':await service(db,token).edit_member(token.user_id,user_id,**body.model_dump())}


@router.post('/{user_id}/credential-setup',status_code=201)
async def invite(user_id: UUID,body: StaffInvite,token=Depends(RequireOwner()),db=Depends(get_tenant_db_session)):
    data=await StaffCredentialService(db).invite(tenant_id=token.tenant_id,schema=token.tenant_schema,
        actor_id=token.user_id,user_id=user_id,owner_password=body.owner_password.get_secret_value(),expected_version=body.expected_version)
    return {'success':True,'data':data}


@router.get('/{user_id}')
async def member(user_id: UUID,token=Depends(RequireOwner()),db=Depends(get_tenant_db_session)):
    current=service(db,token)
    await current.require_owner(token.user_id)
    return {'success':True,'data':await current.member(user_id)}


@router.post('/{user_id}/credential-recovery',status_code=202)
async def request_recovery(user_id: UUID, body: StaffRecoveryRequest, request: Request,
                           token=Depends(RequireOwner()), db=Depends(get_tenant_db_session)):
    if request.query_params:
        raise HTTPException(422,detail={'code':'RECOVERY_QUERY_FORBIDDEN'})
    try:
        data=await StaffCredentialService(db).request_recovery(
            tenant_id=token.tenant_id,schema=token.tenant_schema,actor_id=token.user_id,
            user_id=user_id,owner_password=body.owner_password.get_secret_value(),expected_version=body.expected_version)
    except HTTPException:
        await db.rollback()
        logger.warning('Staff recovery request refused',extra={'event_class':'STAFF_RECOVERY_REQUEST_REFUSED'})
        raise
    except Exception:
        await db.rollback()
        logger.warning('Staff recovery request unavailable',extra={'event_class':'STAFF_RECOVERY_REQUEST_UNAVAILABLE'})
        raise HTTPException(503,detail={'code':'STAFF_RECOVERY_UNAVAILABLE'}) from None
    try:
        await db.commit()
    except BaseException as exc:
        await db.rollback()
        logger.warning('Staff recovery commit outcome unknown',extra={'event_class':'STAFF_RECOVERY_COMMIT_OUTCOME_UNKNOWN'})
        if not isinstance(exc,Exception): raise
        raise HTTPException(503,detail={'code':'STAFF_RECOVERY_COMMIT_OUTCOME_UNKNOWN'}) from None
    return {'success':True,'data':data}


@router.put('/{user_id}/role')
async def edit_role(user_id: UUID,body: StaffRoleEdit,token=Depends(RequireOwner()),db=Depends(get_tenant_db_session)):
    return {'success':True,'data':await service(db,token).edit_member(token.user_id,user_id,**body.model_dump())}
