"""
S4-A: Job Queue Test Endpoints

Test endpoints for job queue functionality.

Philosophy: "Abstract the Job concept first, implement locally second."
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.dependencies_jobs import get_job_queue
from core.jobs import JobQueue
from schemas.common import DataResponse, MessageResponse

router = APIRouter()


class EnqueueJobRequest(BaseModel):
    """Request to enqueue a job."""
    email: str = Field(..., description="Email address")
    delay_seconds: int = Field(0, ge=0, le=300, description="Delay before execution (0-300 seconds)")


class EnqueueJobResponse(BaseModel):
    """Response from enqueuing a job."""
    job_id: str = Field(..., description="Unique job identifier")
    job_name: str = Field(..., description="Job name")
    status: str = Field(..., description="Job status")
    message: str = Field(..., description="Success message")


class SlowJobRequest(BaseModel):
    """Request to enqueue a slow job."""
    task_name: str = Field(..., description="Task name")
    duration: int = Field(5, ge=1, le=60, description="Duration in seconds (1-60)")


class QueueStatusResponse(BaseModel):
    """Job queue status."""
    running: bool
    max_workers: int
    queue_size: int
    stats: dict
    total_jobs: int


@router.post("/email", response_model=DataResponse[EnqueueJobResponse], status_code=status.HTTP_202_ACCEPTED)
async def enqueue_test_email(
    request: EnqueueJobRequest,
    queue: JobQueue = Depends(get_job_queue)
):
    """
    S4-A: Enqueue a test email job.
    
    This endpoint demonstrates async job enqueueing:
    1. Job is enqueued immediately
    2. Returns 202 Accepted with job_id
    3. Job executes in background
    4. API response is not blocked
    
    Args:
        request: Job parameters
        queue: Job queue instance
    
    Returns:
        202 Accepted with job_id
    """
    # Enqueue job
    job_id = await queue.enqueue(
        job_name="test_email",
        payload={"email": request.email},
        delay_seconds=request.delay_seconds
    )
    
    return DataResponse(
        success=True,
        data=EnqueueJobResponse(
            job_id=job_id,
            job_name="test_email",
            status="enqueued",
            message=f"Email job enqueued for {request.email}"
        ),
        timestamp=datetime.utcnow()
    )


@router.post("/slow-job", response_model=DataResponse[EnqueueJobResponse], status_code=status.HTTP_202_ACCEPTED)
async def enqueue_slow_job(
    request: SlowJobRequest,
    queue: JobQueue = Depends(get_job_queue)
):
    """
    S4-A: Enqueue a slow background job.
    
    Demonstrates that slow jobs don't block API responses.
    
    Args:
        request: Job parameters
        queue: Job queue instance
    
    Returns:
        202 Accepted with job_id
    """
    job_id = await queue.enqueue(
        job_name="test_slow_job",
        payload={
            "task_name": request.task_name,
            "duration": request.duration
        }
    )
    
    return DataResponse(
        success=True,
        data=EnqueueJobResponse(
            job_id=job_id,
            job_name="test_slow_job",
            status="enqueued",
            message=f"Slow job '{request.task_name}' enqueued (duration: {request.duration}s)"
        ),
        timestamp=datetime.utcnow()
    )


@router.post("/failing-job", response_model=DataResponse[EnqueueJobResponse], status_code=status.HTTP_202_ACCEPTED)
async def enqueue_failing_job(
    error_message: str = "Simulated failure",
    queue: JobQueue = Depends(get_job_queue)
):
    """
    S4-A: Enqueue a job that will fail.
    
    Demonstrates error handling in background jobs.
    
    Args:
        error_message: Error message to simulate
        queue: Job queue instance
    
    Returns:
        202 Accepted with job_id
    """
    job_id = await queue.enqueue(
        job_name="test_failing_job",
        payload={"error_message": error_message}
    )
    
    return DataResponse(
        success=True,
        data=EnqueueJobResponse(
            job_id=job_id,
            job_name="test_failing_job",
            status="enqueued",
            message="Failing job enqueued (will fail after 1 second)"
        ),
        timestamp=datetime.utcnow()
    )


@router.get("/status", response_model=DataResponse[QueueStatusResponse], status_code=status.HTTP_200_OK)
async def get_queue_status(queue: JobQueue = Depends(get_job_queue)):
    """
    S4-A: Get job queue status.
    
    Returns queue statistics and metrics.
    
    Args:
        queue: Job queue instance
    
    Returns:
        Queue status information
    """
    status_data = await queue.get_status()
    
    return DataResponse(
        success=True,
        data=QueueStatusResponse(**status_data),
        timestamp=datetime.utcnow()
    )


@router.get("/job/{job_id}", response_model=DataResponse[dict], status_code=status.HTTP_200_OK)
async def get_job_status(
    job_id: str,
    queue: JobQueue = Depends(get_job_queue)
):
    """
    S4-A: Get job status by ID.
    
    Args:
        job_id: Job identifier
        queue: Job queue instance
    
    Returns:
        Job details
    
    Raises:
        404: If job not found
    """
    from core.jobs.local_queue import LocalJobQueue
    
    if not isinstance(queue, LocalJobQueue):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Job status lookup not supported for this queue implementation"
        )
    
    job = queue.get_job(job_id)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    
    # Convert datetime objects to ISO format
    job_data = job.copy()
    for key in ["enqueued_at", "started_at", "completed_at"]:
        if job_data.get(key):
            job_data[key] = job_data[key].isoformat()
    
    return DataResponse(
        success=True,
        data=job_data,
        timestamp=datetime.utcnow()
    )
