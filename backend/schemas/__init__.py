"""
Mpango ERP Pydantic Schemas.
Exports all schema classes for easy importing.
"""
from schemas.base import CamelModel
from schemas.common import (
    Pagination,
    ErrorDetail,
    ErrorResponse,
    MessageResponse,
    DataResponse,
    PaginatedResponse
)
from schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    TokenData,
    CurrentUserData,
    CurrentUserResponse,
    TokenPayload
)
from schemas.user import (
    UserCreateRequest,
    UserUpdateRequest,
    UserRead,
    UserResponse,
    UserListResponse,
    AssignRolesRequest,
    RoleRead,
    RoleListResponse
)
from schemas.order import (
    OrderStatus,
    OrderItemCreate,
    OrderItem,
    OrderCreateRequest,
    Order,
    OrderResponse,
    OrderListResponse,
    OrderActionResponse
)
from schemas.wholesaler import (
    WholesalerCreate,
    WholesalerUpdate,
    WholesalerRead,
    WholesalerResponse,
    WholesalerListResponse
)

__all__ = [
    # Base
    "CamelModel",

    # Common
    "Pagination",
    "ErrorDetail",
    "ErrorResponse",
    "MessageResponse",
    "DataResponse",
    "PaginatedResponse",

    # Auth
    "LoginRequest",
    "LoginResponse",
    "RefreshTokenRequest",
    "TokenData",
    "CurrentUserData",
    "CurrentUserResponse",
    "TokenPayload",

    # User
    "UserCreateRequest",
    "UserUpdateRequest",
    "UserRead",
    "UserResponse",
    "UserListResponse",
    "AssignRolesRequest",
    "RoleRead",
    "RoleListResponse",

    # Order
    "OrderStatus",
    "OrderItemCreate",
    "OrderItem",
    "OrderCreateRequest",
    "Order",
    "OrderResponse",
    "OrderListResponse",
    "OrderActionResponse",

    # Wholesaler
    "WholesalerCreate",
    "WholesalerUpdate",
    "WholesalerRead",
    "WholesalerResponse",
    "WholesalerListResponse",
]
