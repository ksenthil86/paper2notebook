# Sprint v1 — Walkthrough

## Summary

Built **Paper2Notebook** end-to-end: a web app where researchers upload a research paper PDF, enter their Gemini API key, and receive a production-quality `.ipynb` Google Colab notebook in their browser. The app features a beautiful dark UI (arcprize.org-inspired), live SSE progress updates, automatic `.ipynb` download, and an optional one-click "Open in Colab" button backed by GitHub Gist upload. All 10 tasks shipped in v1; the API was subsequently migrated from OpenAI to Gemini.

---

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────┐
│                        Browser (React)                        │
│                                                               │
│  ┌───────────────────────────────────────────┐               │
│  │             Form Card                     │               │
│  │  [Gemini API Key ••••]                    │               │
│  │  ▶ Optional — for Open in Colab           │               │
│  │  [Drop PDF here]                          │               │
│  │  [Generate Notebook]                      │               │
│  └──────────────────┬────────────────────────┘               │
│                     │ POST /generate (multipart)             │
│                     │                                        │
│  ┌──────────────────▼────────────────────────┐               │
│  │           Progress Panel                  │               │
│  │  ✓ Parsing PDF...                         │               │
│  │  ✓ Analyzing paper...                     │               │
│  │  ⟳ Generating implementation...           │  GET /status  │
│  │                                           │◀──── SSE ─────┤
│  │  [Download .ipynb]  [Open in Colab ↗]     │               │
│  └───────────────────────────────────────────┘               │
└──────────────────────────────────────────────────────────────-┘
                          │
              POST /generate          GET /status/{job_id}
                          │                    │
┌─────────────────────────▼────────────────────▼───────────────┐
│                   FastAPI Backend                             │
│                                                               │
│  POST /generate ──▶ create job ──▶ background thread         │
│                                         │                     │
│                              ┌──────────▼──────────┐         │
│                              │   pipeline.py        │         │
│                              │                      │         │
│                              │  pdf_parser.py       │         │
│                              │  (pdfplumber)        │         │
│                              │       ↓              │         │
│                              │  notebook_generator  │         │
│                              │  (Gemini API)        │         │
│                              │  Phase 1: metadata   │         │
│                              │  Phase 2: cells JSON │         │
│                              │       ↓              │         │
│                              │  notebook_builder    │         │
│                              │  (nbformat v4)       │         │
│                              │       ↓              │         │
│                              │  gist_uploader       │         │
│                              │  (GitHub Gist API)   │         │
│                              └──────────┬───────────┘         │
│                                         │ emit events         │
│                              ┌──────────▼───────────┐         │
│                              │    JobStore           │         │
│                              │  (in-memory queue)   │         │
│                              └──────────┬───────────┘         │
│                                         │                     │
│  GET /status/{job_id} ──▶ SSE polling ──┘                     │
└──────────────────────────────────────────────────────────────-┘
```

---

## Files Created/Modified

### `backend/main.py`
**Purpose**: FastAPI app entry point — defines HTTP routes and wires the async pipeline dispatch.

**Key functions**:
- `POST /generate` — accepts multipart form (api_key, pdf_file, github_token?), creates a job in `JobStore`, schedules the pipeline as a background task
- `GET /status/{job_id}` — returns an SSE stream via `StreamingResponse`
- `_run_pipeline_in_thread()` — runs the blocking pipeline in a `ThreadPoolExecutor` via `asyncio.run_in_executor()`
- `_sse_generator()` — async generator that polls `JobStore` every 100ms and yields new events until `done` or `error`

**How it works**:

The critical insight is keeping the FastAPI event loop unblocked. The AI calls (Gemini) are slow synchronous operations. If they ran on the event loop directly, all SSE clients would freeze. The fix is `ThreadPoolExecutor`:

```python
_executor = ThreadPoolExecutor(max_workers=4)

async def _run_pipeline_in_thread(job_id, pdf_bytes, api_key, github_token):
    store = get_store()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        _executor, _pipeline.run_pipeline, job_id, store, pdf_bytes, api_key, github_token
    )
