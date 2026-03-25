"""Task 6 — Integration tests: real pipeline wired into background job + SSE.

All external calls (OpenAI, GitHub) are mocked.
"""
import sys
import os
import io
import json
import base64
import asyncio
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

import pytest
from fastapi.testclient import TestClient


# ── Shared PDF fixture ───────────────────────────────────────────────────────

_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
    b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 44>>stream\n"
    b"BT /F1 12 Tf 100 700 Td (Hello World) Tj ET\n"
    b"endstream\nendobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"xref\n0 6\n"
    b"0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n"
    b"0000000101 00000 n \n0000000230 00000 n \n0000000320 00000 n \n"
    b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n393\n%%EOF"
)

_FAKE_METADATA = {
    "title": "Test Paper",
    "authors": ["Author A"],
    "venue": "ICML 2024",
    "domain": "Machine Learning",
    "algorithms": [{"name": "TestAlgo", "description": "A test algorithm"}],
    "key_equations": [r"y = Wx + b"],
    "datasets_mentioned": [],
    "dependencies": ["numpy", "torch"],
}

_FAKE_CELLS = [
    {"cell_type": "markdown", "source": "# Test Paper"},
    {"cell_type": "code", "source": "!pip install numpy torch"},
    {"cell_type": "code", "source": "import numpy as np"},
]


def _make_client(client_fixture):
    return TestClient(client_fixture)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _drain_sse(client, job_id: str, timeout: float = 5.0) -> list[dict]:
    """Read all SSE events from /status/{job_id} until done/error."""
    events = []
    with client.stream("GET", f"/status/{job_id}") as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line.startswith("data:"):
                data = json.loads(line[len("data:"):].strip())
                events.append(data)
                if data.get("phase") in ("done", "error"):
                    break
    return events


