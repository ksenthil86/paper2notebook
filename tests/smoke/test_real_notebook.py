"""
Real-API smoke test — validates end-to-end notebook generation with a real PDF.

Run manually (never auto-collected by the regular test suite):
    pytest tests/smoke/ -m real -s

Requirements:
    GEMINI_API_KEY  — set in environment (test skipped if absent)
    REAL_PDF_PATH   — path to a PDF to upload (optional; defaults to searching
                      ~/Desktop recursively for 'attention*.pdf')

The test launches the backend in-process (FastAPI TestClient) and simulates
what the frontend does: POST to /generate, then stream /status/{job_id} until
a 'done' or 'error' event arrives.  It then decodes the notebook and validates
its structure.
"""
import sys
import os
import io
import json
import glob
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

import pytest

# ── markers ──────────────────────────────────────────────────────────────────

def pytest_configure(config):  # noqa: D103 — called by pytest at collection time
    config.addinivalue_line("markers", "real: mark test as a real-API smoke test")


# ── helpers ───────────────────────────────────────────────────────────────────

def _find_pdf() -> str | None:
    """Return path to a PDF from env or a Desktop search; None if not found."""
    env_path = os.environ.get("REAL_PDF_PATH")
    if env_path:
        return env_path if os.path.isfile(env_path) else None
    desktop = os.path.expanduser("~/Desktop")
    matches = glob.glob(os.path.join(desktop, "**", "attention*.pdf"), recursive=True)
    return matches[0] if matches else None


def _stream_status(client, job_id: str, timeout: float = 180.0) -> dict:
    """Stream SSE from /status/{job_id} and return the final event (done/error)."""
    deadline = time.time() + timeout
    with client.stream("GET", f"/status/{job_id}") as resp:
        assert resp.status_code == 200, f"Status stream returned {resp.status_code}"
        for line in resp.iter_lines():
            if time.time() > deadline:
                pytest.fail(f"Timed out after {timeout}s waiting for done/error event")
            if not line.startswith("data:"):
                continue
            event = json.loads(line[len("data:"):].strip())
            phase = event.get("phase", "")
            print(f"  [{phase}] {event.get('message', '')}")
            if phase in ("done", "error"):
                return event
    pytest.fail("SSE stream ended without a done/error event")


# ── smoke test ────────────────────────────────────────────────────────────────

@pytest.mark.real
def test_real_notebook_generation():
    """
    End-to-end: upload a real PDF, wait for done event, validate notebook.

    Skipped automatically when GEMINI_API_KEY or a suitable PDF is absent.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not set — skipping real-API smoke test")

    pdf_path = _find_pdf()
    if not pdf_path:
        pytest.skip(
            "No PDF found. Set REAL_PDF_PATH or place 'attention*.pdf' on ~/Desktop"
        )

    print(f"\n  Using PDF: {pdf_path}")
    print(f"  API key:   {api_key[:8]}...")

    from main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # ── POST /generate ────────────────────────────────────────────────────────
    with open(pdf_path, "rb") as fh:
        pdf_bytes = fh.read()

    resp = client.post(
        "/generate",
        data={"api_key": api_key},
        files={"pdf_file": ("paper.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"
    job_id = resp.json()["job_id"]
    print(f"  Job ID:    {job_id}")

    # ── Stream status ─────────────────────────────────────────────────────────
    final_event = _stream_status(client, job_id, timeout=180.0)

    if final_event["phase"] == "error":
        pytest.fail(f"Pipeline emitted error: {final_event.get('message')}")

    # ── Decode and validate notebook ──────────────────────────────────────────
    notebook_b64 = final_event.get("notebook_b64")
    assert notebook_b64, "done event missing notebook_b64"

    import base64
    notebook_bytes = base64.b64decode(notebook_b64)
    try:
        nb = json.loads(notebook_bytes)
    except json.JSONDecodeError as exc:
        pytest.fail(f"Notebook is not valid JSON: {exc}")

    # Structure checks
    assert "cells" in nb, "Notebook missing 'cells' key"
    cells = nb["cells"]
    assert len(cells) >= 8, f"Expected ≥8 cells, got {len(cells)}"
    assert nb.get("nbformat") == 4, f"Expected nbformat 4, got {nb.get('nbformat')}"

    def _src(cell: dict) -> str:
        src = cell.get("source", "")
        return "".join(src) if isinstance(src, list) else src

    # At least one markdown cell mentions "Attention"
    md_cells = [c for c in cells if c.get("cell_type") == "markdown"]
    assert md_cells, "No markdown cells in notebook"
    attention_found = any("attention" in _src(c).lower() for c in md_cells)
    assert attention_found, (
        "No markdown cell contains 'Attention' (case-insensitive). "
        f"Markdown sources: {[_src(c)[:80] for c in md_cells]}"
    )

    # At least one code cell contains a Python function definition
    code_cells = [c for c in cells if c.get("cell_type") == "code"]
    assert code_cells, "No code cells in notebook"
    has_function = any("def " in _src(c) for c in code_cells)
    assert has_function, (
        "No code cell contains a function definition ('def '). "
        f"Code sources (first 80 chars): {[_src(c)[:80] for c in code_cells]}"
    )

    # No cell source is empty
    empty_cells = [i for i, c in enumerate(cells) if not _src(c).strip()]
    assert not empty_cells, f"Cells at indices {empty_cells} have empty source"

    print(f"\n  PASS — {len(cells)} cells, {len(md_cells)} markdown, {len(code_cells)} code")
    print(f"  Notebook size: {len(notebook_bytes):,} bytes")
