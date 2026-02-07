"""
S4-A: Job Queue Dependency Injection

Provides dependency injection for job queue access.
"""
from core.jobs import JobQueue


def get_job_queue() -> JobQueue:
    """
    Get the global job queue instance.
    
    Returns:
        JobQueue instance
    
    Usage:
        @router.post("/endpoint")
        async def endpoint(queue: JobQueue = Depends(get_job_queue)):
            await queue.enqueue("job_name", {"param": "value"})
    """
    from main import _job_queue
    
    if _job_queue is None:
        raise RuntimeError("Job queue not initialized")
    
    return _job_queue
