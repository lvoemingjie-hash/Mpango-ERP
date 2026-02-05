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
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info) if record.exc_info else None
            }
        
        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName', 
                          'levelname', 'levelno', 'lineno', 'module', 'msecs', 
                          'message', 'pathname', 'process', 'processName', 
                          'relativeCreated', 'thread', 'threadName', 'exc_info', 
                          'exc_text', 'stack_info']:
                log_entry[key] = value
        
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
    method: Optional[str] = None
) -> None:
    """
    S2-2: Set request context for structured logging.
    
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


def clear_request_context() -> None:
    """
    S2-2: Clear request context after request completes.
    
    Called by middleware in finally block.
    """
    _request_id_ctx.set(None)
    _tenant_schema_ctx.set(None)
    _user_id_ctx.set(None)
    _route_ctx.set(None)
    _method_ctx.set(None)


def get_logger(name: str) -> logging.Logger:
    """
    S2-2: Get a logger that automatically includes context.
    
    Usage:
        logger = get_logger(__name__)
        logger.info("User logged in")  # Automatically includes request_id, tenant, etc.
    """
    return logging.getLogger(name)
