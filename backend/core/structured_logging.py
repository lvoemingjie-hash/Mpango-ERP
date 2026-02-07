"""
S2-2: Structured Logging System

Provides JSON-formatted structured logging with automatic context injection.
All logs include: timestamp, level, service, env, request_id, tenant_schema, user_id, etc.
"""
import logging
import sys
import json
from datetime import datetime
from typing import Any, Dict, Optional
from contextvars import ContextVar

from core.config import get_settings

# Context variables for request-scoped data
_request_id_ctx: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
_tenant_schema_ctx: ContextVar[Optional[str]] = ContextVar('tenant_schema', default=None)
_user_id_ctx: ContextVar[Optional[str]] = ContextVar('user_id', default=None)
_route_ctx: ContextVar[Optional[str]] = ContextVar('route', default=None)
_method_ctx: ContextVar[Optional[str]] = ContextVar('method', default=None)
# S3-A Part 3: Span ID for enhanced traceability
_span_id_ctx: ContextVar[Optional[str]] = ContextVar('span_id', default=None)

# S2.5 Batch B: Sensitive field patterns for log sanitization
SENSITIVE_FIELD_PATTERNS = {
    'password', 'passwd', 'pwd',
    'token', 'access_token', 'refresh_token', 'api_key', 'apikey',
    'secret', 'secret_key', 'client_secret',
    'authorization', 'auth',
    'credit_card', 'card_number', 'cvv', 'ccv',
    'ssn', 'social_security',
    'private_key', 'priv_key'
}

MASK_VALUE = "******"


def sanitize_log_data(data: Any) -> Any:
    """
    S2.5 Batch B: Recursively sanitize sensitive data in log entries.
    
    Masks values for keys matching sensitive patterns.
    Handles nested dictionaries and lists.
    """
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Check if key matches sensitive pattern (case-insensitive)
            key_lower = key.lower()
            if any(pattern in key_lower for pattern in SENSITIVE_FIELD_PATTERNS):
                sanitized[key] = MASK_VALUE
            else:
                sanitized[key] = sanitize_log_data(value)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_log_data(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(sanitize_log_data(item) for item in data)
    else:
        return data


class StructuredJsonFormatter(logging.Formatter):
    """
    S2-2: JSON formatter that automatically includes context variables.
    
    Mandatory fields in every log entry:
    - timestamp: ISO 8601 format
    - level: Log level (INFO, ERROR, etc.)
    - service: Application name
    - env: Environment (production/test)
    - request_id: Unique request identifier
    - tenant_schema: Current tenant schema
    - user_id: Authenticated user ID (if available)
    - route: API route
    - method: HTTP method
    - message: Log message
    """
    
    def __init__(self):
        super().__init__()
        self.settings = get_settings()
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON with context."""
        # Base log entry with mandatory fields
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service": self.settings.APP_NAME,
            "env": self.settings.MPANGO_ENV,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add context variables (S2-2 requirement)
        request_id = _request_id_ctx.get()
        if request_id:
            log_entry["request_id"] = request_id
        
        tenant_schema = _tenant_schema_ctx.get()
        if tenant_schema:
            log_entry["tenant_schema"] = tenant_schema
        
        user_id = _user_id_ctx.get()
        if user_id:
            log_entry["user_id"] = user_id
        
        route = _route_ctx.get()
        if route:
            log_entry["route"] = route
        
        method = _method_ctx.get()
        if method:
            log_entry["method"] = method
        
        # S3-A Part 3: Add span_id for SQL query correlation
        span_id = _span_id_ctx.get()
        if span_id:
            log_entry["span_id"] = span_id
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info) if record.exc_info else None
            }
        
        # Add extra fields from record (S2.5 Batch B: sanitize sensitive data)
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName', 
                          'levelname', 'levelno', 'lineno', 'module', 'msecs', 
                          'message', 'pathname', 'process', 'processName', 
                          'relativeCreated', 'thread', 'threadName', 'exc_info', 
                          'exc_text', 'stack_info']:
                # Check if key matches sensitive pattern (case-insensitive)
                key_lower = key.lower()
                if any(pattern in key_lower for pattern in SENSITIVE_FIELD_PATTERNS):
                    log_entry[key] = MASK_VALUE
                else:
                    log_entry[key] = sanitize_log_data(value)
        
        return json.dumps(log_entry)


def setup_structured_logging(level: str = "INFO") -> None:
    """
    S2-2: Setup structured JSON logging for the application.
    
    Replaces standard logging with structured JSON format.
    All logs automatically include context variables.
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler with structured JSON formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(StructuredJsonFormatter())
    
    root_logger.addHandler(console_handler)
    
    # Log startup message
    root_logger.info("Structured logging initialized", extra={
        "component": "logging",
        "formatter": "StructuredJsonFormatter"
    })


def set_request_context(
    request_id: Optional[str] = None,
    tenant_schema: Optional[str] = None,
    user_id: Optional[str] = None,
    route: Optional[str] = None,
    method: Optional[str] = None,
    span_id: Optional[str] = None  # S3-A Part 3
) -> None:
    """
    S2-2: Set request context for structured logging.
    S3-A Part 3: Added span_id for SQL query correlation.
    
    Called by middleware to inject context into all logs for this request.
    """
    if request_id is not None:
        _request_id_ctx.set(request_id)
    if tenant_schema is not None:
        _tenant_schema_ctx.set(tenant_schema)
    if user_id is not None:
        _user_id_ctx.set(user_id)
    if route is not None:
        _route_ctx.set(route)
    if method is not None:
        _method_ctx.set(method)
    if span_id is not None:
        _span_id_ctx.set(span_id)


def clear_request_context() -> None:
    """
    S2-2: Clear request context after request completes.
    S3-A Part 3: Also clear span_id.
    
    Called by middleware in finally block.
    """
    _request_id_ctx.set(None)
    _tenant_schema_ctx.set(None)
    _user_id_ctx.set(None)
    _route_ctx.set(None)
    _method_ctx.set(None)
    _span_id_ctx.set(None)


def get_logger(name: str) -> logging.Logger:
    """
    S2-2: Get a logger that automatically includes context.
    
    Usage:
        logger = get_logger(__name__)
        logger.info("User logged in")  # Automatically includes request_id, tenant, etc.
    """
    return logging.getLogger(name)
