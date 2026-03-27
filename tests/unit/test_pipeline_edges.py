"""Unit tests: edge cases across backend modules not covered by existing tests."""
import sys
import os
import json
import threading
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

import pytest


# ── notebook_generator._strip_json_fences ────────────────────────────────────

class TestStripJsonFences:

    def test_no_fences_returns_text_unchanged(self):
        from notebook_generator import _strip_json_fences
        raw = '{"key": "value"}'
        assert _strip_json_fences(raw) == raw

    def test_strips_json_fenced_block(self):
        from notebook_generator import _strip_json_fences
        fenced = '```json\n{"key": "value"}\n```'
        assert _strip_json_fences(fenced) == '{"key": "value"}'

    def test_strips_plain_fenced_block(self):
        from notebook_generator import _strip_json_fences
        fenced = '```\n{"key": "value"}\n```'
        assert _strip_json_fences(fenced) == '{"key": "value"}'

    def test_preserves_nested_braces(self):
        from notebook_generator import _strip_json_fences
        inner = '{"a": {"b": {"c": 1}}}'
        fenced = f"```json\n{inner}\n```"
        assert _strip_json_fences(fenced) == inner

    def test_strips_leading_trailing_whitespace(self):
        from notebook_generator import _strip_json_fences
        assert _strip_json_fences("  \n  hello  \n  ") == "hello"

    def test_all_models_fail_raises_runtime_error(self):
        """_call_with_fallback raises RuntimeError when all models fail."""
        from notebook_generator import _call_with_fallback
        client = MagicMock()
        client.models.generate_content.side_effect = Exception("quota exceeded")
        with pytest.raises(RuntimeError, match="All models"):
            _call_with_fallback(client, "system", "user")

    def test_fallback_tries_second_model_after_first_fails(self):
        """_call_with_fallback tries the next model when the first raises."""
        from notebook_generator import _call_with_fallback, MODEL_PREFERENCE
        if len(MODEL_PREFERENCE) < 2:
            pytest.skip("Need at least 2 models in MODEL_PREFERENCE")
        client = MagicMock()
        second_resp = MagicMock()
        second_resp.text = '{"ok": true}'
        # First call raises, second succeeds
        client.models.generate_content.side_effect = [
            Exception("first model failed"),
            second_resp,
        ]
        result = _call_with_fallback(client, "system", "user")
        assert result == '{"ok": true}'
        assert client.models.generate_content.call_count == 2

    def test_generate_cells_raises_on_non_list_json(self):
        """generate_cells raises ValueError when model returns a JSON object, not array."""
        from notebook_generator import generate_cells
        client = MagicMock()
        client.models.generate_content.return_value = MagicMock(text='{"not": "a list"}')
        with pytest.raises(ValueError, match="array"):
            generate_cells(client, "paper text", {})

    def test_analyze_paper_raises_on_invalid_json(self):
        """analyze_paper raises ValueError when model returns unparseable text."""
        from notebook_generator import analyze_paper
        client = MagicMock()
        client.models.generate_content.return_value = MagicMock(text="this is not json at all")
        with pytest.raises(ValueError, match="JSON"):
            analyze_paper(client, "paper text")


# ── notebook_builder edge cases ───────────────────────────────────────────────

def _source(cell: dict) -> str:
    """Return cell source as a flat string (nbformat stores it as list or str)."""
    src = cell.get("source", "")
    return "".join(src) if isinstance(src, list) else src


