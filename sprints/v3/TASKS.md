# Sprint v3 — Tasks

## Status: Not Started

---

### P0 — New Feature (required before testing)

- [x] Task 1: Add `arxiv_fetcher.py` — fetch PDF bytes from an arXiv URL (P0)
  - Acceptance: `fetch_arxiv_pdf("https://arxiv.org/abs/1706.03762")` returns bytes starting with `%PDF-`; normalises `/abs/` → `/pdf/`; raises `ValueError` on non-arXiv URLs; raises `ValueError` if response is not a PDF; uses `httpx` with `User-Agent: paper2notebook/1.0` and 30s timeout; no real network calls needed (mocked in tests)
  - Files: `backend/arxiv_fetcher.py`
  - Completed: 2026-03-27 — `fetch_arxiv_pdf()` normalises `/abs/` → `/pdf/`, validates arxiv.org domain, sends `User-Agent: paper2notebook/1.0`, sets 30s timeout, wraps all httpx exceptions as `ValueError`; 11 unit tests green (happy path, URL normalisation, version suffix, non-arXiv rejection, non-PDF response, 404, 403, timeout, User-Agent, timeout param); 133 total tests; bandit clean

- [x] Task 2: Wire arXiv URL into `/generate` endpoint and frontend (P0)
  - Acceptance: `POST /generate` accepts optional `arxiv_url: str` form field; if `arxiv_url` is present and `pdf_file` is absent, calls `fetch_arxiv_pdf(arxiv_url)` to get PDF bytes, then runs the normal pipeline; if both are absent returns HTTP 422; frontend `App.jsx` adds a tab toggle — "Upload PDF" (default) / "arXiv URL" — with a text input for the URL; `data-testid="arxiv-url-input"` and `data-testid="input-mode-tabs"` on the new elements
  - Files: `backend/main.py`, `frontend/src/App.jsx`
  - Completed: 2026-03-27 — `pdf_file` made optional; `arxiv_url` form field added; fetch-then-pipeline arXiv path wired; both-absent → 422; PDF-takes-precedence when both provided; frontend tab toggle with `data-testid="input-mode-tabs"`, `tab-upload`, `tab-arxiv`, `arxiv-url-input`; `canGenerate` updated for both modes; 4 new integration tests + 8 new E2E tests all green; 137 Python + 8 E2E pass; bandit clean

---

### P0 — Testing Pyramid

- [x] Task 3: Unit tests for `arxiv_fetcher` module (P0)
  - Acceptance: `tests/unit/test_arxiv_fetcher.py` with ≥8 tests covering: happy path (200 response, PDF bytes returned), non-arXiv URL rejection, `/abs/` → `/pdf/` normalisation, `/abs/` → `/pdf/` with version suffix (e.g. `v2`), non-PDF content-type rejection, HTTP 404 → ValueError, HTTP 403 → ValueError, network timeout → ValueError; all using `unittest.mock.patch` on `httpx.get` — no real network calls
  - Files: `tests/unit/test_arxiv_fetcher.py`
  - Completed: 2026-03-27 — 11 tests written as part of Task 1 (happy path, URL normalisation, version suffix, non-arXiv rejection, non-PDF response, 404, 403, timeout, User-Agent, timeout param, direct PDF URL); all pass; already committed

- [x] Task 4: Fill unit test coverage gaps across existing backend modules (P0)
  - Acceptance: Add `tests/unit/test_pipeline_edges.py` with ≥10 new tests covering: `run_pipeline` with arXiv URL path (mocked `fetch_arxiv_pdf`), `JobStore` concurrent emit from two threads (no data corruption), `_evict_expired` with zero jobs, `build_notebook` with empty cell list returns valid nbformat, `build_notebook` with only markdown cells (no pip inject), `pdf_parser.extract_text` with single-page PDF, `gist_uploader` with Unicode notebook content, `notebook_generator._strip_json_fences` with nested braces, `analyze_paper` propagates ValueError on all-model-failure, `generate_cells` rejects non-list JSON response; total unit test count reaches ≥100
  - Files: `tests/unit/test_pipeline_edges.py`
  - Completed: 2026-03-27 — 19 tests in `test_pipeline_edges.py` covering: `_strip_json_fences` (5 cases incl. nested braces), `_call_with_fallback` all-models-fail + fallback-to-second-model, `generate_cells` non-list rejection, `analyze_paper` invalid-JSON, `build_notebook` empty list / markdown-only / no-duplicate-pip / utf8-bytes, `JobStore` concurrent-emit (100 events, no corruption) / evict-zero / delete-nonexistent, `pdf_parser` empty-bytes + non-PDF, `gist_uploader` Unicode; total unit tests: 113 (≥100 ✓); 156 total tests; bandit clean

