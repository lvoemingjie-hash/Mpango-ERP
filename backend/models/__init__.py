"""
Mpango ERP ORM Models.
Exports all models and association tables for Alembic migrations.
"""
from models.base import Base, BaseModel, PublicBaseModel, AuditMixin, UserTrackingMixin
from models.wholesaler import Wholesaler
from models.user import User, Role, Permission
from models.associations import user_roles, role_permissions
from models.order import Order, OrderItem, OrderStatus
from models.retailer import Retailer
from models.invitation import Invitation
from models.binding import WholesalerRetailerBinding
from models.sku import SKU
from models.inventory_stock import InventoryStock

__all__ = [
    # Base classes
    "Base",
    "BaseModel",
    "PublicBaseModel",
    "AuditMixin",
    "UserTrackingMixin",

    # Public schema models
    "Wholesaler",
    "Retailer",
    "Invitation",
    "WholesalerRetailerBinding",

    # Tenant schema models
    "User",
    "Role",
    "Permission",
    "Order",
    "OrderItem",
    "SKU",
    "InventoryStock",

    # Enums
    "OrderStatus",

    # Association tables
    "user_roles",
    "role_permissions",
]
