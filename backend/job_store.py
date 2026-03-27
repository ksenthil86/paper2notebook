"""In-memory job store for background generation jobs."""
import uuid
import time
import threading
from typing import Any

_JOB_TTL_SECONDS = 45 * 60        # 45 minutes
_EVICT_INTERVAL_SECONDS = 5 * 60  # run eviction every 5 minutes


class JobStore:
    """Thread-safe in-memory store for job events with TTL eviction."""

    def __init__(self) -> None:
        # Each job: {"created_at": float, "events": [...]}
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._start_eviction_thread()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _start_eviction_thread(self) -> None:
        """Start a background daemon thread that evicts expired jobs."""
        t = threading.Thread(target=self._eviction_loop, daemon=True)
        t.start()

    def _eviction_loop(self) -> None:
        while True:
            time.sleep(_EVICT_INTERVAL_SECONDS)
            self._evict_expired()

    def _evict_expired(self) -> None:
        """Delete jobs whose created_at is older than _JOB_TTL_SECONDS."""
        cutoff = time.time() - _JOB_TTL_SECONDS
        with self._lock:
            expired = [jid for jid, job in self._jobs.items() if job["created_at"] < cutoff]
            for jid in expired:
                del self._jobs[jid]

    # ── Public API ────────────────────────────────────────────────────────────

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = {"created_at": time.time(), "events": []}
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._jobs.get(job_id)

    def emit(self, job_id: str, phase: str, message: str, **extra: Any) -> None:
        event: dict[str, Any] = {"phase": phase, "message": message, **extra}
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["events"].append(event)

    def get_events(self, job_id: str) -> list[dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return list(job["events"]) if job is not None else []

    def delete_job(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)


# Singleton shared across the app
_store = JobStore()


def get_store() -> JobStore:
    return _store
