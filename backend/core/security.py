"""
Security utilities for Mpango ERP.
Implements JWT token handling and password hashing.

Per multi_tenancy_spec.md section 4.1, JWT claims must contain:
- user_id: UUID
- tenant_id: UUID  
- tenant_schema: string
- exp: expiration timestamp
- type: "access" or "refresh"
"""
from datetime import datetime, timedelta
from typing import Optional

from jose import jwt, JWTError, ExpiredSignatureError
from passlib.context import CryptContext
from pydantic import BaseModel

from core.config import get_settings


# Custom exceptions
class InvalidTokenError(Exception):
    """Raised when JWT token is invalid (bad signature, malformed, etc.)."""
    pass


class ExpiredTokenError(Exception):
    """Raised when JWT token has expired."""
    pass


# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenPayload(BaseModel):
    """
    JWT token payload schema.
    Per multi_tenancy_spec.md section 4.1.
    """
    user_id: str
    tenant_id: str
    tenant_schema: str
    exp: Optional[int] = None
    type: str = "access"  # "access" or "refresh"


def create_access_token(
    user_id: str,
    tenant_id: str,
    tenant_schema: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT access token with tenant claims.
    
    Args:
        user_id: User UUID as string
        tenant_id: Tenant UUID as string
        tenant_schema: Tenant schema name (e.g., "t_abc123...")
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT string
    """
    settings = get_settings()
    
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    expire = datetime.utcnow() + expires_delta
    
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "tenant_schema": tenant_schema,
        "exp": expire,
        "type": "access"
    }
    
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    user_id: str,
    tenant_id: str,
    tenant_schema: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT refresh token with tenant claims.
    
    Args:
        user_id: User UUID as string
        tenant_id: Tenant UUID as string
        tenant_schema: Tenant schema name (e.g., "t_abc123...")
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT string
    """
    settings = get_settings()
    
    if expires_delta is None:
        expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    expire = datetime.utcnow() + expires_delta
    
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "tenant_schema": tenant_schema,
        "exp": expire,
        "type": "refresh"
    }
    
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> TokenPayload:
    """
    Decode and validate JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        TokenPayload with decoded claims
        
    Raises:
        ExpiredTokenError: If token has expired
        InvalidTokenError: If token is invalid (bad signature, malformed)
    """
    settings = get_settings()
    
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return TokenPayload(**payload)
    except ExpiredSignatureError:
        raise ExpiredTokenError("Token has expired")
    except JWTError as e:
        raise InvalidTokenError(f"Invalid token: {str(e)}")


# Password utilities using bcrypt
def hash_password(password: str) -> str:
    """
    Hash password using bcrypt.
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password string
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against hash.
    
    Args:
        plain_password: Plain text password to verify
        hashed_password: Stored password hash
        
    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)
