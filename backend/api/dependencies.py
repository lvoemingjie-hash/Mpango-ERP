from typing import Optional
from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_tenant_db
from core.security import verify_token
from core.exceptions import invalid_credentials, permission_denied
from crud.user import user
from models.user import User

security = HTTPBearer()


async def get_current_user_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """从JWT令牌中获取用户信息"""
    try:
        payload = verify_token(credentials.credentials)
        return payload
    except Exception:
        raise invalid_credentials()


async def get_tenant_db_session(
    token_payload: dict = Depends(get_current_user_token)
) -> AsyncSession:
    """获取租户数据库会话"""
    tenant_schema = token_payload.get("tenant_schema")
    if not tenant_schema:
        raise invalid_credentials()
    
    async with get_tenant_db(tenant_schema) as db:
        yield db


async def get_current_user(
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_tenant_db_session)
) -> User:
    """获取当前用户"""
    user_id = token_payload.get("user_id")
    if not user_id:
        raise invalid_credentials()
    
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise invalid_credentials()
    
    db_user = await user.get(db, id=user_uuid)
    if not db_user:
        raise invalid_credentials()
    
    if not await user.is_active(db_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    return db_user


def require_permission(permission_code: str):
    """权限检查装饰器"""
    async def permission_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_tenant_db_session)
    ) -> User:
        # 获取用户权限
        user_permissions = await user.get_user_permissions(db, user_id=current_user.id)
        
        # 检查是否有所需权限
        if permission_code not in user_permissions:
            raise permission_denied()
        
        return current_user
    
    return permission_checker


async def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db_session)
) -> User:
    """获取当前超级用户（admin角色）"""
    user_permissions = await user.get_user_permissions(db, user_id=current_user.id)
    
    # 检查是否有admin权限（简化检查，实际可能需要更复杂的逻辑）
    if "users:create" not in user_permissions:  # admin应该有所有权限
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    return current_user