```

The pipeline runs in a thread, writes events into `JobStore`, while the SSE generator runs on the event loop and polls `JobStore` every 100ms — interleaving is safe because `JobStore` uses a threading lock.

One subtle bug avoided: `main.py` imports `pipeline` as a module (`import pipeline as _pipeline`) rather than `from pipeline import run_pipeline`. This matters for test mocking — patching `pipeline.run_pipeline` only works if `main.py` looks up `_pipeline.run_pipeline` at call time, not at import time.

---

### `backend/job_store.py`
**Purpose**: Thread-safe in-memory event queue, one per job.

**Key methods**:
- `create_job()` → UUID string; initialises an empty event list
- `emit(job_id, phase, message, **extra)` → appends `{phase, message, ...extra}` to the job's list
- `get_events(job_id)` → returns a snapshot copy (safe for concurrent reads)
- Singleton `get_store()` returns one shared instance across the app

**How it works**:

Every write and read acquires `threading.Lock()`. The SSE generator calls `get_events()` which returns a list copy — so iteration is safe even if the pipeline thread is appending simultaneously. Events accumulate forever for the job's lifetime (no cleanup in v1 — a known limitation).

```python
def emit(self, job_id: str, phase: str, message: str, **extra: Any) -> None:
    event = {"phase": phase, "message": message, **extra}
    with self._lock:
        if job_id in self._jobs:
            self._jobs[job_id].append(event)
```

---

### `backend/pdf_parser.py`
**Purpose**: Extract clean plain text from a PDF upload.

**Key function**: `extract_text(source: bytes | IOBase) -> str`

**How it works**:

Validates the `%PDF-` header before passing to pdfplumber (early rejection of non-PDFs). Extracts text page-by-page with `x_tolerance=3` (handles tight column spacing). Pages are joined with double newlines, then runs of 3+ newlines are collapsed to 2 — giving clean paragraph separation without excessive blank lines.

```python
file_obj.seek(0)
header = file_obj.read(5)
if header != b"%PDF-":
    raise ValueError("Input is not a valid PDF (missing %PDF- header)")
```

Multi-column academic papers sometimes produce garbled text (columns run together), but pdfplumber's character-level extraction handles most cases correctly.

---

### `backend/notebook_generator.py`
**Purpose**: Two-phase Gemini API calls — extract paper metadata, then generate notebook cells.

**Key functions**:
- `make_client(api_key)` → `genai.Client` authenticated with the user's key
- `analyze_paper(client, paper_text)` → Phase 1: structured metadata dict
- `generate_cells(client, paper_text, metadata)` → Phase 2: `[{cell_type, source}, ...]`
- `_call_with_fallback(client, system, user)` → tries `MODEL_PREFERENCE` in order
- `_strip_json_fences(text)` → handles models wrapping JSON in ` ```json ``` `

**How it works**:

Two separate Gemini calls are needed because the token budget for a 30-page paper + full notebook generation in one shot is enormous and the structured metadata is more reliably extracted in isolation.

**Phase 1** sends a strict JSON schema in the user prompt (with `{{}}` to escape literal braces in `.format()` calls) and instructs the model to respond with only valid JSON. The response is stripped of markdown fences and parsed.

**Phase 2** sends the paper text AND the Phase 1 metadata, then instructs the model to produce a JSON array of `{cell_type, source}` objects following a 7-section structure (title → setup → imports → overview → per-algorithm theory/implementation/data/experiment/viz → comparison → discussion).

```python
MODEL_PREFERENCE: list[str] = ["gemini-2.5-pro", "gemini-2.0-flash"]

def _call_with_fallback(client, system_instruction, user_message) -> str:
    for model in MODEL_PREFERENCE:
        try:
            response = client.models.generate_content(
                model=model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=16000,
                ),
            )
            return response.text
        except Exception:
            continue
    raise RuntimeError("All models failed")