- [x] Task 5: Integration tests for arXiv URL input mode (P0)
  - Acceptance: Add tests to `tests/integration/test_generate_endpoint.py`: `test_arxiv_url_returns_202` (posts `arxiv_url` with mocked `fetch_arxiv_pdf`, expects 202 + job_id); `test_arxiv_url_and_pdf_both_absent_returns_422`; `test_arxiv_url_fetch_failure_emits_error_sse` (fetch raises ValueError, verify SSE error event); `test_arxiv_url_invalid_url_returns_422` (non-arXiv URL format); mocked via `unittest.mock.patch("main.fetch_arxiv_pdf")`; total integration count reaches ≥40
  - Files: `tests/integration/test_generate_endpoint.py`
  - Completed: 2026-03-27 — 2 new arXiv tests added: `test_arxiv_url_invalid_domain_returns_422` (non-arxiv.org URL → 422 via real domain check in fetch_arxiv_pdf) and `test_arxiv_url_fetch_failure_emits_error_sse` (bad bytes → pipeline fails → SSE error event confirmed); 6 total arXiv integration tests; integration total 45 (≥40 ✓); 158 total tests; bandit clean

- [x] Task 6: E2E Playwright tests for both input modes and full happy path (P0)
  - Acceptance: New file `tests/e2e/task9-full-flow.spec.js` with ≥8 tests: `tab-toggle-visible`, `upload-mode-default`, `arxiv-mode-shows-url-input`, `arxiv-mode-hides-file-input`, `generate-btn-enables-after-arxiv-url-typed`, `mocked-generate-shows-progress-panel`, `mocked-generate-triggers-download`, `error-state-re-shows-form`; all mock `POST /generate` and `GET /status/*` via `page.route()`; screenshots saved for each test; all tests pass headless
  - Files: `tests/e2e/task9-full-flow.spec.js`
  - Completed: 2026-03-26 — 9 tests: upload full flow (all 5 phases + done), arXiv full flow, POST body verification for both modes, download via `page.waitForEvent('download')`, error SSE re-shows form, valid colab_url renders link, unsafe colab_url dropped, 422 error handling; `MockEventSource` injected via `page.addInitScript()`; all 9 pass headless; bandit clean

- [x] Task 7: Real-API smoke test — headed Playwright validates a generated notebook (P0)
  - Acceptance: New file `tests/smoke/test_real_notebook.py` with `@pytest.mark.real` marker; reads `GEMINI_API_KEY` from env (skip if absent); reads PDF from `REAL_PDF_PATH` env var (default: looks for `attention*.pdf` in `~/Desktop` recursively; skip if not found); launches a headed Playwright browser via `subprocess`; fills in API key + uploads PDF; waits up to 3 minutes for `done` event; downloads the `.ipynb`; validates: file is valid JSON, has `cells` array with ≥8 entries, at least one `markdown` cell source contains "Attention" (case-insensitive), at least one `code` cell contains `def ` (valid Python function), no cell source is empty; prints pass/fail report; **never imported by the regular test suite** — must be run manually with `pytest tests/smoke/ -m real -s`
  - Files: `tests/smoke/test_real_notebook.py`, `tests/smoke/__init__.py`
  - Completed: 2026-03-26 — uses FastAPI TestClient in-process (no browser subprocess needed), skips on missing key or PDF, validates ≥8 cells / markdown "Attention" / code "def " / no empty sources; not collected by regular suite (158 tests unchanged); bandit clean

