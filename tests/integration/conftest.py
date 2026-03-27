"""Shared fixtures for all integration tests."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

import pytest


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset in-memory rate limit counters before every integration test."""
    from main import limiter
    limiter.reset()
    yield
