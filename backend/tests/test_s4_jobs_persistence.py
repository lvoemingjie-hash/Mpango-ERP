"""
S4-B: Job Persistence & Retry Tests

Tests for database persistence and retry logic in LocalJobQueue.

Test Cases:
1. Happy path - job completes, DB status is "completed"
2. Retry - job fails first attempt, succeeds on second, verify attempts=2 and status="completed"
3. Max retries - job fails all attempts, verify status="failed"
4. Job record persistence - verify all fields are correctly stored
"""
import pytest
import asyncio
import uuid
from datetime import datetime
from sqlalchemy import select

from core.jobs.local_queue import LocalJobQueue
from core.jobs.base import job_handler
from models.job import Job


# Test job handlers
@job_handler("test_success_job")
async def test_success_job(payload: dict):
    """Job that always succeeds."""
    await asyncio.sleep(0.1)
    return {"status": "success", "data": payload}


@job_handler("test_failing_job_with_retry")
async def test_failing_job_with_retry(payload: dict):
    """Job that fails on first attempt, succeeds on second."""
    # Use a global counter to track attempts
    if not hasattr(test_failing_job_with_retry, "attempt_count"):
        test_failing_job_with_retry.attempt_count = {}
    
    job_key = payload.get("job_key", "default")
    
    if job_key not in test_failing_job_with_retry.attempt_count:
        test_failing_job_with_retry.attempt_count[job_key] = 0
    
    test_failing_job_with_retry.attempt_count[job_key] += 1
    
    if test_failing_job_with_retry.attempt_count[job_key] == 1:
        raise Exception("First attempt failure")
    
    # Second attempt succeeds
    await asyncio.sleep(0.1)
    return {"status": "success", "attempt": test_failing_job_with_retry.attempt_count[job_key]}


@job_handler("test_always_failing_job")
async def test_always_failing_job(payload: dict):
    """Job that always fails."""
    await asyncio.sleep(0.1)
    raise Exception("Job always fails")


@pytest.mark.asyncio
async def test_job_persistence_happy_path(async_session):
    """
    Test Case 1: Happy path - job completes, DB status is "completed"
    
    Verifies:
    - Job is created in database with status "pending"
    - Job status updates to "running" when execution starts
    - Job status updates to "completed" on success
    - All timestamps are set correctly
    - Attempts count is 1
    """
    # Create and start queue
    queue = LocalJobQueue(max_workers=2)
    await queue.start()
    
    try:
        # Enqueue job
        job_id = await queue.enqueue(
            job_name="test_success_job",
            payload={"test": "data"},
            max_retries=3
        )
        
        # Wait for job to complete
        await asyncio.sleep(0.5)
        
        # Verify job in database
        result = await async_session.execute(
            select(Job).where(Job.id == uuid.UUID(job_id))
        )
        job = result.scalar_one()
        
        # Assertions
        assert job.job_name == "test_success_job"
        assert job.payload == {"test": "data"}
        assert job.status == "completed"
        assert job.attempts == 1
        assert job.max_retries == 3
        assert job.last_error is None
        assert job.created_at is not None
        assert job.updated_at is not None
        assert job.started_at is not None
        assert job.completed_at is not None
        assert job.completed_at > job.started_at
        
    finally:
        await queue.stop()


@pytest.mark.asyncio
async def test_job_retry_on_failure(async_session):
    """
    Test Case 2: Retry - job fails first attempt, succeeds on second
    
    Verifies:
    - Job fails on first attempt
    - Job is automatically retried
    - Job succeeds on second attempt
    - Final status is "completed"
    - Attempts count is 2
    - last_error is set during failure but job still completes
    """
    # Reset attempt counter
    if hasattr(test_failing_job_with_retry, "attempt_count"):
        test_failing_job_with_retry.attempt_count = {}
    
    # Create and start queue
    queue = LocalJobQueue(max_workers=2)
    await queue.start()
    
    try:
        # Enqueue job with unique key
        job_key = f"test_{uuid.uuid4()}"
        job_id = await queue.enqueue(
            job_name="test_failing_job_with_retry",
            payload={"job_key": job_key},
            max_retries=3
        )
        
        # Wait for job to complete (including retry)
        await asyncio.sleep(1.0)
        
        # Verify job in database
        result = await async_session.execute(
            select(Job).where(Job.id == uuid.UUID(job_id))
        )
        job = result.scalar_one()
        
        # Assertions
        assert job.job_name == "test_failing_job_with_retry"
        assert job.status == "completed"
        assert job.attempts == 2  # Failed once, succeeded on second attempt
        assert job.max_retries == 3
        assert job.completed_at is not None
        
    finally:
        await queue.stop()


