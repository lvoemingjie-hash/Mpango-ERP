"""
S4-B: Local In-Process Job Queue with Database Persistence

Implements JobQueue using asyncio.Queue for local background processing.
Now includes database persistence for job tracking and retry capability.

Philosophy: "Jobs are not fire-and-forget, they are tracked and retryable."

Features:
- In-process async job execution
- Database persistence for auditability
- Automatic retry on failure (configurable max_retries)
- Configurable concurrency limit (default: 5)
- Graceful shutdown with job draining
- Job status tracking
- Prometheus metrics
"""
import asyncio
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum

from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.jobs.base import JobQueue, get_job_handler
from core.structured_logging import get_logger
from models.job import Job
from database.session import AsyncSessionLocal

logger = get_logger(__name__)


class JobStatus(str, Enum):
    """Job execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# S4-A: Prometheus metrics for job queue
jobs_enqueued_total = Counter(
    'jobs_enqueued_total',
    'Total jobs enqueued',
    ['job_name']
)

jobs_completed_total = Counter(
    'jobs_completed_total',
    'Total jobs completed successfully',
    ['job_name']
)

jobs_failed_total = Counter(
    'jobs_failed_total',
    'Total jobs failed',
    ['job_name']
)

job_execution_duration_seconds = Histogram(
    'job_execution_duration_seconds',
    'Job execution duration in seconds',
    ['job_name'],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0)
)

jobs_pending_gauge = Gauge(
    'jobs_pending',
    'Number of jobs pending in queue'
)

jobs_running_gauge = Gauge(
    'jobs_running',
    'Number of jobs currently running'
)


class LocalJobQueue(JobQueue):
    """
    Local in-process job queue implementation with database persistence.
    
    Uses asyncio.Queue with background worker tasks to process jobs.
    All jobs are persisted to database for auditability and retry capability.
    
    Suitable for development and low-volume production workloads.
    For high-volume production, consider migrating to Celery/Redis.
    """
    
    def __init__(self, max_workers: int = 5):
        """
        Initialize local job queue.
        
        Args:
            max_workers: Maximum number of concurrent job executions
        """
        self.max_workers = max_workers
        self.queue: asyncio.Queue = asyncio.Queue()
        self.semaphore = asyncio.Semaphore(max_workers)
        self.workers: list[asyncio.Task] = []
        self.running = False
        
        # Job tracking (in-memory for quick access)
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.stats = {
            "enqueued": 0,
            "completed": 0,
            "failed": 0,
            "pending": 0,
            "running": 0
        }
        
        logger.info(
            f"LocalJobQueue initialized with {max_workers} workers",
            extra={"max_workers": max_workers}
        )
    
    async def enqueue(
        self,
        job_name: str,
        payload: Dict[str, Any],
        delay_seconds: int = 0,
        max_retries: int = 3
    ) -> str:
        """
        Enqueue a job for background execution with database persistence.
        
        Args:
            job_name: Name of the job to execute
            payload: Job parameters
            delay_seconds: Delay before execution (0 = immediate)
            max_retries: Maximum number of retry attempts (default: 3)
        
        Returns:
            job_id: Unique identifier for the job (UUID from database)
        """
        # Validate job is registered
        get_job_handler(job_name)  # Raises ValueError if not found
        
        # S4-B: Create job record in database
        async with AsyncSessionLocal() as session:
            # Set tenant context to public schema for sys_jobs table
            session.info["tenant_schema"] = "public"
            
            job = Job(
                job_name=job_name,
                payload=payload,
                status="pending",
                attempts=0,
                max_retries=max_retries
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            job_id = str(job.id)
        
        # Create in-memory job record for queue processing
        job_record = {
            "job_id": job_id,
            "job_name": job_name,
            "payload": payload,
            "delay_seconds": delay_seconds,
            "max_retries": max_retries,
            "status": JobStatus.PENDING,
            "enqueued_at": datetime.utcnow(),
            "started_at": None,
            "completed_at": None,
            "error": None
        }
        
        self.jobs[job_id] = job_record
        
        # Add to queue
        await self.queue.put(job_record)
        
        # Update metrics
        jobs_enqueued_total.labels(job_name=job_name).inc()
        self.stats["enqueued"] += 1
        self.stats["pending"] += 1
        jobs_pending_gauge.set(self.stats["pending"])
        
        logger.info(
            f"Job enqueued: {job_name}",
            extra={
                "job_id": job_id,
                "job_name": job_name,
                "delay_seconds": delay_seconds,
                "max_retries": max_retries
            }
        )
        
        return job_id
    
    async def _worker(self, worker_id: int):
        """
        Background worker that processes jobs from the queue.
        
        Args:
            worker_id: Worker identifier for logging
        """
        logger.info(f"Worker {worker_id} started")
        
        while self.running:
            try:
                # Get job from queue (with timeout to check running flag)
                try:
                    job_record = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process job with semaphore (limit concurrency)
                async with self.semaphore:
                    await self._execute_job(job_record)
                
                self.queue.task_done()
                
            except Exception as e:
                logger.error(
                    f"Worker {worker_id} error: {str(e)}",
                    extra={"worker_id": worker_id, "error": str(e)}
                )
        
        logger.info(f"Worker {worker_id} stopped")
    
    async def _execute_job(self, job_record: Dict[str, Any]):
        """
        Execute a single job with database persistence and retry logic.
        
        Args:
            job_record: Job record with job_name, payload, etc.
        """
        job_id = job_record["job_id"]
        job_name = job_record["job_name"]
        payload = job_record["payload"]
        delay_seconds = job_record["delay_seconds"]
        max_retries = job_record["max_retries"]
        
        # Update status to running
        job_record["status"] = JobStatus.RUNNING
        job_record["started_at"] = datetime.utcnow()
        self.stats["pending"] -= 1
        self.stats["running"] += 1
        jobs_pending_gauge.set(self.stats["pending"])
        jobs_running_gauge.set(self.stats["running"])
        
        # S4-B: Update database status to running
        async with AsyncSessionLocal() as session:
            session.info["tenant_schema"] = "public"
            await session.execute(
                update(Job)
                .where(Job.id == uuid.UUID(job_id))
                .values(
                    status="running",
                    started_at=datetime.utcnow(),
                    attempts=Job.attempts + 1
                )
            )
            await session.commit()
        
        logger.info(
            f"Job started: {job_name}",
            extra={"job_id": job_id, "job_name": job_name}
        )
        
        # Apply delay if specified
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
        
        # Execute job
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Get handler and execute
            handler = get_job_handler(job_name)
            await handler(payload)
            
            # Success
            duration = asyncio.get_event_loop().time() - start_time
            job_record["status"] = JobStatus.COMPLETED
            job_record["completed_at"] = datetime.utcnow()
            
            # S4-B: Update database status to completed
            async with AsyncSessionLocal() as session:
                session.info["tenant_schema"] = "public"
                await session.execute(
                    update(Job)
                    .where(Job.id == uuid.UUID(job_id))
                    .values(
                        status="completed",
                        completed_at=datetime.utcnow()
                    )
                )
                await session.commit()
            
            # Update metrics
            jobs_completed_total.labels(job_name=job_name).inc()
            job_execution_duration_seconds.labels(job_name=job_name).observe(duration)
            self.stats["completed"] += 1
            self.stats["running"] -= 1
            jobs_running_gauge.set(self.stats["running"])
            
            logger.info(
                f"Job completed: {job_name}",
                extra={
                    "job_id": job_id,
                    "job_name": job_name,
                    "duration_seconds": duration
                }
            )
            
        except Exception as e:
            # Failure
            duration = asyncio.get_event_loop().time() - start_time
            job_record["status"] = JobStatus.FAILED
            job_record["completed_at"] = datetime.utcnow()
            job_record["error"] = str(e)
            
            # S4-B: Check if we should retry
            async with AsyncSessionLocal() as session:
                session.info["tenant_schema"] = "public"
                
                # Get current attempts
                result = await session.execute(
                    select(Job).where(Job.id == uuid.UUID(job_id))
                )
                job_db = result.scalar_one()
                current_attempts = job_db.attempts
                
                should_retry = current_attempts < max_retries
                
                if should_retry:
                    # Update status to pending for retry
                    await session.execute(
                        update(Job)
                        .where(Job.id == uuid.UUID(job_id))
                        .values(
                            status="pending",
                            last_error=str(e),
                            updated_at=datetime.utcnow()
                        )
                    )
                    await session.commit()
                    
                    # Re-enqueue for retry
                    job_record["status"] = JobStatus.PENDING
                    await self.queue.put(job_record)
                    self.stats["pending"] += 1
                    jobs_pending_gauge.set(self.stats["pending"])
                    
                    logger.warning(
                        f"Job failed, retrying: {job_name} (attempt {current_attempts}/{max_retries})",
                        extra={
                            "job_id": job_id,
                            "job_name": job_name,
                            "error": str(e),
                            "attempt": current_attempts,
                            "max_retries": max_retries
                        }
                    )
                else:
                    # Max retries reached, mark as failed
                    await session.execute(
                        update(Job)
                        .where(Job.id == uuid.UUID(job_id))
                        .values(
                            status="failed",
                            last_error=str(e),
                            completed_at=datetime.utcnow()
                        )
                    )
                    await session.commit()
                    
                    logger.error(
                        f"Job failed permanently: {job_name} (max retries reached)",
                        extra={
                            "job_id": job_id,
                            "job_name": job_name,
                            "error": str(e),
                            "attempts": current_attempts,
                            "max_retries": max_retries
                        }
                    )
            
            # Update metrics
            jobs_failed_total.labels(job_name=job_name).inc()
            job_execution_duration_seconds.labels(job_name=job_name).observe(duration)
            self.stats["failed"] += 1
            self.stats["running"] -= 1
            jobs_running_gauge.set(self.stats["running"])
    
    async def start(self):
        """Start background workers."""
        if self.running:
            logger.warning("Job queue already running")
            return
        
        self.running = True
        
        # Start worker tasks
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(i))
            self.workers.append(worker)
        
        logger.info(
            f"Job queue started with {self.max_workers} workers",
            extra={"max_workers": self.max_workers}
        )
    
    async def stop(self):
        """Stop workers gracefully and drain pending jobs."""
        if not self.running:
            logger.warning("Job queue not running")
            return
        
        logger.info("Stopping job queue...")
        
        # Stop accepting new jobs
        self.running = False
        
        # Wait for queue to drain (with timeout)
        try:
            await asyncio.wait_for(self.queue.join(), timeout=30.0)
            logger.info("All pending jobs completed")
        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout waiting for jobs to complete, {self.queue.qsize()} jobs remaining"
            )
        
        # Cancel workers
        for worker in self.workers:
            worker.cancel()
        
        # Wait for workers to finish
        await asyncio.gather(*self.workers, return_exceptions=True)
        
        self.workers.clear()
        
        logger.info("Job queue stopped")
    
    async def get_status(self) -> Dict[str, Any]:
        """Get queue status."""
        return {
            "running": self.running,
            "max_workers": self.max_workers,
            "queue_size": self.queue.qsize(),
            "stats": self.stats.copy(),
            "total_jobs": len(self.jobs)
        }
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job details by ID.
        
        Args:
            job_id: Job identifier
        
        Returns:
            Job record or None if not found
        """
        return self.jobs.get(job_id)
