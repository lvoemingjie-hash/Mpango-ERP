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


# HTTP 异常映射
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
