from typing import Optional
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """登录请求"""
    tenant_code: str
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    tenant_id: str
    tenant_schema: str


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求"""
    refresh_token: str


class TokenPayload(BaseModel):
    """JWT载荷"""
    user_id: str
    tenant_id: str
    tenant_schema: str
    exp: Optional[int] = None