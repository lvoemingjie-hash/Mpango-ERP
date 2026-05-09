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
from models.retailer_price import RetailerPrice
from models.reporting import MvSalesDaily, RptSalesDaily, RptReceivablesSummary, RptCashFlowDaily
from models.audit import SysAuditLog
from models.report import SysReport
from models.platform_tenant import PlatformTenant
from models.platform_audit_log import PlatformAuditLog

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
    "RetailerPrice",

    # Enums
    "OrderStatus",

    # Association tables
    "user_roles",
    "role_permissions",

    # S6-1/S6-2: Reporting Read Models (views & materialized views)
    "MvSalesDaily",
    "RptSalesDaily",
    "RptReceivablesSummary",
    "RptCashFlowDaily",

    # S7-3: Audit Trail
    "SysAuditLog",

    # S7-4: Tenant-Scoped Reports
    "SysReport",

    # Platform P0: Tenant lifecycle journal
    "PlatformTenant",
]
