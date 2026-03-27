"""Fetch a research paper PDF from an arXiv URL.

Accepts both abstract URLs (arxiv.org/abs/<id>) and direct PDF URLs
(arxiv.org/pdf/<id>), normalising the former to the latter before fetching.
"""
import httpx
from urllib.parse import urlparse


_USER_AGENT = "paper2notebook/1.0 (https://github.com/paper2notebook)"
_TIMEOUT = 30.0  # seconds


def fetch_arxiv_pdf(url: str) -> bytes:
    """Download a PDF from arXiv and return its raw bytes.

    Args:
        url: An arXiv URL in any of these forms:
             - https://arxiv.org/abs/1706.03762
             - https://arxiv.org/abs/1706.03762v2
             - https://arxiv.org/pdf/1706.03762

    Returns:
        Raw PDF bytes (starts with b"%PDF-").

    Raises:
        ValueError: If the URL is not on arxiv.org, the HTTP request fails,
                    or the response body is not a PDF.
    """
    parsed = urlparse(url)
    if "arxiv.org" not in parsed.netloc:
        raise ValueError(
            f"URL must be on arxiv.org, got: {parsed.netloc!r}"
        )

    # Normalise /abs/<id> → /pdf/<id>
    path = parsed.path
    if path.startswith("/abs/"):
        path = "/pdf/" + path[len("/abs/"):]

    pdf_url = f"https://arxiv.org{path}"

    try:
        response = httpx.get(
            pdf_url,
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise ValueError(f"Request timed out fetching {pdf_url}: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise ValueError(
            f"arXiv returned HTTP {exc.response.status_code} for {pdf_url}"
        ) from exc
    except httpx.RequestError as exc:
        raise ValueError(f"Network error fetching {pdf_url}: {exc}") from exc

    content = response.content
    if not content.startswith(b"%PDF-"):
        raise ValueError(
            f"Response from {pdf_url} is not a PDF "
            f"(starts with {content[:8]!r})"
        )

    return content
