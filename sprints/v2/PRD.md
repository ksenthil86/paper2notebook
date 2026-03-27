# Sprint v2 — PRD: Security Hardening

## Overview
Fix all High and Medium findings from the v1 security review, plus one Low finding and a housekeeping item that reduce the DoS attack surface. No new user-facing features. After this sprint the app is safe to share beyond localhost.

## Goals
- A crafted PDF upload cannot exhaust server RAM or trigger unlimited Gemini API calls
- A user's GitHub token cannot leak back to the browser in an error message
- Browsers receive standard security headers on every response
- FastAPI's auto-generated API docs are not exposed in production
- PDF content passed to Gemini is wrapped in adversarial-hardened delimiters
- Stale jobs are automatically evicted from the in-memory store after 45 minutes

## Security Findings Addressed

| ID | Severity | Finding |
|----|----------|---------|
| H1 | 🔴 High | No upload size limit — RAM exhaustion DoS via large PDF |
| H2 | 🔴 High | No rate limiting on `/generate` — unlimited Gemini API calls |
| M1 | 🟠 Medium | Prompt injection via PDF content sent verbatim to Gemini |
| M2 | 🟠 Medium | GitHub token and internal detail leak in SSE error messages |
| M3 | 🟠 Medium | Missing HTTP security headers (X-Frame-Options, CSP, etc.) |
| M4 | 🟠 Medium | `/docs` and `/openapi.json` exposed by default |
| M5 | 🟠 Medium | CORS: `allow_credentials=True` with wildcard methods/headers |
| L1 | 🟡 Low | `colab_url` used as `href` without URL scheme validation |

## User Stories
- As a server operator, I want upload size capped at 20 MB so a single bad request can't crash the process
- As a server operator, I want rate limiting per IP so one user can't exhaust the thread pool
- As a user, I want my GitHub token to never appear in browser-visible error messages
- As a security-conscious user, I want my browser to receive standard security headers
- As a researcher, I want my PDF content treated as untrusted input in the AI prompt so a malicious PDF can't hijack the model's instructions

## Technical Architecture

All changes are backend-only except L1 (frontend URL validation). No new services or dependencies beyond `slowapi` for rate limiting.

```
┌─────────────────────────────────────────────────────┐
│                    FastAPI (main.py)                │
│                                                     │
│  SecurityHeadersMiddleware  ← NEW (M3)              │
│  SlowAPI rate limiter       ← NEW (H2)              │
│  CORSMiddleware             ← TIGHTENED (M5)        │
│  docs_url=None              ← ADDED (M4)            │
│                                                     │
│  POST /generate                                     │
│    └─ 20 MB size check      ← NEW (H1)             │
│    └─ content-type check    ← NEW (H1)              │
│    └─ rate limit: 10/min/IP ← NEW (H2)             │
│                                                     │
│  GET /status/{job_id}                               │
│    └─ SSE stream                                    │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│                   pipeline.py                       │
│    error handler: sanitise exc message  ← NEW (M2)  │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│             notebook_generator.py                   │
│    PDF text wrapped in <paper>...</paper> tags       │
│    + adversarial framing instruction  ← NEW (M1)    │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│                   job_store.py                      │
│    TTL eviction thread: delete jobs > 45 min ← NEW  │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│                 frontend/App.jsx                    │
│    colab_url validated before use as href ← NEW (L1)│
└─────────────────────────────────────────────────────┘
```

## Out of Scope (v3+)
- Docker / production deployment config
- Authentication / user accounts
- Redis-backed job store for horizontal scaling
- Streaming token-by-token Gemini output
- Private Colab sharing via Google Drive API
- Persistent job history

## Dependencies
- v1 fully complete ✅
- New Python dependency: `slowapi` (rate limiting for FastAPI/Starlette)
- No new frontend dependencies