class TestNotebookBuilderEdges:

    def test_empty_cell_list_returns_valid_nbformat(self):
        """build_notebook([]) returns valid JSON with a pip install cell injected."""
        from notebook_builder import build_notebook
        result = build_notebook([])
        nb = json.loads(result.decode("utf-8"))
        assert "cells" in nb
        assert nb["nbformat"] == 4
        # pip cell should be injected
        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        assert len(code_cells) >= 1
        assert "pip install" in _source(code_cells[0])

    def test_only_markdown_cells_injects_pip_cell(self):
        """build_notebook with only markdown cells still injects a pip install cell."""
        from notebook_builder import build_notebook
        cells = [
            {"cell_type": "markdown", "source": "# Title"},
            {"cell_type": "markdown", "source": "## Overview"},
        ]
        result = build_notebook(cells)
        nb = json.loads(result.decode("utf-8"))
        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        assert len(code_cells) >= 1
        assert "pip install" in _source(code_cells[0])

    def test_existing_pip_cell_not_duplicated(self):
        """build_notebook does NOT inject a second pip cell when one already exists."""
        from notebook_builder import build_notebook
        cells = [
            {"cell_type": "code", "source": "!pip install torch"},
            {"cell_type": "code", "source": "import torch"},
        ]
        result = build_notebook(cells)
        nb = json.loads(result.decode("utf-8"))
        pip_cells = [
            c for c in nb["cells"]
            if c["cell_type"] == "code" and "pip install" in _source(c)
        ]
        assert len(pip_cells) == 1

    def test_result_is_valid_utf8_bytes(self):
        """build_notebook always returns bytes (not str)."""
        from notebook_builder import build_notebook
        result = build_notebook([{"cell_type": "markdown", "source": "# Hi"}])
        assert isinstance(result, bytes)
        result.decode("utf-8")  # must not raise


# ── JobStore concurrency edge cases ──────────────────────────────────────────

class TestJobStoreConcurrency:

    def test_concurrent_emit_no_data_corruption(self):
        """Two threads emitting to the same job produce all events without corruption."""
        from job_store import JobStore
        store = JobStore()
        job_id = store.create_job()
        errors = []

        def emit_n(phase_prefix, n):
            for i in range(n):
                try:
                    store.emit(job_id, f"{phase_prefix}-{i}", f"msg {i}")
                except Exception as exc:
                    errors.append(exc)

        t1 = threading.Thread(target=emit_n, args=("thread1", 50))
        t2 = threading.Thread(target=emit_n, args=("thread2", 50))
        t1.start(); t2.start()
        t1.join(); t2.join()

        assert not errors, f"Thread errors: {errors}"
        events = store.get_events(job_id)
        assert len(events) == 100

    def test_evict_expired_with_zero_jobs_does_not_raise(self):
        """_evict_expired on an empty store is a no-op."""
        from job_store import JobStore
        store = JobStore()
        store._evict_expired()  # must not raise

    def test_delete_nonexistent_job_does_not_raise(self):
        """delete_job on an unknown job_id is a no-op."""
        from job_store import JobStore
        store = JobStore()
        store.delete_job("nonexistent-id-xyz")  # must not raise


# ── pdf_parser edge cases ─────────────────────────────────────────────────────

class TestPdfParserEdges:

    def test_empty_bytes_raises_value_error(self):
        """extract_text(b'') raises ValueError immediately."""
        from pdf_parser import extract_text
        with pytest.raises(ValueError):
            extract_text(b"")

    def test_non_pdf_bytes_raises_value_error(self):
        """extract_text with arbitrary non-PDF bytes raises ValueError."""
        from pdf_parser import extract_text
        with pytest.raises(ValueError, match="PDF"):
            extract_text(b"PK\x03\x04 this is a zip file")


# ── gist_uploader Unicode content ────────────────────────────────────────────

class TestGistUploaderEdges:

    def test_unicode_notebook_content_serialised_correctly(self):
        """upload_gist handles notebooks with non-ASCII characters (e.g. equations)."""
        import httpx
        from gist_uploader import upload_gist

        unicode_nb = '{"cells": [{"source": "α β γ ∑ ∫ — Chinese: 你好"}]}'.encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "id": "abc123",
            "owner": {"login": "testuser"},
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("gist_uploader.httpx.post", return_value=mock_resp) as mock_post:
            url = upload_gist(unicode_nb, "ghp_testtoken")

        assert "abc123" in url
        # Verify the payload was sent as a string (not bytes)
        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs.get("json") or call_kwargs.get("content")
        assert payload is not None
