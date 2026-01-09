from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_tenant_db_session, require_permission
from schemas.user import UserCreate, UserUpdate, UserRead, UserWithRoles
from crud.user import user
from models.user import User

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def read_users_me(
    current_user: User = Depends(get_current_user)
):
    """获取当前用户信息"""
    return current_user


@router.get("/", response_model=List[UserRead])
async def read_users(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_tenant_db_session),
    current_user: User = Depends(require_permission("users:read"))
):
    """获取用户列表"""
    users = await user.get_multi(db, skip=skip, limit=limit)
    return users


@router.post("/", response_model=UserRead)
async def create_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_tenant_db_session),
    current_user: User = Depends(require_permission("users:create"))
):
    """创建新用户"""
    # 检查邮箱是否已存在
    existing_user = await user.get_by_email(db, email=user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    new_user = await user.create(db, obj_in=user_in)
    return new_user


@router.get("/{user_id}", response_model=UserWithRoles)
async def read_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_tenant_db_session),
    current_user: User = Depends(require_permission("users:read"))
):
    """获取指定用户信息"""
    db_user = await user.get_user_with_roles(db, user_id=user_id)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return db_user


@router.put("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_tenant_db_session),
    current_user: User = Depends(require_permission("users:update"))
):
    """更新用户信息"""
    db_user = await user.get(db, id=user_id)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # 如果更新邮箱，检查是否已存在
    if user_in.email and user_in.email != db_user.email:
        existing_user = await user.get_by_email(db, email=user_in.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    updated_user = await user.update(db, db_obj=db_user, obj_in=user_in)
    return updated_user


@router.delete("/{user_id}")
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_tenant_db_session),
    current_user: User = Depends(require_permission("users:deactivate"))
):
    """软删除用户"""
    db_user = await user.get(db, id=user_id)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    await user.remove(db, id=user_id)
    return {"message": "User deleted successfully"}