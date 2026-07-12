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
from typing import Dict, List, Optional

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

    Two token modes:
    - Identity token: user_id + roles only (tenant_id/tenant_schema are None)
    - Contextual token: user_id + roles + tenant_id + tenant_schema

    Identity tokens are issued at login before tenant selection.
    Contextual tokens are issued after POST /auth/select-tenant.
    """
    user_id: str
    tenant_id: Optional[str] = None
    tenant_schema: Optional[str] = None
    roles: List[str] = []
    exp: Optional[int] = None
    type: str = "access"  # "access" or "refresh"
    # DC-3B-R2: signed tenant_id -> tenant-local user_id map for verified
    # identity-only tokens. Lets /select-tenant resolve the correct per-tenant
    # user_id when the same email exists in multiple tenants with different
    # user IDs. Absent on contextual tokens and on legacy identity tokens.
    # This claim is SIGNED but NOT ENCRYPTED: it is client-decodable (any JWT
    # holder can read it) and therefore NOT confidential. It guarantees
    # integrity only (tampering is detected via signature verification). It
    # must contain ONLY verified tenant_id -> user_id pairs and must never
    # include unverified tenants, password hashes, token hashes, or raw tokens.
    tmap: Optional[Dict[str, str]] = None

    @property
    def is_identity_only(self) -> bool:
        """True if this token has no tenant context."""
        return self.tenant_id is None or self.tenant_schema is None

    @property
    def is_super_admin(self) -> bool:
        """True if the token carries the super_admin role."""
        return "super_admin" in self.roles


def create_identity_token(
    user_id: str,
    roles: List[str],
    *,
    token_type: str = "access",
    expires_delta: Optional[timedelta] = None,
    tenant_user_map: Optional[Dict[str, str]] = None,
) -> str:
    """
    Create an Identity JWT -- no tenant context.

    Issued at login before tenant selection.  Contains user_id and roles
    so the frontend can show tenant picker / super-admin UI.

    Args:
        user_id: User UUID as string
        roles: Aggregated role names across all tenants (or ["super_admin"])
        token_type: "access" or "refresh"
        expires_delta: Optional custom expiration time
        tenant_user_map: Optional signed {tenant_id: tenant_local_user_id} map
            of VERIFIED tenant matches (DC-3B-R1). Carried so /select-tenant
            can resolve the correct per-tenant user_id when the same email
            exists in multiple tenants with different user IDs. Only verified
            matches (password_hash verified at login) are included.
    """
    settings = get_settings()
    if expires_delta is None:
        expires_delta = (
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            if token_type == "access"
            else timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        )
    expire = datetime.utcnow() + expires_delta
    payload = {
        "user_id": user_id,
        "roles": roles,
        "exp": expire,
        "type": token_type,
    }
    if tenant_user_map:
        payload["tmap"] = tenant_user_map
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_contextual_token(
    user_id: str,
    roles: List[str],
    tenant_id: str,
    tenant_schema: str,
    *,
    token_type: str = "access",
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a Contextual JWT -- includes tenant context.

    Issued after POST /auth/select-tenant.  The existing Tenant Guardrail
    (ORM filtering) reads tenant_id / tenant_schema from this token.

    Args:
        user_id: User UUID as string
        roles: Role names for this user **within** the selected tenant
        tenant_id: Tenant (wholesaler) UUID as string
        tenant_schema: Tenant schema name (e.g., "t_abc123...")
        token_type: "access" or "refresh"
        expires_delta: Optional custom expiration time
    """
    settings = get_settings()
    if expires_delta is None:
        expires_delta = (
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            if token_type == "access"
            else timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        )
    expire = datetime.utcnow() + expires_delta
    payload = {
        "user_id": user_id,
        "roles": roles,
        "tenant_id": tenant_id,
        "tenant_schema": tenant_schema,
        "exp": expire,
        "type": token_type,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(
    user_id: str,
    tenant_id: str,
    tenant_schema: str,
    expires_delta: Optional[timedelta] = None,
    roles: Optional[List[str]] = None,
) -> str:
    """
    Create JWT access token with tenant claims.

    Legacy wrapper -- delegates to create_contextual_token.
    Kept for backward compatibility with existing callers.
    """
    return create_contextual_token(
        user_id=user_id,
        roles=roles or [],
        tenant_id=tenant_id,
        tenant_schema=tenant_schema,
        token_type="access",
        expires_delta=expires_delta,
    )


def create_refresh_token(
    user_id: str,
    tenant_id: str,
    tenant_schema: str,
    expires_delta: Optional[timedelta] = None,
    roles: Optional[List[str]] = None,
) -> str:
    """
    Create JWT refresh token with tenant claims.

    Legacy wrapper -- delegates to create_contextual_token.
    Kept for backward compatibility with existing callers.
    """
    return create_contextual_token(
        user_id=user_id,
        roles=roles or [],
        tenant_id=tenant_id,
        tenant_schema=tenant_schema,
        token_type="refresh",
        expires_delta=expires_delta,
    )


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
    # Truncate password to 72 bytes for bcrypt compatibility
    return pwd_context.hash(password[:72])


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Stored password hash

    Returns:
        True if password matches, False otherwise
    """
    # Truncate password to 72 bytes for bcrypt compatibility
    return pwd_context.verify(plain_password[:72], hashed_password)
