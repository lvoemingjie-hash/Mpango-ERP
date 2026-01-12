"""
Mpango ERP Pydantic Schemas.
Exports all schema classes for easy importing.
"""
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

__all__ = [
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
]
