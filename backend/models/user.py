"""
User, Role, Permission models - Tenant schema RBAC tables.
Implements database_contract.md tenant schema tables.
"""
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Boolean, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import BaseModel

if TYPE_CHECKING:
    from models.user import Role


class User(BaseModel):
    """
    User model - stored in tenant schema.

    Implements database_contract.md users table:
    - email: varchar(255), UNIQUE, NOT NULL
    - password_hash: varchar(255), NOT NULL
    - full_name: text, NULL
    - is_active: boolean, NOT NULL, DEFAULT true
    """
    __tablename__ = "users"
    __table_args__ = (
        Index('ix_users_email', 'email', unique=True),
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    full_name: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    # Relationships
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary="user_roles",
        back_populates="users",
        lazy="selectin"
    )


class Role(BaseModel):
    """
    Role model - stored in tenant schema.

    Implements database_contract.md roles table:
    - name: varchar(100), UNIQUE, NOT NULL
    - description: text, NULL

    Default roles per rbac_matrix.md: admin, sales, warehouse, finance
    """
    __tablename__ = "roles"
    __table_args__ = (
        Index('ix_roles_name', 'name', unique=True),
    )

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    # Relationships
    users: Mapped[List["User"]] = relationship(
        "User",
        secondary="user_roles",
        back_populates="roles",
        lazy="selectin"
    )
    permissions: Mapped[List["Permission"]] = relationship(
        "Permission",
        secondary="role_permissions",
        back_populates="roles",
        lazy="selectin"
    )


class Permission(BaseModel):
    """
    Permission model - stored in tenant schema.

    Implements database_contract.md permissions table:
    - code: varchar(100), UNIQUE, NOT NULL (format: <resource>:<action>)
    - description: text, NULL

    Permission codes per rbac_matrix.md: users:read, orders:create, etc.
    """
    __tablename__ = "permissions"
    __table_args__ = (
        Index('ix_permissions_code', 'code', unique=True),
    )

    code: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Permission code format: <resource>:<action>"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    # Relationships
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary="role_permissions",
        back_populates="permissions",
        lazy="selectin"
    )
