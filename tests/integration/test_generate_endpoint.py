"""Task 2 — Integration tests: POST /generate and GET /status/{job_id}."""
import sys
import os
import io
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


def _minimal_pdf_bytes() -> bytes:
    """Return a minimal valid PDF as bytes (no external file needed)."""
    pdf = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 44>>stream
BT /F1 12 Tf 100 700 Td (Hello World) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000274 00000 n
0000000368 00000 n
trailer<</Size 6/Root 1 0 R>>
startxref
441
%%EOF"""
    return pdf


# ── /generate endpoint ──────────────────────────────────────────────────────

class TestGenerateEndpoint:

    def test_missing_api_key_returns_422(self, client):
        """Request without api_key field returns 422 Unprocessable Entity."""
        resp = client.post(
            "/generate",
            files={"pdf_file": ("test.pdf", io.BytesIO(_minimal_pdf_bytes()), "application/pdf")},
        )
        assert resp.status_code == 422

    def test_missing_pdf_returns_422(self, client):
        """Request without pdf_file field returns 422."""
        resp = client.post("/generate", data={"api_key": "sk-test"})
        assert resp.status_code == 422

    def test_valid_request_returns_job_id(self, client):
        """Valid request returns 202 with a job_id string."""
        resp = client.post(
            "/generate",
            data={"api_key": "sk-test"},
            files={"pdf_file": ("paper.pdf", io.BytesIO(_minimal_pdf_bytes()), "application/pdf")},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body
        assert isinstance(body["job_id"], str)
        assert len(body["job_id"]) > 0

    def test_optional_github_token_accepted(self, client):
        """github_token is optional — request with it should still return 202."""
        resp = client.post(
            "/generate",
            data={"api_key": "sk-test", "github_token": "ghp_test"},
            files={"pdf_file": ("paper.pdf", io.BytesIO(_minimal_pdf_bytes()), "application/pdf")},
        )
        assert resp.status_code == 202
        assert "job_id" in resp.json()

    def test_response_is_immediate(self, client):
        """Response arrives quickly — job runs in background, not blocking."""
        start = time.time()
        client.post(
            "/generate",
            data={"api_key": "sk-test"},
            files={"pdf_file": ("paper.pdf", io.BytesIO(_minimal_pdf_bytes()), "application/pdf")},
        )
        elapsed = time.time() - start
        assert elapsed < 2.0, f"Response took {elapsed:.2f}s — should be near-instant"


# ── /status/{job_id} SSE endpoint ───────────────────────────────────────────

class TestStatusEndpoint:

    def _post_and_get_job_id(self, client) -> str:
        resp = client.post(
            "/generate",
            data={"api_key": "sk-test"},
            files={"pdf_file": ("paper.pdf", io.BytesIO(_minimal_pdf_bytes()), "application/pdf")},
        )
        assert resp.status_code == 202
        return resp.json()["job_id"]

    def test_unknown_job_returns_404(self, client):
        """GET /status/nonexistent returns 404."""
        resp = client.get("/status/nonexistent-job-id")
        assert resp.status_code == 404

    def test_status_returns_sse_content_type(self, client):
        """GET /status/{job_id} streams text/event-stream content."""
        job_id = self._post_and_get_job_id(client)
        with client.stream("GET", f"/status/{job_id}") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_sse_emits_valid_json_events(self, client):
        """SSE stream emits at least one 'data: {...}' line with valid JSON."""
        job_id = self._post_and_get_job_id(client)
        events = []
        with client.stream("GET", f"/status/{job_id}") as resp:
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    payload = line[len("data:"):].strip()
                    data = json.loads(payload)
                    events.append(data)
                    if data.get("phase") in ("done", "error"):
                        break

        assert len(events) > 0, "No SSE events received"

    def test_sse_events_have_required_fields(self, client):
        """Each SSE event has 'phase' and 'message' keys."""
        job_id = self._post_and_get_job_id(client)
        with client.stream("GET", f"/status/{job_id}") as resp:
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    data = json.loads(line[len("data:"):].strip())
                    assert "phase" in data, f"Missing 'phase' in event: {data}"
                    assert "message" in data, f"Missing 'message' in event: {data}"
                    if data["phase"] in ("done", "error"):
                        break

    def test_job_store_importable(self):
        """job_store module is importable and has expected interface."""
        from job_store import JobStore
        store = JobStore()
        job_id = store.create_job()
        assert job_id is not None
        job = store.get_job(job_id)
        assert job is not None

    def test_job_store_emit_and_read(self):
        """JobStore.emit() queues an event; get_events() retrieves it."""
        from job_store import JobStore
        store = JobStore()
        job_id = store.create_job()
        store.emit(job_id, "parsing", "Parsing PDF...")
        events = store.get_events(job_id)
        assert len(events) >= 1
        assert events[0]["phase"] == "parsing"
        assert events[0]["message"] == "Parsing PDF..."


# ── v2: Upload size and content-type enforcement ─────────────────────────────

MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB


class TestUploadValidation:

    def test_oversized_upload_returns_413(self, client):
        """A file exceeding 20 MB returns HTTP 413 before body is processed."""
        oversized = b"%PDF-1.4 " + b"x" * (MAX_PDF_BYTES + 1)
        resp = client.post(
            "/generate",
            data={"api_key": "sk-test"},
            files={"pdf_file": ("big.pdf", io.BytesIO(oversized), "application/pdf")},
        )
        assert resp.status_code == 413

    def test_exactly_20mb_is_accepted(self, client):
        """A file exactly at the 20 MB limit is not rejected by the size check."""
        exact = b"%PDF-1.4 " + b"x" * (MAX_PDF_BYTES - 9)
        resp = client.post(
            "/generate",
            data={"api_key": "sk-test"},
            files={"pdf_file": ("exact.pdf", io.BytesIO(exact), "application/pdf")},
        )
        # 202 or pipeline-error (invalid PDF content) — but NOT 413
        assert resp.status_code != 413

    def test_non_pdf_content_type_returns_415(self, client):
        """A file uploaded with text/plain content-type returns HTTP 415."""
        resp = client.post(
            "/generate",
            data={"api_key": "sk-test"},
            files={"pdf_file": ("paper.txt", io.BytesIO(b"not a pdf"), "text/plain")},
        )
        assert resp.status_code == 415

    def test_octet_stream_content_type_returns_415(self, client):
        """application/octet-stream (generic binary) is also rejected as non-PDF."""
        resp = client.post(
            "/generate",
            data={"api_key": "sk-test"},
            files={"pdf_file": ("paper.bin", io.BytesIO(b"%PDF-fake"), "application/octet-stream")},
        )
        assert resp.status_code == 415

    def test_valid_pdf_content_type_passes_validation(self, client):
        """A properly typed application/pdf upload passes both validations."""
        resp = client.post(
            "/generate",
            data={"api_key": "sk-test"},
            files={"pdf_file": ("paper.pdf", io.BytesIO(_minimal_pdf_bytes()), "application/pdf")},
        )
        assert resp.status_code == 202


# ── v2: Security headers + FastAPI hardening (M3, M4, M5) ───────────────────

class TestSecurityHeaders:

    def test_x_content_type_options_nosniff(self, client):
        """Every response must include X-Content-Type-Options: nosniff."""
        resp = client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options_deny(self, client):
        """Every response must include X-Frame-Options: DENY."""
        assert client.get("/health").headers.get("x-frame-options") == "DENY"

    def test_referrer_policy(self, client):
        """Every response must include Referrer-Policy."""
        val = client.get("/health").headers.get("referrer-policy", "")
        assert val == "strict-origin-when-cross-origin"

    def test_docs_url_disabled(self, client):
        """GET /docs must return 404 (docs disabled in production)."""
        assert client.get("/docs").status_code == 404

    def test_redoc_url_disabled(self, client):
        """GET /redoc must return 404."""
        assert client.get("/redoc").status_code == 404

    def test_openapi_json_disabled(self, client):
        """GET /openapi.json must return 404."""
        assert client.get("/openapi.json").status_code == 404

    def test_cors_allows_get_and_post(self, client):
        """Preflight for GET and POST from allowed origin succeeds."""
        for method in ("GET", "POST"):
            resp = client.options(
                "/health",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": method,
                },
            )
            assert resp.status_code in (200, 204)

    def test_cors_blocks_arbitrary_method(self, client):
        """Preflight for DELETE is not in the allowed methods list."""
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "DELETE",
            },
        )
        # The browser will see no Access-Control-Allow-Methods: DELETE
        allow = resp.headers.get("access-control-allow-methods", "")
        assert "DELETE" not in allow


# ── v2: Rate limiting ────────────────────────────────────────────────────────

def _generate_request(client):
    """Helper: POST a valid /generate request."""
    return client.post(
        "/generate",
        data={"api_key": "sk-test"},
        files={"pdf_file": ("paper.pdf", io.BytesIO(_minimal_pdf_bytes()), "application/pdf")},
    )


class TestRateLimiting:

    def test_requests_within_limit_return_202(self, client):
        """First request is accepted (well within the 10/minute limit)."""
        resp = _generate_request(client)
        assert resp.status_code == 202

    def test_eleventh_request_returns_429(self, client):
        """After 10 successful requests the 11th is rate-limited (429)."""
        for i in range(10):
            r = _generate_request(client)
            assert r.status_code == 202, f"Request {i+1} unexpectedly rejected: {r.status_code}"
        resp = _generate_request(client)
        assert resp.status_code == 429

    def test_rate_limit_response_has_retry_after_header(self, client):
        """429 response includes a Retry-After header."""
        for _ in range(10):
            _generate_request(client)
        resp = _generate_request(client)
        assert resp.status_code == 429
        assert "retry-after" in {h.lower() for h in resp.headers}


# ── v3: arXiv URL input mode ──────────────────────────────────────────────────

class TestArxivUrlEndpoint:

    def test_arxiv_url_returns_202(self, client):
        """POST /generate with arxiv_url (no pdf_file) returns 202 with job_id."""
        from unittest.mock import patch
        fake_pdf = b"%PDF-1.4 fake"
        with patch("main.fetch_arxiv_pdf", return_value=fake_pdf):
            resp = client.post(
                "/generate",
                data={"api_key": "sk-test", "arxiv_url": "https://arxiv.org/abs/1706.03762"},
            )
        assert resp.status_code == 202
        assert "job_id" in resp.json()

    def test_neither_pdf_nor_arxiv_returns_422(self, client):
        """POST /generate with no pdf_file and no arxiv_url returns 422."""
        resp = client.post("/generate", data={"api_key": "sk-test"})
        assert resp.status_code == 422

    def test_pdf_file_takes_precedence_over_arxiv_url(self, client):
        """When both pdf_file and arxiv_url are provided, pdf_file is used (no fetch call)."""
        from unittest.mock import patch
        with patch("main.fetch_arxiv_pdf") as mock_fetch:
            resp = client.post(
                "/generate",
                data={"api_key": "sk-test", "arxiv_url": "https://arxiv.org/abs/1706.03762"},
                files={"pdf_file": ("paper.pdf", io.BytesIO(_minimal_pdf_bytes()), "application/pdf")},
            )
        assert resp.status_code == 202
        mock_fetch.assert_not_called()

    def test_arxiv_url_fetch_failure_returns_422(self, client):
        """If fetch_arxiv_pdf raises ValueError, endpoint returns 422."""
        from unittest.mock import patch
        with patch("main.fetch_arxiv_pdf", side_effect=ValueError("not a PDF")):
            resp = client.post(
                "/generate",
                data={"api_key": "sk-test", "arxiv_url": "https://arxiv.org/abs/9999.99999"},
            )
        assert resp.status_code == 422

    def test_arxiv_url_invalid_domain_returns_422(self, client):
        """A non-arxiv.org URL is rejected with 422 (fetch_arxiv_pdf raises ValueError for wrong domain)."""
        resp = client.post(
            "/generate",
            data={"api_key": "sk-test", "arxiv_url": "https://evil.com/abs/1706.03762"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body

    def test_arxiv_url_fetch_failure_emits_error_sse(self, client):
        """When arXiv PDF bytes reach the pipeline but PDF is invalid, SSE emits an error event."""
        from unittest.mock import patch
        # Return bytes that look like a valid response but are NOT a valid PDF
        # (missing %PDF- header → pdf_parser raises ValueError → pipeline emits error SSE)
        bad_bytes = b"not-a-pdf-at-all fake content here"
        with patch("main.fetch_arxiv_pdf", return_value=bad_bytes):
            resp = client.post(
                "/generate",
                data={"api_key": "sk-test", "arxiv_url": "https://arxiv.org/abs/1706.03762"},
            )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        # Stream SSE events and verify an error event is eventually emitted
        error_events = []
        with client.stream("GET", f"/status/{job_id}") as stream_resp:
            for line in stream_resp.iter_lines():
                if line.startswith("data:"):
                    event = json.loads(line[len("data:"):].strip())
                    if event.get("phase") == "error":
                        error_events.append(event)
                        break
                    if event.get("phase") == "done":
                        break

        assert len(error_events) == 1, "Expected exactly one error SSE event"
        assert "message" in error_events[0]
