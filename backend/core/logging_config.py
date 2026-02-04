import logging
import json
from typing import Any, Dict

try:
    from pythonjsonlogger import jsonlogger  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    class _FallbackJsonLogger:  # noqa: N801
        JsonFormatter = logging.Formatter

    jsonlogger = _FallbackJsonLogger()


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter that includes request_id and tenant_id if available."""

    def format(self, record: logging.LogRecord) -> str:
        # Add default fields
        if not hasattr(record, 'request_id'):
            record.request_id = 'N/A'
        if not hasattr(record, 'tenant_id'):
            record.tenant_id = 'N/A'

        return super().format(record)


def setup_logging(level: str = 'INFO') -> None:
    """Setup JSON structured logging for production."""

    # Create logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler with JSON formatter
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = CustomJsonFormatter(
        fmt='%(asctime)s %(name)s %(levelname)s %(message)s %(request_id)s %(tenant_id)s'
    )
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)


def get_request_logger(request_id: str = 'N/A', tenant_id: str = 'N/A') -> logging.LoggerAdapter:
    """Get a logger adapter with request context."""
    extra = {'request_id': request_id, 'tenant_id': tenant_id}
    return logging.LoggerAdapter(logging.getLogger(), extra)
