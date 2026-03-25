"""Real generation pipeline: PDF → analysis → notebook cells → .ipynb bytes.

Each phase emits an SSE event via the job store so the frontend can show
live progress. On any error, an 'error' event is emitted and the pipeline
stops immediately.
"""
import base64

from job_store import JobStore
from pdf_parser import extract_text
from notebook_generator import make_client, analyze_paper, generate_cells
from notebook_builder import build_notebook


def run_pipeline(
    job_id: str,
    store: JobStore,
    pdf_bytes: bytes,
    api_key: str,
    github_token: str | None = None,
) -> None:
    """Execute the full generation pipeline synchronously (runs in a thread).

    Phases emitted to SSE:
        parsing    → PDF text extraction
        analyzing  → Phase 1 OpenAI call (metadata)
        generating → Phase 2 OpenAI call (notebook cells)
        assembling → nbformat assembly
        uploading  → GitHub Gist upload (only if github_token provided)
        done       → final event with base64-encoded notebook

    On any exception, emits an 'error' event and returns.
    """
    try:
        # ── Phase 1: parse PDF ──────────────────────────────────────────────
        store.emit(job_id, "parsing", "Parsing PDF and extracting text...")
        paper_text = extract_text(pdf_bytes)

        # ── Phase 2: analyze paper ──────────────────────────────────────────
        store.emit(
            job_id,
            "analyzing",
            "Identifying algorithms, methods, and key equations...",
        )
        client = make_client(api_key)
        metadata = analyze_paper(client, paper_text)

        # ── Phase 3: generate notebook cells ───────────────────────────────
        store.emit(
            job_id,
            "generating",
            "Generating implementation — this takes a moment with reasoning models...",
        )
        cells = generate_cells(client, paper_text, metadata)

        # ── Phase 4: assemble .ipynb ────────────────────────────────────────
        store.emit(job_id, "assembling", "Assembling notebook cells...")
        nb_bytes = build_notebook(cells)

        # ── Phase 5 (optional): upload GitHub Gist ─────────────────────────
        colab_url: str | None = None
        if github_token:
            store.emit(job_id, "uploading", "Uploading to GitHub Gist...")
            # Gist upload implemented in Task 9 (gist_uploader.py)
            # Placeholder: colab_url remains None until Task 9
            try:
                from gist_uploader import upload_gist  # noqa: PLC0415
                colab_url = upload_gist(nb_bytes, github_token)
            except ImportError:
                pass  # Task 9 not yet implemented

        # ── Done ────────────────────────────────────────────────────────────
        notebook_b64 = base64.b64encode(nb_bytes).decode("ascii")
        done_payload: dict = {
            "notebook_b64": notebook_b64,
        }
        if colab_url:
            done_payload["colab_url"] = colab_url

        store.emit(job_id, "done", "Done! Your notebook is ready.", **done_payload)

    except Exception as exc:  # noqa: BLE001
        store.emit(
            job_id,
            "error",
            f"Generation failed: {type(exc).__name__}: {exc}",
        )
