"""In-memory job store for background generation jobs."""
import uuid
import threading
from typing import Any


class JobStore:
    """Thread-safe in-memory store for job events."""

    def __init__(self) -> None:
        self._jobs: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = []
        return job_id

    def get_job(self, job_id: str) -> list[dict[str, Any]] | None:
        with self._lock:
            return self._jobs.get(job_id)

    def emit(self, job_id: str, phase: str, message: str, **extra: Any) -> None:
        event: dict[str, Any] = {"phase": phase, "message": message, **extra}
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].append(event)

    def get_events(self, job_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._jobs.get(job_id, []))

    def delete_job(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)


# Singleton shared across the app
_store = JobStore()


def get_store() -> JobStore:
    return _store
