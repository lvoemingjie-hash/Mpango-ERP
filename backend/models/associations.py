"""
Association tables for many-to-many relationships.
Implements database_contract.md M2M tables with CASCADE delete.
"""
from sqlalchemy import Table, Column, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base


# User-Role M2M association table
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False
    ),
    Column(
        "role_id",
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False
    ),
    Index('ix_user_roles_user_id', 'user_id'),
    Index('ix_user_roles_role_id', 'role_id'),
)


# Role-Permission M2M association table
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False
    ),
    Column(
        "permission_id",
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False
    ),
    Index('ix_role_permissions_role_id', 'role_id'),
    Index('ix_role_permissions_permission_id', 'permission_id'),
)
