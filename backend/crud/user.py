from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from crud.base import CRUDBase
from models.user import User, Role, Permission
from schemas.user import UserCreate, UserUpdate, RoleCreate, RoleUpdate, PermissionCreate, PermissionRead
from core.security import get_password_hash, verify_password


class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    async def get_by_email(self, db: AsyncSession, *, email: str) -> Optional[User]:
        """根据邮箱获取用户"""
        result = await db.execute(
            select(User).where(
                User.email == email,
                User.is_deleted == False
            )
        )
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, *, obj_in: UserCreate) -> User:
        """创建用户（加密密码）"""
        create_data = obj_in.dict()
        create_data["password_hash"] = get_password_hash(create_data.pop("password"))
        
        db_obj = User(**create_data)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def authenticate(
        self, db: AsyncSession, *, email: str, password: str
    ) -> Optional[User]:
        """验证用户凭据"""
        user = await self.get_by_email(db, email=email)
        if not user:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    async def is_active(self, user: User) -> bool:
        """检查用户是否激活"""
        return user.is_active

    async def get_user_with_roles(self, db: AsyncSession, *, user_id: UUID) -> Optional[User]:
        """获取用户及其角色"""
        result = await db.execute(
            select(User)
            .options(selectinload(User.roles).selectinload(UserRole.role))
            .where(
                User.id == user_id,
                User.is_deleted == False
            )
        )
        return result.scalar_one_or_none()

    async def get_user_permissions(self, db: AsyncSession, *, user_id: UUID) -> list[str]:
        """获取用户的所有权限代码"""
        # 这里需要复杂的查询来获取用户通过角色获得的所有权限
        # 简化版本，实际应该通过JOIN查询优化
        user = await self.get_user_with_roles(db, user_id=user_id)
        if not user:
            return []
        
        permissions = set()
        for user_role in user.roles:
            role = user_role.role
            for role_permission in role.permissions:
                permissions.add(role_permission.permission.code)
        
        return list(permissions)


class CRUDRole(CRUDBase[Role, RoleCreate, RoleUpdate]):
    async def get_by_name(self, db: AsyncSession, *, name: str) -> Optional[Role]:
        """根据名称获取角色"""
        result = await db.execute(
            select(Role).where(
                Role.name == name,
                Role.is_deleted == False
            )
        )
        return result.scalar_one_or_none()


class CRUDPermission(CRUDBase[Permission, PermissionCreate, PermissionRead]):
    async def get_by_code(self, db: AsyncSession, *, code: str) -> Optional[Permission]:
        """根据代码获取权限"""
        result = await db.execute(
            select(Permission).where(
                Permission.code == code,
                Permission.is_deleted == False
            )
        )
        return result.scalar_one_or_none()


# 创建CRUD实例
user = CRUDUser(User)
role = CRUDRole(Role)
permission = CRUDPermission(Permission)