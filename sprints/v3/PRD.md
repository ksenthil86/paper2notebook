# Sprint v3 — PRD: Production-Ready

## Overview
Make Paper2Notebook production-ready across three dimensions: a complete testing pyramid (unit → integration → E2E → real smoke test), a GitHub Actions CI/CD pipeline that blocks merges on any failure, and Docker + AWS ECS Fargate deployment with Terraform-managed infrastructure. After this sprint the app can be shared publicly, deployed repeatably, and tested automatically on every push.

## Goals
- Testing pyramid at target ratios: ~70% unit (≥120), ~20% integration (≥35), ~10% E2E (≥15); plus one real-API smoke test gated behind `--real` flag
- GitHub Actions runs on every push and PR: pytest, Playwright, semgrep, pip-audit — all blocking
- `docker compose up` starts the full stack locally in one command
- `terraform apply` provisions AWS ECS Fargate (backend) + CloudFront/S3 (frontend) from scratch
- CD pipeline auto-deploys to AWS on every merge to `main` (after all CI checks pass)

## New Feature: arXiv URL Input Mode
The current app only accepts uploaded PDFs. v3 adds a second input mode: paste an arXiv URL (e.g. `https://arxiv.org/abs/1706.03762`) and the backend fetches the PDF automatically. This unlocks the full testing pyramid — the E2E test can use a stable arXiv URL instead of a local file path, and the real smoke test uses the "Attention Is All You Need" paper by URL.

## User Stories
- As a researcher, I want to paste an arXiv URL instead of uploading a PDF, so I don't need to download the file first
- As a developer, I want every push to run all tests automatically, so regressions are caught before merge
- As an operator, I want `docker compose up` to start the full stack so onboarding new contributors is a single command
- As an operator, I want merges to `main` to automatically deploy to AWS so the live app stays current without manual steps
- As a QA engineer, I want a headed browser test that generates a real notebook end-to-end so I can verify quality before a release

## Technical Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   GitHub (source of truth)                  │
│                                                             │
│  push/PR → GitHub Actions CI:                               │
│    ├── pytest (unit + integration)                          │
│    ├── playwright (E2E headless)                            │
│    ├── semgrep + bandit + pip-audit                         │
│    └── [on main merge] CD: push to ECR → update ECS        │
└───────────────────────┬─────────────────────────────────────┘
                        │ deploy
┌───────────────────────▼─────────────────────────────────────┐
│                        AWS (Terraform-managed)              │
│                                                             │
│  CloudFront ──▶ S3 (frontend static)                        │
│                                                             │
│  ALB ──▶ ECS Fargate (backend FastAPI)                      │
│           └── ECR image: paper2notebook-backend             │
│           └── Task env: GEMINI_API_KEY (ECS Secrets/SSM)    │
└─────────────────────────────────────────────────────────────┘

Local Dev / Docker:
┌─────────────────────────────────────────────────────────────┐
│  docker-compose.yml                                         │
│    backend:  Dockerfile.backend → uvicorn :8000             │
│    frontend: Dockerfile.frontend → nginx :80 → proxy :8000  │
└─────────────────────────────────────────────────────────────┘

New backend module:
  arxiv_fetcher.py
    fetch_arxiv_pdf(url: str) -> bytes
    - Normalises arxiv.org/abs/ID → arxiv.org/pdf/ID
    - httpx GET with User-Agent, 30s timeout
    - Validates %PDF- header on response
    - Returns raw PDF bytes (same type as upload path)
```

## Testing Pyramid (target after v3)

| Layer | Count | % | What |
|-------|-------|---|------|
| Unit | ≥ 120 | ~70% | `arxiv_fetcher`, `pdf_parser`, `notebook_generator`, `notebook_builder`, `gist_uploader`, `pipeline`, `job_store` edge cases |
| Integration | ≥ 35 | ~20% | `/generate` (PDF upload), `/generate` (arXiv URL), `/status` SSE, all with mocked Gemini |
| E2E (mocked) | ≥ 15 | ~9% | Playwright headless; both input modes, progress panel, download, error states |
| Smoke (real) | 1 | ~1% | Headed Playwright; real Gemini API; validates notebook JSON structure, 8 sections, valid Python cells |

The smoke test is gated: only runs with `pytest -m real --real-pdf <path>` or `REAL_PDF_PATH` env var. **Never runs in CI.**

## Module Changes

| File | Change |
|------|--------|
| `backend/arxiv_fetcher.py` | **NEW** — fetches PDF bytes from arXiv URL |
| `backend/main.py` | Add `arxiv_url` optional form field; call `fetch_arxiv_pdf` when present |
| `frontend/src/App.jsx` | Add tab toggle: "Upload PDF" ↔ "arXiv URL" |
| `.github/workflows/ci.yml` | **NEW** — pytest + semgrep + pip-audit |
| `.github/workflows/e2e.yml` | **NEW** — Playwright headless |
| `.github/workflows/cd.yml` | **NEW** — build Docker images + push ECR + update ECS |
| `Dockerfile.backend` | **NEW** |
| `Dockerfile.frontend` | **NEW** — Vite build + nginx |
| `docker-compose.yml` | **NEW** |
| `terraform/` | **NEW** — ECR, ECS, ALB, S3, CloudFront, IAM |

## Out of Scope (v4+)
- Streaming token-by-token Gemini output
- User accounts / persistent job history
- Redis-backed job store (in-memory is fine for single-instance ECS)
- Private Colab sharing via Google Drive API
- Custom domain / TLS certificate management (ACM)
- Multi-region deployment

## Dependencies
- v1 + v2 complete ✅
- GitHub CLI (`gh`) installed locally for Task 10 (branch protection setup)
- AWS IAM user `paper-to-notebook-deploy` created with ECR push + ECS update permissions ✅
- AWS credentials stored in `aws_cred.md` (gitignored) — must be set as GitHub Actions secrets before CD task
- "Attention Is All You Need" PDF available locally for smoke test (path configured via env var, not hardcoded)