def _post_generate(client, github_token=None):
    kwargs = {
        "data": {"api_key": "sk-test"},
        "files": {"pdf_file": ("paper.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
    }
    if github_token:
        kwargs["data"]["github_token"] = github_token
    resp = client.post("/generate", **kwargs)
    assert resp.status_code == 202
    return resp.json()["job_id"]


# ── Pipeline module ──────────────────────────────────────────────────────────

class TestPipelineModule:

    def test_pipeline_importable(self):
        import pipeline
        assert pipeline is not None

    def test_has_run_pipeline(self):
        from pipeline import run_pipeline
        assert callable(run_pipeline)


# ── Full pipeline via POST /generate + GET /status ───────────────────────────

class TestPipelineIntegration:

    @pytest.fixture
    def client(self):
        from main import app
        return TestClient(app)

    def _mock_all(self, colab_url=None):
        """Return a context-manager stack that mocks all external calls."""
        from notebook_builder import build_notebook
        fake_nb_bytes = build_notebook(_FAKE_CELLS)  # real nbformat bytes

        p1 = patch("pipeline.extract_text", return_value="Hello World paper text")
        p2 = patch("pipeline.make_client", return_value=MagicMock())
        p3 = patch("pipeline.analyze_paper", return_value=_FAKE_METADATA)
        p4 = patch("pipeline.generate_cells", return_value=_FAKE_CELLS)
        p5 = patch("pipeline.build_notebook", return_value=fake_nb_bytes)
        p6 = patch("pipeline.upload_gist", return_value=colab_url)
        return p1, p2, p3, p4, p5, p6

    def test_all_phases_emitted(self, client):
        """SSE stream must emit parsing, analyzing, generating, assembling, done phases."""
        patches = self._mock_all()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            job_id = _post_generate(client)
            events = _drain_sse(client, job_id)

        phases = [e["phase"] for e in events]
        for expected in ("parsing", "analyzing", "generating", "assembling", "done"):
            assert expected in phases, f"Missing phase: {expected} — got {phases}"

    def test_done_event_has_notebook_b64(self, client):
        """The 'done' SSE event must include a base64-encoded notebook."""
        patches = self._mock_all()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            job_id = _post_generate(client)
            events = _drain_sse(client, job_id)

        done = next(e for e in events if e["phase"] == "done")
        assert "notebook_b64" in done, f"'done' event missing notebook_b64: {done}"
        # Must decode to valid JSON
        nb_bytes = base64.b64decode(done["notebook_b64"])
        nb = json.loads(nb_bytes)
        assert nb.get("nbformat") == 4

    def test_error_phase_emitted_on_pdf_failure(self, client):
        """If PDF extraction raises, an 'error' event must be emitted."""
        with patch("pipeline.extract_text", side_effect=ValueError("bad PDF")):
            job_id = _post_generate(client)
            events = _drain_sse(client, job_id)

        phases = [e["phase"] for e in events]
        assert "error" in phases, f"Expected error phase, got: {phases}"

    def test_error_phase_emitted_on_openai_failure(self, client):
        """If OpenAI raises, an 'error' event must be emitted."""
        with patch("pipeline.extract_text", return_value="paper text"), \
             patch("pipeline.make_client", return_value=MagicMock()), \
             patch("pipeline.analyze_paper", side_effect=RuntimeError("API failure")):
            job_id = _post_generate(client)
            events = _drain_sse(client, job_id)

        phases = [e["phase"] for e in events]
        assert "error" in phases

    def test_error_event_has_message(self, client):
        """Error SSE event must include a human-readable message."""
        with patch("pipeline.extract_text", side_effect=ValueError("corrupt PDF")):
            job_id = _post_generate(client)
            events = _drain_sse(client, job_id)

        error_event = next(e for e in events if e["phase"] == "error")
        assert "message" in error_event
        assert len(error_event["message"]) > 0

    def test_phases_emitted_in_order(self, client):
        """Phases must appear in: parsing → analyzing → generating → assembling → done."""
        patches = self._mock_all()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            job_id = _post_generate(client)
            events = _drain_sse(client, job_id)

        phases = [e["phase"] for e in events]
        expected_order = ["parsing", "analyzing", "generating", "assembling", "done"]
        # Filter to just the expected phases in order
        filtered = [p for p in phases if p in expected_order]
        assert filtered == expected_order, f"Phase order wrong: {phases}"

    def test_main_uses_pipeline_not_placeholder(self, client):
        """POST /generate must invoke pipeline.run_pipeline, not the old placeholder."""
        patches = self._mock_all()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            with patch("pipeline.run_pipeline", wraps=__import__("pipeline").run_pipeline) as spy:
                job_id = _post_generate(client)
                _drain_sse(client, job_id)
                # run_pipeline should have been called
                assert spy.call_count >= 1

    def test_gist_upload_called_when_token_provided(self, client):
        """When github_token is provided, upload_gist is called and colab_url appears in done event."""
        colab_url = "https://colab.research.google.com/gist/testuser/abc123"
        patches = self._mock_all(colab_url=colab_url)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as mock_gist:
            job_id = _post_generate(client, github_token="ghp_testtoken")
            events = _drain_sse(client, job_id)

        mock_gist.assert_called_once()
        done = next(e for e in events if e["phase"] == "done")
        assert done.get("colab_url") == colab_url

    def test_gist_upload_not_called_without_token(self, client):
        """When no github_token is provided, upload_gist must NOT be called."""
        patches = self._mock_all()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as mock_gist:
            job_id = _post_generate(client)  # no github_token
            _drain_sse(client, job_id)

        mock_gist.assert_not_called()

    def test_uploading_phase_emitted_with_token(self, client):
        """When github_token is provided, the 'uploading' phase must appear in SSE."""
        patches = self._mock_all(colab_url="https://colab.research.google.com/gist/u/id")
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            job_id = _post_generate(client, github_token="ghp_testtoken")
            events = _drain_sse(client, job_id)

        phases = [e["phase"] for e in events]
        assert "uploading" in phases, f"Expected 'uploading' phase, got: {phases}"
