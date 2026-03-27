"""Unit tests: arxiv_fetcher.fetch_arxiv_pdf — all network calls mocked."""
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

import pytest


FAKE_PDF_BYTES = b"%PDF-1.4 fake content"


def _mock_response(content: bytes = FAKE_PDF_BYTES, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from httpx import HTTPStatusError, Request, Response
        resp.raise_for_status.side_effect = HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=MagicMock(status_code=status_code),
        )
    return resp


class TestFetchArxivPdf:

    def test_happy_path_returns_pdf_bytes(self):
        """Valid arXiv abs URL returns bytes starting with %PDF-."""
        from arxiv_fetcher import fetch_arxiv_pdf
        with patch("arxiv_fetcher.httpx.get", return_value=_mock_response()) as mock_get:
            result = fetch_arxiv_pdf("https://arxiv.org/abs/1706.03762")
        assert result == FAKE_PDF_BYTES
        assert result.startswith(b"%PDF-")

    def test_abs_url_normalised_to_pdf_url(self):
        """/abs/ URL is rewritten to /pdf/ before fetching."""
        from arxiv_fetcher import fetch_arxiv_pdf
        with patch("arxiv_fetcher.httpx.get", return_value=_mock_response()) as mock_get:
            fetch_arxiv_pdf("https://arxiv.org/abs/1706.03762")
        called_url = mock_get.call_args[0][0]
        assert "/pdf/" in called_url
        assert "/abs/" not in called_url

    def test_direct_pdf_url_accepted(self):
        """/pdf/ URL is used as-is without double rewrite."""
        from arxiv_fetcher import fetch_arxiv_pdf
        with patch("arxiv_fetcher.httpx.get", return_value=_mock_response()) as mock_get:
            fetch_arxiv_pdf("https://arxiv.org/pdf/1706.03762")
        called_url = mock_get.call_args[0][0]
        assert "1706.03762" in called_url

    def test_version_suffix_preserved(self):
        """arXiv ID with version suffix (e.g. v2) is preserved in the PDF URL."""
        from arxiv_fetcher import fetch_arxiv_pdf
        with patch("arxiv_fetcher.httpx.get", return_value=_mock_response()) as mock_get:
            fetch_arxiv_pdf("https://arxiv.org/abs/1706.03762v2")
        called_url = mock_get.call_args[0][0]
        assert "1706.03762v2" in called_url

    def test_non_arxiv_url_raises_value_error(self):
        """A URL not on arxiv.org raises ValueError immediately (no HTTP call)."""
        from arxiv_fetcher import fetch_arxiv_pdf
        with patch("arxiv_fetcher.httpx.get") as mock_get:
            with pytest.raises(ValueError, match="arxiv.org"):
                fetch_arxiv_pdf("https://example.com/paper.pdf")
        mock_get.assert_not_called()

    def test_non_pdf_response_raises_value_error(self):
        """Response that doesn't start with %PDF- raises ValueError."""
        from arxiv_fetcher import fetch_arxiv_pdf
        with patch("arxiv_fetcher.httpx.get", return_value=_mock_response(b"<html>not a pdf</html>")):
            with pytest.raises(ValueError, match="PDF"):
                fetch_arxiv_pdf("https://arxiv.org/abs/1706.03762")

    def test_http_404_raises_value_error(self):
        """HTTP 404 from arXiv raises ValueError."""
        from arxiv_fetcher import fetch_arxiv_pdf
        with patch("arxiv_fetcher.httpx.get", return_value=_mock_response(b"", 404)):
            with pytest.raises(ValueError):
                fetch_arxiv_pdf("https://arxiv.org/abs/9999.99999")

    def test_http_403_raises_value_error(self):
        """HTTP 403 from arXiv raises ValueError."""
        from arxiv_fetcher import fetch_arxiv_pdf
        with patch("arxiv_fetcher.httpx.get", return_value=_mock_response(b"", 403)):
            with pytest.raises(ValueError):
                fetch_arxiv_pdf("https://arxiv.org/abs/1706.03762")

    def test_network_timeout_raises_value_error(self):
        """Network timeout raises ValueError (not a raw httpx exception)."""
        import httpx
        from arxiv_fetcher import fetch_arxiv_pdf
        with patch("arxiv_fetcher.httpx.get", side_effect=httpx.TimeoutException("timed out")):
            with pytest.raises(ValueError, match="timed out|timeout|network"):
                fetch_arxiv_pdf("https://arxiv.org/abs/1706.03762")

    def test_user_agent_header_sent(self):
        """Request includes a User-Agent header identifying the app."""
        from arxiv_fetcher import fetch_arxiv_pdf
        with patch("arxiv_fetcher.httpx.get", return_value=_mock_response()) as mock_get:
            fetch_arxiv_pdf("https://arxiv.org/abs/1706.03762")
        kwargs = mock_get.call_args[1]
        headers = kwargs.get("headers", {})
        assert any("paper2notebook" in v.lower() for v in headers.values()), \
            f"Expected paper2notebook in User-Agent, got headers: {headers}"

    def test_timeout_parameter_set(self):
        """httpx.get is called with a timeout (not default/unlimited)."""
        from arxiv_fetcher import fetch_arxiv_pdf
        with patch("arxiv_fetcher.httpx.get", return_value=_mock_response()) as mock_get:
            fetch_arxiv_pdf("https://arxiv.org/abs/1706.03762")
        kwargs = mock_get.call_args[1]
        assert "timeout" in kwargs, "timeout kwarg must be set"
        assert kwargs["timeout"] > 0
