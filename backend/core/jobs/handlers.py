"""
S4-A: Job Handlers

Register job handlers for background tasks.

Philosophy: "Abstract the Job concept first, implement locally second."
"""
from core.jobs.base import job_handler
from core.structured_logging import get_logger

logger = get_logger(__name__)


@job_handler("test_email")
async def test_email_job(payload: dict):
    """
    Test job: Simulate sending an email.
    
    Args:
        payload: Job parameters with 'email' field
    """
    email = payload.get("email", "unknown@example.com")
    
    logger.info(
        f"Sending email to {email}...",
        extra={"email": email, "job": "test_email"}
    )
    
    # Simulate email sending delay
    import asyncio
    await asyncio.sleep(2)
    
    logger.info(
        f"Email sent to {email}",
        extra={"email": email, "job": "test_email"}
    )


@job_handler("test_slow_job")
async def test_slow_job(payload: dict):
    """
    Test job: Simulate a slow background task.
    
    Args:
        payload: Job parameters with 'duration' field
    """
    duration = payload.get("duration", 5)
    task_name = payload.get("task_name", "slow_task")
    
    logger.info(
        f"Starting slow task: {task_name} (duration: {duration}s)",
        extra={"task_name": task_name, "duration": duration}
    )
    
    import asyncio
    await asyncio.sleep(duration)
    
    logger.info(
        f"Completed slow task: {task_name}",
        extra={"task_name": task_name, "duration": duration}
    )


@job_handler("test_failing_job")
async def test_failing_job(payload: dict):
    """
    Test job: Simulate a failing job.
    
    Args:
        payload: Job parameters
    """
    error_message = payload.get("error_message", "Simulated failure")
    
    logger.info(
        f"Starting failing job...",
        extra={"error_message": error_message}
    )
    
    # Simulate some work before failing
    import asyncio
    await asyncio.sleep(1)
    
    # Raise error
    raise RuntimeError(error_message)
