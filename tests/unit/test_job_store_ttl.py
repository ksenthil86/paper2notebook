"""Unit tests: JobStore TTL eviction (45-minute daemon thread)."""
import sys
import os
import time
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

import pytest


class TestJobStoreTTL:

    def test_job_has_created_at_timestamp(self):
        """Each job must store a created_at timestamp when created."""
        from job_store import JobStore
        store = JobStore()
        job_id = store.create_job()
        job = store.get_job(job_id)
        assert job is not None
        assert "created_at" in job, "Job must have a 'created_at' key"

    def test_created_at_is_recent(self):
        """created_at must be a float (epoch seconds) close to now."""
        from job_store import JobStore
        store = JobStore()
        before = time.time()
        job_id = store.create_job()
        after = time.time()
        job = store.get_job(job_id)
        ts = job["created_at"]
        assert isinstance(ts, float)
        assert before <= ts <= after

    def test_eviction_removes_old_jobs(self):
        """Jobs older than the TTL must be deleted by _evict_expired()."""
        from job_store import JobStore
        store = JobStore()
        job_id = store.create_job()
        # Back-date the job's created_at by more than TTL
        with store._lock:
            store._jobs[job_id]["created_at"] = time.time() - (45 * 60 + 1)
        store._evict_expired()
        assert store.get_job(job_id) is None, "Old job should have been evicted"

    def test_eviction_keeps_fresh_jobs(self):
        """Jobs younger than the TTL must not be evicted."""
        from job_store import JobStore
        store = JobStore()
        job_id = store.create_job()
        store._evict_expired()
        assert store.get_job(job_id) is not None, "Fresh job should still exist"

    def test_daemon_thread_started_on_init(self):
        """JobStore.__init__ must start a background daemon thread."""
        import threading
        from job_store import JobStore
        before = {t.ident for t in threading.enumerate()}
        store = JobStore()
        after = threading.enumerate()
        daemon_threads = [t for t in after if t.daemon and t.ident not in before]
        assert len(daemon_threads) >= 1, "JobStore should start at least one daemon thread"
