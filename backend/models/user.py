from sqlalchemy import Column, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database.base import BaseModel


class User(BaseModel):
    """用户模型 - 存储在租户schema中"""
    __tablename__ = "users"
    
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # 用户角色关系（多对多）
    roles = relationship("UserRole", back_populates="user")


class Role(BaseModel):
    """角色模型 - 存储在租户schema中"""
    __tablename__ = "roles"
    
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(500), nullable=True)
    
    # 角色权限关系（多对多）
    permissions = relationship("RolePermission", back_populates="role")
    users = relationship("UserRole", back_populates="role")


class Permission(BaseModel):
    """权限模型 - 存储在租户schema中"""
    __tablename__ = "permissions"
    
    code = Column(String(100), unique=True, nullable=False, index=True)  # e.g., 'users:read'
    description = Column(String(500), nullable=True)
    
    # 权限角色关系（多对多）
    roles = relationship("RolePermission", back_populates="permission")


class UserRole(BaseModel):
    """用户角色关联表"""
    __tablename__ = "user_roles"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    
    # 关系
    user = relationship("User", back_populates="roles")
    role = relationship("Role", back_populates="users")


class RolePermission(BaseModel):
    """角色权限关联表"""
    __tablename__ = "role_permissions"
    
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)
    
    # 关系
    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="roles")