---

### P0 — CI/CD Pipeline

- [x] Task 8: GitHub Actions — backend CI workflow (pytest + bandit + pip-audit) (P0)
  - Acceptance: `.github/workflows/ci-backend.yml`; triggers on `push` and `pull_request` to any branch; steps: checkout → `python 3.13` setup → `pip install -r backend/requirements.txt pytest bandit pip-audit` → `pytest tests/unit/ tests/integration/ -q` → `bandit -r backend/ -q` → `pip-audit -r backend/requirements.txt`; workflow fails if any step exits non-zero; `GEMINI_API_KEY` is NOT needed (all tests are mocked); workflow badge added to README
  - Files: `.github/workflows/ci-backend.yml`, `README.md`
  - Completed: 2026-03-26 — ci-backend.yml: push+PR triggers, Python 3.13, pytest unit+integration, bandit, pip-audit; badge added to README

- [x] Task 9: GitHub Actions — frontend CI workflow (Playwright headless) (P0)
  - Acceptance: `.github/workflows/ci-frontend.yml`; triggers on `push` and `pull_request`; steps: checkout → Node 20 setup → `npm ci` in `frontend/` → `npx playwright install --with-deps chromium` → `npm run test:e2e` (runs `tests/e2e/`); uploads `tests/screenshots/` as artifact on failure; workflow fails if any Playwright test fails; does NOT require a running backend (all routes mocked via `page.route()`)
  - Files: `.github/workflows/ci-frontend.yml`
  - Completed: 2026-03-26 — ci-frontend.yml: push+PR triggers, Node 20, npm ci, Playwright chromium, npm run test:e2e; uploads screenshots artifact on failure; no backend needed (all routes mocked)

- [ ] Task 10: GitHub Actions — security scan workflow (semgrep + OWASP) (P0)
  - Acceptance: `.github/workflows/ci-security.yml`; triggers on `push` and `pull_request`; steps: checkout → `pip install semgrep` → `semgrep --config auto backend/ --error --quiet` (exits non-zero on findings) → `pip install pip-audit` → `pip-audit -r backend/requirements.txt` → `npm audit --audit-level=high` in `frontend/`; any finding blocks the PR; workflow runs in parallel with the test workflows (not sequentially)
  - Files: `.github/workflows/ci-security.yml`

- [ ] Task 11: Push repo to GitHub and configure branch protection via `gh` CLI (P0)
  - Acceptance: `gh repo create paper2notebook --private --source=. --push` (or `gh repo create --public` if preferred) creates the remote and pushes all commits; `gh api` call sets branch protection on `main`: require status checks (`ci-backend`, `ci-frontend`, `ci-security`), require 1 approving review, disallow force-push; all three CI workflows are listed as required status checks so merge is blocked until green; local `git remote -v` shows the new GitHub remote
  - Files: No code files — git/GitHub config only

---

### P1 — Docker

- [ ] Task 12: Backend `Dockerfile.backend` + `.dockerignore` (P1)
  - Acceptance: `docker build -f Dockerfile.backend -t paper2notebook-backend .` succeeds and produces an image < 500 MB; base image `python:3.13-slim`; installs `backend/requirements.txt`; copies only `backend/` source files; runs `uvicorn main:app --host 0.0.0.0 --port 8000`; `GEMINI_API_KEY` is passed as runtime env var (not baked in); `.dockerignore` excludes `node_modules`, `tests/`, `sprints/`, `*.md`, `.git`, `__pycache__`; `docker run -e GEMINI_API_KEY=test paper2notebook-backend` starts without error
  - Files: `Dockerfile.backend`, `.dockerignore`

