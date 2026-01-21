"""Authentication context helpers."""
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request, status

from core.security import TokenPayload, decode_token, ExpiredTokenError, InvalidTokenError

_AUTH_CONTEXT_ATTR = "auth_context"


def _http_exc(detail_code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": detail_code, "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


@dataclass
class AuthContext:
    """Container for authenticated request details."""

    token: TokenPayload
    raw_token: str


def extract_bearer_token(request: Request) -> Optional[str]:
    """Extract bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    scheme, _, credentials = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not credentials:
        raise _http_exc("INVALID_AUTH_SCHEME", "Bearer token required in Authorization header")

    return credentials.strip()


def resolve_auth_context(raw_token: str) -> AuthContext:
    """Decode JWT and build auth context."""
    try:
        payload = decode_token(raw_token)
    except ExpiredTokenError as exc:
        raise _http_exc("TOKEN_EXPIRED", "Token has expired") from exc
    except InvalidTokenError as exc:
        raise _http_exc("INVALID_TOKEN", "Invalid token") from exc

    return AuthContext(token=payload, raw_token=raw_token)


def attach_auth_context(request: Request, context: AuthContext) -> None:
    """Attach auth context to request state."""
    setattr(request.state, _AUTH_CONTEXT_ATTR, context)


def clear_auth_context(request: Request) -> None:
    """Remove auth context from request state."""
    if hasattr(request.state, _AUTH_CONTEXT_ATTR):
        delattr(request.state, _AUTH_CONTEXT_ATTR)


def get_auth_context(request: Request) -> AuthContext:
    """Retrieve auth context from request state or raise 401."""
    context = getattr(request.state, _AUTH_CONTEXT_ATTR, None)
    if context is None:
        raise _http_exc("UNAUTHENTICATED", "Authentication required")
    return context
