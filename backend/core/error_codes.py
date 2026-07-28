"""
S2-6: Central Error Codes System

Defines standard error codes and provides global exception handling.
All HTTP exceptions return JSON in standard format with error codes.
"""
from enum import Enum
from typing import Any, Dict, Optional
from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
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
    """DC-12R1-H2: Handler for FastAPI HTTPException.

    Serializes EVERY HTTPException into the standard flat envelope
    ``{code, message, request_id}`` — never a Python ``str(dict)`` repr
    leaking into the ``message`` field.

    Detail handling:
    - **dict detail**: a non-empty string ``code`` is preserved (falling back
      to the status-derived code); only a string ``message`` is preserved;
      an explicitly-public, JSON-safe ``details`` mapping is optionally
      preserved. The complete dict is NEVER stringified.
    - **string detail**: the message is preserved verbatim; the code is
      derived from the status mapping (existing behaviour).
    - **malformed/non-string detail** (list, int, None, object): a fixed
      sanitized fallback message is used; the raw value is never surfaced.
    """
    request_id = getattr(request.state, 'request_id', None)

    # Map status code to the default error code.
    error_code = STATUS_CODE_TO_ERROR_CODE.get(
        exc.status_code,
        ErrorCode.INTERNAL_SERVER_ERROR
    )

    message: str
    details: Optional[Dict[str, Any]] = None
    detail = exc.detail
    # The public code to emit. Defaults to the status-derived ErrorCode; may be
    # overridden by a non-empty string code in a dict detail.
    public_code: str = error_code.value

    if isinstance(detail, str):
        # Plain string detail: preserve verbatim (backward compatible).
        message = detail
    elif isinstance(detail, dict):
        # Structured dict detail (the RBAC/tenant/platform convention).
        # Preserve a non-empty, identifier-safe string code if supplied.
        raw_code = detail.get("code")
        if isinstance(raw_code, str) and raw_code.strip():
            candidate = raw_code.strip()
            if _is_safe_code(candidate):
                public_code = candidate
        # Preserve ONLY a string message; never stringify the whole dict.
        raw_message = detail.get("message")
        message = raw_message if isinstance(raw_message, str) and raw_message else (
            _status_fallback_message(exc.status_code)
        )
        # Optionally preserve an explicitly-public, JSON-safe details mapping.
        raw_details = detail.get("details")
        if isinstance(raw_details, dict) and _is_json_safe(raw_details):
            details = raw_details
    else:
        # Malformed detail (list, int, None, object, ...): fail closed to a
        # sanitized generic message. The raw value is never surfaced.
        message = _status_fallback_message(exc.status_code)

    # Belt-and-braces: guarantee the message is a plain string with no
    # serialized structure that could leak internals.
    if not isinstance(message, str) or not message:
        message = _status_fallback_message(exc.status_code)
    message = _sanitize_message(message)

    # Logging: sanitized code + status only. NEVER log the raw detail repr.
    logger.warning(
        f"HTTP Exception: {exc.status_code}",
        extra={
            "error_code": public_code,
            "status_code": exc.status_code,
            # Intentionally NO raw detail/message here — logs must not carry
            # a dict repr or request content.
        }
    )

    body = create_error_response(
        error_code=error_code,
        message=message,
        status_code=exc.status_code,
        request_id=request_id,
        details=details,
    )
    # Apply the (possibly overridden) public code verbatim.
    body["code"] = public_code

    return JSONResponse(
        status_code=exc.status_code,
        content=body,
        headers=exc.headers
    )


def _is_safe_code(candidate: str) -> bool:
    """True if *candidate* is an identifier-safe error code string.

    Allows UPPER_SNAKE codes (and simple alphanumerics) so a caller-supplied
    code passes through, but rejects anything that could smuggle structure
    (braces, quotes, spaces, repr markers).
    """
    if not candidate:
        return False
    # UPPER_SNAKE_CASE / alphanumeric only.
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
    return all(c in allowed for c in candidate)


def _status_fallback_message(status_code: int) -> str:
    """Return a fixed, sanitized human message for a status code.

    Used when a detail is malformed/missing so we never surface raw content.
    """
    fallbacks = {
        400: "Invalid request.",
        401: "Authentication required.",
        403: "Access denied.",
        404: "Resource not found.",
        405: "Method not allowed.",
        409: "Request conflicts with the current state.",
        422: "Request validation failed.",
        429: "Rate limit exceeded. Please try again later.",
    }
    return fallbacks.get(status_code, "Request could not be completed.")


def _sanitize_message(message: str) -> str:
    """Ensure a message carries no serialized Python structure.

    A genuine human message never contains a dict/list repr; if one slipped
    through (e.g. a caller stuffed a non-string into ``message``), replace it
    with a safe generic rather than leak it.
    """
    if "{'" in message or "'}" in message or "['" in message:
        # Looks like a str(dict)/str(list) repr — refuse to emit it.
        return "Request could not be completed."
    return message


def _is_json_safe(value: Any) -> bool:
    """True if *value* is a JSON-safe mapping of primitives (safe to surface).

    Prevents nested objects, callables, bytes, or arbitrary types from being
    forwarded into a public ``details`` field.
    """
    if not isinstance(value, dict):
        return False
    for v in value.values():
        if isinstance(v, (dict, list)):
            if not _is_json_safe_nested(v):
                return False
        elif not isinstance(v, (str, int, float, bool)) and v is not None:
            return False
    return True


def _is_json_safe_nested(value: Any) -> bool:
    if isinstance(value, dict):
        return all(
            (isinstance(v, (str, int, float, bool)) or v is None
             or (isinstance(v, (dict, list)) and _is_json_safe_nested(v)))
            for v in value.values()
        )
    if isinstance(value, list):
        return all(
            isinstance(v, (str, int, float, bool)) or v is None
            or (isinstance(v, (dict, list)) and _is_json_safe_nested(v))
            for v in value
        )
    return False


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    S2-6: Handler for Pydantic validation errors.

    Converts validation errors to standard error response format.
    """
    request_id = getattr(request.state, 'request_id', None)

    # Extract validation errors
    errors = exc.errors()
    encoded_errors = jsonable_encoder(errors)

    logger.warning(
        "Validation error",
        extra={
            "error_code": ErrorCode.VALIDATION_ERROR.value,
            "validation_errors": encoded_errors
        }
    )

    content = create_error_response(
        error_code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        request_id=request_id,
        details={"validation_errors": errors}
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder(content)
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
