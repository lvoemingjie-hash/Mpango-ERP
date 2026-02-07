"""
S4-A: Job Queue System

Local async job queue implementation for background tasks.

Philosophy: "Abstract the Job concept first, implement locally second."
"""
from core.jobs.base import JobQueue, job_handler, get_job_registry
from core.jobs.local_queue import LocalJobQueue

__all__ = [
    "JobQueue",
    "job_handler",
    "get_job_registry",
    "LocalJobQueue",
]
