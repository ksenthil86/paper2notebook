"""Research Paper → Colab Notebook API."""
import json
import asyncio
from typing import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, File, Form, Request, UploadFile, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse

import pipeline as _pipeline
from job_store import get_store

_executor = ThreadPoolExecutor(max_workers=4)

MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB
_ALLOWED_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}

limiter = Limiter(key_func=get_remote_address)


def _rate_limit_handler(request: StarletteRequest, exc: RateLimitExceeded) -> JSONResponse:
    """Return 429 with a Retry-After header (RFC 6585 compliant)."""
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}. Try again in 60 seconds."},
        headers={"Retry-After": "60"},
    )


app = FastAPI(
    title="Paper2Notebook",
    description="Convert research papers into production-quality Colab notebooks.",
    version="1.0.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/generate", status_code=202)
@limiter.limit("10/minute")
async def generate(
    request: Request,
    background_tasks: BackgroundTasks,
    api_key: str = Form(...),
    pdf_file: UploadFile = File(...),
    github_token: str | None = Form(None),
) -> dict:
    """Accept a PDF + API key, start a background generation job, return job_id."""
    # Content-type check (defence-in-depth; real content validated by pdf_parser)
    content_type = (pdf_file.content_type or "").split(";")[0].strip().lower()
    if content_type not in _ALLOWED_PDF_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Only PDF files are accepted (application/pdf)")

    # Size check — read one byte beyond the limit to detect oversized files
    pdf_bytes = await pdf_file.read(MAX_PDF_BYTES + 1)
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF exceeds the 20 MB size limit")

    store = get_store()
    job_id = store.create_job()

    background_tasks.add_task(
        _run_pipeline_in_thread,
        job_id=job_id,
        pdf_bytes=pdf_bytes,
        api_key=api_key,
        github_token=github_token,
    )

    return {"job_id": job_id}


async def _run_pipeline_in_thread(
    job_id: str,
    pdf_bytes: bytes,
    api_key: str,
    github_token: str | None,
) -> None:
    """Run the blocking pipeline in a thread pool so the event loop stays free."""
    store = get_store()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        _executor,
        _pipeline.run_pipeline,
        job_id,
        store,
        pdf_bytes,
        api_key,
        github_token,
    )


@app.get("/status/{job_id}")
async def status(job_id: str) -> StreamingResponse:
    """Stream SSE events for a job. Returns 404 if job_id is unknown."""
    store = get_store()
    if store.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return StreamingResponse(
        _sse_generator(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _sse_generator(job_id: str) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted events until the 'done' or 'error' phase is emitted."""
    store = get_store()
    emitted_count = 0
    max_wait_seconds = 300
    waited = 0.0
    poll_interval = 0.1

    while waited < max_wait_seconds:
        events = store.get_events(job_id)
        while emitted_count < len(events):
            event = events[emitted_count]
            emitted_count += 1
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("phase") in ("done", "error"):
                return

        await asyncio.sleep(poll_interval)
        waited += poll_interval
