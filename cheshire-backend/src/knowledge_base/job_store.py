from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Optional
from uuid import uuid4


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE    = "done"
    FAILED  = "failed"


@dataclass
class Job:
    key:        str              # == session_id
    status:     JobStatus = JobStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    session_id: Optional[str]        = None
    result:     Optional[list[Any]]  = None
    error:      Optional[str]        = None

    def touch(self) -> None:
        self.updated_at = datetime.now().isoformat()


class InMemoryJobStore:
    """Thread-safe, process-local store keyed by session_id."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock  = threading.Lock()

    def create(self, key: str) -> Job:
        """Create a new job for *key* (= session_id)."""
        job = Job(key=key)
        with self._lock:
            self._jobs[key] = job
        return job

    def get(self, key: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(key)

    def update(self, job: Job) -> None:
        job.touch()
        with self._lock:
            self._jobs[job.key] = job


# Module-level singleton
job_store = InMemoryJobStore()