```

---

### `backend/notebook_builder.py`
**Purpose**: Convert the flat cell JSON array into a valid `.ipynb` file.

**Key function**: `build_notebook(cells: list[dict]) -> bytes`

**How it works**:

Uses `nbformat.v4` helpers to create typed cells. Importantly, it checks whether any code cell starts with `!pip install` and injects a default pip install cell before the first code cell if none is present — so the notebook is always runnable in Colab without manual setup.

The notebook metadata includes a `colab` key with `toc_visible: true` which activates Google Colab's table-of-contents sidebar, and a `python3` kernelspec so Colab selects the right runtime automatically.

```python
nb = new_notebook(cells=nb_cells, metadata=_NOTEBOOK_METADATA)
nb.nbformat = 4
nb.nbformat_minor = 5
return nbformat.writes(nb).encode("utf-8")
```

---

### `backend/pipeline.py`
**Purpose**: Orchestrates all backend phases synchronously; emits SSE events at each phase boundary.

**Key function**: `run_pipeline(job_id, store, pdf_bytes, api_key, github_token=None)`

**How it works**:

Runs entirely synchronously (designed to execute in a thread pool). Emits a `store.emit()` call before each phase so the SSE client sees live progress. The `done` event includes the full base64-encoded notebook — this is how the frontend triggers the download without a separate download endpoint.

```python
notebook_b64 = base64.b64encode(nb_bytes).decode("ascii")
store.emit(job_id, "done", "Done! Your notebook is ready.", notebook_b64=notebook_b64)
```

If a GitHub token is provided, `gist_uploader.upload_gist()` is called after assembly and the returned `colab_url` is included in the `done` event payload.

Any unhandled exception is caught at the top level and emitted as an `error` event — the frontend re-enables the form when it sees this.

---

### `backend/gist_uploader.py`
**Purpose**: Upload the `.ipynb` to GitHub as a public Gist and return a Colab-compatible URL.

**Key function**: `upload_gist(nb_bytes: bytes, github_token: str) -> str`

**How it works**:

POSTs to `https://api.github.com/gists` using `httpx` (synchronous, since this runs in a thread). The notebook bytes are decoded to UTF-8 string (GitHub Gist API accepts string content, not binary). The response JSON contains `id` (gist ID) and `owner.login` (username), which are composed into the Colab URL:

```
https://colab.research.google.com/gist/{username}/{gist_id}
```

Any non-2xx response raises `RuntimeError` with the status code and body — this bubbles up to `pipeline.py`'s catch-all which emits an `error` SSE event.

---

### `frontend/src/App.jsx`
**Purpose**: Single React component managing the full UI — form, SSE streaming, progress panel, download, and Colab link.

**Key state**:
- `apiKey` / `pdfFile` — form inputs; `canGenerate = apiKey.trim() && pdfFile`
- `progress` — `null` = show form, `[]` or populated = show progress panel
- `error` — shown as red text beneath the form

**How it works**:

On submit, POSTs `FormData` to `/generate`, gets `job_id`, then opens an `EventSource` to `/status/{job_id}`. Each SSE message updates the `progress` array.

When the `done` phase arrives, the base64 notebook is decoded inline and a synthetic `<a>` click triggers the browser download:

```js
const blob = new Blob(
  [Uint8Array.from(atob(notebook_b64), c => c.charCodeAt(0))],
  { type: 'application/json' }
)
const url = URL.createObjectURL(blob)
const a = document.createElement('a')
a.href = url; a.download = 'notebook.ipynb'; a.click()
URL.revokeObjectURL(url)
```

A `streamDone` flag prevents the `onerror` handler from firing after the `EventSource` is intentionally closed (browsers fire `onerror` when the stream ends normally).

---

### `frontend/src/App.css`
**Purpose**: arcprize.org-inspired dark theme — all visual styles.

**Design tokens**:
- Background: `#0a0a0b` (near-black)
- Surface/card: `#111113` with `border: 1px solid #222226`
- Accent: `#e8c547` (yellow — used for the "Paper" prefix in the logo)
- Primary text: `#f0f0f0`, muted: `#888`
- Font: Inter (body), JetBrains Mono (code elements)
- Max-width: 680px, centered

Key components styled: `.form-card`, `.dropzone` (dashed border, drag-over highlight), `.collapsible-toggle` (animated chevron), `.generate-btn` (accent fill, disabled state), `.progress-panel`, `.spinner` (CSS keyframe animation), `.checkmark`.

---

### `frontend/index.html`
**Purpose**: HTML shell — loads Google Fonts and mounts the React app.

Loads Inter (weights 400, 500, 600) and JetBrains Mono (weight 400) via Google Fonts preconnect. The `<div id="root">` is where React mounts.

---

### `frontend/vite.config.js`
**Purpose**: Vite dev server config — proxies API calls to the FastAPI backend.

All requests to `/generate`, `/status`, and `/health` are proxied to `http://localhost:8000`, so the React dev server and FastAPI can run on different ports without CORS issues during development.

---

## Data Flow

