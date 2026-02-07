"""
S2-6: Central Error Codes System

Defines standard error codes and provides global exception handling.
All HTTP exceptions return JSON in standard format with error codes.
"""
from enum import Enum
from typing import Any, Dict, Optional
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.structured_logging import get_logger, _request_id_ctx

logger = get_logger(__name__)


class ErrorCode(str, Enum):
    """
    S2-6: Standard error codes for the application.
    
    Format: CATEGORY_SPECIFIC_ERROR
    """
    # Authentication & Authorization (401, 403)
    UNAUTHORIZED = "UNAUTHORIZED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_INVALID = "TOKEN_INVALID"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    
    # Resource Not Found (404)
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    TENANT_NOT_FOUND = "TENANT_NOT_FOUND"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    PAYMENT_NOT_FOUND = "PAYMENT_NOT_FOUND"
    SKU_NOT_FOUND = "SKU_NOT_FOUND"
    
    # Validation Errors (400, 422)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_TENANT_CODE = "INVALID_TENANT_CODE"
    INVALID_ORDER_STATE = "INVALID_ORDER_STATE"
    INVALID_PAYMENT_AMOUNT = "INVALID_PAYMENT_AMOUNT"
    
    # Business Logic Errors (409, 422)
    CONFLICT = "CONFLICT"
    DUPLICATE_RESOURCE = "DUPLICATE_RESOURCE"
    PAYMENT_IDEMPOTENCY_CONFLICT = "PAYMENT_IDEMPOTENCY_CONFLICT"
    ORDER_STATE_TRANSITION_INVALID = "ORDER_STATE_TRANSITION_INVALID"
    INSUFFICIENT_INVENTORY = "INSUFFICIENT_INVENTORY"
    
    # Server Errors (500, 503)
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    
    # Rate Limiting (429)
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    
    # Method Not Allowed (405)
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"


# HTTP Status Code to Error Code mapping
STATUS_CODE_TO_ERROR_CODE = {
    400: ErrorCode.INVALID_INPUT,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.PERMISSION_DENIED,
    404: ErrorCode.RESOURCE_NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMIT_EXCEEDED,
    500: ErrorCode.INTERNAL_SERVER_ERROR,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}


class MpangoAPIException(Exception):
    """
    S2-6: Base exception for Mpango ERP API.
    
    All custom exceptions should inherit from this and provide:
    - error_code: ErrorCode enum value
    - message: Human-readable error message
    - status_code: HTTP status code
    - details: Optional additional details
    """
    
    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


def create_error_response(
    error_code: ErrorCode,
    message: str,
    status_code: int,
    request_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    S2-6: Create standard error response format.
    
    Format:
    {
        "code": "ERROR_CODE",
        "message": "Human readable message",
        "request_id": "uuid",
        "details": {...}  // Optional
    }
    """
    response = {
        "code": error_code.value,
        "message": message,
        "request_id": request_id or _request_id_ctx.get() or "unknown"
    }
    
    if details:
        response["details"] = details
    
    return response


async def mpango_exception_handler(request: Request, exc: MpangoAPIException) -> JSONResponse:
    """
    S2-6: Handler for MpangoAPIException.
    
    Converts custom exceptions to standard error response format.
    """
    request_id = getattr(request.state, 'request_id', None)
    
    logger.error(
        f"API Exception: {exc.error_code.value}",
        extra={
            "error_code": exc.error_code.value,
            "status_code": exc.status_code,
            "details": exc.details
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            error_code=exc.error_code,
            message=exc.message,
            status_code=exc.status_code,
            request_id=request_id,
            details=exc.details
        )
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    S2-6: Handler for FastAPI HTTPException.
    
    Converts standard HTTP exceptions to error response format.
    """
    request_id = getattr(request.state, 'request_id', None)
    
    # Map status code to error code
    error_code = STATUS_CODE_TO_ERROR_CODE.get(
        exc.status_code,
        ErrorCode.INTERNAL_SERVER_ERROR
    )
    
    # Extract message from detail
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    
    logger.warning(
        f"HTTP Exception: {exc.status_code}",
        extra={
            "error_code": error_code.value,
            "status_code": exc.status_code,
            "error_message": message
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            error_code=error_code,
            message=message,
            status_code=exc.status_code,
            request_id=request_id
        ),
        headers=exc.headers
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    S2-6: Handler for Pydantic validation errors.
    
    Converts validation errors to standard error response format.
    """
    request_id = getattr(request.state, 'request_id', None)
    
    # Extract validation errors
    errors = exc.errors()
    
    logger.warning(
        "Validation error",
        extra={
            "error_code": ErrorCode.VALIDATION_ERROR.value,
            "validation_errors": errors
        }
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=create_error_response(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            request_id=request_id,
            details={"validation_errors": errors}
        )
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    S2-6: Handler for unhandled exceptions.
    S2.5 Batch B: Never expose internal error details in production.
    
    Catches all other exceptions and returns standard error response.
    Production: Returns generic message only.
    Non-production: Returns exception type and message for debugging.
    """
    request_id = getattr(request.state, 'request_id', None)
    
    logger.error(
        f"Unhandled exception: {type(exc).__name__}",
        exc_info=exc,
        extra={
            "error_code": ErrorCode.INTERNAL_SERVER_ERROR.value,
            "exception_type": type(exc).__name__
        }
    )
    
    # S2.5 Batch B: Never expose stack traces, exception types, or database errors in production
    from core.config import get_settings
    settings = get_settings()
    
    if settings.MPANGO_ENV == "production":
        # Production: Generic message only, no internal details
        message = "An internal server error occurred. Please contact support."
        details = None
    else:
        # Non-production: Include exception details for debugging
        message = f"{type(exc).__name__}: {str(exc)}"
        details = {
            "exception_type": type(exc).__name__,
            "exception_message": str(exc)
        }
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=create_error_response(
            error_code=ErrorCode.INTERNAL_SERVER_ERROR,
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            request_id=request_id,
            details=details
        )
    )


def register_exception_handlers(app) -> None:
    """
    S2-6: Register all exception handlers with FastAPI app.
    
    Call this during app initialization.
    """
    app.add_exception_handler(MpangoAPIException, mpango_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
    
    logger.info("Exception handlers registered", extra={"component": "error_handling"})
