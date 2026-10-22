"""Legacy read adapters. Unsafe unversioned/password/role-UUID writes are retired."""
from datetime import datetime
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequireOwner
from crud.user import get_user_by_id
from schemas.user import UserCreateRequest, UserUpdateRequest, AssignRolesRequest, UserRead, RoleRead
from services.staff_management_service import StaffManagementService

router=APIRouter()


def user_to_read(user):
    return UserRead(id=str(user.id),email=user.email,full_name=user.full_name,is_active=user.is_active,
        roles=[RoleRead(id=str(r.id),name=r.name,description=r.description) for r in user.roles if not r.is_deleted],
        created_at=user.created_at,updated_at=user.updated_at)


def retired():
    raise HTTPException(status_code=409,detail={'code':'STAFF_MANAGEMENT_REQUIRED',
        'message':'Use versioned staff management and employee mailbox invitations'})


@router.get('')
async def list_users(page: int=Query(1,ge=1),size: int=Query(10,ge=1,le=100),
                     token=Depends(RequireOwner()),db=Depends(get_tenant_db_session)):
    service=StaffManagementService(db,token.tenant_id,token.tenant_schema)
    authority=await service.require_owner(token.user_id)
    ids=list((await db.execute(text(f'SELECT user_id FROM {service.q}.staff_memberships ORDER BY user_id'))).scalars())
    ids=[authority.owner_user_id]+ids
    users=[user_to_read(await get_user_by_id(db,str(uid))) for uid in ids[(page-1)*size:page*size]]
    return {'success':True,'data':{'items':users,'pagination':{'page':page,'size':size,'total':len(ids),'pages':ceil(len(ids)/size)}},'timestamp':datetime.utcnow()}


@router.get('/{user_id}')
async def get_user_endpoint(user_id: UUID,token=Depends(RequireOwner()),db=Depends(get_tenant_db_session)):
    service=StaffManagementService(db,token.tenant_id,token.tenant_schema)
    authority=await service.require_owner(token.user_id)
    if user_id!=authority.owner_user_id:
        await service.member(user_id)
    user=await get_user_by_id(db,str(user_id))
    if user is None: raise HTTPException(status_code=404,detail={'code':'USER_NOT_FOUND'})
    return {'success':True,'data':user_to_read(user),'timestamp':datetime.utcnow()}


@router.post('')
async def create_user_endpoint(request: UserCreateRequest,token=Depends(RequireOwner()),db=Depends(get_tenant_db_session)):
    retired()


@router.put('/{user_id}')
async def update_user_endpoint(user_id: UUID,request: UserUpdateRequest,token=Depends(RequireOwner()),db=Depends(get_tenant_db_session)):
    retired()


@router.delete('/{user_id}')
async def delete_user_endpoint(user_id: UUID,token=Depends(RequireOwner()),db=Depends(get_tenant_db_session)):
    retired()


@router.put('/{user_id}/roles')
async def assign_user_roles_endpoint(user_id: UUID,request: AssignRolesRequest,token=Depends(RequireOwner()),db=Depends(get_tenant_db_session)):
    retired()
