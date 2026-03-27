"""Task 3 (v2) — Unit tests: SSE error message sanitisation.

Verifies that sensitive tokens (GitHub PATs, Gemini API keys) are redacted
before being emitted over SSE, while the full error is still written to stderr.
"""
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_sanitise_fn():
    from pipeline import _sanitise_error
    return _sanitise_error


# ── _sanitise_error unit tests ────────────────────────────────────────────────

class TestSanitiseError:

    def test_plain_message_unchanged(self):
        fn = _get_sanitise_fn()
        msg = "ValueError: invalid PDF header"
        assert fn(msg) == msg

    def test_github_pat_classic_redacted(self):
        """ghp_XXXX tokens must be replaced with [REDACTED]."""
        fn = _get_sanitise_fn()
        msg = "GitHub API error: bad credentials for ghp_abcABC123XYZxyz456DEF"
        result = fn(msg)
        assert "ghp_" not in result
        assert "[REDACTED]" in result

    def test_github_pat_fine_grained_redacted(self):
        """github_pat_XXXX tokens must be replaced with [REDACTED]."""
        fn = _get_sanitise_fn()
        msg = "401 Unauthorized: github_pat_11ABCDEFG0abcdefghij_XYZxyz"
        result = fn(msg)
        assert "github_pat_" not in result
        assert "[REDACTED]" in result

    def test_gemini_api_key_redacted(self):
        """AIza... keys must be replaced with [REDACTED]."""
        fn = _get_sanitise_fn()
        msg = "Invalid API key: AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz1234567"
        result = fn(msg)
        assert "AIza" not in result
        assert "[REDACTED]" in result

    def test_multiple_tokens_all_redacted(self):
        """All token occurrences in a single message are redacted."""
        fn = _get_sanitise_fn()
        msg = "key=AIzaSyTest123 and token=ghp_TestTokenABC"
        result = fn(msg)
        assert "AIza" not in result
        assert "ghp_" not in result
        assert result.count("[REDACTED]") == 2

    def test_empty_string(self):
        fn = _get_sanitise_fn()
        assert fn("") == ""

    def test_no_token_no_change(self):
        fn = _get_sanitise_fn()
        msg = "RuntimeError: connection timeout after 30s"
        assert fn(msg) == msg


# ── pipeline error emission integration ──────────────────────────────────────

class TestPipelineErrorSanitisation:

    def _run_failing_pipeline(self, error_message: str) -> list[dict]:
        """Run the pipeline with a PDF-parse error and return all emitted events."""
        from unittest.mock import patch, MagicMock
        from job_store import JobStore
        import pipeline

        store = JobStore()
        job_id = store.create_job()

        with patch("pipeline.extract_text", side_effect=RuntimeError(error_message)):
            pipeline.run_pipeline(job_id, store, b"%PDF-fake", "AIza-key", None)

        return store.get_events(job_id)

    def test_github_pat_not_in_sse_event(self):
        """A GitHub PAT in the exception message must not reach the SSE client."""
        events = self._run_failing_pipeline(
            "GitHub API returned 401: bad credentials for ghp_SECRETTOKEN123"
        )
        error_events = [e for e in events if e["phase"] == "error"]
        assert len(error_events) == 1
        assert "ghp_" not in error_events[0]["message"]
        assert "[REDACTED]" in error_events[0]["message"]

    def test_gemini_key_not_in_sse_event(self):
        """A Gemini API key in the exception message must not reach the SSE client."""
        events = self._run_failing_pipeline(
            "Invalid API key provided: AIzaSyFakeKeyForTesting12345"
        )
        error_events = [e for e in events if e["phase"] == "error"]
        assert len(error_events) == 1
        assert "AIza" not in error_events[0]["message"]
        assert "[REDACTED]" in error_events[0]["message"]

    def test_plain_error_still_emitted(self):
        """A plain error message (no tokens) still reaches the SSE client unchanged."""
        events = self._run_failing_pipeline("PDF parsing failed: invalid structure")
        error_events = [e for e in events if e["phase"] == "error"]
        assert len(error_events) == 1
        assert "PDF parsing failed" in error_events[0]["message"]
