"""
JWT Authentication middleware for Mpango ERP.
Validates Bearer tokens and extracts user context.

Per requirements REQ-2:
- Validates JWT tokens on every request
- Returns appropriate 401 error codes for invalid/expired/missing tokens
"""
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.security import (
    decode_token,
    TokenPayload,
    InvalidTokenError,
    ExpiredTokenError
)


class JWTBearer(HTTPBearer):
    """
    JWT Bearer token authentication dependency.
    
    Usage:
        @router.get("/protected")
        async def protected_route(token: TokenPayload = Depends(JWTBearer())):
            # token contains user_id, tenant_id, tenant_schema
    """
    
    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)
    
    async def __call__(self, request: Request) -> TokenPayload:
        """
        Validate JWT token from Authorization header.
        
        Args:
            request: FastAPI request object
            
        Returns:
            TokenPayload with decoded claims
            
        Raises:
            HTTPException 401: For missing, invalid, or expired tokens
        """
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)
        
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "MISSING_TOKEN", "message": "Authorization header required"},
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        if credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_SCHEME", "message": "Bearer scheme required"},
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        try:
            payload = decode_token(credentials.credentials)
            
            # Validate token type is access (not refresh)
            if payload.type != "access":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"code": "INVALID_TOKEN_TYPE", "message": "Access token required"},
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            return payload
            
        except ExpiredTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "TOKEN_EXPIRED", "message": "Token has expired"},
                headers={"WWW-Authenticate": "Bearer"}
            )
        except InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_TOKEN", "message": "Invalid token"},
                headers={"WWW-Authenticate": "Bearer"}
            )


# Singleton instance for convenience
jwt_bearer = JWTBearer()
