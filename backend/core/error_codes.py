"""
S2-6: Central Error Codes System

Defines standard error codes and provides global exception handling.
All HTTP exceptions return JSON in standard format with error codes.
"""
import math
import re
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
    ``{code, message, request_id}`` — the handler never creates a Python
    ``str(dict)``/``str(list)`` repr by stringifying a non-string detail.

    Detail handling:
    - **dict detail**: a non-empty, identifier-safe string ``code`` is
      preserved (oversized/malformed codes fall back to the status-derived
      code); only a string ``message`` is preserved; an explicitly-public,
      genuinely JSON-safe ``details`` mapping is optionally preserved.
      The complete dict is NEVER stringified.
    - **string detail**: the message is preserved verbatim; the code is
      derived from the status mapping (existing behaviour).
    - **malformed/non-string detail** (list, int, None, object): a fixed
      sanitized fallback message is used; the raw value is never surfaced.

    The handler itself NEVER raises: any unexpected error while normalizing a
    detail is caught and fail-closed to the standard envelope with the
    original HTTP status preserved.
    """
    request_id = getattr(request.state, 'request_id', None)

    try:
        body, public_code, message, details = _build_error_body(exc, request_id)
    except Exception:
        # DC-12R1-H2-R1: the exception handler must never raise. Any
        # normalization failure fail-closes to a sanitized envelope, still
        # preserving the original HTTP status, code and request_id.
        status_code = exc.status_code if isinstance(getattr(exc, "status_code", None), int) else 500
        error_code = STATUS_CODE_TO_ERROR_CODE.get(status_code, ErrorCode.INTERNAL_SERVER_ERROR)
        message = _status_fallback_message(status_code)
        details = None
        public_code = error_code.value
        body = create_error_response(
            error_code=error_code,
            message=message,
            status_code=status_code,
            request_id=request_id,
        )
        body["code"] = public_code

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

    return JSONResponse(
        status_code=exc.status_code,
        content=body,
        headers=exc.headers
    )


def _build_error_body(exc: HTTPException, request_id: Optional[str]):
    """Normalize ``exc.detail`` into the flat error envelope components.

    Returns ``(body, public_code, message, details)``. Pure normalization
    only — raises on unexpected error so ``http_exception_handler`` can
    fail-close uniformly.
    """
    error_code = STATUS_CODE_TO_ERROR_CODE.get(
        exc.status_code,
        ErrorCode.INTERNAL_SERVER_ERROR
    )

    message: str
    details: Optional[Dict[str, Any]] = None
    detail = exc.detail
    # The public code to emit. Defaults to the status-derived ErrorCode; may be
    # overridden by a non-empty, safe string code in a dict detail.
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
        # Optionally preserve an explicitly-public, genuinely JSON-safe details
        # mapping. Unsafe details are OMITTED — never surfaced — while the
        # original HTTP status, sanitized code/message and request_id survive.
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

    body = create_error_response(
        error_code=error_code,
        message=message,
        status_code=exc.status_code,
        request_id=request_id,
        details=details,
    )
    body["code"] = public_code
    return body, public_code, message, details


_SAFE_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


def _is_safe_code(candidate: str) -> bool:
    """True if *candidate* is a strict, public error-code identifier.

    DC-12R1-H2-R1: codes are constrained to ``^[A-Z][A-Z0-9_]{0,63}$`` — an
    UPPER_SNAKE identifier (max 64 chars) so a caller-supplied code passes
    through, but oversized/malformed codes (braces, quotes, spaces, lowercase,
    repr markers, non-ASCII) are rejected and fall back to the status-derived
    code. Nothing that could smuggle structure is accepted.
    """
    return isinstance(candidate, str) and bool(_SAFE_CODE_RE.match(candidate))


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
    """True if *value* is a genuinely JSON-safe structure safe to surface.

    DC-12R1-H2-R1 hardening. A public ``details`` payload is only preserved
    when it is fully JSON-safe:

    - mappings require **string keys** at every level (top-level and nested);
      any non-string key fails closed
    - leaf values are restricted to ``None``, ``bool``, ``int``, ``str`` and
      finite ``float``
    - **NaN / +Infinity / -Infinity** floats are rejected
    - ``bytes``, ``set``, ``tuple`` and arbitrary objects are rejected
    - nested containers must themselves be JSON-safe dicts (string keys) or
      lists; other iterables/types are rejected

    Unsafe details are OMITTED by the caller — never surfaced — while the
    original HTTP status, sanitized code/message and request_id survive.
    """
    return _is_json_safe_value(value)


def _is_json_safe_value(value: Any) -> bool:
    """Recursive JSON-safety check (string-keyed dicts + JSON primitives)."""
    if value is None:
        return True
    # bool is a subclass of int — check before int so it stays its own case,
    # but both are accepted.
    if isinstance(value, bool):
        return True
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        # Reject NaN and +/-Infinity (not representable in strict JSON).
        return math.isfinite(value)
    if isinstance(value, str):
        return True
    # Explicitly reject other common container/binary types before the generic
    # dict/list handling so they can never slip through.
    if isinstance(value, (bytes, bytearray, set, frozenset, tuple)):
        return False
    if isinstance(value, dict):
        # String keys required at every level.
        for key in value.keys():
            if not isinstance(key, str):
                return False
        return all(_is_json_safe_value(v) for v in value.values())
    if isinstance(value, list):
        return all(_is_json_safe_value(v) for v in value)
    # Any other type (objects, callables, custom classes, generators, ...).
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
