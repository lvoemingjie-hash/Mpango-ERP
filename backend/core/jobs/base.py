"""
S4-A: Job Queue Abstract Base Class

Defines the interface for job queue implementations.

Philosophy: "Abstract the Job concept first, implement locally second."
"""
from abc import ABC, abstractmethod
from typing import Dict, Callable, Any, Awaitable
import functools

from core.structured_logging import get_logger

logger = get_logger(__name__)


# Global job registry: job_name -> handler_function
_job_registry: Dict[str, Callable[[Dict[str, Any]], Awaitable[None]]] = {}


class JobQueue(ABC):
    """
    Abstract base class for job queue implementations.
    
    Defines the interface that all job queue implementations must follow.
    This allows switching between local (in-process) and distributed (Celery/Redis)
    implementations without changing application code.
    """
    
    @abstractmethod
    async def enqueue(
        self,
        job_name: str,
        payload: Dict[str, Any],
        delay_seconds: int = 0
    ) -> str:
        """
        Enqueue a job for background execution.
        
        Args:
            job_name: Name of the job to execute (must be registered)
            payload: Job parameters as a dictionary
            delay_seconds: Delay before execution (0 = immediate)
        
        Returns:
            job_id: Unique identifier for the enqueued job
        
        Raises:
            ValueError: If job_name is not registered
        """
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """
        Start the job queue worker.
        
        Called during application startup to initialize background workers.
        """
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the job queue worker gracefully.
        
        Called during application shutdown to drain pending jobs.
        """
        pass
    
    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """
        Get queue status information.
        
        Returns:
            Dict with queue statistics (pending, completed, failed, etc.)
        """
        pass


def job_handler(job_name: str):
    """
    Decorator to register a job handler function.
    
    Usage:
        @job_handler("send_email")
        async def send_email_job(payload: dict):
            email = payload["email"]
            # Send email logic
            logger.info(f"Email sent to {email}")
    
    Args:
        job_name: Unique name for this job type
    
    Returns:
        Decorator function
    """
    def decorator(func: Callable[[Dict[str, Any]], Awaitable[None]]):
        # Register the handler
        if job_name in _job_registry:
            logger.warning(
                f"Job handler '{job_name}' already registered, overwriting",
                extra={"job_name": job_name}
            )
        
        _job_registry[job_name] = func
        
        logger.info(
            f"Registered job handler: {job_name}",
            extra={"job_name": job_name, "handler": func.__name__}
        )
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator


def get_job_registry() -> Dict[str, Callable[[Dict[str, Any]], Awaitable[None]]]:
    """
    Get the global job registry.
    
    Returns:
        Dictionary mapping job names to handler functions
    """
    return _job_registry


def get_job_handler(job_name: str) -> Callable[[Dict[str, Any]], Awaitable[None]]:
    """
    Get a registered job handler by name.
    
    Args:
        job_name: Name of the job
    
    Returns:
        Handler function
    
    Raises:
        ValueError: If job_name is not registered
    """
    if job_name not in _job_registry:
        raise ValueError(
            f"Job '{job_name}' not registered. "
            f"Available jobs: {list(_job_registry.keys())}"
        )
    
    return _job_registry[job_name]
