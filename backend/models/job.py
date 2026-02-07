"""
S4-B: Job Model

Database model for persistent job tracking.

Table: public.sys_jobs (system-level, cross-tenant)
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID

from models.base import Base


class Job(Base):
    """
    Job model for persistent job tracking.
    
    Stores job metadata for auditability and retry capability.
    Lives in public schema as jobs may cross tenants.
    """
    __tablename__ = "sys_jobs"
    __table_args__ = {"schema": "public"}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_name = Column(String(255), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(
        String(50),
        nullable=False,
        default="pending",
        index=True
    )  # pending, running, completed, failed
    attempts = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    last_error = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Job(id={self.id}, job_name={self.job_name}, status={self.status}, attempts={self.attempts})>"
    
    def to_dict(self):
        """Convert job to dictionary."""
        return {
            "id": str(self.id),
            "job_name": self.job_name,
            "payload": self.payload,
            "status": self.status,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "last_error": self.last_error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