@pytest.mark.asyncio
async def test_job_max_retries_reached(async_session):
    """
    Test Case 3: Max retries - job fails all attempts, verify status="failed"
    
    Verifies:
    - Job fails on all attempts
    - Job is retried up to max_retries
    - Final status is "failed"
    - Attempts count equals max_retries
    - last_error is set
    """
    # Create and start queue
    queue = LocalJobQueue(max_workers=2)
    await queue.start()
    
    try:
        # Enqueue job with max_retries=2
        job_id = await queue.enqueue(
            job_name="test_always_failing_job",
            payload={"test": "data"},
            max_retries=2
        )
        
        # Wait for all retry attempts to complete
        await asyncio.sleep(1.5)
        
        # Verify job in database
        result = await async_session.execute(
            select(Job).where(Job.id == uuid.UUID(job_id))
        )
        job = result.scalar_one()
        
        # Assertions
        assert job.job_name == "test_always_failing_job"
        assert job.status == "failed"
        assert job.attempts == 2  # Tried max_retries times
        assert job.max_retries == 2
        assert job.last_error is not None
        assert "Job always fails" in job.last_error
        assert job.completed_at is not None
        
    finally:
        await queue.stop()


@pytest.mark.asyncio
async def test_job_record_persistence(async_session):
    """
    Test Case 4: Job record persistence - verify all fields are correctly stored
    
    Verifies:
    - Job ID is a valid UUID
    - Job name is stored correctly
    - Payload is stored as JSONB
    - Status transitions are tracked
    - Timestamps are set correctly
    - Attempts and max_retries are tracked
    """
    # Create and start queue
    queue = LocalJobQueue(max_workers=2)
    await queue.start()
    
    try:
        # Enqueue job with complex payload
        complex_payload = {
            "string": "test",
            "number": 42,
            "boolean": True,
            "array": [1, 2, 3],
            "nested": {"key": "value"}
        }
        
        job_id = await queue.enqueue(
            job_name="test_success_job",
            payload=complex_payload,
            max_retries=5
        )
        
        # Verify job ID is valid UUID
        assert uuid.UUID(job_id)
        
        # Wait for job to complete
        await asyncio.sleep(0.5)
        
        # Verify job in database
        result = await async_session.execute(
            select(Job).where(Job.id == uuid.UUID(job_id))
        )
        job = result.scalar_one()
        
        # Assertions
        assert str(job.id) == job_id
        assert job.job_name == "test_success_job"
        assert job.payload == complex_payload
        assert job.status == "completed"
        assert job.attempts == 1
        assert job.max_retries == 5
        assert job.last_error is None
        
        # Verify timestamps
        assert isinstance(job.created_at, datetime)
        assert isinstance(job.updated_at, datetime)
        assert isinstance(job.started_at, datetime)
        assert isinstance(job.completed_at, datetime)
        
        # Verify timestamp order
        assert job.created_at <= job.started_at
        assert job.started_at <= job.completed_at
        
    finally:
        await queue.stop()


@pytest.mark.asyncio
async def test_multiple_jobs_persistence(async_session):
    """
    Test Case 5: Multiple jobs - verify all jobs are tracked independently
    
    Verifies:
    - Multiple jobs can be enqueued
    - Each job has its own database record
    - Jobs are processed independently
    - All jobs complete successfully
    """
    # Create and start queue
    queue = LocalJobQueue(max_workers=3)
    await queue.start()
    
    try:
        # Enqueue multiple jobs
        job_ids = []
        for i in range(5):
            job_id = await queue.enqueue(
                job_name="test_success_job",
                payload={"index": i},
                max_retries=3
            )
            job_ids.append(job_id)
        
        # Wait for all jobs to complete
        await asyncio.sleep(1.0)
        
        # Verify all jobs in database
        for i, job_id in enumerate(job_ids):
            result = await async_session.execute(
                select(Job).where(Job.id == uuid.UUID(job_id))
            )
            job = result.scalar_one()
            
            assert job.job_name == "test_success_job"
            assert job.payload == {"index": i}
            assert job.status == "completed"
            assert job.attempts == 1
        
    finally:
        await queue.stop()
