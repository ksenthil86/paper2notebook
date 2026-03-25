# Sprint v1 — Tasks

## Status: In Progress

---

### P0 — Core pipeline (must ship)

- [x] Task 1: Initialize project structure (P0)
  - Acceptance: Repo has `frontend/` (Vite+React) and `backend/` (FastAPI) folders; `npm run dev` and `uvicorn main:app --reload` both start without errors; `.env.example` documents env vars
  - Files: `frontend/package.json`, `frontend/src/main.jsx`, `frontend/src/App.jsx`, `backend/main.py`, `backend/requirements.txt`, `.env.example`, `README.md`
  - Completed: 2026-03-25 — Scaffolded Vite 6 + React 18 frontend and FastAPI backend; fixed rollup darwin-x64 native binary issue (universal node binary runs x86_64 by default); 9 unit tests green; bandit clean; npm audit 0 vulns

- [x] Task 2: Build FastAPI backend with background job system and SSE endpoint (P0)
  - Acceptance: `POST /generate` accepts `multipart/form-data` (api_key, github_token?, pdf_file), starts a background job, returns `{job_id}` immediately; `GET /status/{job_id}` returns an SSE stream that emits `{"phase": "...", "message": "..."}` events; CORS enabled for localhost:5173
  - Files: `backend/main.py`, `backend/job_store.py`
  - Completed: 2026-03-25 — JobStore (thread-safe in-memory event queue), POST /generate (202 + background task), GET /status (SSE polling generator); 11 integration tests green; bandit clean

- [ ] Task 3: Implement PDF text extraction (P0)
  - Acceptance: Given any PDF upload, extracts clean full text preserving section structure (headings, paragraphs); handles multi-column layouts; returns plain string
  - Files: `backend/pdf_parser.py`

- [ ] Task 4: Build the gpt-5.4 prompt and two-phase OpenAI call (P0)
  - Acceptance:
    - Phase 1 call: extracts paper title, authors, venue, list of algorithms/methods, key equations (LaTeX), and problem domain
    - Phase 2 call: generates the full notebook cell JSON array — each element has `{cell_type, source}` following the 7-section notebook structure in PRD (title → setup → imports → overview → per-algorithm: theory/impl/data/experiment/viz → comparison → discussion)
    - Prompt instructs model to use realistic synthetic data, type hints, docstrings, LaTeX math in markdown, production-quality Python
    - Falls back to `o3` → `gpt-4.1` if gpt-5.4 unavailable
  - Files: `backend/notebook_generator.py`

- [ ] Task 5: Assemble `.ipynb` from cell JSON using nbformat (P0)
  - Acceptance: Given the cell JSON array from Task 4, produces a valid `.ipynb` (nbformat v4); first code cell is `!pip install ...`; markdown cells use nbformat markdown type; notebook passes `nbformat.validate()`; notebook opens in Colab without warnings
  - Files: `backend/notebook_builder.py`

- [ ] Task 6: Wire background job pipeline and SSE events (P0)
  - Acceptance: Full pipeline runs as background job — pdf_parser → notebook_generator (phase 1) → notebook_generator (phase 2) → notebook_builder; each phase emits an SSE event with phase name + human-readable message; final SSE event includes base64-encoded notebook content; errors emit `{phase: "error", message: "..."}` and close the stream
  - Files: `backend/main.py`, `backend/pipeline.py`

- [ ] Task 7: Build the arcprize.org-inspired frontend UI — form + progress panel (P0)
  - Acceptance:
    - Single-page layout, max-width 680px, centered
    - Dark theme: bg `#0a0a0b`, surface `#111113`, accent `#e8c547`, fonts: Inter + JetBrains Mono (via Google Fonts)
    - Form card: OpenAI API key input (password type), collapsible GitHub Token section (labeled "Optional — for Open in Colab"), PDF file drop zone with drag-and-drop support, Generate button (disabled until key + file present)
    - Progress panel: replaces form after submit; shows each phase as a list item with animated spinner → checkmark on completion; displays the human-readable message next to each phase
    - Clean hover states, focus rings, button transitions
  - Files: `frontend/src/App.jsx`, `frontend/src/App.css`, `frontend/index.html` (Google Fonts link)

- [ ] Task 8: Wire frontend to backend — SSE streaming + download + Open in Colab (P0)
  - Acceptance:
    - On submit: POST to `/generate`, get `job_id`, open `EventSource` to `/status/{job_id}`
    - Each SSE event updates the progress panel in real-time
    - On `done` event: decode base64 notebook, trigger browser download of `.ipynb`; if `colab_url` present in event, show "Open in Colab ↗" button linking to that URL in a new tab
    - On `error` event: show error message in red beneath progress panel; re-enable form
  - Files: `frontend/src/App.jsx`

---

### P1 — Open in Colab + polish

- [ ] Task 9: Implement GitHub Gist upload for Open in Colab (P1)
  - Acceptance: If `github_token` provided, pipeline uploads the `.ipynb` to a new public GitHub Gist via `api.github.com/gists`; extracts gist ID; constructs `https://colab.research.google.com/gist/{username}/{gist_id}` URL; includes `colab_url` in the `done` SSE event
  - Files: `backend/gist_uploader.py`, update `backend/pipeline.py`

- [ ] Task 10: Write README with setup and usage instructions (P1)
  - Acceptance: README covers: prerequisites (Python 3.10+, Node 18+), install steps for backend and frontend, how to run both servers, how to use the app, what "Open in Colab" requires, model fallback note
  - Files: `README.md`