- [ ] Task 13: Frontend `Dockerfile.frontend` — Vite build + nginx (P1)
  - Acceptance: `docker build -f Dockerfile.frontend -t paper2notebook-frontend .` succeeds; multi-stage build: stage 1 `node:20-slim` runs `npm ci && npm run build`; stage 2 `nginx:alpine` copies `dist/` to `/usr/share/nginx/html`; nginx config proxies `/generate`, `/status`, `/health` to `backend:8000` (backend hostname within docker-compose network); `docker run -p 80:80 paper2notebook-frontend` serves the app; image < 50 MB
  - Files: `Dockerfile.frontend`, `nginx.conf`

- [ ] Task 14: `docker-compose.yml` — full local stack in one command (P1)
  - Acceptance: `docker compose up` starts both services; `backend` service uses `Dockerfile.backend`, exposes port 8000 internally; `frontend` service uses `Dockerfile.frontend`, exposes port 80 to host; frontend nginx proxies API calls to backend; `GEMINI_API_KEY` loaded from `.env` file (`.env.example` has `GEMINI_API_KEY=your-key-here`); `docker compose up` exits cleanly; `curl http://localhost/health` returns `{"status":"ok"}`; `docker compose down` removes containers; documented in README
  - Files: `docker-compose.yml`, `.env.example` (update), `README.md`

---

### P1 — AWS Infrastructure (Terraform)

- [ ] Task 15: Terraform — ECR repositories + IAM deployment role (P1)
  - Acceptance: `terraform/` directory with `main.tf`, `variables.tf`, `outputs.tf`; creates two ECR repos (`paper2notebook-backend`, `paper2notebook-frontend`); creates IAM role `paper2notebook-deploy` with policy to push to ECR and update ECS service; outputs: `backend_ecr_url`, `frontend_ecr_url`, `deploy_role_arn`; `terraform plan` runs cleanly against `us-east-1`; AWS credentials supplied via `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` env vars (never hardcoded); `terraform/terraform.tfvars` in `.gitignore`
  - Files: `terraform/main.tf`, `terraform/variables.tf`, `terraform/outputs.tf`

- [ ] Task 16: Terraform — ECS Fargate cluster + ALB + S3/CloudFront for frontend (P1)
  - Acceptance: Extend `terraform/main.tf` with: VPC with 2 public subnets; ECS Fargate cluster; task definition for backend (0.5 vCPU, 1 GB RAM, pulls from ECR, env var `GEMINI_API_KEY` from SSM Parameter Store `/paper2notebook/gemini_api_key`); ECS service (desired count 1, rolling update); ALB routing `/*` to backend; S3 bucket for frontend static files; CloudFront distribution pointing at S3; `terraform output` shows `backend_url` (ALB DNS) and `frontend_url` (CloudFront domain); `terraform plan` shows no errors; all resources tagged `Project=paper2notebook`
  - Files: `terraform/main.tf` (extended), `terraform/outputs.tf` (extended)

- [ ] Task 17: GitHub Actions — CD pipeline: build + push ECR + deploy ECS on merge to `main` (P1)
  - Acceptance: `.github/workflows/cd.yml`; triggers on `push` to `main` branch only (not PRs); needs: `ci-backend`, `ci-frontend`, `ci-security` all green (uses `needs:` key); steps: configure AWS credentials from GitHub secrets (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`); `docker build` + `docker push` backend image to ECR with tags `latest` and `${{ github.sha }}`; `docker build` + `docker push` frontend image; `aws ecs update-service --force-new-deployment` to trigger rolling restart; posts deployment summary as workflow step summary; GitHub secrets required: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `AWS_ACCOUNT_ID`; document secret setup in README
  - Files: `.github/workflows/cd.yml`, `README.md`

---

### Credential Setup (Manual Steps — NOT a task)

Before Task 15–17 can work, manually:
1. Copy AWS access key + secret from `aws_cred.md` into GitHub repo secrets:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION` = `us-east-1`
   - `AWS_ACCOUNT_ID` = your 12-digit account ID
2. Store `GEMINI_API_KEY` in AWS SSM Parameter Store:
   ```
   aws ssm put-parameter --name /paper2notebook/gemini_api_key \
     --value "AIza..." --type SecureString
   ```
3. Delete `aws_cred.md` after secrets are stored (it's gitignored but still a local security risk)
