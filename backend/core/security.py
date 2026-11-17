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
from typing import Annotated, Dict, List, Optional
from uuid import UUID

from jose import jwt, JWTError, ExpiredSignatureError
from passlib.context import CryptContext
from pydantic import BaseModel, Field, StrictInt, ValidationError

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

CredentialEpoch = Annotated[StrictInt, Field(gt=0, le=9223372036854775807)]
SESSION_VERSION = 2


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
    # Signed revocation state, never a substitute for current DB authority.
    # Optional here for internal single-layer contexts; decode/mint require v2.
    sv: Optional[StrictInt] = None
    credential_epoch: Optional[CredentialEpoch] = None
    tver: Optional[Dict[str, CredentialEpoch]] = None

    @property
    def is_identity_only(self) -> bool:
        """True if this token has no tenant context."""
        return self.tenant_id is None or self.tenant_schema is None

    @property
    def is_super_admin(self) -> bool:
        """True if the token carries the super_admin role."""
        return "super_admin" in self.roles


def validate_session_claims(token: TokenPayload) -> None:
    """Reject legacy/unbound credentials; never upgrade missing state from DB."""
    if token.sv != SESSION_VERSION:
        raise InvalidTokenError("Session protocol requires a new login")
    try:
        if str(UUID(token.user_id)) != token.user_id:
            raise ValueError
        if token.tenant_id is None and token.tenant_schema is None:
            if not token.tmap or not token.tver or set(token.tmap) != set(token.tver):
                raise ValueError
            if token.credential_epoch is not None or token.user_id not in token.tmap.values():
                raise ValueError
            for tid, uid in token.tmap.items():
                if str(UUID(tid)) != tid or str(UUID(uid)) != uid:
                    raise ValueError
                if not credential_epoch_matches(token.tver[tid], token.tver[tid]):
                    raise ValueError
        else:
            if (not token.tenant_id or not token.tenant_schema or token.tmap is not None
                    or token.tver is not None):
                raise ValueError
            tid = UUID(token.tenant_id)
            if str(tid) != token.tenant_id or token.tenant_schema != "t_" + tid.hex:
                raise ValueError
            if not credential_epoch_matches(token.credential_epoch, token.credential_epoch):
                raise ValueError
    except (TypeError, ValueError, AttributeError, KeyError):
        raise InvalidTokenError("Invalid session binding") from None


def credential_epoch_matches(signed: object, current: object) -> bool:
    """No coercion/default epoch: bool, missing and mock values fail closed."""
    return (type(signed) is int and type(current) is int
            and 0 < signed <= 9223372036854775807 and signed == current)


def selected_credential_binding(token: TokenPayload, tenant_id: str) -> tuple[str, int]:
    """Constrain a tenant switch to an already signed, validated binding."""
    validate_session_claims(token)
    if token.is_identity_only:
        if tenant_id not in token.tmap:
            raise InvalidTokenError("Tenant not in session bindings")
        return token.tmap[tenant_id], token.tver[tenant_id]
    if token.tenant_id != tenant_id:
        raise InvalidTokenError("Sign in again to change tenant context")
    return token.user_id, token.credential_epoch


def create_identity_token(
    user_id: str,
    roles: List[str],
    *,
    token_type: str = "access",
    expires_delta: Optional[timedelta] = None,
    tenant_user_map: Optional[Dict[str, str]] = None,
    tenant_credential_epochs: Optional[Dict[str, int]] = None,
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
    validate_session_claims(TokenPayload(
        user_id=user_id, roles=roles, sv=SESSION_VERSION,
        tmap=tenant_user_map, tver=tenant_credential_epochs,
    ))
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
        "sv": SESSION_VERSION,
        "tver": tenant_credential_epochs,
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
    credential_epoch: int,
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
    validate_session_claims(TokenPayload(
        user_id=user_id, tenant_id=tenant_id, tenant_schema=tenant_schema,
        roles=roles, sv=SESSION_VERSION, credential_epoch=credential_epoch,
    ))
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
        "sv": SESSION_VERSION,
        "credential_epoch": credential_epoch,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(
    user_id: str,
    tenant_id: str,
    tenant_schema: str,
    expires_delta: Optional[timedelta] = None,
    roles: Optional[List[str]] = None,
    *,
    credential_epoch: int,
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
        credential_epoch=credential_epoch,
    )


def create_refresh_token(
    user_id: str,
    tenant_id: str,
    tenant_schema: str,
    expires_delta: Optional[timedelta] = None,
    roles: Optional[List[str]] = None,
    *,
    credential_epoch: int,
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
        credential_epoch=credential_epoch,
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
        if payload.get("type") not in ("access", "refresh"):
            raise InvalidTokenError("Token purpose is missing or invalid")
        token_payload = TokenPayload(**payload)
        validate_session_claims(token_payload)
        return token_payload
    except ExpiredSignatureError:
        raise ExpiredTokenError("Token has expired")
    except JWTError as e:
        raise InvalidTokenError(f"Invalid token: {str(e)}")
    except (ValidationError, TypeError, ValueError):
        raise InvalidTokenError("Invalid token claims") from None


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
