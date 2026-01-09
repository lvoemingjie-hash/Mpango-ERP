from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    """用户基础字段"""
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool = True


class UserCreate(UserBase):
    """创建用户"""
    password: str


class UserUpdate(BaseModel):
    """更新用户"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserRead(UserBase):
    """用户响应"""
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class RoleBase(BaseModel):
    """角色基础字段"""
    name: str
    description: Optional[str] = None


class RoleCreate(RoleBase):
    """创建角色"""
    pass


class RoleUpdate(BaseModel):
    """更新角色"""
    name: Optional[str] = None
    description: Optional[str] = None


class RoleRead(RoleBase):
    """角色响应"""
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PermissionBase(BaseModel):
    """权限基础字段"""
    code: str
    description: Optional[str] = None


class PermissionCreate(PermissionBase):
    """创建权限"""
    pass


class PermissionRead(PermissionBase):
    """权限响应"""
    id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class UserWithRoles(UserRead):
    """带角色的用户"""
    roles: List[RoleRead] = []


class RoleWithPermissions(RoleRead):
    """带权限的角色"""
    permissions: List[PermissionRead] = []