```
1. User fills form (Gemini API key + PDF file)
   → canGenerate = true → Generate button enables

2. User clicks Generate
   → POST /generate (multipart: api_key, pdf_file, github_token?)
   → Backend: create UUID job → add to JobStore → 202 {job_id}
   → Frontend: progress = [] → form replaced by progress panel

3. Frontend opens EventSource to GET /status/{job_id}
   → Backend: _sse_generator polls JobStore every 100ms

4. Background thread runs pipeline.run_pipeline():
   a. store.emit(parsing)    → pdfplumber extracts text
   b. store.emit(analyzing)  → Gemini Phase 1: paper metadata JSON
   c. store.emit(generating) → Gemini Phase 2: notebook cell JSON array
   d. store.emit(assembling) → nbformat assembles .ipynb bytes
   e. [if github_token]
      store.emit(uploading)  → httpx POST to GitHub Gist API
   f. store.emit(done, notebook_b64=..., colab_url=...)

5. SSE generator sees new events → yields to frontend
   → Frontend appends each event to progress[] → panel updates

6. Frontend receives done event:
   → Decodes base64 → Blob → synthetic <a> click → .ipynb downloads
   → If colab_url present → "Open in Colab ↗" link appears

7. If any exception in pipeline:
   → store.emit(error) → frontend shows red error, re-shows form
```

---

## Test Coverage

- **Unit (54 tests)**
  - `test_pdf_parser.py` (6) — valid PDF extraction, invalid input rejection, whitespace normalization
  - `test_notebook_generator.py` (16) — both phases mocked; validates client calls, JSON parsing, fence stripping, model fallback constants
  - `test_notebook_builder.py` (15) — nbformat assembly, pip cell injection, cell type validation, metadata presence
  - `test_gist_uploader.py` (12) — httpx mocked; success path, non-2xx error, URL construction, auth header
  - `test_readme.py` (5) — README content validation (prerequisites, Gemini key, model fallback)

- **Integration (32 tests)**
  - `test_generate_endpoint.py` (11) — FastAPI test client; POST /generate 202 + job_id, GET /status SSE, 404 on unknown job, SSE event format
  - `test_pipeline.py` (12) — full pipeline with all external calls mocked; phase order, done payload, error emission, gist upload conditional

- **E2E (17 tests)**
  - `task7-ui.spec.js` — Playwright; app title, password input, dropzone, button enable/disable, collapsible GitHub token, dark background, accent color, hidden progress panel, form card, fonts
  - `task8-sse.spec.js` (5) — SSE mock via `page.route()`; progress panel appears, events render, download triggered, Colab link visible, error state

**Total: 103 tests — 103 passing**

---

## Security Measures

- **API keys never stored** — `api_key` and `github_token` are form fields passed directly to the pipeline thread; they are not logged or persisted
- **CORS scoped** — only `localhost:5173` and `127.0.0.1:5173` are allowed origins (production deploy will need updating)
- **PDF header validation** — `%PDF-` check before passing to pdfplumber prevents non-PDF files from reaching the parser
- **Bandit clean** — all Python files passed `bandit` static analysis (no high-severity findings)
- **npm audit clean** — 0 vulnerabilities in frontend dependencies
- **No shell injection** — notebook content is assembled via nbformat API, never via string interpolation into shell commands

---

## Known Limitations

- **In-memory job store** — jobs accumulate forever; the server will run out of memory if many PDFs are processed without restarts. v2 should add a TTL-based cleanup or use Redis.
- **No auth/rate limiting** — anyone who can reach the server can trigger Gemini API calls with arbitrary keys. Suitable for local use, not public deployment.
- **Single-server only** — `JobStore` is a process-local singleton; horizontal scaling would split SSE clients from pipeline workers.
- **No upload size limit** — large PDFs (100+ pages) are fully loaded into memory; FastAPI has no `max_upload_size` configured.
- **Gemini token limits** — 80K chars of paper text is sent in Phase 2; very long papers are silently truncated.
- **`.ipynb` filename is always `notebook.ipynb`** — not derived from the paper title.
- **Gist is always public** — Colab requires public gists; private notebooks can't use the "Open in Colab" feature.
- **No streaming AI output** — the progress panel shows phase-level updates, not token-by-token streaming. The "Generating" phase is a black box that can take 30–120 seconds.

---

## What's Next

**v2 priorities:**

1. **Streaming token output** — use Gemini's streaming API to show partial notebook content as it generates, keeping users engaged during the long Phase 2 call
2. **Job cleanup** — TTL-based eviction from `JobStore` (or swap to Redis for scalability)
3. **Upload size limit** — reject PDFs over 20MB at the FastAPI layer
4. **Better filename** — derive download filename from `metadata["title"]` (slugified)
5. **Private Colab sharing** — investigate Colab's Drive import API as an alternative to public Gist
6. **Deployment config** — Dockerfile, nginx reverse proxy, environment-specific CORS, secrets management
