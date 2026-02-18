from fastapi import HTTPException, status


class MpangoException(Exception):
    """Mpango ERP 基础异常类"""
    pass


class TenantNotFoundException(MpangoException):
    """租户未找到异常"""
    pass


class InvalidTenantCodeException(MpangoException):
    """无效租户代码异常"""
    pass


class PermissionDeniedException(MpangoException):
    """权限拒绝异常"""
    pass


class UserNotFoundException(MpangoException):
    """用户未找到异常"""
    pass


class InvalidCredentialsException(MpangoException):
    """无效凭据异常"""
    pass


class LedgerIntegrityError(MpangoException):
    """
    Ledger integrity violation exception.
    
    Raised when a ledger transaction violates double-entry bookkeeping rules.
    Philosophy: "The Ledger is write-only. No exceptions."
    """
    pass


class InventoryShortageError(MpangoException):
    """
    Raised when a stock deduction exceeds available inventory.

    Callers should catch this and return HTTP 409 with code INVENTORY_SHORTAGE.
    See docs/policies/exception_strategy.md §3.
    """
    def __init__(self, sku_code: str, available, requested):
        self.sku_code = sku_code
        self.available = available
        self.requested = requested
        super().__init__(
            f"Insufficient stock for SKU '{sku_code}'. "
            f"Available: {available}, requested: {requested}."
        )


class StaleVersionError(MpangoException):
    """
    Raised when an optimistic lock version check fails.
    HTTP 409 with code STALE_VERSION.
    """
    pass



def tenant_not_found():
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Tenant not found"
    )


def invalid_tenant_code():
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid tenant code format"
    )


def permission_denied():
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Permission denied"
    )


def user_not_found():
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="User not found"
    )


def invalid_credentials():
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def business_conflict(code: str, message: str):
    """
    Standard 409 helper for business logic conflicts.
    
    Usage:
        raise business_conflict("INVENTORY_SHORTAGE", "Available: 5, requested: 10")
    """
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": message},
    )
